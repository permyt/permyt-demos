"""Tests for the provider-response → labelled-facts flattener."""

from app.core.requests.facts import collect_facts


class TestCollectFacts:
    """collect_facts flattens ``call_services`` output into grouped facts."""

    def test_groups_facts_by_source(self):
        facts = collect_facts(
            [
                {"sanctions.check": {"sanctions_match": False}},
                {"name.read": {"full_name": "Jane Doe"}},
            ]
        )
        by_source = {(f["source"], f["label"]): f["value"] for f in facts}
        assert by_source[("Sentinel Screening", "Sanctions match")] == "No"
        assert by_source[("National Identity Service", "Full name")] == "Jane Doe"

    def test_booleans_render_yes_no(self):
        facts = collect_facts([{"identity.check": {"verified": True}}])
        assert facts[0]["value"] == "Yes"

    def test_lists_render_comma_separated(self):
        facts = collect_facts([{"movements.list": {"items": ["a", "b"]}}])
        assert facts[0]["value"] == "a, b"

    def test_unknown_reference_falls_back_to_provider(self):
        facts = collect_facts([{"mystery.read": "value"}])
        assert facts[0]["source"] == "Provider"
        assert facts[0]["value"] == "value"

    def test_ignores_non_dict_entries(self):
        assert collect_facts([None, "x", {"name.read": {"a": 1}}]) == [
            {"source": "National Identity Service", "label": "A", "value": "1"}
        ]
