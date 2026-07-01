from datetime import date
from uuid import uuid4

import factory
from django.contrib.sessions.backends.db import SessionStore
from factory.django import DjangoModelFactory

from .models import User, LoginToken


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    first_name = factory.Sequence(lambda n: f"User{n + 1}")
    last_name = "Test"
    username = factory.Sequence(lambda n: f"user{n + 1}")
    email = factory.Sequence(lambda n: f"user{n + 1}@test.permyt.io")
    permyt_user_id = factory.LazyFunction(uuid4)

    full_name = factory.Sequence(lambda n: f"User {n + 1} Test")
    birthdate = factory.Sequence(lambda n: date(1990, 1, 1).replace(day=(n % 28) + 1))
    address = factory.Sequence(lambda n: f"{n + 1} Demo Street, Demo City")
    country = "US"
    vat = factory.Sequence(lambda n: f"US{str(n + 1).zfill(9)}")
    phone = factory.Sequence(lambda n: f"+1{str(n + 1).zfill(10)}")
    tax_id = factory.Sequence(lambda n: f"100-00-{str(n + 1).zfill(4)}")


class LoginTokenFactory(DjangoModelFactory):
    class Meta:
        model = LoginToken

    token = factory.LazyFunction(lambda: str(uuid4()))

    @factory.lazy_attribute
    def session_id(self):
        store = SessionStore()
        store.create()
        return store.session_key
