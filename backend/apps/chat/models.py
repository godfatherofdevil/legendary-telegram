from django.db import models
from django.db.models import F, Q

from ..common.enums import RoomInvitationStatus, RoomRole, RoomVisibility
from ..common.models import CreatedAtModel, TimestampedModel


class Room(TimestampedModel):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)
    visibility = models.CharField(max_length=16, choices=RoomVisibility.choices)
    owner_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.RESTRICT,
        related_name="owned_rooms",
    )

    class Meta:
        indexes = [
            models.Index(fields=["visibility"]),
            models.Index(fields=["owner_user"]),
            models.Index(fields=["name"]),
        ]
        constraints = [
            models.CheckConstraint(condition=~Q(name=""), name="chat_room_name_not_empty"),
        ]


class RoomMembership(TimestampedModel):
    room = models.ForeignKey(
        "chat.Room",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="room_memberships",
    )
    role = models.CharField(max_length=16, choices=RoomRole.choices, default=RoomRole.MEMBER)
    joined_at = models.DateTimeField()
    invited_by_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="room_memberships_invited",
    )

    class Meta:
        indexes = [
            models.Index(fields=["room"]),
            models.Index(fields=["user"]),
            models.Index(fields=["room", "role"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["room", "user"],
                name="chat_roommembership_unique_pair",
            ),
        ]


class RoomBan(CreatedAtModel):
    room = models.ForeignKey(
        "chat.Room",
        on_delete=models.CASCADE,
        related_name="bans",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="room_bans",
    )
    banned_by_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.RESTRICT,
        related_name="issued_room_bans",
    )
    reason = models.TextField(null=True, blank=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["room"]),
            models.Index(fields=["user"]),
            models.Index(fields=["room", "removed_at"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["room", "user"], name="chat_roomban_unique_pair"),
        ]


class RoomInvitation(TimestampedModel):
    room = models.ForeignKey(
        "chat.Room",
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    invited_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="room_invitations",
    )
    invited_by_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.RESTRICT,
        related_name="room_invitations_sent",
    )
    status = models.CharField(
        max_length=16,
        choices=RoomInvitationStatus.choices,
        default=RoomInvitationStatus.PENDING,
    )
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["room", "status"]),
            models.Index(fields=["invited_user", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["room", "invited_user"],
                condition=Q(status=RoomInvitationStatus.PENDING),
                name="chat_roominvitation_one_pending_per_room_user",
            ),
        ]


class Dialog(TimestampedModel):
    user_low = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="dialogs_low",
    )
    user_high = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="dialogs_high",
    )
    is_frozen = models.BooleanField(default=False)
    frozen_reason = models.TextField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user_low"]),
            models.Index(fields=["user_high"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(user_low__lt=F("user_high")),
                name="chat_dialog_canonical_order",
            ),
            models.UniqueConstraint(
                fields=["user_low", "user_high"],
                name="chat_dialog_unique_pair",
            ),
        ]


class RoomMessage(TimestampedModel):
    room = models.ForeignKey(
        "chat.Room",
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.RESTRICT,
        related_name="room_messages",
    )
    text = models.TextField(null=True, blank=True)
    reply_to_message = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )
    is_edited = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["room", "created_at"]),
            models.Index(fields=["sender_user"]),
            models.Index(fields=["reply_to_message"]),
        ]


class DialogMessage(TimestampedModel):
    dialog = models.ForeignKey(
        "chat.Dialog",
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.RESTRICT,
        related_name="dialog_messages",
    )
    text = models.TextField(null=True, blank=True)
    reply_to_message = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )
    is_edited = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["dialog", "created_at"]),
            models.Index(fields=["sender_user"]),
            models.Index(fields=["reply_to_message"]),
        ]


class RoomReadState(TimestampedModel):
    room = models.ForeignKey(
        "chat.Room",
        on_delete=models.CASCADE,
        related_name="read_states",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="room_read_states",
    )
    last_read_room_message = models.ForeignKey(
        "chat.RoomMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["room"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["room", "user"], name="chat_roomreadstate_unique_pair"),
        ]


class DialogReadState(TimestampedModel):
    dialog = models.ForeignKey(
        "chat.Dialog",
        on_delete=models.CASCADE,
        related_name="read_states",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="dialog_read_states",
    )
    last_read_dialog_message = models.ForeignKey(
        "chat.DialogMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["dialog"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["dialog", "user"],
                name="chat_dialogreadstate_unique_pair",
            ),
        ]
