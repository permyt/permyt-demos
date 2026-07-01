from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from app.core.bookings.models import Booking

from .models import Log


class LogClearView(APIView):
    """Delete log entries for the current session's booking."""

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    def post(self, request):
        if not request.session.session_key:
            return Response({"cleared": False})
        booking = Booking.objects.filter(session_key=request.session.session_key).first()
        if not booking:
            return Response({"cleared": False})
        Log.objects.filter(booking=booking).delete()
        return Response({"cleared": True})
