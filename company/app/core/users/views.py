import json

from django.contrib.auth import login
from django.core.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from app.core.requests.client import PermytClient
from app.mixins.viewsets import AppModelViewSet
from app.utils.qr import generate_qr_svg

from .models import User, LoginToken

# Connect envelope (nonce + timestamp window) is valid for 5 minutes.
QR_TTL_SECONDS = 5 * 60


class UserViewSet(AppModelViewSet):
    """
    Users are created via QR-login, not REST.
    This ViewSet provides read-only access.
    """

    model = User
    CAN_CREATE = False
    CAN_DELETE = False


# ---------------------------------------------------------------------------
# QR Login — polling endpoint (AllowAny)
# ---------------------------------------------------------------------------


class LoginStatusView(APIView):
    """Poll endpoint — returns whether QR login has completed."""

    permission_classes = [AllowAny]

    def get(self, request):
        login_id = request.query_params.get("id")
        if not login_id:
            return Response({"error": "id is required."}, status=400)

        try:
            token_obj = LoginToken.objects.select_related("user").get(id=login_id)
        except LoginToken.DoesNotExist:
            return Response({"error": "Unknown login id."}, status=404)

        if token_obj.user:
            login(request, token_obj.user, backend="django.contrib.auth.backends.ModelBackend")
            token_obj.delete()
            return Response({"status": "authenticated"})

        return Response({"status": "pending"})


class RegistrationStatusView(APIView):
    """Poll endpoint — has a registered record been linked to a PERMYT profile?

    Unlike ``LoginStatusView`` this never logs a browser session in; it only
    reports whether the record now has a ``permyt_user_id`` (i.e. someone
    scanned its registration QR with their PERMYT app)."""

    permission_classes = [AllowAny]

    def get(self, request):
        record_id = request.query_params.get("id")
        if not record_id:
            return Response({"error": "id is required."}, status=400)

        try:
            record = User.objects.get_queryset().get(id=record_id)
        except (User.DoesNotExist, ValueError, ValidationError):
            return Response({"error": "Unknown record id."}, status=404)

        return Response({"status": "connected" if record.is_connected else "pending"})


# ---------------------------------------------------------------------------
# QR refresh — re-mint the connect token before the 5-min envelope expires
# ---------------------------------------------------------------------------


class RefreshLoginQrView(APIView):
    """Re-mint the connect token + QR SVG for a pending browser-login.

    The PERMYT connect envelope expires after 5 minutes. The login page
    calls this before that window closes so the displayed QR stays
    scannable. Updates the existing ``LoginToken`` in place so the page's
    poll id stays stable.
    """

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    def post(self, request):
        login_id = request.data.get("id")
        if not login_id:
            return Response({"error": "id is required."}, status=400)

        try:
            token_obj = LoginToken.objects.select_related("user").get(id=login_id)
        except (LoginToken.DoesNotExist, ValueError, ValidationError):
            return Response({"error": "Unknown login id."}, status=404)

        if token_obj.user:
            return Response({"error": "Already authenticated."}, status=409)

        connect = PermytClient().generate_connect_token(system_user_id=None)
        token_obj.token = connect["token"]
        token_obj.save()

        return Response(
            {
                "qr_svg": generate_qr_svg(json.dumps(connect["data"])),
                "ttl_seconds": QR_TTL_SECONDS,
            }
        )


class RefreshRegistrationQrView(APIView):
    """Re-mint the connect token + QR SVG for a pending record registration.

    Registration polling keys off the record id (not the token), so a fresh
    ``LoginToken`` is issued for the record on each refresh; stale ones expire
    on their own.
    """

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    def post(self, request):
        record_id = request.data.get("id")
        if not record_id:
            return Response({"error": "id is required."}, status=400)

        try:
            record = User.objects.get_queryset().get(id=record_id)
        except (User.DoesNotExist, ValueError, ValidationError):
            return Response({"error": "Unknown record id."}, status=404)

        if record.is_connected:
            return Response({"error": "Already connected."}, status=409)

        connect = PermytClient().generate_connect_token(system_user_id=str(record.id))
        LoginToken.objects.create(token=connect["token"], user=record)

        return Response(
            {
                "qr_svg": generate_qr_svg(json.dumps(connect["data"])),
                "ttl_seconds": QR_TTL_SECONDS,
            }
        )
