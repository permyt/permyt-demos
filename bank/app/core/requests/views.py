import logging

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from permyt.exceptions import PermytError

from app.core.bank.models import Movement
from app.core.requests.client import PermytClient
from app.core.requests.scopes.executors import serialize_movement
from app.core.users.serializers import ProfileUpdateSerializer

logger = logging.getLogger(__name__)


def _serialize_profile(user) -> dict:
    """Serialize the user's bank account fields for the dashboard."""
    return {
        "full_name": user.full_name or "",
        "address": user.address or "",
        "birthdate": user.birthdate or "",
        "iban": user.iban or "",
        "balance": str(user.balance) if user.balance is not None else "0",
        "currency": user.currency or "EUR",
        "email": user.email or "",
        "onboarding_complete": bool(user.onboarding_complete),
    }


def _list_movements_for(user, limit: int = 20) -> list[dict]:
    qs = Movement.objects.get_queryset().filter(user=user).order_by("-created_at")[:limit]
    return [serialize_movement(m) for m in qs]


class PermytInboundView(APIView):
    """Single inbound endpoint for token_request, user_connect, request_status."""

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    def post(self, request: Request, *args, **kwargs) -> Response:
        """Delegate the signed inbound payload to ``PermytClient.handle_inbound``
        for signature verification and action routing."""
        client = PermytClient()
        try:
            result = client.handle_inbound(request.data)
            return Response(result)
        except PermytError as exc:
            return Response(client.handle_permyt_error(exc), status=400)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(f"Unexpected error in PERMYT inbound request: {exc}")
            return Response({"error": "Internal server error"}, status=500)


class ScopeCallView(APIView):
    """Per-scope endpoint for service_call actions (e.g. /rest/balance/read/, /rest/payment/send/)."""

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    def post(self, request: Request, field_name: str, action: str) -> Response:
        """Per-scope endpoint; delegates to ``handle_inbound`` identically
        to the main inbound view."""
        client = PermytClient()
        try:
            result = client.handle_inbound(request.data)
            return Response(result)
        except PermytError as exc:
            return Response(client.handle_permyt_error(exc), status=400)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(f"Unexpected error in scope call: {exc}")
            return Response({"error": "Internal server error"}, status=500)


class ProfileView(APIView):
    """Read or update the authenticated user's bank account header.

    Only ``full_name`` is editable from the dashboard. IBAN, balance, and
    currency are read-only — balance changes only via the ``payment.send``
    scope.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "put"]

    def get(self, request: Request) -> Response:
        return Response(_serialize_profile(request.user))

    def put(self, request: Request) -> Response:
        serializer = ProfileUpdateSerializer(instance=request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(_serialize_profile(request.user))


class OnboardingStatusView(APIView):
    """Poll endpoint for the onboarding screen — actively reconciles the
    identity request against the broker (``check_access``) and finalizes if
    complete, so a lost push callback can't leave the account hanging.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]

    def get(self, request: Request) -> Response:
        complete = PermytClient().sync_onboarding(request.user)
        return Response({"onboarding_complete": bool(complete)})


class OnboardingRetryView(APIView):
    """Re-fire the identity onboarding request for the signed-in account.

    Secure by construction: authenticated-only, and it acts solely on
    ``request.user`` — the access request is always for the caller's own
    ``permyt_user_id`` (never an id supplied by the client). Used by the
    onboarding screen's "Request again" button after a failure/timeout.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["post"]

    def post(self, request: Request) -> Response:
        user = request.user
        if user.onboarding_complete:
            return Response({"ok": True, "onboarding_complete": True})
        PermytClient()._fire_identity_request(user)  # noqa: SLF001 — own client
        return Response({"ok": True})


class MovementsView(APIView):
    """Return the authenticated user's most recent movements as JSON.

    UI-only endpoint — the dashboard's WebSocket-driven refresh fetches
    this after a ``balance_changed`` notification. Not part of the PERMYT
    protocol.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]

    def get(self, request: Request) -> Response:
        return Response({"movements": _list_movements_for(request.user)})
