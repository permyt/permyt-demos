import logging
import random

from django.utils.text import slugify
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from permyt.exceptions import PermytError

from app.core.requests.client import PermytClient
from app.core.users.models import NoteField, User, UserFieldValue, SEED_TEXTS

from .scopes.utils import sync_scopes_to_broker

logger = logging.getLogger(__name__)


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
    """Per-scope endpoint for service_call actions (e.g. /rest/mission_log/read/)."""

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


class NoteFieldView(APIView):
    """CRUD for individual note field values (used by the dashboard)."""

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "put", "delete"]

    def get(self, request: Request, field_name: str) -> Response:
        """Return the field value for the authenticated user."""
        try:
            fv = UserFieldValue.objects.get(user=request.user, field__slug=field_name)
        except UserFieldValue.DoesNotExist:
            return Response({"error": f"Unknown field: {field_name}"}, status=404)
        return Response({"field": field_name, "content": fv.value})

    def put(self, request: Request, field_name: str) -> Response:
        """Update the field value for the authenticated user."""
        try:
            fv = UserFieldValue.objects.get(user=request.user, field__slug=field_name)
        except UserFieldValue.DoesNotExist:
            return Response({"error": f"Unknown field: {field_name}"}, status=404)
        fv.value = request.data.get("content", "")
        fv.save(update_fields=["value", "updated_at"])
        return Response({"field": field_name, "content": fv.value})

    def delete(self, request: Request, field_name: str) -> Response:
        """Delete the NoteField (superuser only) and sync scopes to the broker."""
        if not request.user.is_superuser:
            return Response({"error": "Only superusers can delete fields."}, status=403)
        try:
            note_field = NoteField.objects.get(slug=field_name)
        except NoteField.DoesNotExist:
            return Response({"error": f"Unknown field: {field_name}"}, status=404)
        note_field.delete()
        sync_scopes_to_broker()
        return Response(status=204)


class NoteFieldListView(APIView):
    """Create new note fields (superusers only)."""

    permission_classes = [IsAuthenticated]
    http_method_names = ["post"]

    def post(self, request: Request) -> Response:
        """Create a new NoteField, seed values for all users, and sync scopes."""
        if not request.user.is_superuser:
            return Response({"error": "Only superusers can create fields."}, status=403)

        name = request.data.get("name", "").strip()
        if not name:
            return Response({"error": "Name is required."}, status=400)

        slug = slugify(name).replace("-", "_")
        if not slug:
            return Response({"error": "Invalid name."}, status=400)

        if NoteField.objects.filter(slug=slug).exists():
            return Response({"error": f"Field '{slug}' already exists."}, status=409)

        note_field = NoteField.objects.create(slug=slug, name=name)

        # Seed a value for every existing user
        users = User.objects.all()
        UserFieldValue.objects.bulk_create(
            [
                UserFieldValue(user=u, field=note_field, value=random.choice(SEED_TEXTS))
                for u in users
            ],
            ignore_conflicts=True,
        )

        sync_scopes_to_broker()
        return Response(
            {"field": note_field.slug, "name": note_field.name},
            status=201,
        )
