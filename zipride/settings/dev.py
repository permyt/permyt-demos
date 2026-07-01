###############################################################################
# This code has the configurations for development mode and
# it is automatically imported if the system is in DEBUG mode.
###############################################################################

from .base import *  # pylint: disable=wildcard-import, unused-wildcard-import

if DEBUG:
    INSTALLED_APPS += [
        "django_extensions",
        "debug_toolbar",
    ]

    MIDDLEWARE += [
        "debug_toolbar.middleware.DebugToolbarMiddleware",
    ]

    INTERNAL_IPS = [
        "localhost",
        "127.0.0.1",
    ]
