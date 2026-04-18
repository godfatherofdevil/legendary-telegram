from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.serializers import serialize_public_user
from apps.chat.models import Dialog, DialogMessage, Room, RoomMembership
from apps.common.enums import RoomVisibility

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


def serialize_dialog_summary(*, dialog: Dialog, other_user: User, unread_count: int, last_message: DialogMessage | None) -> dict:
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


def serialize_dialog_create(dialog: Dialog, other_user: User) -> dict:
    return {
        "id": str(dialog.id),
        "other_user": {"id": str(other_user.id), "username": other_user.username},
        "is_frozen": dialog.is_frozen,
        "created_at": _isoformat(dialog.created_at),
    }
