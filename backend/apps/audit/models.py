from django.db import models

from ..common.enums import ModerationActionType
from ..common.models import CreatedAtModel


class ModerationEvent(CreatedAtModel):
    action_type = models.CharField(max_length=32, choices=ModerationActionType.choices)
    actor_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_events_performed",
    )
    target_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_events_received",
    )
    room = models.ForeignKey(
        "chat.Room",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_events",
    )
    dialog = models.ForeignKey(
        "chat.Dialog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_events",
    )
    room_message = models.ForeignKey(
        "chat.RoomMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    dialog_message = models.ForeignKey(
        "chat.DialogMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    attachment = models.ForeignKey(
        "attachments.Attachment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_events",
    )
    session = models.ForeignKey(
        "accounts.UserSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_events",
    )
    metadata_json = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=["action_type"]),
            models.Index(fields=["actor_user"]),
            models.Index(fields=["target_user"]),
            models.Index(fields=["room"]),
            models.Index(fields=["created_at"]),
        ]
