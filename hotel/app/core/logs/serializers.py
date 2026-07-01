from app.mixins.serializers import AppModelSerializer

from .models import Log


class LogSerializer(AppModelSerializer):

    class Meta:
        model = Log
        fields = ("booking", "action", "success", "data", "permyt_request_id", "updated_at")
        read_only_fields = fields
