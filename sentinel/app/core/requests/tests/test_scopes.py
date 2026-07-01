"""Tests for the static Sentinel Screening scope catalogue."""

from unittest.mock import patch

import pytest

from permyt.exceptions import InvalidScopeError

from app.core.requests.scopes.utils import SentinelScopes, sync_scopes_to_broker

EXPECTED_REFERENCES = {
    "sanctions.check",
    "pep.check",
    "adverse_media.check",
    "self_exclusion.check",
}

# scope reference → (model attr, response key)
SCOPE_MAP = {
    "sanctions.check": ("sanctions_match", "sanctions_match"),
    "pep.check": ("pep", "pep"),
    "adverse_media.check": ("adverse_media", "adverse_media"),
    "self_exclusion.check": ("self_excluded", "self_excluded"),
}


class TestCatalogueShape:
    def test_get_available_scopes_returns_full_catalogue(self):
        refs = SentinelScopes().get_available_scopes()
        assert set(refs) == EXPECTED_REFERENCES
        assert len(refs) == len(EXPECTED_REFERENCES)

    def test_unknown_reference_raises(self):
        with pytest.raises(InvalidScopeError):
            SentinelScopes()._get_descriptor("nope.check")

    def test_invalid_action_raises(self):
        with pytest.raises(InvalidScopeError):
            SentinelScopes()._parse_reference("sanctions.write")

    def test_missing_dot_raises(self):
        with pytest.raises(InvalidScopeError):
            SentinelScopes()._parse_reference("sanctions")


@pytest.mark.django_db
class TestCheckScopes:
    @pytest.mark.parametrize("reference", sorted(EXPECTED_REFERENCES))
    def test_clear_subject_returns_false(self, user, reference):
        attr, key = SCOPE_MAP[reference]
        result = SentinelScopes().execute(user, reference, {})
        assert result == {key: False}

    @pytest.mark.parametrize("reference", sorted(EXPECTED_REFERENCES))
    def test_flagged_subject_returns_true(self, user, reference):
        attr, key = SCOPE_MAP[reference]
        setattr(user, attr, True)
        user.save()
        result = SentinelScopes().execute(user, reference, {})
        assert result == {key: True}

    def test_no_inputs_required(self):
        # Sentinel scopes declare no inputs — locked={} must pass.
        assert SentinelScopes().validate_params("sanctions.check", {}, locked={}) == {}


class TestEndpointMapping:
    def test_check_endpoint(self):
        endpoint = SentinelScopes.get_endpoint("sanctions.check")
        assert endpoint["url"].endswith("/rest/sanctions/check/")
        assert endpoint["input_fields"] is None


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
        # No Sentinel scope declares inputs; all are high-sensitivity prompt_once.
        for d in definitions:
            assert d["inputs"] == []
            assert d["high_sensitivity"] is True
            assert d["default_consent_mode"] == "prompt_once"
