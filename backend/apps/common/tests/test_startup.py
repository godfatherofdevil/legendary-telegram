import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db.migrations.exceptions import InconsistentMigrationHistory
from django.urls import resolve

from config import startup


def test_django_check_passes(db) -> None:
    call_command("check")


def test_fresh_database_can_apply_all_migrations(tmp_path) -> None:
    backend_dir = Path(__file__).resolve().parents[3]
    database_path = tmp_path / "fresh-migrations.sqlite3"
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DATABASE_URL": f"sqlite:///{database_path}",
    }

    result = subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        cwd=backend_dir,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_admin_route_is_registered() -> None:
    match = resolve("/admin/")
    assert match is not None


def test_auth_login_route_is_registered() -> None:
    match = resolve("/api/v1/auth/login")
    assert match is not None


def test_health_routes_are_registered() -> None:
    assert resolve("/health/live/") is not None
    assert resolve("/health/ready/") is not None


def test_run_startup_migrations_recovers_known_inconsistent_history(monkeypatch) -> None:
    calls: list[str] = []

    def fake_run_migrate() -> None:
        calls.append("migrate")
        if len(calls) == 1:
            raise InconsistentMigrationHistory(startup.KNOWN_ADMIN_ACCOUNTS_INCONSISTENCY)

    monkeypatch.setenv("DJANGO_RESET_INCONSISTENT_MIGRATIONS", "1")
    monkeypatch.setattr(startup, "_run_migrate", fake_run_migrate)
    monkeypatch.setattr(startup, "reset_default_database", lambda: calls.append("reset"))

    startup.run_startup_migrations()

    assert calls == ["migrate", "reset", "migrate"]


def test_run_startup_migrations_does_not_hide_other_inconsistencies(monkeypatch) -> None:
    monkeypatch.setenv("DJANGO_RESET_INCONSISTENT_MIGRATIONS", "1")
    monkeypatch.setattr(
        startup,
        "_run_migrate",
        lambda: (_ for _ in ()).throw(
            InconsistentMigrationHistory(
                "Migration chat.0002_example is applied before its dependency chat.0001_initial "
                "on database 'default'."
            )
        ),
    )
    monkeypatch.setattr(startup, "reset_default_database", lambda: None)

    with pytest.raises(InconsistentMigrationHistory):
        startup.run_startup_migrations()


def test_run_attachment_storage_backfill_on_startup_is_disabled_by_default(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    monkeypatch.delenv("ATTACHMENTS_RUN_BACKFILL_ON_STARTUP", raising=False)
    monkeypatch.setattr(startup.settings, "ATTACHMENTS_STORAGE_BACKEND", "s3")
    monkeypatch.setattr(
        startup,
        "call_command",
        lambda name, **kwargs: calls.append((name, kwargs)),
    )

    startup.run_attachment_storage_backfill_on_startup()

    assert calls == []


def test_run_attachment_storage_backfill_on_startup_runs_when_flag_enabled(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    monkeypatch.setenv("ATTACHMENTS_RUN_BACKFILL_ON_STARTUP", "1")
    monkeypatch.setattr(startup.settings, "ATTACHMENTS_STORAGE_BACKEND", "s3")
    monkeypatch.setattr(
        startup,
        "call_command",
        lambda name, **kwargs: calls.append((name, kwargs)),
    )

    startup.run_attachment_storage_backfill_on_startup()

    assert calls == [("backfill_attachments_to_object_storage", {"verbosity": 1})]


def test_run_attachment_storage_backfill_on_startup_skips_non_s3_backend(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    monkeypatch.setenv("ATTACHMENTS_RUN_BACKFILL_ON_STARTUP", "1")
    monkeypatch.setattr(startup.settings, "ATTACHMENTS_STORAGE_BACKEND", "filesystem")
    monkeypatch.setattr(
        startup,
        "call_command",
        lambda name, **kwargs: calls.append((name, kwargs)),
    )

    startup.run_attachment_storage_backfill_on_startup()

    assert calls == []


def test_reset_sqlite_database_removes_existing_file(tmp_path) -> None:
    database_path = tmp_path / "stale.sqlite3"
    database_path.write_text("placeholder", encoding="utf-8")

    startup.reset_sqlite_database({"NAME": str(database_path)})

    assert not database_path.exists()


def test_validate_runtime_configuration_rejects_default_secret_key_in_non_debug(
    monkeypatch,
) -> None:
    monkeypatch.setattr(startup.settings, "DEBUG", False)
    monkeypatch.setattr(startup.settings, "SECRET_KEY", startup.settings.LOCAL_DEV_SECRET_KEY)
    monkeypatch.setattr(startup.settings, "ALLOWED_HOSTS", ["localhost"])

    with pytest.raises(ImproperlyConfigured):
        startup.validate_runtime_configuration()


def test_validate_runtime_configuration_requires_allowed_hosts_in_non_debug(monkeypatch) -> None:
    monkeypatch.setattr(startup.settings, "DEBUG", False)
    monkeypatch.setattr(startup.settings, "SECRET_KEY", "production-secret")
    monkeypatch.setattr(startup.settings, "ALLOWED_HOSTS", [])
    monkeypatch.setattr(startup.settings, "REDIS_URL", "redis://redis:6379/0")

    with pytest.raises(ImproperlyConfigured):
        startup.validate_runtime_configuration()


def test_validate_runtime_configuration_requires_redis_in_non_debug(monkeypatch) -> None:
    monkeypatch.setattr(startup.settings, "DEBUG", False)
    monkeypatch.setattr(startup.settings, "SECRET_KEY", "production-secret")
    monkeypatch.setattr(startup.settings, "ALLOWED_HOSTS", ["example.com"])
    monkeypatch.setattr(startup.settings, "REDIS_URL", "")

    with pytest.raises(ImproperlyConfigured):
        startup.validate_runtime_configuration()


def test_prepare_runtime_directories_creates_media_and_static_dirs(tmp_path, monkeypatch) -> None:
    media_root = tmp_path / "media"
    static_root = tmp_path / "staticfiles"
    monkeypatch.setattr(startup.settings, "MEDIA_ROOT", media_root)
    monkeypatch.setattr(startup.settings, "STATIC_ROOT", static_root)

    startup.prepare_runtime_directories()

    assert media_root.is_dir()
    assert static_root.is_dir()


def _write_fake_executable(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def _wait_for_log_line(log_path: Path, expected_line: str, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8").splitlines()
            if expected_line in lines:
                return
        time.sleep(0.05)

    pytest.fail(f"Timed out waiting for {expected_line!r} in {log_path}")


def test_entrypoint_forwards_sigint_during_startup(tmp_path) -> None:
    backend_dir = Path(__file__).resolve().parents[3]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    event_log = tmp_path / "events.log"

    _write_fake_executable(
        bin_dir / "python",
        """#!/bin/sh
set -eu
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "config.startup" ]; then
    trap 'echo startup-interrupted >> "$TEST_EVENT_LOG"; exit 130' INT TERM HUP QUIT
    echo startup-begin >> "$TEST_EVENT_LOG"
    while :; do
        sleep 0.1
    done
fi
exit 1
""",
    )
    _write_fake_executable(
        bin_dir / "daphne",
        """#!/bin/sh
set -eu
echo daphne-begin >> "$TEST_EVENT_LOG"
exit 0
""",
    )

    env = {
        **os.environ,
        "TEST_EVENT_LOG": str(event_log),
        "BACKEND_STARTUP_COMMAND": str(bin_dir / "python") + " -m config.startup",
        "BACKEND_SERVER_COMMAND": str(bin_dir / "daphne"),
    }

    process = subprocess.Popen(
        ["/bin/sh", str(backend_dir / "entrypoint.sh")],
        cwd=backend_dir,
        env=env,
        text=True,
    )
    _wait_for_log_line(event_log, "startup-begin")

    process.send_signal(signal.SIGINT)
    return_code = process.wait(timeout=3)

    lines = event_log.read_text(encoding="utf-8").splitlines()
    assert return_code != 0
    assert "startup-interrupted" in lines
    assert "daphne-begin" not in lines


def test_entrypoint_forwards_sigint_to_daphne(tmp_path) -> None:
    backend_dir = Path(__file__).resolve().parents[3]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    event_log = tmp_path / "events.log"

    _write_fake_executable(
        bin_dir / "python",
        """#!/bin/sh
set -eu
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "config.startup" ]; then
    echo startup-complete >> "$TEST_EVENT_LOG"
    exit 0
fi
exit 1
""",
    )
    _write_fake_executable(
        bin_dir / "daphne",
        """#!/bin/sh
set -eu
trap 'echo daphne-interrupted >> "$TEST_EVENT_LOG"; exit 130' INT TERM HUP QUIT
echo daphne-begin >> "$TEST_EVENT_LOG"
while :; do
    sleep 0.1
done
""",
    )

    env = {
        **os.environ,
        "TEST_EVENT_LOG": str(event_log),
        "BACKEND_STARTUP_COMMAND": str(bin_dir / "python") + " -m config.startup",
        "BACKEND_SERVER_COMMAND": str(bin_dir / "daphne"),
    }

    process = subprocess.Popen(
        ["/bin/sh", str(backend_dir / "entrypoint.sh")],
        cwd=backend_dir,
        env=env,
        text=True,
    )
    _wait_for_log_line(event_log, "daphne-begin")

    process.send_signal(signal.SIGINT)
    return_code = process.wait(timeout=3)

    lines = event_log.read_text(encoding="utf-8").splitlines()
    assert return_code != 0
    assert "startup-complete" in lines
    assert "daphne-interrupted" in lines
