import json

from django.contrib.sessions.models import Session
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from app.core.logs.models import Log
from app.core.requests.client import PermytClient
from app.core.requests.views import _serialize_profile, _serialize_shareholders
from app.core.users.models import (
    PROFILE_BUSINESS,
    PROFILE_PERSON,
    BusinessProfile,
    LoginToken,
    Shareholder,
    User,
)
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
                "title": "Gov.ID — National Digital Identity",
            },
        )

    def _dashboard(self, request):
        user = request.user
        profile = _serialize_profile(user)
        logs = (
            Log.objects.get_queryset()
            .filter(user=user, permyt_request_id__isnull=False)
            .order_by("-updated_at")[:50]
        )

        return render(
            request,
            "pages/dashboard/index.html",
            {
                "title": "Gov.ID — National Digital Identity",
                "profile": profile,
                "is_business": user.is_business,
                "business": getattr(user, "business_profile", None),
                "shareholders": _serialize_shareholders(user),
                "logs": logs,
            },
        )


class RegisterView(View):
    """Operator console — register persons and businesses, then issue a
    connect QR per record so the holder can link it to their PERMYT profile."""

    def get(self, request):
        records = User.objects.get_queryset().order_by("-created_at")[:50]
        return render(
            request,
            "pages/register/index.html",
            {
                "title": "Registry Console — Gov.ID",
                "records": [self._summary(r) for r in records],
            },
        )

    def post(self, request):
        profile_type = request.POST.get("profile_type", PROFILE_PERSON)
        if profile_type == PROFILE_BUSINESS:
            record = self._create_business(request)
        else:
            record = self._create_person(request)
        return redirect(reverse("register-detail", args=[record.id]))

    # -- creation helpers --------------------------------------------------
    def _create_person(self, request):
        p = request.POST
        user = User.objects.create(
            username=f"person-{p.get('email') or p.get('full_name') or User.objects.count()}",
            profile_type=PROFILE_PERSON,
            full_name=p.get("full_name", ""),
            birthdate=p.get("birthdate") or None,
            address=p.get("address", ""),
            country=p.get("country", ""),
            vat=p.get("vat", ""),
            phone=p.get("phone", ""),
            email=p.get("email") or None,
            tax_id=p.get("tax_id", ""),
        )
        user.seed_profile()
        return user

    def _create_business(self, request):
        p = request.POST
        user = User.objects.create(
            username=f"business-{p.get('registration_number') or User.objects.count()}",
            profile_type=PROFILE_BUSINESS,
        )
        biz = BusinessProfile.objects.create(
            user=user,
            legal_name=p.get("legal_name", ""),
            registration_number=p.get("registration_number", ""),
            tax_id=p.get("tax_id", ""),
            incorporation_date=p.get("incorporation_date") or None,
            registered_address=p.get("registered_address", ""),
            country=p.get("country", ""),
            structure=p.get("structure", "private_corporation"),
            mcc=p.get("mcc", ""),
            website=p.get("website", ""),
        )
        for row in self._parse_shareholders(p.get("shareholders_json", "")):
            Shareholder.objects.create(
                business=biz,
                first_name=row.get("first_name", ""),
                last_name=row.get("last_name", ""),
                birthdate=row.get("birthdate") or None,
                address=row.get("address", ""),
                country=row.get("country", ""),
                id_number=row.get("id_number", ""),
                ownership_percent=row.get("ownership_percent") or 0,
                title=row.get("title", ""),
                is_representative=bool(row.get("is_representative")),
                is_director=bool(row.get("is_director")),
            )
        user.seed_business()  # fill any blanks; ensures >=1 owner
        return user

    @staticmethod
    def _parse_shareholders(raw: str) -> list[dict]:
        try:
            data = json.loads(raw or "[]")
            return data if isinstance(data, list) else []
        except (ValueError, TypeError):
            return []

    @staticmethod
    def _summary(record: User) -> dict:
        if record.is_business:
            biz = getattr(record, "business_profile", None)
            name = (biz.legal_name if biz else "") or "Unnamed company"
        else:
            name = record.full_name or "Unnamed person"
        return {
            "id": str(record.id),
            "name": name,
            "type": record.profile_type,
            "connected": record.is_connected,
        }


class RegisterDetailView(View):
    """Show a single registered record with a connect QR + live status."""

    def get(self, request, record_id):
        try:
            record = User.objects.get_queryset().get(id=record_id)
        except User.DoesNotExist:
            return redirect(reverse("register"))

        client = PermytClient()
        connect = client.generate_connect_token(system_user_id=str(record.id))
        LoginToken.objects.create(token=connect["token"], user=record)
        qr_svg = generate_qr_svg(json.dumps(connect["data"]))

        return render(
            request,
            "pages/register/detail.html",
            {
                "title": "Connect Record — Gov.ID",
                "record_id": str(record.id),
                "summary": RegisterView._summary(record),
                "details": self._details(record),
                "qr_svg": qr_svg,
                "connected": record.is_connected,
            },
        )

    @staticmethod
    def _details(record: User) -> list[dict]:
        if not record.is_business:
            return [
                {"label": "Full name", "value": record.full_name},
                {"label": "Birthdate", "value": record.birthdate},
                {"label": "Country", "value": record.country},
                {"label": "Tax ID / NIF", "value": record.tax_id},
                {"label": "Passport no.", "value": record.passport_number},
                {"label": "Citizen card no.", "value": record.citizen_card_number},
            ]
        biz = getattr(record, "business_profile", None)
        if not biz:
            return []
        rows = [
            {"label": "Legal name", "value": biz.legal_name},
            {"label": "Registration no.", "value": biz.registration_number},
            {"label": "Tax ID", "value": biz.tax_id},
            {"label": "Country", "value": biz.country},
            {"label": "MCC", "value": biz.mcc},
        ]
        for s in biz.shareholders.all():
            rows.append(
                {
                    "label": "Owner",
                    "value": f"{s.first_name} {s.last_name} — {s.ownership_percent}%",
                }
            )
        return rows
