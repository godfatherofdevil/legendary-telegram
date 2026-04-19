from django.db import models
from django.db.models import F, Q

from ..common.enums import FriendRequestStatus
from ..common.models import CreatedAtModel, TimestampedModel


class FriendRequest(TimestampedModel):
    from_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="sent_friend_requests",
    )
    to_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="received_friend_requests",
    )
    message = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=FriendRequestStatus.choices,
        default=FriendRequestStatus.PENDING,
    )
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["to_user", "status"]),
            models.Index(fields=["from_user", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(from_user=F("to_user")),
                name="social_friendrequest_distinct_users",
            ),
            models.UniqueConstraint(
                fields=["from_user", "to_user"],
                condition=Q(status=FriendRequestStatus.PENDING),
                name="social_friendrequest_one_pending_per_direction",
            ),
        ]


class Friendship(CreatedAtModel):
    user_low = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="friendships_low",
    )
    user_high = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="friendships_high",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(user_low__lt=F("user_high")),
                name="social_friendship_canonical_order",
            ),
            models.UniqueConstraint(
                fields=["user_low", "user_high"],
                name="social_friendship_unique_pair",
            ),
        ]


class PeerBan(CreatedAtModel):
    source_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="peer_bans_created",
    )
    target_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="peer_bans_received",
    )
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["source_user"]),
            models.Index(fields=["target_user"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(source_user=F("target_user")),
                name="social_peerban_distinct_users",
            ),
            models.UniqueConstraint(
                fields=["source_user", "target_user"],
                name="social_peerban_unique_pair",
            ),
        ]
