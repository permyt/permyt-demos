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
        # TO DO LATER: Save messages to test if they are being sent during tests
        # current_test = test_globals.get_test_name()
        # test_settings = test_globals.SETTINGS.get(current_test)
        # if test_settings and test_settings.STORE_WS_MESSAGES:
        #     test_settings.WS_MESSAGES += [data]
        return

    dumped_data = json.dumps(data, cls=JSONEncoder)
    async_to_sync(channel_layer.group_send)(channel, {"type": "notify", "data": dumped_data})
