"""Tests for the provider-response → labelled-facts flattener."""

from app.core.requests import facts

PROVIDER_RESPONSES = [
    {
        "name.read": {"full_name": "Eleanor Pembroke"},
        "is_older.check": {"is_older": True},
        "address.read": {"address": "10 Clerkenwell Road, London EC1M 5QA"},
    },
    {
        "affordability.read": {"within_means": True, "monthly_disposable": "1200 GBP"},
    },
    {"self_exclusion.check": {"self_excluded": False}},
    {"sanctions.check": True},
    "garbage-not-a-dict",
]


class TestCollectFacts:
    """collect_facts flattens responses into {source, label, value} rows."""

    def test_groups_by_authoritative_source(self):
        rows = facts.collect_facts(PROVIDER_RESPONSES)
        sources = {r["source"] for r in rows}
        assert "National Identity Service" in sources
        assert "Meridian Bank" in sources
        assert "Sentinel Screening" in sources

    def test_booleans_humanized(self):
        rows = facts.collect_facts([{"is_older.check": {"is_older": True}}])
        assert rows == [
            {"source": "National Identity Service", "label": "Is older", "value": "Yes"}
        ]

    def test_scalar_payload_uses_reference_label(self):
        rows = facts.collect_facts([{"sanctions.check": True}])
        assert rows == [
            {"source": "Sentinel Screening", "label": "Sanctions.check", "value": "Yes"}
        ]

    def test_non_dict_responses_skipped(self):
        rows = facts.collect_facts(["nope", 42, None])
        assert rows == []

    def test_unknown_reference_falls_back_to_provider(self):
        rows = facts.collect_facts([{"mystery.read": {"value": 1}}])
        assert rows[0]["source"] == "Provider"
