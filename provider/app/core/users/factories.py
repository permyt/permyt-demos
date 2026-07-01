from uuid import uuid4

import factory
from django.contrib.sessions.backends.db import SessionStore
from factory.django import DjangoModelFactory

from .models import User, LoginToken, NoteField, UserFieldValue


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    first_name = factory.Sequence(lambda n: f"User{n + 1}")
    last_name = "Test"
    username = factory.Sequence(lambda n: f"user{n + 1}")
    email = factory.Sequence(lambda n: f"user{n + 1}@test.permyt.io")
    permyt_user_id = factory.LazyFunction(uuid4)


class LoginTokenFactory(DjangoModelFactory):
    class Meta:
        model = LoginToken

    token = factory.LazyFunction(lambda: str(uuid4()))

    @factory.lazy_attribute
    def session_id(self):
        store = SessionStore()
        store.create()
        return store.session_key


class NoteFieldFactory(DjangoModelFactory):
    class Meta:
        model = NoteField

    slug = factory.Sequence(lambda n: f"field_{n}")
    name = factory.Sequence(lambda n: f"Field {n}")


class UserFieldValueFactory(DjangoModelFactory):
    class Meta:
        model = UserFieldValue

    user = factory.SubFactory(UserFactory)
    field = factory.SubFactory(NoteFieldFactory)
    value = "Test value."
