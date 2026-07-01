# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the PERMYT demo age-verification requester.

## Project Overview

**verify/** is a PERMYT demo Requester for **age verification**. It is a Django app on port 9015 that subclasses `permyt.PermytClient` from `permyt-api-python` and implements the Requester + Connect endpoints of the PERMYT protocol.

A single page renders a QR code with "scan to verify your age". When the user scans with the PERMYT mobile app, the broker fires `user_connect`, the app immediately submits an access request for the **`is_older.check`** scope with `min_age` locked to `18` (configurable), and a step list animates while polling the broker. On `completed`, the app calls the government provider, parses `{"is_older": true|false}`, and shows a big checkmark (success) or cross (fail) with a "Verify again" button below.

### Sibling project

- `../government` — the Government demo provider (Django) that exposes the `is_older.check` scope and returns `{"is_older": true|false}` for a given `min_age`.

## Commands

### Development

```bash
python -m venv env && source env/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # then fill in secrets
python manage.py migrate                   # apply migrations
python manage.py runserver 9015            # run dev server
```

### Testing

```bash
pytest                                     # all tests
pytest app/core/requests/tests/            # contract tests
pytest -v -k "test_nonce"                  # by keyword
```

### Key generation (one-time)

```bash
mkdir -p keys/connector keys/permyt
openssl ecparam -name prime256v1 -genkey -noout -out keys/connector/private.pem
openssl ec -in keys/connector/private.pem -pubout -out keys/connector/public.pem
# Download PERMYT public key from dashboard -> keys/permyt/public.pem
```

## Architecture

```
verify/
  app/
    mixins/             # AppModel — UUID PK + timestamps, base for all models
    core/
      users/            # User model (kept from harness; demo is anonymous)
      requests/         # PermytClient (requester impl), Nonce, inbound webhook
      verifications/    # Verification model, LoginToken, QR + reset endpoints
      logs/             # Log model with activity context manager
    common/
      pages/            # VerifyView, templates, static (CSS/JS)
    utils/              # Fields, encoders, middleware, authentication, websocket
  settings/             # Django settings (base, dev, test), urls, wsgi, asgi
  conftest.py           # Shared test fixtures
```

### Key classes

| Class                     | File                                    | Role                                                                  |
| ------------------------- | --------------------------------------- | --------------------------------------------------------------------- |
| `AppModel`                | `app/mixins/models.py`                  | Abstract base model (UUID pk, created_at, updated_at)                 |
| `Verification`            | `app/core/verifications/models.py`      | Session-bound age check (status, min_age, is_older, request_id)       |
| `LoginToken`              | `app/core/verifications/models.py`      | QR connect-token bound to a session + Verification                    |
| `Nonce`                   | `app/core/requests/models.py`           | Replay protection (unique nonce values)                               |
| `Log`                     | `app/core/logs/models.py`               | Activity log with context manager, encrypted JSON data, scoped per Verification |
| `PermytClient`            | `app/core/requests/client.py`           | Requester-side client — QR connect, nonce, age-check request lifecycle |
| `PermytInboundView`       | `app/core/requests/views.py`            | Inbound webhook for PERMYT callbacks                                  |
| `RefreshQrView`           | `app/core/verifications/views.py`       | Issues a fresh QR before the connect token expires                    |
| `ResetVerificationView`   | `app/core/verifications/views.py`       | "Verify again" — clears state and returns a new QR                    |
| `VerifyView`              | `app/common/pages/views.py`             | Single-page landing — renders QR + step track                         |

### Request flow

```
GET /  →  VerifyView renders QR + step track
User scans QR with PERMYT mobile
  → Broker POSTs user_connect → PermytInboundView → PermytClient.process_user_connect()
    → binds permyt_user_id to Verification
    → fires request_access({description: "Age verification: confirm at least 18..."})
    → status: AWAITING ; WS event "scanned" / "awaiting_approval"
  → User approves the is_older.check scope on mobile (min_age locked to 18)
  → Broker posts status updates → PermytClient.process_request_status()
    → status: VERIFYING ; WS event "verifying"
    → on completed: call_services(...) → provider /rest/is_older/check/ → {"is_older": bool}
    → status: VERIFIED (is_older=True) or FAILED ; WS event "verified" / "verification_failed"
  → Browser swaps to result pane (big check or cross) with "Verify again" button
```

## Settings

Django settings module is `settings/`. Entry points:

- `manage.py` → `settings.dev`
- `pytest.ini` → `settings.test`
- `settings/wsgi.py` → `settings.dev`

All config via environment variables — see `.env.example`. Demo-specific:

| Variable           | Default          | Purpose                                          |
| ------------------ | ---------------- | ------------------------------------------------ |
| `VERIFY_MIN_AGE`   | `18`             | Threshold sent as locked `min_age` input         |
| `VERIFY_APP_NAME`  | `PERMYT Verify`  | Page title / navbar badge                        |

## Testing

Tests use **pure pytest** (not `django.test.TestCase`). DB-touching tests use `@pytest.mark.django_db`.

Shared fixtures in `conftest.py`:

- `verification` — pre-created Verification
- `mock_permyt_client` — PermytClient with mocked key loading

## Patterns to follow

- All models extend `AppModel` from `app/mixins/models.py`.
- Tests use pytest fixtures from `conftest.py`, not `setUp`/`TestCase`.
- `Log.activity()` context manager for audit-logged operations.
- WebSocket notifications drive the in-page step track in real time.
- Django settings live in `settings/`.

<!-- PERMYT Protocol Reference v1 -->

## PERMYT Protocol Reference

### Actors

| Actor          | Description                                                                                                                                   |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **Broker**     | The PERMYT server (`permyt`). Orchestrates all flows, runs AI scope evaluation, manages consent, brokers tokens. Never sees actual user data. |
| **Requester**  | A service that wants access to user data. Uses the `permyt` SDK (`permyt-api-python`). This project is a Requester.                           |
| **Provider**   | A service that holds user data and issues tokens. Uses the `permyt` SDK.                                                                      |
| **Mobile App** | The user's device (`permyt-mobile`). Used to scan QR codes (connect) and approve/deny access requests.                                        |

### Connect Cycle

Links a Service to a User Profile via QR code. Creates the `ServiceConnection` and materializes `ScopeConsent` records.

```
  Service                    Mobile App                   Broker                        Service
    │                            │                          │                              │
    │  1. generate_connect_token()                          │                              │
    │──────────────────────────► │                          │                              │
    │  Returns: QR payload       │                          │                              │
    │  (signed JWT + JWE data)   │                          │                              │
    │                            │                          │                              │
    │                   2. User scans QR                    │                              │
    │                            │                          │                              │
    │                            │  3. POST /profiles/{id}/connect/                        │
    │                            │  {service_id, payload, proof}                           │
    │                            │─────────────────────────►│                              │
    │                            │                          │                              │
    │                            │              4. Validate proof + nonce + timestamp       │
    │                            │                 Decrypt JWE payload                      │
    │                            │                 Create ServiceConnection                 │
    │                            │                 Materialize ScopeConsent records         │
    │                            │                 (one per scope, copies default_consent_mode)
    │                            │                          │                              │
    │                            │                          │  5. Webhook: action=user_connect
    │                            │                          │  {token (signed JWT), user_id}│
    │                            │                          │─────────────────────────────►│
    │                            │                          │                              │
    │                            │                          │      6. process_user_connect()
    │                            │                          │         Link/create account   │
    │                            │                          │◄─────────────────────────────│
    │                            │                          │                              │
    │                            │  7. Return service response                             │
    │                            │◄─────────────────────────│                              │
```

### Request Access Cycle

A Requester asks for user data. Broker evaluates scopes via AI, routes user approval, and brokers encrypted tokens between Requester and Provider(s).

```
  Requester                  Broker                     Mobile App                  Provider
    │                          │                            │                          │
    │  1. POST /access         │                            │                          │
    │  {user_id, purpose,      │                            │                          │
    │   details, callback_url} │                            │                          │
    │  (signed + encrypted)    │                            │                          │
    │─────────────────────────►│                            │                          │
    │                          │                            │                          │
    │  ◄── {request_id, status: QUEUED}                     │                          │
    │                          │                            │                          │
    │              2. AI scope evaluation                    │                          │
    │                 Determines minimum scopes needed       │                          │
    │                 Extracts force-input values            │                          │
    │                 ↓ missing_data → INCOMPLETE (end)      │                          │
    │                 ↓ missing_capability → UNAVAILABLE (end)                          │
    │                          │                            │                          │
    │              3. Categorize scopes via ScopeConsent     │                          │
    │                 AUTO_GRANT → pre-approved              │                          │
    │                 PROMPT_ONCE + existing grant → pre-approved/denied                │
    │                 PROMPT_ONCE (no grant) or PROMPT_ALWAYS → needs approval          │
    │                          │                            │                          │
    │                          │  4. If needs approval:     │                          │
    │                          │     status → AWAITING      │                          │
    │                          │     Push notification      │                          │
    │                          │     {pending_scopes with   │                          │
    │                          │      inputs + consent_mode}│                          │
    │                          │───────────────────────────►│                          │
    │                          │                            │                          │
    │                          │  5. User decides:          │                          │
    │                          │     ALWAYS_ALLOW / ONCE_ALLOW / ONCE_DENY / ALWAYS_DENY
    │                          │     POST /respond/         │                          │
    │                          │     {decision, scopes}     │                          │
    │                          │◄───────────────────────────│                          │
    │                          │                            │                          │
    │              6. If approved → status: PROCESSING      │                          │
    │                 POST action=token_request              │                          │
    │                 TokenRequestData: {request_id,         │                          │
    │                   permyt_user_id, service_id,          │                          │
    │                   service_public_key,                   │                          │
    │                   scope (ScopeGrant), ttl_minutes}      │                          │
    │                          │─────────────────────────────────────────────────────►│
    │                          │                            │                          │
    │                          │                            │  7. Provider issues token │
    │                          │                            │     Single-use JWT         │
    │                          │                            │     Encrypted for Requester│
    │                          │                            │     Returns: {encrypted_token,
    │                          │                            │      endpoints, expires_at} │
    │                          │◄─────────────────────────────────────────────────────│
    │                          │                            │                          │
    │  8. Callback or polling  │                            │                          │
    │     status: COMPLETED    │                            │                          │
    │     {services: [{encrypted_token, endpoints,          │                          │
    │       expires_at, public_key}]}                        │                          │
    │◄─────────────────────────│                            │                          │
    │                          │                            │                          │
    │  9. Requester decrypts token, calls Provider directly │                          │
    │     (Broker is NOT involved in steps 9-10)            │                          │
    │─────────────────────────────────────────────────────────────────────────────────►│
    │                          │                            │  10. Validate JWT, enforce│
    │                          │                            │      force inputs, return │
    │◄─────────────────────────────────────────────────────────────────────────────────│
```

### Consent & Grant Model

**Consent modes** (set per scope at connection time, stored in `ScopeConsent`):

| Mode            | Behavior                                          | GrantedScope created?                            |
| --------------- | ------------------------------------------------- | ------------------------------------------------ |
| `AUTO_GRANT`    | Auto-approve for any requester                    | Yes (GRANTED), automatically                     |
| `PROMPT_ONCE`   | Ask on first request per requester, then remember | Yes, if user chooses ALWAYS_ALLOW or ALWAYS_DENY |
| `PROMPT_ALWAYS` | Always ask, never persist approval                | Only if ALWAYS_DENY (denials always persist)     |

**Grant decisions** (returned by user via mobile app):

| Decision       | Effect                                                             |
| -------------- | ------------------------------------------------------------------ |
| `ALWAYS_ALLOW` | Approve + persist `GrantedScope(GRANTED)` for future auto-approval |
| `ONCE_ALLOW`   | One-time approval, no record persisted                             |
| `ONCE_DENY`    | One-time denial, no record persisted                               |
| `ALWAYS_DENY`  | Persist `GrantedScope(DENIED)` — future requests auto-rejected     |

### Security Model

All service-to-Broker and Broker-to-service communication uses **ES256 signing** (proof-of-possession JWT over payload hash) + **JWE encryption** (ECDH-ES+A256KW + A256GCM). Every request includes a unique **nonce** (64-char hex) + **ISO timestamp** for replay protection. Tokens are **single-use** (must be marked used atomically).

**Encryption-for-recipient principle** — sensitive `data` is always encrypted with the _recipient's_ public key:

| Flow                                  | Encrypted with                                     |
| ------------------------------------- | -------------------------------------------------- |
| Broker → Provider (token request)     | Provider's public key                              |
| Provider → Requester (token response) | Requester's public key (from `service_public_key`) |
| Broker → Requester (approved access)  | Requester's public key                             |
| Requester → Provider (service call)   | Provider's public key                              |

### Key Data Shapes (from `permyt-api-python/permyt/typing.py`)

- **`ScopeGrant`**: `dict[str, dict[str, Any]]` — scope reference → locked force-input values (empty dict if no inputs)
- **`AccessRequest`**: `{user_id, purpose, details, callback_url?, request_id?}`
- **`TokenRequestData`**: `{request_id, permyt_user_id, service_id, service_public_key, scope: ScopeGrant, ttl_minutes}`
- **`ServiceCredential`**: `{request_id, encrypted_token, endpoints, expires_at, public_key}`
- **`TokenMetadata`**: `{user, scope: ScopeGrant, service_public_key, expires_at}`

### This Project's Role: Demo Requester for Age Verification

This app is a **Requester** in the PERMYT protocol that only ever asks for the `is_older.check` scope:

- **Connect cycle (step 6)**: `process_user_connect()` handles the broker's webhook — binds `permyt_user_id` to a session-keyed `Verification` and immediately fires the age-check `request_access` so the user only has to scan once.
- **Request cycle (steps 1, 8-9)**: `process_request_status()` watches the broker's status updates; on `completed` it calls `call_services()`, parses `{"is_older": bool}` from the provider response, and stores the result on the `Verification`.
- **Page**: Single QR pane with a stage track (`Waiting for scan` → `Scanned — approve on PERMYT` → `Verifying age` → `Age verified`). On success swaps to a big check with a "Verify again" button; on failure swaps to a cross with the same retry button.
