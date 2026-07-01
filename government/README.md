# Government — PERMYT Demo Provider

A working Django app that demonstrates how to build a **government identity Provider** using the [`permyt`](https://github.com/LeopardLabs/permyt-api-python) Python SDK.

## What is PERMYT

PERMYT is a zero-knowledge authorization broker. Users control who can access their data and under what conditions — the broker orchestrates consent and token exchange without ever seeing the data itself. For protocol details and the full API reference, see the [permyt SDK README](https://github.com/LeopardLabs/permyt-api-python).

## What this demo does

Government implements the **Provider** and **Connect** roles for PERMYT access requests, with a **fixed, read-only** citizen profile per user (full name, birthdate, address, country of residence, VAT number, phone, email, tax ID).

It exposes two kinds of scopes:

1. **Direct read scopes** — return the raw value of a single profile field (`name.read`, `birthdate.read`, `address.read`, `country.read`, `vat.read`, `phone.read`, `email.read`, `tax_id.read`).
2. **Privacy-preserving predicate scopes** — take an input and return a single boolean, without revealing the underlying field:
   - `is_older.check(min_age: int)` → `{ is_older: bool }`
   - `is_resident_of.check(country_code: str)` → `{ is_resident: bool }`
   - `vat_matches.check(value: str)` → `{ matches: bool }`

A requester that only needs to verify "is this person 18+?" can ask for `is_older.check` instead of `birthdate.read` — the broker's AI scope selector and the user's mobile-app consent UI both prefer the predicate, because it leaks one bit instead of a date of birth.

The catalogue is **static** — defined once in `app/core/requests/scopes/catalogue.py` and pushed to the broker via the `update_scope` management command. Adding a new scope is a one-line append.

## Key integration points

### PermytClient subclass — [`app/core/requests/client.py`](app/core/requests/client.py)

Every PERMYT provider subclasses `permyt.PermytClient` and implements a set of abstract methods. The SDK handles all cryptography (ES256 signing, JWE encryption), signature verification, nonce validation, and protocol routing — the provider only needs to implement the data-layer logic: who are your users, how do you store tokens, and what happens when a scope is executed.

| Method | Purpose |
|--------|---------|
| `get_service_id()` | Returns the registered service ID from settings |
| `get_private_key()` | Returns the path to the connector private key (ES256) |
| `get_permyt_public_key()` | Loads the broker's public key for signature verification |
| `_validate_nonce_and_timestamp()` | Replay protection — checks timestamp window, stores nonce |
| `resolve_user()` | Looks up local User by `permyt_user_id` |
| `store_token()` | Persists broker-issued request tokens with validated scope |
| `get_token_metadata()` | Retrieves and consumes single-use tokens |
| `get_endpoints_for_scope()` | Maps scope grants to provider endpoint URLs |
| `process_request()` | Executes granted scopes against user data |
| `process_user_connect()` | Handles the Connect callback — creates/links users, seeds the profile |
| `process_user_disconnect()` | Handles the Disconnect callback — unlinks `permyt_user_id`, drops login tokens |

### Scope catalogue — [`app/core/requests/scopes/catalogue.py`](app/core/requests/scopes/catalogue.py)

`SCOPES` is a tuple of `ScopeDescriptor` records. Each entry maps a scope reference (e.g. `is_older.check`) to a name, description, optional input serializer, and an executor callable. `GovernmentScopes` (in `scopes/utils.py`) implements the same public surface the SDK expects — `validate_params`, `validate_locked`, `execute`, `get_endpoint` — but reads from the static catalogue instead of the database.

To add a new scope, append one descriptor to `SCOPES` and re-run `python manage.py update_scope`.

### Predicate input enforcement

Predicate scopes accept inputs (`min_age`, `country_code`, `value`). All inputs are **locked at the broker** — the user approves a specific value (`min_age=18`) and that value is canonicalized into the request token. At call time, `validate_params` re-runs the input through the same serializer with `locked_data=` set, raising `InvalidInputError` if the request-time input doesn't match the approved value. A predicate scope arriving with an empty `locked` dict is rejected outright (fail-closed).

### Inbound webhook — [`app/core/requests/views.py`](app/core/requests/views.py)

One endpoint handles all broker callbacks. `PermytInboundView` receives signed POST requests and delegates to `client.handle_inbound()`, which verifies the signature, validates the nonce, and routes by action type (`token_request`, `user_connect`, `user_disconnect`, `service_call`, etc.). The view itself is minimal — the SDK does the heavy lifting.

### Profile editing — [`app/core/requests/views.py`](app/core/requests/views.py)

`ProfileView` (`GET/PUT /rest/profile/`) is the dashboard's edit endpoint. It is **not** part of the PERMYT protocol — only the logged-in user can edit their own profile through the UI. PERMYT scopes themselves are read-only.

### Connect flow — [`app/common/pages/views.py`](app/common/pages/views.py)

The Connect flow is a general-purpose mechanism for linking a user's PERMYT identity to an action in the provider. The pattern: generate a connect token with `client.generate_connect_token()`, store a record of what that token is for, and render the QR payload. When the user scans the code, the broker calls back to the inbound webhook with the user's identity. `process_user_connect()` then authenticates the user and calls `seed_profile()` to fill any blank profile fields with synthetic Faker data — useful for the demo so each new user has a complete record.

When the user revokes the connection from their PERMYT app, the broker fires a mirror `user_disconnect` callback. `process_user_disconnect()` is idempotent. Regular users have no non-PERMYT login path, so the `User` row is deleted outright — cascade wipes the citizen profile and login tokens. Privileged users (staff / superuser / account manager) keep their account; only `permyt_user_id` is nulled and the login tokens are dropped so they can still reach the admin paths.

## Requirements

- Python 3.14+
- Redis (used by Celery, Django Channels, and cache)
- SQLite (development — default)
- A running PERMYT broker instance

## Installation

```bash
python -m venv env
source env/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

After completing the setup sections below, apply migrations and start the server:

```bash
python manage.py migrate
python manage.py update_scope        # push scope catalogue to broker
python manage.py runserver 9012
```

## Setup: PERMYT broker

### 1. Generate connector keys

```bash
mkdir -p keys/connector keys/permyt
openssl ecparam -name prime256v1 -genkey -noout -out keys/connector/private.pem
openssl ec -in keys/connector/private.pem -pubout -out keys/connector/public.pem
```

### 2. Register the service in PERMYT

Create a new service in the PERMYT dashboard:

- **Name**: "Government"
- **Callback URL**: `http://localhost:9012/rest/permyt/inbound` (production: `https://goverment.permyt.io/rest/permyt/inbound`)
- **Public key**: upload `keys/connector/public.pem`

Note the **Service ID** for `.env`.

### 3. Download PERMYT public key

Save the broker's public key to `keys/permyt/public.pem`.

### 4. Update `.env`

```env
PERMYT_SERVICE_ID=<your-service-id>
PERMYT_PUBLIC_KEY_PATH=keys/permyt/public.pem
PRIVATE_KEY_PATH=keys/connector/private.pem
BASE_URL=http://localhost:9012
```

### 5. Push the scope catalogue

```bash
python manage.py update_scope
```

Run this once on first deploy and any time you change `app/core/requests/scopes/catalogue.py`.

## Project structure

```
goverment/
├── app/
│   ├── mixins/             # AppModel base class (UUID pk, timestamps)
│   ├── core/
│   │   ├── users/          # User (citizen profile cols), LoginToken, QR login
│   │   ├── requests/       # PermytClient, RequestToken, Nonce, webhook + scope views
│   │   │   ├── scopes/     # GovernmentScopes catalogue + predicate serializers
│   │   │   └── management/ # update_scope command
│   │   └── logs/           # Log model with activity context manager
│   ├── common/
│   │   └── pages/          # IndexView, templates (login/dashboard), static (CSS/JS)
│   └── utils/              # Fields, encoders, middleware, authentication, websocket
├── settings/               # Django settings (base, dev, test)
├── conftest.py             # Shared test fixtures
└── requirements.txt
```

## Endpoints

### PERMYT protocol (handled by SDK)

- `POST /rest/permyt/inbound` — single inbound endpoint for token requests, service calls, and user connect webhooks
- `POST /rest/<field>/<action>/` — per-scope endpoints, derived from the static catalogue (e.g. `/rest/name/read/`, `/rest/is_older/check/`)

### Dashboard profile API

- `GET /rest/profile/` — return the current user's profile
- `PUT /rest/profile/` — partial update (any subset of profile fields)

### QR-login

- `GET /` — login page (QR code) or dashboard (if authenticated)
- `GET /rest/login/status/?id=<login_id>` — poll QR login status

## Testing

```bash
pytest                                     # all tests
pytest -v                                  # verbose
pytest app/core/requests/tests/            # contract + scope tests
```

## Configuration reference

| Variable                 | Description                         | Default                      |
| ------------------------ | ----------------------------------- | ---------------------------- |
| `PERMYT_SERVICE_ID`      | Registered service ID in the broker | —                            |
| `PERMYT_PUBLIC_KEY_PATH` | Path to PERMYT broker public key    | `keys/permyt/public.pem`    |
| `PRIVATE_KEY_PATH`       | Path to connector private key       | `keys/connector/private.pem` |
| `BASE_URL`               | Provider's public URL               | `http://localhost:9012`      |
| `NONCE_TTL_SECONDS`      | Replay protection window            | `60`                         |
| `PERMYT_HOST`            | PERMYT broker URL                   | `http://localhost:8000`      |
| `REDIS_HOST`             | Redis host for Celery, Channels     | `localhost`                  |

## License

MIT — see [LICENSE](LICENSE).
