import json

from django.contrib.sessions.models import Session
from django.shortcuts import render
from django.views import View

from app.core.requests.client import PermytClient
from app.core.requests.views import _serialize_kb
from app.core.users.models import LoginToken
from app.utils.qr import generate_qr_svg


class IndexView(View):
    """Single entry point at /. Dispatches to the product landing + QR sign-in
    (unauthenticated) or the company knowledge-base editor (authenticated)."""

    def get(self, request):
        if not request.user.is_authenticated:
            return self._login(request)
        return self._dashboard(request)

    def _login(self, request):
        if not request.session.session_key:
            request.session.create()

        session = Session.objects.get(session_key=request.session.session_key)

        client = PermytClient()
        connect = client.generate_connect_token(system_user_id=None)
        token_obj = LoginToken.objects.create(token=connect["token"], session=session)
        qr_svg = generate_qr_svg(json.dumps(connect["data"]))

        return render(
            request,
            "pages/login/index.html",
            {
                "login_id": str(token_obj.id),
                "qr_svg": qr_svg,
                "title": "Atlas — The Company Agent",
            },
        )

    def _dashboard(self, request):
        if not request.user.onboarding_complete:
            return render(
                request,
                "pages/onboarding/index.html",
                {"title": "Fetching your company details — Atlas"},
            )

        kb = _serialize_kb(request.user)
        return render(
            request,
            "pages/dashboard/index.html",
            {
                "title": "Atlas — Company knowledge base",
                "kb": kb,
                "company_name": kb.get("name") or "Your company",
            },
        )
