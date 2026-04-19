import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def test_live_health_endpoint_is_public(api_client: APIClient) -> None:
    response = api_client.get(reverse("health-live"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_health_endpoint_reports_runtime_checks(api_client: APIClient, settings) -> None:
    response = api_client.get(reverse("health-ready"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["checks"]["database"] == "ok"
    assert response.json()["checks"]["media_root"] == "ok"
    assert response.json()["checks"]["redis_configured"] == bool(settings.REDIS_URL)
