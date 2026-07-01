import datetime
import pytz

from django.conf import settings
from django.utils import dateparse


def parse_datetime(value: str):
    """
    Parse a string and return a datetime.datetime.

    This function supports time zone offsets. When the input contains one,
    the output uses a timezone with a fixed offset from UTC.

    Return None if the input is not valid
    """
    if not value:
        return None

    if isinstance(value, datetime.datetime):
        return value

    try:
        value = dateparse.parse_datetime(value)
        if value and value.tzinfo is None:
            server_timezone = pytz.timezone(settings.TIME_ZONE)
            value = server_timezone.localize(value)
    except ValueError:
        value = None

    return value


def parse_date(value: str):
    """
    Parse a string and return a datetime.date.

    Return None if the input is not valid
    """
    if not value:
        return None

    if isinstance(value, datetime.datetime):
        return value.date()

    if isinstance(value, datetime.date):
        return value

    try:
        value = dateparse.parse_date(value)
    except ValueError:
        value = None

    return value
