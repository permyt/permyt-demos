# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the Bank demo provider.

## Project Overview

**bank/** is a PERMYT demo provider called **Bank**. It is a Django app on port 9013 (production: `bank.permyt.io`) that subclasses `permyt.PermytClient` from `permyt-api-python` and implements the Provider + Connect endpoints of the PERMYT protocol.

Each user has a fake bank account: a single IBAN, a current balance, a base currency (EUR), and a small history of mock movements seeded on first connect. The provider exposes a **static** scope catalogue with **3 scopes**:

- `balance.read` (no inputs) → returns balance + currency + IBAN.
- `movements.list` (no inputs) → returns the last 20 movements.
- `payment.send` — financially-significant inputs locked at the broker, labelling fields free:
  - **locked**: `account`, `value`, `currency`.
  - **free** (set by requester at call time): `name`, `description`.

Locked inputs mean the broker can't substitute the destination account, amount, or currency between user approval and provider execution. The unlocked `name` and `description` fields let the requester fill in human-readable context (counterparty display name, invoice number, etc.) without re-prompting the user.

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
python manage.py runserver 9013            # run dev server
```

`update_scope` must be re-run whenever `app/core/requests/scopes/catalogue.py` changes.

### Testing

```bash
pytest                                     # all tests
pytest app/core/requests/tests/            # contract + scope tests
pytest -v -k "test_payment"                # by keyword
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
bank/
  app/
    mixins/             # AppModel — UUID PK + timestamps, base for all models
    core/
      users/            # User (IBAN, balance, currency), LoginToken, QR login
      bank/             # Movement model, seed_movements helper
      requests/         # PermytClient, RequestToken, Nonce, webhook + per-scope endpoints
        scopes/         # BankScopes + ScopeDescriptor catalogue + executors
        management/     # update_scope command (push catalogue to broker)
      logs/             # Log model with activity context manager
    common/
      pages/            # IndexView (login/dashboard), templates, static (CSS/JS)
    utils/              # Fields, encoders, middleware, authentication, websocket
  settings/             # Django settings (base, dev, test)
  conftest.py           # Shared test fixtures
```

### Key classes

| Class                | File                                                         | Role                                                                       |
| -------------------- | ------------------------------------------------------------ | -------------------------------------------------------------------------- |
| `AppModel`           | `app/mixins/models.py`                                       | Abstract base model (UUID pk, created_at, updated_at)                      |
| `User`               | `app/core/users/models.py`                                   | Custom user model — bank account fields + `seed_profile()`                 |
| `LoginToken`         | `app/core/users/models.py`                                   | Short-lived QR-login session binding                                       |
| `Movement`           | `app/core/bank/models.py`                                    | Single account movement (signed amount, counterparty, type)                |
| `RequestToken`       | `app/core/requests/models.py`                                | Single-use token with full ScopeGrant                                      |
| `Nonce`              | `app/core/requests/models.py`                                | Replay protection (unique nonce values)                                    |
| `Log`                | `app/core/logs/models.py`                                    | Activity log with context manager                                          |
| `ScopeDescriptor`    | `app/core/requests/scopes/catalogue.py`                      | Dataclass — one entry per scope (reference, executor, input serializer)    |
| `BankScopes`         | `app/core/requests/scopes/utils.py`                          | Static scope catalogue — validation + execute, backed by `SCOPES`          |
| `PaymentSendSerializer` | `app/core/requests/scopes/serializers.py`                | Payment input — every field is in `Meta.locked_fields`                     |
| `PermytClient`       | `app/core/requests/client.py`                                | PermytClient implementation — the SDK integration layer                    |
| `ProfileView`        | `app/core/requests/views.py`                                 | Authenticated GET/PUT for the dashboard's account header                   |
| `MovementsView`      | `app/core/requests/views.py`                                 | Authenticated GET — returns last 20 movements (UI-only)                    |
| `ScopeCallView`      | `app/core/requests/views.py`                                 | Per-scope endpoint for service_call actions                                |
| `IndexView`          | `app/common/pages/views.py`                                  | Login/dashboard page dispatcher                                            |

### Dispatch path

```
PERMYT webhook → PermytClient.process_request()
  → BankScopes.validate_params()    # locked-input enforcement (fail-closed for any locked_fields)
  → BankScopes.execute(user, ref)   # read balance / list movements / send payment
```

### Scope catalogue (`BankScopes`)

Scopes are **static** — defined in `app/core/requests/scopes/catalogue.py` as a tuple of `ScopeDescriptor` records. There are 3 scopes:

- `balance.read` (no inputs) → executor `read_balance`.
- `movements.list` (no inputs) → executor `list_movements`.
- `payment.send` → executor `send_payment`. Locked: `account`, `value`, `currency`. Free: `name`, `description`.

Adding a scope = append one `ScopeDescriptor` to `SCOPES` and re-run `python manage.py update_scope`.

**Generic locked-input strict-mode:** `validate_params` rejects any scope whose serializer declares `Meta.locked_fields` if `locked={}` arrives empty — bank actions must never accept unlocked inputs.

### Endpoints

| URL pattern                          | View              | Purpose                                                  |
| ------------------------------------ | ----------------- | -------------------------------------------------------- |
| `/rest/permyt/inbound`               | PermytInboundView | token_request, user_connect, user_disconnect, etc.       |
| `/rest/<field>/<action>/`            | ScopeCallView     | Per-scope service_call endpoint (e.g. `payment/send`)    |
| `/rest/profile/`                     | ProfileView       | GET/PUT the authenticated user's account header (UI only — not part of the PERMYT protocol) |
| `/rest/movements/`                   | MovementsView     | GET the authenticated user's last 20 movements (UI only) |

### Real-time dashboard refresh

When `payment.send` executes, the executor schedules a `balance_changed` WebSocket push on `transaction.on_commit`. The dashboard's JS listens on `/ws/` (group `user-{user.id}`, set up by the existing Channels consumer at `app/websocket.py`) and re-fetches `/rest/profile/` + `/rest/movements/` to refresh the balance card and movements list in place. No polling, no page reload.

## Settings

Django settings module is `settings/`. Entry points:

- `manage.py` → `settings.dev`
- `pytest.ini` → `settings.test`
- `settings/wsgi.py` → `settings.dev`

All config via environment variables — see `.env.example`.

## Testing

Tests use **pure pytest** (not `django.test.TestCase`). DB-touching tests use `@pytest.mark.django_db`.

Shared fixtures in `conftest.py`:

- `user` — pre-created User with a populated bank account profile (deterministic via `UserFactory`)
- `make_token` — factory for RequestToken records (default scope grant: `{"balance.read": {}}`)
- `make_movement` — factory for Movement records bound to a user
- `mock_permyt_client` — PermytClient with mocked key loading

## Security invariants

- **Single-use tokens** — `get_token_metadata()` acquires a row-level lock via `select_for_update()` inside `transaction.atomic()` before reading `used`, so two concurrent redemptions cannot both observe `used=False`. Regression-protected by `test_select_for_update_is_used` and `test_concurrent_redemption_yields_one_success`.
- **Replay protection** — `_validate_nonce_and_timestamp()` creates a `Nonce` record (unique constraint rejects duplicates).
- **Scope enforcement** — `process_request()` validates each scope reference against the granted ScopeGrant before dispatching.
- **Locked-input fail-closed** — `validate_params()` rejects scopes whose serializer declares `Meta.locked_fields` when `locked={}` (covered by `test_payment_without_locked_input_rejected`).
- **Atomic balance updates** — `send_payment` wraps the Movement insert + balance decrement in `transaction.atomic()` with `User.objects.select_for_update()` so concurrent payments serialise.

## Patterns to follow

- All models extend `AppModel` from `app/mixins/models.py`.
- Scopes are descriptor-driven (`SCOPES` tuple in `catalogue.py`). Add one entry per new scope; do not subclass `BankScopes`.
- Locked inputs MUST live in `Meta.locked_fields`. Without this the broker can't lock them and tampered requests pass.
- Tests use pytest fixtures from `conftest.py`, not `setUp`/`TestCase`.
- Django settings live in `settings/`. After scope changes, re-run `python manage.py update_scope`.
- WS pushes use `transaction.on_commit` — never push from inside an open transaction, the message could fire then the DB write rolls back.

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

### Request Access Cycle

A Requester asks for user data. Broker evaluates scopes via AI, routes user approval, and brokers encrypted tokens between Requester and Provider(s). For bank scopes, the broker locks every input field in the issued grant — the user has explicitly approved the exact beneficiary, amount, and reference.

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

### This Project's Role: Bank Provider

This app is a **Provider** in the PERMYT protocol, holding a fake bank account per user (IBAN, balance, currency, movements) and exposing both reads and one money-moving action — all with locked inputs:

- **Connect cycle**: `process_user_connect()` handles the broker's webhook — creates/links user via `permyt_user_id`, binds to QR login session, calls `seed_profile()` to populate IBAN, starting balance, and ~15 mock movements.
- **Disconnect cycle**: `process_user_disconnect()` is idempotent — a repeat call for an unknown user is a no-op. Regular users have no non-PERMYT login path, so the `User` row is deleted outright (cascade wipes `LoginToken`, `Movement`, and account state). Privileged users (`is_staff`, `is_superuser`, `is_account_manager`) keep their account; only `permyt_user_id` is nulled and their login tokens are dropped, so they can still sign in via the admin paths.
- **Request cycle (token issuance)**: `store_token()` receives `TokenRequestData`, canonicalizes the locked scope grant via `BankScopes.validate_locked()`, persists `RequestToken`. SDK issues encrypted JWT.
- **Request cycle (execution)**: `process_request()` validates JWT via `get_token_metadata()`, enforces locked-input matching per scope (fail-closed if `locked={}` for any scope with `Meta.locked_fields`), and dispatches to `BankScopes.execute()` which runs the descriptor's executor against the user's account. `send_payment` decrements the balance, appends a `Movement`, and pushes a `balance_changed` WS event on commit.
