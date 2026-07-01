"""Tests for the Sentinel Screening subject record and ProfileView."""

import json

import pytest
from django.test import Client

from app.mixins.tests import ModelTest

from .factories import UserFactory, LoginTokenFactory
from .models import User, LoginToken


class TestUser(ModelTest):
    model = User
    factory = UserFactory
    endpoint = "users"
    PERMISSION_TYPE = ModelTest.PERMISSION_TYPES.OWNER
    PERMISSION_PUBLIC = False
    SUPERUSER_FIELD = "is_account_manager"
    CAN_CREATE = False
    CAN_DELETE = False
    OBJS_LIST = 1
    SERIALIZER_READ_ONLY_FIELDS = ("permyt_user_id", "is_account_manager")
    SERIALIZER_IMMUTABLE_FIELDS = ("permyt_user_id",)


class TestLoginToken(ModelTest):
    model = LoginToken
    factory = LoginTokenFactory
    PERMISSION_TYPE = ModelTest.PERMISSION_TYPES.SUPERUSER
    SUPERUSER_FIELD = "is_account_manager"
    ENABLE_VIEWS = False


@pytest.mark.django_db
class TestScreeningRecord:
    """The subject's screening outcomes default clear and seed idempotently."""

    def test_outcomes_default_clear(self):
        u = User.objects.create(username="fresh")
        assert u.sanctions_match is False
        assert u.pep is False
        assert u.adverse_media is False
        assert u.self_excluded is False

    def test_seed_persists_record(self):
        u = User.objects.create(username="seedme")
        u.seed()  # alias for seed_profile()
        u.refresh_from_db()
        assert u.sanctions_match is False

    def test_seed_preserves_existing_flags(self):
        u = UserFactory(sanctions_match=True, adverse_media=True)
        u.seed_profile()
        u.refresh_from_db()
        assert u.sanctions_match is True
        assert u.adverse_media is True
        assert u.pep is False


@pytest.mark.django_db
class TestProfileView:
    """GET returns the four screening booleans; PUT edits them."""

    def _login(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_get_returns_screening(self, user):
        client = self._login(user)
        resp = client.get("/rest/profile/")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {
            "sanctions_match": False,
            "pep": False,
            "adverse_media": False,
            "self_excluded": False,
        }

    def test_put_flags_subject(self, user):
        client = self._login(user)
        resp = client.put(
            "/rest/profile/",
            data=json.dumps({"sanctions_match": True}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["sanctions_match"] is True
        user.refresh_from_db()
        assert user.sanctions_match is True

    def test_put_partial_leaves_others_untouched(self, user):
        client = self._login(user)
        client.put(
            "/rest/profile/",
            data=json.dumps({"pep": True}),
            content_type="application/json",
        )
        user.refresh_from_db()
        assert user.pep is True
        assert user.sanctions_match is False

    def test_unauthenticated_rejected(self, db):
        resp = Client().get("/rest/profile/")
        assert resp.status_code in (401, 403)
