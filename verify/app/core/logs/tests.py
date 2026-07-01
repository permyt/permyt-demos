from app.core.logs.factories import LogFactory
from app.core.logs.models import Log
from app.mixins.tests import ModelTest


class TestLog(ModelTest):
    model = Log
    factory = LogFactory
    endpoint = None
    PERMISSION_TYPE = ModelTest.PERMISSION_TYPES.SUPERUSER
    ENABLE_VIEWS = False
