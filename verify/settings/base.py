import os

from pathlib import Path
from kombu.serialization import register

from app.utils.encoders import JSONEncoder

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-b#1R#h85LO0REhrlP^qcb$wBasdcZ!$QZjqUtnhk%C7^VSRXr2m",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", "true").lower() == "true"
TEST = False
LOG_ACTIVITY = True

ALLOWED_HOSTS = ["*"]
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
SESSION_COOKIE_NAME = "permyt-verify"

# Default primary key field type
# https://docs.djangoproject.com/en/6.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Application definition

INSTALLED_APPS = [
    "daphne",  # Daphne is a HTTP, HTTP2 and WebSocket protocol server for ASGI
    # Django default apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    # Project apps
    "app",
    # Common
    "app.common",
    "app.common.pages",
    "app.common.unittests",
    # Core
    "app.core.logs",
    "app.core.requests",
    "app.core.users",
    "app.core.verifications",
    # 3rd-party apps
    "corsheaders",  # Adds CORS (Cross-Origin Resource Sharing) headers to responses
    "django_celery_beat",  # Allows to schedule tasks for celery from admin page
    "rest_framework",  # Django REST Framework
    "secured_fields",  # Secured fields for Django models and forms
    "compressor",  # Compresses linked and inline JS/CSS into cacheable files
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "app.utils.middleware.ThreadLocalUserMiddleware",
]


ROOT_URLCONF = "app.urls"
ASGI_APPLICATION = "settings.asgi.application"
WSGI_APPLICATION = "settings.wsgi.application"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

COMPRESS_PRECOMPILERS = [
    ("text/x-scss", "django_libsass.SassCompiler"),
]

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "compressor.finders.CompressorFinder",
]

ASGI_APPLICATION = "settings.asgi.application"
WSGI_APPLICATION = "settings.wsgi.application"


# Django REST Framework
# https://www.django-rest-framework.org/
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "app.utils.renderers.JSONRenderer",
        "rest_framework.renderers.AdminRenderer",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 100,
}

# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
    },
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_USER_MODEL = "users.User"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static")

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/media-files/

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 10  # 10MB

# Logging.
# ---------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "propagate": True,
            "level": "INFO" if DEBUG else "ERROR",
        },
        "console": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "DEBUG"),
        },
    },
}


# Celery: Background tasks queues with monitor
# https://docs.celeryproject.org/en/stable/django/

# Register custom serializer to handle non serializable data
register(
    "celery-serializer",
    JSONEncoder.dumps,
    JSONEncoder.loads,
    content_type="application/json",
)

CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BROKER_URL = f"redis://{REDIS_HOST}:6379"
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_RESULT_BACKEND = f"redis://{REDIS_HOST}:6379"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_DEFAULT_QUEUE = "permyt-verify-dev-celery-"
CELERY_TASK_SERIALIZER = "celery-serializer"
CELERY_TASK_TIME_LIMIT = 60 * 30  # 30 minutes
CELERY_TASK_TRACK_STARTED = True
CELERY_TIMEZONE = "UTC"

# Redis specific celery settings
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": CELERY_TASK_TIME_LIMIT * 2,
}


# Channels
# https://channels.readthedocs.io/

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_HOST, 6379)],
            "prefix": "permyt-verify-dev-channels-",
        },
    }
}

# Redis Cache
# https://niwinz.github.io/django-redis/latest/

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:6379",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SERIALIZER_CLASS": "app.utils.encoders.RedisSerializer",
        },
        "KEY_PREFIX": "permyt-verify-dev-cache-",
    }
}

# CORS
# https://github.com/adamchainz/django-cors-headers

CORS_ALLOW_ALL_ORIGINS = DEBUG


# Secured Fields: https://github.com/C0D1UM/django-secured-fields
# ---------------------------------------------------------------

# NOTE: Do not use this key in production
SECURED_FIELDS_KEY = os.environ.get(
    "SECURED_FIELDS_KEY", "Ot1ee8MohgGosTKeen8XKKnRsgcwHANhfO3I4Y-0PPc="
)
SECURED_FIELDS_HASH_SALT = os.environ.get("SECURED_FIELDS_HASH_SALT", "8d352777")


# ---------------------------------------------------------------------------
# PERMYT connector settings
# ---------------------------------------------------------------------------

PERMYT_SERVICE_ID = os.environ.get("PERMYT_SERVICE_ID", "")
PERMYT_PUBLIC_KEY_PATH = os.environ.get("PERMYT_PUBLIC_KEY_PATH", "keys/permyt/public.pem")
PRIVATE_KEY_PATH = os.environ.get("PRIVATE_KEY_PATH", "keys/connector/private.pem")

BASE_URL = os.environ.get("BASE_URL", "http://localhost:9015")
NONCE_TTL_SECONDS = int(os.environ.get("NONCE_TTL_SECONDS", "60"))

PERMYT_HOST = os.environ.get("PERMYT_HOST", "http://localhost:8000")
REQUESTER_CALLBACK_URL = os.environ.get("REQUESTER_CALLBACK_URL", BASE_URL + "/rest/permyt/inbound")


# ---------------------------------------------------------------------------
# Verify demo settings
# ---------------------------------------------------------------------------

VERIFY_MIN_AGE = int(os.environ.get("VERIFY_MIN_AGE", "18"))
VERIFY_APP_NAME = os.environ.get("VERIFY_APP_NAME", "PERMYT Verify")


# Local settings
# This is the file where to save settings for development and for server secure settings.
try:
    from .local import *  # pylint: disable=unused-wildcard-import,wildcard-import
except ImportError:
    pass
