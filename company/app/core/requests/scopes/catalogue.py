"""Static scope catalogue for the Company-Agent PERMYT provider.

A hybrid catalogue: three structured read scopes backed by ``CompanyKB`` fields,
plus one open-ended ``company.ask`` scope answered by an LLM grounded in the KB.

Adding a new scope = append one ``ScopeDescriptor`` to ``SCOPES``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .serializers import CompanyAskSerializer, ScopeSerializer

# ``ask`` joins read/check so a single company.ask question scope is valid.
VALID_ACTIONS = ("read", "check", "ask")


@dataclass(frozen=True)
class ScopeDescriptor:
    reference: str
    name: str
    description: str
    input_serializer: type[ScopeSerializer] | None
    executor: Callable[[Any, dict], dict]
    high_sensitivity: bool = False
    default_consent_mode: str = "prompt_once"


def _kb(user):
    """Return the user's ``CompanyKB`` or raise if missing."""
    from permyt.exceptions import InvalidUserError  # pylint: disable=import-outside-toplevel

    kb = getattr(user, "company_kb", None)
    if kb is None:
        raise InvalidUserError("This record has no company knowledge base.")
    return kb


def _business_plan(user, _params):
    return {"business_plan": _kb(user).business_plan}


def _financials(user, _params):
    return {"financials_summary": _kb(user).financials_summary}


def _products(user, _params):
    return {"products": _kb(user).products}


def _company_ask(user, params):
    from app.core.agent.llm import answer_question  # pylint: disable=import-outside-toplevel

    kb = _kb(user)
    question = (params or {}).get("question", "")
    return {"question": question, "answer": answer_question(kb.as_context(), question)}


SCOPES: tuple[ScopeDescriptor, ...] = (
    ScopeDescriptor(
        reference="business_plan.read",
        name="Read business plan",
        description="Read the company's business plan narrative.",
        input_serializer=None,
        executor=_business_plan,
    ),
    ScopeDescriptor(
        reference="financials.summary",
        name="Read financials summary",
        description="Read a high-level summary of the company's financials.",
        input_serializer=None,
        executor=_financials,
    ),
    ScopeDescriptor(
        reference="products.read",
        name="Read product catalogue",
        description="Read the company's list of products / services.",
        input_serializer=None,
        executor=_products,
    ),
    ScopeDescriptor(
        reference="company.ask",
        name="Ask the company agent",
        description=(
            "Ask an open-ended question about the company. The company's agent "
            "answers from its knowledge base. The exact ``question`` is locked "
            "into the grant at approval time."
        ),
        input_serializer=CompanyAskSerializer,
        executor=_company_ask,
        default_consent_mode="prompt_always",
    ),
)


SCOPES_BY_REFERENCE: dict[str, ScopeDescriptor] = {d.reference: d for d in SCOPES}
