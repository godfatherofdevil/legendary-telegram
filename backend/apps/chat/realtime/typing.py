from django.conf import settings

from ..infrastructure.redis import client as redis_client
from ..infrastructure.redis.keys import typing_key


def typing_ttl_seconds() -> int:
    return settings.CHAT_TYPING_TTL_SECONDS


def set_typing_indicator(*, chat_type: str, chat_id, user_id) -> None:
    client = redis_client.get_redis_connection()
    client.set(
        typing_key(chat_type=chat_type, chat_id=chat_id, user_id=user_id),
        "1",
        ex=typing_ttl_seconds(),
    )


def clear_typing_indicator(*, chat_type: str, chat_id, user_id) -> None:
    client = redis_client.get_redis_connection()
    client.delete(typing_key(chat_type=chat_type, chat_id=chat_id, user_id=user_id))
