import json
import logging
import traceback


from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer

from django.db.models import TextChoices

logger = logging.getLogger("console")


class WebsocketChannel(TextChoices):
    ALL = "all", "Notify all users"
    SESSION = "session", "Notify a single session"


WEBSOCKET_CHANNELS = WebsocketChannel


class Websocket(WebsocketConsumer):
    """
    Websocket consumer keyed on the Django session.

    No authentication: visitors are anonymous. Each connection joins:
        - "all"  for global broadcasts.
        - "session-{session_key}"  for booking-scoped events.
    """

    ALL = "all"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_key: str | None = None

    def connect(self) -> None:
        session = self.scope.get("session")
        if not session:
            self.close()
            return

        if not session.session_key:
            session.save()

        self.session_key = session.session_key
        self.accept()

        async_to_sync(self.channel_layer.group_add)(self.ALL, self.channel_name)
        async_to_sync(self.channel_layer.group_add)(
            f"session-{self.session_key}", self.channel_name
        )

    def disconnect(self, *args, **kwargs) -> None:
        if not getattr(self, "session_key", None):
            return
        async_to_sync(self.channel_layer.group_discard)(self.ALL, self.channel_name)
        async_to_sync(self.channel_layer.group_discard)(
            f"session-{self.session_key}", self.channel_name
        )

    def notify(self, message: dict) -> None:
        try:
            self.send(text_data=message["data"])
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"\n\n[WEBSOCKET ERROR]: {exc}\n\nMESSAGE:\n{message}\n")
            traceback.print_exc()

    def receive(self, text_data: str = None, bytes_data: bytes = None):
        json_data = json.loads(text_data)
        data_type = json_data.get("type")

        if data_type == "ping":
            self.send(text_data=json.dumps({"type": "pong"}))
