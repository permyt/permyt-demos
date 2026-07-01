from uuid import uuid4

import factory
from django.contrib.sessions.backends.db import SessionStore
from factory.django import DjangoModelFactory

from .models import CompanyKB, LoginToken, User


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"company{n + 1}")
    email = factory.Sequence(lambda n: f"company{n + 1}@test.permyt.io")
    permyt_user_id = factory.LazyFunction(uuid4)


class CompanyKBFactory(DjangoModelFactory):
    class Meta:
        model = CompanyKB

    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Test Company {n + 1} Ltd")
    business_plan = "A test business plan."
    financials_summary = "Test financials."
    products = factory.LazyFunction(lambda: ["Product A", "Product B"])


class LoginTokenFactory(DjangoModelFactory):
    class Meta:
        model = LoginToken

    token = factory.LazyFunction(lambda: str(uuid4()))

    @factory.lazy_attribute
    def session_id(self):
        store = SessionStore()
        store.create()
        return store.session_key
