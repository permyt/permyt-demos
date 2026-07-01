# PERMYT Demo — Age Verification

A working Django app that demonstrates how to build a privacy-preserving **age-verification Requester** using the [`permyt`](https://github.com/LeopardLabs/permyt-api-python) Python SDK.

The user lands on a single page with a QR code: scan with the PERMYT mobile app, approve the `is_older.check` scope, and the page tells you "you're verified" — without ever revealing the user's birthdate, name, or any other identity field. Only a boolean (`is_older: true|false`) is shared.

## What is PERMYT

PERMYT is a zero-knowledge authorization broker. Users control who can access their data and under what conditions — the broker orchestrates consent and token exchange without ever seeing the data itself. For protocol details and the full API reference, see the [permyt SDK README](https://github.com/LeopardLabs/permyt-api-python).

## What this demo does

This app implements the **Requester** and **Connect** roles for PERMYT access requests, narrowed to a single scope:

- Renders a QR connect token on `GET /`. No form, no fields — only the QR + "scan to verify".
- When the user scans, the broker fires `user_connect`. The app binds the `permyt_user_id` to the session and immediately fires an access request with the natural-language description *"Age verification: confirm the user is at least 18 years old using a privacy-preserving check…"*.
- The broker's AI scope resolver picks the government provider's `is_older.check` scope and locks `min_age=18` as a force-input.
- The user approves on mobile. The broker brokers a single-use token to the requester.
- The requester calls the provider's `/rest/is_older/check/` endpoint, parses `{"is_older": true|false}`, and updates the page in real time via WebSocket.
- A "Verify again" button resets state and issues a fresh QR — no reload required.

A requester never stores user data — it asks for access, receives a single-use token, calls the provider directly, and displays only the boolean answer.

## Sibling project

This demo expects [`../government`](../government) — the Government provider — to be running. It exposes the `is_older.check` scope and returns `{"is_older": bool}`.

## Key integration points

### PermytClient subclass — [`app/core/requests/client.py`](app/core/requests/client.py)

Every PERMYT service subclasses `permyt.PermytClient` and implements a set of abstract methods. The SDK handles all cryptography (ES256 signing, JWE encryption), signature verification, nonce validation, and protocol routing — the requester only implements identity, replay protection, and what to do on broker callbacks.

A requester implements fewer methods than a provider. Provider-only methods (`resolve_user`, `store_token`, `get_token_metadata`, etc.) are stubbed with `NotImplementedError` — the SDK requires them to exist but a requester never executes them.

| Method                          | Purpose                                                                       |
| ------------------------------- | ----------------------------------------------------------------------------- |
| `get_service_id()`              | Returns the registered service ID from settings                               |
| `get_private_key()`             | Returns the path to the connector private key (ES256)                         |
| `get_permyt_public_key()`       | Loads the broker's public key for signature verification                      |
| `_validate_nonce_and_timestamp()` | Replay protection — checks timestamp window, stores nonce                   |
| `_prepare_data_for_endpoint()`  | Builds per-endpoint payload — supplies `min_age` when the scope requires it   |
| `process_user_connect()`        | Handles QR scan — binds `permyt_user_id` and auto-fires the age-check request |
| `process_request_status()`      | Handles broker status callbacks, calls the provider on `completed`            |

### Auto-trigger after scan — [`app/core/requests/client.py`](app/core/requests/client.py) → `_fire_age_check`

There is no submit button in this demo. The moment `process_user_connect` resolves the scanning user, `_fire_age_check()` calls `request_access` with the natural-language description and locks `min_age` to the configured value. From then on the page is driven entirely by WebSocket events from `process_request_status`.

### Inbound webhook — [`app/core/requests/views.py`](app/core/requests/views.py)

One endpoint handles all broker callbacks. `PermytInboundView` receives signed POST requests and delegates to `client.handle_inbound()`, which verifies the signature, validates the nonce, and routes by action type. The view itself is minimal — the SDK does the heavy lifting.

### Verification model — [`app/core/verifications/models.py`](app/core/verifications/models.py)

`Verification` is a session-keyed record holding the current `status` (one of `pending`, `scanned`, `awaiting`, `verifying`, `verified`, `failed`), the locked `min_age`, the resolved `is_older` boolean, and the broker `request_id`. Anonymous — no user account required.

`RefreshQrView` keeps the displayed QR scannable indefinitely by issuing a new connect token before the previous one expires. `ResetVerificationView` powers the "Verify again" button: it drops the existing record, creates a fresh one, and returns a new QR SVG.

## Requirements

- Python 3.14+
- Redis (used by Celery, Django Channels, and cache)
- SQLite (development — default)
- A running PERMYT broker instance
- A running `../government` provider (or any provider that exposes `is_older.check`)

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
python manage.py runserver 9015
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

- **Name**: "Demo Age Verifier"
- **Callback URL**: `http://localhost:9015/rest/permyt/inbound`
- **Public key**: upload `keys/connector/public.pem`

Note the **Service ID** for `.env`.

### 3. Download PERMYT public key

Save the broker's public key to `keys/permyt/public.pem`.

### 4. Update `.env`

```env
PERMYT_SERVICE_ID=<your-service-id>
PERMYT_PUBLIC_KEY_PATH=keys/permyt/public.pem
PRIVATE_KEY_PATH=keys/connector/private.pem
BASE_URL=http://localhost:9015
VERIFY_MIN_AGE=18
VERIFY_APP_NAME=PERMYT Verify
```

## Project structure

```
verify/
├── app/
│   ├── mixins/             # AppModel base class (UUID pk, timestamps)
│   ├── core/
│   │   ├── requests/       # PermytClient (requester), inbound webhook, Nonce
│   │   ├── verifications/  # Verification, LoginToken, QR + reset endpoints
│   │   ├── logs/           # Log model with activity context manager
│   │   └── users/          # User model (kept from harness; demo is anonymous)
│   ├── common/
│   │   └── pages/          # VerifyView, templates, static (CSS/JS)
│   └── utils/              # Fields, encoders, middleware, authentication, websocket
├── settings/               # Django settings (base, dev, test)
├── conftest.py             # Shared test fixtures
└── requirements.txt
```

## Endpoints

### PERMYT protocol

- `POST /rest/permyt/inbound` — inbound webhook for `user_connect` and status callbacks

### Page

- `GET /` — age-verification landing page (QR + step track)
- `POST /rest/verification/qr/` — issue a fresh connect token / QR
- `POST /rest/verification/reset/` — clear state and start over (powers "Verify again")

## Testing

```bash
pytest                                     # all tests
pytest -v                                  # verbose
pytest app/core/requests/tests/            # contract tests
```

## Configuration reference

| Variable                  | Description                         | Default                          |
| ------------------------- | ----------------------------------- | -------------------------------- |
| `DJANGO_SECRET_KEY`       | Django secret key                   | insecure dev default             |
| `SECURED_FIELDS_KEY`      | Fernet key for encrypted fields     | insecure dev default             |
| `SECURED_FIELDS_HASH_SALT`| Salt for hashed fields              | insecure dev default             |
| `PERMYT_SERVICE_ID`       | Registered service ID in the broker | —                                |
| `PERMYT_PUBLIC_KEY_PATH`  | Path to PERMYT broker public key    | `keys/permyt/public.pem`         |
| `PRIVATE_KEY_PATH`        | Path to connector private key       | `keys/connector/private.pem`     |
| `BASE_URL`                | Requester's public URL              | `http://localhost:9015`          |
| `REQUESTER_CALLBACK_URL`  | Webhook URL sent to the broker      | `{BASE_URL}/rest/permyt/inbound` |
| `NONCE_TTL_SECONDS`       | Replay protection window            | `60`                             |
| `PERMYT_HOST`             | PERMYT broker URL                   | `http://localhost:8000`          |
| `REDIS_HOST`              | Redis host for Celery, Channels     | `localhost`                      |
| `VERIFY_MIN_AGE`          | Threshold sent as locked `min_age`  | `18`                             |
| `VERIFY_APP_NAME`         | Page title / navbar badge           | `PERMYT Verify`                  |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).
