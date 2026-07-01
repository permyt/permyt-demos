import json
import logging
from decimal import Decimal

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings
from django.contrib.sessions.models import Session

from permyt.exceptions import PermytError

from app.core.logs.models import Log
from app.core.requests.client import PermytClient
from app.utils.qr import generate_qr_svg

from .models import Booking, BookingStatus, LoginToken

logger = logging.getLogger(__name__)


def _get_booking(request: Request) -> Booking | None:
    if not request.session.session_key:
        return None
    return Booking.objects.filter(session_key=request.session.session_key).first()


class UpdateNightsView(APIView):
    """Recompute total when the guest changes the number of nights."""

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    def post(self, request: Request) -> Response:
        booking = _get_booking(request)
        if not booking:
            return Response({"error": "No active booking."}, status=404)

        try:
            nights = int(request.data.get("nights", 1))
        except (TypeError, ValueError):
            return Response({"error": "nights must be an integer."}, status=400)

        if nights < 1 or nights > 30:
            return Response({"error": "nights must be between 1 and 30."}, status=400)

        booking.nights = nights
        booking.total_amount = booking.compute_total()
        booking.currency = settings.HOTEL_CURRENCY
        booking.save()

        return Response(
            {
                "nights": booking.nights,
                "total": str(booking.total_amount),
                "currency": booking.currency,
            }
        )


class RefreshQrView(APIView):
    """Issue a fresh connect token + QR SVG for the current session.

    The PERMYT connect token's envelope expires after 5 minutes. The page
    polls this endpoint before that window closes so the displayed QR stays
    scannable indefinitely.
    """

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    def post(self, request: Request) -> Response:
        booking = _get_booking(request)
        if not booking:
            return Response({"error": "No active booking."}, status=404)

        if booking.permyt_user_id:
            return Response({"error": "Booking already connected."}, status=409)

        session = Session.objects.get(session_key=request.session.session_key)
        client = PermytClient()
        connect = client.generate_connect_token(system_user_id=None)
        LoginToken.objects.create(
            token=connect["token"],
            session=session,
            booking=booking,
        )
        return Response(
            {
                "qr_svg": generate_qr_svg(json.dumps(connect["data"])),
                "ttl_seconds": 5 * 60,
            }
        )


class PayView(APIView):
    """
    Trigger the payment access request via PERMYT.

    The hotel does NOT specify the bank or any account-side detail. It only
    describes its need ("pay €X to IBAN Y for an N-night stay"). The broker
    resolves this to the right scope (bank's `payment.send`) and locks the
    inputs there. We only learn `payment_request_id` here; the actual money
    moves once the user approves on mobile and the bank confirms via webhook.
    """

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    def post(self, request: Request) -> Response:
        booking = _get_booking(request)
        if not booking:
            return Response({"error": "No active booking."}, status=404)

        if booking.status != BookingStatus.IDENTITY_FILLED:
            return Response(
                {"error": f"Booking is not ready for payment (status: {booking.status})."},
                status=409,
            )

        if not booking.permyt_user_id:
            return Response({"error": "Booking has no PERMYT user."}, status=409)

        if booking.total_amount is None:
            booking.total_amount = booking.compute_total()
            booking.currency = settings.HOTEL_CURRENCY
            booking.save()

        amount = Decimal(booking.total_amount).quantize(Decimal("0.01"))
        currency = booking.currency or settings.HOTEL_CURRENCY
        description = (
            f"Pay {amount} {currency} to {settings.HOTEL_NAME} "
            f"(IBAN {settings.HOTEL_IBAN}) for a {booking.nights}-night stay. "
            f"Reference: hotel check-in."
        )

        client = PermytClient()
        try:
            response = client.request_access(
                {
                    "user_id": str(booking.permyt_user_id),
                    "description": description,
                }
            )
        except PermytError as exc:
            Log.error(
                "payment_request",
                data={"description": description, "error": str(exc)},
                booking=booking,
            )
            return Response(client.handle_permyt_error(exc), status=502)

        request_id = response.get("request_id") if isinstance(response, dict) else None
        status_value = response.get("status") if isinstance(response, dict) else None

        if request_id:
            booking.payment_request_id = str(request_id)
            booking.set_status(BookingStatus.PAYMENT_REQUESTED)
            Log.upsert_request(
                booking,
                str(request_id),
                action="payment_submitted",
                data={
                    "kind": "payment",
                    "amount": str(amount),
                    "currency": currency,
                    "nights": booking.nights,
                    "status": status_value,
                },
            )

        return Response({"request_id": request_id, "status": status_value})
