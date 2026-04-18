import base64
import binascii
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.attachments.models import Attachment
from apps.audit.models import ModerationEvent
from apps.chat.models import Dialog, DialogMessage, DialogReadState, Room, RoomBan, RoomMembership, RoomMessage, RoomReadState
from apps.common.enums import ModerationActionType, RoomRole, RoomVisibility
from apps.social.models import Friendship, PeerBan

User = get_user_model()


class DomainConflictError(Exception):
    pass


class DomainForbiddenError(Exception):
    pass


@dataclass(frozen=True)
class PageWindow:
    offset: int
    limit: int


def encode_cursor(offset: int | None) -> str | None:
    if offset is None:
        return None
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


def decode_cursor(raw_cursor: str | None) -> int:
    if not raw_cursor:
        return 0
    try:
        decoded = base64.urlsafe_b64decode(raw_cursor.encode("ascii")).decode("ascii")
        offset = int(decoded)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("Invalid cursor.") from exc
    if offset < 0:
        raise ValueError("Invalid cursor.")
    return offset


def get_page_window(*, raw_limit: str | None, raw_cursor: str | None, default_limit: int, max_limit: int) -> PageWindow:
    limit = default_limit
    if raw_limit is not None:
        try:
            limit = int(raw_limit)
        except ValueError as exc:
            raise ValueError("Invalid limit.") from exc
    if limit <= 0:
        raise ValueError("Invalid limit.")
    limit = min(limit, max_limit)
    return PageWindow(offset=decode_cursor(raw_cursor), limit=limit)


def _canonical_user_pair(user_a: User, user_b: User) -> tuple[User, User]:
    if user_a.pk == user_b.pk:
        raise DomainForbiddenError("You cannot create a dialog with yourself.")
    if str(user_a.pk) < str(user_b.pk):
        return user_a, user_b
    return user_b, user_a


def is_room_member(*, room: Room, user: User) -> bool:
    return RoomMembership.objects.filter(room=room, user=user).exists()


def get_user_room_role(*, room: Room, user: User) -> str:
    membership = RoomMembership.objects.filter(room=room, user=user).values_list("role", flat=True).first()
    return membership or "none"


def get_room_for_detail(*, room_id, user: User) -> Room:
    room = get_object_or_404(Room.objects.select_related("owner_user"), pk=room_id)
    if room.visibility == RoomVisibility.PRIVATE and not is_room_member(room=room, user=user):
        raise Room.DoesNotExist
    return room


def require_room_member(*, room: Room, user: User) -> None:
    if not is_room_member(room=room, user=user):
        raise Room.DoesNotExist


@transaction.atomic
def create_room(*, owner_user: User, name: str, description: str | None, visibility: str) -> Room:
    room = Room.objects.create(
        name=name,
        description=description,
        visibility=visibility,
        owner_user=owner_user,
    )
    RoomMembership.objects.create(
        room=room,
        user=owner_user,
        role=RoomRole.OWNER,
        joined_at=room.created_at,
    )
    ModerationEvent.objects.create(
        action_type=ModerationActionType.ROOM_CREATED,
        actor_user=owner_user,
        room=room,
    )
    return room


@transaction.atomic
def update_room(*, room: Room, actor: User, **updates) -> Room:
    if room.owner_user_id != actor.id:
        raise DomainForbiddenError("Only the room owner may update this room.")
    for field, value in updates.items():
        setattr(room, field, value)
    room.save(update_fields=[*updates.keys(), "updated_at"])
    ModerationEvent.objects.create(
        action_type=ModerationActionType.ROOM_UPDATED,
        actor_user=actor,
        room=room,
    )
    return room


@transaction.atomic
def delete_room(*, room: Room, actor: User) -> None:
    if room.owner_user_id != actor.id:
        raise DomainForbiddenError("Only the room owner may delete this room.")
    attachment_ids = list(
        Attachment.objects.filter(room_message_bindings__room_message__room=room)
        .values_list("id", flat=True)
        .distinct()
    )
    if attachment_ids:
        Attachment.objects.filter(id__in=attachment_ids).delete()
    ModerationEvent.objects.create(
        action_type=ModerationActionType.ROOM_DELETED,
        actor_user=actor,
        room=room,
    )
    room.delete()


@transaction.atomic
def join_room(*, room: Room, user: User) -> None:
    if room.visibility != RoomVisibility.PUBLIC:
        raise DomainForbiddenError("Only public rooms may be joined directly.")
    if RoomBan.objects.filter(room=room, user=user, removed_at__isnull=True).exists():
        raise DomainForbiddenError("You are banned from this room.")
    if RoomMembership.objects.filter(room=room, user=user).exists():
        raise DomainConflictError("You are already a member of this room.")
    RoomMembership.objects.create(room=room, user=user, role=RoomRole.MEMBER, joined_at=timezone.now())


@transaction.atomic
def leave_room(*, room: Room, user: User) -> None:
    membership = RoomMembership.objects.filter(room=room, user=user).first()
    if membership is None:
        raise DomainConflictError("You are not a member of this room.")
    if membership.role == RoomRole.OWNER or room.owner_user_id == user.id:
        raise DomainForbiddenError("The room owner cannot leave the room.")
    membership.delete()
    RoomReadState.objects.filter(room=room, user=user).delete()


def list_public_rooms(*, search: str | None):
    queryset = Room.objects.filter(visibility=RoomVisibility.PUBLIC).select_related("owner_user")
    if search:
        queryset = queryset.filter(name__icontains=search.strip())
    return queryset.annotate(member_count=Count("memberships", distinct=True)).order_by("name", "id")


def list_joined_room_rows(*, user: User):
    memberships = list(
        RoomMembership.objects.filter(user=user)
        .select_related("room")
        .annotate(member_count=Count("room__memberships", distinct=True))
        .order_by("room__name", "room__id")
    )
    room_ids = [membership.room_id for membership in memberships]
    read_states = {
        item["room_id"]: item["last_read_at"]
        for item in RoomReadState.objects.filter(room_id__in=room_ids, user=user).values("room_id", "last_read_at")
    }
    unread_counts = {room_id: 0 for room_id in room_ids}
    for message in RoomMessage.objects.filter(room_id__in=room_ids).exclude(sender_user=user).values(
        "room_id",
        "created_at",
    ):
        last_read_at = read_states.get(message["room_id"])
        if last_read_at is None or message["created_at"] > last_read_at:
            unread_counts[message["room_id"]] += 1
    return memberships, unread_counts


def list_room_members(*, room: Room):
    memberships = list(
        RoomMembership.objects.filter(room=room).select_related("user")
    )
    role_order = {
        RoomRole.OWNER: 0,
        RoomRole.ADMIN: 1,
        RoomRole.MEMBER: 2,
    }
    memberships.sort(key=lambda item: (role_order[item.role], item.user.username, str(item.user.id)))
    return memberships


def are_friends(*, user_a: User, user_b: User) -> bool:
    user_low, user_high = _canonical_user_pair(user_a, user_b)
    return Friendship.objects.filter(user_low=user_low, user_high=user_high).exists()


def has_active_peer_ban(*, user_a: User, user_b: User) -> bool:
    return PeerBan.objects.filter(
        Q(source_user=user_a, target_user=user_b) | Q(source_user=user_b, target_user=user_a),
        removed_at__isnull=True,
    ).exists()


@transaction.atomic
def get_or_create_dialog(*, current_user: User, other_user: User) -> tuple[Dialog, bool]:
    if has_active_peer_ban(user_a=current_user, user_b=other_user):
        raise DomainForbiddenError("You are not allowed to create this dialog.")
    if not are_friends(user_a=current_user, user_b=other_user):
        raise DomainForbiddenError("You are not allowed to create this dialog.")
    user_low, user_high = _canonical_user_pair(current_user, other_user)
    try:
        dialog, created = Dialog.objects.get_or_create(user_low=user_low, user_high=user_high)
    except IntegrityError:
        dialog = Dialog.objects.get(user_low=user_low, user_high=user_high)
        created = False
    return dialog, created


def list_dialog_rows(*, user: User):
    dialogs = list(
        Dialog.objects.filter(Q(user_low=user) | Q(user_high=user))
        .select_related("user_low", "user_high")
        .order_by("-updated_at", "-id")
    )
    dialog_ids = [dialog.id for dialog in dialogs]
    read_states = {
        item["dialog_id"]: item["last_read_at"]
        for item in DialogReadState.objects.filter(dialog_id__in=dialog_ids, user=user).values(
            "dialog_id",
            "last_read_at",
        )
    }
    unread_counts = {dialog_id: 0 for dialog_id in dialog_ids}
    for message in DialogMessage.objects.filter(dialog_id__in=dialog_ids).exclude(sender_user=user).values(
        "dialog_id",
        "created_at",
    ):
        last_read_at = read_states.get(message["dialog_id"])
        if last_read_at is None or message["created_at"] > last_read_at:
            unread_counts[message["dialog_id"]] += 1

    last_messages = {}
    for message in (
        DialogMessage.objects.filter(dialog_id__in=dialog_ids)
        .select_related("sender_user")
        .order_by("dialog_id", "-created_at", "-id")
    ):
        last_messages.setdefault(message.dialog_id, message)
    return dialogs, unread_counts, last_messages
