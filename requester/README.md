# PERMYT Demo Requester

A working Django app that demonstrates how to build a **Requester** using the [`permyt`](https://github.com/LeopardLabs/permyt-api-python) Python SDK.

## What is PERMYT

PERMYT is a zero-knowledge authorization broker. Users control who can access their data and under what conditions — the broker orchestrates consent and token exchange without ever seeing the data itself. For protocol details and the full API reference, see the [permyt SDK README](https://github.com/LeopardLabs/permyt-api-python).

## What this demo does

This app implements the **Requester** and **Connect** roles for PERMYT access requests:

- Submits natural-language data access requests to the PERMYT broker on behalf of an authenticated user
- Polls the broker for status updates as the request moves through its lifecycle (queued → awaiting → processing → completed)
- Calls provider endpoints with broker-issued tokens when access is approved
- Lets users log in by scanning a QR code (PERMYT Connect flow)
- Displays real-time request activity on a dashboard via WebSocket

A requester never stores user data — it asks for access, receives a single-use token, calls the provider directly, and displays the result. The broker is not involved in the final data exchange.

## Key integration points

### PermytClient subclass — [`app/core/requests/client.py`](app/core/requests/client.py)

Every PERMYT service subclasses `permyt.PermytClient` and implements a set of abstract methods. The SDK handles all cryptography (ES256 signing, JWE encryption), signature verification, nonce validation, and protocol routing — the requester only needs to implement identity, replay protection, and what to do when the broker calls back.

A requester implements fewer methods than a provider. Provider-only methods (`resolve_user`, `store_token`, `get_token_metadata`, etc.) are stubbed with `NotImplementedError` — the SDK requires them to exist but a requester never executes them.

| Method | Purpose |
|--------|---------|
| `get_service_id()` | Returns the registered service ID from settings |
| `get_private_key()` | Returns the path to the connector private key (ES256) |
| `get_permyt_public_key()` | Loads the broker's public key for signature verification |
| `_validate_nonce_and_timestamp()` | Replay protection — checks timestamp window, stores nonce |
| `_prepare_data_for_endpoint()` | Builds per-endpoint payload for service calls (empty in this demo) |
| `process_user_connect()` | Handles QR login — creates/links user, authenticates session |
| `process_user_disconnect()` | Handles the Disconnect callback — unlinks `permyt_user_id`, drops login tokens |
| `process_request_status()` | Handles broker status callbacks, calls providers on completion |

### Request submission — [`app/core/requests/views.py`](app/core/requests/views.py)

`SubmitRequestView` is the entry point for the requester flow. It takes a natural-language description from the authenticated user, calls `client.request_access()`, and creates an initial Log entry for dashboard tracking. The broker receives this request, runs AI scope evaluation to determine which scopes are needed, and routes user approval — the requester does not need to know about scopes or providers at submission time.

```python
# In SubmitRequestView.post():
response = client.request_access({
    "user_id": str(user.permyt_user_id),
    "description": description,
})
```

That's it. The broker returns a `request_id` and initial `status`. From here, the requester waits for status callbacks.

### Status callbacks — [`app/core/requests/client.py`](app/core/requests/client.py)

`process_request_status()` handles the broker's lifecycle callbacks. As the request advances (queued → awaiting user approval → processing → completed), the broker pushes status updates to the requester's inbound webhook. The key pattern is **wait-and-react**: the requester tracks status on a Log row keyed by `request_id`, and on `completed` it calls `call_services()` to fetch the actual data from providers.

```python
# Simplified flow inside process_request_status():
if status == "completed":
    responses = self.call_services(services)    # SDK handles token decryption + HTTP calls
    record(action="data_received", data={"responses": responses})
elif status in {"rejected", "incomplete", "unavailable"}:
    record(action="ended", data={"status": status, "reason": reason})
else:
    record(action=status, data={"status": status})  # queued, awaiting, processing
```

The SDK's `call_services()` handles all the complexity: decrypting the provider's token (JWE), building the signed request, and calling each provider endpoint. The requester just receives the response.

### Inbound webhook — [`app/core/requests/views.py`](app/core/requests/views.py)

One endpoint handles all broker callbacks. `PermytInboundView` receives signed POST requests and delegates to `client.handle_inbound()`, which verifies the signature, validates the nonce, and routes by action type (`user_connect`, `user_disconnect`, `request_status`, etc.). The view itself is minimal — the SDK does the heavy lifting.

### Connect flow — [`app/common/pages/views.py`](app/common/pages/views.py)

The Connect flow links a user's PERMYT identity to the requester. The pattern: generate a connect token with `client.generate_connect_token()`, store a record of what that token is for, and render the QR payload. When the user scans the code, the broker calls back to the inbound webhook with the user's identity. The requester then looks up the stored context and fires whatever action is needed.

This demo uses Connect for login — `IndexView._login()` creates a `LoginToken` tied to the session, and `process_user_connect()` authenticates the user when the callback arrives. But the same pattern works for linking accounts, starting workflows, or any action that needs to be tied to a verified user identity.

When the user revokes the connection from their PERMYT app, the broker fires a mirror `user_disconnect` callback. `process_user_disconnect()` is idempotent. Regular users have no non-PERMYT login path, so the `User` row is deleted outright — cascade wipes the login tokens. Privileged users (staff / superuser / account manager) keep their account; only `permyt_user_id` is nulled and the login tokens are dropped so they can still reach the admin paths.

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
python manage.py runserver 9010
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

- **Name**: "Demo Requester"
- **Callback URL**: `http://localhost:9010/rest/permyt/inbound`
- **Public key**: upload `keys/connector/public.pem`

Note the **Service ID** for `.env`.

### 3. Download PERMYT public key

Save the broker's public key to `keys/permyt/public.pem`.

### 4. Update `.env`

```env
PERMYT_SERVICE_ID=<your-service-id>
PERMYT_PUBLIC_KEY_PATH=keys/permyt/public.pem
PRIVATE_KEY_PATH=keys/connector/private.pem
BASE_URL=http://localhost:9010
```

## Project structure

```
requester/
├── app/
│   ├── mixins/             # AppModel base class (UUID pk, timestamps)
│   ├── core/
│   │   ├── users/          # User model, LoginToken, QR login
│   │   ├── requests/       # PermytClient (requester), webhook + submit views
│   │   └── logs/           # Log model with activity context manager
│   ├── common/
│   │   └── pages/          # IndexView, templates (login/dashboard), static (CSS/JS)
│   └── utils/              # Fields, encoders, middleware, authentication, websocket
├── settings/               # Django settings (base, dev, test)
├── conftest.py             # Shared test fixtures
└── requirements.txt
```

## Endpoints

### PERMYT protocol

- `POST /rest/permyt/inbound` — inbound webhook for user connect and status callbacks

### Dashboard

- `POST /rest/requests/submit/` — submit an access request (natural-language description)
- `GET /rest/login/status/?id=<login_id>` — poll QR login status

### Pages

- `GET /` — login page (QR code) or dashboard (if authenticated)

## Testing

```bash
pytest                                     # all tests
pytest -v                                  # verbose
pytest app/core/requests/tests/            # contract tests
```

## Configuration reference

| Variable                  | Description                         | Default                      |
| ------------------------- | ----------------------------------- | ---------------------------- |
| `DJANGO_SECRET_KEY`       | Django secret key                   | insecure dev default         |
| `SECURED_FIELDS_KEY`      | Fernet key for encrypted fields     | insecure dev default         |
| `SECURED_FIELDS_HASH_SALT`| Salt for hashed fields              | insecure dev default         |
| `PERMYT_SERVICE_ID`       | Registered service ID in the broker | —                            |
| `PERMYT_PUBLIC_KEY_PATH`  | Path to PERMYT broker public key    | `keys/permyt/public.pem`    |
| `PRIVATE_KEY_PATH`        | Path to connector private key       | `keys/connector/private.pem` |
| `BASE_URL`                | Requester's public URL              | `http://localhost:9010`      |
| `REQUESTER_CALLBACK_URL`  | Webhook URL sent to the broker      | `{BASE_URL}/rest/permyt/inbound` |
| `NONCE_TTL_SECONDS`       | Replay protection window            | `60`                         |
| `PERMYT_HOST`             | PERMYT broker URL                   | `http://localhost:8000`      |
| `REDIS_HOST`              | Redis host for Celery, Channels     | `localhost`                  |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).
