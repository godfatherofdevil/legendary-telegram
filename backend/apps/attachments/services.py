import mimetypes
import os
import uuid
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from ..accounts.serializers import serialize_public_user
from .models import Attachment, DialogMessageAttachment, RoomMessageAttachment
from .storage import delete_attachment_from_storage, get_attachment_storage
from ..chat.models import RoomBan, RoomMembership
from ..common.enums import AttachmentBindingType

User = get_user_model()

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_SIZE_BYTES = 3 * 1024 * 1024


class AttachmentConflictError(Exception):
    pass


class AttachmentValidationError(Exception):
    pass


def delete_attachment_file(*, storage_key: str) -> None:
    delete_attachment_from_storage(storage_key=storage_key)


def _guess_content_type(uploaded_file: UploadedFile) -> str:
    content_type = (uploaded_file.content_type or "").strip()
    if content_type:
        return content_type
    guessed_type, _encoding = mimetypes.guess_type(uploaded_file.name)
    return guessed_type or "application/octet-stream"


def _validate_uploaded_file(uploaded_file: UploadedFile) -> tuple[int, str]:
    size_bytes = uploaded_file.size or 0
    if size_bytes <= 0:
        raise AttachmentValidationError("Uploaded file must not be empty.")

    content_type = _guess_content_type(uploaded_file)
    max_size = MAX_IMAGE_SIZE_BYTES if content_type.startswith("image/") else MAX_FILE_SIZE_BYTES
    if size_bytes > max_size:
        raise AttachmentValidationError("Uploaded file exceeds the allowed size limit.")
    return size_bytes, content_type


def _build_storage_key(original_filename: str) -> str:
    suffix = Path(original_filename).suffix
    token = uuid.uuid4().hex
    return f"{token[:2]}/{token}{suffix}"


def _serialize_attachment_base(attachment: Attachment) -> dict:
    return {
        "id": str(attachment.id),
        "filename": attachment.original_filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "comment": attachment.comment,
        "created_at": attachment.created_at.isoformat().replace("+00:00", "Z"),
    }


def serialize_attachment_created(attachment: Attachment) -> dict:
    return {
        **_serialize_attachment_base(attachment),
        "uploaded_by": serialize_public_user(attachment.uploaded_by_user, include_presence=False),
        "status": "uploaded",
    }


def serialize_attachment_metadata(attachment: Attachment) -> dict:
    return _serialize_attachment_base(attachment)


def require_attachment_access(*, attachment: Attachment, user: User) -> None:
    if attachment.deleted_at is not None:
        raise Attachment.DoesNotExist

    if attachment.binding_type == AttachmentBindingType.UNBOUND:
        if attachment.uploaded_by_user_id != user.id:
            raise Attachment.DoesNotExist
        return

    if attachment.binding_type == AttachmentBindingType.ROOM_MESSAGE:
        binding = (
            RoomMessageAttachment.objects.select_related("room_message__room")
            .filter(attachment=attachment)
            .first()
        )
        if binding is None:
            raise Attachment.DoesNotExist
        room = binding.room_message.room
        is_member = RoomMembership.objects.filter(room=room, user=user).exists()
        is_banned = RoomBan.objects.filter(room=room, user=user, removed_at__isnull=True).exists()
        if not is_member or is_banned:
            raise Attachment.DoesNotExist
        return

    if attachment.binding_type == AttachmentBindingType.DIALOG_MESSAGE:
        binding = (
            DialogMessageAttachment.objects.select_related("dialog_message__dialog")
            .filter(attachment=attachment)
            .first()
        )
        if binding is None:
            raise Attachment.DoesNotExist
        dialog = binding.dialog_message.dialog
        if dialog.user_low_id != user.id and dialog.user_high_id != user.id:
            raise Attachment.DoesNotExist
        return

    raise Attachment.DoesNotExist


@transaction.atomic
def create_attachment(
    *, uploaded_by_user: User, uploaded_file: UploadedFile, comment: str | None
) -> Attachment:
    size_bytes, content_type = _validate_uploaded_file(uploaded_file)
    original_filename = os.path.basename(uploaded_file.name)
    storage_key = _build_storage_key(original_filename)
    storage = get_attachment_storage()

    try:
        storage.put_uploaded_file(
            storage_key=storage_key,
            uploaded_file=uploaded_file,
            content_type=content_type,
            original_filename=original_filename,
        )
    except Exception:
        raise

    try:
        attachment = Attachment.objects.create(
            uploaded_by_user=uploaded_by_user,
            storage_key=storage_key,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            comment=comment,
        )
    except Exception:
        storage.delete(storage_key=storage_key)
        raise

    return attachment


@transaction.atomic
def delete_unbound_attachment(*, attachment: Attachment, actor: User) -> None:
    if attachment.uploaded_by_user_id != actor.id:
        raise Attachment.DoesNotExist
    if attachment.binding_type != AttachmentBindingType.UNBOUND:
        raise AttachmentConflictError("Bound attachments must be deleted through message deletion.")
    attachment.delete()


@transaction.atomic
def delete_room_message_attachments(*, message) -> None:
    attachment_ids = list(message.attachment_bindings.values_list("attachment_id", flat=True))
    if attachment_ids:
        Attachment.objects.filter(id__in=attachment_ids).delete()


@transaction.atomic
def delete_dialog_message_attachments(*, message) -> None:
    attachment_ids = list(message.attachment_bindings.values_list("attachment_id", flat=True))
    if attachment_ids:
        Attachment.objects.filter(id__in=attachment_ids).delete()
