from django.urls import path, re_path

from .views import PermytInboundView, ProfileView, ScopeCallView

urlpatterns = [
    re_path(r"^permyt/inbound/?$", PermytInboundView.as_view(), name="permyt-inbound"),
    # ``profile/`` MUST come before the ``<field>/<action>/`` catchall — Django
    # path resolution is order-sensitive and the catchall would otherwise
    # swallow any future ``/rest/profile/<x>/`` route.
    path("profile/", ProfileView.as_view(), name="profile"),
    path("<str:field_name>/<str:action>/", ScopeCallView.as_view(), name="scope-call"),
]
