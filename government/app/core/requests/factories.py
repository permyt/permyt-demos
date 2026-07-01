from datetime import timedelta
from uuid import uuid4

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from app.core.requests.models import Nonce, RequestToken
from app.core.users.factories import UserFactory


class NonceFactory(DjangoModelFactory):
    class Meta:
        model = Nonce

    value = factory.LazyFunction(lambda: uuid4().hex)


class RequestTokenFactory(DjangoModelFactory):
    class Meta:
        model = RequestToken

    jti = factory.LazyFunction(lambda: uuid4().hex)
    user = factory.SubFactory(UserFactory)
    request_id = factory.LazyFunction(uuid4)
    service_id = factory.LazyFunction(uuid4)
    service_public_key = "mock_requester_public_key"
    scope = factory.LazyFunction(lambda: {"field_0.read": {}})
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(minutes=5))
    used = False
