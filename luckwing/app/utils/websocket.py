import json


from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings

from app.utils.encoders import JSONEncoder

channel_layer = get_channel_layer()


def send_to_websocket(channel, data: dict) -> None:
    """
    Send a message to a websocket.
    :param channel: Websocket channel.
    :param data: Data to be sent to channel.
    """
    if settings.TEST:
        return

    dumped_data = json.dumps(data, cls=JSONEncoder)
    async_to_sync(channel_layer.group_send)(channel, {"type": "notify", "data": dumped_data})
