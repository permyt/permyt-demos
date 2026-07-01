import factory
from factory.django import DjangoModelFactory

from .models import Log


class LogFactory(DjangoModelFactory):
    class Meta:
        model = Log

    action = factory.Sequence(lambda n: f"action_{n}")
