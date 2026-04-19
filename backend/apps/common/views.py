import socket
from urllib.parse import urlparse

from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse

from ..attachments.storage import get_attachment_storage_readiness


def live_view(_request):
    return JsonResponse({"status": "ok"})


def ready_view(_request):
    redis_backend = settings.CHANNEL_LAYERS["default"]["BACKEND"]
    attachment_storage_ok, attachment_checks = get_attachment_storage_readiness()
    checks = {
        "database": "ok",
        "redis_configured": bool(settings.REDIS_URL),
        "channel_layer_backend": redis_backend,
        "realtime_transport": "redis" if "RedisChannelLayer" in redis_backend else "inmemory",
        **attachment_checks,
    }

    if settings.REDIS_URL:
        checks["redis_reachable"] = "ok" if _redis_is_reachable(settings.REDIS_URL) else "error"

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except OperationalError:
        checks["database"] = "error"

    redis_ok = checks.get("redis_reachable", "ok") == "ok"
    status_code = (
        200
        if checks["database"] == "ok" and attachment_storage_ok and redis_ok
        else 503
    )
    return JsonResponse(
        {
            "status": "ok" if status_code == 200 else "error",
            "checks": checks,
            "migration_flags": settings.CHAT_MIGRATION_FLAGS,
        },
        status=status_code,
    )


def _redis_is_reachable(redis_url: str) -> bool:
    parsed = urlparse(redis_url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False
