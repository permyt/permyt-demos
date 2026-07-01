"""Map PERMYT provider responses to Stripe Connect account parameters.

The broker returns one response dict per called provider endpoint, each keyed by
scope reference (e.g. ``{"company.registry.read": {...}}``). This module merges
them and translates the verified facts into Stripe ``Account.create`` /
``Account.create_person`` parameters, tagging each field with its source
provider for the onboarding UI's provenance display.
"""

from __future__ import annotations

import re
from typing import Any

from django.conf import settings

# Which authoritative source answers each scope — drives the UI provenance tags.
SOURCE_BY_REFERENCE = {
    "company.registry.read": "Government · Registry",
    "company.tax_id.read": "Government · Tax",
    "company.address.read": "Government · Registry",
    "company.profile.read": "Government · Registry",
    "company.officers.read": "Government · Registry",
    "company.ownership.read": "Government · Registry",
    "business_plan.read": "Company Agent",
    "financials.summary": "Company Agent",
    "products.read": "Company Agent",
    "company.ask": "Company Agent",
    "balance.read": "Bank",
    "accounts.read": "Bank",
}

# Stripe test-mode magic values that clear verification without real documents.
TEST_TAX_ID = "000000000"
TEST_ID_NUMBER = "000000000"
TEST_DOB = {"day": 1, "month": 1, "year": 1901}

# Stripe's documented test bank accounts (https://stripe.com/docs/connect/
# testing#account-numbers). A *test* Stripe key REJECTS real account numbers,
# so we must send one of these for the external (payout) account. Keyed by the
# connected-account country; each is a full ``external_account`` payload.
TEST_BANK_BY_COUNTRY = {
    "GB": {"currency": "gbp", "account_number": "GB82WEST12345698765432"},
    "US": {"currency": "usd", "routing_number": "110000000", "account_number": "000123456789"},
    "IE": {"currency": "eur", "account_number": "IE29AIBK93115212345678"},
    "DE": {"currency": "eur", "account_number": "DE89370400440532013000"},
    "FR": {"currency": "eur", "account_number": "FR1420041010050500013M02606"},
    "ES": {"currency": "eur", "account_number": "ES9121000418450200051332"},
    "PT": {"currency": "eur", "account_number": "PT50000201231234567890154"},
    "NL": {"currency": "eur", "account_number": "NL39RABO0300065264"},
}

UK_POSTCODE_RE = re.compile(r"[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}", re.IGNORECASE)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower()) or "company"


def _synth_email(*parts: str, domain: str = "") -> str:
    """Build a plausible email from name parts (contact fields aren't held by
    the government registry, so we derive them for the KYC payload)."""
    local = ".".join(_slug(p) for p in parts if p) or "contact"
    return f"{local}@{domain or 'permyt-demo.com'}"


def _synth_phone() -> str:
    # E.164, Stripe test-friendly. Real value isn't held by the registry.
    return "+442079460000"


def merge_responses(responses: list[Any]) -> dict[str, dict]:
    """Merge the per-endpoint response dicts into one ``{reference: payload}`` map."""
    combined: dict[str, dict] = {}
    for resp in responses or []:
        if isinstance(resp, dict):
            for ref, payload in resp.items():
                if isinstance(payload, dict):
                    combined[ref] = payload
    return combined


def _parse_dob(iso: str | None) -> dict | None:
    if not iso:
        return None
    try:
        year, month, day = (int(x) for x in iso.split("-")[:3])
        return {"day": day, "month": month, "year": year}
    except (ValueError, AttributeError):
        return None


def _parse_address(raw: str, country: str) -> dict:
    """Best-effort split of a single-line address into Stripe address parts."""
    raw = (raw or "").strip()
    country = (country or settings.STRIPE_ACCOUNT_COUNTRY or "GB").upper()
    postcode_match = UK_POSTCODE_RE.search(raw)
    postal_code = postcode_match.group(0).upper() if postcode_match else ""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    line1 = parts[0] if parts else raw
    city = parts[-1] if len(parts) > 1 else "London"
    # Strip a trailing postcode from the city token if it leaked in.
    if postal_code and postal_code.lower() in city.lower():
        city = city.replace(postal_code, "").strip() or "London"
    return {
        "line1": line1 or "1 Demo Street",
        "city": city or "London",
        "postal_code": postal_code or "EC1M 5QA",
        "country": country,
    }


def _normalize_url(raw: str | None) -> str:
    """Return a Stripe-acceptable URL, or ``""`` if the value can't be one.

    The synthetic gov website may arrive without a scheme or as junk. Add
    ``https://`` when missing and require a dotted, space-free host; otherwise
    drop it so Stripe doesn't 400 on ``business_profile[url]``.
    """
    url = (raw or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    host = url.split("//", 1)[-1].split("/", 1)[0].lower()
    if "." not in host or " " in host or host.startswith(".") or host.endswith("."):
        return ""
    # Stripe rejects reserved / documentation / test domains (example.com,
    # test.com, *.example, localhost, …) with "Not a valid URL" — drop them so
    # the synthetic gov website never 400s the account create.
    if host == "localhost" or host.split(".")[-1] in {"example", "test", "localhost", "invalid"}:
        return ""
    root = ".".join(host.split(".")[-2:])
    if root in {"example.com", "example.org", "example.net", "example.edu", "test.com"}:
        return ""
    return url


def build_payload(combined: dict[str, dict]) -> dict:
    """Build Stripe params + a UI-friendly ``collected`` provenance list.

    Returns ``{account, persons, collected}`` where ``account`` feeds
    ``Account.create``, ``persons`` feeds ``Account.create_person`` (one each),
    and ``collected`` is ``[{label, value, source}]`` for the dashboard.
    """
    use_test = settings.STRIPE_USE_TEST_VALUES
    collected: list[dict] = []

    registry = combined.get("company.registry.read", {})
    tax = combined.get("company.tax_id.read", {})
    addr = combined.get("company.address.read", {})
    profile = combined.get("company.profile.read", {})
    ownership = combined.get("company.ownership.read", {})

    country = (registry.get("country") or settings.STRIPE_ACCOUNT_COUNTRY or "GB").upper()

    company: dict = {}
    if registry:
        company["name"] = registry.get("legal_name", "")
        company["registration_number"] = registry.get("registration_number", "")
        collected.append(
            {
                "label": "Legal name",
                "value": registry.get("legal_name", ""),
                "source": SOURCE_BY_REFERENCE["company.registry.read"],
            }
        )
        collected.append(
            {
                "label": "Registration number",
                "value": registry.get("registration_number", ""),
                "source": SOURCE_BY_REFERENCE["company.registry.read"],
            }
        )
    if tax:
        real_tax = tax.get("tax_id", "")
        company["tax_id"] = TEST_TAX_ID if use_test else real_tax
        collected.append(
            {
                "label": "Tax ID",
                "value": real_tax,
                "source": SOURCE_BY_REFERENCE["company.tax_id.read"],
            }
        )
    if addr:
        company["address"] = _parse_address(addr.get("registered_address", ""), country)
        collected.append(
            {
                "label": "Registered address",
                "value": addr.get("registered_address", ""),
                "source": SOURCE_BY_REFERENCE["company.address.read"],
            }
        )

    # Contact details + completeness flags. The registry doesn't hold a phone or
    # email, so derive them; the *_provided flags tell Stripe the owner/director/
    # executive lists are complete (clears the matching "provide a …" actions).
    legal_name = registry.get("legal_name", "") if registry else ""
    website = _normalize_url(profile.get("website")) if profile else ""
    domain = website.split("//", 1)[-1].split("/", 1)[0] if website else ""
    company["phone"] = _synth_phone()
    company["directors_provided"] = True
    company["owners_provided"] = True
    company["executives_provided"] = True
    company_email = _synth_email(legal_name or "company", domain=domain)

    business_profile: dict = {}
    if profile:
        if profile.get("mcc"):
            business_profile["mcc"] = profile["mcc"]
        # Stripe rejects ``business_profile[url]`` unless it's a fully-qualified
        # URL. The gov website is synthetic and may be bare (no scheme) or junk,
        # so normalise it and only send it when it's plausibly valid — otherwise
        # omit it (``product_description`` already satisfies the requirement).
        website_url = _normalize_url(profile.get("website"))
        if website_url:
            business_profile["url"] = website_url
        collected.append(
            {
                "label": "MCC",
                "value": profile.get("mcc", ""),
                "source": SOURCE_BY_REFERENCE["company.profile.read"],
            }
        )

    description = _build_description(combined, collected)
    if description:
        business_profile["product_description"] = description

    account = {
        "type": "custom",
        "country": country,
        "email": company_email,
        "business_type": "company",
        "company": company,
        "business_profile": business_profile,
        "capabilities": {
            "card_payments": {"requested": True},
            "transfers": {"requested": True},
        },
    }

    # Payout (external) account — from the company's bank if it shared one,
    # otherwise a Stripe test bank token so the payout requirement clears.
    external = _external_account(
        combined.get("balance.read") or combined.get("accounts.read") or {},
        country,
        use_test,
        collected,
    )
    if external:
        account["external_account"] = external

    persons = _build_persons(ownership, use_test, domain, collected)
    return {"account": account, "persons": persons, "collected": collected}


def _external_account(bank: dict, country: str, use_test: bool, collected: list[dict]):
    """Resolve the Stripe external (payout) account.

    The company's real IBAN is recorded for provenance, but a *test* Stripe key
    rejects real account numbers ("You must use a test bank account number"), so
    whenever we're on a test key (or test mode is forced) we send Stripe's
    documented test bank account for the country. Only a live key + a real IBAN
    passes the IBAN through.
    """
    iban = (bank.get("iban") or "").strip()
    currency = (bank.get("currency") or "").strip().lower()
    if iban:
        collected.append(
            {"label": "Bank account (IBAN)", "value": iban, "source": SOURCE_BY_REFERENCE["balance.read"]}
        )

    is_test_key = (settings.STRIPE_SECRET_KEY or "").startswith("sk_test")
    if use_test or is_test_key or not iban:
        test_bank = TEST_BANK_BY_COUNTRY.get(country) or TEST_BANK_BY_COUNTRY["GB"]
        return {"object": "bank_account", "country": country, **test_bank}

    return {
        "object": "bank_account",
        "country": country,
        "currency": currency or "gbp",
        "account_number": iban,
    }


def _build_description(combined: dict[str, dict], collected: list[dict]) -> str:
    """Compose business_profile.product_description from the company agent's data."""
    bits = []
    products = combined.get("products.read", {}).get("products")
    if products:
        bits.append("Products: " + ", ".join(products))
        collected.append(
            {
                "label": "Products",
                "value": ", ".join(products),
                "source": SOURCE_BY_REFERENCE["products.read"],
            }
        )
    plan = combined.get("business_plan.read", {}).get("business_plan")
    if plan:
        collected.append(
            {
                "label": "Business plan",
                "value": plan[:160] + "…",
                "source": SOURCE_BY_REFERENCE["business_plan.read"],
            }
        )
        bits.append(plan)
    answer = combined.get("company.ask", {}).get("answer")
    if answer:
        collected.append(
            {
                "label": "Agent answer",
                "value": answer[:160],
                "source": SOURCE_BY_REFERENCE["company.ask"],
            }
        )
        bits.append(answer)
    return " ".join(bits)[:5000]


def _build_persons(ownership: dict, use_test: bool, domain: str, collected: list[dict]) -> list[dict]:
    persons = []
    owners = ownership.get("owners", []) or []
    for i, owner in enumerate(owners):
        dob = TEST_DOB if use_test else _parse_dob(owner.get("birthdate"))
        first = owner.get("first_name", "")
        last = owner.get("last_name", "")
        is_rep = bool(owner.get("is_representative")) or i == 0  # at least one representative
        person = {
            "first_name": first,
            "last_name": last,
            # Contact + job title aren't on the registry record — derive so the
            # per-person phone/email/title requirements clear.
            "email": _synth_email(first, last, domain=domain),
            "phone": _synth_phone(),
            "relationship": {
                "owner": True,
                "director": True,
                "executive": True,
                "representative": is_rep,
                "percent_ownership": owner.get("ownership_percent", 0),
                "title": owner.get("title") or "Director",
            },
        }
        if dob:
            person["dob"] = dob
        if owner.get("address"):
            person["address"] = _parse_address(
                owner["address"], owner.get("country") or settings.STRIPE_ACCOUNT_COUNTRY
            )
        person["id_number"] = TEST_ID_NUMBER if use_test else owner.get("id_number", "")
        persons.append(person)
        collected.append(
            {
                "label": "Beneficial owner",
                "value": f"{first} {last} — {owner.get('ownership_percent', 0)}%",
                "source": SOURCE_BY_REFERENCE["company.ownership.read"],
            }
        )
    return persons
