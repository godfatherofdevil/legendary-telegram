from collections.abc import Iterable
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import UserSession
from apps.accounts.services import hash_session_key
from apps.common.enums import FriendRequestStatus, PresenceState
from apps.presence.models import UserPresenceConnection
from apps.social.models import FriendRequest

User = get_user_model()

AFK_TIMEOUT = timedelta(minutes=1)


def _presence_from_connections(*, connections: list[UserPresenceConnection], now):
    if not connections:
        return PresenceState.OFFLINE

    active_cutoff = now - AFK_TIMEOUT
    if any(
        connection.is_active or connection.last_interaction_at > active_cutoff
        for connection in connections
    ):
        return PresenceState.ONLINE
    return PresenceState.AFK


@transaction.atomic
def recompute_user_presence(*, user: User, now=None) -> tuple[str, timezone.datetime]:
    current_time = now or timezone.now()
    open_connections = list(
        UserPresenceConnection.objects.select_for_update()
        .filter(user=user, disconnected_at__isnull=True)
        .order_by("-last_interaction_at", "-last_heartbeat_at", "-connected_at", "-id")
    )
    computed_presence = _presence_from_connections(connections=open_connections, now=current_time)
    last_changed_at = user.presence_last_changed_at

    if computed_presence != user.presence_state:
        user.presence_state = computed_presence
        user.presence_last_changed_at = current_time
        user.save(update_fields=["presence_state", "presence_last_changed_at", "updated_at"])
        last_changed_at = current_time

    return computed_presence, last_changed_at


def get_presence_snapshots(*, user_ids: Iterable[str]) -> list[dict[str, str]]:
    requested_ids = [str(user_id) for user_id in user_ids]
    if not requested_ids:
        return []

    users = {
        str(user.id): user
        for user in User.objects.filter(id__in=requested_ids).order_by("id")
    }

    payload = []
    for user_id in requested_ids:
        user = users.get(user_id)
        if user is None:
            continue
        presence, last_changed_at = recompute_user_presence(user=user)
        payload.append(
            {
                "user_id": str(user.id),
                "presence": presence,
                "last_changed_at": last_changed_at.isoformat().replace("+00:00", "Z"),
            }
        )
    return payload


def get_notification_summary(*, user: User) -> dict:
    from apps.chat.services import list_dialog_rows, list_joined_room_rows

    memberships, room_unread_counts = list_joined_room_rows(user=user)
    dialogs, dialog_unread_counts, _last_messages = list_dialog_rows(user=user)

    rooms = [
        {"room_id": str(membership.room_id), "unread_count": room_unread_counts[membership.room_id]}
        for membership in memberships
        if room_unread_counts[membership.room_id] > 0
    ]
    dialogs_payload = [
        {"dialog_id": str(dialog.id), "unread_count": dialog_unread_counts[dialog.id]}
        for dialog in dialogs
        if dialog_unread_counts[dialog.id] > 0
    ]
    incoming_friend_requests = FriendRequest.objects.filter(
        to_user=user,
        status=FriendRequestStatus.PENDING,
    ).count()

    return {
        "rooms": rooms,
        "dialogs": dialogs_payload,
        "incoming_friend_requests": incoming_friend_requests,
    }


def serialize_presence_update(*, user: User) -> dict:
    return {
        "user_id": str(user.id),
        "presence": user.presence_state,
        "last_changed_at": user.presence_last_changed_at.isoformat().replace("+00:00", "Z"),
    }


def _get_session_record(*, session_key: str | None) -> UserSession | None:
    if not session_key:
        return None
    return UserSession.objects.filter(
        session_key_hash=hash_session_key(session_key),
        is_currently_valid=True,
    ).first()


@transaction.atomic
def upsert_presence_connection(
    *,
    user: User,
    connection_key: str,
    session_key: str | None,
    tab_id: str | None = None,
    is_active: bool = True,
    last_interaction_at=None,
    now=None,
) -> dict | None:
    current_time = now or timezone.now()
    previous_presence = user.presence_state
    defaults = {
        "user": user,
        "session": _get_session_record(session_key=session_key),
        "tab_id": tab_id or connection_key,
        "is_active": is_active,
        "last_interaction_at": last_interaction_at or current_time,
        "last_heartbeat_at": current_time,
        "connected_at": current_time,
        "disconnected_at": None,
    }
    UserPresenceConnection.objects.update_or_create(
        connection_key=connection_key,
        defaults=defaults,
    )
    recompute_user_presence(user=user, now=current_time)
    user.refresh_from_db(fields=["presence_state", "presence_last_changed_at"])
    if user.presence_state == previous_presence:
        return None
    return serialize_presence_update(user=user)


@transaction.atomic
def close_presence_connection(*, user: User, connection_key: str, now=None) -> dict | None:
    current_time = now or timezone.now()
    previous_presence = user.presence_state
    UserPresenceConnection.objects.filter(
        connection_key=connection_key,
        user=user,
        disconnected_at__isnull=True,
    ).update(
        disconnected_at=current_time,
        updated_at=current_time,
    )
    recompute_user_presence(user=user, now=current_time)
    user.refresh_from_db(fields=["presence_state", "presence_last_changed_at"])
    if user.presence_state == previous_presence:
        return None
    return serialize_presence_update(user=user)
