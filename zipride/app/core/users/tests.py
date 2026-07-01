from app.mixins.tests import ModelTest

from .factories import UserFactory, LoginTokenFactory
from .models import User, LoginToken


class TestUser(ModelTest):
    model = User
    factory = UserFactory
    endpoint = "users"
    PERMISSION_TYPE = ModelTest.PERMISSION_TYPES.OWNER
    SUPERUSER_FIELD = "is_account_manager"
    CAN_CREATE = False
    CAN_DELETE = False
    OBJS_LIST = 1
    SERIALIZER_READ_ONLY_FIELDS = ("permyt_user_id", "is_account_manager")
    SERIALIZER_IMMUTABLE_FIELDS = ("permyt_user_id",)


class TestLoginToken(ModelTest):
    model = LoginToken
    factory = LoginTokenFactory
    PERMISSION_TYPE = ModelTest.PERMISSION_TYPES.SUPERUSER
    SUPERUSER_FIELD = "is_account_manager"
    ENABLE_VIEWS = False
