# SCHEMA.md

## 1. Purpose

This document defines the initial database schema for the Online Chat Server.

It is authoritative for persistent data design and is intended to align with:

- `AGENTS.md`
- `API_CONTRACT.md`

This schema covers all required core entities needed to support:

- authentication and user identity
- active session metadata
- friends and friend requests
- peer bans
- rooms and room membership
- room admins
- room bans
- room invitations
- dialogs
- messages
- attachments
- unread/read state
- audit-relevant moderation metadata

This document defines the **logical schema** and the required relational structure. It is technology-aware, but implementation details such as Django model class names or SQLAlchemy mappings MAY vary as long as this schema is preserved.

---

## 2. Global Schema Rules

- All primary keys MUST be stable and externally serializable as strings.
- All timestamp fields MUST be stored in UTC.
- All tables MUST include explicit primary keys.
- Foreign key constraints MUST be enforced unless explicitly stated otherwise.
- Required uniqueness constraints MUST be enforced at the database level.
- Required referential integrity MUST be enforced at the database level where practical.
- Authorization MUST NOT rely solely on the schema; service-layer checks remain required.
- Soft delete is NOT required unless explicitly stated.
- This initial schema assumes hard deletion for entities that must be permanently removed.

---

## 3. ID Strategy

The schema MAY use UUID-based primary keys, ULIDs, or another string-safe identifier format.

The following examples assume string identifiers such as:

- `usr_*`
- `sess_*`
- `room_*`
- `dlg_*`
- `msg_*`
- `att_*`

Implementation MAY physically store these as UUID columns, but the public API MUST serialize them as strings.

---

## 4. Enum Definitions

The following logical enums MUST exist.

## 4.1 PresenceState

Allowed values:

- `online`
- `afk`
- `offline`

## 4.2 RoomVisibility

Allowed values:

- `public`
- `private`

## 4.3 RoomRole

Allowed values:

- `owner`
- `admin`
- `member`

## 4.4 ChatType

Allowed values:

- `room`
- `dialog`

## 4.5 AttachmentBindingType

Allowed values:

- `unbound`
- `room_message`
- `dialog_message`

## 4.6 FriendRequestStatus

Allowed values:

- `pending`
- `accepted`
- `rejected`
- `cancelled`

## 4.7 RoomInvitationStatus

Allowed values:

- `pending`
- `accepted`
- `rejected`
- `revoked`

## 4.8 ModerationActionType

Allowed values:

- `room_created`
- `room_updated`
- `room_deleted`
- `member_removed`
- `member_banned`
- `member_unbanned`
- `admin_promoted`
- `admin_demoted`
- `peer_ban_created`
- `peer_ban_removed`
- `message_deleted`
- `session_revoked`

---

## 5. Core Identity and Authentication Tables

## 5.1 users

### Purpose
Stores registered user accounts.

### Columns

- `id` — PK, string/UUID, not null
- `email` — varchar, not null
- `username` — varchar, not null
- `password_hash` — varchar, not null
- `presence_state` — enum `PresenceState`, not null, default `offline`
- `presence_last_changed_at` — timestamptz, not null
- `is_active` — boolean, not null, default `true`
- `created_at` — timestamptz, not null
- `updated_at` — timestamptz, not null

### Constraints

- PK on `id`
- UNIQUE on `email`
- UNIQUE on `username`
- CHECK `email` not empty
- CHECK `username` not empty

### Rules

- Username is immutable after creation at the application layer.
- Email uniqueness MUST be case-normalized consistently by implementation.
- Passwords MUST be stored only as secure hashes.

---

## 5.2 password_reset_tokens

### Purpose
Stores password reset tokens.

### Columns

- `id` — PK, string/UUID, not null
- `user_id` — FK to `users.id`, not null
- `token_hash` — varchar, not null
- `expires_at` — timestamptz, not null
- `used_at` — timestamptz, null
- `created_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `user_id -> users.id` ON DELETE CASCADE
- UNIQUE on `token_hash`

### Rules

- Raw tokens MUST NOT be stored.
- Expired or used tokens MUST be rejected by application logic.

---

## 5.3 user_sessions

### Purpose
Stores active-session metadata required for session listing and targeted revocation.

### Columns

- `id` — PK, string/UUID, not null
- `user_id` — FK to `users.id`, not null
- `session_key_hash` — varchar, not null
- `ip_address` — varchar, null
- `user_agent` — text, null
- `is_currently_valid` — boolean, not null, default `true`
- `last_seen_at` — timestamptz, not null
- `expires_at` — timestamptz, not null
- `created_at` — timestamptz, not null
- `revoked_at` — timestamptz, null

### Constraints

- PK on `id`
- FK `user_id -> users.id` ON DELETE CASCADE
- UNIQUE on `session_key_hash`

### Indexes

- INDEX on `user_id`
- INDEX on `user_id, is_currently_valid`
- INDEX on `expires_at`

### Rules

- Session listing API MUST read from this table or an equivalent metadata source.
- Session revocation MUST invalidate both application session state and this row’s validity.

---

## 5.4 user_presence_connections

### Purpose
Tracks tab/session-level presence inputs for multi-tab presence aggregation.

### Columns

- `id` — PK, string/UUID, not null
- `user_id` — FK to `users.id`, not null
- `session_id` — FK to `user_sessions.id`, null
- `connection_key` — varchar, not null
- `tab_id` — varchar, not null
- `is_active` — boolean, not null, default `true`
- `last_interaction_at` — timestamptz, not null
- `last_heartbeat_at` — timestamptz, not null
- `connected_at` — timestamptz, not null
- `disconnected_at` — timestamptz, null
- `created_at` — timestamptz, not null
- `updated_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `user_id -> users.id` ON DELETE CASCADE
- FK `session_id -> user_sessions.id` ON DELETE SET NULL
- UNIQUE on `connection_key`

### Indexes

- INDEX on `user_id`
- INDEX on `user_id, disconnected_at`
- INDEX on `last_heartbeat_at`

### Rules

- Presence aggregation MUST treat non-disconnected rows as open tabs/connections.
- This table supports user-level presence computation across multiple tabs.

---

## 6. Friendship and Peer Ban Tables

## 6.1 friend_requests

### Purpose
Stores friend requests between users.

### Columns

- `id` — PK, string/UUID, not null
- `from_user_id` — FK to `users.id`, not null
- `to_user_id` — FK to `users.id`, not null
- `message` — text, null
- `status` — enum `FriendRequestStatus`, not null, default `pending`
- `responded_at` — timestamptz, null
- `created_at` — timestamptz, not null
- `updated_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `from_user_id -> users.id` ON DELETE CASCADE
- FK `to_user_id -> users.id` ON DELETE CASCADE
- CHECK `from_user_id <> to_user_id`

### Indexes

- INDEX on `to_user_id, status`
- INDEX on `from_user_id, status`
- UNIQUE partial-like rule required by implementation to prevent duplicate active requests between same pair

### Rules

- There MUST NOT be more than one pending request from one user to another at a time.
- If users are already friends, new pending requests MUST be rejected.

---

## 6.2 friendships

### Purpose
Stores accepted friendship relationships.

### Columns

- `id` — PK, string/UUID, not null
- `user_low_id` — FK to `users.id`, not null
- `user_high_id` — FK to `users.id`, not null
- `created_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `user_low_id -> users.id` ON DELETE CASCADE
- FK `user_high_id -> users.id` ON DELETE CASCADE
- CHECK `user_low_id <> user_high_id`
- UNIQUE on `(user_low_id, user_high_id)`

### Rules

- Pair MUST be stored in canonical sorted order to enforce uniqueness.
- Friendship existence enables personal messaging unless blocked by peer ban.

---

## 6.3 peer_bans

### Purpose
Stores user-to-user bans.

### Columns

- `id` — PK, string/UUID, not null
- `source_user_id` — FK to `users.id`, not null
- `target_user_id` — FK to `users.id`, not null
- `created_at` — timestamptz, not null
- `removed_at` — timestamptz, null

### Constraints

- PK on `id`
- FK `source_user_id -> users.id` ON DELETE CASCADE
- FK `target_user_id -> users.id` ON DELETE CASCADE
- CHECK `source_user_id <> target_user_id`
- UNIQUE on `(source_user_id, target_user_id)`

### Indexes

- INDEX on `source_user_id`
- INDEX on `target_user_id`

### Rules

- Active peer ban is represented by `removed_at IS NULL`.
- Existing dialog history remains readable, but new personal messages MUST be blocked while peer ban is active.
- Friendship SHOULD be removed when peer ban is created.

---

## 7. Room and Membership Tables

## 7.1 rooms

### Purpose
Stores chat rooms.

### Columns

- `id` — PK, string/UUID, not null
- `name` — varchar, not null
- `description` — text, null
- `visibility` — enum `RoomVisibility`, not null
- `owner_user_id` — FK to `users.id`, not null
- `created_at` — timestamptz, not null
- `updated_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `owner_user_id -> users.id` ON DELETE RESTRICT
- UNIQUE on `name`

### Indexes

- INDEX on `visibility`
- INDEX on `owner_user_id`
- INDEX on `name`

### Rules

- Room name MUST be globally unique.
- Owner cannot leave room without deleting it.
- Room deletion MUST cascade through room-scoped data.

---

## 7.2 room_memberships

### Purpose
Stores room membership and roles.

### Columns

- `id` — PK, string/UUID, not null
- `room_id` — FK to `rooms.id`, not null
- `user_id` — FK to `users.id`, not null
- `role` — enum `RoomRole`, not null, default `member`
- `joined_at` — timestamptz, not null
- `invited_by_user_id` — FK to `users.id`, null
- `created_at` — timestamptz, not null
- `updated_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `room_id -> rooms.id` ON DELETE CASCADE
- FK `user_id -> users.id` ON DELETE CASCADE
- FK `invited_by_user_id -> users.id` ON DELETE SET NULL
- UNIQUE on `(room_id, user_id)`

### Indexes

- INDEX on `room_id`
- INDEX on `user_id`
- INDEX on `room_id, role`

### Rules

- Exactly one membership row per user per room.
- Owner SHOULD also have a membership row with `role = owner`.
- Admins are represented by `role = admin`.
- Standard members are represented by `role = member`.

---

## 7.3 room_bans

### Purpose
Stores bans from specific rooms.

### Columns

- `id` — PK, string/UUID, not null
- `room_id` — FK to `rooms.id`, not null
- `user_id` — FK to `users.id`, not null
- `banned_by_user_id` — FK to `users.id`, not null
- `reason` — text, null
- `created_at` — timestamptz, not null
- `removed_at` — timestamptz, null

### Constraints

- PK on `id`
- FK `room_id -> rooms.id` ON DELETE CASCADE
- FK `user_id -> users.id` ON DELETE CASCADE
- FK `banned_by_user_id -> users.id` ON DELETE RESTRICT
- UNIQUE on `(room_id, user_id)`

### Indexes

- INDEX on `room_id`
- INDEX on `user_id`
- INDEX on `room_id, removed_at`

### Rules

- Active room ban is represented by `removed_at IS NULL`.
- Removing a member from a room MUST create or activate a room ban.
- Banned users MUST lose access immediately to room messages and room attachments.

---

## 7.4 room_invitations

### Purpose
Stores invitations to private rooms.

### Columns

- `id` — PK, string/UUID, not null
- `room_id` — FK to `rooms.id`, not null
- `invited_user_id` — FK to `users.id`, not null
- `invited_by_user_id` — FK to `users.id`, not null
- `status` — enum `RoomInvitationStatus`, not null, default `pending`
- `responded_at` — timestamptz, null
- `created_at` — timestamptz, not null
- `updated_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `room_id -> rooms.id` ON DELETE CASCADE
- FK `invited_user_id -> users.id` ON DELETE CASCADE
- FK `invited_by_user_id -> users.id` ON DELETE RESTRICT

### Indexes

- INDEX on `room_id, status`
- INDEX on `invited_user_id, status`

### Rules

- There MUST NOT be duplicate active pending invitations for the same room-user pair.
- Accepting invitation SHOULD create room membership.
- Rejected or revoked invitations MUST NOT grant access.

---

## 8. Dialog Tables

## 8.1 dialogs

### Purpose
Stores personal one-to-one dialogs.

### Columns

- `id` — PK, string/UUID, not null
- `user_low_id` — FK to `users.id`, not null
- `user_high_id` — FK to `users.id`, not null
- `is_frozen` — boolean, not null, default `false`
- `frozen_reason` — text, null
- `created_at` — timestamptz, not null
- `updated_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `user_low_id -> users.id` ON DELETE CASCADE
- FK `user_high_id -> users.id` ON DELETE CASCADE
- CHECK `user_low_id <> user_high_id`
- UNIQUE on `(user_low_id, user_high_id)`

### Indexes

- INDEX on `user_low_id`
- INDEX on `user_high_id`

### Rules

- Dialog pairs MUST be stored in canonical sorted order.
- Exactly one dialog per user pair.
- Dialogs have exactly two participants by construction.
- `is_frozen = true` indicates that history remains readable but new messages are blocked.

---

## 9. Message Tables

To keep referential integrity strong and authorization simple, this initial schema uses **separate room and dialog message tables** instead of a polymorphic message target.

This is preferred for initial correctness.

## 9.1 room_messages

### Purpose
Stores messages sent in rooms.

### Columns

- `id` — PK, string/UUID, not null
- `room_id` — FK to `rooms.id`, not null
- `sender_user_id` — FK to `users.id`, not null
- `text` — text, null
- `reply_to_message_id` — FK to `room_messages.id`, null
- `is_edited` — boolean, not null, default `false`
- `created_at` — timestamptz, not null
- `updated_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `room_id -> rooms.id` ON DELETE CASCADE
- FK `sender_user_id -> users.id` ON DELETE RESTRICT
- FK `reply_to_message_id -> room_messages.id` ON DELETE SET NULL
- CHECK message has non-empty text or at least one attachment enforced partly in service layer
- CHECK text size <= 3 KB enforced in application/service layer

### Indexes

- INDEX on `room_id, created_at`
- INDEX on `sender_user_id`
- INDEX on `reply_to_message_id`

### Rules

- Ordering for history MUST primarily use `created_at`, with stable secondary ordering by `id`.
- Replies MUST reference another message in the same room; this MUST be enforced in service logic.

---

## 9.2 dialog_messages

### Purpose
Stores messages sent in dialogs.

### Columns

- `id` — PK, string/UUID, not null
- `dialog_id` — FK to `dialogs.id`, not null
- `sender_user_id` — FK to `users.id`, not null
- `text` — text, null
- `reply_to_message_id` — FK to `dialog_messages.id`, null
- `is_edited` — boolean, not null, default `false`
- `created_at` — timestamptz, not null
- `updated_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `dialog_id -> dialogs.id` ON DELETE CASCADE
- FK `sender_user_id -> users.id` ON DELETE RESTRICT
- FK `reply_to_message_id -> dialog_messages.id` ON DELETE SET NULL
- CHECK message has non-empty text or at least one attachment enforced partly in service layer
- CHECK text size <= 3 KB enforced in application/service layer

### Indexes

- INDEX on `dialog_id, created_at`
- INDEX on `sender_user_id`
- INDEX on `reply_to_message_id`

### Rules

- Sender MUST be one of the two dialog participants; enforce in service logic.
- Replies MUST reference another message in the same dialog; enforce in service logic.
- New sends MUST be rejected when dialog is frozen.

---

## 10. Attachment Tables

## 10.1 attachments

### Purpose
Stores uploaded file/image metadata.

### Columns

- `id` — PK, string/UUID, not null
- `uploaded_by_user_id` — FK to `users.id`, not null
- `storage_key` — varchar, not null
- `original_filename` — varchar, not null
- `content_type` — varchar, not null
- `size_bytes` — bigint, not null
- `comment` — text, null
- `binding_type` — enum `AttachmentBindingType`, not null, default `unbound`
- `created_at` — timestamptz, not null
- `updated_at` — timestamptz, not null
- `deleted_at` — timestamptz, null

### Constraints

- PK on `id`
- FK `uploaded_by_user_id -> users.id` ON DELETE RESTRICT
- UNIQUE on `storage_key`
- CHECK `size_bytes > 0`

### Indexes

- INDEX on `uploaded_by_user_id`
- INDEX on `binding_type`
- INDEX on `created_at`

### Rules

- Raw files are stored on local filesystem; `storage_key` references internal storage location.
- Filesystem path MUST NOT be exposed directly in API.
- Size limits:
  - generic file max: 20 MB
  - image max: 3 MB
- Size/type validation is enforced in service layer.

---

## 10.2 room_message_attachments

### Purpose
Binds attachments to room messages.

### Columns

- `id` — PK, string/UUID, not null
- `room_message_id` — FK to `room_messages.id`, not null
- `attachment_id` — FK to `attachments.id`, not null
- `created_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `room_message_id -> room_messages.id` ON DELETE CASCADE
- FK `attachment_id -> attachments.id` ON DELETE CASCADE
- UNIQUE on `attachment_id`
- UNIQUE on `(room_message_id, attachment_id)`

### Indexes

- INDEX on `room_message_id`

### Rules

- An attachment may be bound to only one message total.
- When bound here, `attachments.binding_type` MUST be `room_message`.

---

## 10.3 dialog_message_attachments

### Purpose
Binds attachments to dialog messages.

### Columns

- `id` — PK, string/UUID, not null
- `dialog_message_id` — FK to `dialog_messages.id`, not null
- `attachment_id` — FK to `attachments.id`, not null
- `created_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `dialog_message_id -> dialog_messages.id` ON DELETE CASCADE
- FK `attachment_id -> attachments.id` ON DELETE CASCADE
- UNIQUE on `attachment_id`
- UNIQUE on `(dialog_message_id, attachment_id)`

### Indexes

- INDEX on `dialog_message_id`

### Rules

- An attachment may be bound to only one message total.
- When bound here, `attachments.binding_type` MUST be `dialog_message`.

---

## 11. Read State and Unread Tracking Tables

This schema stores per-user read state rather than denormalized unread counters as the primary source of truth.

Unread counts SHOULD be computed from last-read markers and message timestamps, with optional caching if needed.

## 11.1 room_read_states

### Purpose
Stores per-user last-read position for rooms.

### Columns

- `id` — PK, string/UUID, not null
- `room_id` — FK to `rooms.id`, not null
- `user_id` — FK to `users.id`, not null
- `last_read_room_message_id` — FK to `room_messages.id`, null
- `last_read_at` — timestamptz, null
- `updated_at` — timestamptz, not null
- `created_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `room_id -> rooms.id` ON DELETE CASCADE
- FK `user_id -> users.id` ON DELETE CASCADE
- FK `last_read_room_message_id -> room_messages.id` ON DELETE SET NULL
- UNIQUE on `(room_id, user_id)`

### Indexes

- INDEX on `user_id`
- INDEX on `room_id`

### Rules

- Only current room members may maintain/use room read state.
- Unread counts in room list derive from messages newer than read marker.

---

## 11.2 dialog_read_states

### Purpose
Stores per-user last-read position for dialogs.

### Columns

- `id` — PK, string/UUID, not null
- `dialog_id` — FK to `dialogs.id`, not null
- `user_id` — FK to `users.id`, not null
- `last_read_dialog_message_id` — FK to `dialog_messages.id`, null
- `last_read_at` — timestamptz, null
- `updated_at` — timestamptz, not null
- `created_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `dialog_id -> dialogs.id` ON DELETE CASCADE
- FK `user_id -> users.id` ON DELETE CASCADE
- FK `last_read_dialog_message_id -> dialog_messages.id` ON DELETE SET NULL
- UNIQUE on `(dialog_id, user_id)`

### Indexes

- INDEX on `user_id`
- INDEX on `dialog_id`

### Rules

- Only dialog participants may maintain dialog read state.
- Frozen dialogs remain readable; read state remains valid.

---

## 12. Audit and Moderation Event Tables

## 12.1 moderation_events

### Purpose
Stores audit-relevant moderation actions and security-sensitive state changes.

### Columns

- `id` — PK, string/UUID, not null
- `action_type` — enum `ModerationActionType`, not null
- `actor_user_id` — FK to `users.id`, null
- `target_user_id` — FK to `users.id`, null
- `room_id` — FK to `rooms.id`, null
- `dialog_id` — FK to `dialogs.id`, null
- `room_message_id` — FK to `room_messages.id`, null
- `dialog_message_id` — FK to `dialog_messages.id`, null
- `attachment_id` — FK to `attachments.id`, null
- `session_id` — FK to `user_sessions.id`, null
- `metadata_json` — jsonb, not null, default `{}`
- `created_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `actor_user_id -> users.id` ON DELETE SET NULL
- FK `target_user_id -> users.id` ON DELETE SET NULL
- FK `room_id -> rooms.id` ON DELETE SET NULL
- FK `dialog_id -> dialogs.id` ON DELETE SET NULL
- FK `room_message_id -> room_messages.id` ON DELETE SET NULL
- FK `dialog_message_id -> dialog_messages.id` ON DELETE SET NULL
- FK `attachment_id -> attachments.id` ON DELETE SET NULL
- FK `session_id -> user_sessions.id` ON DELETE SET NULL

### Indexes

- INDEX on `action_type`
- INDEX on `actor_user_id`
- INDEX on `target_user_id`
- INDEX on `room_id`
- INDEX on `created_at`

### Rules

- This table is not the primary source of truth for bans or roles.
- It exists for auditability and moderation history.

---

## 13. Optional Support Tables

These are recommended but not strictly required for minimal correctness.

## 13.1 websocket_subscriptions

### Purpose
Tracks explicit chat subscriptions if application design wants persistence/observability.

### Columns

- `id` — PK, string/UUID, not null
- `user_id` — FK to `users.id`, not null
- `session_id` — FK to `user_sessions.id`, null
- `connection_key` — varchar, not null
- `chat_type` — enum `ChatType`, not null
- `room_id` — FK to `rooms.id`, null
- `dialog_id` — FK to `dialogs.id`, null
- `subscribed_at` — timestamptz, not null
- `unsubscribed_at` — timestamptz, null
- `created_at` — timestamptz, not null

### Constraints

- PK on `id`
- FK `user_id -> users.id` ON DELETE CASCADE
- FK `session_id -> user_sessions.id` ON DELETE SET NULL
- FK `room_id -> rooms.id` ON DELETE CASCADE
- FK `dialog_id -> dialogs.id` ON DELETE CASCADE
- CHECK exactly one of `room_id` or `dialog_id` is non-null
- CHECK chat type matches populated target column

### Rules

- This table MAY be omitted if subscriptions are handled entirely in-memory/Redis.

---

## 14. Referential Deletion Rules

These are mandatory lifecycle expectations.

## 14.1 User Deletion

When a user is deleted:

- `password_reset_tokens` MUST delete via cascade
- `user_sessions` MUST delete via cascade
- `user_presence_connections` MUST delete via cascade
- `friend_requests` MUST delete via cascade
- `friendships` MUST delete via cascade
- `peer_bans` MUST delete via cascade
- membership in non-owned rooms MUST delete via cascade
- dialogs involving user MUST delete via cascade unless product chooses archival; initial schema uses cascade
- owned rooms MUST be deleted explicitly by service logic first
- room-scoped data of owned rooms MUST be deleted through room deletion cascade

### Important
Room ownership uses `ON DELETE RESTRICT` to force service logic to handle owned-room deletion explicitly and safely.

---

## 14.2 Room Deletion

When a room is deleted:

- `room_memberships` MUST delete via cascade
- `room_bans` MUST delete via cascade
- `room_invitations` MUST delete via cascade
- `room_messages` MUST delete via cascade
- `room_message_attachments` MUST delete via cascade
- `room_read_states` MUST delete via cascade
- room-linked moderation rows MAY remain with `room_id = NULL` if desired, but initial schema allows SET NULL only where parent still exists; for strict permanent deletion, moderation rows may also be retained as detached audit events

### Attachment lifecycle
If a room is deleted, all attachments bound to room messages in that room MUST also be permanently removed from storage.

Database-level deletion of `attachments` themselves MAY be handled either by:

- cascade through a cleanup routine, or
- application deletion transaction

Initial implementation SHOULD explicitly delete attachment rows and storage objects tied to deleted room messages.

---

## 14.3 Dialog Deletion

When a dialog is deleted:

- `dialog_messages` MUST delete via cascade
- `dialog_message_attachments` MUST delete via cascade
- `dialog_read_states` MUST delete via cascade

Bound dialog attachments SHOULD be explicitly cleaned from storage as part of dialog deletion if the dialog itself is ever hard-deleted.

---

## 15. Cross-Table Invariants

These invariants MUST be enforced by a combination of database constraints and service-layer logic.

## 15.1 Friendship Pair Ordering

- `friendships.user_low_id < friendships.user_high_id` MUST hold logically.
- If DB supports it cleanly, a CHECK SHOULD enforce canonical ordering.

## 15.2 Dialog Pair Ordering

- `dialogs.user_low_id < dialogs.user_high_id` MUST hold logically.
- If DB supports it cleanly, a CHECK SHOULD enforce canonical ordering.

## 15.3 Room Owner Membership

- Room owner MUST also be present in `room_memberships` with role `owner`.

## 15.4 Single Active Membership

- There is at most one membership row per `(room_id, user_id)`.

## 15.5 Single Active Room Ban

- There is at most one room ban row per `(room_id, user_id)`.

## 15.6 Single Active Peer Ban

- There is at most one peer ban row per `(source_user_id, target_user_id)`.

## 15.7 Attachment Single Binding

- An attachment can be unbound, bound to a room message, or bound to a dialog message.
- It MUST NOT be bound to more than one message.
- Binding type MUST match whichever join table contains the attachment.

## 15.8 Reply Scope Integrity

- A room message may reply only to another room message in the same room.
- A dialog message may reply only to another dialog message in the same dialog.

## 15.9 Dialog Participant Sending

- `dialog_messages.sender_user_id` MUST match one of the dialog’s two participants.

## 15.10 Frozen Dialog Constraint

- If `dialogs.is_frozen = true`, no new dialog messages may be inserted.

## 15.11 Room Ban Access Constraint

- If an active `room_bans` row exists for `(room_id, user_id)`, that user MUST NOT have active room membership.
- Service logic MUST remove membership when banning/removing.

---

## 16. Required Index Strategy

The implementation MUST create indexes sufficient for the following hot paths:

- login by email
- lookup by username
- session list by user
- public room catalog search by name
- joined rooms by user
- room members by room
- room messages by room ordered by time
- dialog messages by dialog ordered by time
- friend requests incoming/outgoing
- room bans by room
- invitations by invited user
- unread/read state lookup by user + chat
- presence connections by user
- active peer bans lookup by user pair

Recommended indexes are already listed per table and MUST be implemented or improved equivalently.

---

## 17. Initial PostgreSQL Mapping Guidance

The initial physical PostgreSQL mapping SHOULD use:

- `uuid` for primary keys, or `varchar` if repository ID generation requires prefixed string storage
- `timestamptz` for all timestamps
- `jsonb` for metadata blobs
- PostgreSQL enum types or constrained text columns for enums

Recommended normalized text handling:

- store email in normalized lowercase form
- store username in a consistent canonical form if case-insensitive uniqueness is intended

---

## 18. Suggested Table Creation Order

The following creation order is recommended:

1. `users`
2. `password_reset_tokens`
3. `user_sessions`
4. `user_presence_connections`
5. `friend_requests`
6. `friendships`
7. `peer_bans`
8. `rooms`
9. `room_memberships`
10. `room_bans`
11. `room_invitations`
12. `dialogs`
13. `room_messages`
14. `dialog_messages`
15. `attachments`
16. `room_message_attachments`
17. `dialog_message_attachments`
18. `room_read_states`
19. `dialog_read_states`
20. `moderation_events`
21. `websocket_subscriptions` if used

---

## 19. Minimal Initial Migration Scope

The first schema migration set MUST include at least:

- all tables in sections 5 through 12
- all required primary keys
- all required foreign keys
- all required uniqueness constraints
- all required indexes for hot paths
- enum definitions or equivalent constrained-value representation

`websocket_subscriptions` MAY be deferred if subscription state is not persisted initially.

---

## 20. Non-Goals of This Schema

This schema does not define:

- XMPP/Jabber federation entities
- search indexing tables
- analytics/BI schema
- rate-limit storage
- object storage migration schema
- antivirus/quarantine file pipeline
- push notification delivery tables
- email outbox tables

Those MAY be added later if required by higher-precedence documents.

---

## 21. Compliance Summary

An implementation is schema-compliant only if it can represent and enforce all of the following:

- unique email
- unique username
- immutable username at application layer
- unique room names
- room owner/admin/member roles
- room-specific bans with ban metadata
- private-room invitation flow
- friendship and friend request flow
- peer bans that freeze dialogs
- exactly-two-user dialogs
- room and dialog message history
- replies
- attachments with safe binding
- per-user read state
- active sessions and targeted session revocation metadata
- multi-tab presence input tracking
- audit-relevant moderation events

---
