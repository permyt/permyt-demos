from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Log


class LogClearView(APIView):
    """Delete all log entries belonging to the current user."""

    permission_classes = [IsAuthenticated]
    http_method_names = ["post"]

    def post(self, request):
        Log.objects.filter(user=request.user).delete()
        return Response({"cleared": True})
