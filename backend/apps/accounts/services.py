import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import PasswordResetToken, UserSession
from ..attachments.models import Attachment
from ..audit.models import ModerationEvent
from ..chat.models import Room
from ..common.enums import ModerationActionType

logger = logging.getLogger(__name__)
User = get_user_model()

PASSWORD_RESET_TOKEN_BYTES = 32
PASSWORD_RESET_TOKEN_TTL = timedelta(hours=1)


def hash_session_key(session_key: str) -> str:
    return hashlib.sha256(session_key.encode("utf-8")).hexdigest()


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def get_client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def get_user_agent(request) -> str | None:
    user_agent = request.META.get("HTTP_USER_AGENT", "").strip()
    return user_agent or None


def compute_session_expiry(request) -> timezone.datetime:
    return timezone.now() + timedelta(seconds=request.session.get_expiry_age())


def sync_session_record(
    request,
    *,
    user=None,
    previous_session_key: str | None = None,
) -> UserSession | None:
    session_key = request.session.session_key
    if not session_key:
        request.session.save()
        session_key = request.session.session_key
    if not session_key:
        return None

    session_user = user or getattr(request, "user", None)
    if not session_user or not session_user.is_authenticated:
        return None

    now = timezone.now()
    session_hash = hash_session_key(session_key)
    defaults = {
        "user": session_user,
        "ip_address": get_client_ip(request),
        "user_agent": get_user_agent(request),
        "is_currently_valid": True,
        "last_seen_at": now,
        "expires_at": compute_session_expiry(request),
        "revoked_at": None,
    }
    session_record, _ = UserSession.objects.update_or_create(
        session_key_hash=session_hash,
        defaults=defaults,
    )

    if previous_session_key and previous_session_key != session_key:
        UserSession.objects.filter(
            session_key_hash=hash_session_key(previous_session_key),
            user=session_user,
            is_currently_valid=True,
        ).update(
            is_currently_valid=False,
            revoked_at=now,
        )

    return session_record


def authenticate_user(*, email: str, password: str, request):
    user = authenticate(request=request, email=email, password=password)
    if user is None:
        logger.warning("Authentication failed for email=%s", email)
    return user


@transaction.atomic
def create_authenticated_session(*, request, user, remember_me: bool) -> UserSession | None:
    login(request, user)
    if remember_me:
        request.session.set_expiry(settings.SESSION_COOKIE_AGE)
    else:
        request.session.set_expiry(0)
    request.session.save()
    return sync_session_record(request, user=user)


def revoke_session_record(session_record: UserSession, *, actor=None) -> None:
    now = timezone.now()
    if session_record.is_currently_valid:
        session_record.is_currently_valid = False
        session_record.revoked_at = now
        session_record.save(update_fields=["is_currently_valid", "revoked_at"])

    session_key = find_session_key_by_hash(session_record.session_key_hash)
    if session_key:
        Session.objects.filter(session_key=session_key).delete()

    ModerationEvent.objects.create(
        action_type=ModerationActionType.SESSION_REVOKED,
        actor_user=actor,
        target_user=session_record.user,
        session=session_record,
        metadata_json={"session_id": str(session_record.id)},
    )
    logger.info(
        "Session revoked session_id=%s user_id=%s",
        session_record.id,
        session_record.user_id,
    )


def revoke_current_session(request) -> None:
    session_key = request.session.session_key
    if session_key:
        UserSession.objects.filter(
            session_key_hash=hash_session_key(session_key),
            user=request.user,
            is_currently_valid=True,
        ).update(
            is_currently_valid=False,
            revoked_at=timezone.now(),
        )
    logout(request)


def find_session_key_by_hash(session_key_hash: str) -> str | None:
    active_sessions = Session.objects.filter(expire_date__gt=timezone.now()).only("session_key")
    for session in active_sessions.iterator():
        if hash_session_key(session.session_key) == session_key_hash:
            return session.session_key
    return None


def create_password_reset_token(*, user) -> str:
    raw_token = secrets.token_urlsafe(PASSWORD_RESET_TOKEN_BYTES)
    PasswordResetToken.objects.create(
        user=user,
        token_hash=hash_reset_token(raw_token),
        expires_at=timezone.now() + PASSWORD_RESET_TOKEN_TTL,
    )
    return raw_token


def issue_password_reset(*, user) -> None:
    raw_token = create_password_reset_token(user=user)
    send_mail(
        subject="Chat App password reset",
        message=f"Use this token to reset your password: {raw_token}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    logger.info("Password reset issued user_id=%s", user.id)


@transaction.atomic
def reset_password(*, raw_token: str, new_password: str) -> User:
    now = timezone.now()
    token = (
        PasswordResetToken.objects.select_for_update()
        .select_related("user")
        .filter(token_hash=hash_reset_token(raw_token))
        .first()
    )
    if token is None or token.used_at is not None or token.expires_at <= now:
        raise ValueError("invalid_token")

    user = token.user
    user.set_password(new_password)
    user.save(update_fields=["password"])
    token.used_at = now
    token.save(update_fields=["used_at"])
    return user


@transaction.atomic
def change_password(*, request, current_password: str, new_password: str) -> None:
    user = request.user
    if not user.check_password(current_password):
        logger.warning(
            "Password change rejected for user_id=%s due to invalid current password",
            user.id,
        )
        raise PermissionError("invalid_current_password")

    previous_session_key = request.session.session_key
    user.set_password(new_password)
    user.save(update_fields=["password"])
    update_session_auth_hash(request, user)
    sync_session_record(request, user=user, previous_session_key=previous_session_key)
    logger.info("Password changed user_id=%s", user.id)


@transaction.atomic
def delete_account(*, user) -> None:
    owned_room_ids = list(user.owned_rooms.values_list("id", flat=True))
    room_attachment_ids = list(
        Attachment.objects.filter(room_message_bindings__room_message__room_id__in=owned_room_ids)
        .values_list("id", flat=True)
        .distinct()
    )
    user_attachment_ids = list(
        Attachment.objects.filter(uploaded_by_user=user).values_list("id", flat=True)
    )

    if room_attachment_ids:
        Attachment.objects.filter(id__in=room_attachment_ids).delete()
    if user_attachment_ids:
        Attachment.objects.filter(id__in=user_attachment_ids).delete()

    Room.objects.filter(id__in=owned_room_ids).delete()

    active_sessions = UserSession.objects.select_for_update().filter(
        user=user,
        is_currently_valid=True,
    )
    for session_record in active_sessions:
        revoke_session_record(session_record, actor=user)

    user.delete()
    logger.info("Account deleted user_id=%s", user.id)


def cleanup_expired_session_records() -> None:
    now = timezone.now()
    UserSession.objects.filter(Q(expires_at__lte=now) | Q(revoked_at__isnull=False)).update(
        is_currently_valid=False
    )
