import io
import sys
import types
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from ..models import Attachment, RoomMessageAttachment
from ..storage import (
    AttachmentObjectNotFoundError,
    S3AttachmentStorage,
    _build_s3_client,
    attachment_absolute_path,
    delete_attachment_from_storage,
    get_attachment_storage_readiness,
    open_attachment_for_download,
)
from ..views import _iter_attachment_chunks
from ...chat.models import Room, RoomMembership, RoomMessage
from ...common.enums import AttachmentBindingType, RoomRole, RoomVisibility

User = get_user_model()


class FakeS3Error(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}
        super().__init__(code)


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict] = {}
        self.buckets: set[str] = {"uploads"}
        self.head_bucket_error: Exception | None = None
        self.get_object_calls: list[dict[str, str]] = []

    def upload_fileobj(self, fileobj, bucket: str, key: str, ExtraArgs: dict | None = None) -> None:
        self.objects[(bucket, key)] = {
            "body": fileobj.read(),
            "content_type": (ExtraArgs or {}).get("ContentType"),
            "metadata": (ExtraArgs or {}).get("Metadata", {}),
        }

    def put_object(self, Bucket: str, Key: str, Body: bytes, **kwargs) -> None:
        self.objects[(Bucket, Key)] = {
            "body": Body,
            "content_type": kwargs.get("ContentType"),
            "metadata": kwargs.get("Metadata", {}),
        }

    def get_object(self, Bucket: str, Key: str, Range: str | None = None) -> dict:
        try:
            item = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise FakeS3Error("NoSuchKey") from exc
        body = item["body"]
        if Range is not None:
            start, end = _parse_fake_s3_range(Range=Range, total_size=len(body))
            body = body[start : end + 1]
        self.get_object_calls.append({"bucket": Bucket, "key": Key, "range": Range})
        return {"Body": io.BytesIO(body)}

    def head_object(self, Bucket: str, Key: str) -> dict:
        try:
            item = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise FakeS3Error("404") from exc
        return {"ContentLength": len(item["body"])}

    def head_bucket(self, Bucket: str) -> dict:
        if self.head_bucket_error is not None:
            raise self.head_bucket_error
        if Bucket not in self.buckets:
            raise FakeS3Error("NoSuchBucket")
        return {}

    def list_buckets(self) -> dict:
        return {"Buckets": [{"Name": bucket} for bucket in sorted(self.buckets)]}

    def delete_object(self, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)


def _parse_fake_s3_range(*, Range: str, total_size: int) -> tuple[int, int]:
    if not Range.startswith("bytes="):
        raise FakeS3Error("InvalidRange")

    start_text, end_text = Range.removeprefix("bytes=").split("-", 1)
    if not start_text:
        suffix_length = int(end_text)
        if suffix_length <= 0:
            raise FakeS3Error("InvalidRange")
        start = max(total_size - suffix_length, 0)
        return (start, total_size - 1)

    start = int(start_text)
    if start >= total_size:
        raise FakeS3Error("InvalidRange")
    end = total_size - 1 if not end_text else int(end_text)
    if end < start:
        raise FakeS3Error("InvalidRange")
    return (start, min(end, total_size - 1))


class TrackingFile:
    def __init__(self, data: bytes) -> None:
        self._buffer = io.BytesIO(data)
        self.closed = False
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self._buffer.read(size)

    def close(self) -> None:
        self.closed = True


class ClosingUploadedFile:
    def __init__(self, data: bytes, name: str) -> None:
        self._buffer = io.BytesIO(data)
        self.name = name
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        return self._buffer.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        return self._buffer.seek(offset, whence)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def fake_s3_client(monkeypatch) -> FakeS3Client:
    client = FakeS3Client()
    monkeypatch.setattr("apps.attachments.storage._build_s3_client", lambda: client)
    return client


def test_s3_client_uses_path_style_addressing(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeConfig:
        def __init__(self, *, s3: dict[str, str]) -> None:
            self.s3 = s3

    def fake_client(service_name: str, **kwargs):
        captured["service_name"] = service_name
        captured["kwargs"] = kwargs
        return object()

    fake_boto3 = types.SimpleNamespace(client=fake_client)
    fake_botocore_config = types.SimpleNamespace(Config=FakeConfig)
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore.config", fake_botocore_config)

    _build_s3_client()

    assert captured["service_name"] == "s3"
    config = captured["kwargs"]["config"]
    assert isinstance(config, FakeConfig)
    assert getattr(config, "s3") == {"addressing_style": "path"}


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


def test_iter_attachment_chunks_reads_in_bounded_chunks_and_closes_file(monkeypatch) -> None:
    file_handle = TrackingFile(b"0123456789")
    monkeypatch.setattr("apps.attachments.views.STREAM_CHUNK_SIZE", 4)

    chunks = list(_iter_attachment_chunks(file_handle, remaining_bytes=None))

    assert chunks == [b"0123", b"4567", b"89"]
    assert file_handle.read_sizes == [4, 4, 4, 4]
    assert file_handle.closed is True


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
def test_s3_attachment_storage_crud(fake_s3_client: FakeS3Client) -> None:
    storage = S3AttachmentStorage()

    storage.put_bytes(
        storage_key="ab/file.txt",
        data=b"hello",
        content_type="text/plain",
        original_filename="file.txt",
    )

    assert storage.exists(storage_key="ab/file.txt") is True
    assert storage.size(storage_key="ab/file.txt") == 5
    assert storage.open(storage_key="ab/file.txt").read() == b"hello"
    assert fake_s3_client.objects[("uploads", "ab/file.txt")]["metadata"] == {
        "original_filename": "file.txt"
    }

    storage.delete(storage_key="ab/file.txt")

    assert storage.exists(storage_key="ab/file.txt") is False
    with pytest.raises(AttachmentObjectNotFoundError):
        storage.size(storage_key="ab/file.txt")


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
def test_s3_attachment_storage_accepts_upload_stream_closed_by_backend(
    fake_s3_client: FakeS3Client,
) -> None:
    storage = S3AttachmentStorage()
    uploaded_file = ClosingUploadedFile(b"hello", "file.txt")

    def upload_fileobj(fileobj, bucket: str, key: str, ExtraArgs: dict | None = None) -> None:
        fake_s3_client.objects[(bucket, key)] = {
            "body": fileobj.read(),
            "content_type": (ExtraArgs or {}).get("ContentType"),
            "metadata": (ExtraArgs or {}).get("Metadata", {}),
        }
        fileobj.close()

    fake_s3_client.upload_fileobj = upload_fileobj

    storage.put_uploaded_file(
        storage_key="ab/file.txt",
        uploaded_file=uploaded_file,
        content_type="text/plain",
        original_filename="file.txt",
    )

    assert uploaded_file.closed is True
    assert fake_s3_client.objects[("uploads", "ab/file.txt")]["body"] == b"hello"


@pytest.mark.django_db
@override_settings(
    MEDIA_ROOT="/tmp/chat-app-test-media-s3-fallback",
    ATTACHMENTS_STORAGE_BACKEND="s3",
    ATTACHMENTS_S3_ENDPOINT_URL="http://minio:9000",
    ATTACHMENTS_S3_BUCKET="uploads",
    ATTACHMENTS_S3_ACCESS_KEY_ID="minioadmin",
    ATTACHMENTS_S3_SECRET_ACCESS_KEY="minioadmin",
    ATTACHMENTS_S3_USE_SSL=False,
    ATTACHMENTS_S3_VERIFY_SSL=False,
)
def test_open_attachment_for_download_falls_back_to_legacy_filesystem_when_s3_object_is_missing(
    fake_s3_client: FakeS3Client,
) -> None:
    legacy_path = attachment_absolute_path("legacy/file.txt")
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(b"legacy-bytes")

    file_handle = open_attachment_for_download(storage_key="legacy/file.txt")

    assert file_handle.read() == b"legacy-bytes"
    file_handle.close()
    assert ("uploads", "legacy/file.txt") not in fake_s3_client.objects


@pytest.mark.django_db
@override_settings(
    MEDIA_ROOT="/tmp/chat-app-test-media-s3-cleanup",
    ATTACHMENTS_STORAGE_BACKEND="s3",
    ATTACHMENTS_S3_ENDPOINT_URL="http://minio:9000",
    ATTACHMENTS_S3_BUCKET="uploads",
    ATTACHMENTS_S3_ACCESS_KEY_ID="minioadmin",
    ATTACHMENTS_S3_SECRET_ACCESS_KEY="minioadmin",
    ATTACHMENTS_S3_USE_SSL=False,
    ATTACHMENTS_S3_VERIFY_SSL=False,
)
def test_delete_attachment_from_storage_also_removes_legacy_filesystem_blob(
    fake_s3_client: FakeS3Client,
) -> None:
    legacy_path = attachment_absolute_path("cleanup/file.txt")
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(b"legacy-bytes")
    fake_s3_client.put_object(
        Bucket="uploads",
        Key="cleanup/file.txt",
        Body=b"s3-bytes",
        ContentType="text/plain",
        Metadata={"original_filename": "file.txt"},
    )

    delete_attachment_from_storage(storage_key="cleanup/file.txt")

    assert legacy_path.exists() is False
    assert ("uploads", "cleanup/file.txt") not in fake_s3_client.objects


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
def test_s3_attachment_storage_readiness_succeeds_when_bucket_exists(
    fake_s3_client: FakeS3Client,
) -> None:
    is_ready, checks = get_attachment_storage_readiness()

    assert is_ready is True
    assert checks["attachment_storage_backend"] == "s3"
    assert checks["object_storage"] == "ok"
    assert checks["object_storage_bucket"] == "uploads"


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
def test_s3_attachment_storage_readiness_fails_when_bucket_is_missing(
    fake_s3_client: FakeS3Client,
) -> None:
    fake_s3_client.buckets.clear()

    is_ready, checks = get_attachment_storage_readiness()

    assert is_ready is False
    assert checks["attachment_storage_backend"] == "s3"
    assert checks["object_storage"] == "error"
    assert checks["object_storage_bucket"] == "uploads"
    assert checks["object_storage_error"] == "NoSuchBucket"


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
def test_s3_attachment_storage_readiness_uses_bucket_listing_fallback_on_head_bucket_error(
    fake_s3_client: FakeS3Client,
) -> None:
    fake_s3_client.head_bucket_error = FakeS3Error("BadRequest")

    is_ready, checks = get_attachment_storage_readiness()

    assert is_ready is True
    assert checks["attachment_storage_backend"] == "s3"
    assert checks["object_storage"] == "ok"
    assert checks["object_storage_bucket"] == "uploads"


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
def test_attachment_upload_and_download_preserve_contract_with_s3_backend(
    api_client: APIClient, fake_s3_client: FakeS3Client
) -> None:
    user = create_user(email="s3-uploader@example.com", username="s3uploader")
    api_client.force_login(user)

    response = api_client.post(
        reverse("attachment-list-create"),
        {
            "file": SimpleUploadedFile(
                "photo.png",
                b"s3-image",
                content_type="image/png",
            ),
            "comment": "Stored in object storage",
        },
        format="multipart",
    )

    assert response.status_code == 201
    payload = response.json()["data"]["attachment"]
    attachment = Attachment.objects.get(id=payload["id"])

    assert fake_s3_client.objects[("uploads", attachment.storage_key)]["body"] == b"s3-image"

    metadata_response = api_client.get(
        reverse("attachment-detail", kwargs={"attachment_id": attachment.id})
    )
    download_response = api_client.get(
        reverse("attachment-download", kwargs={"attachment_id": attachment.id})
    )

    assert metadata_response.status_code == 200
    assert metadata_response.json()["data"]["attachment"]["filename"] == "photo.png"
    assert download_response.status_code == 200
    assert download_response.streaming is True
    assert download_response["Content-Disposition"].startswith("inline;")
    assert download_response["Accept-Ranges"] == "bytes"
    assert b"".join(download_response.streaming_content) == b"s3-image"


@pytest.mark.django_db
@override_settings(
    MEDIA_ROOT="/tmp/chat-app-test-media-s3-legacy-download",
    ATTACHMENTS_STORAGE_BACKEND="s3",
    ATTACHMENTS_S3_ENDPOINT_URL="http://minio:9000",
    ATTACHMENTS_S3_BUCKET="uploads",
    ATTACHMENTS_S3_ACCESS_KEY_ID="minioadmin",
    ATTACHMENTS_S3_SECRET_ACCESS_KEY="minioadmin",
    ATTACHMENTS_S3_USE_SSL=False,
    ATTACHMENTS_S3_VERIFY_SSL=False,
)
def test_attachment_download_endpoint_serves_legacy_filesystem_blob_during_s3_cutover(
    api_client: APIClient,
    fake_s3_client: FakeS3Client,
) -> None:
    owner = create_user(email="legacy-owner@example.com", username="legacyowner")
    member = create_user(email="legacy-member@example.com", username="legacymember")
    room = create_room(owner=owner, name="legacy-room", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=room,
        user=member,
        role=RoomRole.MEMBER,
        joined_at=timezone.now(),
    )
    message = RoomMessage.objects.create(room=room, sender_user=owner, text="legacy file")
    attachment = Attachment.objects.create(
        uploaded_by_user=owner,
        storage_key="legacy/room-file.txt",
        original_filename="room-file.txt",
        content_type="text/plain",
        size_bytes=12,
        binding_type=AttachmentBindingType.ROOM_MESSAGE,
    )
    RoomMessageAttachment.objects.create(room_message=message, attachment=attachment)
    legacy_path = attachment_absolute_path(attachment.storage_key)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(b"legacy-bytes")

    member_client = APIClient()
    member_client.force_login(member)

    response = member_client.get(
        reverse("attachment-download", kwargs={"attachment_id": attachment.id})
    )

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"legacy-bytes"
    assert ("uploads", attachment.storage_key) not in fake_s3_client.objects


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
def test_attachment_download_supports_single_range_requests_for_s3_media(
    fake_s3_client: FakeS3Client,
) -> None:
    owner = create_user(email="s3-range-owner@example.com", username="s3rangeowner")
    room = create_room(owner=owner, name="s3-range-room", visibility=RoomVisibility.PUBLIC)
    message = RoomMessage.objects.create(room=room, sender_user=owner, text="with ranged file")
    attachment = Attachment.objects.create(
        uploaded_by_user=owner,
        storage_key="range/video.mp4",
        original_filename="video.mp4",
        content_type="video/mp4",
        size_bytes=10,
        binding_type=AttachmentBindingType.ROOM_MESSAGE,
    )
    RoomMessageAttachment.objects.create(room_message=message, attachment=attachment)
    fake_s3_client.put_object(
        Bucket="uploads",
        Key=attachment.storage_key,
        Body=b"0123456789",
        ContentType=attachment.content_type,
        Metadata={"original_filename": attachment.original_filename},
    )

    owner_client = APIClient()
    owner_client.force_login(owner)

    response = owner_client.get(
        reverse("attachment-download", kwargs={"attachment_id": attachment.id}),
        HTTP_RANGE="bytes=2-5",
    )

    assert response.status_code == 206
    assert response.streaming is True
    assert response["Accept-Ranges"] == "bytes"
    assert response["Content-Range"] == "bytes 2-5/10"
    assert response["Content-Length"] == "4"
    assert response["Content-Disposition"].startswith("inline;")
    assert b"".join(response.streaming_content) == b"2345"
    assert fake_s3_client.get_object_calls[-1]["range"] == "bytes=2-5"


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
def test_attachment_download_supports_open_ended_and_suffix_ranges_for_s3_media(
    fake_s3_client: FakeS3Client,
) -> None:
    owner = create_user(email="s3-suffix-owner@example.com", username="s3suffixowner")
    room = create_room(owner=owner, name="s3-suffix-room", visibility=RoomVisibility.PUBLIC)
    message = RoomMessage.objects.create(room=room, sender_user=owner, text="with ranged file")
    attachment = Attachment.objects.create(
        uploaded_by_user=owner,
        storage_key="range/song.mp3",
        original_filename="song.mp3",
        content_type="audio/mpeg",
        size_bytes=10,
        binding_type=AttachmentBindingType.ROOM_MESSAGE,
    )
    RoomMessageAttachment.objects.create(room_message=message, attachment=attachment)
    fake_s3_client.put_object(
        Bucket="uploads",
        Key=attachment.storage_key,
        Body=b"0123456789",
        ContentType=attachment.content_type,
        Metadata={"original_filename": attachment.original_filename},
    )

    owner_client = APIClient()
    owner_client.force_login(owner)

    open_ended_response = owner_client.get(
        reverse("attachment-download", kwargs={"attachment_id": attachment.id}),
        HTTP_RANGE="bytes=4-",
    )
    suffix_response = owner_client.get(
        reverse("attachment-download", kwargs={"attachment_id": attachment.id}),
        HTTP_RANGE="bytes=-3",
    )

    assert open_ended_response.status_code == 206
    assert open_ended_response["Content-Range"] == "bytes 4-9/10"
    assert open_ended_response["Content-Length"] == "6"
    assert open_ended_response["Content-Disposition"].startswith("inline;")
    assert b"".join(open_ended_response.streaming_content) == b"456789"

    assert suffix_response.status_code == 206
    assert suffix_response["Content-Range"] == "bytes 7-9/10"
    assert suffix_response["Content-Length"] == "3"
    assert suffix_response["Content-Disposition"].startswith("inline;")
    assert b"".join(suffix_response.streaming_content) == b"789"


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
def test_attachment_download_rejects_unsatisfiable_range_requests(
    fake_s3_client: FakeS3Client,
) -> None:
    owner = create_user(email="s3-unsat-owner@example.com", username="s3unsatowner")
    room = create_room(owner=owner, name="s3-unsat-room", visibility=RoomVisibility.PUBLIC)
    message = RoomMessage.objects.create(room=room, sender_user=owner, text="with file")
    attachment = Attachment.objects.create(
        uploaded_by_user=owner,
        storage_key="range/audio.mp3",
        original_filename="audio.mp3",
        content_type="audio/mpeg",
        size_bytes=5,
        binding_type=AttachmentBindingType.ROOM_MESSAGE,
    )
    RoomMessageAttachment.objects.create(room_message=message, attachment=attachment)
    fake_s3_client.put_object(
        Bucket="uploads",
        Key=attachment.storage_key,
        Body=b"12345",
        ContentType=attachment.content_type,
        Metadata={"original_filename": attachment.original_filename},
    )

    owner_client = APIClient()
    owner_client.force_login(owner)

    response = owner_client.get(
        reverse("attachment-download", kwargs={"attachment_id": attachment.id}),
        HTTP_RANGE="bytes=10-20",
    )

    assert response.status_code == 416
    assert response["Accept-Ranges"] == "bytes"
    assert response["Content-Range"] == "bytes */5"


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
def test_room_deletion_removes_s3_object_and_revokes_attachment_access(
    fake_s3_client: FakeS3Client
) -> None:
    owner = create_user(email="s3-owner@example.com", username="s3owner")
    member = create_user(email="s3-member@example.com", username="s3member")
    outsider = create_user(email="s3-outsider@example.com", username="s3outsider")
    room = create_room(owner=owner, name="s3-room", visibility=RoomVisibility.PUBLIC)
    RoomMembership.objects.create(
        room=room,
        user=member,
        role=RoomRole.MEMBER,
        joined_at=timezone.now(),
    )
    message = RoomMessage.objects.create(room=room, sender_user=owner, text="with s3 file")
    attachment = Attachment.objects.create(
        uploaded_by_user=owner,
        storage_key="aa/object.txt",
        original_filename="object.txt",
        content_type="text/plain",
        size_bytes=10,
        binding_type=AttachmentBindingType.ROOM_MESSAGE,
    )
    fake_s3_client.put_object(
        Bucket="uploads",
        Key=attachment.storage_key,
        Body=b"room-bytes",
        ContentType=attachment.content_type,
        Metadata={"original_filename": attachment.original_filename},
    )
    RoomMessageAttachment.objects.create(room_message=message, attachment=attachment)

    member_client = APIClient()
    member_client.force_login(member)
    outsider_client = APIClient()
    outsider_client.force_login(outsider)
    owner_client = APIClient()
    owner_client.force_login(owner)

    assert member_client.get(
        reverse("attachment-download", kwargs={"attachment_id": attachment.id})
    ).status_code == 200
    assert outsider_client.get(
        reverse("attachment-detail", kwargs={"attachment_id": attachment.id})
    ).status_code == 404

    delete_response = owner_client.delete(reverse("room-detail", kwargs={"room_id": room.id}))

    assert delete_response.status_code == 204
    assert Attachment.objects.filter(id=attachment.id).exists() is False
    assert ("uploads", attachment.storage_key) not in fake_s3_client.objects
    assert member_client.get(
        reverse("attachment-download", kwargs={"attachment_id": attachment.id})
    ).status_code == 404


@pytest.mark.django_db
@override_settings(
    MEDIA_ROOT="/tmp/chat-app-test-media-backfill",
    ATTACHMENTS_STORAGE_BACKEND="s3",
    ATTACHMENTS_S3_ENDPOINT_URL="http://minio:9000",
    ATTACHMENTS_S3_BUCKET="uploads",
    ATTACHMENTS_S3_ACCESS_KEY_ID="minioadmin",
    ATTACHMENTS_S3_SECRET_ACCESS_KEY="minioadmin",
    ATTACHMENTS_S3_USE_SSL=False,
    ATTACHMENTS_S3_VERIFY_SSL=False,
)
def test_backfill_command_is_idempotent(fake_s3_client: FakeS3Client) -> None:
    user = create_user(email="backfill@example.com", username="backfill")
    attachment = Attachment.objects.create(
        uploaded_by_user=user,
        storage_key="bf/existing.txt",
        original_filename="existing.txt",
        content_type="text/plain",
        size_bytes=12,
        binding_type=AttachmentBindingType.UNBOUND,
    )
    source_path = attachment_absolute_path(attachment.storage_key)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"legacy-bytes")

    stdout_first = io.StringIO()
    stdout_second = io.StringIO()

    call_command("backfill_attachments_to_object_storage", stdout=stdout_first)
    call_command("backfill_attachments_to_object_storage", stdout=stdout_second)

    assert fake_s3_client.objects[("uploads", attachment.storage_key)]["body"] == b"legacy-bytes"
    assert "copied=1" in stdout_first.getvalue()
    assert "skipped_existing=1" in stdout_second.getvalue()


@pytest.mark.django_db
@override_settings(
    MEDIA_ROOT="/tmp/chat-app-test-media-backfill-failure",
    ATTACHMENTS_STORAGE_BACKEND="s3",
    ATTACHMENTS_S3_ENDPOINT_URL="http://minio:9000",
    ATTACHMENTS_S3_BUCKET="uploads",
    ATTACHMENTS_S3_ACCESS_KEY_ID="minioadmin",
    ATTACHMENTS_S3_SECRET_ACCESS_KEY="minioadmin",
    ATTACHMENTS_S3_USE_SSL=False,
    ATTACHMENTS_S3_VERIFY_SSL=False,
)
def test_backfill_command_reports_missing_or_invalid_source_files(
    fake_s3_client: FakeS3Client,
) -> None:
    user = create_user(email="backfill-failure@example.com", username="backfillfailure")
    good = Attachment.objects.create(
        uploaded_by_user=user,
        storage_key="bf/good.txt",
        original_filename="good.txt",
        content_type="text/plain",
        size_bytes=4,
        binding_type=AttachmentBindingType.UNBOUND,
    )
    bad = Attachment.objects.create(
        uploaded_by_user=user,
        storage_key="bf/missing.txt",
        original_filename="missing.txt",
        content_type="text/plain",
        size_bytes=7,
        binding_type=AttachmentBindingType.UNBOUND,
    )
    good_path = attachment_absolute_path(good.storage_key)
    good_path.parent.mkdir(parents=True, exist_ok=True)
    good_path.write_bytes(b"good")
    bad_path = Path(str(attachment_absolute_path(bad.storage_key)))
    if bad_path.exists():
        bad_path.unlink()

    stdout = io.StringIO()
    call_command("backfill_attachments_to_object_storage", stdout=stdout)

    assert fake_s3_client.objects[("uploads", good.storage_key)]["body"] == b"good"
    assert ("uploads", bad.storage_key) not in fake_s3_client.objects
    assert "copied=1" in stdout.getvalue()
    assert "missing_source=1" in stdout.getvalue()
