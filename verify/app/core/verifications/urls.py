from django.urls import path

from .views import RefreshQrView, ResetVerificationView

urlpatterns = [
    path("verification/qr/", RefreshQrView.as_view(), name="verification-qr"),
    path("verification/reset/", ResetVerificationView.as_view(), name="verification-reset"),
]
