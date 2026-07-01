"""Static scope catalogue for the Bank PERMYT provider.

The Bank demo exposes three scopes — view balance, list movements, send
payment. Every input field is locked at the broker, so the user approves
exact beneficiaries and amounts on their mobile app and tampering between
approval and execution is rejected by ``BankScopes.validate_params``.

Adding a new scope = append one ``ScopeDescriptor`` to ``SCOPES``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .executors import (
    confirm_account_ownership,
    list_movements,
    read_affordability,
    read_balance,
    read_source_of_funds,
    send_payment,
)
from .serializers import PaymentSendSerializer, ScopeSerializer

VALID_ACTIONS = ("read", "list", "send", "check")


@dataclass(frozen=True)
class ScopeDescriptor:
    reference: str
    name: str
    description: str
    input_serializer: type[ScopeSerializer] | None
    executor: Callable[[Any, dict], dict]
    high_sensitivity: bool = False
    default_consent_mode: str = "prompt_once"


SCOPES: tuple[ScopeDescriptor, ...] = (
    ScopeDescriptor(
        reference="balance.read",
        name="Read account balance",
        description="Read the user's current account balance, currency, and IBAN.",
        input_serializer=None,
        executor=lambda user, _params: read_balance(user),
        high_sensitivity=True,
        default_consent_mode="prompt_once",
    ),
    ScopeDescriptor(
        reference="movements.list",
        name="List recent movements",
        description="List the user's 20 most recent account movements (transactions).",
        input_serializer=None,
        executor=lambda user, _params: list_movements(user),
        high_sensitivity=True,
        default_consent_mode="prompt_once",
    ),
    ScopeDescriptor(
        reference="payment.send",
        name="Send a payment",
        description=(
            "Send a payment to a fully-locked beneficiary, amount, currency, "
            "and reference. All inputs are approved by the user and locked "
            "by the broker — the connector enforces exact-match at execution."
        ),
        input_serializer=PaymentSendSerializer,
        executor=send_payment,
        high_sensitivity=True,
        default_consent_mode="prompt_always",
    ),
    ScopeDescriptor(
        reference="account_ownership.check",
        name="Confirm account ownership",
        description="Confirms the account holder owns a current account at the bank.",
        input_serializer=None,
        executor=lambda user, _params: confirm_account_ownership(user),
        default_consent_mode="prompt_once",
    ),
    ScopeDescriptor(
        reference="source_of_funds.read",
        name="Read source of funds",
        description=(
            "Reads the account holder's declared source of funds (e.g. salary "
            "accumulated over a period), as held by the bank."
        ),
        input_serializer=None,
        executor=lambda user, _params: read_source_of_funds(user),
        high_sensitivity=True,
        default_consent_mode="prompt_once",
    ),
    ScopeDescriptor(
        reference="affordability.read",
        name="Read affordability signal",
        description=(
            "Reads an affordability signal — the account holder's disposable-"
            "income band and whether any gambling-harm flag is set — without "
            "exposing individual transactions."
        ),
        input_serializer=None,
        executor=lambda user, _params: read_affordability(user),
        high_sensitivity=True,
        default_consent_mode="prompt_once",
    ),
)


SCOPES_BY_REFERENCE: dict[str, ScopeDescriptor] = {d.reference: d for d in SCOPES}
