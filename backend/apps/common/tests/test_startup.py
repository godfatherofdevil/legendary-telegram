import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db.migrations.exceptions import InconsistentMigrationHistory
from django.urls import Resolver404, resolve

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


def test_unconfigured_api_namespace_is_not_exposed() -> None:
    try:
        resolve("/api/v1/auth/login")
    except Resolver404:
        return
    raise AssertionError("Contract routes should not exist until implemented.")


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


def test_reset_sqlite_database_removes_existing_file(tmp_path) -> None:
    database_path = tmp_path / "stale.sqlite3"
    database_path.write_text("placeholder", encoding="utf-8")

    startup.reset_sqlite_database({"NAME": str(database_path)})

    assert not database_path.exists()
