from django.urls import path

from .views import PayView, RefreshQrView, UpdateNightsView

urlpatterns = [
    path("booking/nights/", UpdateNightsView.as_view(), name="booking-nights"),
    path("booking/pay/", PayView.as_view(), name="booking-pay"),
    path("booking/qr/", RefreshQrView.as_view(), name="booking-qr"),
]
