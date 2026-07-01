"""Root conftest -- shared fixtures for the NoteVault provider test suite."""

from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.utils import timezone

from app.core.users.factories import NoteFieldFactory, UserFactory, UserFieldValueFactory


@pytest.fixture
def note_field(db):
    """A NoteField for testing."""
    return NoteFieldFactory(slug="mission_log", name="Mission Log")


@pytest.fixture
def user(db, note_field):
    """A user with a field value for the default note_field."""
    u = UserFactory()
    UserFieldValueFactory(user=u, field=note_field, value="Test mission log entry.")
    return u


@pytest.fixture
def make_token(db, note_field):
    """Factory for RequestToken creation."""
    from app.core.requests.models import RequestToken

    def _make(user, scope_grant=None, used=False, expires_in_minutes=5):
        return RequestToken.objects.create(
            jti=uuid4().hex,
            request_id=uuid4(),
            user=user,
            service_id=uuid4(),
            service_public_key="mock_requester_public_key",
            scope=scope_grant or {f"{note_field.slug}.read": {}},
            expires_at=timezone.now() + timedelta(minutes=expires_in_minutes),
            used=used,
        )

    return _make


@pytest.fixture
def mock_permyt_client():
    """Create a PermytClient with mocked key loading."""
    with patch("app.core.requests.client.Path") as mock_path:
        mock_path.return_value.read_text.return_value = "mock-key"
        with patch("permyt.PermytClient.__init__", return_value=None):
            from app.core.requests.client import PermytClient

            client = PermytClient()
            client.private_key = MagicMock()
            client.host = "http://localhost:8000"
            client.service_id = "test-service-id"
            yield client
