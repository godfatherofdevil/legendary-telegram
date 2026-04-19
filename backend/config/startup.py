import os
from pathlib import Path

import django
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import connections
from django.db.migrations.exceptions import InconsistentMigrationHistory

KNOWN_ADMIN_ACCOUNTS_INCONSISTENCY = (
    "Migration admin.0001_initial is applied before its dependency "
    "accounts.0001_initial on database 'default'."
)


def env_bool(name: str, default: bool = False) -> bool:
    value = str(os.environ.get(name, str(int(default)))).strip().lower()
    return value in {"1", "true", "yes", "on"}


def run_startup_migrations() -> None:
    try:
        _run_migrate()
    except InconsistentMigrationHistory as exc:
        if not should_reset_inconsistent_history(exc):
            raise

        print(
            "Detected stale local migration history "
            "(admin.0001_initial before accounts.0001_initial); "
            "resetting the default database schema."
        )
        reset_default_database()
        _run_migrate()


def run_attachment_storage_backfill_on_startup() -> None:
    if not env_bool("ATTACHMENTS_RUN_BACKFILL_ON_STARTUP", False):
        return
    if settings.ATTACHMENTS_STORAGE_BACKEND != "s3":
        return
    call_command("backfill_attachments_to_object_storage", verbosity=1)


def should_reset_inconsistent_history(exc: InconsistentMigrationHistory) -> bool:
    return env_bool("DJANGO_RESET_INCONSISTENT_MIGRATIONS", False) and (
        KNOWN_ADMIN_ACCOUNTS_INCONSISTENCY in str(exc)
    )


def reset_default_database() -> None:
    connection = connections["default"]
    engine = connection.settings_dict["ENGINE"]

    if engine == "django.db.backends.postgresql":
        reset_postgresql_schema(connection)
        return

    if engine == "django.db.backends.sqlite3":
        reset_sqlite_database(connection.settings_dict)
        return

    raise RuntimeError(
        f"Unsupported database engine for inconsistent migration recovery: {engine}"
    )


def reset_postgresql_schema(connection) -> None:
    connection.close()
    with connection.cursor() as cursor:
        cursor.execute("DROP SCHEMA IF EXISTS public CASCADE")
        cursor.execute("CREATE SCHEMA public")
        cursor.execute("GRANT ALL ON SCHEMA public TO CURRENT_USER")
        cursor.execute("GRANT ALL ON SCHEMA public TO public")


def reset_sqlite_database(settings_dict: dict) -> None:
    name = settings_dict["NAME"]
    if name == ":memory:":
        raise RuntimeError("Cannot reset an in-memory SQLite database for migration recovery.")

    db_path = Path(name)
    if db_path.exists():
        db_path.unlink()


def _run_migrate() -> None:
    call_command("migrate", interactive=False, verbosity=1)


def validate_runtime_configuration() -> None:
    if settings.DEBUG:
        return

    if not settings.SECRET_KEY or settings.SECRET_KEY == settings.LOCAL_DEV_SECRET_KEY:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set to a non-default value when DJANGO_DEBUG=0."
        )

    if not settings.ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must include at least one host when DJANGO_DEBUG=0."
        )

    if not settings.REDIS_URL:
        raise ImproperlyConfigured(
            "REDIS_URL must be configured when DJANGO_DEBUG=0 so realtime uses Redis-backed fanout."
        )


def prepare_runtime_directories() -> None:
    for directory in (Path(settings.MEDIA_ROOT), Path(settings.STATIC_ROOT)):
        directory.mkdir(parents=True, exist_ok=True)


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    validate_runtime_configuration()
    prepare_runtime_directories()
    run_startup_migrations()
    run_attachment_storage_backfill_on_startup()


if __name__ == "__main__":
    main()
