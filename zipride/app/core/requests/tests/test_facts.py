"""Tests for the provider-response → labelled-facts flattener."""

from app.core.requests import facts

PROVIDER_RESPONSES = [
    {
        "name.read": {"first_name": "Eleanor", "last_name": "Pembroke"},
        "right_to_work.check": {"right_to_work": True, "eligibility_type": "settled status"},
    },
    {"driving_licence.read": {"valid": True, "categories": ["B", "C1"], "disqualified": False}},
]


class TestCollectFacts:
    """collect_facts flattens responses into {source, label, value} rows."""

    def test_maps_reference_to_source(self):
        rows = facts.collect_facts(PROVIDER_RESPONSES)
        sources = {r["source"] for r in rows}
        assert sources == {"National Identity Service"}

    def test_humanizes_labels(self):
        rows = facts.collect_facts(PROVIDER_RESPONSES)
        labels = {r["label"] for r in rows}
        assert "First name" in labels
        assert "Right to work" in labels
        assert "Eligibility type" in labels

    def test_formats_booleans_and_lists(self):
        rows = facts.collect_facts(PROVIDER_RESPONSES)
        by_label = {r["label"]: r["value"] for r in rows}
        assert by_label["Right to work"] == "Yes"
        assert by_label["Disqualified"] == "No"
        assert by_label["Categories"] == "B, C1"

    def test_unknown_reference_falls_back_to_provider(self):
        rows = facts.collect_facts([{"mystery.read": {"foo": "bar"}}])
        assert rows[0]["source"] == "Provider"

    def test_non_dict_payload_uses_reference_label(self):
        rows = facts.collect_facts([{"identity.check": "verified"}])
        assert rows[0] == {
            "source": "National Identity Service",
            "label": "Identity.check",
            "value": "verified",
        }

    def test_ignores_non_dict_responses(self):
        assert facts.collect_facts([None, "junk", 42]) == []
