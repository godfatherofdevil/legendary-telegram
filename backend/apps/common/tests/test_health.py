import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .. import views


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def test_live_health_endpoint_is_public(api_client: APIClient) -> None:
    response = api_client.get(reverse("health-live"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_health_endpoint_reports_runtime_checks(
    api_client: APIClient,
    settings,
    monkeypatch,
) -> None:
    if settings.REDIS_URL:
        monkeypatch.setattr(views, "_redis_is_reachable", lambda _redis_url: True)
    response = api_client.get(reverse("health-ready"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["checks"]["database"] == "ok"
    assert response.json()["checks"]["redis_configured"] == bool(settings.REDIS_URL)
    assert (
        response.json()["checks"]["channel_layer_backend"]
        == settings.CHANNEL_LAYERS["default"]["BACKEND"]
    )
    assert response.json()["checks"]["realtime_transport"] in {"redis", "inmemory"}
    assert (
        response.json()["checks"]["attachment_storage_backend"]
        == settings.ATTACHMENTS_STORAGE_BACKEND
    )
    assert response.json()["checks"]["attachment_storage"] == "ok"
    assert response.json()["migration_flags"] == settings.CHAT_MIGRATION_FLAGS


@pytest.mark.django_db
def test_ready_health_endpoint_requires_object_storage_when_s3_backend_is_enabled(
    api_client: APIClient,
    settings,
    monkeypatch,
) -> None:
    monkeypatch.setattr(views, "_redis_is_reachable", lambda _redis_url: True)
    monkeypatch.setattr(
        views,
        "get_attachment_storage_readiness",
        lambda: (
            False,
            {
                "attachment_storage_backend": "s3",
                "object_storage": "error",
                "object_storage_bucket": "uploads",
                "object_storage_error": "EndpointConnectionError",
            },
        ),
    )

    response = api_client.get(reverse("health-ready"))

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert response.json()["checks"]["object_storage"] == "error"
    assert response.json()["checks"]["object_storage_bucket"] == "uploads"


@pytest.mark.django_db
def test_ready_health_endpoint_reports_s3_bucket_success(
    api_client: APIClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(views, "_redis_is_reachable", lambda _redis_url: True)
    monkeypatch.setattr(
        views,
        "get_attachment_storage_readiness",
        lambda: (
            True,
            {
                "attachment_storage_backend": "s3",
                "object_storage": "ok",
                "object_storage_bucket": "uploads",
                "object_storage_endpoint": "http://minio:9000",
            },
        ),
    )

    response = api_client.get(reverse("health-ready"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["checks"]["object_storage"] == "ok"
    assert response.json()["checks"]["object_storage_bucket"] == "uploads"


@pytest.mark.django_db
@override_settings(
    ATTACHMENTS_STORAGE_BACKEND="s3",
    ATTACHMENTS_S3_ENDPOINT_URL="http://minio:9000",
    ATTACHMENTS_S3_BUCKET="uploads",
    ATTACHMENTS_S3_ACCESS_KEY_ID="minioadmin",
    ATTACHMENTS_S3_SECRET_ACCESS_KEY="minioadmin",
    ATTACHMENTS_S3_USE_SSL=False,
    ATTACHMENTS_S3_VERIFY_SSL=False,
)
def test_ready_health_endpoint_succeeds_when_bucket_listing_confirms_bucket_during_startup(
    api_client: APIClient,
    monkeypatch,
) -> None:
    class StartupMinioClient:
        def head_bucket(self, Bucket: str) -> dict:
            raise Exception("BadRequest")

        def list_buckets(self) -> dict:
            return {"Buckets": [{"Name": "uploads"}]}

    monkeypatch.setattr(views, "_redis_is_reachable", lambda _redis_url: True)
    monkeypatch.setattr("apps.attachments.storage._build_s3_client", lambda: StartupMinioClient())

    response = api_client.get(reverse("health-ready"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["checks"]["object_storage"] == "ok"
    assert response.json()["checks"]["object_storage_bucket"] == "uploads"
