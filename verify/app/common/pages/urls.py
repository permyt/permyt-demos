from django.urls import path
from django.views.generic import RedirectView

from .views import VerifyView

urlpatterns = [
    path("", VerifyView.as_view(), name="index"),
    path("favicon.ico", RedirectView.as_view(url="/static/logos/logo-dark.svg")),
]
