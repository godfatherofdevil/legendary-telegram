from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from ...chat.models import Dialog, DialogMessage, Room, RoomMembership, RoomMessage
from ...common.enums import FriendRequestStatus, PresenceState, RoomRole, RoomVisibility
from ..models import UserPresenceConnection
from ...social.models import FriendRequest, Friendship

User = get_user_model()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def create_user(*, email: str, username: str) -> User:
    return User.objects.create_user(email=email, username=username, password="StrongPassword123!")


def create_room(*, owner: User, name: str, visibility: str) -> Room:
    room = Room.objects.create(
        name=name,
        visibility=visibility,
        description="desc",
        owner_user=owner,
    )
    RoomMembership.objects.create(
        room=room,
        user=owner,
        role=RoomRole.OWNER,
        joined_at=timezone.now(),
    )
    return room


def make_friends(user_a: User, user_b: User) -> None:
    user_low, user_high = sorted([user_a, user_b], key=lambda user: str(user.id))
    Friendship.objects.create(user_low=user_low, user_high=user_high)


def create_presence_connection(
    *,
    user: User,
    tab_id: str,
    is_active: bool,
    last_interaction_at,
    disconnected_at=None,
) -> UserPresenceConnection:
    now = timezone.now()
    return UserPresenceConnection.objects.create(
        user=user,
        connection_key=f"{user.id}-{tab_id}",
        tab_id=tab_id,
        is_active=is_active,
        last_interaction_at=last_interaction_at,
        last_heartbeat_at=now,
        connected_at=now,
        disconnected_at=disconnected_at,
    )


@pytest.mark.django_db
def test_presence_query_returns_computed_values_for_multiple_users(api_client: APIClient) -> None:
    requester = create_user(email="requester@example.com", username="requester")
    online_user = create_user(email="online@example.com", username="online")
    afk_user = create_user(email="afk@example.com", username="afk")
    offline_user = create_user(email="offline@example.com", username="offline")
    now = timezone.now()
    create_presence_connection(
        user=online_user,
        tab_id="tab-online",
        is_active=True,
        last_interaction_at=now,
    )
    create_presence_connection(
        user=afk_user,
        tab_id="tab-afk",
        is_active=False,
        last_interaction_at=now - timedelta(seconds=61),
    )
    api_client.force_login(requester)

    response = api_client.post(
        reverse("presence-query"),
        {"user_ids": [str(online_user.id), str(afk_user.id), str(offline_user.id)]},
        format="json",
    )

    online_user.refresh_from_db()
    afk_user.refresh_from_db()
    offline_user.refresh_from_db()

    assert response.status_code == 200
    assert response.json()["data"] == [
        {
            "user_id": str(online_user.id),
            "presence": "online",
            "last_changed_at": online_user.presence_last_changed_at.isoformat().replace(
                "+00:00", "Z"
            ),
        },
        {
            "user_id": str(afk_user.id),
            "presence": "afk",
            "last_changed_at": afk_user.presence_last_changed_at.isoformat().replace("+00:00", "Z"),
        },
        {
            "user_id": str(offline_user.id),
            "presence": "offline",
            "last_changed_at": offline_user.presence_last_changed_at.isoformat().replace(
                "+00:00", "Z"
            ),
        },
    ]
    afk_user.refresh_from_db()
    assert afk_user.presence_state == PresenceState.AFK


@pytest.mark.django_db
def test_notifications_summary_returns_unread_counts_and_pending_requests(
    api_client: APIClient,
) -> None:
    alice = create_user(email="alice@example.com", username="alice")
    bob = create_user(email="bob@example.com", username="bob")
    carol = create_user(email="carol@example.com", username="carol")
    dave = create_user(email="dave@example.com", username="dave")
    room = create_room(owner=bob, name="general", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=room,
        user=alice,
        role=RoomRole.MEMBER,
        joined_at=timezone.now(),
    )
    RoomMessage.objects.create(room=room, sender_user=bob, text="one")
    RoomMessage.objects.create(room=room, sender_user=bob, text="two")
    dialog = Dialog.objects.create(
        user_low=min(alice, carol, key=lambda user: str(user.id)),
        user_high=max(alice, carol, key=lambda user: str(user.id)),
    )
    make_friends(alice, carol)
    DialogMessage.objects.create(dialog=dialog, sender_user=carol, text="hi")
    DialogMessage.objects.create(dialog=dialog, sender_user=carol, text="again")
    FriendRequest.objects.create(
        from_user=dave,
        to_user=alice,
        message="ping",
        status=FriendRequestStatus.PENDING,
    )
    FriendRequest.objects.create(
        from_user=bob,
        to_user=alice,
        message="old",
        status=FriendRequestStatus.REJECTED,
    )
    api_client.force_login(alice)

    response = api_client.get(reverse("notifications-summary"))

    assert response.status_code == 200
    assert response.json()["data"] == {
        "rooms": [{"room_id": str(room.id), "unread_count": 2}],
        "dialogs": [{"dialog_id": str(dialog.id), "unread_count": 2}],
        "incoming_friend_requests": 1,
    }
