import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from ...chat.models import Dialog, DialogMessage
from ..models import FriendRequest, Friendship, PeerBan

User = get_user_model()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def create_user(*, email: str, username: str) -> User:
    return User.objects.create_user(email=email, username=username, password="StrongPassword123!")


def make_friends(user_a: User, user_b: User) -> Friendship:
    user_low, user_high = sorted([user_a, user_b], key=lambda user: str(user.id))
    return Friendship.objects.create(user_low=user_low, user_high=user_high)


@pytest.mark.django_db
def test_friend_request_list_and_accept_flow(api_client: APIClient) -> None:
    alice = create_user(email="alice-social@example.com", username="alice-social")
    bob = create_user(email="bob-social@example.com", username="bob-social")

    alice_client = APIClient()
    alice_client.force_login(alice)
    bob_client = APIClient()
    bob_client.force_login(bob)

    create_response = alice_client.post(
        reverse("friend-request-list-create"),
        {"username": "bob-social", "message": "Let us connect"},
        format="json",
    )

    assert create_response.status_code == 201
    request_id = create_response.json()["data"]["friend_request"]["id"]

    outgoing_response = alice_client.get(reverse("friend-request-outgoing-list"))
    incoming_response = bob_client.get(reverse("friend-request-incoming-list"))

    assert outgoing_response.status_code == 200
    assert outgoing_response.json()["data"][0]["to_user"]["username"] == "bob-social"
    assert incoming_response.status_code == 200
    assert incoming_response.json()["data"][0]["from_user"]["username"] == "alice-social"

    accept_response = bob_client.post(
        reverse("friend-request-accept", kwargs={"request_id": request_id})
    )

    assert accept_response.status_code == 200
    assert accept_response.json()["data"]["friendship"]["user"]["username"] == "alice-social"
    assert Friendship.objects.count() == 1
    friend_request = FriendRequest.objects.get(id=request_id)
    assert friend_request.status == "accepted"


@pytest.mark.django_db
def test_friend_list_returns_existing_friendships(api_client: APIClient) -> None:
    alice = create_user(email="alice-friends@example.com", username="alice-friends")
    bob = create_user(email="bob-friends@example.com", username="bob-friends")
    friendship = make_friends(alice, bob)

    api_client.force_login(alice)

    response = api_client.get(reverse("friend-list"))

    assert response.status_code == 200
    assert response.json()["data"] == [
        {
            "user": {
                "id": str(bob.id),
                "username": "bob-friends",
                "presence": "offline",
            },
            "friend_since": friendship.created_at.isoformat().replace("+00:00", "Z"),
        }
    ]


@pytest.mark.django_db
def test_friend_request_reject_and_conflict_rules(api_client: APIClient) -> None:
    alice = create_user(email="alice-reject@example.com", username="alice-reject")
    bob = create_user(email="bob-reject@example.com", username="bob-reject")
    carol = create_user(email="carol-reject@example.com", username="carol-reject")
    make_friends(alice, carol)
    PeerBan.objects.create(source_user=bob, target_user=alice)

    alice_client = APIClient()
    alice_client.force_login(alice)
    bob_client = APIClient()
    bob_client.force_login(bob)

    blocked_response = alice_client.post(
        reverse("friend-request-list-create"),
        {"username": "bob-reject"},
        format="json",
    )
    assert blocked_response.status_code == 403

    already_friend_response = alice_client.post(
        reverse("friend-request-list-create"),
        {"username": "carol-reject"},
        format="json",
    )
    assert already_friend_response.status_code == 409

    pending = FriendRequest.objects.create(from_user=alice, to_user=bob, message="hi")
    reject_response = bob_client.post(
        reverse("friend-request-reject", kwargs={"request_id": pending.id})
    )
    assert reject_response.status_code == 204
    pending.refresh_from_db()
    assert pending.status == "rejected"


@pytest.mark.django_db
def test_remove_friend_and_peer_ban_update_dialog_state(api_client: APIClient) -> None:
    alice = create_user(email="alice-ban@example.com", username="alice-ban")
    bob = create_user(email="bob-ban@example.com", username="bob-ban")
    make_friends(alice, bob)
    user_low, user_high = sorted([alice, bob], key=lambda user: str(user.id))
    dialog = Dialog.objects.create(user_low=user_low, user_high=user_high)

    alice_client = APIClient()
    alice_client.force_login(alice)

    remove_friend_response = alice_client.delete(
        reverse("friend-detail", kwargs={"user_id": bob.id})
    )
    assert remove_friend_response.status_code == 204
    dialog.refresh_from_db()
    assert dialog.is_frozen is True

    create_ban_response = alice_client.post(
        reverse("peer-ban-list-create"),
        {"user_id": str(bob.id)},
        format="json",
    )
    assert create_ban_response.status_code == 201
    assert PeerBan.objects.filter(
        source_user=alice,
        target_user=bob,
        removed_at__isnull=True,
    ).exists()
    dialog.refresh_from_db()
    assert dialog.is_frozen is True
    assert Friendship.objects.exists() is False

    list_response = alice_client.get(reverse("peer-ban-list-create"))
    assert list_response.status_code == 200
    assert list_response.json()["data"][0]["user"]["username"] == "bob-ban"

    remove_ban_response = alice_client.delete(
        reverse("peer-ban-detail", kwargs={"user_id": bob.id})
    )
    assert remove_ban_response.status_code == 204
    dialog.refresh_from_db()
    assert dialog.is_frozen is True


@pytest.mark.django_db
def test_remove_friend_updates_other_user_reload_state(api_client: APIClient) -> None:
    alice = create_user(email="alice-remove@example.com", username="alice-remove")
    bob = create_user(email="bob-remove@example.com", username="bob-remove")
    make_friends(alice, bob)
    user_low, user_high = sorted([alice, bob], key=lambda user: str(user.id))
    dialog = Dialog.objects.create(user_low=user_low, user_high=user_high)

    alice_client = APIClient()
    alice_client.force_login(alice)
    bob_client = APIClient()
    bob_client.force_login(bob)

    response = alice_client.delete(reverse("friend-detail", kwargs={"user_id": bob.id}))

    assert response.status_code == 204
    assert alice_client.get(reverse("friend-list")).json()["data"] == []
    assert bob_client.get(reverse("friend-list")).json()["data"] == []
    assert bob_client.get(reverse("dialog-list-create")).json()["data"] == [
        {
            "id": str(dialog.id),
            "other_user": {
                "id": str(alice.id),
                "username": "alice-remove",
                "presence": "offline",
            },
            "last_message": None,
            "unread_count": 0,
            "is_frozen": True,
        }
    ]


@pytest.mark.django_db
def test_peer_ban_freezes_existing_dialog_sends_for_both_users(api_client: APIClient) -> None:
    alice = create_user(email="alice-freeze@example.com", username="alice-freeze")
    bob = create_user(email="bob-freeze@example.com", username="bob-freeze")
    make_friends(alice, bob)
    user_low, user_high = sorted([alice, bob], key=lambda user: str(user.id))
    dialog = Dialog.objects.create(user_low=user_low, user_high=user_high)
    existing_message = DialogMessage.objects.create(
        dialog=dialog,
        sender_user=alice,
        text="history",
    )

    alice_client = APIClient()
    alice_client.force_login(alice)
    bob_client = APIClient()
    bob_client.force_login(bob)

    ban_response = alice_client.post(
        reverse("peer-ban-list-create"),
        {"user_id": str(bob.id)},
        format="json",
    )
    alice_send_response = alice_client.post(
        reverse("dialog-message-list-create", kwargs={"dialog_id": dialog.id}),
        {"text": "owner blocked too"},
        format="json",
    )
    bob_send_response = bob_client.post(
        reverse("dialog-message-list-create", kwargs={"dialog_id": dialog.id}),
        {"text": "blocked"},
        format="json",
    )
    alice_history_response = alice_client.get(
        reverse("dialog-message-list-create", kwargs={"dialog_id": dialog.id})
    )
    bob_history_response = bob_client.get(
        reverse("dialog-message-list-create", kwargs={"dialog_id": dialog.id})
    )

    assert ban_response.status_code == 201
    assert alice_send_response.status_code == 403
    assert bob_send_response.status_code == 403
    assert alice_history_response.status_code == 200
    assert bob_history_response.status_code == 200
    assert alice_history_response.json()["data"][0]["id"] == str(existing_message.id)
    assert bob_history_response.json()["data"][0]["id"] == str(existing_message.id)
