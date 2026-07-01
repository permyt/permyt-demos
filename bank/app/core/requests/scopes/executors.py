"""Scope executors for the Bank PERMYT provider.

Each executor is invoked from ``BankScopes.execute`` after the input has
been validated and locked-field tampering rejected. They read or mutate
the user's bank state and return a JSON-serializable dict.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from django.db import transaction

from app.core.bank.models import Movement
from app.utils.websocket import send_to_websocket


def serialize_movement(m: Movement) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "amount": str(m.amount),
        "currency": m.currency,
        "counterparty_name": m.counterparty_name,
        "counterparty_iban": m.counterparty_iban,
        "reference": m.reference,
        "type": m.type,
        "date": m.created_at.date().isoformat() if m.created_at else None,
        "timestamp": m.created_at.isoformat() if m.created_at else None,
    }


def read_balance(user) -> dict[str, Any]:
    """Return the user's current balance, currency, and IBAN."""
    return {
        "amount": str(user.balance),
        "currency": user.currency,
        "iban": user.iban,
    }


def list_movements(user) -> dict[str, Any]:
    """Return the user's last 20 movements, newest first."""
    qs = Movement.objects.get_queryset().filter(user=user).order_by("-created_at")[:20]
    return {"movements": [serialize_movement(m) for m in qs]}


def confirm_account_ownership(user) -> dict[str, Any]:
    """Confirm the account is owned by the connected user (source-direct)."""
    return {"confirmed": user.iban != ""}


def read_source_of_funds(user) -> dict[str, Any]:
    """Return the account holder's declared source of funds."""
    return {"source": user.source_of_funds}


def read_affordability(user) -> dict[str, Any]:
    """Return the affordability band and whether any gambling-harm flag is set."""
    return {
        "disposable_income_band": user.disposable_income_band,
        "gambling_harm": bool(user.gambling_harm),
    }


def send_payment(user, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a payment: append a debit movement and decrement the balance.

    Locked inputs (``account``, ``value``, ``currency``) are broker-enforced
    and have already matched what the user approved on their mobile app by
    the time this runs. ``name`` and ``description`` are free-form, set by
    the requester at call time. Wrapped in an atomic transaction with
    row-level locking to keep concurrent payments consistent. On commit,
    fires a websocket notification so the user's open dashboard refreshes
    its balance and movements list without polling.
    """
    UserModel = type(user)  # avoids a top-level import cycle with users.models
    value: Decimal = params["value"]
    currency: str = params["currency"]
    account: str = params["account"]
    name: str = params.get("name") or ""
    description: str = params.get("description") or ""

    with transaction.atomic():
        # Re-fetch user with row-level lock so concurrent payments serialise.
        locked_user = UserModel.objects.select_for_update().get(pk=user.pk)

        movement = Movement.objects.create(
            user=locked_user,
            amount=-value,
            currency=currency,
            counterparty_name=name,
            counterparty_iban=account,
            reference=description,
            type=Movement.TYPE_TRANSFER,
        )
        locked_user.balance = (locked_user.balance or Decimal("0")) - value
        locked_user.save(update_fields=["balance", "updated_at"])

        new_balance = locked_user.balance
        user_id = locked_user.id

        def _notify() -> None:
            send_to_websocket(
                f"user-{user_id}",
                {
                    "type": "balance_changed",
                    "balance": str(new_balance),
                    "currency": currency,
                },
            )

        transaction.on_commit(_notify)

    return {
        "payment": {
            "id": str(movement.id),
            "status": "COMPLETED",
            "account": account,
            "value": str(value),
            "currency": currency,
            "name": name,
            "description": description,
            "timestamp": (movement.created_at or datetime.now(timezone.utc)).isoformat(),
        }
    }


__all__ = (
    "read_balance",
    "list_movements",
    "send_payment",
    "serialize_movement",
    "confirm_account_ownership",
    "read_source_of_funds",
    "read_affordability",
)
