from django.contrib.sessions.models import Session


def login_session(*, session: Session, user):
    """Login a user to a specific session (used for QR code login)"""

    session_data = session.get_decoded()
    session_data["_auth_user_id"] = str(user.pk)
    session_data["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
    session_data["_auth_user_hash"] = user.get_session_auth_hash()
    session.session_data = Session.objects.encode(session_data)
    session.save()
