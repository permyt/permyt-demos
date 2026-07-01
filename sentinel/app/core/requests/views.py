import logging

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from permyt.exceptions import PermytError

from app.core.requests.client import PermytClient
from app.core.users.serializers import ScreeningUpdateSerializer

logger = logging.getLogger(__name__)


SCREENING_FIELDS = (
    "sanctions_match",
    "pep",
    "adverse_media",
    "self_excluded",
)


def _serialize_screening(user) -> dict:
    """The subject's four screening outcomes as plain booleans."""
    return {field: bool(getattr(user, field, False)) for field in SCREENING_FIELDS}


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
    """Per-scope endpoint for service_call actions (e.g. /rest/sanctions/check/)."""

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
    """Read or update the authenticated subject's screening record.

    UI only — not part of the PERMYT protocol. The four booleans are editable
    from the dashboard so denials (a flagged subject) can be demonstrated.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "put"]

    def get(self, request: Request) -> Response:
        return Response(_serialize_screening(request.user))

    def put(self, request: Request) -> Response:
        user = request.user
        serializer = ScreeningUpdateSerializer(instance=user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(_serialize_screening(user))
