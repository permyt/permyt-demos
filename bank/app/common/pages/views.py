import json

from django.contrib.sessions.models import Session
from django.shortcuts import render
from django.views import View

from app.core.requests.client import PermytClient
from app.core.requests.views import _list_movements_for, _serialize_profile
from app.core.users.models import PROFILE_BUSINESS, PROFILE_PERSON, LoginToken
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
        if not request.session.session_key:
            request.session.create()

        session = Session.objects.get(session_key=request.session.session_key)

        profile_type = request.GET.get("as")
        if profile_type not in (PROFILE_PERSON, PROFILE_BUSINESS):
            profile_type = PROFILE_PERSON

        client = PermytClient()
        connect = client.generate_connect_token(system_user_id=None)

        token_obj = LoginToken.objects.create(
            token=connect["token"],
            session=session,
            profile_type=profile_type,
        )

        qr_svg = generate_qr_svg(json.dumps(connect["data"]))

        return render(
            request,
            "pages/login/index.html",
            {
                "login_id": str(token_obj.id),
                "qr_svg": qr_svg,
                "profile_type": profile_type,
                "title": "Meridian — PERMYT",
            },
        )

    def _dashboard(self, request):
        user = request.user

        if not user.onboarding_complete:
            return render(
                request,
                "pages/onboarding/index.html",
                {"title": "Opening your account — Meridian"},
            )

        profile = _serialize_profile(user)
        movements = _list_movements_for(user, limit=20)

        return render(
            request,
            "pages/dashboard/index.html",
            {
                "title": "Bank — PERMYT",
                "profile": profile,
                "movements": movements,
            },
        )
