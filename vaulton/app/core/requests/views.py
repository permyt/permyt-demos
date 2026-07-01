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
    """Manually (re)submit the KYC verification request for the signed-in
    trader. Onboarding normally auto-starts on connect; this stays as an
    explicit re-trigger. Delegates to ``PermytClient.start_onboarding``.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["post"]

    def post(self, request: Request) -> Response:
        request_id = PermytClient().start_onboarding(request.user, request.data.get("description"))
        return Response({"request_id": request_id})


class OnboardingStateView(APIView):
    """Return the current onboarding state for the signed-in trader.

    The dashboard polls this on load so a reload mid-flow (or after the
    answers arrived) reflects the real state — onboarding auto-starts on
    connect, so there's no button to re-fire it.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]

    def get(self, request: Request) -> Response:
        # Latest Log row for this user's onboarding request (data is merged/
        # accumulated by ``Log.upsert_request``, so it holds the full state).
        row = (
            Log.objects.get_queryset()
            .filter(user=request.user, permyt_request_id__isnull=False)
            .order_by("-updated_at")
            .first()
        )
        if not row:
            return Response({"request_id": None})
        return Response(
            {
                "request_id": row.permyt_request_id,
                "data": row.data or {},
                "success": row.success,
            }
        )
