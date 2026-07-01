import factory
from factory.django import DjangoModelFactory

from .models import User


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    first_name = factory.Sequence(lambda n: f"User{n + 1}")
    last_name = "Test"
    username = factory.Sequence(lambda n: f"user{n + 1}")
    email = factory.Sequence(lambda n: f"user{n + 1}@test.permyt.io")
