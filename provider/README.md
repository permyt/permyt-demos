# NoteVault — PERMYT Demo Provider

A working Django app that demonstrates how to build a **Provider** using the [`permyt`](https://github.com/LeopardLabs/permyt-api-python) Python SDK.

## What is PERMYT

PERMYT is a zero-knowledge authorization broker. Users control who can access their data and under what conditions — the broker orchestrates consent and token exchange without ever seeing the data itself. For protocol details and the full API reference, see the [permyt SDK README](https://github.com/LeopardLabs/permyt-api-python).

## What this demo does

NoteVault implements the **Provider** and **Connect** roles for PERMYT access requests:

- Receives signed token-request callbacks from the broker and issues single-use access tokens
- Serves user data to authorized requesters via scope-specific endpoints
- Supports **dynamic scope creation** — superusers add or remove data fields at runtime; a single `sync_scopes_to_broker()` call makes the new scopes and endpoints instantly available to all users and requesters, with no code changes or redeployment anywhere in the ecosystem
- Lets users log in by scanning a QR code (PERMYT Connect flow)
- Displays real-time request activity on a dashboard via WebSocket

The data itself is simple — space-themed text fields per user (mission log, coordinates, crew notes, transmission) — but the integration patterns apply to any provider.

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
| `process_user_connect()` | Handles the Connect callback — creates/links users, triggers actions |
| `process_user_disconnect()` | Handles the Disconnect callback — unlinks `permyt_user_id`, drops login tokens |

### Scope catalogue — [`app/core/requests/scopes/utils.py`](app/core/requests/scopes/utils.py)

`NoteVaultScopes` is a dynamic scope catalogue backed by `NoteField` records in the database. Each field with slug `X` automatically generates two scopes: `X.read` and `X.write`. Because the catalogue queries the database live, there are no dead endpoints — scopes always reflect the current state.

The key pattern is **define-and-sync**: when a superuser creates a new field, the provider builds scope definitions from the database and pushes them to the broker via `update_scopes()`:

```python
# In NoteFieldListView.post():
note_field = NoteField.objects.create(slug=slug, name=name)
sync_scopes_to_broker()  # pushes updated scope catalogue to the broker
```

That's it. After this call:

- **All connected requesters immediately see the new scopes and endpoints** — no code changes, redeployment, or reconfiguration needed on the requester side.
- **All connected users automatically get the updated consent options** — new scopes appear in their approval flows without any action on their part.
- **Existing grants are unaffected** — previously approved scopes continue to work; only the new/removed scopes change.

This pattern works for any provider: define your scopes programmatically (from a database, config file, or any source), call `update_scopes()`, and the entire ecosystem updates.

Default fields (seeded on first migration): `mission_log`, `coordinates`, `crew_notes`, `transmission`. Superusers can add or remove fields at runtime from the dashboard.

### Inbound webhook — [`app/core/requests/views.py`](app/core/requests/views.py)

One endpoint handles all broker callbacks. `PermytInboundView` receives signed POST requests and delegates to `client.handle_inbound()`, which verifies the signature, validates the nonce, and routes by action type (`token_request`, `user_connect`, `user_disconnect`, `service_call`, etc.). The view itself is minimal — the SDK does the heavy lifting.

### Connect flow — [`app/common/pages/views.py`](app/common/pages/views.py)

The Connect flow is a general-purpose mechanism for linking a user's PERMYT identity to an action in the provider. The pattern: generate a connect token with `client.generate_connect_token()`, store a record of what that token is for, and render the QR payload. When the user scans the code, the broker calls back to the inbound webhook with the user's identity. The provider then looks up the stored context and fires whatever action is needed.

NoteVault uses this for login — `IndexView._login()` creates a `LoginToken` tied to the session, and `process_user_connect()` authenticates the user when the callback arrives. But the same pattern works for starting workflows, filling forms, triggering approvals, or any action that needs to be tied to a verified user identity.

When the user revokes the connection from their PERMYT app, the broker fires a mirror `user_disconnect` callback. `process_user_disconnect()` is idempotent. Regular users have no non-PERMYT login path, so the `User` row is deleted outright — cascade wipes the stored note values and login tokens. Privileged users (staff / superuser / account manager) keep their account; only `permyt_user_id` is nulled and the login tokens are dropped so they can still reach the admin paths.

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
python manage.py runserver 9011
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

- **Name**: "NoteVault"
- **Callback URL**: `http://localhost:9011/rest/permyt/inbound`
- **Public key**: upload `keys/connector/public.pem`

Note the **Service ID** for `.env`.

### 3. Download PERMYT public key

Save the broker's public key to `keys/permyt/public.pem`.

### 4. Update `.env`

```env
PERMYT_SERVICE_ID=<your-service-id>
PERMYT_PUBLIC_KEY_PATH=keys/permyt/public.pem
PRIVATE_KEY_PATH=keys/connector/private.pem
BASE_URL=http://localhost:9011
```

Scopes are synced automatically on first migration and whenever fields are added or removed — no manual scope registration needed.

## Project structure

```
provider/
├── app/
│   ├── mixins/             # AppModel base class (UUID pk, timestamps)
│   ├── core/
│   │   ├── users/          # User model, NoteField, UserFieldValue, LoginToken, QR login
│   │   ├── requests/       # PermytClient, RequestToken, Nonce, webhook + scope views
│   │   │   └── scopes/     # NoteVaultScopes catalogue, ScopeSerializer
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
- `POST /rest/<field>/<action>/` — per-scope endpoints, dynamically generated from the scope catalogue

### Dashboard field CRUD

- `GET /rest/notes/<field_name>/` — read a note field
- `PUT /rest/notes/<field_name>/` — update a note field
- `DELETE /rest/notes/<field_name>/` — delete a field (superuser only)
- `POST /rest/notes/` — create a new field (superuser only)

### QR-login

- `GET /` — login page (QR code) or dashboard (if authenticated)
- `GET /rest/login/status/?id=<login_id>` — poll QR login status

## Testing

```bash
pytest                                     # all tests
pytest -v                                  # verbose
pytest app/core/requests/tests/            # contract + model tests
```

## Configuration reference

| Variable                 | Description                         | Default                      |
| ------------------------ | ----------------------------------- | ---------------------------- |
| `PERMYT_SERVICE_ID`      | Registered service ID in the broker | —                            |
| `PERMYT_PUBLIC_KEY_PATH` | Path to PERMYT broker public key    | `keys/permyt/public.pem`    |
| `PRIVATE_KEY_PATH`       | Path to connector private key       | `keys/connector/private.pem` |
| `BASE_URL`               | Provider's public URL               | `http://localhost:9011`      |
| `NONCE_TTL_SECONDS`      | Replay protection window            | `60`                         |
| `PERMYT_HOST`            | PERMYT broker URL                   | `http://localhost:8000`      |
| `REDIS_HOST`             | Redis host for Celery, Channels     | `localhost`                  |

## License

MIT — see [LICENSE](LICENSE).
