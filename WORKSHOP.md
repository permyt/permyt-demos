# Permyt × Stripe — End-to-End Workshop Demo

Runnable demo of the deck's agentic KYC/KYB flow: a marketplace (**Stripe KYC**)
onboards **London Coffee Roasters Ltd** for Stripe Treasury payouts by pulling
**verified facts straight from authoritative sources** through PERMYT — no document
upload — and opens a Stripe Connect connected account.

```
 Stripe KYC (requester, :9016)        PERMYT broker (:8000)
        │  request_access  ───────────────▶│  AI picks scopes across the
        │                                  │  company profile's providers
        │                                  ▼
        │                      Company approves once on mobile
        │                                  │
        │  ◀── encrypted tokens ───────────│
        ▼
   pulls facts directly from:
     • Government  (:9012)  company registry, tax id, address, MCC, owners (KYC)
     • Company Agent (:9014) business plan / financials / products / ask
        │
        ▼  maps → stripe-python
   Stripe Connect connected account (test mode)
```

## Components

| Role | App | Port | Notes |
|---|---|---|---|
| Provider | `government/` | 9012 | Persons **and** businesses; `company.*` scopes + person scopes; registry console |
| Provider | `company-agent/` | 9014 | Company KB; `business_plan.read`, `financials.summary`, `products.read`, `company.ask` (LLM) |
| Requester | `stripe-kyc/` | 9016 | Submits onboarding request, maps facts → Stripe, live two-pane dashboard |
| Broker | `../permyt/` | 8000 | The PERMYT server (run separately, with Redis + Celery) |

## Key model finding (single approval)

A broker **profile** can hold many service connections. The company connects
`government` (business), `company-agent`, and `stripe-kyc` to its **same** profile,
so one `request_access` resolves scopes across all of them and **one company
approval** covers the whole onboarding. Shareholder KYC rides on the business
record's `company.ownership.read` scope (no separate per-owner approval).

---

## 1. One-time setup

### 1a. Register the two new services in the PERMYT dashboard
Government is already registered. For **Company Agent** (provider) and **Stripe KYC**
(requester), create a service in the broker dashboard and provide:

| Field | Company Agent | Stripe KYC |
|---|---|---|
| Role | Provider | Requester |
| Connector public key | `company-agent/keys/connector/public.pem` | `stripe-kyc/keys/connector/public.pem` |
| `callback_url` | `http://localhost:9014/rest/permyt/inbound` | `http://localhost:9016/rest/permyt/inbound` |

The dashboard returns a **service id** for each. (The broker uses the per-request
`callback_url` Stripe-KYC already sends, so the requester works even if the
service-level callback is blank.)

### 1b. Fill each demo's `.env`
```bash
cd <demo> && cp .env.example .env
```
Set `PERMYT_SERVICE_ID` to the id from 1a. Keep `PERMYT_PUBLIC_KEY_PATH` pointing at
`keys/permyt/public.pem` (the broker public key — already copied into each demo).
- **company-agent/.env**: set `ANTHROPIC_API_KEY` (optional — without it `company.ask`
  returns a clearly-labelled stub).
- **stripe-kyc/.env**: set `STRIPE_SECRET_KEY=sk_test_…` (optional — without it the
  account creation is stubbed but the full mapped payload still shows on the dashboard).

### 1c. Python envs + migrate + seed
```bash
for d in government company-agent stripe-kyc; do
  cd $d && python -m venv env && source env/bin/activate \
    && pip install -r requirements.txt \
    && python manage.py migrate \
    && deactivate; cd ..
done

# Seed workshop data + push scopes (providers only)
cd government     && source env/bin/activate && python manage.py seed_demo && python manage.py update_scope && deactivate && cd ..
cd company-agent  && source env/bin/activate && python manage.py seed_demo && python manage.py update_scope && deactivate && cd ..
```

---

## 2. Stripe sandbox (what you do once)
1. Log into Stripe → toggle **Test mode** (top-right). Sandboxes are test-mode.
2. **Developers → API keys** → copy the **Secret key** (`sk_test_…`) into
   `stripe-kyc/.env` as `STRIPE_SECRET_KEY`.
3. Enable **Connect** (Test mode) so `Account.create(type="custom")` works.
4. Test verification values are pre-wired by the mapper (`STRIPE_USE_TEST_VALUES=true`):
   tax id `000000000`, dob `1901-01-01`, id number `000000000` — these clear Stripe's
   test verification without documents.
5. Watch created accounts under **Connect → Accounts** (test data).
Docs: stripe.com/docs/connect/testing · stripe.com/docs/api/accounts/create

---

## 3. Run

Terminal A — broker (see `../permyt`):
```bash
cd ../permyt && python manage.py runserver 8000   # + `python manage.py celery` in another shell + Redis
```
Terminals B/C/D — the demos:
```bash
cd government    && source env/bin/activate && python manage.py runserver 9012
cd company-agent && source env/bin/activate && python manage.py runserver 9014
cd stripe-kyc    && source env/bin/activate && python manage.py runserver 9016
```

---

## 4. Demo script

1. **Government** `http://localhost:9012/register/` → the seeded *London Coffee
   Roasters Ltd* business is listed → open it → shows its connect QR.
2. On the PERMYT mobile app (using the **company** profile), scan:
   - the **Government business** QR, then
   - the **Company Agent** QR (`http://localhost:9014/register/<id>/`), then
   - the **Stripe KYC** QR (`http://localhost:9016/` login page).
   All three land on the same company profile.
3. **Stripe KYC** `http://localhost:9016/` is now the onboarding dashboard. Click
   **Start onboarding**.
4. Approve once on mobile. Watch the dashboard stage track advance
   *Request sent → Awaiting approval → Approved → Fetching from sources → Pushing to
   Stripe → Account created*, with each verified fact shimmering in tagged by its
   **source provider**, ending on the `acct_…` id and `requirements.currently_due: []`.
5. Confirm the connected account under Stripe **Connect → Accounts** (test data).

---

## What's where
- Government business model + `company.*` scopes: `government/app/core/users/models.py`,
  `government/app/core/requests/scopes/catalogue.py`; registry UI in `government/app/common/pages/`.
- Company agent KB + LLM: `company-agent/app/core/users/models.py`,
  `company-agent/app/core/agent/llm.py`, scopes in `company-agent/app/core/requests/scopes/`.
- Stripe mapping + push: `stripe-kyc/app/core/stripe_kyc/{mapper,service}.py`; the live
  dashboard in `stripe-kyc/app/common/pages/` + completion handler in
  `stripe-kyc/app/core/requests/client.py`.

## Tests
```bash
cd <demo> && source env/bin/activate && pytest -q
```
All three suites pass (incl. their black + pylint gates). Stripe-KYC includes
`app/core/requests/tests/test_mapper.py` covering the field mapper + test-value
substitution; Company-Agent includes `company.ask` fail-closed tests.
