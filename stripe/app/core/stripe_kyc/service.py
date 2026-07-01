"""Create + populate a Stripe Connect connected account from mapped facts.

Uses stripe-python in test mode. If no key is configured, returns a deterministic
stub so the demo runs offline (the dashboard still shows the assembled payload).
"""

from __future__ import annotations

import json
import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)


def create_connected_account(payload: dict) -> dict:
    """Create a connected account + its beneficial owners, return status.

    Args:
        payload: ``{account, persons, collected}`` from ``mapper.build_payload``.

    Returns:
        ``{stripe_account_id, requirements, persons, stub}`` — ``requirements``
        is ``Account.requirements.currently_due`` (empty/short = good), ``stub``
        is True when no Stripe key was configured.
    """
    account_params = dict(payload["account"])
    persons = payload.get("persons", [])

    # Custom accounts require the platform to record Terms-of-Service
    # acceptance on the account's behalf (clears the "Accept terms of service"
    # action). Stamp it here where we have a wall clock.
    account_params.setdefault(
        "tos_acceptance",
        {"date": int(time.time()), "ip": getattr(settings, "STRIPE_TOS_IP", "127.0.0.1")},
    )

    # Debug: log exactly what we're about to send to Stripe so a 400 can be
    # traced to the offending field. Logged regardless of stub/live mode.
    logger.info("Stripe Account.create payload: %s", json.dumps(account_params, default=str))
    logger.info(
        "Stripe Account.create_person payloads (%d): %s",
        len(persons),
        json.dumps(persons, default=str),
    )

    if not settings.STRIPE_SECRET_KEY:
        logger.warning("STRIPE_SECRET_KEY not set — returning stubbed Stripe account.")
        return {
            "stripe_account_id": "acct_stub_demo",
            "requirements": {"currently_due": [], "note": "stub — set STRIPE_SECRET_KEY"},
            "persons": [f"{p.get('first_name')} {p.get('last_name')}" for p in persons],
            "stub": True,
        }

    import stripe  # pylint: disable=import-outside-toplevel,import-error

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        # Pass the full assembled params (type, country, email, company,
        # business_profile, capabilities, external_account, tos_acceptance, …).
        account = stripe.Account.create(**account_params)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error(
            "Stripe Account.create FAILED: %s | account=%s",
            exc,
            json.dumps(account_params, default=str),
        )
        raise

    created_persons = []
    for person in persons:
        try:
            p = stripe.Account.create_person(account.id, **person)
            created_persons.append(f"{p.first_name} {p.last_name}")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(
                "create_person failed: %s | person=%s", exc, json.dumps(person, default=str)
            )

    # The account exists now — a failure reading requirements must NOT be
    # reported as an onboarding failure (stripe-python v15 ``StripeObject`` has
    # no ``.get``; attribute access, not ``dict.get``). Default to empty.
    requirements = {"currently_due": [], "eventually_due": [], "past_due": []}
    try:
        refreshed = stripe.Account.retrieve(account.id)
        raw = getattr(refreshed, "requirements", None)
        if raw is not None:
            requirements = {
                "currently_due": list(getattr(raw, "currently_due", None) or []),
                "eventually_due": list(getattr(raw, "eventually_due", None) or []),
                "past_due": list(getattr(raw, "past_due", None) or []),
            }
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Could not read requirements for %s: %s", account.id, exc)

    return {
        "stripe_account_id": account.id,
        "requirements": requirements,
        "persons": created_persons,
        "stub": False,
    }
