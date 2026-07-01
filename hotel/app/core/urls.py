from django.urls import include, path

urlpatterns = [
    path("", include("app.core.bookings.urls")),
    path("", include("app.core.logs.urls")),
    path("", include("app.core.requests.urls")),
]
