import logging

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from permyt.exceptions import PermytError

from app.core.requests.client import PermytClient
from app.core.users.models import BusinessProfile, Shareholder
from app.core.users.serializers import (
    BusinessProfileUpdateSerializer,
    ProfileUpdateSerializer,
    ShareholderSerializer,
)

logger = logging.getLogger(__name__)


PROFILE_FIELDS = (
    "full_name",
    "birthdate",
    "address",
    "country",
    "vat",
    "phone",
    "email",
    "tax_id",
    "passport_number",
    "social_security_number",
    "citizen_card_number",
)

BUSINESS_FIELDS = (
    "legal_name",
    "registration_number",
    "tax_id",
    "incorporation_date",
    "registered_address",
    "country",
    "structure",
    "mcc",
    "website",
)


def _serialize_fields(obj, fields) -> dict:
    out = {}
    for f in fields:
        value = getattr(obj, f, None)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        out[f] = value or ""
    return out


def _serialize_profile(user) -> dict:
    return _serialize_fields(user, PROFILE_FIELDS)


def _serialize_business(user) -> dict:
    business = getattr(user, "business_profile", None) or BusinessProfile(user=user)
    return _serialize_fields(business, BUSINESS_FIELDS)


def _serialize_shareholders(user) -> list:
    """Beneficial owners as plain dicts for the dashboard stakeholders editor."""
    business = getattr(user, "business_profile", None)
    if not business:
        return []
    return [
        {
            "first_name": s.first_name,
            "last_name": s.last_name,
            "birthdate": s.birthdate.isoformat() if s.birthdate else "",
            "address": s.address,
            "country": s.country,
            "id_number": s.id_number,
            "ownership_percent": str(s.ownership_percent),
            "title": s.title,
            "is_representative": s.is_representative,
        }
        for s in business.shareholders.all()
    ]


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
    """Per-scope endpoint for service_call actions (e.g. /rest/name/read/, /rest/is_older/check/)."""

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
    """Read or update the authenticated user's citizen profile."""

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "put"]

    def get(self, request: Request) -> Response:
        if request.user.is_business:
            return Response(
                {
                    **_serialize_business(request.user),
                    "shareholders": _serialize_shareholders(request.user),
                }
            )
        return Response(_serialize_profile(request.user))

    def put(self, request: Request) -> Response:
        user = request.user
        if user.is_business:
            business, _ = BusinessProfile.objects.get_or_create(user=user)
            serializer = BusinessProfileUpdateSerializer(
                instance=business, data=request.data, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            if "shareholders" in request.data:
                self._sync_shareholders(business, request.data.get("shareholders") or [])
            return Response(
                {**_serialize_business(user), "shareholders": _serialize_shareholders(user)}
            )

        serializer = ProfileUpdateSerializer(instance=user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(_serialize_profile(user))

    @staticmethod
    def _sync_shareholders(business, rows) -> None:
        """Replace the company's beneficial owners with the submitted rows.

        Each row is validated via ``ShareholderSerializer``; blank-date /
        blank-percent values are coerced, and rows with no name are dropped
        (so the trailing empty row in the editor isn't persisted).
        """
        cleaned = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            row = dict(row)
            if not row.get("birthdate"):
                row["birthdate"] = None
            if row.get("ownership_percent") in ("", None):
                row["ownership_percent"] = 0
            if not (row.get("first_name") or row.get("last_name")):
                continue
            serializer = ShareholderSerializer(data=row)
            serializer.is_valid(raise_exception=True)
            cleaned.append(serializer.validated_data)

        business.shareholders.all().delete()
        Shareholder.objects.bulk_create(
            [Shareholder(business=business, **row) for row in cleaned]
        )
