from app import models


class Movement(models.AppModel):
    """A single account movement (transaction) on the user's bank account.

    Amount is *signed* — debits are negative (outgoing payments, fees, card
    spend) and credits are positive (incoming transfers, refunds). The
    counterparty IBAN/name describe the other side of the transaction.
    """

    WEBSOCKET_NOTIFICATIONS_ENABLED = False

    TYPE_TRANSFER = "TRANSFER"
    TYPE_CARD_PAYMENT = "CARD_PAYMENT"
    TYPE_INCOMING = "INCOMING"
    TYPE_FEE = "FEE"
    TYPE_CHOICES = (
        (TYPE_TRANSFER, "Transfer"),
        (TYPE_CARD_PAYMENT, "Card payment"),
        (TYPE_INCOMING, "Incoming"),
        (TYPE_FEE, "Fee"),
    )

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="movements",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    counterparty_name = models.CharField(max_length=255, blank=True, default="")
    counterparty_iban = models.CharField(max_length=34, blank=True, default="")
    reference = models.CharField(max_length=255, blank=True, default="")
    type = models.CharField(max_length=16, choices=TYPE_CHOICES, default=TYPE_TRANSFER)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        sign = "+" if self.amount >= 0 else "-"
        return f"{sign}{abs(self.amount)} {self.currency} → {self.counterparty_name or self.counterparty_iban}"
