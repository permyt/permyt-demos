# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the Sentinel Screening demo provider.

## Project Overview

**sentinel/** is a PERMYT demo provider called **Sentinel Screening** — a compliance-grade watchlist authority. It is a Django app on port 9018 (production: `sentinel.permyt.io`) that subclasses `permyt.PermytClient` from `permyt-api-python` and implements the Provider + Connect endpoints of the PERMYT protocol.

Each connected subject has a screening record of four booleans (`sanctions_match`, `pep`, `adverse_media`, `self_excluded`), all seeded **clear** on connect. The provider exposes a **static** scope catalogue of four boolean checks (no inputs, all `high_sensitivity`, `default_consent_mode="prompt_once"`):
- `sanctions.check` → `{sanctions_match: bool}`
- `pep.check` → `{pep: bool}`
- `adverse_media.check` → `{adverse_media: bool}`
- `self_exclusion.check` → `{self_excluded: bool}`

Each check leaks one bit — the authoritative source answers directly (source-direct provenance), without exposing any underlying records. The screening booleans are editable from the dashboard so denials can be demonstrated. The scope catalogue class is `SentinelScopes` (`app/core/requests/scopes/utils.py`).

### Sibling project

- `../requester` — the demo requester app (Django, port 9010). Submits access requests to providers via PERMYT.

## Commands

### Development

```bash
python -m venv env && source env/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # then fill in secrets
python manage.py migrate                   # apply migrations
python manage.py update_scope              # push static scope catalogue to broker
python manage.py runserver 9012            # run dev server
```

`update_scope` must be re-run whenever `app/core/requests/scopes/catalogue.py` changes.

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
goverment/
  app/
    mixins/             # AppModel — UUID PK + timestamps, base for all models
    core/
      users/            # User (8 profile cols), LoginToken, QR login
      requests/         # PermytClient, RequestToken, Nonce, webhook + per-scope endpoints
        scopes/         # GovernmentScopes + ScopeDescriptor catalogue
        management/     # update_scope command (push catalogue to broker)
      logs/             # Log model with activity context manager
    common/
      pages/            # IndexView (login/dashboard), templates, static (CSS/JS)
    utils/              # Fields, encoders, middleware, authentication, websocket
  settings/             # Django settings (base, dev, test), urls, wsgi
  conftest.py           # Shared test fixtures
```

### Key classes

| Class                | File                                                         | Role                                                                       |
| -------------------- | ------------------------------------------------------------ | -------------------------------------------------------------------------- |
| `AppModel`           | `app/mixins/models.py`                                       | Abstract base model (UUID pk, created_at, updated_at)                      |
| `User`               | `app/core/users/models.py`                                   | Custom user model — citizen profile cols + `seed_profile()` (Faker)        |
| `LoginToken`         | `app/core/users/models.py`                                   | Short-lived QR-login session binding                                       |
| `RequestToken`       | `app/core/requests/models.py`                                | Single-use token with full ScopeGrant                                      |
| `Nonce`              | `app/core/requests/models.py`                                | Replay protection (unique nonce values)                                    |
| `Log`                | `app/core/logs/models.py`                                    | Activity log with context manager                                          |
| `ScopeDescriptor`    | `app/core/requests/scopes/catalogue.py`                      | Dataclass — one entry per scope (reference, executor, input serializer)    |
| `GovernmentScopes`   | `app/core/requests/scopes/utils.py`                          | Static scope catalogue — validation + execute, backed by `SCOPES`          |
| `IsOlderSerializer`  | `app/core/requests/scopes/serializers.py`                    | Predicate input — `min_age` (locked)                                       |
| `IsResidentOfSerializer` | `app/core/requests/scopes/serializers.py`                | Predicate input — `country_code` (locked)                                  |
| `VatMatchesSerializer` | `app/core/requests/scopes/serializers.py`                  | Predicate input — `value` (locked)                                         |
| `PermytClient`       | `app/core/requests/client.py`                                | PermytClient implementation — the SDK integration layer                    |
| `ProfileView`        | `app/core/requests/views.py`                                 | Authenticated GET/PUT for the dashboard's profile editor                   |
| `ScopeCallView`      | `app/core/requests/views.py`                                 | Per-scope endpoint for service_call actions                                |
| `IndexView`          | `app/common/pages/views.py`                                  | Login/dashboard page dispatcher                                            |

### Dispatch path

```
PERMYT webhook → PermytClient.process_request()
  → GovernmentScopes.validate_params()   # locked-input enforcement (predicates fail-closed)
  → GovernmentScopes.execute(user, ref)  # read profile col / compute predicate
```

### Scope catalogue (`GovernmentScopes`)

Scopes are **static** — defined in `app/core/requests/scopes/catalogue.py` as a tuple of `ScopeDescriptor` records. There are 11 scopes:

- 8 reads (no inputs): `name.read`, `birthdate.read`, `address.read`, `country.read`, `vat.read`, `phone.read`, `email.read`, `tax_id.read`.
- 3 predicates (`.check`, all inputs locked at the broker):
  - `is_older.check(min_age: int) → {is_older: bool}`
  - `is_resident_of.check(country_code: str) → {is_resident: bool}`
  - `vat_matches.check(value: str) → {matches: bool}`

Adding a scope = append one `ScopeDescriptor` to `SCOPES` and re-run `python manage.py update_scope`.

**Predicate strict-mode:** `validate_params` rejects predicate scopes that arrive with an empty `locked` dict — identity data must never accept unlocked inputs.

### Endpoints

| URL pattern                          | View              | Purpose                                                  |
| ------------------------------------ | ----------------- | -------------------------------------------------------- |
| `/rest/permyt/inbound`               | PermytInboundView | token_request, user_connect, user_disconnect, etc.       |
| `/rest/<field>/<action>/`            | ScopeCallView     | Per-scope service_call endpoint (e.g. `is_older/check`)  |
| `/rest/profile/`                     | ProfileView       | GET/PUT the authenticated user's citizen profile (UI only — not part of the PERMYT protocol) |

## Settings

Django settings module is `settings/`. Entry points:

- `manage.py` → `settings.dev`
- `pytest.ini` → `settings.test`
- `settings/wsgi.py` → `settings.dev`

All config via environment variables — see `.env.example`.

## Testing

Tests use **pure pytest** (not `django.test.TestCase`). DB-touching tests use `@pytest.mark.django_db`.

Shared fixtures in `conftest.py`:

- `user` — pre-created User with a populated citizen profile (deterministic via `UserFactory`)
- `make_token` — factory for RequestToken records (default scope grant: `{"name.read": {}}`)
- `mock_permyt_client` — PermytClient with mocked key loading

## Security invariants

- **Single-use tokens** — `get_token_metadata()` acquires a row-level lock via `select_for_update()` inside `transaction.atomic()` before reading `used`, so two concurrent redemptions cannot both observe `used=False`. Regression-protected by `test_select_for_update_is_used` and `test_concurrent_redemption_yields_one_success`.
- **Replay protection** — `_validate_nonce_and_timestamp()` creates a `Nonce` record (unique constraint rejects duplicates).
- **Scope enforcement** — `process_request()` validates each scope reference against the granted ScopeGrant before dispatching.
- **Predicate fail-closed** — `validate_params()` rejects `.check` scopes that arrive without locked inputs (covered by `test_predicate_without_locked_input_rejected`).

## Patterns to follow

- All models extend `AppModel` from `app/mixins/models.py`.
- Scopes are descriptor-driven (`SCOPES` tuple in `catalogue.py`). Add one entry per new scope; do not subclass `GovernmentScopes`.
- Predicate inputs MUST live in `Meta.locked_fields`. Without this the broker can't lock them and tampered requests pass.
- Tests use pytest fixtures from `conftest.py`, not `setUp`/`TestCase`.
- Django settings live in `settings/`. After scope changes, re-run `python manage.py update_scope`.

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

### This Project's Role: Government Provider

This app is a **Provider** in the PERMYT protocol, holding a fixed citizen profile per user (full_name, birthdate, address, country, vat, phone, email, tax_id) and exposing both raw reads and privacy-preserving predicates:

- **Connect cycle (step 6)**: `process_user_connect()` handles the Broker's webhook — creates/links user via `permyt_user_id`, binds to QR login session, calls `seed_profile()` to fill any blank fields with synthetic Faker data.
- **Disconnect cycle**: `process_user_disconnect()` is idempotent. Regular users have no non-PERMYT login path, so the `User` row is deleted outright — cascade wipes the citizen profile fields, login tokens, and any related rows. Privileged users (`is_staff`, `is_superuser`, `is_account_manager`) keep their account; only `permyt_user_id` is nulled and login tokens are dropped, so they can still sign in via the admin paths.
- **Request cycle (step 7)**: `store_token()` receives `TokenRequestData`, canonicalizes the locked scope grant via `GovernmentScopes.validate_locked()`, persists `RequestToken`. SDK issues encrypted JWT.
- **Request cycle (step 10)**: `process_request()` validates JWT via `get_token_metadata()`, enforces locked-input matching per scope (predicates fail-closed if `locked={}`), and dispatches to `GovernmentScopes.execute()` which runs the descriptor's executor against the user's profile.
