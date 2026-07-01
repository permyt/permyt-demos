import json
import logging

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django.contrib.sessions.models import Session

from app.core.requests.client import PermytClient
from app.utils.qr import generate_qr_svg

from .models import LoginToken, Verification

logger = logging.getLogger(__name__)


def _get_verification(request: Request) -> Verification | None:
    if not request.session.session_key:
        return None
    return Verification.objects.filter(session_key=request.session.session_key).first()


class RefreshQrView(APIView):
    """Issue a fresh connect token + QR SVG for the current session.

    The PERMYT connect token's envelope expires after 5 minutes. The page
    polls this endpoint before that window closes so the displayed QR stays
    scannable indefinitely.
    """

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    def post(self, request: Request) -> Response:
        verification = _get_verification(request)
        if not verification:
            return Response({"error": "No active verification."}, status=404)

        if verification.permyt_user_id:
            return Response({"error": "Verification already connected."}, status=409)

        session = Session.objects.get(session_key=request.session.session_key)
        client = PermytClient()
        connect = client.generate_connect_token(system_user_id=None)
        LoginToken.objects.create(
            token=connect["token"],
            session=session,
            verification=verification,
        )
        return Response(
            {
                "qr_svg": generate_qr_svg(json.dumps(connect["data"])),
                "ttl_seconds": 5 * 60,
            }
        )


class ResetVerificationView(APIView):
    """Reset the session's verification so the user can re-run the demo.

    Clears the existing Verification + any LoginTokens, then returns a fresh
    Verification + QR SVG so the page can swap in the new code without a reload.
    """

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    def post(self, request: Request) -> Response:
        if not request.session.session_key:
            request.session.create()

        session_key = request.session.session_key
        Verification.objects.filter(session_key=session_key).delete()

        verification = Verification.objects.create(session_key=session_key)
        session = Session.objects.get(session_key=session_key)
        client = PermytClient()
        connect = client.generate_connect_token(system_user_id=None)
        LoginToken.objects.create(
            token=connect["token"],
            session=session,
            verification=verification,
        )
        return Response(
            {
                "qr_svg": generate_qr_svg(json.dumps(connect["data"])),
                "ttl_seconds": 5 * 60,
                "status": verification.status,
            }
        )
