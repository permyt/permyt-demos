import logging

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from permyt.exceptions import PermytError

from app.core.logs.models import Log
from app.core.requests.client import PermytClient

logger = logging.getLogger(__name__)


class PermytInboundView(APIView):
    """Webhook endpoint for all inbound PERMYT callbacks.

    Receives signed payloads from the broker (``user_connect``, request
    status updates) and delegates to ``PermytClient.handle_inbound()``
    for verification and routing.
    """

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    def post(self, request: Request, *args, **kwargs) -> Response:
        client = PermytClient()
        try:
            result = client.handle_inbound(request.data)
            return Response(result)
        except PermytError as exc:
            return Response(client.handle_permyt_error(exc), status=400)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(f"Unexpected error in PERMYT inbound request: {exc}")
            return Response({"error": "Internal server error"}, status=500)


class SubmitRequestView(APIView):
    """Submit a natural-language access request to the PERMYT broker.

    Accepts a description from the authenticated user, calls
    ``PermytClient.request_access()``, and records the initial Log
    entry for dashboard tracking.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["post"]

    def post(self, request: Request) -> Response:
        description = (request.data.get("description") or "").strip()
        user = request.user

        if not description:
            return Response({"error": "description is required"}, status=400)

        client = PermytClient()

        try:
            response = client.request_access(
                {
                    "user_id": str(user.permyt_user_id),
                    "description": description,
                }
            )
        except PermytError as exc:
            Log.error(
                "request_access",
                data={"description": description[:200], "error": str(exc)},
                user=user,
            )
            return Response(client.handle_permyt_error(exc), status=502)

        permyt_request_id = response.get("request_id") if isinstance(response, dict) else None
        status = response.get("status") if isinstance(response, dict) else None

        if permyt_request_id:
            Log.upsert_request(
                user,
                str(permyt_request_id),
                action="submitted",
                data={"description": description[:200], "status": status},
            )

        return Response(
            {
                "request_id": permyt_request_id,
                "status": status,
                "description": description,
            }
        )
