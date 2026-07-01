from uuid import uuid4

import factory
from factory.django import DjangoModelFactory

from app.core.requests.models import Nonce


class NonceFactory(DjangoModelFactory):
    class Meta:
        model = Nonce

    value = factory.LazyFunction(lambda: uuid4().hex)
