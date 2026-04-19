import logging

from ..realtime.presence import PresenceConnectionSnapshot, compute_presence
from ...common.enums import PresenceState
from ...presence.models import UserPresenceConnection

logger = logging.getLogger(__name__)


def compare_presence_state_to_legacy_sql(*, user, redis_connections, now) -> list[str]:
    sql_connections = list(
        UserPresenceConnection.objects.filter(
            user=user,
            disconnected_at__isnull=True,
        ).order_by("-last_interaction_at", "-last_heartbeat_at", "-connected_at", "-id")
    )
    sql_snapshots = [
        PresenceConnectionSnapshot(
            connection_key=item.connection_key,
            user_id=str(item.user_id),
            session_id=str(item.session_id) if item.session_id else None,
            tab_id=item.tab_id,
            is_active=item.is_active,
            last_interaction_at=item.last_interaction_at,
            last_heartbeat_at=item.last_heartbeat_at,
            connected_at=item.connected_at,
        )
        for item in sql_connections
    ]
    mismatches: list[str] = []
    redis_presence = compute_presence(connections=redis_connections, now=now)
    sql_presence = compute_presence(connections=sql_snapshots, now=now)
    if redis_presence != sql_presence:
        mismatches.append(f"presence mismatch redis={redis_presence} sql={sql_presence}")
    if len(redis_connections) != len(sql_snapshots):
        mismatches.append(
            f"connection count mismatch redis={len(redis_connections)} sql={len(sql_snapshots)}"
        )
    if redis_presence not in {
        PresenceState.ONLINE,
        PresenceState.AFK,
        PresenceState.OFFLINE,
    }:
        mismatches.append(f"unexpected redis presence value={redis_presence}")
    return mismatches


def log_presence_parity_mismatches(*, user, redis_connections, now) -> None:
    mismatches = compare_presence_state_to_legacy_sql(
        user=user,
        redis_connections=redis_connections,
        now=now,
    )
    if mismatches:
        logger.warning(
            "Redis presence parity mismatch for user %s: %s",
            user.id,
            "; ".join(mismatches),
        )
