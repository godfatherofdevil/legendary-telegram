import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_openapi_schema_endpoint_is_public_and_lists_backend_routes(api_client: APIClient) -> None:
    response = api_client.get(reverse("api-schema"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["openapi"] == "3.0.3"
    assert "/api/v1/auth/login" in payload["paths"]
    assert "/api/v1/rooms/{room_id}" in payload["paths"]
    assert "/api/v1/attachments/{attachment_id}" in payload["paths"]
    assert payload["components"]["securitySchemes"]["sessionAuth"]["in"] == "cookie"


@pytest.mark.django_db
def test_swagger_ui_endpoint_is_public(api_client: APIClient) -> None:
    response = api_client.get(reverse("api-docs"))

    assert response.status_code == 200
    assert reverse("api-schema") in response.content.decode()
    assert "SwaggerUIBundle" in response.content.decode()
