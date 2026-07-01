from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from typing import Any

from permyt import PermytClient as BasePermytClient, exceptions
from permyt.typing import (
    ScopeGrant,
    ServiceCallEndpoint,
    TokenMetadata,
    TokenRequestData,
)

from django.conf import settings
from django.db import IntegrityError, transaction

from app.core.logs.models import Log
from app.core.users.models import User, LoginToken

from .models import Nonce

# Default onboarding ask — drives the broker's AI scope selection across the
# player's connected providers (national identity service, bank, screening).
# Phrased so the authoritative sources answer the safer-gambling checks
# directly (over-18, identity, affordability, self-exclusion) without ever
# handing Luckwing the underlying documents.
ONBOARDING_DESCRIPTION = (
    "Confirm the customer is over 18, verify their identity, confirm this "
    "deposit is within their means, and confirm they are not on the national "
    "self-exclusion register — to open their account."
)


class PermytClient(BasePermytClient):
    """Requester-side PERMYT client.

    Subclasses the SDK's ``PermytClient`` to implement identity, replay
    protection, user connect (QR login), and status-callback handling.
    Provider-only methods are stubbed with ``NotImplementedError``.

    See README — "Key integration points" for an overview of how this
    class maps to the SDK.
    """

    def __init__(self):
        super().__init__(host=settings.PERMYT_HOST)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def get_service_id(self) -> str:
        return settings.PERMYT_SERVICE_ID

    def get_private_key(self) -> str:
        return settings.PRIVATE_KEY_PATH

    def get_permyt_public_key(self) -> str:
        return Path(settings.PERMYT_PUBLIC_KEY_PATH).read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Replay protection
    # ------------------------------------------------------------------

    def _validate_nonce_and_timestamp(self, nonce: str, timestamp: str) -> None:
        """Reject replayed or expired inbound requests.

        Checks the timestamp is within ``NONCE_TTL_SECONDS`` of now and
        atomically stores the nonce to prevent reuse.
        """
        with Log.activity(
            "validate_nonce",
            data={"nonce_prefix": (nonce or "")[:8], "timestamp": timestamp},
        ):
            ts = datetime.fromisoformat(timestamp)
            now = datetime.now(timezone.utc)
            window = timedelta(seconds=settings.NONCE_TTL_SECONDS)

            if abs(now - ts) > window:
                raise exceptions.ExpiredRequestError(
                    "Request timestamp is outside the valid window."
                )

            try:
                with transaction.atomic():
                    Nonce.objects.create(value=nonce)
            except IntegrityError as exc:
                raise exceptions.ExpiredRequestError("Nonce has already been used.") from exc

    # ------------------------------------------------------------------
    # Requester: build per-endpoint payloads
    # ------------------------------------------------------------------

    def _prepare_data_for_endpoint(
        self, request_id: str, endpoint: ServiceCallEndpoint
    ) -> dict[str, Any]:
        """Build the payload for a single provider endpoint call.

        This demo sends no additional inputs. Production requesters would
        populate endpoint-specific query parameters here.
        """
        return {}

    # ------------------------------------------------------------------
    # User connect (QR-login)
    # ------------------------------------------------------------------

    def process_user_connect(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Handle the ``user_connect`` callback from the PERMYT broker.

        Called when a user scans the QR code on the login page. Validates
        the login token, creates or links the local User via
        ``permyt_user_id``, and marks the session as authenticated.
        """
        permyt_user_id = data.get("permyt_user_id")
        with Log.activity(
            "user_connect",
            data={"permyt_user_id": str(permyt_user_id) if permyt_user_id else None},
        ) as ctx:
            if not permyt_user_id:
                raise exceptions.InvalidInputError("permyt_user_id is required for user connect.")

            try:
                token = LoginToken.objects.get(token=data.get("token"))
            except LoginToken.DoesNotExist as exc:
                raise exceptions.InvalidInputError("Invalid login token.") from exc

            if token.user:
                if token.user.permyt_user_id != permyt_user_id:
                    raise exceptions.InvalidUserError(
                        "User already linked to a different permyt profile."
                    )
                ctx.user = token.user
            else:
                ctx.user = User.objects.get_or_create(
                    permyt_user_id=permyt_user_id,
                    defaults={"username": permyt_user_id},
                )[0]

            token.login(ctx.user)

            # Kick off the account-opening request immediately on connect, so the
            # player doesn't have to click anything — by the time the dashboard
            # loads, the request is already in flight and the stage track is live.
            self.start_onboarding(ctx.user)
            return {"logged": True}

    def start_onboarding(self, user, description: str | None = None) -> str | None:
        """Submit the KYC access request for ``user`` and log it for the
        dashboard. Returns the broker request id (or ``None`` on failure).

        Shared by the connect handler (auto-start) and ``SubmitRequestView``.
        """
        description = (description or "").strip() or ONBOARDING_DESCRIPTION
        try:
            response = self.request_access(
                {"user_id": str(user.permyt_user_id), "description": description}
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            Log.error(
                "request_access",
                data={"description": description[:200], "error": str(exc)},
                user=user,
            )
            return None

        request_id = response.get("request_id") if isinstance(response, dict) else None
        status = response.get("status") if isinstance(response, dict) else None
        if request_id:
            Log.upsert_request(
                user,
                str(request_id),
                action="submitted",
                data={"description": description[:200], "status": status, "stage": "sent"},
            )
        return request_id

    # ------------------------------------------------------------------
    # User disconnect
    # ------------------------------------------------------------------

    def process_user_disconnect(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Handle the ``user_disconnect`` callback from the PERMYT broker.

        Idempotent — a repeat call for an already-disconnected user is a
        no-op. Regular users have no non-PERMYT login path, so the row is
        deleted outright (cascade clears LoginTokens). Privileged users
        (staff, superuser, account manager) keep their account: only
        ``permyt_user_id`` is nulled and login tokens are dropped so they
        can still sign in via the admin paths.
        """
        permyt_user_id = data.get("permyt_user_id")
        with Log.activity(
            "user_disconnect",
            data={"permyt_user_id": str(permyt_user_id) if permyt_user_id else None},
        ):
            if not permyt_user_id:
                raise exceptions.InvalidInputError(
                    "permyt_user_id is required for user disconnect."
                )

            try:
                user = User.objects.get(permyt_user_id=permyt_user_id)
            except User.DoesNotExist:
                return {"disconnected": True}

            if user.is_staff or user.is_superuser or user.is_account_manager:
                LoginToken.objects.filter(user=user).delete()
                user.permyt_user_id = None
                user.save()
            else:
                user.delete()
            return {"disconnected": True}

    # ------------------------------------------------------------------
    # Token revoke (sibling fan-out)
    # ------------------------------------------------------------------

    def process_token_revoke(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Handle the ``token_revoke`` callback from the PERMYT broker.

        Fired when the user disconnects or blacklists a peer service in the
        same profile. As a requester this app consumes single-use tokens
        immediately and persists none, so there is nothing to invalidate —
        this is an explicit no-op for parity with the provider demos.
        """
        return {"revoked": 0}

    # ------------------------------------------------------------------
    # Status callbacks
    # ------------------------------------------------------------------

    TERMINAL_FAILURES = {"rejected", "incomplete", "unavailable"}

    def process_request_status(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Handle status callbacks pushed by the broker.

        The dashboard Log row is keyed on ``permyt_request_id`` and upserted
        here as the broker advances the request through its lifecycle
        (queued → awaiting → processing → completed / rejected / …). On
        ``completed`` we also call the provider endpoints and record the
        final response on the same row.
        """
        data = data or {}
        request_id = data.get("request_id")
        if not request_id:
            return {"received": True}
        request_id = str(request_id)

        # Resolve the user who originally submitted this request via the Log
        # row created by SubmitRequestView (the callback itself carries no user).
        existing = Log.objects.filter(permyt_request_id=request_id).first()
        if not existing:
            return {"received": True}

        record = partial(Log.upsert_request, existing.user, request_id)
        status = data.get("status")

        if status == "completed":
            # Idempotent + race-safe: a redelivered/duplicate ``completed``
            # callback must not re-run the flow — the single-use provider token
            # is spent on the first call, so a second run fails and clobbers the
            # finished result with a spurious error. Two callbacks can overlap,
            # so a plain ``collected`` check isn't enough: claim the request
            # atomically under a row lock.
            with transaction.atomic():
                locked = Log.objects.select_for_update().filter(pk=existing.pk).first()
                locked_data = (locked.data if locked else None) or {}
                already = bool(locked_data.get("collected") or locked_data.get("creating"))
                if not already:
                    record(action="creating", data={"creating": True})
            if already:
                return {"received": True}
            self._handle_completion(record, data.get("services") or [])
        elif status in self.TERMINAL_FAILURES:
            record(
                action="ended",
                data={"status": status, "reason": data.get("reason")},
                success=False,
            )
        else:
            record(action=status or "updated", data={"status": status})

        return {"received": True}

    def _handle_completion(self, record, services: list[Any]) -> None:
        """Approved → pull the scoped answers from the providers and surface them
        as labelled facts (grouped by authoritative source) for the dashboard.
        Each step is recorded on the same Log row so the stage track advances
        live."""
        if not services:
            record(
                action="ended",
                data={"status": "no_data", "stage": "failed", "note": "no providers returned data"},
                success=False,
            )
            return

        # Stage: fetching answers from the authoritative sources.
        record(
            action="fetching",
            data={"status": "fetching", "stage": "fetching", "num_services": len(services)},
        )
        try:
            responses = self.call_services(services)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            record(
                action="ended",
                data={"status": "error", "stage": "failed", "error": str(exc)},
                success=False,
            )
            return

        from app.core.requests.facts import collect_facts  # pylint: disable=import-outside-toplevel

        facts = collect_facts(responses)

        # Stage: answers received — surface them (with provenance) for the UI reveal.
        record(
            action="answers",
            data={"status": "answers", "stage": "done", "collected": facts},
        )

    # ------------------------------------------------------------------
    # Provider-only stubs (required by SDK abstract class)
    # ------------------------------------------------------------------

    def resolve_user(self, permyt_user_id: str | None = None) -> Any:
        raise NotImplementedError("Requester does not resolve users for service calls")

    def store_token(
        self, token: str, user: Any, data: TokenRequestData, expires_at: datetime
    ) -> None:
        raise NotImplementedError("Requester does not store tokens")

    def get_token_metadata(self, token: str) -> TokenMetadata:
        raise NotImplementedError("Requester does not issue tokens")

    def get_endpoints_for_scope(self, scope: ScopeGrant) -> list[ServiceCallEndpoint]:
        return []

    def process_request(
        self, metadata: TokenMetadata, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        return {"error": "This is a requester, not a provider"}
