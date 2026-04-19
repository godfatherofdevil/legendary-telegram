from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from ..audit.models import ModerationEvent
from ..chat.models import Dialog
from ..common.enums import FriendRequestStatus, ModerationActionType
from .models import FriendRequest, Friendship, PeerBan

User = get_user_model()


class SocialConflictError(Exception):
    pass


class SocialForbiddenError(Exception):
    pass


class SocialValidationError(Exception):
    pass


@dataclass(frozen=True)
class FriendshipResult:
    request: FriendRequest | None
    friend: User
    created_at: object


def _canonical_user_pair(user_a: User, user_b: User) -> tuple[User, User]:
    if user_a.pk == user_b.pk:
        raise SocialValidationError("This action requires another user.")
    if str(user_a.pk) < str(user_b.pk):
        return user_a, user_b
    return user_b, user_a


def _freeze_dialog_for_pair(*, user_a: User, user_b: User, reason: str) -> Dialog | None:
    user_low, user_high = _canonical_user_pair(user_a, user_b)
    dialog = (
        Dialog.objects.select_related("user_low", "user_high")
        .filter(user_low=user_low, user_high=user_high)
        .first()
    )
    if dialog is None:
        return None
    dialog.is_frozen = True
    dialog.frozen_reason = reason
    dialog.updated_at = timezone.now()
    dialog.save(update_fields=["is_frozen", "frozen_reason", "updated_at"])
    return dialog


def _refresh_dialog_state_for_pair(*, user_a: User, user_b: User) -> None:
    user_low, user_high = _canonical_user_pair(user_a, user_b)
    is_friends = Friendship.objects.filter(user_low=user_low, user_high=user_high).exists()
    has_ban = PeerBan.objects.filter(
        Q(source_user=user_a, target_user=user_b) | Q(source_user=user_b, target_user=user_a),
        removed_at__isnull=True,
    ).exists()
    Dialog.objects.filter(user_low=user_low, user_high=user_high).update(
        is_frozen=not is_friends or has_ban,
        frozen_reason=None if is_friends and not has_ban else "friendship_required",
        updated_at=timezone.now(),
    )


def list_friends(*, user: User) -> list[FriendshipResult]:
    friendships = (
        Friendship.objects.filter(Q(user_low=user) | Q(user_high=user))
        .select_related("user_low", "user_high")
        .order_by("-created_at", "-id")
    )
    results: list[FriendshipResult] = []
    for friendship in friendships:
        friend = friendship.user_high if friendship.user_low_id == user.id else friendship.user_low
        results.append(
            FriendshipResult(
                request=None,
                friend=friend,
                created_at=friendship.created_at,
            )
        )
    return results


def list_incoming_friend_requests(*, user: User):
    return (
        FriendRequest.objects.filter(to_user=user, status=FriendRequestStatus.PENDING)
        .select_related("from_user")
        .order_by("-created_at", "-id")
    )


def list_outgoing_friend_requests(*, user: User):
    return (
        FriendRequest.objects.filter(from_user=user, status=FriendRequestStatus.PENDING)
        .select_related("to_user")
        .order_by("-created_at", "-id")
    )


def list_peer_bans(*, user: User):
    return (
        PeerBan.objects.filter(source_user=user, removed_at__isnull=True)
        .select_related("target_user")
        .order_by("-created_at", "-id")
    )


@transaction.atomic
def create_friend_request(*, from_user: User, username: str, message: str | None) -> FriendRequest:
    to_user = User.objects.filter(username=username).first()
    if to_user is None:
        raise User.DoesNotExist
    if to_user.id == from_user.id:
        raise SocialValidationError("You cannot send a friend request to yourself.")
    if PeerBan.objects.filter(
        Q(source_user=to_user, target_user=from_user) | Q(source_user=from_user, target_user=to_user),
        removed_at__isnull=True,
    ).exists():
        raise SocialForbiddenError("You are not allowed to send a friend request to this user.")
    user_low, user_high = _canonical_user_pair(from_user, to_user)
    if Friendship.objects.filter(user_low=user_low, user_high=user_high).exists():
        raise SocialConflictError("You are already friends with this user.")
    has_pending_request = FriendRequest.objects.filter(
        from_user=from_user,
        to_user=to_user,
        status=FriendRequestStatus.PENDING,
    ).exists() or FriendRequest.objects.filter(
        from_user=to_user,
        to_user=from_user,
        status=FriendRequestStatus.PENDING,
    ).exists()
    if has_pending_request:
        raise SocialConflictError("A pending friend request already exists for this user.")
    try:
        return FriendRequest.objects.create(
            from_user=from_user,
            to_user=to_user,
            message=message,
        )
    except IntegrityError as exc:
        raise SocialConflictError("A pending friend request already exists for this user.") from exc


@transaction.atomic
def accept_friend_request(*, request_id, actor: User) -> FriendshipResult:
    friend_request = get_object_or_404(
        FriendRequest.objects.select_for_update().select_related("from_user", "to_user"),
        id=request_id,
    )
    if friend_request.to_user_id != actor.id:
        raise FriendRequest.DoesNotExist
    if friend_request.status != FriendRequestStatus.PENDING:
        raise SocialConflictError("This friend request is no longer pending.")
    user_low, user_high = _canonical_user_pair(friend_request.from_user, friend_request.to_user)
    friendship, _created = Friendship.objects.get_or_create(user_low=user_low, user_high=user_high)
    friend_request.status = FriendRequestStatus.ACCEPTED
    friend_request.responded_at = timezone.now()
    friend_request.save(update_fields=["status", "responded_at", "updated_at"])
    _refresh_dialog_state_for_pair(user_a=friend_request.from_user, user_b=friend_request.to_user)
    return FriendshipResult(
        request=friend_request,
        friend=friend_request.from_user,
        created_at=friendship.created_at,
    )


@transaction.atomic
def reject_friend_request(*, request_id, actor: User) -> FriendRequest:
    friend_request = get_object_or_404(
        FriendRequest.objects.select_for_update(),
        id=request_id,
    )
    if friend_request.to_user_id != actor.id:
        raise FriendRequest.DoesNotExist
    if friend_request.status != FriendRequestStatus.PENDING:
        raise SocialConflictError("This friend request is no longer pending.")
    friend_request.status = FriendRequestStatus.REJECTED
    friend_request.responded_at = timezone.now()
    friend_request.save(update_fields=["status", "responded_at", "updated_at"])
    return friend_request


@transaction.atomic
def remove_friend(*, actor: User, other_user_id) -> Dialog | None:
    other_user = get_object_or_404(User, id=other_user_id)
    user_low, user_high = _canonical_user_pair(actor, other_user)
    deleted_count, _details = Friendship.objects.filter(
        user_low=user_low,
        user_high=user_high,
    ).delete()
    if deleted_count == 0:
        raise Friendship.DoesNotExist
    return _freeze_dialog_for_pair(
        user_a=actor,
        user_b=other_user,
        reason="friendship_required",
    )


@transaction.atomic
def create_peer_ban(*, actor: User, target_user_id) -> PeerBan:
    target_user = get_object_or_404(User, id=target_user_id)
    if target_user.id == actor.id:
        raise SocialValidationError("You cannot ban yourself.")
    user_low, user_high = _canonical_user_pair(actor, target_user)
    Friendship.objects.filter(user_low=user_low, user_high=user_high).delete()
    ban, created = PeerBan.objects.select_for_update().get_or_create(
        source_user=actor,
        target_user=target_user,
        defaults={"removed_at": None},
    )
    if not created and ban.removed_at is None:
        raise SocialConflictError("This user is already banned.")
    if not created:
        ban.removed_at = None
        ban.created_at = timezone.now()
        ban.save(update_fields=["removed_at", "created_at"])
    _freeze_dialog_for_pair(user_a=actor, user_b=target_user, reason="peer_ban")
    ModerationEvent.objects.create(
        action_type=ModerationActionType.PEER_BAN_CREATED,
        actor_user=actor,
        target_user=target_user,
    )
    return ban


@transaction.atomic
def remove_peer_ban(*, actor: User, target_user_id) -> None:
    ban = (
        PeerBan.objects.select_for_update()
        .filter(source_user=actor, target_user_id=target_user_id, removed_at__isnull=True)
        .first()
    )
    if ban is None:
        raise PeerBan.DoesNotExist
    ban.removed_at = timezone.now()
    ban.save(update_fields=["removed_at"])
    ModerationEvent.objects.create(
        action_type=ModerationActionType.PEER_BAN_REMOVED,
        actor_user=actor,
        target_user_id=target_user_id,
    )
    _refresh_dialog_state_for_pair(user_a=actor, user_b=ban.target_user)
