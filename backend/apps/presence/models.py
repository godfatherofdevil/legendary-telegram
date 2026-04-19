from django.db import models

from ..common.models import TimestampedModel


class UserPresenceConnection(TimestampedModel):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="presence_connections",
    )
    session = models.ForeignKey(
        "accounts.UserSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="presence_connections",
    )
    connection_key = models.CharField(max_length=255, unique=True)
    tab_id = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    last_interaction_at = models.DateTimeField()
    last_heartbeat_at = models.DateTimeField()
    connected_at = models.DateTimeField()
    disconnected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["user", "disconnected_at"]),
            models.Index(fields=["last_heartbeat_at"]),
        ]
