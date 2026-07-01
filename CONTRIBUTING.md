# Contributing

This repo holds many independent PERMYT demo apps. Work happens **inside a single
demo directory** — each is a self-contained Django project with its own env,
settings, tests and deploy config.

## Conventions

- **One demo per directory**, one deployment **port** per demo (currently
  9010–9021 — pick the next free port for a new one and never reuse).
- **Providers** declare data via a static scope catalogue
  (`app/core/requests/scopes/catalogue.py`) — add one `ScopeDescriptor` per scope
  and re-run `python manage.py update_scope`. **Requesters** submit plain-English
  intents via `request_access` and render the returned facts; they never hand-pick
  scopes.
- **Keep UI copy honest**: PERMYT provides *source-direct provenance* — say "the
  authoritative source answered directly", not "cryptographically verified".
- **Secrets & machine state stay out of git** — `.env`, `keys/`, `settings/local.py`,
  `env/`, `<demo>/static/`, `*.sqlite3` are all ignored. Commit `.env.example`
  instead of `.env`.
- **Formatting/lint**: each demo uses `black`/`ruff` (line length 100). Run them
  before committing; `TestCode` (black/pylint) is part of each suite.

## Running tests

Each demo has its own suite (pure `pytest`, `settings.test`):

```bash
cd <demo>
python -m pytest              # all tests
python -m pytest -k <keyword> # subset
```

## Adding a new demo

1. Clone the closest existing demo (a provider from `government/`, a requester from
   `stripe-kyc/` or `requester/`) into a new top-level directory.
2. Rebrand: `settings/base.py` (`SESSION_COOKIE_NAME`, `ORGANIZATION_NAME`,
   `BASE_URL` port), `config/{app,tasks,beat,nginx}.conf` + `config/update`
   (program names, port, celery node, deploy path, `server_name`), templates and
   SCSS.
3. Regenerate migrations if the model changed; run `manage.py check`,
   `makemigrations --check`, and `compress --force`.
4. Add a row to the table in [`README.md`](README.md).
5. Register the Service on the broker dashboard and (providers) run `update_scope`.
