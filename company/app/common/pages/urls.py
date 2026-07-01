from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import RedirectView

from .views import IndexView

urlpatterns = [
    # Self-service only: each company sees its OWN data via login/dashboard.
    # No operator registry — that would expose every company to any visitor.
    path("", IndexView.as_view(), name="index"),
    path("logout/", LogoutView.as_view(next_page="/"), name="logout"),
    path("favicon.ico", RedirectView.as_view(url="/static/logos/logo-dark.svg")),
]
