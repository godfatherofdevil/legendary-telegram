import pytest
from django.db import IntegrityError
from django.utils import timezone

from ...accounts.models import User
from ..models import FriendRequest, Friendship


@pytest.mark.django_db
def test_friend_request_allows_only_one_pending_request_per_direction() -> None:
    sender = User.objects.create_user(
        email="sender@example.com",
        username="sender",
        password="strong-pass-123",
    )
    recipient = User.objects.create_user(
        email="recipient@example.com",
        username="recipient",
        password="strong-pass-123",
    )

    FriendRequest.objects.create(from_user=sender, to_user=recipient)

    with pytest.raises(IntegrityError):
        FriendRequest.objects.create(from_user=sender, to_user=recipient)


@pytest.mark.django_db
def test_friendship_requires_canonical_user_order() -> None:
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
        Friendship.objects.create(
            user_low=ordered[1],
            user_high=ordered[0],
            created_at=timezone.now(),
        )
