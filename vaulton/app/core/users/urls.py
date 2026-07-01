from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import UserViewSet, LoginStatusView, RefreshLoginQrView

router = SimpleRouter()
router.register("users", UserViewSet, basename="users")

urlpatterns = [
    path("login/status/", LoginStatusView.as_view(), name="login-status"),
    path("login/qr/refresh/", RefreshLoginQrView.as_view(), name="login-qr-refresh"),
] + router.urls
