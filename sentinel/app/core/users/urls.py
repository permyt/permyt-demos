from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    UserViewSet,
    LoginStatusView,
    RegistrationStatusView,
    RefreshLoginQrView,
    RefreshRegistrationQrView,
)

router = SimpleRouter()
router.register("users", UserViewSet, basename="users")

urlpatterns = [
    path("login/status/", LoginStatusView.as_view(), name="login-status"),
    path("login/qr/refresh/", RefreshLoginQrView.as_view(), name="login-qr-refresh"),
    path("registration/status/", RegistrationStatusView.as_view(), name="registration-status"),
    path(
        "registration/qr/refresh/",
        RefreshRegistrationQrView.as_view(),
        name="registration-qr-refresh",
    ),
] + router.urls
