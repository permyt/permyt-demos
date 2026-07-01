"""Static scope catalogue for the Sentinel Screening PERMYT provider.

Sentinel is a compliance-grade watchlist authority. It answers four boolean
screening checks about a connected subject, sourced directly from the
authority's own register. Each scope is a ``.check`` that leaks a single bit —
the authoritative source answered directly, with no underlying records exposed.

Adding a new scope = append one ``ScopeDescriptor`` to ``SCOPES``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .serializers import ScopeSerializer

VALID_ACTIONS = ("read", "check")


@dataclass(frozen=True)
class ScopeDescriptor:
    reference: str
    name: str
    description: str
    input_serializer: type[ScopeSerializer] | None
    executor: Callable[[Any, dict], dict]
    high_sensitivity: bool = False
    default_consent_mode: str = "prompt_once"


def _sanctions(user, _params):
    """Sanctions / watchlist screening — answered directly by the authority."""
    return {"sanctions_match": bool(user.sanctions_match)}


def _pep(user, _params):
    """Politically-exposed-person screening — answered directly."""
    return {"pep": bool(user.pep)}


def _adverse_media(user, _params):
    """Adverse-media screening — answered directly."""
    return {"adverse_media": bool(user.adverse_media)}


def _self_exclusion(user, _params):
    """Gambling self-exclusion register check — answered directly."""
    return {"self_excluded": bool(user.self_excluded)}


SCOPES: tuple[ScopeDescriptor, ...] = (
    ScopeDescriptor(
        reference="sanctions.check",
        name="Sanctions / watchlist check",
        description=(
            "Returns true if the subject appears on a sanctions or watchlist "
            "screening. The authoritative source answers directly — no "
            "underlying list entries are exposed."
        ),
        input_serializer=None,
        executor=_sanctions,
        high_sensitivity=True,
    ),
    ScopeDescriptor(
        reference="pep.check",
        name="Politically exposed person check",
        description=(
            "Returns true if the subject is flagged as a politically exposed "
            "person (PEP). The authoritative source answers directly."
        ),
        input_serializer=None,
        executor=_pep,
        high_sensitivity=True,
    ),
    ScopeDescriptor(
        reference="adverse_media.check",
        name="Adverse media check",
        description=(
            "Returns true if the subject is associated with adverse media. "
            "The authoritative source answers directly."
        ),
        input_serializer=None,
        executor=_adverse_media,
        high_sensitivity=True,
    ),
    ScopeDescriptor(
        reference="self_exclusion.check",
        name="Gambling self-exclusion check",
        description=(
            "Returns true if the subject is listed on the gambling "
            "self-exclusion register. The authoritative source answers directly."
        ),
        input_serializer=None,
        executor=_self_exclusion,
        high_sensitivity=True,
    ),
)


SCOPES_BY_REFERENCE: dict[str, ScopeDescriptor] = {d.reference: d for d in SCOPES}
