from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from ...infrastructure.redis.client import get_redis_connection
from ....presence.models import UserPresenceConnection
from ....presence.services import get_presence_snapshots, upsert_presence_connection

User = get_user_model()


class FakeRedis:
    def __init__(self):
        self.now = timezone.now()
        self.values: dict[str, tuple[str, timezone.datetime | None]] = {}
        self.sets: dict[str, tuple[set[str], timezone.datetime | None]] = {}

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)

    def _expired(self, expires_at):
        return expires_at is not None and self.now >= expires_at

    def _prune_key(self, name: str) -> None:
        value = self.values.get(name)
        if value and self._expired(value[1]):
            self.values.pop(name, None)
        set_value = self.sets.get(name)
        if set_value and self._expired(set_value[1]):
            self.sets.pop(name, None)

    def set(self, name: str, value: str, ex: int | None = None) -> None:
        expires_at = self.now + timedelta(seconds=ex) if ex is not None else None
        self.values[name] = (value, expires_at)

    def get(self, name: str) -> str | None:
        self._prune_key(name)
        value = self.values.get(name)
        if value is None:
            return None
        return value[0]

    def delete(self, *names: str) -> None:
        for name in names:
            self.values.pop(name, None)
            self.sets.pop(name, None)

    def sadd(self, name: str, *values: str) -> None:
        self._prune_key(name)
        members, expires_at = self.sets.get(name, (set(), None))
        members.update(values)
        self.sets[name] = (members, expires_at)

    def srem(self, name: str, *values: str) -> None:
        self._prune_key(name)
        members, expires_at = self.sets.get(name, (set(), None))
        members.difference_update(values)
        if members:
            self.sets[name] = (members, expires_at)
        else:
            self.sets.pop(name, None)

    def smembers(self, name: str) -> set[str]:
        self._prune_key(name)
        members, _expires_at = self.sets.get(name, (set(), None))
        return set(members)

    def expire(self, name: str, seconds: int) -> None:
        expires_at = self.now + timedelta(seconds=seconds)
        if name in self.values:
            value, _existing = self.values[name]
            self.values[name] = (value, expires_at)
        if name in self.sets:
            members, _existing = self.sets[name]
            self.sets[name] = (members, expires_at)


@pytest.fixture(autouse=True)
def clear_redis_cache():
    get_redis_connection.cache_clear()
    yield
    get_redis_connection.cache_clear()


def create_user(*, email: str, username: str):
    return User.objects.create_user(email=email, username=username, password="StrongPassword123!")


@pytest.mark.django_db
@override_settings(
    CHAT_MIGRATION_FLAGS={
        "redis_presence_enabled": True,
        "redis_fanout_enabled": False,
        "redis_stream_publish_enabled": False,
        "async_persistence_enabled": False,
        "legacy_sql_presence_enabled": False,
        "legacy_sql_fanout_enabled": False,
        "stream_fallback_to_sync_sql_enabled": False,
        "parity_verification_enabled": False,
    }
)
def test_redis_presence_registry_expires_to_offline(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(
        "apps.chat.infrastructure.redis.client.get_redis_connection",
        lambda: fake_redis,
    )
    user = create_user(email="redis-presence@example.com", username="redis-presence")
    now = timezone.now()

    presence_online = upsert_presence_connection(
        user=user,
        connection_key="chan-1",
        session_key=None,
        tab_id="tab-1",
        is_active=True,
        last_interaction_at=now,
        now=now,
    )

    user.refresh_from_db()
    assert presence_online is not None
    assert presence_online["presence"] == "online"
    assert user.presence_state == "online"
    assert UserPresenceConnection.objects.count() == 0

    fake_redis.advance(seconds=91)
    snapshots = get_presence_snapshots(user_ids=[str(user.id)])

    user.refresh_from_db()
    assert snapshots == [
        {
            "user_id": str(user.id),
            "presence": "offline",
            "last_changed_at": user.presence_last_changed_at.isoformat().replace("+00:00", "Z"),
        }
    ]
    assert user.presence_state == "offline"


@pytest.mark.django_db
@override_settings(
    CHAT_MIGRATION_FLAGS={
        "redis_presence_enabled": True,
        "redis_fanout_enabled": False,
        "redis_stream_publish_enabled": False,
        "async_persistence_enabled": False,
        "legacy_sql_presence_enabled": True,
        "legacy_sql_fanout_enabled": False,
        "stream_fallback_to_sync_sql_enabled": False,
        "parity_verification_enabled": True,
    }
)
def test_redis_presence_dual_writes_legacy_sql(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(
        "apps.chat.infrastructure.redis.client.get_redis_connection",
        lambda: fake_redis,
    )
    user = create_user(email="dual-write@example.com", username="dual-write")
    now = timezone.now()

    upsert_presence_connection(
        user=user,
        connection_key="chan-2",
        session_key=None,
        tab_id="tab-2",
        is_active=False,
        last_interaction_at=now - timedelta(minutes=2),
        now=now,
    )

    legacy_connection = UserPresenceConnection.objects.get(user=user, connection_key="chan-2")
    assert legacy_connection.tab_id == "tab-2"
    assert legacy_connection.is_active is False
