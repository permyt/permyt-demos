import json
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

from app.core.ai.services import HotelMappingService
from app.core.bookings.models import Booking, BookingStatus, LoginToken
from app.core.logs.models import Log
from app.utils.websocket import send_to_websocket

from .models import Nonce

logger = logging.getLogger(__name__)


IDENTITY_DESCRIPTION = (
    "Hotel check-in: read the guest's full legal name, postal address, "
    "country of residence, and VAT / tax identification number."
)


def _ws_send(booking: Booking, event: str, **payload) -> None:
    """Push a custom event to all sockets watching this booking's session."""
    if not booking or not booking.session_key:
        return
    send_to_websocket(
        f"session-{booking.session_key}",
        {"event": event, "booking_id": str(booking.id), **payload},
    )


class PermytClient(BasePermytClient):
    """Hotel-side PERMYT client.

    Subclasses the SDK's ``PermytClient`` to implement identity, replay
    protection, the QR connect flow (now session-bound, no user accounts),
    and request status callbacks for both the identity-fetch and payment
    legs of the hotel check-in flow.
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

        booking = Booking.objects.filter(payment_request_id=request_id).first()
        if not booking:
            return {}

        candidates = {
            "account": settings.HOTEL_IBAN,
            "value": str(booking.total_amount) if booking.total_amount is not None else None,
            "currency": booking.currency or settings.HOTEL_CURRENCY,
            "name": settings.HOTEL_NAME,
            "description": f"{booking.nights}-night stay — booking {booking.id}",
        }

        return {k: v for k, v in candidates.items() if k in input_fields and v is not None}

    # ------------------------------------------------------------------
    # User connect (QR scan binds the booking to a permyt_user_id)
    # ------------------------------------------------------------------

    def process_user_connect(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Handle the ``user_connect`` callback from the PERMYT broker.

        Looks up the ``LoginToken`` issued when the hotel page rendered,
        binds the resolved ``permyt_user_id`` to the Booking, then fires the
        identity ``request_access`` so the form starts auto-filling.
        """
        permyt_user_id = data.get("permyt_user_id")
        booking: Booking | None = None
        with Log.activity(
            "user_connect",
            data={"permyt_user_id": str(permyt_user_id) if permyt_user_id else None},
        ) as ctx:
            if not permyt_user_id:
                raise exceptions.InvalidInputError("permyt_user_id is required for user connect.")

            try:
                token = LoginToken.objects.select_related("booking").get(token=data.get("token"))
            except LoginToken.DoesNotExist as exc:
                raise exceptions.InvalidInputError("Invalid login token.") from exc

            booking = token.booking
            if not booking:
                raise exceptions.InvalidInputError("Login token is not bound to a booking.")

            booking.permyt_user_id = permyt_user_id
            token.scanned = True
            token.save()
            ctx.booking = booking

            _ws_send(booking, "scanned", permyt_user_id=str(permyt_user_id))

            self._fire_identity_request(booking)
            return {"logged": True}

    def _fire_identity_request(self, booking: Booking) -> None:
        """Submit the identity access request and persist the request_id."""
        try:
            response = self.request_access(
                {
                    "user_id": str(booking.permyt_user_id),
                    "description": IDENTITY_DESCRIPTION,
                }
            )
        except exceptions.PermytError as exc:
            booking.set_status(BookingStatus.FAILED, failure_reason=str(exc))
            Log.error(
                "identity_request",
                data={"description": IDENTITY_DESCRIPTION, "error": str(exc)},
                booking=booking,
            )
            _ws_send(booking, "identity_failed", reason=str(exc))
            return

        request_id = response.get("request_id") if isinstance(response, dict) else None
        status = response.get("status") if isinstance(response, dict) else None

        booking.identity_request_id = str(request_id) if request_id else None
        booking.set_status(BookingStatus.IDENTITY_REQUESTED)

        if request_id:
            Log.upsert_request(
                booking,
                str(request_id),
                action="identity_submitted",
                data={
                    "kind": "identity",
                    "description": IDENTITY_DESCRIPTION,
                    "status": status,
                },
            )

    # ------------------------------------------------------------------
    # User disconnect (broker tells the hotel the link was revoked)
    # ------------------------------------------------------------------

    def process_user_disconnect(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Handle the ``user_disconnect`` callback from the PERMYT broker.

        Undoes the connect-time link: clears ``permyt_user_id`` on every
        Booking bound to this profile and drops their LoginTokens, so the
        booking is no longer associated with the PERMYT user. Idempotent — a
        repeat call or an unknown ``permyt_user_id`` is a no-op.
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

            bookings = list(Booking.objects.filter(permyt_user_id=permyt_user_id))
            for booking in bookings:
                LoginToken.objects.filter(booking=booking).delete()
                booking.permyt_user_id = None
                booking.save()

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
    # Status callbacks (identity + payment share the same handler)
    # ------------------------------------------------------------------

    TERMINAL_FAILURES = {"rejected", "incomplete", "unavailable"}

    def process_request_status(self, data: dict[str, Any]) -> dict[str, Any] | None:
        data = data or {}
        request_id = data.get("request_id")
        if not request_id:
            return {"received": True}
        request_id = str(request_id)

        booking = Booking.objects.filter(identity_request_id=request_id).first()
        kind = "identity"
        if not booking:
            booking = Booking.objects.filter(payment_request_id=request_id).first()
            kind = "payment"
        if not booking:
            return {"received": True}

        status = data.get("status")
        Log.upsert_request(
            booking,
            request_id,
            action=status or "updated",
            data={"kind": kind, "status": status},
        )
        _ws_send(booking, "status", kind=kind, status=status)

        if status == "completed":
            services = data.get("services") or []
            if kind == "identity":
                self._handle_identity_completion(booking, request_id, services)
            else:
                self._handle_payment_completion(booking, request_id, services)
        elif status in self.TERMINAL_FAILURES:
            reason = data.get("reason") or status
            booking.set_status(BookingStatus.FAILED, failure_reason=str(reason))
            Log.upsert_request(
                booking,
                request_id,
                action="ended",
                data={"kind": kind, "status": status, "reason": reason},
                success=False,
            )
            _ws_send(booking, f"{kind}_failed", reason=str(reason))

        return {"received": True}

    # ------------------------------------------------------------------
    # Completion handlers
    # ------------------------------------------------------------------

    def _handle_identity_completion(
        self, booking: Booking, request_id: str, services: list[Any]
    ) -> None:
        if not services:
            booking.set_status(
                BookingStatus.FAILED, failure_reason="No identity provider responded."
            )
            Log.upsert_request(
                booking,
                request_id,
                action="identity_empty",
                data={"kind": "identity", "status": "completed", "note": "no services"},
                success=False,
            )
            _ws_send(booking, "identity_failed", reason="No identity provider responded.")
            return

        try:
            responses = self.call_services(services)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            booking.set_status(BookingStatus.FAILED, failure_reason=str(exc))
            Log.upsert_request(
                booking,
                request_id,
                action="identity_call_error",
                data={"kind": "identity", "error": str(exc)},
                success=False,
            )
            _ws_send(booking, "identity_failed", reason=str(exc))
            return

        clean_responses = [r if isinstance(r, dict) else {"raw": str(r)} for r in responses]
        mapped = self._map_with_ai(clean_responses)

        booking.form_data = mapped.get("mapped_fields") or {}
        booking.total_amount = booking.compute_total()
        booking.currency = settings.HOTEL_CURRENCY
        booking.set_status(BookingStatus.IDENTITY_FILLED)

        Log.upsert_request(
            booking,
            request_id,
            action="identity_filled",
            data={
                "kind": "identity",
                "status": "completed",
                "num_services": len(services),
                "missing_fields": mapped.get("missing_fields") or [],
                "ai_notes": mapped.get("notes") or "",
            },
        )
        _ws_send(
            booking,
            "form_filled",
            form_data=booking.form_data,
            missing_fields=mapped.get("missing_fields") or [],
            nights=booking.nights,
            total=str(booking.total_amount),
            currency=booking.currency,
        )

    def _handle_payment_completion(
        self, booking: Booking, request_id: str, services: list[Any]
    ) -> None:
        if not services:
            booking.set_status(BookingStatus.FAILED, failure_reason="Bank did not respond.")
            Log.upsert_request(
                booking,
                request_id,
                action="payment_empty",
                data={"kind": "payment", "status": "completed", "note": "no services"},
                success=False,
            )
            _ws_send(booking, "payment_failed", reason="Bank did not respond.")
            return

        # Real intermediate event: the broker has confirmed approval and we are
        # about to instruct the bank to move the money. The UI activates its
        # "charge" step on this so the visible state reflects an actual backend
        # action, not a timer.
        _ws_send(booking, "charging")

        try:
            responses = self.call_services(services)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            booking.set_status(BookingStatus.FAILED, failure_reason=str(exc))
            Log.upsert_request(
                booking,
                request_id,
                action="payment_call_error",
                data={"kind": "payment", "error": str(exc)},
                success=False,
            )
            _ws_send(booking, "payment_failed", reason=str(exc))
            return

        reference = self._extract_payment_reference(responses)
        booking.payment_reference = reference
        booking.set_status(BookingStatus.PAID)

        Log.upsert_request(
            booking,
            request_id,
            action="payment_completed",
            data={
                "kind": "payment",
                "status": "completed",
                "reference": reference,
            },
        )
        _ws_send(booking, "paid", reference=reference, total=str(booking.total_amount))

    @staticmethod
    def _extract_payment_reference(responses: list[Any]) -> str | None:
        """Best-effort dig through provider responses for a payment id/reference."""
        for resp in responses:
            if not isinstance(resp, dict):
                continue
            for key in ("payment_reference", "reference", "id"):
                if resp.get(key):
                    return str(resp[key])
            payment = resp.get("payment")
            if isinstance(payment, dict):
                for key in ("id", "reference", "transaction_id"):
                    if payment.get(key):
                        return str(payment[key])
        return None

    # ------------------------------------------------------------------
    # AI mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_with_ai(responses: list[dict[str, Any]]) -> dict[str, Any]:
        """Run the HotelMappingService and return a tolerant result dict."""
        try:
            service = HotelMappingService()
            result = service.run(json.dumps(responses, default=str))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(f"AI mapping failed, falling back to direct: {exc}")
            return {
                "mapped_fields": _direct_field_map(responses),
                "missing_fields": [],
                "notes": f"AI fallback: {exc}",
            }
        if not isinstance(result, dict) or "mapped_fields" not in result:
            return {
                "mapped_fields": _direct_field_map(responses),
                "missing_fields": [],
                "notes": "AI returned no mapped_fields; used direct map.",
            }
        return result

    # ------------------------------------------------------------------
    # Provider-only stubs (required by SDK abstract class)
    # ------------------------------------------------------------------

    def resolve_user(self, permyt_user_id: str | None = None) -> Any:
        raise NotImplementedError("Hotel does not resolve users for service calls")

    def store_token(
        self, token: str, user: Any, data: TokenRequestData, expires_at: datetime
    ) -> None:
        raise NotImplementedError("Hotel does not store tokens")

    def get_token_metadata(self, token: str) -> TokenMetadata:
        raise NotImplementedError("Hotel does not issue tokens")

    def get_endpoints_for_scope(self, scope: ScopeGrant) -> list[ServiceCallEndpoint]:
        return []

    def process_request(
        self, metadata: TokenMetadata, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        return {"error": "This is a requester, not a provider"}


def _direct_field_map(responses: list[dict[str, Any]]) -> dict[str, str]:
    """Naive merge of provider responses if the AI service is unavailable.

    Used only as a fallback so the demo stays functional offline. Picks the
    first non-empty value for each known hotel form field.
    """
    keys = {
        "full_name": ("full_name", "name", "display_name"),
        "address": ("address", "postal_address"),
        "country": ("country", "country_code"),
        "vat": ("vat", "vat_number", "tax_id"),
    }
    out: dict[str, str] = {}
    for field, candidates in keys.items():
        for resp in responses:
            if not isinstance(resp, dict):
                continue
            for key in candidates:
                value = resp.get(key)
                if value:
                    out[field] = str(value)
                    break
            if field in out:
                break
    return out
