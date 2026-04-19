import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from ..models import PasswordResetToken, UserSession
from ...attachments.models import Attachment, RoomMessageAttachment
from ...chat.models import Room, RoomMembership, RoomMessage
from ...common.enums import RoomRole, RoomVisibility

User = get_user_model()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def create_user(*, email="alice@example.com", username="alice", password="StrongPassword123!"):
    return User.objects.create_user(email=email, username=username, password=password)


@pytest.mark.django_db
def test_register_success(api_client: APIClient) -> None:
    response = api_client.post(
        reverse("auth-register"),
        {"email": "alice@example.com", "username": "alice", "password": "StrongPassword123!"},
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["data"]["user"]["email"] == "alice@example.com"


@pytest.mark.django_db
def test_register_accepts_contract_valid_password_payload(api_client: APIClient) -> None:
    response = api_client.post(
        reverse("auth-register"),
        {"email": "bob@example.com", "username": "bob", "password": "password"},
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["data"]["user"]["username"] == "bob"


@override_settings(CORS_ALLOWED_ORIGINS=["http://localhost:3000"], CORS_ALLOW_CREDENTIALS=True)
@pytest.mark.django_db
def test_register_options_preflight_returns_cors_headers(api_client: APIClient) -> None:
    response = api_client.options(
        reverse("auth-register"),
        HTTP_ORIGIN="http://localhost:3000",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-csrftoken",
    )

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert response["Access-Control-Allow-Credentials"] == "true"


@pytest.mark.django_db
def test_session_status_is_anonymous_safe_and_sets_csrf_cookie(api_client: APIClient) -> None:
    response = api_client.get(reverse("auth-session-status"))

    assert response.status_code == 200
    assert response.json()["data"] == {"authenticated": False}
    assert "csrftoken" in response.cookies


@pytest.mark.django_db
def test_session_status_returns_authenticated_for_logged_in_user(api_client: APIClient) -> None:
    user = create_user()
    api_client.force_login(user)

    response = api_client.get(reverse("auth-session-status"))

    assert response.status_code == 200
    assert response.json()["data"] == {"authenticated": True}


@pytest.mark.django_db
def test_register_duplicate_email_returns_conflict(api_client: APIClient) -> None:
    create_user()

    response = api_client.post(
        reverse("auth-register"),
        {"email": "ALICE@example.com", "username": "other", "password": "StrongPassword123!"},
        format="json",
    )

    assert response.status_code == 409


@pytest.mark.django_db
def test_register_duplicate_username_returns_validation_error(api_client: APIClient) -> None:
    create_user()

    response = api_client.post(
        reverse("auth-register"),
        {"email": "other@example.com", "username": "alice", "password": "StrongPassword123!"},
        format="json",
    )

    assert response.status_code == 409


@pytest.mark.django_db
def test_login_creates_authenticated_session(api_client: APIClient) -> None:
    user = create_user()

    response = api_client.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPassword123!", "remember_me": True},
        format="json",
    )

    assert response.status_code == 200
    assert response.cookies[settings.SESSION_COOKIE_NAME].value
    assert UserSession.objects.filter(user=user, is_currently_valid=True).count() == 1


@pytest.mark.django_db
def test_login_invalid_credentials_returns_unauthorized(api_client: APIClient) -> None:
    user = create_user()

    response = api_client.post(
        reverse("auth-login"),
        {"email": user.email, "password": "wrong-password", "remember_me": False},
        format="json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_me_returns_current_user(api_client: APIClient) -> None:
    user = create_user()
    api_client.force_login(user)

    response = api_client.get(reverse("auth-me"))

    assert response.status_code == 200
    assert response.json()["data"]["user"]["username"] == user.username


@pytest.mark.django_db
def test_me_rejects_unauthenticated_requests(api_client: APIClient) -> None:
    response = api_client.get(reverse("auth-me"))
    assert response.status_code == 401
    assert "csrftoken" in response.cookies


@pytest.mark.django_db
def test_logout_invalidates_only_current_session() -> None:
    user = create_user()
    client_one = APIClient()
    client_two = APIClient()
    client_one.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPassword123!", "remember_me": True},
        format="json",
    )
    client_two.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPassword123!", "remember_me": True},
        format="json",
    )

    logout_response = client_one.post(reverse("auth-logout"))

    assert logout_response.status_code == 204
    assert client_one.get(reverse("auth-me")).status_code == 401
    assert client_two.get(reverse("auth-me")).status_code == 200


@pytest.mark.django_db
def test_change_password_updates_password(api_client: APIClient) -> None:
    user = create_user()
    api_client.force_login(user)

    response = api_client.post(
        reverse("auth-change-password"),
        {"current_password": "StrongPassword123!", "new_password": "NewStrongPassword123!"},
        format="json",
    )

    user.refresh_from_db()
    assert response.status_code == 204
    assert user.check_password("NewStrongPassword123!")


@pytest.mark.django_db
def test_change_password_rejects_invalid_current_password(api_client: APIClient) -> None:
    user = create_user()
    api_client.force_login(user)

    response = api_client.post(
        reverse("auth-change-password"),
        {"current_password": "wrong", "new_password": "NewStrongPassword123!"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_password_reset_request_is_privacy_safe(api_client: APIClient) -> None:
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    response = api_client.post(
        reverse("auth-request-password-reset"),
        {"email": "missing@example.com"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"accepted": True}
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_password_reset_confirm_updates_password(api_client: APIClient) -> None:
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = create_user()

    response = api_client.post(
        reverse("auth-request-password-reset"),
        {"email": user.email},
        format="json",
    )

    assert response.status_code == 200
    token = mail.outbox[0].body.rsplit(" ", maxsplit=1)[-1]
    confirm_response = api_client.post(
        reverse("auth-reset-password"),
        {"token": token, "new_password": "ResetPassword123!"},
        format="json",
    )

    user.refresh_from_db()
    token_record = PasswordResetToken.objects.get(user=user)

    assert confirm_response.status_code == 204
    assert user.check_password("ResetPassword123!")
    assert token_record.used_at is not None


@pytest.mark.django_db
def test_session_list_returns_active_sessions() -> None:
    user = create_user()
    client_one = APIClient()
    client_two = APIClient()
    client_one.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPassword123!", "remember_me": True},
        format="json",
    )
    client_two.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPassword123!", "remember_me": True},
        format="json",
    )

    response = client_one.get(reverse("session-list"))

    assert response.status_code == 200
    assert len(response.json()["data"]) == 2


@pytest.mark.django_db
def test_revoke_other_session_keeps_current_session_active() -> None:
    user = create_user()
    client_one = APIClient()
    client_two = APIClient()
    client_one.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPassword123!", "remember_me": True},
        format="json",
    )
    client_two.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPassword123!", "remember_me": True},
        format="json",
    )
    sessions = client_one.get(reverse("session-list")).json()["data"]
    other_id = next(item["id"] for item in sessions if not item["is_current"])

    response = client_one.delete(reverse("session-detail", kwargs={"session_id": other_id}))

    assert response.status_code == 204
    assert client_one.get(reverse("auth-me")).status_code == 200
    assert client_two.get(reverse("auth-me")).status_code == 401


@pytest.mark.django_db
def test_revoke_current_session_logs_out_current_browser(api_client: APIClient) -> None:
    user = create_user()
    api_client.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPassword123!", "remember_me": True},
        format="json",
    )
    session_id = api_client.get(reverse("session-list")).json()["data"][0]["id"]

    response = api_client.delete(reverse("session-detail", kwargs={"session_id": session_id}))

    assert response.status_code == 204
    assert api_client.get(reverse("auth-me")).status_code == 401


@pytest.mark.django_db
def test_delete_account_removes_owned_room_data(api_client: APIClient) -> None:
    owner = create_user()
    other_room_owner = create_user(
        email="other@example.com",
        username="other",
        password="StrongPassword123!",
    )
    owned_room = Room.objects.create(
        name="owned-room",
        visibility=RoomVisibility.PUBLIC,
        owner_user=owner,
    )
    other_room = Room.objects.create(
        name="other-room",
        visibility=RoomVisibility.PUBLIC,
        owner_user=other_room_owner,
    )
    RoomMembership.objects.create(
        room=other_room,
        user=owner,
        role=RoomRole.MEMBER,
        joined_at=owned_room.created_at,
    )
    room_message = RoomMessage.objects.create(room=owned_room, sender_user=owner, text="hello")
    attachment = Attachment.objects.create(
        uploaded_by_user=owner,
        storage_key="owned-room-file",
        original_filename="hello.txt",
        content_type="text/plain",
        size_bytes=5,
    )
    RoomMessageAttachment.objects.create(room_message=room_message, attachment=attachment)
    login_response = api_client.post(
        reverse("auth-login"),
        {"email": owner.email, "password": "StrongPassword123!", "remember_me": True},
        format="json",
    )

    response = api_client.delete(
        reverse("account-delete"),
        {"password": "StrongPassword123!"},
        format="json",
    )

    assert login_response.status_code == 200
    assert response.status_code == 204
    assert api_client.get(reverse("auth-me")).status_code == 401
    assert not User.objects.filter(id=owner.id).exists()
    assert not Room.objects.filter(id=owned_room.id).exists()
    assert not RoomMembership.objects.filter(room=other_room, user=owner).exists()
    assert not Attachment.objects.filter(id=attachment.id).exists()
    assert not UserSession.objects.filter(user_id=owner.id).exists()
