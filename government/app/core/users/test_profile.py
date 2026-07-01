"""Tests for the Government citizen profile: User.seed_profile and ProfileView."""

import json

import pytest
from django.test import Client

from .factories import UserFactory
from .models import User


@pytest.mark.django_db
class TestUserModel:
    def test_country_uppercased_on_save(self):
        u = UserFactory(country="pt")
        u.refresh_from_db()
        assert u.country == "PT"

    def test_seed_profile_fills_blank_fields(self):
        u = User.objects.create(
            username="seedme",
            email="seedme@test.permyt.io",
            full_name="",
            address="",
            country="",
        )
        u.seed_profile()
        u.refresh_from_db()
        assert u.full_name
        assert u.birthdate is not None
        assert u.address
        assert len(u.country) == 2
        assert u.vat
        assert u.phone.startswith("+")
        assert u.tax_id

    def test_seed_profile_idempotent(self):
        u = UserFactory(full_name="Pre-set Name", country="PT", vat="PT999999999")
        u.seed_profile()
        u.refresh_from_db()
        assert u.full_name == "Pre-set Name"
        assert u.country == "PT"
        assert u.vat == "PT999999999"

    def test_seed_profile_only_fills_missing(self):
        u = UserFactory(full_name="")
        original_country = u.country
        u.seed_profile()
        u.refresh_from_db()
        assert u.full_name  # newly filled
        assert u.country == original_country  # untouched


@pytest.mark.django_db
class TestProfileView:
    def _login(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_get_returns_profile(self, user):
        client = self._login(user)
        resp = client.get("/rest/profile/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["full_name"] == user.full_name
        assert data["country"] == user.country
        assert data["birthdate"] == user.birthdate.isoformat()

    def test_put_partial_update(self, user):
        client = self._login(user)
        resp = client.put(
            "/rest/profile/",
            data=json.dumps({"country": "pt"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.country == "PT"

    def test_put_invalid_country_rejected(self, user):
        client = self._login(user)
        resp = client.put(
            "/rest/profile/",
            data=json.dumps({"country": "XYZ"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_put_invalid_phone_rejected(self, user):
        client = self._login(user)
        resp = client.put(
            "/rest/profile/",
            data=json.dumps({"phone": "not-a-phone"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_unauthenticated_rejected(self, db):
        resp = Client().get("/rest/profile/")
        assert resp.status_code in (401, 403)
