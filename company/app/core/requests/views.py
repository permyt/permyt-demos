import logging

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from permyt.exceptions import PermytError

from app.core.requests.client import PermytClient
from app.core.users.models import CompanyKB
from app.core.users.serializers import CompanyKBUpdateSerializer

logger = logging.getLogger(__name__)


def _serialize_kb(user) -> dict:
    """Serialize the user's company knowledge base for the dashboard editor."""
    kb = getattr(user, "company_kb", None) or CompanyKB(user=user)
    return {
        # Gov.ID-sourced identity — non-editable.
        "name": kb.name or "",
        "registration_number": kb.registration_number or "",
        "registered_address": kb.registered_address or "",
        "country": kb.country or "",
        "onboarding_complete": bool(getattr(user, "onboarding_complete", False)),
        # Editable knowledge base.
        "business_plan": kb.business_plan or "",
        "financials_summary": kb.financials_summary or "",
        "products": "\n".join(kb.products or []),
        "narrative": kb.narrative or "",
    }


class CompanyProfileView(APIView):
    """Read or update the authenticated company's knowledge base."""

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "put"]

    def get(self, request: Request) -> Response:
        return Response(_serialize_kb(request.user))

    def put(self, request: Request) -> Response:
        kb, _ = CompanyKB.objects.get_or_create(user=request.user)
        serializer = CompanyKBUpdateSerializer(instance=kb, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(_serialize_kb(request.user))


class OnboardingStatusView(APIView):
    """Poll endpoint for the onboarding screen — actively reconciles the
    company-identity request against the broker (``check_access``) and
    finalizes if complete, so a lost push callback can't leave it hanging.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]

    def get(self, request: Request) -> Response:
        complete = PermytClient().sync_onboarding(request.user)
        return Response({"onboarding_complete": bool(complete)})


class OnboardingRetryView(APIView):
    """Re-fire the company-identity onboarding request for the signed-in user.

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


class PermytInboundView(APIView):
    """Single inbound endpoint for token_request, user_connect, request_status."""

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


class ScopeCallView(APIView):
    """Per-scope endpoint for service_call actions (e.g. /rest/business_plan/read/,
    /rest/company/ask/)."""

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    def post(self, request: Request, field_name: str, action: str) -> Response:
        client = PermytClient()
        try:
            result = client.handle_inbound(request.data)
            return Response(result)
        except PermytError as exc:
            return Response(client.handle_permyt_error(exc), status=400)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(f"Unexpected error in scope call: {exc}")
            return Response({"error": "Internal server error"}, status=500)
