from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from ...common.enums import PresenceState

AFK_TIMEOUT = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class PresenceConnectionSnapshot:
    connection_key: str
    user_id: str
    session_id: str | None
    tab_id: str
    is_active: bool
    last_interaction_at: timezone.datetime
    last_heartbeat_at: timezone.datetime
    connected_at: timezone.datetime


def compute_presence(*, connections: list[PresenceConnectionSnapshot], now) -> str:
    if not connections:
        return PresenceState.OFFLINE

    active_cutoff = now - AFK_TIMEOUT
    if any(
        connection.is_active or connection.last_interaction_at > active_cutoff
        for connection in connections
    ):
        return PresenceState.ONLINE
    return PresenceState.AFK


def serialize_timestamp(value) -> str:
    return value.isoformat().replace("+00:00", "Z")

