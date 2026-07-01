# PERMYT Demos

A collection of runnable demo apps for the **PERMYT** authorization protocol — a
network of independent services (banks, government registries, screening bodies,
marketplaces, exchanges…) that request and answer for user data **directly from
the authoritative source**, brokered by the PERMYT server. Each demo is its own
small Django app with a distinct brand, so the set behaves like real, separate
parties talking to each other.

> **What PERMYT delivers today:** *source-direct provenance* — trust comes from
> **who answered** (the request reached the real source over a signed, encrypted
> channel and the source responded directly). It is **not** cryptographic
> verifiable-credentials yet. UI copy across the demos keeps that line honest:
> "the authoritative source answered directly", never "cryptographically
> verified data".

## Roles

- **Broker** — the PERMYT server (separate repo). Runs AI scope selection, routes
  user approvals, brokers single-use encrypted tokens. Never sees the data.
- **Provider** — holds user data and answers scoped requests (e.g. a bank, a
  national identity service).
- **Requester** — asks for facts in plain English (e.g. an exchange onboarding a
  trader). Uses the `permyt` SDK.
- **Mobile app** — where the user scans QR codes to connect and approves/denies
  each request.

## The demos

Each app runs on its own port and deploys independently. Providers hold data;
requesters ask for it. Some apps are both.

| Demo | Dir | Port | Role | What it is |
|---|---|---|---|---|
| Demo Requester | `requester/` | 9010 | Requester | Generic requester — submit any plain-English request |
| NoteVault | `provider/` | 9011 | Provider | Space-themed notes provider (dynamic scopes) |
| Gov.ID / National Identity Service | `government/` | 9012 | Provider | Citizen + company registry; identity, over-18-without-DOB, right-to-work, driving licence, company KYB |
| Meridian Bank | `bank/` | 9013 | Provider + Requester | Bank account, movements, payments; source-of-funds & affordability; pulls verified identity from Gov.ID |
| The Aurelia | `hotel/` | 9014 | Requester | Boutique hotel booking / guest onboarding |
| Verify | `verify/` | 9015 | Requester | Standalone age-verification requester |
| Stripe KYC (Northwind Marketplace) | `stripe-kyc/` | 9016 | Requester | Onboards a company to a Stripe Connect account from verified facts |
| Atlas / Company Agent | `company-agent/` | 9017 | Provider | Company business plan, products, financials |
| Sentinel Screening | `sentinel/` | 9018 | Provider | Compliance watchlist — sanctions, PEP, adverse-media, gambling self-exclusion |
| Vaulton | `vaulton/` | 9019 | Requester | Crypto exchange onboarding (identity + address + source-of-funds + sanctions/PEP) |
| Luckwing | `luckwing/` | 9020 | Requester | iGaming onboarding (over-18, identity, affordability, self-exclusion) |
| Zipride | `zipride/` | 9021 | Requester | Driver onboarding (identity, right-to-work, driving licence) |

Ports **9010–9021** are reserved one-per-demo; keep them unique when adding more.

See [`WORKSHOP.md`](WORKSHOP.md) for a narrated end-to-end walkthrough of the
Stripe KYC / KYB flow.

## Repository layout

```
permyt-demo/
  <demo>/                     # one self-contained Django app per demo
    app/                      # core/{users,requests,logs}, common/pages, mixins, utils
    settings/                 # base.py, dev.py, test.py  (local.py is git-ignored)
    config/                   # nginx.conf, app.conf, tasks.conf, beat.conf, update
    keys/                     # ES256 keypair + broker pubkey        (git-ignored)
    pyproject.toml  uv.lock  .python-version  manage.py  pytest.ini  CLAUDE.md
  README.md  LICENSE  WORKSHOP.md  .gitignore  .gitattributes
```

Per-demo internals are documented in each demo's own `CLAUDE.md` / `README.md`.

## Running a demo locally

Each demo is independent and uses [uv](https://docs.astral.sh/uv/) with a `.venv`
virtualenv. From its directory:

```bash
cd <demo>
uv sync                              # create .venv (Python from .python-version) + install prod+dev deps
source .venv/bin/activate            # (or prefix commands with .venv/bin/)
cp .env.example .env                 # fill in secrets (see below)

# One-time ES256 keys
mkdir -p keys/connector keys/permyt
openssl ecparam -name prime256v1 -genkey -noout -out keys/connector/private.pem
openssl ec -in keys/connector/private.pem -pubout -out keys/connector/public.pem
# download the broker's public key from the dashboard -> keys/permyt/public.pem

python manage.py migrate
python manage.py update_scope        # providers only — push the scope catalogue
python manage.py runserver <port>    # e.g. 9013
```

Every app needs a **Service** registered on the PERMYT broker dashboard: create
it, upload `keys/connector/public.pem`, set its webhook to
`<BASE_URL>/rest/permyt/inbound/`, and copy the Service ID into `.env` as
`PERMYT_SERVICE_ID`. Providers must additionally run `manage.py update_scope`
whenever their `app/core/requests/scopes/catalogue.py` changes.

Requirements: [uv](https://docs.astral.sh/uv/), Python 3.14, Redis
(broker/cache/websockets), and a running PERMYT broker.

## Server deployment

All demos deploy under one `demo/` folder on the server and share a single
[`update`](update) script at the repo root. It cd's into the deploy folder
itself (`/var/deployments/demo`, override with `DEMO_ROOT`) so it **runs from
any directory**, pulls the monorepo once, then updates **only** the demos that
need it — those whose code changed in the pull, any missing their `.venv`, or
all of them with `--force`:

```bash
/var/deployments/demo/update    # from anywhere — pulls, updates changed demos
./update --force                # rebuild/restart every demo
./update bank government         # update only the named demos
DEMO_ROOT="$PWD" ./update        # run against a different folder (e.g. local)
```

For each demo the script runs `uv sync --frozen --no-dev` (installs the pinned
**prod** dependencies from `uv.lock` into `.venv`, dev group excluded), migrates,
runs `update_scope` (a no-op on requesters), `collectstatic`, and restarts that
demo's supervisor programs (names read from the demo's own `config/`). Each
demo's `config/` still provides its nginx + supervisor program definitions.
Prod config (DEBUG, DB, secrets) is loaded from each demo's git-ignored
`settings/local.py`. Generated state — `.venv/`, `keys/`, `.env`,
`settings/local.py`, `<demo>/static/`, `*.sqlite3` — is git-ignored and lives
only on the server.

### Migrating existing per-demo checkouts to this monorepo

The server already has each demo as its own git checkout under a `demo/` folder.
To switch them all to this single repository **without disturbing local state**
(keys, `.env`, virtualenvs, collected static are all git-ignored, so git leaves
them alone):

```bash
cd /var/deployments/demo            # the folder that contains bank/, government/, ...

# 1. Drop each demo's individual git metadata
find . -maxdepth 2 -name .git -type d -exec rm -rf {} +

# 2. Point the folder at the monorepo and adopt it in place
git init
git remote add origin <this-repo-url>
git fetch origin
git checkout -f <branch>            # e.g. main — overwrites tracked SOURCE only

# 3. Confirm nothing local was touched
git status                          # keys/, .env, static/, old env/ show as ignored

# 4. Build the uv .venv for every demo and (re)start them
./update --force
```

`git checkout -f` only overwrites **tracked** files (source that already matches
what's deployed), so existing code, keys, databases and the old `env/`
virtualenvs are untouched. The demos now run from a uv `.venv` (created by
`./update --force`); the previous `env/` directories are unused and can be
deleted. Supervisor/nginx configs already point at `.venv/bin/…`, so re-copy
each demo's `config/*.conf` into supervisor/nginx and reload once.

## License

MIT — see [`LICENSE`](LICENSE).
