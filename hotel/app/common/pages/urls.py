from django.urls import path
from django.views.generic import RedirectView

from .views import ConfirmationView, HotelView, NewBookingView

urlpatterns = [
    path("", HotelView.as_view(), name="index"),
    path("confirmation/", ConfirmationView.as_view(), name="confirmation"),
    path("new/", NewBookingView.as_view(), name="new_booking"),
    path("favicon.ico", RedirectView.as_view(url="/static/logos/logo-dark.svg")),
]
