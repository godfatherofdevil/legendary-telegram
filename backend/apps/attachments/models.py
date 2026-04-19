from django.db import models

from ..common.enums import AttachmentBindingType
from ..common.models import CreatedAtModel, TimestampedModel


class Attachment(TimestampedModel):
    uploaded_by_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.RESTRICT,
        related_name="attachments",
    )
    storage_key = models.CharField(max_length=255, unique=True)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=255)
    size_bytes = models.BigIntegerField()
    comment = models.TextField(null=True, blank=True)
    binding_type = models.CharField(
        max_length=16,
        choices=AttachmentBindingType.choices,
        default=AttachmentBindingType.UNBOUND,
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["uploaded_by_user"]),
            models.Index(fields=["binding_type"]),
            models.Index(fields=["created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(size_bytes__gt=0),
                name="attachments_attachment_size_positive",
            ),
        ]


class RoomMessageAttachment(CreatedAtModel):
    room_message = models.ForeignKey(
        "chat.RoomMessage",
        on_delete=models.CASCADE,
        related_name="attachment_bindings",
    )
    attachment = models.ForeignKey(
        "attachments.Attachment",
        on_delete=models.CASCADE,
        related_name="room_message_bindings",
    )

    class Meta:
        indexes = [
            models.Index(fields=["room_message"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["attachment"],
                name="attachments_roommessageattachment_unique_attachment",
            ),
            models.UniqueConstraint(
                fields=["room_message", "attachment"],
                name="attachments_roommessageattachment_unique_pair",
            ),
        ]


class DialogMessageAttachment(CreatedAtModel):
    dialog_message = models.ForeignKey(
        "chat.DialogMessage",
        on_delete=models.CASCADE,
        related_name="attachment_bindings",
    )
    attachment = models.ForeignKey(
        "attachments.Attachment",
        on_delete=models.CASCADE,
        related_name="dialog_message_bindings",
    )

    class Meta:
        indexes = [
            models.Index(fields=["dialog_message"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["attachment"],
                name="attachments_dialogmessageattachment_unique_attachment",
            ),
            models.UniqueConstraint(
                fields=["dialog_message", "attachment"],
                name="attachments_dialogmessageattachment_unique_pair",
            ),
        ]
