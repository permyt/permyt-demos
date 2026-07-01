"""Static scope catalogue for the Government PERMYT provider.

Adding a new scope = append one ``ScopeDescriptor`` to ``SCOPES``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from .serializers import (
    CompanyIsRegisteredSerializer,
    IsOlderSerializer,
    IsResidentOfSerializer,
    ScopeSerializer,
    VatMatchesSerializer,
)

VALID_ACTIONS = ("read", "check")

PROFILE_PERSON = "person"
PROFILE_BUSINESS = "business"


@dataclass(frozen=True)
class ScopeDescriptor:
    reference: str
    name: str
    description: str
    input_serializer: type[ScopeSerializer] | None
    executor: Callable[[Any, dict], dict]
    high_sensitivity: bool = False
    default_consent_mode: str = "prompt_once"
    profile_type: str = PROFILE_PERSON


def _years_between(start: date, end: date) -> int:
    return end.year - start.year - ((end.month, end.day) < (start.month, start.day))


def _read(attr: str, key: str | None = None):
    key = key or attr

    def executor(user, _params):
        value = getattr(user, attr, None)
        if isinstance(value, date):
            value = value.isoformat()
        return {key: value}

    return executor


def _is_older(user, params):
    if not user.birthdate:
        return {"is_older": False}
    age = _years_between(user.birthdate, date.today())
    return {"is_older": age >= int(params["min_age"])}


def _is_resident_of(user, params):
    return {"is_resident": (user.country or "").upper() == params["country_code"].upper()}


def _vat_matches(user, params):
    return {
        "matches": (user.vat or "").strip().casefold()
        == (params.get("value") or "").strip().casefold()
    }


def _identity_verified(user, _params):
    """Confirm the citizen's identity is verified on file (source-direct)."""
    return {"verified": bool(user.identity_verified)}


def _right_to_work(user, _params):
    """Confirm the citizen's right to work, with the eligibility category."""
    return {
        "right_to_work": bool(user.right_to_work),
        "eligibility_type": user.right_to_work_type or "",
    }


def _driving_licence(user, _params):
    """Read the citizen's driving-licence standing (valid, categories, points)."""
    categories = [
        c.strip() for c in (user.driving_licence_categories or "").split(",") if c.strip()
    ]
    return {
        "valid": bool(user.driving_licence_valid),
        "categories": categories,
        "disqualified": bool(user.driving_licence_disqualified),
        "points_band": user.driving_licence_points_band or "",
    }


# ── Business (Companies-House / HMRC style) executors ─────────────────
def _business(user):
    """Return the user's ``BusinessProfile`` or raise if missing/wrong type."""
    from permyt.exceptions import InvalidUserError  # pylint: disable=import-outside-toplevel

    profile = getattr(user, "business_profile", None)
    if profile is None:
        raise InvalidUserError("This record has no business profile.")
    return profile


def _company_registry(user, _params):
    b = _business(user)
    return {
        "legal_name": b.legal_name,
        "registration_number": b.registration_number,
        "incorporation_date": b.incorporation_date.isoformat() if b.incorporation_date else None,
        "country": b.country,
        "structure": b.structure,
    }


def _company_tax_id(user, _params):
    return {"tax_id": _business(user).tax_id}


def _company_address(user, _params):
    return {"registered_address": _business(user).registered_address}


def _company_profile(user, _params):
    b = _business(user)
    return {"mcc": b.mcc, "website": b.website}


def _company_officers(user, _params):
    b = _business(user)
    return {
        "officers": [
            {
                "first_name": s.first_name,
                "last_name": s.last_name,
                "title": s.title,
                "is_director": s.is_director,
            }
            for s in b.shareholders.all()
        ]
    }


def _company_ownership(user, _params):
    b = _business(user)
    return {
        "owners": [
            {
                "first_name": s.first_name,
                "last_name": s.last_name,
                "birthdate": s.birthdate.isoformat() if s.birthdate else None,
                "address": s.address,
                "country": s.country,
                "id_number": s.id_number,
                "ownership_percent": float(s.ownership_percent),
                "is_representative": s.is_representative,
            }
            for s in b.shareholders.all()
        ]
    }


def _company_is_registered(user, params):
    target = (params.get("registration_number") or "").strip().casefold()
    return {"matches": (_business(user).registration_number or "").strip().casefold() == target}


SCOPES: tuple[ScopeDescriptor, ...] = (
    ScopeDescriptor(
        reference="name.read",
        name="Read full name",
        description="Read the citizen's full legal name on file.",
        input_serializer=None,
        executor=_read("full_name"),
    ),
    ScopeDescriptor(
        reference="birthdate.read",
        name="Read birthdate",
        description="Read the citizen's date of birth (ISO 8601).",
        input_serializer=None,
        executor=_read("birthdate"),
        high_sensitivity=True,
    ),
    ScopeDescriptor(
        reference="address.read",
        name="Read address",
        description="Read the citizen's registered residential address.",
        input_serializer=None,
        executor=_read("address"),
        high_sensitivity=True,
    ),
    ScopeDescriptor(
        reference="country.read",
        name="Read country of residence",
        description="Read the citizen's ISO 3166-1 alpha-2 country of residence.",
        input_serializer=None,
        executor=_read("country"),
    ),
    ScopeDescriptor(
        reference="vat.read",
        name="Read VAT / tax number",
        description="Read the citizen's VAT identification number.",
        input_serializer=None,
        executor=_read("vat"),
        high_sensitivity=True,
    ),
    ScopeDescriptor(
        reference="phone.read",
        name="Read phone number",
        description="Read the citizen's registered phone number (E.164).",
        input_serializer=None,
        executor=_read("phone"),
        high_sensitivity=True,
    ),
    ScopeDescriptor(
        reference="email.read",
        name="Read email",
        description="Read the citizen's registered email address.",
        input_serializer=None,
        executor=_read("email"),
    ),
    ScopeDescriptor(
        reference="tax_id.read",
        name="Read tax ID",
        description="Read the citizen's national tax identifier (e.g. SSN-style).",
        input_serializer=None,
        executor=_read("tax_id"),
        high_sensitivity=True,
    ),
    ScopeDescriptor(
        reference="passport.read",
        name="Read passport number",
        description="Read the citizen's national passport number.",
        input_serializer=None,
        executor=_read("passport_number"),
        high_sensitivity=True,
    ),
    ScopeDescriptor(
        reference="social_security.read",
        name="Read social security number",
        description="Read the citizen's social security number.",
        input_serializer=None,
        executor=_read("social_security_number"),
        high_sensitivity=True,
    ),
    ScopeDescriptor(
        reference="citizen_card.read",
        name="Read citizen card number",
        description="Read the citizen's national identity card number.",
        input_serializer=None,
        executor=_read("citizen_card_number"),
        high_sensitivity=True,
    ),
    ScopeDescriptor(
        reference="is_older.check",
        name="Verify minimum age",
        description=(
            "Privacy-preserving age check: returns true if the citizen is at "
            "least ``min_age`` years old, without revealing the birthdate."
        ),
        input_serializer=IsOlderSerializer,
        executor=_is_older,
    ),
    ScopeDescriptor(
        reference="is_resident_of.check",
        name="Verify country of residence",
        description=(
            "Returns true if the citizen's country of residence matches "
            "``country_code`` (ISO 3166-1 alpha-2)."
        ),
        input_serializer=IsResidentOfSerializer,
        executor=_is_resident_of,
    ),
    ScopeDescriptor(
        reference="vat_matches.check",
        name="Verify VAT number",
        description=(
            "Returns true if the citizen's VAT number on file matches the "
            "provided ``value`` (case- and whitespace-insensitive)."
        ),
        input_serializer=VatMatchesSerializer,
        executor=_vat_matches,
    ),
    ScopeDescriptor(
        reference="identity.check",
        name="Confirm identity",
        description=(
            "Confirms the citizen's identity is verified on the national "
            "register — returns true without exposing the underlying documents."
        ),
        input_serializer=None,
        executor=_identity_verified,
    ),
    ScopeDescriptor(
        reference="right_to_work.check",
        name="Confirm right to work",
        description=(
            "Confirms the citizen is entitled to work and returns their "
            "eligibility category (e.g. 'settled status')."
        ),
        input_serializer=None,
        executor=_right_to_work,
    ),
    ScopeDescriptor(
        reference="driving_licence.read",
        name="Read driving licence standing",
        description=(
            "Reads the citizen's driving-licence standing: whether it is valid, "
            "the categories held, whether they are disqualified, and their "
            "penalty-points band."
        ),
        input_serializer=None,
        executor=_driving_licence,
        high_sensitivity=True,
    ),
    # ── Business / company registry scopes (profile_type="business") ──
    ScopeDescriptor(
        reference="company.registry.read",
        name="Read company registry record",
        description=(
            "Read the company's authoritative registry record: legal name, "
            "registration number, incorporation date, country, and structure."
        ),
        input_serializer=None,
        executor=_company_registry,
        profile_type=PROFILE_BUSINESS,
    ),
    ScopeDescriptor(
        reference="company.tax_id.read",
        name="Read company tax ID",
        description="Read the company's tax identifier (HMRC / VAT registration).",
        input_serializer=None,
        executor=_company_tax_id,
        high_sensitivity=True,
        profile_type=PROFILE_BUSINESS,
    ),
    ScopeDescriptor(
        reference="company.address.read",
        name="Read registered address",
        description="Read the company's registered office address.",
        input_serializer=None,
        executor=_company_address,
        profile_type=PROFILE_BUSINESS,
    ),
    ScopeDescriptor(
        reference="company.profile.read",
        name="Read business profile",
        description="Read the company's MCC (merchant category) and website.",
        input_serializer=None,
        executor=_company_profile,
        profile_type=PROFILE_BUSINESS,
    ),
    ScopeDescriptor(
        reference="company.officers.read",
        name="Read company officers",
        description="List the company's officers/directors (name, title, director flag).",
        input_serializer=None,
        executor=_company_officers,
        profile_type=PROFILE_BUSINESS,
    ),
    ScopeDescriptor(
        reference="company.ownership.read",
        name="Read beneficial owners",
        description=(
            "List the company's beneficial owners with the KYC needed to onboard "
            "them: name, date of birth, address, id number, and ownership percent."
        ),
        input_serializer=None,
        executor=_company_ownership,
        high_sensitivity=True,
        profile_type=PROFILE_BUSINESS,
    ),
    ScopeDescriptor(
        reference="company.is_registered.check",
        name="Verify company registration",
        description=(
            "Returns true if the company's registration number on file matches "
            "the provided ``registration_number`` (case-insensitive)."
        ),
        input_serializer=CompanyIsRegisteredSerializer,
        executor=_company_is_registered,
        profile_type=PROFILE_BUSINESS,
    ),
)


SCOPES_BY_REFERENCE: dict[str, ScopeDescriptor] = {d.reference: d for d in SCOPES}
