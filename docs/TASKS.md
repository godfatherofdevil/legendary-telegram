# TASKS.md

## 1. Purpose

This document defines the execution plan for implementing the Online Chat Server in a way that is fully aligned with:

- `AGENTS.md`
- `API_CONTRACT.md`

This file is a delivery and sequencing guide.

It is normative for implementation planning, task decomposition, and progress tracking, but it does not override `AGENTS.md` or `API_CONTRACT.md`.

If this file conflicts with a higher-precedence document, the higher-precedence document MUST win.

---

## 2. Planning Rules

- Tasks MUST be executed in dependency order.
- Foundational tasks MUST be completed before dependent tasks begin.
- No task may be considered complete unless its required tests are added and passing.
- If a task changes externally visible behavior, relevant documentation MUST be updated before the task is considered done.
- If a task requires schema changes, migrations MUST be included in the same task or an explicitly preceding dependency task.
- Optional scope MUST NOT begin until all required core tasks are complete and stable.

---

## 3. Status Model

Each task SHOULD be tracked using one of the following statuses:

- `TODO`
- `IN PROGRESS`
- `BLOCKED`
- `DONE`

A task MUST NOT be marked `DONE` unless it satisfies the definition of done from `AGENTS.md`.

---

## 4. Milestones

Implementation MUST proceed through these milestones in order:

1. Repository foundation and local execution
2. Data model and migrations
3. Authentication and session management
4. Core room and dialog domain
5. Messaging and history
6. Attachments and file access
7. Presence and unread state
8. Moderation, bans, and invitations
9. WebSocket real-time protocol
10. UI integration
11. Deployment hardening
12. Optional advanced scope

---

## 5. Task Breakdown

## M1. Repository Foundation and Local Execution

### T1.1 Create backend project scaffold
**Status:** DONE

#### Objective
Create the initial project structure for the Python/Django backend aligned with repository constraints.

#### Requirements
- MUST use Python 3.12+
- MUST use Django
- MUST include Django REST Framework
- MUST include Django Channels
- MUST include Redis integration
- MUST be compatible with PostgreSQL
- MUST be runnable in Docker

#### Deliverables
- backend project scaffold
- dependency manifest
- settings split or equivalent configuration organization
- ASGI entrypoint
- base app/module structure

#### Acceptance Criteria
- project boots successfully
- ASGI app loads successfully
- no placeholder code is presented as complete

#### Tests
- smoke test for application startup if repository test strategy supports it

---

### T1.2 Create Docker Compose local environment
**Status:** DONE

#### Objective
Provide a local environment that can run the full project stack.

#### Requirements
- MUST support `docker compose up` from repo root
- MUST include:
  - app service
  - postgres service
  - redis service
- MUST expose required ports
- MUST support backend startup against containerized dependencies

#### Deliverables
- `docker-compose.yml`
- container build files
- environment variable documentation or examples

#### Acceptance Criteria
- application containers start
- backend connects to postgres
- backend connects to redis

#### Tests
- manual or automated smoke verification of container health

---

### T1.3 Establish repository quality tooling
**Status:** DONE

#### Objective
Add baseline development tooling needed for safe implementation.

#### Requirements
- SHOULD include formatting
- SHOULD include linting
- SHOULD include test runner configuration
- SHOULD include environment variable template

#### Deliverables
- formatter config
- linter config
- test config
- `.env.example`

#### Acceptance Criteria
- local developer workflow is documented and usable

---

## M2. Data Model and Migrations

### T2.1 Read and map SCHEMA.md to implementation model
**Status:** DONE

#### Objective
Translate `SCHEMA.md` into concrete application models and migration plan.

#### Requirements
- MUST treat `SCHEMA.md` as source of truth
- MUST identify all entities required by `API_CONTRACT.md`
- MUST identify constraints and relationships before coding model layer

#### Deliverables
- entity mapping notes in implementation work
- model list
- migration plan

#### Acceptance Criteria
- all required API resources map to concrete model concepts
- no major contract entity is missing

---

### T2.2 Implement core database models
**Status:** DONE

#### Objective
Create the core persistent model layer.

#### Required Entities
At minimum, the implementation MUST support model concepts for:

- user
- session record or equivalent session metadata
- friend request
- friendship
- peer ban
- room
- room membership
- room admin role or role field
- room ban
- room invitation
- dialog
- dialog participant invariant
- message
- attachment
- unread/read state
- audit-relevant moderation metadata where needed for contract-visible behavior

#### Required Constraints
- unique email
- unique username
- unique room name
- exactly-two-participant constraint for dialogs
- message-to-chat consistency
- attachment ownership/binding consistency

#### Deliverables
- application models
- relationship definitions
- integrity constraints

#### Acceptance Criteria
- model layer can represent all required product flows
- invariants are enforceable at model/service layer

---

### T2.3 Generate and verify migrations
**Status:** DONE

#### Objective
Create the initial migration set for all required core entities.

#### Requirements
- MUST generate migrations for schema changes
- MUST preserve migration reproducibility
- MUST not rely on implicit database drift
- MUST align with `SCHEMA.md`

#### Deliverables
- migration files
- migration application instructions if needed

#### Acceptance Criteria
- fresh database can migrate successfully
- schema matches required entities and constraints

#### Tests
- migration apply test on clean database

---

## M3. Authentication and Session Management

### T3.1 Implement registration endpoint
**Status:** DONE

#### Endpoint
- `POST /api/v1/auth/register`

#### Requirements
- MUST support email, username, password
- MUST enforce unique email
- MUST enforce unique username
- MUST keep username immutable
- MUST return contract-compliant response

#### Acceptance Criteria
- valid registration succeeds
- duplicate email fails correctly
- duplicate username fails correctly

#### Tests
- registration success
- duplicate email rejection
- duplicate username rejection
- validation failure cases

---

### T3.2 Implement login and authenticated session creation
**Status:** DONE

#### Endpoints
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

#### Requirements
- MUST authenticate by email and password
- MUST create server-side authenticated session
- MUST support persistent login
- MUST expose authenticated user through `/auth/me`

#### Acceptance Criteria
- valid login sets session
- invalid credentials fail with correct status
- authenticated request returns current user
- unauthenticated request is rejected

#### Tests
- login success
- login failure
- me success
- me unauthorized

---

### T3.3 Implement logout and current-session invalidation
**Status:** DONE

#### Endpoint
- `POST /api/v1/auth/logout`

#### Requirements
- MUST invalidate only current session
- MUST NOT invalidate other active sessions

#### Acceptance Criteria
- current session becomes invalid
- second session remains valid

#### Tests
- multi-session logout isolation

---

### T3.4 Implement password change and reset flow
**Status:** DONE

#### Endpoints
- `POST /api/v1/auth/change-password`
- `POST /api/v1/auth/request-password-reset`
- `POST /api/v1/auth/reset-password`

#### Requirements
- MUST support logged-in password change
- MUST support password reset request flow
- MUST avoid leaking whether reset email exists

#### Acceptance Criteria
- change password works for valid credentials
- reset request is privacy-safe
- reset confirm updates password

#### Tests
- change password success/failure
- reset request response behavior
- reset confirm success/failure

---

### T3.5 Implement account deletion
**Status:** DONE

#### Endpoint
- `DELETE /api/v1/account`

#### Requirements
- MUST delete account
- MUST delete rooms owned by user
- MUST delete room messages and attachments for owned rooms
- MUST remove membership from other rooms

#### Acceptance Criteria
- owned rooms are deleted
- associated owned-room data is deleted
- user removed elsewhere correctly

#### Tests
- account deletion full cascade behavior
- membership cleanup verification

---

### T3.6 Implement active session listing and targeted revocation
**Status:** DONE

#### Endpoints
- `GET /api/v1/sessions`
- `DELETE /api/v1/sessions/{session_id}`

#### Requirements
- MUST show session metadata
- MUST allow revoking selected sessions
- MUST support revoking current session and non-current sessions

#### Acceptance Criteria
- session list is accurate
- selected session is revoked
- current session revocation logs out current browser only when targeted

#### Tests
- list sessions
- revoke another session
- revoke current session

---

## M4. Core Room and Dialog Domain

### T4.1 Implement user lookup endpoints
**Status:** DONE

#### Endpoints
- `GET /api/v1/users/{user_id}`
- `GET /api/v1/users/by-username/{username}`

#### Requirements
- MUST expose only permitted public fields
- MUST not expose private data such as email

#### Tests
- public profile fetch
- username lookup
- privacy assertions

---

### T4.2 Implement public room listing and joined room listing
**Status:** DONE

#### Endpoints
- `GET /api/v1/rooms/public`
- `GET /api/v1/rooms/joined`

#### Requirements
- MUST support public room search
- MUST provide joined room list for current user
- MUST include unread counts on joined rooms

#### Tests
- public room list
- public room search
- joined room list with unread counts

---

### T4.3 Implement room creation and detail retrieval
**Status:** DONE

#### Endpoints
- `POST /api/v1/rooms`
- `GET /api/v1/rooms/{room_id}`

#### Requirements
- MUST enforce unique room name
- MUST support public/private visibility
- MUST assign owner correctly
- MUST return role-aware room details

#### Tests
- room creation success
- duplicate room name rejection
- public/private visibility behavior
- room detail retrieval by authorized/unauthorized users

---

### T4.4 Implement room update and room deletion
**Status:** DONE

#### Endpoints
- `PATCH /api/v1/rooms/{room_id}`
- `DELETE /api/v1/rooms/{room_id}`

#### Requirements
- room update MUST be owner-only
- room deletion MUST be owner-only
- room deletion MUST remove room data permanently

#### Tests
- owner update success
- non-owner update rejection
- owner delete success
- non-owner delete rejection
- room deletion cascades to room messages and attachments

---

### T4.5 Implement room join and leave flows
**Status:** DONE

#### Endpoints
- `POST /api/v1/rooms/{room_id}/join`
- `POST /api/v1/rooms/{room_id}/leave`

#### Requirements
- MUST allow joining public rooms only
- MUST prevent banned users from joining
- MUST prevent owner from leaving own room

#### Tests
- join public room success
- join private room rejection
- join banned user rejection
- leave room success
- owner leave rejection

---

### T4.6 Implement room member listing
**Status:** DONE

#### Endpoint
- `GET /api/v1/rooms/{room_id}/members`

#### Requirements
- MUST expose roles and presence
- MUST paginate where applicable

#### Tests
- member list success
- unauthorized member list rejection

---

### T4.7 Implement personal dialog creation/retrieval and listing
**Status:** DONE

#### Endpoints
- `GET /api/v1/dialogs`
- `POST /api/v1/dialogs`

#### Requirements
- MUST maintain exactly two participants
- MUST only allow dialog creation if users are friends and not peer-banned
- MUST return existing dialog when one exists

#### Tests
- dialog creation success
- existing dialog reuse
- non-friend rejection
- peer-ban rejection

---

## M5. Messaging and History

### T5.1 Implement room message model/services
**Status:** DONE

#### Objective
Create service logic for room message lifecycle.

#### Requirements
- MUST support text, replies, attachments
- MUST enforce 3 KB text limit
- MUST persist before broadcast
- MUST preserve chronological ordering

#### Tests
- send message
- reply message
- message size rejection
- authorization checks

---

### T5.2 Implement room message REST endpoints
**Status:** DONE

#### Endpoints
- `GET /api/v1/rooms/{room_id}/messages`
- `POST /api/v1/rooms/{room_id}/messages`
- `PATCH /api/v1/rooms/{room_id}/messages/{message_id}`
- `DELETE /api/v1/rooms/{room_id}/messages/{message_id}`

#### Requirements
- only members may read/send
- only author may edit
- author/admin/owner may delete according to contract
- history MUST be cursor-paginated
- edits MUST expose edited state

#### Tests
- history pagination
- send/edit/delete authorization
- reply behavior
- edited indicator behavior

---

### T5.3 Implement dialog message model/services
**Status:** DONE

#### Requirements
- MUST mirror room message features where contract requires parity
- MUST block sending when dialog is frozen
- MUST allow existing frozen history to remain readable

#### Tests
- dialog send success
- frozen dialog send rejection
- history still readable after freeze

---

### T5.4 Implement dialog message REST endpoints
**Status:** DONE

#### Endpoints
- `GET /api/v1/dialogs/{dialog_id}/messages`
- `POST /api/v1/dialogs/{dialog_id}/messages`
- `PATCH /api/v1/dialogs/{dialog_id}/messages/{message_id}`
- `DELETE /api/v1/dialogs/{dialog_id}/messages/{message_id}`

#### Requirements
- only participants may access
- only author may edit/delete
- frozen dialog MUST reject new sends

#### Tests
- participant authorization
- edit/delete ownership
- frozen send rejection

---

### T5.5 Implement read markers and unread state
**Status:** DONE

#### Endpoints
- `POST /api/v1/rooms/{room_id}/read`
- `POST /api/v1/dialogs/{dialog_id}/read`

#### Requirements
- MUST clear unread state for current user in target chat
- MUST support unread counts in room/dialog summaries

#### Tests
- unread increment on new message
- unread cleared on read endpoint
- room list/dialog list unread count accuracy

---

## M6. Attachments and File Access

### T6.1 Implement attachment upload and metadata model
**Status:** DONE

#### Requirements
- MUST preserve original filename
- MUST support optional comment
- MUST track uploader
- MUST support upload-before-bind flow

#### Tests
- upload success
- metadata persistence

---

### T6.2 Implement attachment upload endpoint
**Status:** DONE

#### Endpoint
- `POST /api/v1/attachments`

#### Requirements
- MUST accept multipart/form-data
- MUST enforce:
  - max file size 20 MB
  - max image size 3 MB
- MUST return contract-compliant metadata

#### Tests
- generic file upload success
- image upload success
- oversize file rejection
- oversize image rejection

---

### T6.3 Implement attachment retrieval and download authorization
**Status:** DONE

#### Endpoints
- `GET /api/v1/attachments/{attachment_id}`
- `GET /api/v1/attachments/{attachment_id}/download`

#### Requirements
- room attachments accessible only to current room members
- dialog attachments accessible only to dialog participants
- removed users MUST lose access immediately

#### Tests
- authorized download success
- unauthorized download rejection
- access revoked after room removal/ban

---

### T6.4 Implement unbound attachment deletion
**Status:** DONE

#### Endpoint
- `DELETE /api/v1/attachments/{attachment_id}`

#### Requirements
- SHOULD allow deletion only before message binding
- MUST preserve contract semantics for bound attachments

#### Tests
- unbound delete success
- bound delete rejection if implemented as restricted

---

### T6.5 Introduce object-storage abstraction for attachments
**Status:** DONE

#### Objective
Prepare attachment storage for migration away from direct Django filesystem operations without changing the public API contract.

#### Requirements
- MUST preserve all existing attachment API fields and authorization semantics
- MUST keep `attachments.storage_key` as the canonical internal object identifier unless a higher-precedence schema change requires otherwise
- MUST replace direct path-centric attachment operations with an explicit storage service boundary
- MUST use the AWS `boto3` Python client for object operations against an S3-compatible backend
- MUST make the storage backend configurable by environment so local migration rollout can be validated safely

#### Deliverables
- attachment storage service interface for upload, stream/read, existence check, and delete
- MinIO-compatible implementation using `boto3`
- migration notes covering fallback, rollback, and cutover expectations

#### Acceptance Criteria
- attachment application code no longer depends directly on local filesystem paths in core business flows
- the API contract for upload, metadata, download, and deletion remains unchanged

#### Tests
- unit tests for object-storage service behavior
- contract-preservation tests for attachment API flows

---

### T6.6 Migrate attachment read/write/delete flows to MinIO-backed storage
**Status:** DONE

#### Objective
Move attachment binary persistence from local filesystem storage to MinIO while preserving contract-visible behavior.

#### Requirements
- MUST store all new attachment objects in bucket `uploads`
- MUST use `boto3` against the MinIO endpoint for upload, download, and delete operations
- MUST preserve original filename, size validation, and access-control rules
- MUST ensure room deletion and message-driven attachment deletion remove the corresponding MinIO object
- MUST ensure room access loss revokes attachment download immediately

#### Acceptance Criteria
- new uploads are persisted in MinIO rather than the backend container filesystem
- authorized downloads still work through the documented API endpoints
- deletion paths remove both metadata and object storage state

#### Tests
- upload success against MinIO-backed storage
- authorized download success against MinIO-backed storage
- unauthorized download rejection remains unchanged
- room deletion removes corresponding MinIO objects

---

### T6.7 Backfill existing filesystem attachments into MinIO
**Status:** DONE

#### Objective
Provide a deterministic migration path for attachments that already exist on local filesystem storage.

#### Requirements
- MUST enumerate existing attachment records and associated filesystem objects
- MUST copy existing blobs into MinIO bucket `uploads` using stable object keys
- MUST verify copied object size and presence before considering an item migrated
- MUST define behavior for missing filesystem blobs and partially migrated states
- MUST provide an idempotent migration command or job

#### Deliverables
- migration command or operational script
- verification/reporting output for migrated, skipped, and failed objects
- rollback notes for incomplete runs

#### Acceptance Criteria
- repeated migration runs do not duplicate or corrupt already migrated objects
- attachment metadata remains consistent with migrated object keys

#### Tests
- idempotent backfill test
- partial-failure handling test
- post-backfill attachment download smoke test

---

### T6.8 Implement streaming-safe attachment delivery for inline media
**Status:** DONE

#### Objective
Prevent large attachment downloads from exhausting backend memory or crashing browser media rendering by serving object-storage-backed media as a streamed response path.

#### Requirements
- MUST preserve the existing attachment authorization boundary at the backend
- MUST preserve the existing public API endpoints unless a higher-precedence contract update is required
- MUST NOT read the full attachment into backend memory before sending the response
- MUST support streamed reads from MinIO/object storage for large attachments
- MUST evaluate support for browser range requests for media playback and seeking when the object is stored in MinIO
- MUST define whether delivery uses direct backend streaming, backend proxying with passthrough headers, or short-lived backend-authorized redirects, and document the tradeoff
- MUST preserve immediate access revocation when room or dialog access is lost
- MUST preserve original filename and content type handling
- SHOULD set response headers that help browsers avoid unnecessary eager downloads for inline media previews

#### Deliverables
- delivery design decision for large attachment downloads
- backend attachment download implementation updated to use a true streaming path for object storage
- header and range-request behavior documented for attachment downloads
- operational notes covering revocation, expiry, and fallback behavior

#### Acceptance Criteria
- large attachments can be rendered or downloaded without buffering the full object in backend memory
- browser media elements can request only the bytes they need for preview/playback where supported
- unauthorized users still receive the same contract-compliant rejection behavior

#### Tests
- download response test proving streaming iteration for MinIO-backed files
- range-request test for authorized media download if range support is implemented
- authorization regression tests for revoked room/dialog access
- large-object integration smoke test that avoids loading the full payload into process memory

#### Implementation Notes
- backend attachment downloads use `StreamingHttpResponse` and bounded chunk iteration
- image, video, and audio attachments return `Content-Disposition: inline`
- single-range passthrough is supported for object-storage-backed downloads, including open-ended and suffix ranges
- legacy filesystem fallback remains available during MinIO cutover without changing authorization behavior

---

## M7. Presence and Unread State

### T7.1 Implement presence domain logic
**Status:** DONE

#### Requirements
- MUST compute presence across tabs/sessions
- MUST support:
  - online
  - afk
  - offline
- MUST apply one-minute AFK rule exactly

#### Tests
- any-tab-active => online
- all-tabs-idle > 1 minute => afk
- no-tabs => offline

---

### T7.2 Implement presence query endpoint
**Status:** DONE

#### Endpoint
- `POST /api/v1/presence/query`

#### Requirements
- MUST return presence for requested users
- MUST align with computed user-level aggregate state

#### Tests
- query multiple users
- correct presence values returned

---

### T7.3 Implement notification summary endpoint
**Status:** DONE

#### Endpoint
- `GET /api/v1/notifications/summary`

#### Requirements
- MUST include room unread counts
- MUST include dialog unread counts
- MUST include incoming friend request count

#### Tests
- notification summary correctness

---

## M8. Moderation, Bans, Invitations, and Friendship Flows

### T8.1 Implement friend request APIs
**Status:** DONE

#### Endpoints
- `GET /api/v1/friends`
- `GET /api/v1/friend-requests/incoming`
- `GET /api/v1/friend-requests/outgoing`
- `POST /api/v1/friend-requests`
- `POST /api/v1/friend-requests/{request_id}/accept`
- `POST /api/v1/friend-requests/{request_id}/reject`
- `DELETE /api/v1/friends/{user_id}`

#### Requirements
- MUST support request by username
- MUST require acceptance for friendship
- MUST block duplicate/invalid transitions

#### Tests
- send request
- accept request
- reject request
- remove friend
- duplicate request rejection

---

### T8.2 Implement peer ban APIs and frozen dialog behavior
**Status:** DONE

#### Endpoints
- `GET /api/v1/user-bans`
- `POST /api/v1/user-bans`
- `DELETE /api/v1/user-bans/{user_id}`

#### Requirements
- peer ban MUST terminate friendship
- peer ban MUST block new personal messaging
- existing dialog MUST remain visible but frozen
- unban MUST not automatically restore friendship unless product explicitly does so elsewhere

#### Tests
- peer ban creation
- DM blocked after ban
- existing history remains readable
- friendship termination verified
- unban behavior verified

---

### T8.3 Implement room invitations
**Status:** DONE

#### Endpoints
- `POST /api/v1/rooms/{room_id}/invitations`
- `GET /api/v1/rooms/{room_id}/invitations`
- `POST /api/v1/room-invitations/{invitation_id}/accept`
- `POST /api/v1/room-invitations/{invitation_id}/reject`

#### Requirements
- admin/owner authorization
- private room invite flow must work
- invited user must be able to join private room through invitation accept flow

#### Tests
- create invitation
- accept invitation
- reject invitation
- unauthorized invite rejection

---

### T8.4 Implement room admin role management
**Status:** DONE

#### Endpoints
- `POST /api/v1/rooms/{room_id}/admins`
- `DELETE /api/v1/rooms/{room_id}/admins/{user_id}`

#### Requirements
- owner MUST be able to promote member to admin
- owner MUST be able to demote non-owner admin
- admin demotion behavior MUST align with API contract
- owner admin status MUST never be removable

#### Tests
- promote member
- demote admin
- owner demotion rejection
- unauthorized role change rejection

---

### T8.5 Implement room member removal, bans, and unbans
**Status:** DONE

#### Endpoints
- `POST /api/v1/rooms/{room_id}/remove-member`
- `POST /api/v1/rooms/{room_id}/bans`
- `GET /api/v1/rooms/{room_id}/bans`
- `DELETE /api/v1/rooms/{room_id}/bans/{user_id}`

#### Requirements
- removing a member MUST behave as a ban
- room ban metadata MUST include who performed the ban
- banned/removed users MUST lose message and file access immediately
- unban MUST restore eligibility to join, not automatic re-membership

#### Tests
- remove-member behaves as ban
- explicit room ban works
- banned user cannot rejoin
- unban restores join eligibility
- access revocation to history/files verified

---

## M9. WebSocket Real-Time Protocol

### T9.1 Implement authenticated WebSocket connection
**Status:** DONE

#### Endpoint
- `/ws/v1/chat`

#### Requirements
- MUST use authenticated session cookie
- MUST reject unauthenticated clients
- MUST use contract envelope format

#### Tests
- authenticated connect success
- unauthenticated connect rejection

---

### T9.2 Implement basic WebSocket protocol primitives
**Status:** DONE

#### Events
- `ping`
- `pong`
- `ack`
- `error`

#### Requirements
- MUST support request correlation with `request_id`
- MUST produce contract-compliant error payloads

#### Tests
- ping/pong
- ack behavior
- validation error payloads
- authorization error payloads

---

### T9.3 Implement room/dialog subscription events
**Status:** DONE

#### Events
- `room.subscribe`
- `room.unsubscribe`
- `dialog.subscribe`
- `dialog.unsubscribe`

#### Requirements
- only authorized users may subscribe
- subscription state must control live broadcast fanout

#### Tests
- authorized subscribe
- unauthorized subscribe rejection
- unsubscribe behavior

---

### T9.4 Implement WebSocket message send/edit/delete flows
**Status:** DONE

#### Events
- `room.message.send`
- `dialog.message.send`
- `room.message.edit`
- `room.message.delete`
- `dialog.message.edit`
- `dialog.message.delete`

#### Requirements
- MUST enforce same business rules as REST
- MUST persist before broadcast
- MUST emit created/updated/deleted events with contract payload shape

#### Tests
- room message live broadcast
- dialog message live broadcast
- authorization checks
- persisted-before-broadcast guarantee where testable

---

### T9.5 Implement WebSocket read-state events
**Status:** DONE

#### Events
- `room.read`
- `dialog.read`
- `room.read.updated`
- `dialog.read.updated`

#### Requirements
- MUST align with unread state model
- MUST update current user read state and broadcast relevant updates

#### Tests
- read event processing
- unread count reset propagation

---

### T9.6 Implement presence heartbeat and presence update events
**Status:** DONE

#### Events
- `presence.heartbeat`
- `presence.updated`

#### Requirements
- MUST support multi-tab heartbeat aggregation
- MUST publish presence changes promptly
- MUST align with user-level presence logic

#### Tests
- heartbeat updates state
- aggregate multi-tab behavior
- presence transitions broadcast

---

### T9.7 Implement friend request and invitation WebSocket notifications
**Status:** DONE

#### Events
- `friend_request.created`
- `room.invitation.created`
- `room.membership.updated`

#### Requirements
- MUST notify relevant recipients only
- MUST reflect persisted state

#### Tests
- incoming friend request notification
- incoming room invitation notification
- room membership update notification

---

## M10. UI Integration

### T10.1 Implement authentication UI
**Status:** IN PROGRESS

#### Requirements
- sign in
- registration
- password reset request
- session-aware auth state

#### Acceptance Criteria
- happy path auth works end-to-end against backend

---

### T10.2 Implement classic chat layout
**Status:** IN PROGRESS

#### Requirements
- top navigation
- room/contact sidebar
- central message pane
- bottom multiline input
- member/context panel

#### Acceptance Criteria
- UI matches classic web chat interaction model

---

### T10.3 Implement room and dialog lists
**Status:** IN PROGRESS

#### Requirements
- show rooms and contacts
- show unread indicators
- support public room search
- support private/public distinction

---

### T10.4 Implement message history and composition UI
**Status:** IN PROGRESS

#### Requirements
- infinite scroll
- multiline input
- reply flow
- edited indicator
- attachment support
- no forced autoscroll when user is reading older messages

---

### T10.5 Implement moderation and admin UI
**Status:** IN PROGRESS

#### Requirements
- manage room members
- manage admins
- manage bans
- invite users
- delete messages
- delete room
- use dialogs/modals where appropriate

---

### T10.6 Implement sessions UI
**Status:** IN PROGRESS

#### Requirements
- show active sessions
- revoke selected session
- support current-session semantics correctly

---

### T10.7 Harden inline attachment rendering for large media
**Status:** IN PROGRESS

#### Objective
Keep the chat UI usable when messages contain large images or videos by avoiding browser behavior that eagerly loads full media objects.

#### Requirements
- MUST keep attachment access on the existing authorized download path
- MUST define separate rendering behavior for images, videos, and non-previewable files
- MUST avoid automatically forcing full-media fetches when only a preview/poster/metadata view is needed
- MUST provide a safe fallback interaction for very large media, such as click-to-open or explicit load
- MUST remain compatible with the backend streaming strategy chosen in `T6.8`
- MUST preserve the existing attachment link/download behavior for files that are not previewed inline

#### Acceptance Criteria
- message history remains usable when large media attachments are present
- inline previews do not trigger avoidable full-media downloads during normal scrolling
- users still have an explicit path to open or download the original attachment

#### Tests
- vitest frontend rendering test for image attachments
- vitest frontend rendering test for video attachments with non-eager loading behavior
- manual browser validation notes for large-media preview and playback

#### Implementation Notes
- small images render inline with lazy image loading
- large images and videos require explicit user action before preview media is requested
- video previews use `preload=\"metadata\"` so the browser can inspect playable media without eagerly downloading the full object
- non-previewable files continue to use explicit download/open links only

---

## M11. Deployment Hardening

### T11.1 Align deployment with DEPLOYMENT.md
**Status:** DONE

#### Requirements
- implementation MUST match documented deployment steps
- docs MUST be updated if deployment requirements changed

#### Tests
- clean startup through documented compose workflow

---

### T11.2 Finalize environment configuration
**Status:** DONE

#### Requirements
- document required env vars
- provide safe defaults for local development where possible
- ensure production-sensitive settings are not hardcoded

---

### T11.3 Validate storage, static/media, and service wiring
**Status:** DONE

#### Requirements
- local filesystem attachment storage works
- media paths are guarded by application authorization
- postgres, redis, websocket stack all work together

#### Tests
- end-to-end smoke validation

---

### T11.4 Add MinIO to Docker Compose topology
**Status:** DONE

#### Objective
Extend local deployment so object storage runs as a first-class service.

#### Requirements
- MUST add a dedicated `minio` service to Docker Compose
- MinIO MUST run separately from `backend`, `postgres`, `redis`, and `frontend`
- MUST use a persistent Docker volume for MinIO data
- MUST document required MinIO environment variables and local defaults

#### Acceptance Criteria
- `docker compose up` starts MinIO successfully alongside the rest of the stack
- MinIO data persists across container recreation

#### Tests
- compose startup smoke test including MinIO health
- persistence smoke test across MinIO restart

---

### T11.5 Bootstrap the `uploads` bucket during deployment
**Status:** DONE

#### Objective
Ensure local deployment always provisions the required attachment bucket automatically.

#### Requirements
- deployment MUST create bucket `uploads` if it does not already exist
- bucket bootstrap MUST be safe to run repeatedly
- bootstrap MUST complete before backend attachment flows depend on the bucket
- bootstrap MAY use a dedicated one-shot init container or equivalent deterministic startup step

#### Acceptance Criteria
- a fresh local deployment results in an available `uploads` bucket without manual steps
- repeated deployments do not fail when the bucket already exists

#### Tests
- fresh-environment bucket creation smoke test
- idempotent re-run smoke test

---

### T11.6 Replace local media-root readiness checks with object-storage validation
**Status:** DONE

#### Objective
Align backend and deployment readiness with the MinIO-backed attachment design.

#### Requirements
- MUST stop treating local media directory existence as the primary attachment readiness signal
- readiness MUST verify MinIO connectivity and required bucket availability
- health output SHOULD clearly indicate object-storage status for debugging
- docs MUST be updated to remove outdated local-filesystem-only readiness assumptions

#### Acceptance Criteria
- backend readiness fails when MinIO is unavailable or bucket `uploads` is missing
- backend readiness succeeds when object storage is healthy

#### Tests
- readiness failure test when MinIO is unreachable
- readiness success test when MinIO and `uploads` are available

---

## M12. Migrate to Redis-backed realtime architecture

### T12.0 Baseline, flags, and observability
**Status:** IN PROGRESS

#### Objective
Establish the migration guardrails defined in `docs/MIGRATION_TASKS.md` Milestone 0 before changing live behavior.

#### Current State
- migration feature flags exist in backend settings
- `docs/MIGRATION_PLAN.md` exists
- `apps/chat/realtime/` exists and is already used by the current websocket path
- required migration package, rollback docs, milestone docs, and observability work are not yet complete

---

### T12.1 Canonical event contract
**Status:** TODO

#### Objective
Add the canonical internal event contract from `docs/MIGRATION_TASKS.md` Milestone 1.

#### Current State
- contract-style websocket payloads exist for live clients
- `apps/chat/events/`, `docs/EVENT_CONTRACT.md`, and migration-specific contract tests do not yet exist

---

### T12.2 Redis presence and connection registry
**Status:** TODO

#### Objective
Move presence, typing, and connection routing to Redis-backed abstractions per `docs/MIGRATION_TASKS.md` Milestone 2.

#### Current State
- presence is implemented and tested
- current presence storage is SQL-backed through `apps.presence.models.UserPresenceConnection`
- Redis presence abstractions, key documentation, and parity checks are not yet implemented

---

### T12.3 Redis-backed live fanout
**Status:** IN PROGRESS

#### Objective
Move live room and user fanout onto Redis-backed Channels groups per `docs/MIGRATION_TASKS.md` Milestone 3.

#### Current State
- `apps/chat/realtime/fanout.py`, `groups.py`, `routing.py`, and websocket tests already exist
- stable room, dialog, user, and presence group naming is implemented
- migration-specific flag-driven cutover, rollback verification, and parity checks are not yet complete

---

### T12.4 Stream publishing in shadow mode
**Status:** TODO

#### Objective
Publish canonical chat events to Redis Streams in additive shadow mode per `docs/MIGRATION_TASKS.md` Milestone 4.

#### Current State
- stream publishing feature flags exist
- no `apps/chat/events/publishers.py`, `stream_names.py`, or stream publish integration tests exist yet

---

### T12.5 Persistence workers and dual-write parity
**Status:** TODO

#### Objective
Introduce Redis Stream consumers that persist to PostgreSQL with idempotency and parity checks per `docs/MIGRATION_TASKS.md` Milestone 5.

#### Current State
- worker package and persistence worker implementation are not present
- parity and reconciliation tooling for durable writes is not present

---

### T12.6 Async persistence cutover
**Status:** TODO

#### Objective
Remove synchronous PostgreSQL persistence from the live send critical path per `docs/MIGRATION_TASKS.md` Milestone 6.

#### Current State
- current room and dialog message creation still persists in the request/consumer path before broadcast
- accepted versus stored state transitions are not modeled yet

---

### T12.7 Derived-write removal from hot path
**Status:** TODO

#### Objective
Move unread updates and other derived writes off the send hot path per `docs/MIGRATION_TASKS.md` Milestone 7.

#### Current State
- unread and summary behavior exists in the synchronous application path
- projection workers and rebuild tooling do not yet exist

---

### T12.8 Reconciliation hardening and backfill tooling
**Status:** TODO

#### Objective
Add rebuild, repair, backfill, and runbook tooling per `docs/MIGRATION_TASKS.md` Milestone 8.

#### Current State
- migration runbooks and operational tooling are not yet present

---

### T12.9 Legacy path retirement
**Status:** TODO

#### Objective
Retire legacy PostgreSQL-hot-path realtime behavior only after the migrated architecture is proven per `docs/MIGRATION_TASKS.md` Milestone 9.

#### Current State
- not started; preconditions from earlier migration milestones are not met

## M13. Cross-Cutting Verification

### T13.1 Add contract compliance tests
**Status:** IN PROGRESS

#### Objective
Ensure API behavior matches `API_CONTRACT.md`.

#### Coverage
- endpoint paths
- field names
- status codes
- enum values
- error model
- authorization semantics

---

### T13.2 Add permission matrix tests
**Status:** IN PROGRESS

#### Objective
Verify the authorization matrix from `API_CONTRACT.md`.

#### Coverage
- room member/admin/owner permissions
- non-member restrictions
- dialog participant restrictions
- peer-ban effects
- room-ban effects

---

### T13.3 Add deletion and access-revocation tests
**Status:** TODO

#### Objective
Verify the highest-risk data and access flows.

#### Coverage
- room deletion cascades
- account deletion cascades
- room access loss revokes message access
- room access loss revokes attachment access
- peer ban freezes dialog send capability

---

### T13.4 Add performance-sane query/path checks
**Status:** TODO

#### Objective
Catch obvious scalability mistakes early.

#### Coverage
- paginated history
- paginated lists
- no full-history load on standard reads
- avoidance of obvious N+1 hot-path patterns where testable

---

## M14. Optional Advanced Scope

This milestone MUST NOT begin until all required milestones above are complete and stable.

### T14.1 Add XMPP/Jabber integration plan
**Status:** TODO

#### Requirements
- MUST define achievable support level
- MUST keep core application behavior intact
- MUST isolate integration concerns from core chat flows

---

### T14.2 Implement XMPP client connectivity
**Status:** TODO

#### Requirements
- users SHOULD be able to connect via Jabber client
- implementation MUST use a library appropriate for the stack

---

### T14.3 Implement federation between two servers
**Status:** TODO

#### Requirements
- MUST support cross-server messaging if this scope is implemented
- MUST include docker-compose support for multi-server topology

---

### T14.4 Implement Jabber/federation admin UI
**Status:** TODO

#### Requirements
- connection dashboard for admin
- federation traffic information/statistics

---

### T14.5 Add federation load test scenario
**Status:** TODO

#### Requirements
- 50+ clients on server A
- 50+ clients on server B
- messaging from A to B and back

---

## 6. Execution Dependencies

The following dependencies MUST be respected:

- T1.1 before all backend implementation tasks
- T1.2 before integrated local verification tasks
- T2.1 before T2.2
- T2.2 before T2.3
- T2.3 before most API implementation tasks that require persistence
- T3.x before any authenticated feature acceptance
- T4.x before T5.x for room/dialog message behavior
- T5.x before T9.4
- T6.x before attachment binding in message flows is complete
- T7.1 before T7.2 and T9.6
- T8.2 before frozen-dialog behavior can be considered complete
- T8.5 before room access revocation is complete
- T9.1 before all other websocket tasks
- T10.x after corresponding backend/API tasks exist
- T11.x after core integration is functional
- T12.x throughout implementation, but final verification MUST happen before project completion
- T13.x only after M1–M12 are complete

---

## 7. Minimum Release Criteria

The project MUST NOT be considered ready for initial release until all of the following are complete:

- M1 through M12 are DONE
- `docker compose up` works from repository root
- required REST endpoints are implemented
- required WebSocket events are implemented
- authorization matrix is enforced
- room removal/ban access revocation works
- peer ban frozen-dialog behavior works
- attachment access control works
- tests cover critical product flows
- documentation is aligned with implementation

---

## 8. Suggested Implementation Order Within Core Scope

The recommended core implementation order is:

1. T1.1
2. T1.2
3. T1.3
4. T2.1
5. T2.2
6. T2.3
7. T3.1
8. T3.2
9. T3.3
10. T3.4
11. T3.6
12. T4.2
13. T4.3
14. T4.5
15. T4.6
16. T8.1
17. T8.2
18. T4.7
19. T5.1
20. T5.2
21. T5.3
22. T5.4
23. T5.5
24. T6.1
25. T6.2
26. T6.3
27. T6.4
28. T7.1
29. T7.2
30. T7.3
31. T8.3
32. T8.4
33. T8.5
34. T9.1
35. T9.2
36. T9.3
37. T9.4
38. T9.5
39. T9.6
40. T9.7
41. T10.1
42. T10.2
43. T10.3
44. T10.4
45. T10.5
46. T10.6
47. T11.1
48. T11.2
49. T11.3
50. T12.1
51. T12.2
52. T12.3
53. T12.4

---

## 9. Final Rule

When choosing between speed and correctness, implementers MUST choose correctness.

When choosing between broad scope and contract fidelity, implementers MUST choose contract fidelity.

When choosing between cleverness and maintainability, implementers MUST choose maintainability.

This task plan exists to ensure the repository reaches a secure, testable, deployable, and spec-compliant implementation.

---
