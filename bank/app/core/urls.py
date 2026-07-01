from django.urls import include, path

from app.core.logs.views import LogClearView

urlpatterns = [
    path("", include("app.core.users.urls")),
    path("logs/clear/", LogClearView.as_view(), name="logs-clear"),
    # Requests URLs last — ScopeCallView's catch-all <field>/<action>/ pattern
    # would shadow other two-segment routes (e.g. users/<id>/) if placed earlier.
    path("", include("app.core.requests.urls")),
]
