import json

from django.contrib.sessions.models import Session
from django.shortcuts import render
from django.views import View

from app.core.logs.models import Log
from app.core.requests.client import PermytClient
from app.core.users.models import LoginToken
from app.utils.qr import generate_qr_svg


class IndexView(View):
    """
    Single entry point at /.
    Dispatches to login or dashboard based on auth state.
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return self._login(request)
        return self._dashboard(request)

    def _login(self, request):
        """Render the QR-code login page.

        Generates a connect token via ``PermytClient.generate_connect_token()``,
        creates a ``LoginToken`` bound to the current session, and passes
        the QR payload to the template. When the user scans the code, the
        broker calls back to ``PermytInboundView`` with ``action=user_connect``.
        """
        if not request.session.session_key:
            request.session.create()

        session = Session.objects.get(session_key=request.session.session_key)

        client = PermytClient()
        connect = client.generate_connect_token(system_user_id=None)

        token_obj = LoginToken.objects.create(
            token=connect["token"],
            session=session,
        )

        qr_svg = generate_qr_svg(json.dumps(connect["data"]))

        return render(
            request,
            "pages/login/index.html",
            {
                "login_id": str(token_obj.id),
                "qr_svg": qr_svg,
                "title": "Requester — PERMYT",
            },
        )

    def _dashboard(self, request):
        logs = Log.objects.filter(user=request.user, permyt_request_id__isnull=False).order_by(
            "-updated_at"
        )[:50]

        return render(
            request,
            "pages/dashboard/index.html",
            {
                "title": "Dashboard — PERMYT",
                "logs": logs,
                "permyt_user_id": (
                    str(request.user.permyt_user_id) if request.user.permyt_user_id else ""
                ),
            },
        )
