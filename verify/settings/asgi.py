"""
ASGI config for app project.

It exposes the ASGI callable as a module-level variable named `application`.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from channels.sessions import SessionMiddlewareStack

from django.core.asgi import get_asgi_application
from django.urls import path

from app.websocket import Websocket

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.base")


application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": AllowedHostsOriginValidator(
            SessionMiddlewareStack(
                URLRouter(
                    [
                        path("ws/", Websocket.as_asgi(), name="ws"),
                    ]
                )
            )
        ),
    }
)
