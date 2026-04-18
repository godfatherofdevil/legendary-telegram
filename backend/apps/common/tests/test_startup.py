from django.core.management import call_command
from django.urls import resolve, Resolver404


def test_django_check_passes(db) -> None:
    call_command("check")


def test_admin_route_is_registered() -> None:
    match = resolve("/admin/")
    assert match is not None


def test_unconfigured_api_namespace_is_not_exposed() -> None:
    try:
        resolve("/api/v1/auth/login")
    except Resolver404:
        return
    raise AssertionError("Contract routes should not exist until implemented.")
