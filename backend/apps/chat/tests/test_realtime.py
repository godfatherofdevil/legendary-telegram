from django.core.exceptions import ImproperlyConfigured

from ..realtime import PRESENCE_GROUP, dialog_group, room_group, user_group
from config import settings


def test_realtime_group_names_are_stable() -> None:
    assert PRESENCE_GROUP == "presence.all"
    assert user_group("usr_01") == "user.usr_01"
    assert room_group("room_01") == "room.room_01"
    assert dialog_group("dlg_01") == "dialog.dlg_01"


def test_build_channel_layers_prefers_redis() -> None:
    channel_layers = settings.build_channel_layers(
        redis_url="redis://redis:6379/0",
        allow_inmemory_fallback=False,
    )

    assert channel_layers == {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": ["redis://redis:6379/0"]},
        }
    }


def test_build_channel_layers_allows_explicit_inmemory_fallback() -> None:
    channel_layers = settings.build_channel_layers(
        redis_url="",
        allow_inmemory_fallback=True,
    )

    assert channel_layers == {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


def test_build_channel_layers_rejects_missing_redis_when_fallback_disabled() -> None:
    try:
        settings.build_channel_layers(redis_url="", allow_inmemory_fallback=False)
    except ImproperlyConfigured:
        pass
    else:
        raise AssertionError("Expected missing REDIS_URL to be rejected.")
