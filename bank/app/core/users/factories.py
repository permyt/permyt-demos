from decimal import Decimal
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
    iban = factory.Sequence(lambda n: f"GB29NWBK60161331{str(n + 1).zfill(6)}")
    balance = Decimal("5000.00")
    currency = "EUR"


class LoginTokenFactory(DjangoModelFactory):
    class Meta:
        model = LoginToken

    token = factory.LazyFunction(lambda: str(uuid4()))

    @factory.lazy_attribute
    def session_id(self):
        store = SessionStore()
        store.create()
        return store.session_key
