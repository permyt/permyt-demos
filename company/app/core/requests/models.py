from app import managers, models
from app.core.users.models import User


class Nonce(models.AppModel):
    """Replay protection — each nonce is used exactly once."""

    WEBSOCKET_NOTIFICATIONS_ENABLED = False
    DELETE_AFTER = 60  # in minutes, to allow for cleanup after use

    value = models.CharField(max_length=128, unique=True, db_index=True)

    # Only superusers can see and manage nonces
    objects = managers.SuperuserManager()

    def __str__(self):
        return self.value[:20]


class RequestToken(models.AppModel):
    """Single-use token issued to a requester for accessing user data."""

    WEBSOCKET_NOTIFICATIONS_ENABLED = False
    DEFAULT_EXPIRATION = 5  # minutes
    DELETE_AFTER = 60  # minutes

    jti = models.CharField(max_length=256, unique=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="request_tokens")
    request_id = models.UUIDField()
    service_id = models.UUIDField()
    service_public_key = models.EncryptedTextField()
    scope = models.EncryptedJSONField(default=dict)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    objects = managers.SuperuserManager()

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Token {self.jti[:12]}… (used={self.used})"
