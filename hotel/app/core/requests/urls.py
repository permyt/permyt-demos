from django.urls import path, re_path

from .views import PermytInboundView

urlpatterns = [
    re_path(r"^permyt/inbound/?$", PermytInboundView.as_view(), name="permyt-inbound"),
]
