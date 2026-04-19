import asyncio

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from ..models import DialogMessage, RoomMessage
from ..realtime.groups import PRESENCE_GROUP, dialog_group, room_group, user_group
from ..realtime.serializers import build_broadcast_event, build_control_event
from ..serializers import (
    _isoformat,
    serialize_dialog_message,
    serialize_dialog_summary_for_user,
    serialize_room_message,
)
from ..services import get_dialog_unread_count
from ...social.serializers import (
    serialize_friend_request_update,
    serialize_incoming_friend_request,
)


def _dispatch_group_message(group_name: str, message: dict) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        async_to_sync(channel_layer.group_send)(group_name, message)
    else:
        loop.create_task(channel_layer.group_send(group_name, message))


def _send_group_event(group_name: str, *, event_type: str, payload: dict) -> None:
    _dispatch_group_message(
        group_name,
        build_broadcast_event(event_type=event_type, payload=payload),
    )


def _send_control_event(group_name: str, *, control_type: str, payload: dict) -> None:
    _dispatch_group_message(
        group_name,
        build_control_event(control_type=control_type, payload=payload),
    )


def publish_presence_payload(payload: dict) -> None:
    _send_group_event(PRESENCE_GROUP, event_type="presence.updated", payload=payload)


def publish_room_message_created(message: RoomMessage) -> None:
    _send_group_event(
        room_group(message.room_id),
        event_type="room.message.created",
        payload={"message": serialize_room_message(message)},
    )


def publish_room_message_updated(message: RoomMessage) -> None:
    _send_group_event(
        room_group(message.room_id),
        event_type="room.message.updated",
        payload={"message": serialize_room_message(message)},
    )


def publish_room_message_deleted(*, room_id, message_id) -> None:
    _send_group_event(
        room_group(room_id),
        event_type="room.message.deleted",
        payload={"room_id": str(room_id), "message_id": str(message_id)},
    )


def publish_dialog_message_created(message: DialogMessage) -> None:
    _send_group_event(
        dialog_group(message.dialog_id),
        event_type="dialog.message.created",
        payload={"message": serialize_dialog_message(message)},
    )


def publish_dialog_message_updated(message: DialogMessage) -> None:
    _send_group_event(
        dialog_group(message.dialog_id),
        event_type="dialog.message.updated",
        payload={"message": serialize_dialog_message(message)},
    )


def publish_dialog_message_deleted(*, dialog_id, message_id) -> None:
    _send_group_event(
        dialog_group(dialog_id),
        event_type="dialog.message.deleted",
        payload={"dialog_id": str(dialog_id), "message_id": str(message_id)},
    )


def publish_room_read_updated(*, room_id, user_id, unread_count: int) -> None:
    _send_group_event(
        room_group(room_id),
        event_type="room.read.updated",
        payload={
            "room_id": str(room_id),
            "user_id": str(user_id),
            "unread_count": unread_count,
        },
    )


def publish_dialog_read_updated(*, dialog_id, user_id, unread_count: int) -> None:
    _send_group_event(
        dialog_group(dialog_id),
        event_type="dialog.read.updated",
        payload={
            "dialog_id": str(dialog_id),
            "user_id": str(user_id),
            "unread_count": unread_count,
        },
    )


def publish_friend_request_created(friend_request) -> None:
    _send_group_event(
        user_group(friend_request.to_user_id),
        event_type="friend_request.created",
        payload={"request": serialize_incoming_friend_request(friend_request)},
    )


def publish_friend_request_updated(friend_request) -> None:
    for user_id, other_user in (
        (friend_request.from_user_id, friend_request.to_user),
        (friend_request.to_user_id, friend_request.from_user),
    ):
        _send_group_event(
            user_group(user_id),
            event_type="friend_request.updated",
            payload={
                "request": serialize_friend_request_update(
                    item=friend_request,
                    other_user=other_user,
                )
            },
        )


def publish_dialog_summary_updated(dialog, *, recipients=None, last_message=None) -> None:
    recipient_ids = recipients
    if recipient_ids is None:
        recipient_ids = [dialog.user_low_id, dialog.user_high_id]
    for recipient_id in recipient_ids:
        recipient = dialog.user_low if dialog.user_low_id == recipient_id else dialog.user_high
        _send_group_event(
            user_group(recipient_id),
            event_type="dialog.summary.updated",
            payload={
                "dialog": serialize_dialog_summary_for_user(
                    dialog=dialog,
                    user=recipient,
                    unread_count=get_dialog_unread_count(dialog=dialog, user=recipient),
                    last_message=last_message,
                )
            },
        )


def publish_room_invitation_created(invitation) -> None:
    _send_group_event(
        user_group(invitation.invited_user_id),
        event_type="room.invitation.created",
        payload={
            "invitation": {
                "id": str(invitation.id),
                "room_id": str(invitation.room_id),
                "room_name": invitation.room.name,
                "created_at": _isoformat(invitation.created_at),
            }
        },
    )


def publish_room_membership_updated(*, room_id, user_id, action: str) -> None:
    _send_group_event(
        room_group(room_id),
        event_type="room.membership.updated",
        payload={
            "room_id": str(room_id),
            "user_id": str(user_id),
            "action": action,
        },
    )


def force_room_unsubscribe(*, user_id, room_id) -> None:
    _send_control_event(
        user_group(user_id),
        control_type="membership.force_room_unsubscribe",
        payload={"room_id": str(room_id)},
    )
