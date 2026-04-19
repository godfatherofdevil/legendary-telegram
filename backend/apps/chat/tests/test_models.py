import pytest
from django.db import IntegrityError
from django.utils import timezone

from ...accounts.models import User
from ..models import Dialog, Room, RoomInvitation
from ...common.enums import RoomInvitationStatus, RoomVisibility


@pytest.mark.django_db
def test_room_name_is_unique() -> None:
    owner = User.objects.create_user(
        email="owner@example.com",
        username="owner",
        password="strong-pass-123",
    )

    Room.objects.create(name="general", visibility=RoomVisibility.PUBLIC, owner_user=owner)

    with pytest.raises(IntegrityError):
        Room.objects.create(name="general", visibility=RoomVisibility.PRIVATE, owner_user=owner)


@pytest.mark.django_db
def test_dialog_requires_canonical_user_order() -> None:
    user_a = User.objects.create_user(
        email="a@example.com",
        username="usera",
        password="strong-pass-123",
    )
    user_b = User.objects.create_user(
        email="b@example.com",
        username="userb",
        password="strong-pass-123",
    )

    ordered = sorted([user_a, user_b], key=lambda user: str(user.pk))

    with pytest.raises(IntegrityError):
        Dialog.objects.create(
            user_low=ordered[1],
            user_high=ordered[0],
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )


@pytest.mark.django_db
def test_room_invitation_allows_only_one_pending_invitation_per_room_user() -> None:
    owner = User.objects.create_user(
        email="owner@example.com",
        username="owner",
        password="strong-pass-123",
    )
    invited = User.objects.create_user(
        email="invited@example.com",
        username="invited",
        password="strong-pass-123",
    )
    room = Room.objects.create(name="general", visibility=RoomVisibility.PUBLIC, owner_user=owner)

    RoomInvitation.objects.create(room=room, invited_user=invited, invited_by_user=owner)
    RoomInvitation.objects.create(
        room=room,
        invited_user=invited,
        invited_by_user=owner,
        status=RoomInvitationStatus.REVOKED,
    )

    with pytest.raises(IntegrityError):
        RoomInvitation.objects.create(room=room, invited_user=invited, invited_by_user=owner)
