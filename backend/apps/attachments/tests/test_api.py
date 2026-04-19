import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from ..models import Attachment, RoomMessageAttachment
from ..storage import attachment_absolute_path
from ...chat.models import Dialog, Room, RoomBan, RoomMembership, RoomMessage
from ...common.enums import AttachmentBindingType, RoomRole, RoomVisibility
from ...social.models import Friendship

User = get_user_model()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def create_user(*, email: str, username: str) -> User:
    return User.objects.create_user(email=email, username=username, password="StrongPassword123!")


def create_room(*, owner: User, name: str, visibility: str) -> Room:
    room = Room.objects.create(
        name=name,
        description="desc",
        visibility=visibility,
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
@override_settings(MEDIA_ROOT="/tmp/chat-app-test-media-upload")
def test_attachment_upload_persists_metadata_and_file(api_client: APIClient) -> None:
    user = create_user(email="uploader@example.com", username="uploader")
    api_client.force_login(user)

    response = api_client.post(
        reverse("attachment-list-create"),
        {
            "file": SimpleUploadedFile(
                "photo.png",
                b"image-bytes",
                content_type="image/png",
            ),
            "comment": "Screenshot",
        },
        format="multipart",
    )

    assert response.status_code == 201
    payload = response.json()["data"]["attachment"]
    attachment = Attachment.objects.get(id=payload["id"])
    assert payload == {
        "id": str(attachment.id),
        "filename": "photo.png",
        "content_type": "image/png",
        "size_bytes": len(b"image-bytes"),
        "comment": "Screenshot",
        "created_at": attachment.created_at.isoformat().replace("+00:00", "Z"),
        "uploaded_by": {"id": str(user.id), "username": "uploader"},
        "status": "uploaded",
    }
    assert attachment.binding_type == AttachmentBindingType.UNBOUND
    assert attachment_absolute_path(attachment.storage_key).read_bytes() == b"image-bytes"


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/chat-app-test-media-limits")
def test_attachment_upload_rejects_oversized_generic_and_image_files(api_client: APIClient) -> None:
    user = create_user(email="limits@example.com", username="limits")
    api_client.force_login(user)

    oversized_file = api_client.post(
        reverse("attachment-list-create"),
        {
            "file": SimpleUploadedFile(
                "dump.bin",
                b"x" * (20 * 1024 * 1024 + 1),
                content_type="application/octet-stream",
            ),
        },
        format="multipart",
    )
    oversized_image = api_client.post(
        reverse("attachment-list-create"),
        {
            "file": SimpleUploadedFile(
                "image.png",
                b"x" * (3 * 1024 * 1024 + 1),
                content_type="image/png",
            ),
        },
        format="multipart",
    )

    assert oversized_file.status_code == 422
    assert oversized_image.status_code == 422
    assert Attachment.objects.count() == 0


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/chat-app-test-media-access")
def test_attachment_metadata_and_download_require_current_room_access(
    api_client: APIClient,
) -> None:
    owner = create_user(email="owner@example.com", username="owner")
    member = create_user(email="member@example.com", username="member")
    outsider = create_user(email="outsider@example.com", username="outsider")
    room = create_room(owner=owner, name="files-room", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=room,
        user=member,
        role=RoomRole.MEMBER,
        joined_at=timezone.now(),
    )
    message = RoomMessage.objects.create(room=room, sender_user=owner, text="with file")
    attachment = Attachment.objects.create(
        uploaded_by_user=owner,
        storage_key="ab/room-file.txt",
        original_filename="room-file.txt",
        content_type="text/plain",
        size_bytes=5,
        binding_type=AttachmentBindingType.ROOM_MESSAGE,
    )
    attachment_path = attachment_absolute_path(attachment.storage_key)
    attachment_path.parent.mkdir(parents=True, exist_ok=True)
    attachment_path.write_bytes(b"hello")
    RoomMessageAttachment.objects.create(room_message=message, attachment=attachment)

    member_client = APIClient()
    member_client.force_login(member)
    outsider_client = APIClient()
    outsider_client.force_login(outsider)

    metadata_response = member_client.get(
        reverse("attachment-detail", kwargs={"attachment_id": attachment.id})
    )
    download_response = member_client.get(
        reverse("attachment-download", kwargs={"attachment_id": attachment.id})
    )
    outsider_response = outsider_client.get(
        reverse("attachment-detail", kwargs={"attachment_id": attachment.id})
    )

    assert metadata_response.status_code == 200
    assert metadata_response.json()["data"]["attachment"] == {
        "id": str(attachment.id),
        "filename": "room-file.txt",
        "content_type": "text/plain",
        "size_bytes": 5,
        "comment": None,
        "created_at": attachment.created_at.isoformat().replace("+00:00", "Z"),
    }
    assert download_response.status_code == 200
    assert b"".join(download_response.streaming_content) == b"hello"
    assert outsider_response.status_code == 404

    RoomMembership.objects.filter(room=room, user=member).delete()
    revoked_response = member_client.get(
        reverse("attachment-download", kwargs={"attachment_id": attachment.id})
    )
    assert revoked_response.status_code == 404

    RoomMembership.objects.create(
        room=room,
        user=member,
        role=RoomRole.MEMBER,
        joined_at=timezone.now(),
    )
    RoomBan.objects.create(room=room, user=member, banned_by_user=owner)
    banned_response = member_client.get(
        reverse("attachment-detail", kwargs={"attachment_id": attachment.id})
    )
    assert banned_response.status_code == 404


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/chat-app-test-media-delete")
def test_attachment_delete_allows_unbound_owner_only_and_rejects_bound(
    api_client: APIClient,
) -> None:
    owner = create_user(email="delete-owner@example.com", username="deleteowner")
    other = create_user(email="other@example.com", username="other")
    room = create_room(owner=owner, name="bound-room", visibility=RoomVisibility.PUBLIC)
    message = RoomMessage.objects.create(room=room, sender_user=owner, text="bound")

    unbound = Attachment.objects.create(
        uploaded_by_user=owner,
        storage_key="cd/unbound.txt",
        original_filename="unbound.txt",
        content_type="text/plain",
        size_bytes=7,
        binding_type=AttachmentBindingType.UNBOUND,
    )
    unbound_path = attachment_absolute_path(unbound.storage_key)
    unbound_path.parent.mkdir(parents=True, exist_ok=True)
    unbound_path.write_bytes(b"unbound")

    bound = Attachment.objects.create(
        uploaded_by_user=owner,
        storage_key="ef/bound.txt",
        original_filename="bound.txt",
        content_type="text/plain",
        size_bytes=5,
        binding_type=AttachmentBindingType.ROOM_MESSAGE,
    )
    bound_path = attachment_absolute_path(bound.storage_key)
    bound_path.parent.mkdir(parents=True, exist_ok=True)
    bound_path.write_bytes(b"bound")
    RoomMessageAttachment.objects.create(room_message=message, attachment=bound)

    other_client = APIClient()
    other_client.force_login(other)
    owner_client = APIClient()
    owner_client.force_login(owner)

    other_delete = other_client.delete(
        reverse("attachment-detail", kwargs={"attachment_id": unbound.id})
    )
    owner_delete = owner_client.delete(
        reverse("attachment-detail", kwargs={"attachment_id": unbound.id})
    )
    bound_delete = owner_client.delete(
        reverse("attachment-detail", kwargs={"attachment_id": bound.id})
    )

    assert other_delete.status_code == 404
    assert owner_delete.status_code == 204
    assert Attachment.objects.filter(id=unbound.id).exists() is False
    assert unbound_path.exists() is False
    assert bound_delete.status_code == 409
    assert Attachment.objects.filter(id=bound.id).exists() is True
    assert bound_path.exists() is True


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/chat-app-test-media-room-delete")
def test_room_deletion_revokes_attachment_access_and_removes_file(api_client: APIClient) -> None:
    owner = create_user(email="delete-room-owner@example.com", username="delete-room-owner")
    member = create_user(email="delete-room-member@example.com", username="delete-room-member")
    room = create_room(owner=owner, name="deleted-files-room", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=room,
        user=member,
        role=RoomRole.MEMBER,
        joined_at=timezone.now(),
    )
    message = RoomMessage.objects.create(room=room, sender_user=owner, text="with file")
    attachment = Attachment.objects.create(
        uploaded_by_user=owner,
        storage_key="ij/deleted-room.txt",
        original_filename="deleted-room.txt",
        content_type="text/plain",
        size_bytes=12,
        binding_type=AttachmentBindingType.ROOM_MESSAGE,
    )
    path = attachment_absolute_path(attachment.storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"room content")
    RoomMessageAttachment.objects.create(room_message=message, attachment=attachment)

    owner_client = APIClient()
    owner_client.force_login(owner)
    member_client = APIClient()
    member_client.force_login(member)

    assert member_client.get(
        reverse("attachment-detail", kwargs={"attachment_id": attachment.id})
    ).status_code == 200

    delete_response = owner_client.delete(reverse("room-detail", kwargs={"room_id": room.id}))
    detail_response = member_client.get(
        reverse("attachment-detail", kwargs={"attachment_id": attachment.id})
    )
    download_response = member_client.get(
        reverse("attachment-download", kwargs={"attachment_id": attachment.id})
    )

    assert delete_response.status_code == 204
    assert detail_response.status_code == 404
    assert download_response.status_code == 404
    assert Attachment.objects.filter(id=attachment.id).exists() is False
    assert path.exists() is False


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/chat-app-test-media-dialog")
def test_dialog_attachment_access_is_limited_to_participants(api_client: APIClient) -> None:
    alice = create_user(email="alice@example.com", username="alice")
    bob = create_user(email="bob@example.com", username="bob")
    outsider = create_user(email="eve@example.com", username="eve")
    make_friends(alice, bob)
    user_low, user_high = sorted([alice, bob], key=lambda user: str(user.id))
    dialog = Dialog.objects.create(user_low=user_low, user_high=user_high)
    attachment = Attachment.objects.create(
        uploaded_by_user=alice,
        storage_key="gh/dialog.txt",
        original_filename="dialog.txt",
        content_type="text/plain",
        size_bytes=6,
        binding_type=AttachmentBindingType.DIALOG_MESSAGE,
    )
    path = attachment_absolute_path(attachment.storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"dialog")
    dialog_message = dialog.messages.create(sender_user=alice, text="file")
    dialog_message.attachment_bindings.create(attachment=attachment)

    bob_client = APIClient()
    bob_client.force_login(bob)
    outsider_client = APIClient()
    outsider_client.force_login(outsider)

    bob_metadata = bob_client.get(
        reverse("attachment-detail", kwargs={"attachment_id": attachment.id})
    )
    outsider_download = outsider_client.get(
        reverse("attachment-download", kwargs={"attachment_id": attachment.id})
    )

    assert bob_metadata.status_code == 200
    assert (
        outsider_download.status_code
        == 404
    )
