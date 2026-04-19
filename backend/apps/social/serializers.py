from django.contrib.auth import get_user_model
from rest_framework import serializers

from ..accounts.serializers import serialize_public_user

User = get_user_model()


class FriendRequestCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    message = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PeerBanCreateSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()


def _isoformat(value):
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def serialize_friend_item(*, user: User, friend_since, include_presence: bool) -> dict:
    return {
        "user": serialize_public_user(user, include_presence=include_presence),
        "friend_since": _isoformat(friend_since),
    }


def serialize_incoming_friend_request(item) -> dict:
    return {
        "id": str(item.id),
        "from_user": serialize_public_user(item.from_user, include_presence=False),
        "message": item.message,
        "created_at": _isoformat(item.created_at),
    }


def serialize_outgoing_friend_request(item) -> dict:
    return {
        "id": str(item.id),
        "to_user": serialize_public_user(item.to_user, include_presence=False),
        "message": item.message,
        "created_at": _isoformat(item.created_at),
    }


def serialize_created_friend_request(item) -> dict:
    return {
        "id": str(item.id),
        "to_user": serialize_public_user(item.to_user, include_presence=False),
        "message": item.message,
        "status": item.status,
        "created_at": _isoformat(item.created_at),
    }


def serialize_friend_request_update(*, item, other_user: User) -> dict:
    return {
        "id": str(item.id),
        "status": item.status,
        "other_user": serialize_public_user(other_user, include_presence=False),
        "responded_at": _isoformat(item.responded_at),
    }


def serialize_peer_ban(item) -> dict:
    return {
        "user": serialize_public_user(item.target_user, include_presence=False),
        "created_at": _isoformat(item.created_at),
    }
