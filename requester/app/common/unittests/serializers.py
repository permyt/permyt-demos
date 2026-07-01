from app.serializers import AppModelSerializer

from .models import TstMessage, TstModelA, TstModelB


class TstModelASerializer(AppModelSerializer):
    """
    Default serializer to convert a TstModelA into JSON.
    """

    class Meta:
        model = TstModelA
        fields = ("id", "data", "message")


class TstModelBSerializer(AppModelSerializer):
    """
    Default serializer to convert a CountryGroup into JSON.
    """

    class Meta:
        model = TstModelB
        fields = ("id", "data", "message")


class TstMessageSerializer(AppModelSerializer):  # pylint: disable=abstract-method
    """
    Default serializer to convert a TstMessage into JSON.
    """

    class Meta:
        model = TstMessage
        fields = ("id", "data", "message")
