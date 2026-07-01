# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the NoteVault demo provider.

## Project Overview

**provider/** is a PERMYT demo provider called **NoteVault**. It is a Django app on port 9011 that subclasses `permyt.PermytClient` from `permyt-api-python` and implements the Provider + Connect endpoints of the PERMYT protocol. Superusers create dynamic note fields; each field generates 2 scopes (read/write) that are synced to the broker via `update_scopes()`.

### Sibling project

- `../requester` — the demo requester app (Django, port 9010). Submits access requests to providers via PERMYT.

## Commands

### Development

```bash
python -m venv env && source env/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # then fill in secrets
python manage.py migrate                   # apply migrations
python manage.py runserver 9011            # run dev server
```

### Testing

```bash
pytest                                     # all tests
pytest app/core/requests/tests/            # contract + model tests
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
provider/
  app/
    mixins/             # AppModel — UUID PK + timestamps, base for all models
    core/
      users/            # User, NoteField (global), UserFieldValue (per-user), LoginToken, QR login
      requests/         # PermytClient, RequestToken, Nonce, webhook + per-scope endpoints
        scopes/         # NoteVaultScopes catalogue, ScopeSerializer, SCOPE_DEFINITIONS
      logs/             # Log model with activity context manager
    common/
      pages/            # IndexView (login/dashboard), templates, static (CSS/JS)
    utils/              # Fields, encoders, middleware, authentication, websocket
  settings/             # Django settings (base, dev, test), urls, wsgi
  conftest.py           # Shared test fixtures
```

### Key classes

| Class              | File                                  | Role                                                    |
| ------------------ | ------------------------------------- | ------------------------------------------------------- |
| `AppModel`         | `app/mixins/models.py`                | Abstract base model (UUID pk, created_at, updated_at)   |
| `User`             | `app/core/users/models.py`            | Custom user model (QR login, seed_field_values)         |
| `NoteField`        | `app/core/users/models.py`            | Global field definition (slug + name). Superuser-managed |
| `UserFieldValue`   | `app/core/users/models.py`            | Per-user value for a NoteField                          |
| `LoginToken`       | `app/core/users/models.py`            | Short-lived QR-login session binding                    |
| `RequestToken`     | `app/core/requests/models.py`         | Single-use token with full ScopeGrant                   |
| `Nonce`            | `app/core/requests/models.py`         | Replay protection (unique nonce values)                 |
| `Log`              | `app/core/logs/models.py`             | Activity log with context manager                       |
| `NoteVaultScopes`  | `app/core/requests/scopes/utils.py`   | Dynamic scope catalogue — DB-backed, validation + execute |
| `PermytClient`     | `app/core/requests/client.py`         | PermytClient implementation — the SDK integration layer |
| `NoteFieldView`    | `app/core/requests/views.py`          | Dashboard CRUD for field values (GET/PUT/DELETE)        |
| `NoteFieldListView`| `app/core/requests/views.py`          | Create new fields (POST, superuser only)                |
| `ScopeCallView`    | `app/core/requests/views.py`          | Per-scope endpoint for service_call actions             |
| `IndexView`        | `app/common/pages/views.py`           | Login/dashboard page dispatcher                         |

### Dispatch path

```
PERMYT webhook → PermytClient.process_request()
  → NoteVaultScopes.validate_params()    # input validation + locked-field enforcement
  → NoteVaultScopes.execute(user, ref)   # read/write UserFieldValue directly
```

### Scope catalogue (`NoteVaultScopes`)

Scopes are **dynamic** — driven by `NoteField` records in the database. Each NoteField with slug `X` generates:
- `X.read` — read scope (no inputs)
- `X.write` — write scope (accepts `content` field via NoteWriteSerializer)

Scopes are synced to the broker via `sync_scopes_to_broker()` on every field create/delete.
Default fields (seeded on first migration): mission_log, coordinates, crew_notes, transmission.

### Endpoints

| URL pattern                          | View              | Purpose                          |
| ------------------------------------ | ----------------- | -------------------------------- |
| `/rest/permyt/inbound`               | PermytInboundView | token_request, user_connect, user_disconnect, etc |
| `/rest/<field>/<action>/`            | ScopeCallView     | Per-scope service_call endpoint  |
| `/rest/notes/`                       | NoteFieldListView | Create fields (POST, superuser)  |
| `/rest/notes/<slug>/`                | NoteFieldView     | GET/PUT/DELETE field values       |

## Settings

Django settings module is `settings/`. Entry points:

- `manage.py` → `settings.dev`
- `pytest.ini` → `settings.test`
- `settings/wsgi.py` → `settings.dev`

All config via environment variables — see `.env.example`.

## Testing

Tests use **pure pytest** (not `django.test.TestCase`). DB-touching tests use `@pytest.mark.django_db`.

Shared fixtures in `conftest.py`:

- `user` — pre-created User with note fields
- `make_token` — factory for RequestToken records
- `mock_permyt_client` — PermytClient with mocked key loading

## Security invariants

- **Single-use tokens** — `get_token_metadata()` acquires a row-level lock via `select_for_update()` inside `transaction.atomic()` before reading `used`, so two concurrent redemptions cannot both observe `used=False`. Regression-protected by `test_select_for_update_is_used` and `test_concurrent_redemption_yields_one_success`.
- **Replay protection** — `_validate_nonce_and_timestamp()` creates a `Nonce` record (unique constraint rejects duplicates).
- **Scope enforcement** — `process_request()` validates each scope reference against the granted ScopeGrant before dispatching.

## Patterns to follow

- All models extend `AppModel` from `app/mixins/models.py`.
- Scopes are class-based (`NoteVaultScopes`) with `@classmethod` for static lookups.
- User model methods handle scope actions directly (no external API — just DB read/write).
- Tests use pytest fixtures from `conftest.py`, not `setUp`/`TestCase`.
- Django settings live in `settings/`.

<!-- PERMYT Protocol Reference v1 -->

## PERMYT Protocol Reference

### Actors

| Actor          | Description                                                                                                                                   |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **Broker**     | The PERMYT server (`permyt`). Orchestrates all flows, runs AI scope evaluation, manages consent, brokers tokens. Never sees actual user data. |
| **Requester**  | A service that wants access to user data. Uses the `permyt` SDK (`permyt-api-python`).                                                        |
| **Provider**   | A service that holds user data and issues tokens. Uses the `permyt` SDK. This project is a Provider.                                          |
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

### This Project's Role: NoteVault Provider

This app is a **Provider** in the PERMYT protocol, storing space-themed text fields:

- **Connect cycle (step 6)**: `process_user_connect()` handles the Broker's webhook — creates/links user via `permyt_user_id`, binds to QR login session
- **Disconnect cycle**: `process_user_disconnect()` is idempotent. Regular users have no non-PERMYT login path, so the `User` row is deleted outright — cascade wipes `UserFieldValue`, `LoginToken`, and any related rows. Privileged users (`is_staff`, `is_superuser`, `is_account_manager`) keep their account; only `permyt_user_id` is nulled and login tokens are dropped, so they can still sign in via the admin paths.
- **Request cycle (step 7)**: `store_token()` receives `TokenRequestData`, persists `RequestToken` with canonicalized scope grant. SDK issues encrypted JWT.
- **Request cycle (step 10)**: `process_request()` validates JWT via `get_token_metadata()`, enforces scope grants, dispatches to `User` model read/write methods
