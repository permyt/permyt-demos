from app.mixins.tests import ModelTest
from app.core.requests.factories import NonceFactory
from app.core.requests.models import Nonce


class TestNonce(ModelTest):
    model = Nonce
    factory = NonceFactory
    endpoint = None
    PERMISSION_TYPE = ModelTest.PERMISSION_TYPES.SUPERUSER
    ENABLE_VIEWS = False
