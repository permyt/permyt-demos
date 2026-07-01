from django.urls import path

from .views import LogClearView

urlpatterns = [
    path("logs/clear/", LogClearView.as_view(), name="logs-clear"),
]
