from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from .models import Movement


class MovementFactory(DjangoModelFactory):
    class Meta:
        model = Movement

    amount = Decimal("-50.00")
    currency = "EUR"
    counterparty_name = factory.Sequence(lambda n: f"Counterparty {n + 1}")
    counterparty_iban = factory.Sequence(lambda n: f"GB29NWBK60161331{str(n + 1).zfill(6)}")
    reference = factory.Sequence(lambda n: f"Ref {n + 1}")
    type = Movement.TYPE_TRANSFER
