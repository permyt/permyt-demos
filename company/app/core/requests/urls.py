from django.urls import path, re_path

from .views import (
    CompanyProfileView,
    OnboardingRetryView,
    OnboardingStatusView,
    PermytInboundView,
    ScopeCallView,
)

urlpatterns = [
    re_path(r"^permyt/inbound/?$", PermytInboundView.as_view(), name="permyt-inbound"),
    # These UI routes MUST precede the ``<field>/<action>/`` catchall.
    path("profile/", CompanyProfileView.as_view(), name="profile"),
    path("onboarding/status/", OnboardingStatusView.as_view(), name="onboarding-status"),
    path("onboarding/retry/", OnboardingRetryView.as_view(), name="onboarding-retry"),
    path("<str:field_name>/<str:action>/", ScopeCallView.as_view(), name="scope-call"),
]
