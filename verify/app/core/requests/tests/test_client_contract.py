"""
Tests for the requester PermytClient contract.

Exercises the client's abstract-method implementations:
* Nonce replay protection (atomic insert)
* _prepare_data_for_endpoint (locks min_age from Verification)
* _extract_is_older (parses provider response shape)
"""

from datetime import datetime, timedelta, timezone

import pytest

from permyt.exceptions import ExpiredRequestError


@pytest.mark.django_db
class TestNonceAndTimestamp:
    def test_fresh_nonce_accepted(self, mock_permyt_client):
        mock_permyt_client._validate_nonce_and_timestamp(
            "nonce-1", datetime.now(timezone.utc).isoformat()
        )

    def test_nonce_reuse_rejected(self, mock_permyt_client):
        ts = datetime.now(timezone.utc).isoformat()
        mock_permyt_client._validate_nonce_and_timestamp("nonce-2", ts)
        with pytest.raises(ExpiredRequestError, match="Nonce"):
            mock_permyt_client._validate_nonce_and_timestamp("nonce-2", ts)

    def test_expired_timestamp_rejected(self, mock_permyt_client):
        old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        with pytest.raises(ExpiredRequestError, match="timestamp"):
            mock_permyt_client._validate_nonce_and_timestamp("nonce-old", old)

    def test_future_timestamp_rejected(self, mock_permyt_client):
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        with pytest.raises(ExpiredRequestError, match="timestamp"):
            mock_permyt_client._validate_nonce_and_timestamp("nonce-future", future)


class TestPrepareDataForEndpoint:
    def test_empty_input_fields_returns_empty(self, mock_permyt_client):
        result = mock_permyt_client._prepare_data_for_endpoint(
            "req-123", {"url": "http://provider/api/something", "scope": "test"}
        )
        assert result == {}

    @pytest.mark.django_db
    def test_min_age_supplied_when_input_field_present(self, mock_permyt_client):
        from app.core.verifications.models import Verification

        verification = Verification.objects.create(
            session_key="t1", min_age=18, request_id="req-456"
        )
        result = mock_permyt_client._prepare_data_for_endpoint(
            "req-456",
            {
                "url": "http://gov/rest/is_older/check/",
                "scope": "is_older.check",
                "input_fields": {"min_age": "integer"},
            },
        )
        assert result == {"min_age": verification.min_age}


class TestExtractIsOlder:
    def test_returns_true_when_provider_says_true(self, mock_permyt_client):
        assert mock_permyt_client._extract_is_older([{"is_older": True}]) is True

    def test_returns_false_when_provider_says_false(self, mock_permyt_client):
        assert mock_permyt_client._extract_is_older([{"is_older": False}]) is False

    def test_returns_none_when_field_missing(self, mock_permyt_client):
        assert mock_permyt_client._extract_is_older([{"other": "data"}]) is None
        assert mock_permyt_client._extract_is_older([]) is None
