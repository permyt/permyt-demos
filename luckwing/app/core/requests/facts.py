"""Flatten provider responses into labelled facts grouped by source.

A KYC requester just displays the scoped answers the authoritative sources
returned directly (source-direct provenance — not cryptographic verification).
"""

from __future__ import annotations

from typing import Any

SOURCE_BY_REFERENCE = {
    "name.read": "National Identity Service",
    "country.read": "National Identity Service",
    "address.read": "National Identity Service",
    "is_older.check": "National Identity Service",
    "identity.check": "National Identity Service",
    "right_to_work.check": "National Identity Service",
    "driving_licence.read": "National Identity Service",
    "balance.read": "Meridian Bank",
    "movements.list": "Meridian Bank",
    "account_ownership.check": "Meridian Bank",
    "source_of_funds.read": "Meridian Bank",
    "affordability.read": "Meridian Bank",
    "sanctions.check": "Sentinel Screening",
    "pep.check": "Sentinel Screening",
    "adverse_media.check": "Sentinel Screening",
    "self_exclusion.check": "Sentinel Screening",
}


def _humanize(key: str) -> str:
    return (key or "").replace("_", " ").strip().capitalize()


def _format(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value) or "—"
    return "" if value is None else str(value)


def collect_facts(responses: list[Any]) -> list[dict]:
    facts: list[dict] = []
    for resp in responses or []:
        if not isinstance(resp, dict):
            continue
        for ref, payload in resp.items():
            source = SOURCE_BY_REFERENCE.get(ref, "Provider")
            if isinstance(payload, dict):
                for key, value in payload.items():
                    facts.append(
                        {"source": source, "label": _humanize(key), "value": _format(value)}
                    )
            else:
                facts.append({"source": source, "label": _humanize(ref), "value": _format(payload)})
    return facts
