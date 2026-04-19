from django.contrib.auth import get_user_model
from rest_framework import serializers

from ..accounts.serializers import serialize_public_user
from .models import (
    Dialog,
    DialogMessage,
    Room,
    RoomBan,
    RoomInvitation,
    RoomMembership,
    RoomMessage,
)
from ..common.enums import ChatType, RoomVisibility

User = get_user_model()


class RoomCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    visibility = serializers.ChoiceField(choices=RoomVisibility.choices)


class RoomUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    visibility = serializers.ChoiceField(choices=RoomVisibility.choices, required=False)


class DialogCreateSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()


class UsernameLookupSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)


class UserIdSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()


class MessageCreateSerializer(serializers.Serializer):
    text = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    reply_to_message_id = serializers.UUIDField(required=False, allow_null=True)
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )


class MessageUpdateSerializer(serializers.Serializer):
    text = serializers.CharField(required=False, allow_blank=True, allow_null=True)


def _isoformat(value):
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def serialize_room_owner(room: Room) -> dict:
    return {"id": str(room.owner_user.id), "username": room.owner_user.username}


def serialize_room_list_item(room: Room) -> dict:
    return {
        "id": str(room.id),
        "name": room.name,
        "description": room.description,
        "visibility": room.visibility,
        "member_count": getattr(room, "member_count", room.memberships.count()),
        "owner": serialize_room_owner(room),
    }


def serialize_joined_room_item(*, membership: RoomMembership, unread_count: int) -> dict:
    room = membership.room
    return {
        "id": str(room.id),
        "name": room.name,
        "description": room.description,
        "visibility": room.visibility,
        "member_count": membership.member_count,
        "unread_count": unread_count,
    }


def serialize_room_detail(*, room: Room, current_user_role: str, is_member: bool) -> dict:
    admin_memberships = list(
        room.memberships.select_related("user").filter(role__in=["owner", "admin"])
    )
    admin_memberships.sort(
        key=lambda membership: (
            0 if membership.role == "owner" else 1,
            membership.user.username,
            str(membership.user.id),
        )
    )
    admins = []
    for membership in admin_memberships:
        admins.append({"id": str(membership.user.id), "username": membership.user.username})
    return {
        "id": str(room.id),
        "name": room.name,
        "description": room.description,
        "visibility": room.visibility,
        "owner": serialize_room_owner(room),
        "admins": admins,
        "member_count": room.memberships.count(),
        "created_at": _isoformat(room.created_at),
        "current_user_role": current_user_role,
        "is_member": is_member,
    }


def serialize_room_update(room: Room) -> dict:
    return {
        "id": str(room.id),
        "name": room.name,
        "description": room.description,
        "visibility": room.visibility,
    }


def serialize_room_create(room: Room) -> dict:
    return {
        "id": str(room.id),
        "name": room.name,
        "description": room.description,
        "visibility": room.visibility,
        "owner": serialize_room_owner(room),
        "created_at": _isoformat(room.created_at),
    }


def serialize_room_member(membership: RoomMembership) -> dict:
    return {
        "user": serialize_public_user(membership.user, include_presence=True),
        "role": membership.role,
    }


def serialize_room_invitation(invitation: RoomInvitation) -> dict:
    return {
        "id": str(invitation.id),
        "room_id": str(invitation.room_id),
        "user": serialize_public_user(invitation.invited_user, include_presence=False),
        "created_at": _isoformat(invitation.created_at),
    }


def serialize_room_ban(ban: RoomBan) -> dict:
    return {
        "user": serialize_public_user(ban.user, include_presence=False),
        "banned_by": serialize_public_user(ban.banned_by_user, include_presence=False),
        "created_at": _isoformat(ban.created_at),
    }


def serialize_dialog_summary(
    *, dialog: Dialog, other_user: User, unread_count: int, last_message: DialogMessage | None
) -> dict:
    payload = {
        "id": str(dialog.id),
        "other_user": serialize_public_user(other_user, include_presence=True),
        "unread_count": unread_count,
        "is_frozen": dialog.is_frozen,
    }
    if last_message is not None:
        payload["last_message"] = {
            "id": str(last_message.id),
            "sender_id": str(last_message.sender_user_id),
            "text": last_message.text,
            "created_at": _isoformat(last_message.created_at),
        }
    else:
        payload["last_message"] = None
    return payload


def serialize_dialog_summary_for_user(
    *, dialog: Dialog, user: User, unread_count: int, last_message: DialogMessage | None
) -> dict:
    other_user = dialog.user_high if dialog.user_low_id == user.id else dialog.user_low
    return serialize_dialog_summary(
        dialog=dialog,
        other_user=other_user,
        unread_count=unread_count,
        last_message=last_message,
    )


def serialize_dialog_create(dialog: Dialog, other_user: User) -> dict:
    return {
        "id": str(dialog.id),
        "other_user": {"id": str(other_user.id), "username": other_user.username},
        "is_frozen": dialog.is_frozen,
        "created_at": _isoformat(dialog.created_at),
    }


def serialize_message_attachment(attachment) -> dict:
    return {
        "id": str(attachment.id),
        "filename": attachment.original_filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "comment": attachment.comment,
        "download_url": f"/api/v1/attachments/{attachment.id}/download",
    }


def serialize_message_reply(reply_to_message) -> dict | None:
    if reply_to_message is None:
        return None
    return {
        "id": str(reply_to_message.id),
        "sender": serialize_public_user(reply_to_message.sender_user, include_presence=False),
        "text": reply_to_message.text or "",
    }


def _serialize_message(*, message, chat_type: str, chat_id) -> dict:
    attachments = [
        serialize_message_attachment(binding.attachment)
        for binding in getattr(message, "attachment_bindings").all()
    ]
    return {
        "id": str(message.id),
        "chat_type": chat_type,
        "chat_id": str(chat_id),
        "sender": serialize_public_user(message.sender_user, include_presence=False),
        "text": message.text or "",
        "reply_to": serialize_message_reply(message.reply_to_message),
        "attachments": attachments,
        "is_edited": message.is_edited,
        "created_at": _isoformat(message.created_at),
        "updated_at": _isoformat(message.updated_at),
    }


def serialize_room_message(message: RoomMessage) -> dict:
    return _serialize_message(message=message, chat_type=ChatType.ROOM, chat_id=message.room_id)


def serialize_dialog_message(message: DialogMessage) -> dict:
    return _serialize_message(message=message, chat_type=ChatType.DIALOG, chat_id=message.dialog_id)
