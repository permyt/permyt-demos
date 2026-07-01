from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import RedirectView

from .views import IndexView, RegisterDetailView, RegisterView

urlpatterns = [
    path("", IndexView.as_view(), name="index"),
    path("register/", RegisterView.as_view(), name="register"),
    path("register/<uuid:record_id>/", RegisterDetailView.as_view(), name="register-detail"),
    path("logout/", LogoutView.as_view(next_page="/"), name="logout"),
    path("favicon.ico", RedirectView.as_view(url="/static/logos/logo-dark.svg")),
]
