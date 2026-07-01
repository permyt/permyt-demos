from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from app.core.verifications.models import Verification

from .models import Log


class LogClearView(APIView):
    """Delete log entries for the current session's verification."""

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    def post(self, request):
        if not request.session.session_key:
            return Response({"cleared": False})
        verification = Verification.objects.filter(session_key=request.session.session_key).first()
        if not verification:
            return Response({"cleared": False})
        Log.objects.filter(verification=verification).delete()
        return Response({"cleared": True})
