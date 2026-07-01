import json
from decimal import Decimal

from django.conf import settings
from django.contrib.sessions.models import Session
from django.shortcuts import redirect, render
from django.views import View

from app.core.bookings.models import Booking, BookingStatus, LoginToken
from app.core.requests.client import PermytClient
from app.utils.qr import generate_qr_svg


class HotelView(View):
    """Hotel check-in landing page.

    Renders the split form/QR layout. Anonymous (session-only) — every
    visitor gets a fresh ``Booking`` keyed on their session, plus a fresh
    ``LoginToken`` carrying the QR connect-token payload.
    """

    def get(self, request):
        if not request.session.session_key:
            request.session.create()

        session_key = request.session.session_key
        session = Session.objects.get(session_key=session_key)

        booking, _ = Booking.objects.get_or_create(
            session_key=session_key,
            defaults={
                "currency": settings.HOTEL_CURRENCY,
                "total_amount": Decimal(settings.HOTEL_NIGHTLY_RATE).quantize(Decimal("0.01")),
            },
        )

        if booking.status == BookingStatus.PAID:
            return redirect("confirmation")

        client = PermytClient()
        connect = client.generate_connect_token(system_user_id=None)
        LoginToken.objects.create(
            token=connect["token"],
            session=session,
            booking=booking,
        )
        qr_svg = generate_qr_svg(json.dumps(connect["data"]))

        rate = Decimal(settings.HOTEL_NIGHTLY_RATE).quantize(Decimal("0.01"))

        return render(
            request,
            "pages/hotel/index.html",
            {
                "title": f"{settings.HOTEL_NAME} — Check-in",
                "hotel_name": settings.HOTEL_NAME,
                "qr_svg": qr_svg,
                "booking": booking,
                "form_data": booking.form_data or {},
                "nights": booking.nights,
                "rate": rate,
                "total": booking.total_amount or (rate * booking.nights),
                "currency": booking.currency or settings.HOTEL_CURRENCY,
                "session_key": session_key,
                "status": booking.status,
            },
        )


class NewBookingView(View):
    """Reset the current session's booking so the user can run the demo again."""

    def post(self, request):
        session_key = request.session.session_key
        if session_key:
            Booking.objects.filter(session_key=session_key).delete()
        return redirect("index")


class ConfirmationView(View):
    """Booking confirmation page (post-payment)."""

    def get(self, request):
        session_key = request.session.session_key
        booking = None
        if session_key:
            booking = Booking.objects.filter(session_key=session_key).first()

        if not booking or booking.status != BookingStatus.PAID:
            return render(
                request,
                "pages/confirmation/index.html",
                {
                    "title": f"{settings.HOTEL_NAME} — Confirmation",
                    "hotel_name": settings.HOTEL_NAME,
                    "booking": None,
                },
                status=404,
            )

        return render(
            request,
            "pages/confirmation/index.html",
            {
                "title": f"{settings.HOTEL_NAME} — Confirmation",
                "hotel_name": settings.HOTEL_NAME,
                "booking": booking,
                "form_data": booking.form_data or {},
            },
        )
