from django.db import models


class PresenceState(models.TextChoices):
    ONLINE = "online", "Online"
    AFK = "afk", "AFK"
    OFFLINE = "offline", "Offline"


class RoomVisibility(models.TextChoices):
    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"


class RoomRole(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    MEMBER = "member", "Member"


class ChatType(models.TextChoices):
    ROOM = "room", "Room"
    DIALOG = "dialog", "Dialog"


class AttachmentBindingType(models.TextChoices):
    UNBOUND = "unbound", "Unbound"
    ROOM_MESSAGE = "room_message", "Room Message"
    DIALOG_MESSAGE = "dialog_message", "Dialog Message"


class FriendRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class RoomInvitationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    REVOKED = "revoked", "Revoked"


class ModerationActionType(models.TextChoices):
    ROOM_CREATED = "room_created", "Room Created"
    ROOM_UPDATED = "room_updated", "Room Updated"
    ROOM_DELETED = "room_deleted", "Room Deleted"
    MEMBER_REMOVED = "member_removed", "Member Removed"
    MEMBER_BANNED = "member_banned", "Member Banned"
    MEMBER_UNBANNED = "member_unbanned", "Member Unbanned"
    ADMIN_PROMOTED = "admin_promoted", "Admin Promoted"
    ADMIN_DEMOTED = "admin_demoted", "Admin Demoted"
    PEER_BAN_CREATED = "peer_ban_created", "Peer Ban Created"
    PEER_BAN_REMOVED = "peer_ban_removed", "Peer Ban Removed"
    MESSAGE_DELETED = "message_deleted", "Message Deleted"
    SESSION_REVOKED = "session_revoked", "Session Revoked"
