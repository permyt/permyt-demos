from app import managers, models


class Nonce(models.AppModel):
    """Replay protection — each nonce is used exactly once."""

    WEBSOCKET_NOTIFICATIONS_ENABLED = False
    DELETE_AFTER = 60  # in minutes, to allow for cleanup after use

    value = models.CharField(max_length=128, unique=True, db_index=True)

    # Only superusers can see and manage nonces
    objects = managers.SuperuserManager()

    def __str__(self):
        return self.value[:20]
