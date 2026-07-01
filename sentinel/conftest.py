"""Root conftest -- shared fixtures for the Sentinel Screening provider test suite."""

from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.utils import timezone

from app.core.users.factories import UserFactory


@pytest.fixture
def user(db):
    """A connected subject with a clear screening record."""
    return UserFactory()


@pytest.fixture
def make_token(db):
    """Factory for RequestToken creation."""
    from app.core.requests.models import RequestToken

    def _make(user, scope_grant=None, used=False, expires_in_minutes=5):
        return RequestToken.objects.create(
            jti=uuid4().hex,
            request_id=uuid4(),
            user=user,
            service_id=uuid4(),
            service_public_key="mock_requester_public_key",
            scope=scope_grant or {"sanctions.check": {}},
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
