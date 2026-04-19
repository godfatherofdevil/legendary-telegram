from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from redis import Redis


@lru_cache(maxsize=1)
def get_redis_connection() -> Redis:
    if not settings.REDIS_URL:
        raise ImproperlyConfigured(
            "REDIS_URL must be configured when Redis-backed presence is enabled."
        )
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)

