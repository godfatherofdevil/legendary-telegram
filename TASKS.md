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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

#### Endpoint
- `DELETE /api/v1/attachments/{attachment_id}`

#### Requirements
- SHOULD allow deletion only before message binding
- MUST preserve contract semantics for bound attachments

#### Tests
- unbound delete success
- bound delete rejection if implemented as restricted

---

## M7. Presence and Unread State

### T7.1 Implement presence domain logic
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

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
**Status:** TODO

#### Requirements
- sign in
- registration
- password reset request
- session-aware auth state

#### Acceptance Criteria
- happy path auth works end-to-end against backend

---

### T10.2 Implement classic chat layout
**Status:** TODO

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
**Status:** TODO

#### Requirements
- show rooms and contacts
- show unread indicators
- support public room search
- support private/public distinction

---

### T10.4 Implement message history and composition UI
**Status:** TODO

#### Requirements
- infinite scroll
- multiline input
- reply flow
- edited indicator
- attachment support
- no forced autoscroll when user is reading older messages

---

### T10.5 Implement moderation and admin UI
**Status:** TODO

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
**Status:** TODO

#### Requirements
- show active sessions
- revoke selected session
- support current-session semantics correctly

---

## M11. Deployment Hardening

### T11.1 Align deployment with DEPLOYMENT.md
**Status:** TODO

#### Requirements
- implementation MUST match documented deployment steps
- docs MUST be updated if deployment requirements changed

#### Tests
- clean startup through documented compose workflow

---

### T11.2 Finalize environment configuration
**Status:** TODO

#### Requirements
- document required env vars
- provide safe defaults for local development where possible
- ensure production-sensitive settings are not hardcoded

---

### T11.3 Validate storage, static/media, and service wiring
**Status:** TODO

#### Requirements
- local filesystem attachment storage works
- media paths are guarded by application authorization
- postgres, redis, websocket stack all work together

#### Tests
- end-to-end smoke validation

---

## M12. Cross-Cutting Verification

### T12.1 Add contract compliance tests
**Status:** TODO

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

### T12.2 Add permission matrix tests
**Status:** TODO

#### Objective
Verify the authorization matrix from `API_CONTRACT.md`.

#### Coverage
- room member/admin/owner permissions
- non-member restrictions
- dialog participant restrictions
- peer-ban effects
- room-ban effects

---

### T12.3 Add deletion and access-revocation tests
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

### T12.4 Add performance-sane query/path checks
**Status:** TODO

#### Objective
Catch obvious scalability mistakes early.

#### Coverage
- paginated history
- paginated lists
- no full-history load on standard reads
- avoidance of obvious N+1 hot-path patterns where testable

---

## M13. Optional Advanced Scope

This milestone MUST NOT begin until all required milestones above are complete and stable.

### T13.1 Add XMPP/Jabber integration plan
**Status:** TODO

#### Requirements
- MUST define achievable support level
- MUST keep core application behavior intact
- MUST isolate integration concerns from core chat flows

---

### T13.2 Implement XMPP client connectivity
**Status:** TODO

#### Requirements
- users SHOULD be able to connect via Jabber client
- implementation MUST use a library appropriate for the stack

---

### T13.3 Implement federation between two servers
**Status:** TODO

#### Requirements
- MUST support cross-server messaging if this scope is implemented
- MUST include docker-compose support for multi-server topology

---

### T13.4 Implement Jabber/federation admin UI
**Status:** TODO

#### Requirements
- connection dashboard for admin
- federation traffic information/statistics

---

### T13.5 Add federation load test scenario
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

