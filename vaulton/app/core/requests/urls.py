from django.urls import path, re_path

from .views import OnboardingStateView, PermytInboundView, SubmitRequestView

urlpatterns = [
    re_path(r"^permyt/inbound/?$", PermytInboundView.as_view(), name="permyt-inbound"),
    path("requests/submit/", SubmitRequestView.as_view(), name="request-submit"),
    path("onboarding/state/", OnboardingStateView.as_view(), name="onboarding-state"),
]
