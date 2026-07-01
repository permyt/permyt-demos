"""Seed helpers for the Bank demo provider."""

from decimal import Decimal

from faker import Faker

from .models import Movement

_TYPE_WEIGHTS = (
    (Movement.TYPE_TRANSFER, 4),
    (Movement.TYPE_CARD_PAYMENT, 5),
    (Movement.TYPE_INCOMING, 2),
    (Movement.TYPE_FEE, 1),
)


def _weighted_type(fake: Faker) -> str:
    refs = tuple(t for t, _ in _TYPE_WEIGHTS)
    return fake.random_element(elements=refs)


def seed_movements(user, count: int = 15) -> list[Movement]:
    """Populate ``count`` mock movements for ``user``.

    Mixes small debits, occasional incoming credits, and the odd fee. The
    user's running balance is *not* recomputed from these movements — they
    are purely cosmetic history. ``balance`` is set independently in
    ``seed_profile``.
    """
    fake = Faker("en_GB")
    movements: list[Movement] = []
    for _ in range(count):
        m_type = _weighted_type(fake)
        if m_type == Movement.TYPE_INCOMING:
            amount = Decimal(fake.random_int(min=200, max=2500))
            counterparty_name = fake.company()
            reference = fake.sentence(nb_words=3).rstrip(".")
        elif m_type == Movement.TYPE_FEE:
            amount = Decimal(-fake.random_int(min=1, max=5))
            counterparty_name = "Bank fees"
            reference = "Monthly fee"
        elif m_type == Movement.TYPE_CARD_PAYMENT:
            amount = Decimal(-fake.random_int(min=5, max=120))
            counterparty_name = fake.company()
            reference = fake.word().capitalize()
        else:  # TRANSFER
            amount = Decimal(-fake.random_int(min=20, max=400))
            counterparty_name = fake.name()
            reference = fake.sentence(nb_words=2).rstrip(".")

        movements.append(
            Movement.objects.create(
                user=user,
                amount=amount,
                currency=user.currency or "EUR",
                counterparty_name=counterparty_name,
                counterparty_iban=fake.iban(),
                reference=reference,
                type=m_type,
            )
        )
    return movements
