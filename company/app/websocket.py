import json
import logging
import traceback


from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer

from django.core.handlers.asgi import logger

from django.db.models import TextChoices

logger = logging.getLogger("console")


class WebsocketChannel(TextChoices):
    ALL = "all", "Notify all users"
    OWNER = "owner", "Only owner of object can be notified"


WEBSOCKET_CHANNELS = WebsocketChannel


class Websocket(WebsocketConsumer):
    """
    Websocket to send changes to users to allow real-time collaboration.
    """

    ALL = "all"

    def connect(self) -> None:
        """Connect the socket."""

        # Close connection if user is not authenticated
        user = self.scope.get("user")
        if not user.is_authenticated:
            self.close()
            return

        # Accept connection
        self.accept()

        # Add user to global notifications
        async_to_sync(self.channel_layer.group_add)(self.ALL, self.channel_name)

        # Add user to his own notifications
        async_to_sync(self.channel_layer.group_add)(f"user-{user.id}", self.channel_name)

    def disconnect(self, *args, **kwargs) -> None:
        """Remove channel from"""

        # Do nothing if user is not authenticated
        user = self.scope.get("user")
        if not user.is_authenticated:
            return

        # Remove user from global notifications
        async_to_sync(self.channel_layer.group_discard)(self.ALL, self.channel_name)

        # Remove user from his own notifications
        async_to_sync(self.channel_layer.group_discard)(f"user-{user.id}", self.channel_name)

    def notify(self, message: dict) -> None:
        """Send message to users."""
        try:
            self.send(text_data=message["data"])
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"\n\n[WEBSOCKET ERROR]: {exc}\n\nMESSAGE:\n{message}\n")
            traceback.print_exc()

    def receive(self, text_data: str = None, bytes_data: bytes = None):
        """Receive message from websocket."""
        json_data = json.loads(text_data)
        data_type = json_data.get("type")

        # Respond with healthy status
        if data_type == "ping":
            self.send(text_data=json.dumps({"type": "pong"}))
