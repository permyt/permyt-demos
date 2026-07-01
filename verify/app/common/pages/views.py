import json

from django.conf import settings
from django.contrib.sessions.models import Session
from django.shortcuts import render
from django.views import View

from app.core.requests.client import PermytClient
from app.core.verifications.models import LoginToken, Verification, VerificationStatus
from app.utils.qr import generate_qr_svg


class VerifyView(View):
    """Age-verification landing page.

    Renders a single QR pane. Anonymous (session-only) — every visitor gets
    a fresh ``Verification`` keyed on their session, plus a fresh
    ``LoginToken`` carrying the QR connect-token payload.
    """

    def get(self, request):
        if not request.session.session_key:
            request.session.create()

        session_key = request.session.session_key
        session = Session.objects.get(session_key=session_key)

        verification, _ = Verification.objects.get_or_create(
            session_key=session_key,
            defaults={"min_age": settings.VERIFY_MIN_AGE},
        )

        client = PermytClient()
        connect = client.generate_connect_token(system_user_id=None)
        LoginToken.objects.create(
            token=connect["token"],
            session=session,
            verification=verification,
        )
        qr_svg = generate_qr_svg(json.dumps(connect["data"]))

        return render(
            request,
            "pages/verify/index.html",
            {
                "title": f"{settings.VERIFY_APP_NAME} — Age verification",
                "app_name": settings.VERIFY_APP_NAME,
                "min_age": verification.min_age,
                "qr_svg": qr_svg,
                "verification": verification,
                "session_key": session_key,
                "status": verification.status,
                "is_verified": verification.status == VerificationStatus.VERIFIED,
                "is_older": verification.is_older,
            },
        )
