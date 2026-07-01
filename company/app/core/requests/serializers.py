from app.mixins.serializers import AppModelSerializer
from app.core.requests.models import Nonce


class NonceSerializer(AppModelSerializer):
    class Meta:
        model = Nonce
        fields = ("value",)
        read_only_fields = fields
