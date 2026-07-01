from app.mixins.serializers import AppModelSerializer

from .models import Log


class LogSerializer(AppModelSerializer):

    class Meta:
        model = Log
        fields = ("user", "action", "success", "data")
        read_only_fields = fields
