import base64
import binascii
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from ..attachments.models import Attachment, DialogMessageAttachment, RoomMessageAttachment
from ..attachments.services import (
    delete_dialog_message_attachments,
    delete_room_message_attachments,
)
from ..audit.models import ModerationEvent
from .models import (
    Dialog,
    DialogMessage,
    DialogReadState,
    Room,
    RoomBan,
    RoomInvitation,
    RoomMembership,
    RoomMessage,
    RoomReadState,
)
from ..common.enums import AttachmentBindingType, ModerationActionType, RoomRole, RoomVisibility
from ..social.models import Friendship, PeerBan

User = get_user_model()
MESSAGE_TEXT_LIMIT_BYTES = 3 * 1024


class DomainConflictError(Exception):
    pass


class DomainForbiddenError(Exception):
    pass


class DomainValidationError(Exception):
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


def get_page_window(
    *, raw_limit: str | None, raw_cursor: str | None, default_limit: int, max_limit: int
) -> PageWindow:
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
    membership = (
        RoomMembership.objects.filter(room=room, user=user).values_list("role", flat=True).first()
    )
    return membership or "none"


def require_room_owner(*, room: Room, user: User) -> str:
    role = get_user_room_role(room=room, user=user)
    if role != RoomRole.OWNER:
        raise DomainForbiddenError("Only the room owner may perform this action.")
    return role


def require_room_admin_or_owner(*, room: Room, user: User) -> str:
    role = get_user_room_role(room=room, user=user)
    if role not in {RoomRole.OWNER, RoomRole.ADMIN}:
        raise DomainForbiddenError("You are not allowed to perform this action.")
    return role


def get_room_for_detail(*, room_id, user: User) -> Room:
    room = get_object_or_404(Room.objects.select_related("owner_user"), pk=room_id)
    if room.visibility == RoomVisibility.PRIVATE and not is_room_member(room=room, user=user):
        raise Room.DoesNotExist
    return room


def require_room_member(*, room: Room, user: User) -> None:
    if not is_room_member(room=room, user=user):
        raise Room.DoesNotExist


def is_room_banned(*, room: Room, user: User) -> bool:
    return RoomBan.objects.filter(room=room, user=user, removed_at__isnull=True).exists()


def require_room_message_access(*, room: Room, user: User) -> None:
    require_room_member(room=room, user=user)
    if is_room_banned(room=room, user=user):
        raise Room.DoesNotExist


def get_dialog_for_user(*, dialog_id, user: User) -> Dialog:
    dialog = get_object_or_404(Dialog.objects.select_related("user_low", "user_high"), pk=dialog_id)
    if dialog.user_low_id != user.id and dialog.user_high_id != user.id:
        raise Dialog.DoesNotExist
    return dialog


def _normalize_message_text(text: str | None) -> str | None:
    if text is None:
        return None
    if len(text.encode("utf-8")) > MESSAGE_TEXT_LIMIT_BYTES:
        raise DomainValidationError("Message text must not exceed 3 KB.")
    return text


def _validate_message_content(*, text: str | None, attachment_ids: list[str]) -> str | None:
    text = _normalize_message_text(text)
    if text is None and not attachment_ids:
        raise DomainValidationError("Message must include text or at least one attachment.")
    if text is not None and not text.strip() and not attachment_ids:
        raise DomainValidationError("Message must include text or at least one attachment.")
    return text


def _lock_owned_unbound_attachments(*, user: User, attachment_ids: list[str]) -> list[Attachment]:
    if not attachment_ids:
        return []
    deduped_ids = list(dict.fromkeys(str(attachment_id) for attachment_id in attachment_ids))
    if len(deduped_ids) != len(attachment_ids):
        raise DomainValidationError("Attachment ids must be unique.")
    attachments = list(
        Attachment.objects.select_for_update().filter(id__in=deduped_ids, deleted_at__isnull=True)
    )
    if len(attachments) != len(deduped_ids):
        raise DomainValidationError("One or more attachments are invalid.")
    attachments_by_id = {str(attachment.id): attachment for attachment in attachments}
    ordered_attachments = [attachments_by_id[attachment_id] for attachment_id in deduped_ids]
    for attachment in ordered_attachments:
        if attachment.uploaded_by_user_id != user.id:
            raise DomainValidationError("One or more attachments are invalid.")
        if attachment.binding_type != AttachmentBindingType.UNBOUND:
            raise DomainValidationError("One or more attachments are invalid.")
    return ordered_attachments


def _room_message_prefetch():
    return RoomMessage.objects.select_related(
        "sender_user",
        "reply_to_message__sender_user",
    ).prefetch_related(
        Prefetch(
            "attachment_bindings",
            queryset=RoomMessageAttachment.objects.select_related("attachment").order_by(
                "created_at", "id"
            ),
        )
    )


def _dialog_message_prefetch():
    return DialogMessage.objects.select_related(
        "sender_user",
        "reply_to_message__sender_user",
    ).prefetch_related(
        Prefetch(
            "attachment_bindings",
            queryset=DialogMessageAttachment.objects.select_related("attachment").order_by(
                "created_at", "id"
            ),
        )
    )


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
    RoomMembership.objects.create(
        room=room, user=user, role=RoomRole.MEMBER, joined_at=timezone.now()
    )


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
    return queryset.annotate(member_count=Count("memberships", distinct=True)).order_by(
        "name", "id"
    )


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
        for item in RoomReadState.objects.filter(room_id__in=room_ids, user=user).values(
            "room_id", "last_read_at"
        )
    }
    unread_counts = {room_id: 0 for room_id in room_ids}
    for message in (
        RoomMessage.objects.filter(room_id__in=room_ids)
        .exclude(sender_user=user)
        .values(
            "room_id",
            "created_at",
        )
    ):
        last_read_at = read_states.get(message["room_id"])
        if last_read_at is None or message["created_at"] > last_read_at:
            unread_counts[message["room_id"]] += 1
    return memberships, unread_counts


def list_room_members(*, room: Room):
    memberships = list(RoomMembership.objects.filter(room=room).select_related("user"))
    role_order = {
        RoomRole.OWNER: 0,
        RoomRole.ADMIN: 1,
        RoomRole.MEMBER: 2,
    }
    memberships.sort(
        key=lambda item: (role_order[item.role], item.user.username, str(item.user.id))
    )
    return memberships


def list_room_invitations(*, room: Room, actor: User):
    require_room_admin_or_owner(room=room, user=actor)
    return (
        RoomInvitation.objects.filter(room=room, status="pending")
        .select_related("invited_user")
        .order_by("-created_at", "-id")
    )


@transaction.atomic
def create_room_invitation(*, room: Room, actor: User, invited_user: User) -> RoomInvitation:
    require_room_admin_or_owner(room=room, user=actor)
    if room.visibility != RoomVisibility.PRIVATE:
        raise DomainConflictError("Invitations are only supported for private rooms.")
    if invited_user.id == actor.id:
        raise DomainValidationError("You cannot invite yourself.")
    if is_room_banned(room=room, user=invited_user):
        raise DomainForbiddenError("This user is banned from the room.")
    if is_room_member(room=room, user=invited_user):
        raise DomainConflictError("This user is already a member of the room.")
    invitation, created = RoomInvitation.objects.get_or_create(
        room=room,
        invited_user=invited_user,
        status="pending",
        defaults={"invited_by_user": actor},
    )
    if not created:
        raise DomainConflictError("A pending invitation already exists for this user.")
    return invitation


@transaction.atomic
def accept_room_invitation(*, invitation_id, actor: User) -> None:
    invitation = (
        RoomInvitation.objects.select_for_update()
        .select_related("room", "invited_user", "invited_by_user")
        .filter(id=invitation_id)
        .first()
    )
    if invitation is None or invitation.invited_user_id != actor.id:
        raise RoomInvitation.DoesNotExist
    if invitation.status != "pending":
        raise DomainConflictError("This invitation is no longer pending.")
    if is_room_banned(room=invitation.room, user=actor):
        raise DomainForbiddenError("You are banned from this room.")
    RoomMembership.objects.get_or_create(
        room=invitation.room,
        user=actor,
        defaults={
            "role": RoomRole.MEMBER,
            "joined_at": timezone.now(),
            "invited_by_user": invitation.invited_by_user,
        },
    )
    invitation.status = "accepted"
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "responded_at", "updated_at"])


@transaction.atomic
def reject_room_invitation(*, invitation_id, actor: User) -> None:
    invitation = RoomInvitation.objects.select_for_update().filter(id=invitation_id).first()
    if invitation is None or invitation.invited_user_id != actor.id:
        raise RoomInvitation.DoesNotExist
    if invitation.status != "pending":
        raise DomainConflictError("This invitation is no longer pending.")
    invitation.status = "rejected"
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "responded_at", "updated_at"])


@transaction.atomic
def promote_room_admin(*, room: Room, actor: User, target_user: User) -> None:
    require_room_owner(room=room, user=actor)
    membership = (
        RoomMembership.objects.select_for_update().filter(room=room, user=target_user).first()
    )
    if membership is None:
        raise RoomMembership.DoesNotExist
    if membership.role == RoomRole.OWNER:
        raise DomainForbiddenError("The room owner already has owner privileges.")
    if membership.role == RoomRole.ADMIN:
        raise DomainConflictError("This user is already an admin.")
    membership.role = RoomRole.ADMIN
    membership.save(update_fields=["role", "updated_at"])
    ModerationEvent.objects.create(
        action_type=ModerationActionType.ADMIN_PROMOTED,
        actor_user=actor,
        target_user=target_user,
        room=room,
    )


@transaction.atomic
def demote_room_admin(*, room: Room, actor: User, target_user: User) -> None:
    actor_role = require_room_admin_or_owner(room=room, user=actor)
    membership = (
        RoomMembership.objects.select_for_update().filter(room=room, user=target_user).first()
    )
    if membership is None:
        raise RoomMembership.DoesNotExist
    if membership.role == RoomRole.OWNER:
        raise DomainForbiddenError("You cannot remove owner admin status.")
    if membership.role != RoomRole.ADMIN:
        raise DomainConflictError("This user is not an admin.")
    if actor_role == RoomRole.ADMIN and target_user.id == actor.id:
        raise DomainForbiddenError("Admins cannot remove their own admin status.")
    membership.role = RoomRole.MEMBER
    membership.save(update_fields=["role", "updated_at"])
    ModerationEvent.objects.create(
        action_type=ModerationActionType.ADMIN_DEMOTED,
        actor_user=actor,
        target_user=target_user,
        room=room,
    )


def _get_room_member_for_moderation(*, room: Room, actor: User, target_user: User) -> RoomMembership:
    actor_role = require_room_admin_or_owner(room=room, user=actor)
    membership = (
        RoomMembership.objects.select_for_update().filter(room=room, user=target_user).first()
    )
    if membership is None:
        raise RoomMembership.DoesNotExist
    if membership.role == RoomRole.OWNER:
        raise DomainForbiddenError("The room owner cannot be moderated.")
    if actor_role == RoomRole.ADMIN and membership.role == RoomRole.ADMIN:
        raise DomainForbiddenError("Room admins cannot moderate other admins.")
    return membership


@transaction.atomic
def create_room_ban(*, room: Room, actor: User, target_user: User, action_type: str) -> RoomBan:
    membership = _get_room_member_for_moderation(room=room, actor=actor, target_user=target_user)
    membership.delete()
    RoomReadState.objects.filter(room=room, user=target_user).delete()
    ban, created = RoomBan.objects.select_for_update().get_or_create(
        room=room,
        user=target_user,
        defaults={"banned_by_user": actor, "removed_at": None},
    )
    if not created and ban.removed_at is None:
        raise DomainConflictError("This user is already banned from the room.")
    if not created:
        ban.banned_by_user = actor
        ban.reason = None
        ban.removed_at = None
        ban.created_at = timezone.now()
        ban.save(update_fields=["banned_by_user", "reason", "removed_at", "created_at"])
    ModerationEvent.objects.create(
        action_type=action_type,
        actor_user=actor,
        target_user=target_user,
        room=room,
    )
    return ban


def list_room_bans(*, room: Room, actor: User):
    require_room_admin_or_owner(room=room, user=actor)
    return (
        RoomBan.objects.filter(room=room, removed_at__isnull=True)
        .select_related("user", "banned_by_user")
        .order_by("-created_at", "-id")
    )


@transaction.atomic
def remove_room_ban(*, room: Room, actor: User, target_user: User) -> None:
    require_room_admin_or_owner(room=room, user=actor)
    ban = (
        RoomBan.objects.select_for_update()
        .filter(room=room, user=target_user, removed_at__isnull=True)
        .first()
    )
    if ban is None:
        raise RoomBan.DoesNotExist
    ban.removed_at = timezone.now()
    ban.save(update_fields=["removed_at"])
    ModerationEvent.objects.create(
        action_type=ModerationActionType.MEMBER_UNBANNED,
        actor_user=actor,
        target_user=target_user,
        room=room,
    )


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
    for message in (
        DialogMessage.objects.filter(dialog_id__in=dialog_ids)
        .exclude(sender_user=user)
        .values(
            "dialog_id",
            "created_at",
        )
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


def get_dialog_unread_count(*, dialog: Dialog, user: User) -> int:
    if dialog.user_low_id != user.id and dialog.user_high_id != user.id:
        raise Dialog.DoesNotExist
    last_read_at = (
        DialogReadState.objects.filter(dialog=dialog, user=user)
        .values_list("last_read_at", flat=True)
        .first()
    )
    queryset = DialogMessage.objects.filter(dialog=dialog).exclude(sender_user=user)
    if last_read_at is not None:
        queryset = queryset.filter(created_at__gt=last_read_at)
    return queryset.count()


def list_room_message_rows(
    *, room: Room, user: User, page: PageWindow
) -> tuple[list[RoomMessage], bool]:
    require_room_message_access(room=room, user=user)
    messages = list(
        _room_message_prefetch()
        .filter(room=room)
        .order_by("-created_at", "-id")[page.offset : page.offset + page.limit + 1]
    )
    has_next = len(messages) > page.limit
    page_items = list(reversed(messages[: page.limit]))
    return page_items, has_next


def list_dialog_message_rows(
    *, dialog: Dialog, user: User, page: PageWindow
) -> tuple[list[DialogMessage], bool]:
    if dialog.user_low_id != user.id and dialog.user_high_id != user.id:
        raise Dialog.DoesNotExist
    messages = list(
        _dialog_message_prefetch()
        .filter(dialog=dialog)
        .order_by("-created_at", "-id")[page.offset : page.offset + page.limit + 1]
    )
    has_next = len(messages) > page.limit
    page_items = list(reversed(messages[: page.limit]))
    return page_items, has_next


def _get_room_reply_message(*, room: Room, reply_to_message_id) -> RoomMessage | None:
    if reply_to_message_id is None:
        return None
    reply_to_message = (
        RoomMessage.objects.select_related("sender_user")
        .filter(id=reply_to_message_id, room=room)
        .first()
    )
    if reply_to_message is None:
        raise DomainValidationError("Reply target must belong to the same room.")
    return reply_to_message


def _get_dialog_reply_message(*, dialog: Dialog, reply_to_message_id) -> DialogMessage | None:
    if reply_to_message_id is None:
        return None
    reply_to_message = (
        DialogMessage.objects.select_related("sender_user")
        .filter(id=reply_to_message_id, dialog=dialog)
        .first()
    )
    if reply_to_message is None:
        raise DomainValidationError("Reply target must belong to the same dialog.")
    return reply_to_message


@transaction.atomic
def create_room_message(
    *,
    room: Room,
    sender: User,
    text: str | None,
    reply_to_message_id,
    attachment_ids: list[str],
) -> RoomMessage:
    require_room_message_access(room=room, user=sender)
    text = _validate_message_content(text=text, attachment_ids=attachment_ids)
    reply_to_message = _get_room_reply_message(room=room, reply_to_message_id=reply_to_message_id)
    attachments = _lock_owned_unbound_attachments(user=sender, attachment_ids=attachment_ids)
    message = RoomMessage.objects.create(
        room=room,
        sender_user=sender,
        text=text,
        reply_to_message=reply_to_message,
    )
    if attachments:
        RoomMessageAttachment.objects.bulk_create(
            [
                RoomMessageAttachment(room_message=message, attachment=attachment)
                for attachment in attachments
            ]
        )
        Attachment.objects.filter(id__in=[attachment.id for attachment in attachments]).update(
            binding_type=AttachmentBindingType.ROOM_MESSAGE,
            updated_at=timezone.now(),
        )
    return _room_message_prefetch().get(id=message.id)


@transaction.atomic
def update_room_message(*, room: Room, message_id, actor: User, text: str | None) -> RoomMessage:
    require_room_message_access(room=room, user=actor)
    message = RoomMessage.objects.select_for_update().filter(id=message_id, room=room).first()
    if message is None:
        raise RoomMessage.DoesNotExist
    if message.sender_user_id != actor.id:
        raise DomainForbiddenError("Only the message author may edit this message.")
    text = _validate_message_content(
        text=text,
        attachment_ids=list(message.attachment_bindings.values_list("attachment_id", flat=True)),
    )
    message.text = text
    message.is_edited = True
    message.save(update_fields=["text", "is_edited", "updated_at"])
    return _room_message_prefetch().get(id=message.id)


@transaction.atomic
def delete_room_message(*, room: Room, message_id, actor: User) -> None:
    require_room_message_access(room=room, user=actor)
    message = RoomMessage.objects.select_for_update().filter(id=message_id, room=room).first()
    if message is None:
        raise RoomMessage.DoesNotExist
    actor_role = get_user_room_role(room=room, user=actor)
    can_delete = message.sender_user_id == actor.id or actor_role in {
        RoomRole.OWNER,
        RoomRole.ADMIN,
    }
    if not can_delete:
        raise DomainForbiddenError("You are not allowed to delete this message.")
    ModerationEvent.objects.create(
        action_type=ModerationActionType.MESSAGE_DELETED,
        actor_user=actor,
        room=room,
        room_message=message,
    )
    delete_room_message_attachments(message=message)
    message.delete()


@transaction.atomic
def create_dialog_message(
    *,
    dialog: Dialog,
    sender: User,
    text: str | None,
    reply_to_message_id,
    attachment_ids: list[str],
) -> DialogMessage:
    if dialog.user_low_id != sender.id and dialog.user_high_id != sender.id:
        raise Dialog.DoesNotExist
    if dialog.is_frozen:
        raise DomainForbiddenError("You are not allowed to send messages to this dialog.")
    other_user = dialog.user_high if dialog.user_low_id == sender.id else dialog.user_low
    if not are_friends(user_a=sender, user_b=other_user) or has_active_peer_ban(
        user_a=sender, user_b=other_user
    ):
        raise DomainForbiddenError("You are not allowed to send messages to this dialog.")
    text = _validate_message_content(text=text, attachment_ids=attachment_ids)
    reply_to_message = _get_dialog_reply_message(
        dialog=dialog, reply_to_message_id=reply_to_message_id
    )
    attachments = _lock_owned_unbound_attachments(user=sender, attachment_ids=attachment_ids)
    message = DialogMessage.objects.create(
        dialog=dialog,
        sender_user=sender,
        text=text,
        reply_to_message=reply_to_message,
    )
    if attachments:
        DialogMessageAttachment.objects.bulk_create(
            [
                DialogMessageAttachment(dialog_message=message, attachment=attachment)
                for attachment in attachments
            ]
        )
        Attachment.objects.filter(id__in=[attachment.id for attachment in attachments]).update(
            binding_type=AttachmentBindingType.DIALOG_MESSAGE,
            updated_at=timezone.now(),
        )
    Dialog.objects.filter(id=dialog.id).update(updated_at=timezone.now())
    return _dialog_message_prefetch().get(id=message.id)


@transaction.atomic
def update_dialog_message(
    *, dialog: Dialog, message_id, actor: User, text: str | None
) -> DialogMessage:
    if dialog.user_low_id != actor.id and dialog.user_high_id != actor.id:
        raise Dialog.DoesNotExist
    message = DialogMessage.objects.select_for_update().filter(id=message_id, dialog=dialog).first()
    if message is None:
        raise DialogMessage.DoesNotExist
    if message.sender_user_id != actor.id:
        raise DomainForbiddenError("Only the message author may edit this message.")
    text = _validate_message_content(
        text=text,
        attachment_ids=list(message.attachment_bindings.values_list("attachment_id", flat=True)),
    )
    message.text = text
    message.is_edited = True
    message.save(update_fields=["text", "is_edited", "updated_at"])
    Dialog.objects.filter(id=dialog.id).update(updated_at=timezone.now())
    return _dialog_message_prefetch().get(id=message.id)


@transaction.atomic
def delete_dialog_message(*, dialog: Dialog, message_id, actor: User) -> None:
    if dialog.user_low_id != actor.id and dialog.user_high_id != actor.id:
        raise Dialog.DoesNotExist
    message = DialogMessage.objects.select_for_update().filter(id=message_id, dialog=dialog).first()
    if message is None:
        raise DialogMessage.DoesNotExist
    if message.sender_user_id != actor.id:
        raise DomainForbiddenError("Only the message author may delete this message.")
    ModerationEvent.objects.create(
        action_type=ModerationActionType.MESSAGE_DELETED,
        actor_user=actor,
        dialog=dialog,
        dialog_message=message,
    )
    delete_dialog_message_attachments(message=message)
    message.delete()
    Dialog.objects.filter(id=dialog.id).update(updated_at=timezone.now())


@transaction.atomic
def mark_room_read(*, room: Room, user: User) -> None:
    require_room_message_access(room=room, user=user)
    latest_message = RoomMessage.objects.filter(room=room).order_by("-created_at", "-id").first()
    defaults = {
        "last_read_room_message": latest_message,
        "last_read_at": latest_message.created_at if latest_message is not None else timezone.now(),
    }
    RoomReadState.objects.update_or_create(room=room, user=user, defaults=defaults)


@transaction.atomic
def mark_dialog_read(*, dialog: Dialog, user: User) -> None:
    if dialog.user_low_id != user.id and dialog.user_high_id != user.id:
        raise Dialog.DoesNotExist
    latest_message = (
        DialogMessage.objects.filter(dialog=dialog).order_by("-created_at", "-id").first()
    )
    defaults = {
        "last_read_dialog_message": latest_message,
        "last_read_at": latest_message.created_at if latest_message is not None else timezone.now(),
    }
    DialogReadState.objects.update_or_create(dialog=dialog, user=user, defaults=defaults)
