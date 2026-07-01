from django.urls import path, re_path

from .views import (
    MovementsView,
    OnboardingRetryView,
    OnboardingStatusView,
    PermytInboundView,
    ProfileView,
    ScopeCallView,
)

urlpatterns = [
    re_path(r"^permyt/inbound/?$", PermytInboundView.as_view(), name="permyt-inbound"),
    # These UI routes MUST come before the ``<field>/<action>/`` catchall —
    # Django path resolution is order-sensitive and the catchall would
    # otherwise swallow them.
    path("profile/", ProfileView.as_view(), name="profile"),
    path("movements/", MovementsView.as_view(), name="movements"),
    path("onboarding/status/", OnboardingStatusView.as_view(), name="onboarding-status"),
    path("onboarding/retry/", OnboardingRetryView.as_view(), name="onboarding-retry"),
    path("<str:field_name>/<str:action>/", ScopeCallView.as_view(), name="scope-call"),
]
