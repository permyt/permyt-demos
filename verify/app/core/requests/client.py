import logging

from datetime import datetime, timedelta, timezone
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
from app.core.verifications.models import LoginToken, Verification, VerificationStatus
from app.utils.websocket import send_to_websocket

from .models import Nonce

logger = logging.getLogger(__name__)


AGE_CHECK_DESCRIPTION = (
    "Age verification: confirm the user is at least {min_age} years old using a "
    "privacy-preserving check that returns only true or false, without revealing "
    "the birthdate."
)


def _ws_send(verification: Verification, event: str, **payload) -> None:
    """Push a custom event to all sockets watching this verification's session."""
    if not verification or not verification.session_key:
        return
    send_to_websocket(
        f"session-{verification.session_key}",
        {"event": event, "verification_id": str(verification.id), **payload},
    )


class PermytClient(BasePermytClient):
    """Verify-side PERMYT client.

    Subclasses the SDK's ``PermytClient`` to implement identity, replay
    protection, the QR connect flow (session-bound, no user accounts), and
    the age-verification request lifecycle.
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
        input_fields = endpoint.get("input_fields") or {}
        if not input_fields:
            return {}

        verification = Verification.objects.filter(request_id=request_id).first()
        if not verification:
            return {}

        candidates = {"min_age": verification.min_age}
        return {k: v for k, v in candidates.items() if k in input_fields and v is not None}

    # ------------------------------------------------------------------
    # User connect (QR scan binds the verification to a permyt_user_id)
    # ------------------------------------------------------------------

    def process_user_connect(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Handle the ``user_connect`` callback from the PERMYT broker.

        Looks up the ``LoginToken`` issued when the verify page rendered,
        binds the resolved ``permyt_user_id`` to the Verification, then
        immediately fires the age-check ``request_access``.
        """
        permyt_user_id = data.get("permyt_user_id")
        verification: Verification | None = None
        with Log.activity(
            "user_connect",
            data={"permyt_user_id": str(permyt_user_id) if permyt_user_id else None},
        ) as ctx:
            if not permyt_user_id:
                raise exceptions.InvalidInputError("permyt_user_id is required for user connect.")

            try:
                token = LoginToken.objects.select_related("verification").get(
                    token=data.get("token")
                )
            except LoginToken.DoesNotExist as exc:
                raise exceptions.InvalidInputError("Invalid login token.") from exc

            verification = token.verification
            if not verification:
                raise exceptions.InvalidInputError("Login token is not bound to a verification.")

            verification.set_status(VerificationStatus.SCANNED, permyt_user_id=permyt_user_id)
            token.scanned = True
            token.save()
            ctx.verification = verification

            _ws_send(verification, "scanned", permyt_user_id=str(permyt_user_id))

            self._fire_age_check(verification)
            return {"logged": True}

    def _fire_age_check(self, verification: Verification) -> None:
        """Submit the age-verification access request and persist the request_id."""
        description = AGE_CHECK_DESCRIPTION.format(min_age=verification.min_age)
        try:
            response = self.request_access(
                {
                    "user_id": str(verification.permyt_user_id),
                    "description": description,
                }
            )
        except exceptions.PermytError as exc:
            verification.set_status(VerificationStatus.FAILED, failure_reason=str(exc))
            Log.error(
                "age_check_request",
                data={"description": description, "error": str(exc)},
                verification=verification,
            )
            _ws_send(verification, "verification_failed", reason=str(exc))
            return

        request_id = response.get("request_id") if isinstance(response, dict) else None
        status = response.get("status") if isinstance(response, dict) else None

        if not request_id:
            reason = "Broker did not return a request id."
            verification.set_status(VerificationStatus.FAILED, failure_reason=reason)
            Log.error(
                "age_check_request",
                data={"description": description, "response": response},
                verification=verification,
            )
            _ws_send(verification, "verification_failed", reason=reason)
            return

        verification.set_status(VerificationStatus.AWAITING, request_id=str(request_id))
        _ws_send(verification, "awaiting_approval")

        Log.upsert_request(
            verification,
            str(request_id),
            action="age_check_submitted",
            data={
                "kind": "age_check",
                "description": description,
                "min_age": verification.min_age,
                "status": status,
            },
        )

    # ------------------------------------------------------------------
    # User disconnect
    # ------------------------------------------------------------------

    def process_user_disconnect(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Handle the ``user_disconnect`` callback from the PERMYT broker.

        Undoes the connect-time link by ``permyt_user_id``: clears the PERMYT
        association from any Verification(s) bound to it and drops their login
        tokens. Idempotent — a repeat call or an unknown ``permyt_user_id`` is a
        no-op and still returns ``{"disconnected": True}``.
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

            verifications = list(Verification.objects.filter(permyt_user_id=permyt_user_id))
            for verification in verifications:
                LoginToken.objects.filter(verification=verification).delete()
                verification.permyt_user_id = None
                verification.save()

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
        data = data or {}
        request_id = data.get("request_id")
        if not request_id:
            return {"received": True}
        request_id = str(request_id)

        verification = Verification.objects.filter(request_id=request_id).first()
        if not verification:
            return {"received": True}

        status = data.get("status")
        Log.upsert_request(
            verification,
            request_id,
            action=status or "updated",
            data={"kind": "age_check", "status": status},
        )
        _ws_send(verification, "status", status=status)

        if status == "completed":
            services = data.get("services") or []
            self._handle_age_check_completion(verification, request_id, services)
        elif status in self.TERMINAL_FAILURES:
            reason = data.get("reason") or status
            verification.set_status(VerificationStatus.FAILED, failure_reason=str(reason))
            Log.upsert_request(
                verification,
                request_id,
                action="ended",
                data={"kind": "age_check", "status": status, "reason": reason},
                success=False,
            )
            _ws_send(verification, "verification_failed", reason=str(reason))

        return {"received": True}

    # ------------------------------------------------------------------
    # Completion handler
    # ------------------------------------------------------------------

    def _handle_age_check_completion(
        self, verification: Verification, request_id: str, services: list[Any]
    ) -> None:
        if not services:
            verification.set_status(
                VerificationStatus.FAILED, failure_reason="No provider responded."
            )
            Log.upsert_request(
                verification,
                request_id,
                action="age_check_empty",
                data={"kind": "age_check", "status": "completed", "note": "no services"},
                success=False,
            )
            _ws_send(verification, "verification_failed", reason="No provider responded.")
            return

        verification.set_status(VerificationStatus.VERIFYING)
        _ws_send(verification, "verifying")

        try:
            responses = self.call_services(services)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            verification.set_status(VerificationStatus.FAILED, failure_reason=str(exc))
            Log.upsert_request(
                verification,
                request_id,
                action="age_check_call_error",
                data={"kind": "age_check", "error": str(exc)},
                success=False,
            )
            _ws_send(verification, "verification_failed", reason=str(exc))
            return

        is_older = self._extract_is_older(responses)
        if is_older is None:
            verification.set_status(
                VerificationStatus.FAILED,
                failure_reason="Provider did not return an age decision.",
            )
            Log.upsert_request(
                verification,
                request_id,
                action="age_check_unparseable",
                data={"kind": "age_check", "responses": responses},
                success=False,
            )
            _ws_send(
                verification,
                "verification_failed",
                reason="Provider did not return an age decision.",
            )
            return

        verification.is_older = is_older
        verification.set_status(
            VerificationStatus.VERIFIED if is_older else VerificationStatus.FAILED,
            failure_reason=None if is_older else f"User is not at least {verification.min_age}.",
        )

        Log.upsert_request(
            verification,
            request_id,
            action="age_check_completed",
            data={
                "kind": "age_check",
                "status": "completed",
                "is_older": is_older,
                "min_age": verification.min_age,
            },
            success=is_older,
        )

        if is_older:
            _ws_send(verification, "verified", min_age=verification.min_age)
        else:
            _ws_send(
                verification,
                "verification_failed",
                reason=f"User is not at least {verification.min_age}.",
            )

    @staticmethod
    def _extract_is_older(responses: list[Any]) -> bool | None:
        """Find the boolean ``is_older`` in any provider response."""
        for resp in responses:
            if isinstance(resp, dict) and "is_older" in resp:
                return bool(resp["is_older"])
        return None

    # ------------------------------------------------------------------
    # Provider-only stubs (required by SDK abstract class)
    # ------------------------------------------------------------------

    def resolve_user(self, permyt_user_id: str | None = None) -> Any:
        raise NotImplementedError("Verify does not resolve users for service calls")

    def store_token(
        self, token: str, user: Any, data: TokenRequestData, expires_at: datetime
    ) -> None:
        raise NotImplementedError("Verify does not store tokens")

    def get_token_metadata(self, token: str) -> TokenMetadata:
        raise NotImplementedError("Verify does not issue tokens")

    def get_endpoints_for_scope(self, scope: ScopeGrant) -> list[ServiceCallEndpoint]:
        return []

    def process_request(
        self, metadata: TokenMetadata, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        return {"error": "This is a requester, not a provider"}
