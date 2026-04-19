from pathlib import Path

from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse


def live_view(_request):
    return JsonResponse({"status": "ok"})


def ready_view(_request):
    checks = {
        "database": "ok",
        "media_root": "ok" if Path(settings.MEDIA_ROOT).exists() else "missing",
        "redis_configured": bool(settings.REDIS_URL),
    }

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except OperationalError:
        checks["database"] = "error"

    status_code = 200 if checks["database"] == "ok" and checks["media_root"] == "ok" else 503
    return JsonResponse(
        {
            "status": "ok" if status_code == 200 else "error",
            "checks": checks,
        },
        status=status_code,
    )
