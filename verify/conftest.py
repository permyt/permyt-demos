"""Root conftest -- shared fixtures for the verify demo test suite."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def verification(db):
    """A pending Verification attached to a fake session_key."""
    from app.core.verifications.models import Verification

    return Verification.objects.create(session_key="test-session-key")


@pytest.fixture
def mock_permyt_client():
    """A PermytClient with key loading + transport mocked."""
    with patch("app.core.requests.client.Path") as mock_path:
        mock_path.return_value.read_text.return_value = "mock-key"
        with patch("permyt.PermytClient.__init__", return_value=None):
            from app.core.requests.client import PermytClient

            client = PermytClient()
            client.private_key = MagicMock()
            client.host = "http://localhost:8000"
            client.service_id = "test-service-id"
            yield client
