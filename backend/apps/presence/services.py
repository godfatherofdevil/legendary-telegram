from collections.abc import Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from ..accounts.models import UserSession
from ..accounts.services import hash_session_key
from ..chat.migration.parity_checks import log_presence_parity_mismatches
from ..chat.realtime.connection_registry import (
    list_connections as list_redis_connections,
)
from ..chat.realtime.connection_registry import (
    register_connection,
    unregister_connection,
    write_presence_snapshot,
)
from ..chat.realtime.presence import compute_presence, serialize_timestamp
from ..common.enums import FriendRequestStatus
from .models import UserPresenceConnection
from ..social.models import FriendRequest

User = get_user_model()


def _presence_from_connections(*, connections: list[UserPresenceConnection], now):
    from ..chat.realtime.presence import PresenceConnectionSnapshot

    snapshots = [
        PresenceConnectionSnapshot(
            connection_key=connection.connection_key,
            user_id=str(connection.user_id),
            session_id=str(connection.session_id) if connection.session_id else None,
            tab_id=connection.tab_id,
            is_active=connection.is_active,
            last_interaction_at=connection.last_interaction_at,
            last_heartbeat_at=connection.last_heartbeat_at,
            connected_at=connection.connected_at,
        )
        for connection in connections
    ]
    return compute_presence(connections=snapshots, now=now)


def _redis_presence_enabled() -> bool:
    return settings.CHAT_MIGRATION_FLAGS.get("redis_presence_enabled", False)


def _legacy_sql_presence_enabled() -> bool:
    return settings.CHAT_MIGRATION_FLAGS.get("legacy_sql_presence_enabled", False)


def _parity_verification_enabled() -> bool:
    return settings.CHAT_MIGRATION_FLAGS.get("parity_verification_enabled", False)


def _locked_user(*, user_id):
    return User.objects.select_for_update().get(pk=user_id)


@transaction.atomic
def recompute_user_presence(*, user: User, now=None) -> tuple[str, timezone.datetime]:
    current_time = now or timezone.now()
    if _redis_presence_enabled():
        locked_user = _locked_user(user_id=user.id)
        connections = list_redis_connections(user_id=locked_user.id)
        computed_presence = compute_presence(connections=connections, now=current_time)
        last_changed_at = locked_user.presence_last_changed_at
        if computed_presence != locked_user.presence_state:
            locked_user.presence_state = computed_presence
            locked_user.presence_last_changed_at = current_time
            locked_user.save(
                update_fields=["presence_state", "presence_last_changed_at", "updated_at"]
            )
            last_changed_at = current_time
        write_presence_snapshot(
            user_id=locked_user.id,
            presence=locked_user.presence_state,
            last_changed_at=last_changed_at,
        )
        user.presence_state = locked_user.presence_state
        user.presence_last_changed_at = last_changed_at
        return locked_user.presence_state, last_changed_at

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
                "last_changed_at": serialize_timestamp(last_changed_at),
            }
        )
    return payload


def get_notification_summary(*, user: User) -> dict:
    from ..chat.services import list_dialog_rows, list_joined_room_rows

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
        "last_changed_at": serialize_timestamp(user.presence_last_changed_at),
    }


def _get_session_record(*, session_key: str | None) -> UserSession | None:
    if not session_key:
        return None
    return UserSession.objects.filter(
        session_key_hash=hash_session_key(session_key),
        is_currently_valid=True,
    ).first()


def _legacy_upsert_presence_connection(
    *,
    user: User,
    connection_key: str,
    session_key: str | None,
    tab_id: str | None = None,
    is_active: bool = True,
    last_interaction_at=None,
    now=None,
) -> None:
    current_time = now or timezone.now()
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


def _legacy_close_presence_connection(*, user: User, connection_key: str, now=None) -> None:
    current_time = now or timezone.now()
    UserPresenceConnection.objects.filter(
        connection_key=connection_key,
        user=user,
        disconnected_at__isnull=True,
    ).update(
        disconnected_at=current_time,
        updated_at=current_time,
    )


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
    if _redis_presence_enabled():
        session_record = _get_session_record(session_key=session_key)
        if _legacy_sql_presence_enabled():
            _legacy_upsert_presence_connection(
                user=user,
                connection_key=connection_key,
                session_key=session_key,
                tab_id=tab_id,
                is_active=is_active,
                last_interaction_at=last_interaction_at,
                now=current_time,
            )

        register_connection(
            user_id=user.id,
            connection_key=connection_key,
            session_id=str(session_record.id) if session_record else None,
            tab_id=tab_id or connection_key,
            is_active=is_active,
            last_interaction_at=last_interaction_at or current_time,
            now=current_time,
        )
        locked_user = _locked_user(user_id=user.id)
        previous_presence = locked_user.presence_state
        presence, last_changed_at = recompute_user_presence(user=locked_user, now=current_time)
        if _legacy_sql_presence_enabled() and _parity_verification_enabled():
            log_presence_parity_mismatches(
                user=locked_user,
                redis_connections=list_redis_connections(user_id=locked_user.id),
                now=current_time,
            )
        user.presence_state = presence
        user.presence_last_changed_at = last_changed_at
        if presence == previous_presence:
            return None
        return serialize_presence_update(user=locked_user)

    previous_presence = user.presence_state
    _legacy_upsert_presence_connection(
        user=user,
        connection_key=connection_key,
        session_key=session_key,
        tab_id=tab_id,
        is_active=is_active,
        last_interaction_at=last_interaction_at,
        now=current_time,
    )
    recompute_user_presence(user=user, now=current_time)
    user.refresh_from_db(fields=["presence_state", "presence_last_changed_at"])
    if user.presence_state == previous_presence:
        return None
    return serialize_presence_update(user=user)


@transaction.atomic
def close_presence_connection(*, user: User, connection_key: str, now=None) -> dict | None:
    current_time = now or timezone.now()
    if _redis_presence_enabled():
        if _legacy_sql_presence_enabled():
            _legacy_close_presence_connection(
                user=user,
                connection_key=connection_key,
                now=current_time,
            )
        unregister_connection(user_id=user.id, connection_key=connection_key)
        locked_user = _locked_user(user_id=user.id)
        previous_presence = locked_user.presence_state
        presence, last_changed_at = recompute_user_presence(user=locked_user, now=current_time)
        if _legacy_sql_presence_enabled() and _parity_verification_enabled():
            log_presence_parity_mismatches(
                user=locked_user,
                redis_connections=list_redis_connections(user_id=locked_user.id),
                now=current_time,
            )
        user.presence_state = presence
        user.presence_last_changed_at = last_changed_at
        if presence == previous_presence:
            return None
        return serialize_presence_update(user=locked_user)

    previous_presence = user.presence_state
    _legacy_close_presence_connection(user=user, connection_key=connection_key, now=current_time)
    recompute_user_presence(user=user, now=current_time)
    user.refresh_from_db(fields=["presence_state", "presence_last_changed_at"])
    if user.presence_state == previous_presence:
        return None
    return serialize_presence_update(user=user)
