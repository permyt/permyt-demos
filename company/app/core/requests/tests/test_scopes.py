"""Company-Agent scope catalogue tests."""

import pytest

from permyt.exceptions import InvalidInputError, InvalidScopeError

from app.core.requests.scopes.utils import CompanyAgentScopes


class TestStructuredScopes:
    """Structured KB read scopes return the stored fields."""

    @pytest.mark.django_db
    def test_business_plan_read(self, user):
        out = CompanyAgentScopes().execute(user, "business_plan.read", {})
        assert out["business_plan"] == user.company_kb.business_plan

    @pytest.mark.django_db
    def test_products_read(self, user):
        out = CompanyAgentScopes().execute(user, "products.read", {})
        assert out["products"] == user.company_kb.products

    def test_unknown_scope_rejected(self):
        with pytest.raises(InvalidScopeError):
            CompanyAgentScopes()._get_descriptor("does.not.exist")


class TestAskScope:
    """The open-ended company.ask scope is fail-closed on its locked question."""

    def test_ask_requires_locked_input(self):
        with pytest.raises(InvalidInputError):
            CompanyAgentScopes().validate_params("company.ask", {"question": "hi"}, locked={})

    def test_ask_locked_mismatch_rejected(self):
        scopes = CompanyAgentScopes()
        with pytest.raises(InvalidInputError):
            scopes.validate_params(
                "company.ask",
                {"question": "tampered"},
                locked={"question": "approved question"},
            )

    def test_ask_locked_match_ok(self):
        scopes = CompanyAgentScopes()
        out = scopes.validate_params(
            "company.ask",
            {"question": "approved question"},
            locked={"question": "approved question"},
        )
        assert out["question"] == "approved question"

    @pytest.mark.django_db
    def test_ask_executes_without_api_key(self, user, settings):
        # No API key -> stubbed answer, but still returns a dict with the answer.
        settings.ANTHROPIC_API_KEY = ""
        out = CompanyAgentScopes().execute(user, "company.ask", {"question": "What do you sell?"})
        assert "answer" in out and out["question"] == "What do you sell?"
