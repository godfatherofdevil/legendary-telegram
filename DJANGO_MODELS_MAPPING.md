# DJANGO_MODELS_MAPPING.md

## 1. Purpose

This document maps `SCHEMA.md` into a Django-oriented model design for the Online Chat Server.

It is an implementation guide for Django developers and coding agents. It explains:

- recommended Django app structure
- model-to-table mapping
- field mapping
- relationship mapping
- enum mapping
- constraint mapping
- manager/service responsibilities
- deletion semantics
- notes about what MUST be enforced in model/service layer rather than only in the database

This document is aligned with:

- `AGENTS.md`
- `API_CONTRACT.md`
- `SCHEMA.md`

It does not replace those documents.

---

## 2. Recommended Django App Layout

The project SHOULD be split into focused apps.

Recommended apps:

- `accounts`
- `presence`
- `social`
- `chat`
- `attachments`
- `audit`

### 2.1 accounts

Owns:

- user model
- password reset token model
- user session metadata model

### 2.2 presence

Owns:

- tab/connection presence model

### 2.3 social

Owns:

- friend requests
- friendships
- peer bans

### 2.4 chat

Owns:

- rooms
- room memberships
- room bans
- room invitations
- dialogs
- room messages
- dialog messages
- read states

### 2.5 attachments

Owns:

- attachment model
- room message attachment binding
- dialog message attachment binding

### 2.6 audit

Owns:

- moderation/audit event model

---

## 3. Base Django Conventions

### 3.1 Base Model Recommendation

Most models SHOULD inherit from a shared abstract timestamp base:

```python
class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
````

For immutable created-only models, a narrower base MAY be used.

### 3.2 ID Strategy

Recommended:

* `models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`

If the implementation wants string-prefixed IDs externally, keep UUIDs internally and serialize them as strings in API layer.

### 3.3 Timezone Handling

All datetime fields MUST use timezone-aware UTC storage.

### 3.4 User Model

The project SHOULD use a custom Django user model from the beginning.

Agents MUST NOT use default `auth.User` if the schema requires custom fields such as:

* immutable username semantics
* presence fields
* normalized email uniqueness

---

## 4. Enum Mapping

Use Django `TextChoices` for model enums unless PostgreSQL-native enums are intentionally introduced.

---

## 4.1 PresenceState

```python
class PresenceState(models.TextChoices):
    ONLINE = "online", "Online"
    AFK = "afk", "AFK"
    OFFLINE = "offline", "Offline"
```

---

## 4.2 RoomVisibility

```python
class RoomVisibility(models.TextChoices):
    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"
```

---

## 4.3 RoomRole

```python
class RoomRole(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    MEMBER = "member", "Member"
```

---

## 4.4 FriendRequestStatus

```python
class FriendRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"
```

---

## 4.5 RoomInvitationStatus

```python
class RoomInvitationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    REVOKED = "revoked", "Revoked"
```

---

## 4.6 AttachmentBindingType

```python
class AttachmentBindingType(models.TextChoices):
    UNBOUND = "unbound", "Unbound"
    ROOM_MESSAGE = "room_message", "Room Message"
    DIALOG_MESSAGE = "dialog_message", "Dialog Message"
```

---

## 4.7 ModerationActionType

```python
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
```

---

## 5. Accounts App Model Mapping

## 5.1 User Model

### Recommended Django Model

```python
class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=255)
    presence_state = models.CharField(
        max_length=16,
        choices=PresenceState.choices,
        default=PresenceState.OFFLINE,
    )
    presence_last_changed_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]
```

### Notes

* This SHOULD be the `AUTH_USER_MODEL`.
* `email` SHOULD be normalized to lowercase before save.
* `username` immutability MUST be enforced in service or model clean/save logic.
* Do not rely on `unique=True` alone for case-insensitive email semantics unless normalized consistently.

### Recommended Meta/Index Notes

```python
class Meta:
    db_table = "users"
    indexes = [
        models.Index(fields=["email"]),
        models.Index(fields=["username"]),
        models.Index(fields=["presence_state"]),
    ]
```

### Required Non-Database Enforcement

* Prevent username changes after creation.
* Prevent blank normalized email.
* Use `set_password()` for password hashing.

---

## 5.2 PasswordResetToken Model

```python
class PasswordResetToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token_hash = models.CharField(max_length=255, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "password_reset_tokens"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["expires_at"]),
        ]
```

### Notes

* Raw reset token MUST NOT be stored.
* Validation of expiry and used state belongs in service layer.

---

## 5.3 UserSession Model

```python
class UserSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="session_records",
    )
    session_key_hash = models.CharField(max_length=255, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    is_currently_valid = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_sessions"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["user", "is_currently_valid"]),
            models.Index(fields=["expires_at"]),
        ]
```

### Notes

* This model stores session metadata, not necessarily the full Django session payload.
* It SHOULD map to actual session lifecycle.
* Revoking a session MUST also invalidate the corresponding Django session.

---

## 6. Presence App Model Mapping

## 6.1 UserPresenceConnection Model

```python
class UserPresenceConnection(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
        db_table = "user_presence_connections"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["user", "disconnected_at"]),
            models.Index(fields=["last_heartbeat_at"]),
        ]
```

### Notes

* This table supports multi-tab presence aggregation.
* Presence computation SHOULD live in a service, not only in model methods.
* Active/open tab detection is derived from `disconnected_at IS NULL` plus heartbeat freshness.

---

## 7. Social App Model Mapping

## 7.1 FriendRequest Model

```python
class FriendRequest(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_friend_requests",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
        db_table = "friend_requests"
        indexes = [
            models.Index(fields=["to_user", "status"]),
            models.Index(fields=["from_user", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(from_user=models.F("to_user")),
                name="friend_request_not_self",
            ),
        ]
```

### Notes

* Duplicate active pending requests SHOULD be prevented in service logic and, if practical, with a conditional unique constraint.
* If using PostgreSQL, a conditional unique constraint on pending requests is recommended.

Example:

```python
models.UniqueConstraint(
    fields=["from_user", "to_user"],
    condition=models.Q(status="pending"),
    name="unique_pending_friend_request",
)
```

---

## 7.2 Friendship Model

```python
class Friendship(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_low = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="friendships_as_low",
    )
    user_high = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="friendships_as_high",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "friendships"
        constraints = [
            models.CheckConstraint(
                check=~models.Q(user_low=models.F("user_high")),
                name="friendship_not_self",
            ),
            models.UniqueConstraint(
                fields=["user_low", "user_high"],
                name="unique_friendship_pair",
            ),
        ]
```

### Notes

* Canonical ordering MUST be enforced in service layer before save:

  * smaller UUID/string goes to `user_low`
  * larger goes to `user_high`
* This model is best handled through a service helper like `FriendshipService.make_pair(user_a, user_b)`.

---

## 7.3 PeerBan Model

```python
class PeerBan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="peer_bans_issued",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="peer_bans_received",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "peer_bans"
        indexes = [
            models.Index(fields=["source_user"]),
            models.Index(fields=["target_user"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(source_user=models.F("target_user")),
                name="peer_ban_not_self",
            ),
            models.UniqueConstraint(
                fields=["source_user", "target_user"],
                name="unique_peer_ban_pair",
            ),
        ]
```

### Notes

* Active peer ban means `removed_at IS NULL`.
* Creating a peer ban SHOULD also:

  * remove friendship if present
  * freeze dialog if present

That belongs in service logic, not the model alone.

---

## 8. Chat App Model Mapping

## 8.1 Room Model

```python
class Room(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)
    visibility = models.CharField(max_length=16, choices=RoomVisibility.choices)
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="owned_rooms",
    )

    class Meta:
        db_table = "rooms"
        indexes = [
            models.Index(fields=["visibility"]),
            models.Index(fields=["owner_user"]),
            models.Index(fields=["name"]),
        ]
```

### Notes

* Owner delete handling MUST be explicit.
* Room creation service SHOULD also create owner membership row.

---

## 8.2 RoomMembership Model

```python
class RoomMembership(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        "chat.Room",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="room_memberships",
    )
    role = models.CharField(
        max_length=16,
        choices=RoomRole.choices,
        default=RoomRole.MEMBER,
    )
    joined_at = models.DateTimeField()
    invited_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="room_memberships_invited",
    )

    class Meta:
        db_table = "room_memberships"
        indexes = [
            models.Index(fields=["room"]),
            models.Index(fields=["user"]),
            models.Index(fields=["room", "role"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["room", "user"],
                name="unique_room_membership",
            ),
        ]
```

### Notes

* Owner SHOULD have a membership row with role `owner`.
* Role checks should be wrapped in helper/service methods:

  * `is_owner`
  * `is_admin`
  * `can_moderate`

---

## 8.3 RoomBan Model

```python
class RoomBan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        "chat.Room",
        on_delete=models.CASCADE,
        related_name="bans",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="room_bans",
    )
    banned_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="room_bans_issued",
    )
    reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "room_bans"
        indexes = [
            models.Index(fields=["room"]),
            models.Index(fields=["user"]),
            models.Index(fields=["room", "removed_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["room", "user"],
                name="unique_room_ban_pair",
            ),
        ]
```

### Notes

* Active ban means `removed_at IS NULL`.
* Removing a member from a room MUST be implemented as ban creation/activation plus membership deletion.

---

## 8.4 RoomInvitation Model

```python
class RoomInvitation(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        "chat.Room",
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    invited_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="room_invitations",
    )
    invited_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
        db_table = "room_invitations"
        indexes = [
            models.Index(fields=["room", "status"]),
            models.Index(fields=["invited_user", "status"]),
        ]
```

### Notes

* A conditional unique constraint for pending invites is recommended.

Example:

```python
models.UniqueConstraint(
    fields=["room", "invited_user"],
    condition=models.Q(status="pending"),
    name="unique_pending_room_invitation",
)
```

---

## 8.5 Dialog Model

```python
class Dialog(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_low = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dialogs_as_low",
    )
    user_high = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dialogs_as_high",
    )
    is_frozen = models.BooleanField(default=False)
    frozen_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "dialogs"
        indexes = [
            models.Index(fields=["user_low"]),
            models.Index(fields=["user_high"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(user_low=models.F("user_high")),
                name="dialog_not_self",
            ),
            models.UniqueConstraint(
                fields=["user_low", "user_high"],
                name="unique_dialog_pair",
            ),
        ]
```

### Notes

* Dialog pair MUST be canonically ordered in service layer.
* This model intentionally avoids a separate participants table because dialogs are exactly two users.
* Sending to a frozen dialog MUST be prevented in service layer.

### Suggested Helper

```python
def includes_user(self, user_id) -> bool:
    return self.user_low_id == user_id or self.user_high_id == user_id
```

---

## 8.6 RoomMessage Model

```python
class RoomMessage(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        "chat.Room",
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
        db_table = "room_messages"
        indexes = [
            models.Index(fields=["room", "created_at"]),
            models.Index(fields=["sender_user"]),
            models.Index(fields=["reply_to_message"]),
        ]
```

### Notes

* Django model cannot easily enforce “reply belongs to same room” with a plain DB constraint; enforce in service layer.
* Message text size <= 3 KB MUST be validated in serializer/service layer.
* Empty `text` is allowed only if attachments are present; enforce in service layer.

---

## 8.7 DialogMessage Model

```python
class DialogMessage(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dialog = models.ForeignKey(
        "chat.Dialog",
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
        db_table = "dialog_messages"
        indexes = [
            models.Index(fields=["dialog", "created_at"]),
            models.Index(fields=["sender_user"]),
            models.Index(fields=["reply_to_message"]),
        ]
```

### Notes

* Sender must be one of dialog participants; service-layer enforcement required.
* Frozen dialog send block belongs in service layer.
* Reply target must belong to same dialog; service-layer enforcement required.

---

## 8.8 RoomReadState Model

```python
class RoomReadState(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        "chat.Room",
        on_delete=models.CASCADE,
        related_name="read_states",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
        db_table = "room_read_states"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["room"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["room", "user"],
                name="unique_room_read_state",
            ),
        ]
```

### Notes

* Unread count SHOULD be derived from this marker, not stored as the source of truth.
* Service logic should ensure only room members can update it.

---

## 8.9 DialogReadState Model

```python
class DialogReadState(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dialog = models.ForeignKey(
        "chat.Dialog",
        on_delete=models.CASCADE,
        related_name="read_states",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
        db_table = "dialog_read_states"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["dialog"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["dialog", "user"],
                name="unique_dialog_read_state",
            ),
        ]
```

### Notes

* Service logic should ensure only dialog participants can update it.

---

## 9. Attachments App Model Mapping

## 9.1 Attachment Model

```python
class Attachment(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    uploaded_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="attachments",
    )
    storage_key = models.CharField(max_length=255, unique=True)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=255)
    size_bytes = models.BigIntegerField()
    comment = models.TextField(null=True, blank=True)
    binding_type = models.CharField(
        max_length=32,
        choices=AttachmentBindingType.choices,
        default=AttachmentBindingType.UNBOUND,
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "attachments"
        indexes = [
            models.Index(fields=["uploaded_by_user"]),
            models.Index(fields=["binding_type"]),
            models.Index(fields=["created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(size_bytes__gt=0),
                name="attachment_size_positive",
            ),
        ]
```

### Notes

* `storage_key` is internal only.
* Do not expose filesystem paths directly.
* File size and image size limits belong in upload service/validator.

---

## 9.2 RoomMessageAttachment Model

```python
class RoomMessageAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "room_message_attachments"
        indexes = [
            models.Index(fields=["room_message"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["attachment"],
                name="unique_room_message_attachment_once",
            ),
            models.UniqueConstraint(
                fields=["room_message", "attachment"],
                name="unique_room_message_attachment_pair",
            ),
        ]
```

### Notes

* When creating this binding, service logic MUST set:

  * `attachment.binding_type = room_message`
* Service logic MUST ensure attachment is currently unbound.

---

## 9.3 DialogMessageAttachment Model

```python
class DialogMessageAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dialog_message_attachments"
        indexes = [
            models.Index(fields=["dialog_message"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["attachment"],
                name="unique_dialog_message_attachment_once",
            ),
            models.UniqueConstraint(
                fields=["dialog_message", "attachment"],
                name="unique_dialog_message_attachment_pair",
            ),
        ]
```

### Notes

* When creating this binding, service logic MUST set:

  * `attachment.binding_type = dialog_message`

---

## 10. Audit App Model Mapping

## 10.1 ModerationEvent Model

```python
class ModerationEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action_type = models.CharField(
        max_length=64,
        choices=ModerationActionType.choices,
    )
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_events_acted",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_events_targeted",
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
        related_name="+",
    )
    session = models.ForeignKey(
        "accounts.UserSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    metadata_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "moderation_events"
        indexes = [
            models.Index(fields=["action_type"]),
            models.Index(fields=["actor_user"]),
            models.Index(fields=["target_user"]),
            models.Index(fields=["room"]),
            models.Index(fields=["created_at"]),
        ]
```

### Notes

* This is audit/supporting data.
* Core authorization must not depend solely on this table.

---

## 11. Recommended Model Managers and QuerySets

Custom managers/querysets SHOULD be introduced for common active-state filtering.

---

## 11.1 PeerBanQuerySet

```python
class PeerBanQuerySet(models.QuerySet):
    def active(self):
        return self.filter(removed_at__isnull=True)
```

---

## 11.2 RoomBanQuerySet

```python
class RoomBanQuerySet(models.QuerySet):
    def active(self):
        return self.filter(removed_at__isnull=True)
```

---

## 11.3 FriendRequestQuerySet

```python
class FriendRequestQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=FriendRequestStatus.PENDING)
```

---

## 11.4 RoomInvitationQuerySet

```python
class RoomInvitationQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=RoomInvitationStatus.PENDING)
```

---

## 12. Recommended Service Layer Responsibilities

Some rules MUST NOT live only in model `save()` because they span multiple models.

The project SHOULD have explicit services such as:

* `RegistrationService`
* `SessionService`
* `FriendshipService`
* `PeerBanService`
* `RoomService`
* `RoomModerationService`
* `InvitationService`
* `DialogService`
* `RoomMessageService`
* `DialogMessageService`
* `AttachmentService`
* `PresenceService`
* `ReadStateService`
* `ModerationAuditService`

---

## 12.1 RegistrationService

Responsible for:

* normalized email creation
* username immutability guarantees
* password hashing
* duplicate validation semantics

---

## 12.2 SessionService

Responsible for:

* creating `UserSession` records on login
* revoking current/selected session
* syncing Django session state with `UserSession`

---

## 12.3 FriendshipService

Responsible for:

* creating canonical friendship pairs
* accepting/rejecting friend requests
* preventing duplicate active pending requests
* removing friendship on peer ban

---

## 12.4 PeerBanService

Responsible for:

* creating/removing peer bans
* freezing dialogs when peer ban becomes active
* blocking new DM creation or sends
* keeping history readable

---

## 12.5 RoomService

Responsible for:

* room creation
* owner membership creation
* room detail role calculations
* room join/leave rules
* owner leave prohibition

---

## 12.6 RoomModerationService

Responsible for:

* promote/demote admin
* remove member as ban
* create room ban
* unban
* membership revocation
* room deletion cascade orchestration
* moderation event creation

---

## 12.7 InvitationService

Responsible for:

* private room invite creation
* duplicate pending invite prevention
* acceptance/rejection flow
* membership creation on accept

---

## 12.8 DialogService

Responsible for:

* canonical dialog pair creation
* friendship checks
* peer-ban checks
* freeze/unfreeze behavior
* dialog retrieval by pair

---

## 12.9 RoomMessageService

Responsible for:

* membership validation
* room-ban validation
* reply scope validation
* message length validation
* attachment binding
* unread updates
* persistence-before-broadcast

---

## 12.10 DialogMessageService

Responsible for:

* participant validation
* frozen dialog validation
* peer-ban/friendship validation
* reply scope validation
* attachment binding
* unread updates
* persistence-before-broadcast

---

## 12.11 AttachmentService

Responsible for:

* upload validation
* storage key generation
* file/image size enforcement
* authorized download resolution
* room/dialog access validation
* cleanup on room/dialog deletion

---

## 12.12 PresenceService

Responsible for:

* connection heartbeat updates
* tab/session aggregation
* user presence transition calculations
* updating `User.presence_state`
* broadcasting presence updates

---

## 12.13 ReadStateService

Responsible for:

* mark-as-read updates
* room/dialog unread count derivation
* read marker consistency

---

## 13. Serializer Mapping Guidance

The database model shape SHOULD NOT be exposed directly.

Examples:

* `RoomMembership.role` maps into room member API role field.
* `Dialog.user_low/user_high` must be converted into `other_user` depending on requester.
* `Attachment.storage_key` MUST never be serialized publicly.
* `User.email` MUST not appear in public profile serializers.
* `RoomBan.banned_by_user` maps into `banned_by` in ban list responses.

---

## 14. Deletion Behavior Mapping

## 14.1 User deletion

In Django, user deletion SHOULD be orchestrated by service logic, not by calling `user.delete()` casually.

Required behavior:

* delete owned rooms first
* remove membership in other rooms
* delete friendships, friend requests, bans via cascades
* delete sessions/presence via cascades

### Recommendation

Create a dedicated method such as:

```python
AccountDeletionService.delete_user(user, password_confirmation=...)
```

---

## 14.2 Room deletion

Room deletion MUST:

* delete room messages
* delete room bindings
* delete room read states
* delete room memberships
* delete room bans/invitations
* delete bound files from filesystem

### Recommendation

Do not rely only on DB cascade for storage cleanup. Use a service that:

1. finds bound attachments
2. deletes storage objects
3. deletes DB rows in a transactionally safe order

---

## 14.3 Dialog deletion

If dialogs are ever deleted:

* remove bound attachment files
* delete DB rows safely
* preserve audit rows as detached if desired

---

## 15. Recommended Validation Placement

## 15.1 Model-level clean()

Use `clean()` for local row validation such as:

* non-self relationships
* positive attachment size
* obvious field invariants

## 15.2 Serializer validation

Use serializer validation for:

* request shape
* message text length
* enum value validation
* required API payload logic

## 15.3 Service validation

Use service-layer validation for multi-model rules:

* room membership + ban + send checks
* dialog participant + freeze + friendship checks
* owner leave prevention
* remove-member-as-ban semantics
* reply belongs to same chat
* attachment is unbound before binding

---

## 16. Recommended `select_related` / `prefetch_related` Use

To avoid N+1 behavior in hot paths:

### 16.1 Room member listing

Use `select_related("user")`

### 16.2 Room messages

Use `select_related("sender_user", "reply_to_message", "reply_to_message__sender_user")`
and `prefetch_related("attachment_bindings__attachment")`

### 16.3 Dialog messages

Use same strategy as room messages

### 16.4 Joined room list

Annotate unread counts or compute via efficient subqueries rather than per-room loops

### 16.5 Dialog list

Preload other user and last message via efficient annotations or subqueries

---

## 17. Suggested Django Constraint Examples

Some schema constraints map cleanly to Django.

### 17.1 Unique membership

```python
models.UniqueConstraint(
    fields=["room", "user"],
    name="unique_room_membership",
)
```

### 17.2 Unique dialog pair

```python
models.UniqueConstraint(
    fields=["user_low", "user_high"],
    name="unique_dialog_pair",
)
```

### 17.3 Conditional unique pending friend request

```python
models.UniqueConstraint(
    fields=["from_user", "to_user"],
    condition=models.Q(status=FriendRequestStatus.PENDING),
    name="unique_pending_friend_request",
)
```

### 17.4 Conditional unique pending room invitation

```python
models.UniqueConstraint(
    fields=["room", "invited_user"],
    condition=models.Q(status=RoomInvitationStatus.PENDING),
    name="unique_pending_room_invitation",
)
```

---

## 18. Things That MUST NOT Be Modeled Incorrectly

The following mistakes MUST be avoided:

* using a many-to-many field for friendships without canonical pair control
* using a generic polymorphic message target for initial version if it weakens integrity
* exposing attachment storage paths directly
* storing raw password reset tokens
* relying only on frontend for room/dialog authorization
* omitting owner membership row from room membership model
* allowing attachment to bind to more than one message
* creating a dialog participants table for exactly-two-user dialogs unless there is a strong reason
* storing unread counts as the only source of truth

---

## 19. Suggested Migration Order in Django

Recommended model migration order:

1. accounts user
2. password reset token
3. user session
4. presence connection
5. friend request
6. friendship
7. peer ban
8. room
9. room membership
10. room ban
11. room invitation
12. dialog
13. room message
14. dialog message
15. attachment
16. room message attachment
17. dialog message attachment
18. room read state
19. dialog read state
20. moderation event

---

## 20. Minimal Example Import Topology

To avoid circular imports:

* put enums in shared module per app or `common/enums.py`
* reference models by string where needed
* keep service layer separate from models
* avoid importing consumers/views inside models

Example:

```python
# chat/models.py
class RoomMembership(models.Model):
    room = models.ForeignKey("chat.Room", ...)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, ...)
```

---

## 21. Compliance Summary

A Django model implementation based on this document is compliant only if it supports all required contract behaviors, including:

* unique email and username
* immutable username
* session listing/revocation metadata
* multi-tab presence tracking
* friend requests and friendships
* peer bans
* unique room names
* room owner/admin/member roles
* room invitations and room bans
* exactly-two-user dialogs
* room and dialog messages
* replies
* attachments with safe one-message binding
* per-user read states
* audit-relevant moderation events

Models alone are not sufficient.

A compliant implementation MUST combine:

* Django models
* database constraints
* serializer validation
* service-layer business logic
* authorization enforcement
* storage cleanup orchestration

---



