import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.attachments.models import Attachment, DialogMessageAttachment, RoomMessageAttachment
from apps.chat.models import (
    Dialog,
    DialogMessage,
    DialogReadState,
    Room,
    RoomBan,
    RoomMembership,
    RoomMessage,
    RoomReadState,
)
from apps.common.enums import AttachmentBindingType, RoomRole, RoomVisibility
from apps.social.models import Friendship, PeerBan

User = get_user_model()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def create_user(*, email: str, username: str) -> User:
    return User.objects.create_user(email=email, username=username, password="StrongPassword123!")


def create_room(*, owner: User, name: str, visibility: str, description: str = "desc") -> Room:
    room = Room.objects.create(
        name=name,
        visibility=visibility,
        description=description,
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


@pytest.mark.django_db
def test_user_profile_endpoints_expose_only_public_fields(api_client: APIClient) -> None:
    requester = create_user(email="requester@example.com", username="requester")
    target = create_user(email="bob@example.com", username="bob")
    api_client.force_login(requester)

    by_id_response = api_client.get(reverse("user-profile", kwargs={"user_id": target.id}))
    by_username_response = api_client.get(
        reverse("user-by-username", kwargs={"username": target.username})
    )

    assert by_id_response.status_code == 200
    assert by_username_response.status_code == 200
    assert by_id_response.json()["data"]["user"] == {
        "id": str(target.id),
        "username": "bob",
        "presence": "offline",
    }
    assert "email" not in by_username_response.json()["data"]["user"]


@pytest.mark.django_db
def test_public_room_list_supports_search(api_client: APIClient) -> None:
    requester = create_user(email="requester@example.com", username="requester")
    owner = create_user(email="owner@example.com", username="owner")
    create_room(owner=owner, name="engineering", visibility=RoomVisibility.PUBLIC)
    create_room(owner=owner, name="design", visibility=RoomVisibility.PUBLIC)
    create_room(owner=owner, name="private-eng", visibility=RoomVisibility.PRIVATE)
    api_client.force_login(requester)

    response = api_client.get(reverse("room-public-list"), {"search": "eng", "limit": 50})

    assert response.status_code == 200
    payload = response.json()
    assert [item["name"] for item in payload["data"]] == ["engineering"]
    assert payload["data"][0]["member_count"] == 1
    assert payload["pagination"] == {"next_cursor": None, "limit": 50}


@pytest.mark.django_db
def test_joined_room_list_includes_unread_counts(api_client: APIClient) -> None:
    member = create_user(email="member@example.com", username="member")
    owner = create_user(email="owner@example.com", username="owner")
    other = create_user(email="other@example.com", username="other")
    room = create_room(owner=owner, name="general", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=room, user=member, role=RoomRole.MEMBER, joined_at=timezone.now()
    )
    RoomMessage.objects.create(room=room, sender_user=other, text="one")
    RoomMessage.objects.create(room=room, sender_user=other, text="two")
    RoomMessage.objects.create(room=room, sender_user=member, text="mine")
    api_client.force_login(member)

    response = api_client.get(reverse("room-joined-list"))

    assert response.status_code == 200
    assert response.json()["data"] == [
        {
            "id": str(room.id),
            "name": "general",
            "description": "desc",
            "visibility": "public",
            "member_count": 2,
            "unread_count": 2,
        }
    ]


@pytest.mark.django_db
def test_create_room_creates_owner_membership(api_client: APIClient) -> None:
    owner = create_user(email="owner@example.com", username="owner")
    api_client.force_login(owner)

    response = api_client.post(
        reverse("room-list-create"),
        {"name": "engineering", "description": "Backend", "visibility": "public"},
        format="json",
    )

    assert response.status_code == 201
    room = Room.objects.get(name="engineering")
    owner_membership = RoomMembership.objects.get(room=room, user=owner)
    assert owner_membership.role == RoomRole.OWNER
    assert response.json()["data"]["room"]["owner"]["username"] == "owner"


@pytest.mark.django_db
def test_create_room_rejects_duplicate_name(api_client: APIClient) -> None:
    owner = create_user(email="owner@example.com", username="owner")
    create_room(owner=owner, name="engineering", visibility=RoomVisibility.PUBLIC)
    api_client.force_login(owner)

    response = api_client.post(
        reverse("room-list-create"),
        {"name": "engineering", "description": "Backend", "visibility": "public"},
        format="json",
    )

    assert response.status_code == 409


@pytest.mark.django_db
def test_room_detail_is_visible_for_public_rooms_and_hidden_for_private_non_members(
    api_client: APIClient,
) -> None:
    owner = create_user(email="owner@example.com", username="owner")
    outsider = create_user(email="outsider@example.com", username="outsider")
    public_room = create_room(owner=owner, name="public-room", visibility=RoomVisibility.PUBLIC)
    private_room = create_room(owner=owner, name="private-room", visibility=RoomVisibility.PRIVATE)
    api_client.force_login(outsider)

    public_response = api_client.get(reverse("room-detail", kwargs={"room_id": public_room.id}))
    private_response = api_client.get(reverse("room-detail", kwargs={"room_id": private_room.id}))

    assert public_response.status_code == 200
    assert public_response.json()["data"]["room"]["current_user_role"] == "none"
    assert public_response.json()["data"]["room"]["is_member"] is False
    assert private_response.status_code == 404


@pytest.mark.django_db
def test_room_update_and_delete_are_owner_only(api_client: APIClient) -> None:
    owner = create_user(email="owner@example.com", username="owner")
    member = create_user(email="member@example.com", username="member")
    room = create_room(owner=owner, name="engineering", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=room, user=member, role=RoomRole.MEMBER, joined_at=timezone.now()
    )
    api_client.force_login(member)

    update_response = api_client.patch(
        reverse("room-detail", kwargs={"room_id": room.id}),
        {"description": "Updated"},
        format="json",
    )
    delete_response = api_client.delete(reverse("room-detail", kwargs={"room_id": room.id}))

    assert update_response.status_code == 403
    assert delete_response.status_code == 403


@pytest.mark.django_db
def test_room_delete_cascades_room_messages_and_attachments(api_client: APIClient) -> None:
    owner = create_user(email="owner@example.com", username="owner")
    room = create_room(owner=owner, name="engineering", visibility=RoomVisibility.PUBLIC)
    message = RoomMessage.objects.create(room=room, sender_user=owner, text="hello")
    attachment = Attachment.objects.create(
        uploaded_by_user=owner,
        storage_key="storage/key",
        original_filename="hello.txt",
        content_type="text/plain",
        size_bytes=5,
        binding_type="room_message",
    )
    RoomMessageAttachment.objects.create(room_message=message, attachment=attachment)
    api_client.force_login(owner)

    response = api_client.delete(reverse("room-detail", kwargs={"room_id": room.id}))

    assert response.status_code == 204
    assert Room.objects.filter(id=room.id).exists() is False
    assert RoomMessage.objects.filter(id=message.id).exists() is False
    assert Attachment.objects.filter(id=attachment.id).exists() is False


@pytest.mark.django_db
def test_join_room_allows_public_and_rejects_private_and_banned(api_client: APIClient) -> None:
    owner = create_user(email="owner@example.com", username="owner")
    member = create_user(email="member@example.com", username="member")
    public_room = create_room(owner=owner, name="public-room", visibility=RoomVisibility.PUBLIC)
    private_room = create_room(owner=owner, name="private-room", visibility=RoomVisibility.PRIVATE)
    banned_room = create_room(owner=owner, name="banned-room", visibility=RoomVisibility.PUBLIC)
    RoomBan.objects.create(room=banned_room, user=member, banned_by_user=owner)
    api_client.force_login(member)

    public_response = api_client.post(reverse("room-join", kwargs={"room_id": public_room.id}))
    private_response = api_client.post(reverse("room-join", kwargs={"room_id": private_room.id}))
    banned_response = api_client.post(reverse("room-join", kwargs={"room_id": banned_room.id}))

    assert public_response.status_code == 204
    assert RoomMembership.objects.filter(room=public_room, user=member).exists() is True
    assert private_response.status_code == 403
    assert banned_response.status_code == 403


@pytest.mark.django_db
def test_leave_room_rejects_owner_and_allows_member(api_client: APIClient) -> None:
    owner = create_user(email="owner@example.com", username="owner")
    member = create_user(email="member@example.com", username="member")
    room = create_room(owner=owner, name="general", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=room, user=member, role=RoomRole.MEMBER, joined_at=timezone.now()
    )

    owner_client = APIClient()
    owner_client.force_login(owner)
    member_client = APIClient()
    member_client.force_login(member)

    owner_response = owner_client.post(reverse("room-leave", kwargs={"room_id": room.id}))
    member_response = member_client.post(reverse("room-leave", kwargs={"room_id": room.id}))

    assert owner_response.status_code == 403
    assert member_response.status_code == 204
    assert RoomMembership.objects.filter(room=room, user=member).exists() is False


@pytest.mark.django_db
def test_room_member_list_requires_membership(api_client: APIClient) -> None:
    owner = create_user(email="owner@example.com", username="owner")
    member = create_user(email="member@example.com", username="member")
    outsider = create_user(email="outsider@example.com", username="outsider")
    room = create_room(owner=owner, name="general", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=room, user=member, role=RoomRole.ADMIN, joined_at=timezone.now()
    )

    member_client = APIClient()
    member_client.force_login(member)
    outsider_client = APIClient()
    outsider_client.force_login(outsider)

    member_response = member_client.get(reverse("room-member-list", kwargs={"room_id": room.id}))
    outsider_response = outsider_client.get(
        reverse("room-member-list", kwargs={"room_id": room.id})
    )

    assert member_response.status_code == 200
    assert member_response.json()["data"][0]["role"] == "owner"
    assert member_response.json()["data"][1]["role"] == "admin"
    assert outsider_response.status_code == 404


@pytest.mark.django_db
def test_dialog_create_returns_existing_dialog_and_requires_friendship(
    api_client: APIClient,
) -> None:
    alice = create_user(email="alice@example.com", username="alice")
    bob = create_user(email="bob@example.com", username="bob")
    make_friends(alice, bob)
    user_low, user_high = sorted([alice, bob], key=lambda user: str(user.id))
    existing_dialog = Dialog.objects.create(user_low=user_low, user_high=user_high)
    api_client.force_login(alice)

    response = api_client.post(
        reverse("dialog-list-create"), {"user_id": str(bob.id)}, format="json"
    )

    assert response.status_code == 200
    assert response.json()["data"]["dialog"]["id"] == str(existing_dialog.id)
    assert Dialog.objects.count() == 1


@pytest.mark.django_db
def test_dialog_create_rejects_non_friend_and_peer_ban(api_client: APIClient) -> None:
    alice = create_user(email="alice@example.com", username="alice")
    bob = create_user(email="bob@example.com", username="bob")
    carol = create_user(email="carol@example.com", username="carol")
    make_friends(alice, carol)
    PeerBan.objects.create(source_user=carol, target_user=alice)
    api_client.force_login(alice)

    non_friend_response = api_client.post(
        reverse("dialog-list-create"),
        {"user_id": str(bob.id)},
        format="json",
    )
    banned_response = api_client.post(
        reverse("dialog-list-create"),
        {"user_id": str(carol.id)},
        format="json",
    )

    assert non_friend_response.status_code == 403
    assert banned_response.status_code == 403


@pytest.mark.django_db
def test_dialog_list_includes_last_message_and_unread_count(api_client: APIClient) -> None:
    alice = create_user(email="alice@example.com", username="alice")
    bob = create_user(email="bob@example.com", username="bob")
    make_friends(alice, bob)
    user_low, user_high = sorted([alice, bob], key=lambda user: str(user.id))
    dialog = Dialog.objects.create(user_low=user_low, user_high=user_high)
    DialogMessage.objects.create(dialog=dialog, sender_user=bob, text="hello")
    DialogMessage.objects.create(dialog=dialog, sender_user=bob, text="still unread")
    last_message = DialogMessage.objects.create(dialog=dialog, sender_user=alice, text="my reply")
    api_client.force_login(alice)

    response = api_client.get(reverse("dialog-list-create"))

    assert response.status_code == 200
    assert response.json()["data"] == [
        {
            "id": str(dialog.id),
            "other_user": {
                "id": str(bob.id),
                "username": "bob",
                "presence": "offline",
            },
            "last_message": {
                "id": str(last_message.id),
                "sender_id": str(alice.id),
                "text": "my reply",
                "created_at": last_message.created_at.isoformat().replace("+00:00", "Z"),
            },
            "unread_count": 2,
            "is_frozen": False,
        }
    ]


@pytest.mark.django_db
def test_room_message_history_send_reply_edit_delete_and_read_flow(api_client: APIClient) -> None:
    owner = create_user(email="owner@example.com", username="owner")
    member = create_user(email="member@example.com", username="member")
    outsider = create_user(email="outsider@example.com", username="outsider")
    room = create_room(owner=owner, name="history-room", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=room, user=member, role=RoomRole.ADMIN, joined_at=timezone.now()
    )
    first = RoomMessage.objects.create(room=room, sender_user=owner, text="first")
    second = RoomMessage.objects.create(room=room, sender_user=owner, text="second")
    attachment = Attachment.objects.create(
        uploaded_by_user=owner,
        storage_key="storage/room-message",
        original_filename="spec.txt",
        content_type="text/plain",
        size_bytes=4,
        binding_type=AttachmentBindingType.UNBOUND,
    )

    owner_client = APIClient()
    owner_client.force_login(owner)
    member_client = APIClient()
    member_client.force_login(member)
    outsider_client = APIClient()
    outsider_client.force_login(outsider)

    send_response = owner_client.post(
        reverse("room-message-list-create", kwargs={"room_id": room.id}),
        {
            "text": "third",
            "reply_to_message_id": str(first.id),
            "attachment_ids": [str(attachment.id)],
        },
        format="json",
    )

    assert send_response.status_code == 201
    message_payload = send_response.json()["data"]["message"]
    created_message = RoomMessage.objects.get(id=message_payload["id"])
    attachment.refresh_from_db()
    assert created_message.reply_to_message_id == first.id
    assert message_payload["reply_to"] == {
        "id": str(first.id),
        "sender": {"id": str(owner.id), "username": "owner"},
        "text": "first",
    }
    assert message_payload["attachments"] == [
        {
            "id": str(attachment.id),
            "filename": "spec.txt",
            "content_type": "text/plain",
            "size_bytes": 4,
            "comment": None,
            "download_url": f"/api/v1/attachments/{attachment.id}/download",
        }
    ]
    assert attachment.binding_type == AttachmentBindingType.ROOM_MESSAGE
    assert (
        RoomMessageAttachment.objects.filter(
            room_message=created_message, attachment=attachment
        ).exists()
        is True
    )

    page_one = owner_client.get(
        reverse("room-message-list-create", kwargs={"room_id": room.id}), {"limit": 2}
    )
    assert page_one.status_code == 200
    assert [item["id"] for item in page_one.json()["data"]] == [
        str(second.id),
        str(created_message.id),
    ]
    assert page_one.json()["pagination"]["next_cursor"] is not None

    page_two = owner_client.get(
        reverse("room-message-list-create", kwargs={"room_id": room.id}),
        {"limit": 2, "cursor": page_one.json()["pagination"]["next_cursor"]},
    )
    assert page_two.status_code == 200
    assert [item["id"] for item in page_two.json()["data"]] == [str(first.id)]

    edit_forbidden = outsider_client.patch(
        reverse(
            "room-message-detail", kwargs={"room_id": room.id, "message_id": created_message.id}
        ),
        {"text": "hijack"},
        format="json",
    )
    assert edit_forbidden.status_code == 404

    edit_response = owner_client.patch(
        reverse(
            "room-message-detail", kwargs={"room_id": room.id, "message_id": created_message.id}
        ),
        {"text": "third updated"},
        format="json",
    )
    assert edit_response.status_code == 200
    assert edit_response.json()["data"]["message"]["is_edited"] is True
    assert edit_response.json()["data"]["message"]["text"] == "third updated"

    delete_response = member_client.delete(
        reverse(
            "room-message-detail", kwargs={"room_id": room.id, "message_id": created_message.id}
        )
    )
    assert delete_response.status_code == 204
    assert RoomMessage.objects.filter(id=created_message.id).exists() is False

    mark_read_response = owner_client.post(reverse("room-read", kwargs={"room_id": room.id}))
    assert mark_read_response.status_code == 204
    read_state = RoomReadState.objects.get(room=room, user=owner)
    assert read_state.last_read_room_message_id == second.id


@pytest.mark.django_db
def test_room_message_validation_and_authorization_rules(api_client: APIClient) -> None:
    owner = create_user(email="owner2@example.com", username="owner2")
    other_owner = create_user(email="other-owner@example.com", username="otherowner")
    banned_user = create_user(email="banned@example.com", username="banned")
    room = create_room(owner=owner, name="validation-room", visibility=RoomVisibility.PUBLIC)
    other_room = create_room(owner=other_owner, name="other-room", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=room, user=banned_user, role=RoomRole.MEMBER, joined_at=timezone.now()
    )
    RoomBan.objects.create(room=room, user=banned_user, banned_by_user=owner)
    foreign_message = RoomMessage.objects.create(
        room=other_room, sender_user=other_owner, text="foreign"
    )

    owner_client = APIClient()
    owner_client.force_login(owner)
    banned_client = APIClient()
    banned_client.force_login(banned_user)

    too_large = owner_client.post(
        reverse("room-message-list-create", kwargs={"room_id": room.id}),
        {"text": "x" * 3073},
        format="json",
    )
    empty = owner_client.post(
        reverse("room-message-list-create", kwargs={"room_id": room.id}),
        {"text": ""},
        format="json",
    )
    wrong_reply = owner_client.post(
        reverse("room-message-list-create", kwargs={"room_id": room.id}),
        {"text": "reply", "reply_to_message_id": str(foreign_message.id)},
        format="json",
    )
    banned_send = banned_client.post(
        reverse("room-message-list-create", kwargs={"room_id": room.id}),
        {"text": "blocked"},
        format="json",
    )

    assert too_large.status_code == 422
    assert empty.status_code == 422
    assert wrong_reply.status_code == 422
    assert banned_send.status_code == 404


@pytest.mark.django_db
def test_room_message_delete_requires_author_or_moderator(api_client: APIClient) -> None:
    owner = create_user(email="owner3@example.com", username="owner3")
    author = create_user(email="author@example.com", username="author")
    member = create_user(email="member3@example.com", username="member3")
    room = create_room(owner=owner, name="delete-room", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=room, user=author, role=RoomRole.MEMBER, joined_at=timezone.now()
    )
    RoomMembership.objects.create(
        room=room, user=member, role=RoomRole.MEMBER, joined_at=timezone.now()
    )
    message = RoomMessage.objects.create(room=room, sender_user=author, text="delete me")

    member_client = APIClient()
    member_client.force_login(member)

    response = member_client.delete(
        reverse("room-message-detail", kwargs={"room_id": room.id, "message_id": message.id})
    )

    assert response.status_code == 403
    assert RoomMessage.objects.filter(id=message.id).exists() is True


@pytest.mark.django_db
def test_dialog_message_send_history_edit_delete_and_read_flow(api_client: APIClient) -> None:
    alice = create_user(email="alice2@example.com", username="alice2")
    bob = create_user(email="bob2@example.com", username="bob2")
    outsider = create_user(email="outsider2@example.com", username="outsider2")
    make_friends(alice, bob)
    user_low, user_high = sorted([alice, bob], key=lambda user: str(user.id))
    dialog = Dialog.objects.create(user_low=user_low, user_high=user_high)
    first = DialogMessage.objects.create(dialog=dialog, sender_user=bob, text="first")
    attachment = Attachment.objects.create(
        uploaded_by_user=alice,
        storage_key="storage/dialog-message",
        original_filename="hello.txt",
        content_type="text/plain",
        size_bytes=5,
        binding_type=AttachmentBindingType.UNBOUND,
    )

    alice_client = APIClient()
    alice_client.force_login(alice)
    bob_client = APIClient()
    bob_client.force_login(bob)
    outsider_client = APIClient()
    outsider_client.force_login(outsider)

    send_response = alice_client.post(
        reverse("dialog-message-list-create", kwargs={"dialog_id": dialog.id}),
        {
            "text": "reply",
            "reply_to_message_id": str(first.id),
            "attachment_ids": [str(attachment.id)],
        },
        format="json",
    )

    assert send_response.status_code == 201
    created_id = send_response.json()["data"]["message"]["id"]
    created_message = DialogMessage.objects.get(id=created_id)
    attachment.refresh_from_db()
    assert attachment.binding_type == AttachmentBindingType.DIALOG_MESSAGE
    assert (
        DialogMessageAttachment.objects.filter(
            dialog_message=created_message, attachment=attachment
        ).exists()
        is True
    )

    list_response = bob_client.get(
        reverse("dialog-message-list-create", kwargs={"dialog_id": dialog.id}), {"limit": 10}
    )
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["data"]] == [str(first.id), created_id]

    outsider_list = outsider_client.get(
        reverse("dialog-message-list-create", kwargs={"dialog_id": dialog.id})
    )
    assert outsider_list.status_code == 404

    edit_response = alice_client.patch(
        reverse(
            "dialog-message-detail",
            kwargs={"dialog_id": dialog.id, "message_id": created_message.id},
        ),
        {"text": "reply updated"},
        format="json",
    )
    assert edit_response.status_code == 200
    assert edit_response.json()["data"]["message"]["is_edited"] is True

    foreign_delete = bob_client.delete(
        reverse(
            "dialog-message-detail",
            kwargs={"dialog_id": dialog.id, "message_id": created_message.id},
        )
    )
    assert foreign_delete.status_code == 403

    delete_response = alice_client.delete(
        reverse(
            "dialog-message-detail",
            kwargs={"dialog_id": dialog.id, "message_id": created_message.id},
        )
    )
    assert delete_response.status_code == 204

    mark_read_response = bob_client.post(reverse("dialog-read", kwargs={"dialog_id": dialog.id}))
    assert mark_read_response.status_code == 204
    read_state = DialogReadState.objects.get(dialog=dialog, user=bob)
    assert read_state.last_read_dialog_message_id == first.id


@pytest.mark.django_db
def test_dialog_message_send_rejects_frozen_dialog_and_peer_ban_but_history_remains_readable(
    api_client: APIClient,
) -> None:
    alice = create_user(email="alice3@example.com", username="alice3")
    bob = create_user(email="bob3@example.com", username="bob3")
    make_friends(alice, bob)
    user_low, user_high = sorted([alice, bob], key=lambda user: str(user.id))
    dialog = Dialog.objects.create(
        user_low=user_low, user_high=user_high, is_frozen=True, frozen_reason="moderated"
    )
    existing_message = DialogMessage.objects.create(dialog=dialog, sender_user=bob, text="history")

    alice_client = APIClient()
    alice_client.force_login(alice)

    send_response = alice_client.post(
        reverse("dialog-message-list-create", kwargs={"dialog_id": dialog.id}),
        {"text": "blocked"},
        format="json",
    )
    list_response = alice_client.get(
        reverse("dialog-message-list-create", kwargs={"dialog_id": dialog.id})
    )

    assert send_response.status_code == 403
    assert (
        send_response.json()["error"]["message"]
        == "You are not allowed to send messages to this dialog."
    )
    assert list_response.status_code == 200
    assert list_response.json()["data"][0]["id"] == str(existing_message.id)

    dialog.is_frozen = False
    dialog.save(update_fields=["is_frozen", "updated_at"])
    PeerBan.objects.create(source_user=bob, target_user=alice)
    peer_ban_send = alice_client.post(
        reverse("dialog-message-list-create", kwargs={"dialog_id": dialog.id}),
        {"text": "still blocked"},
        format="json",
    )
    assert peer_ban_send.status_code == 403
