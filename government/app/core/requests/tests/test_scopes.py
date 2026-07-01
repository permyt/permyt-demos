"""Tests for the static Government scope catalogue."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from permyt.exceptions import InvalidInputError, InvalidScopeError

from app.core.requests.scopes.utils import GovernmentScopes, sync_scopes_to_broker

EXPECTED_REFERENCES = {
    "name.read",
    "birthdate.read",
    "address.read",
    "country.read",
    "vat.read",
    "phone.read",
    "email.read",
    "tax_id.read",
    "passport.read",
    "social_security.read",
    "citizen_card.read",
    "is_older.check",
    "is_resident_of.check",
    "vat_matches.check",
    "identity.check",
    "right_to_work.check",
    "driving_licence.read",
    "company.registry.read",
    "company.tax_id.read",
    "company.address.read",
    "company.profile.read",
    "company.officers.read",
    "company.ownership.read",
    "company.is_registered.check",
}


class TestCatalogueShape:
    def test_get_available_scopes_returns_full_catalogue(self):
        refs = GovernmentScopes().get_available_scopes()
        assert set(refs) == EXPECTED_REFERENCES
        assert len(refs) == len(EXPECTED_REFERENCES)

    def test_unknown_reference_raises(self):
        with pytest.raises(InvalidScopeError):
            GovernmentScopes()._get_descriptor("nope.read")

    def test_invalid_action_raises(self):
        with pytest.raises(InvalidScopeError):
            GovernmentScopes()._parse_reference("name.write")

    def test_missing_dot_raises(self):
        with pytest.raises(InvalidScopeError):
            GovernmentScopes()._parse_reference("name")


@pytest.mark.django_db
class TestReadScopes:
    @pytest.mark.parametrize(
        "reference,attr,expected_key",
        [
            ("name.read", "full_name", "full_name"),
            ("address.read", "address", "address"),
            ("country.read", "country", "country"),
            ("vat.read", "vat", "vat"),
            ("phone.read", "phone", "phone"),
            ("email.read", "email", "email"),
            ("tax_id.read", "tax_id", "tax_id"),
        ],
    )
    def test_read_returns_field_value(self, user, reference, attr, expected_key):
        result = GovernmentScopes().execute(user, reference, {})
        assert result == {expected_key: getattr(user, attr)}

    def test_birthdate_read_returns_iso(self, user):
        user.birthdate = date(1990, 6, 15)
        user.save()
        result = GovernmentScopes().execute(user, "birthdate.read", {})
        assert result == {"birthdate": "1990-06-15"}

    def test_birthdate_read_handles_none(self, user):
        user.birthdate = None
        user.save()
        result = GovernmentScopes().execute(user, "birthdate.read", {})
        assert result == {"birthdate": None}


@pytest.mark.django_db
class TestIsOlder:
    def test_above_threshold(self, user):
        user.birthdate = date(1990, 1, 1)
        user.save()
        result = GovernmentScopes().execute(user, "is_older.check", {"min_age": 18})
        assert result == {"is_older": True}

    def test_below_threshold(self, user):
        user.birthdate = date.today() - timedelta(days=365 * 17)
        user.save()
        result = GovernmentScopes().execute(user, "is_older.check", {"min_age": 18})
        assert result == {"is_older": False}

    def test_exact_boundary(self, user):
        # 18 years ago to the day → True (uses >=).
        today = date.today()
        try:
            user.birthdate = today.replace(year=today.year - 18)
        except ValueError:
            user.birthdate = today.replace(year=today.year - 18, day=28)
        user.save()
        result = GovernmentScopes().execute(user, "is_older.check", {"min_age": 18})
        assert result == {"is_older": True}

    def test_birthdate_none(self, user):
        user.birthdate = None
        user.save()
        result = GovernmentScopes().execute(user, "is_older.check", {"min_age": 0})
        assert result == {"is_older": False}


@pytest.mark.django_db
class TestIsResidentOf:
    def test_match_uppercases_both_sides(self, user):
        user.country = "pt"  # save() uppercases this
        user.save()
        result = GovernmentScopes().execute(user, "is_resident_of.check", {"country_code": "PT"})
        assert result == {"is_resident": True}

    def test_mismatch(self, user):
        user.country = "US"
        user.save()
        result = GovernmentScopes().execute(user, "is_resident_of.check", {"country_code": "PT"})
        assert result == {"is_resident": False}


@pytest.mark.django_db
class TestVatMatches:
    @pytest.mark.parametrize(
        "stored,probe,expected",
        [
            ("PT123456789", "PT123456789", True),
            ("PT123456789", "pt123456789", True),
            ("PT123456789", "  PT123456789 ", True),
            ("PT123456789", "PT123456788", False),
            ("", "PT123456789", False),
        ],
    )
    def test_match(self, user, stored, probe, expected):
        user.vat = stored
        user.save()
        result = GovernmentScopes().execute(user, "vat_matches.check", {"value": probe})
        assert result == {"matches": expected}


@pytest.mark.django_db
class TestLockedInputEnforcement:
    def test_matching_input_passes(self):
        validated = GovernmentScopes().validate_params(
            "is_older.check", {"min_age": 18}, locked={"min_age": 18}
        )
        assert validated == {"min_age": 18}

    def test_tampered_input_rejected(self):
        with pytest.raises(InvalidInputError):
            GovernmentScopes().validate_params(
                "is_older.check", {"min_age": 0}, locked={"min_age": 18}
            )

    def test_predicate_without_locked_input_rejected(self):
        # Strict-mode: identity-data predicate scopes require broker-locked inputs.
        with pytest.raises(InvalidInputError):
            GovernmentScopes().validate_params("is_older.check", {"min_age": 18}, locked={})

    def test_read_scope_without_locked_passes(self):
        # Pure reads have no inputs; locked={} is fine.
        assert GovernmentScopes().validate_params("name.read", {}, locked={}) == {}

    def test_validate_locked_canonicalizes(self):
        validated = GovernmentScopes().validate_locked(
            "is_resident_of.check", {"country_code": "us"}
        )
        assert validated == {"country_code": "US"}


class TestEndpointMapping:
    def test_read_endpoint(self):
        endpoint = GovernmentScopes.get_endpoint("name.read")
        assert endpoint["url"].endswith("/rest/name/read/")
        assert endpoint["input_fields"] is None

    def test_check_endpoint_includes_inputs(self):
        endpoint = GovernmentScopes.get_endpoint("is_older.check")
        assert endpoint["url"].endswith("/rest/is_older/check/")
        assert "min_age" in endpoint["input_fields"]


class TestSyncScopesToBroker:
    def test_pushes_full_catalogue_definitions(self):
        with patch(
            "app.core.requests.client.PermytClient.update_scopes",
            return_value={"ok": True},
        ) as update:
            with patch("app.core.requests.client.PermytClient.__init__", return_value=None):
                sync_scopes_to_broker()

        update.assert_called_once()
        (definitions,), _ = update.call_args
        assert len(definitions) == len(EXPECTED_REFERENCES)
        assert {d["reference"] for d in definitions} == EXPECTED_REFERENCES
        # Predicate scopes carry input definitions; reads do not.
        by_ref = {d["reference"]: d for d in definitions}
        assert by_ref["is_older.check"]["inputs"][0]["name"] == "min_age"
        assert by_ref["name.read"]["inputs"] == []
