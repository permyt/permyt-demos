import factory
from factory.django import DjangoModelFactory

from app.core.users.factories import UserFactory
from .models import Log


class LogFactory(DjangoModelFactory):
    class Meta:
        model = Log

    user = factory.SubFactory(UserFactory)
    action = factory.Sequence(lambda n: f"action_{n}")
