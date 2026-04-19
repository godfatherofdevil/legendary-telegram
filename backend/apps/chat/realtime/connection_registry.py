import json

from django.conf import settings
from django.utils import timezone

from ..infrastructure.redis import client as redis_client
from ..infrastructure.redis.keys import (
    presence_connection_key,
    presence_user_key,
    user_connections_key,
)
from ..realtime.presence import PresenceConnectionSnapshot, serialize_timestamp


def _heartbeat_ttl_seconds() -> int:
    return settings.CHAT_PRESENCE_HEARTBEAT_TTL_SECONDS


def _snapshot_ttl_seconds() -> int:
    return settings.CHAT_PRESENCE_SNAPSHOT_TTL_SECONDS


def _serialize_connection(snapshot: PresenceConnectionSnapshot) -> str:
    return json.dumps(
        {
            "connection_key": snapshot.connection_key,
            "user_id": snapshot.user_id,
            "session_id": snapshot.session_id,
            "tab_id": snapshot.tab_id,
            "is_active": snapshot.is_active,
            "last_interaction_at": serialize_timestamp(snapshot.last_interaction_at),
            "last_heartbeat_at": serialize_timestamp(snapshot.last_heartbeat_at),
            "connected_at": serialize_timestamp(snapshot.connected_at),
        }
    )


def _deserialize_connection(raw_value: str) -> PresenceConnectionSnapshot:
    payload = json.loads(raw_value)
    return PresenceConnectionSnapshot(
        connection_key=payload["connection_key"],
        user_id=payload["user_id"],
        session_id=payload["session_id"],
        tab_id=payload["tab_id"],
        is_active=payload["is_active"],
        last_interaction_at=timezone.datetime.fromisoformat(
            payload["last_interaction_at"].replace("Z", "+00:00")
        ),
        last_heartbeat_at=timezone.datetime.fromisoformat(
            payload["last_heartbeat_at"].replace("Z", "+00:00")
        ),
        connected_at=timezone.datetime.fromisoformat(
            payload["connected_at"].replace("Z", "+00:00")
        ),
    )


def register_connection(
    *,
    user_id,
    connection_key: str,
    session_id: str | None,
    tab_id: str,
    is_active: bool,
    last_interaction_at,
    now=None,
):
    current_time = now or timezone.now()
    client = redis_client.get_redis_connection()
    snapshot = PresenceConnectionSnapshot(
        connection_key=connection_key,
        user_id=str(user_id),
        session_id=session_id,
        tab_id=tab_id,
        is_active=is_active,
        last_interaction_at=last_interaction_at,
        last_heartbeat_at=current_time,
        connected_at=current_time,
    )
    client.set(
        presence_connection_key(connection_key),
        _serialize_connection(snapshot),
        ex=_heartbeat_ttl_seconds(),
    )
    client.sadd(user_connections_key(user_id), connection_key)
    client.expire(user_connections_key(user_id), _heartbeat_ttl_seconds())
    return list_connections(user_id=user_id)


def unregister_connection(*, user_id, connection_key: str):
    client = redis_client.get_redis_connection()
    client.delete(presence_connection_key(connection_key))
    client.srem(user_connections_key(user_id), connection_key)
    return list_connections(user_id=user_id)


def list_connections(*, user_id) -> list[PresenceConnectionSnapshot]:
    client = redis_client.get_redis_connection()
    registry_key = user_connections_key(user_id)
    connection_ids = sorted(client.smembers(registry_key))
    if not connection_ids:
        client.delete(registry_key)
        return []

    connections: list[PresenceConnectionSnapshot] = []
    stale_connection_ids: list[str] = []
    for connection_id in connection_ids:
        raw_value = client.get(presence_connection_key(connection_id))
        if raw_value is None:
            stale_connection_ids.append(connection_id)
            continue
        connections.append(_deserialize_connection(raw_value))

    if stale_connection_ids:
        client.srem(registry_key, *stale_connection_ids)
    if connections:
        client.expire(registry_key, _heartbeat_ttl_seconds())
    else:
        client.delete(registry_key)

    return sorted(
        connections,
        key=lambda item: (
            item.last_interaction_at,
            item.last_heartbeat_at,
            item.connected_at,
            item.connection_key,
        ),
        reverse=True,
    )


def write_presence_snapshot(*, user_id, presence: str, last_changed_at) -> None:
    client = redis_client.get_redis_connection()
    client.set(
        presence_user_key(user_id),
        json.dumps(
            {
                "user_id": str(user_id),
                "presence": presence,
                "last_changed_at": serialize_timestamp(last_changed_at),
            }
        ),
        ex=_snapshot_ttl_seconds(),
    )


def read_presence_snapshot(*, user_id) -> dict | None:
    client = redis_client.get_redis_connection()
    raw_value = client.get(presence_user_key(user_id))
    if raw_value is None:
        return None
    return json.loads(raw_value)
