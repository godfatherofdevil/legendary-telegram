# MIGRATION_TASKS.md

## 1. Purpose

This document defines the required implementation milestones for migrating the chat service from a PostgreSQL-hot-path architecture to a Redis-backed realtime architecture while preserving PostgreSQL as the durable system of record.

This document is normative. Terms such as MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as strict implementation requirements.

This milestone plan assumes:

- the chat application already exists in production
- the current implementation relies heavily on PostgreSQL for live message delivery and/or internal coordination
- the migration MUST occur incrementally inside the existing repository
- the migration MUST preserve rollback capability at every stage

---

## 2. Global execution rules

The implementation team MUST follow all of the rules below for every milestone.

### 2.1 Safety rules

1. No milestone MAY require a big-bang cutover.
2. Every milestone MUST have explicit rollback criteria.
3. Every milestone MUST have explicit acceptance criteria.
4. No destructive removal of legacy behavior MAY occur before parity is proven.
5. Migration code MUST be isolated from permanent business logic wherever practical.
6. The production chat service MUST remain operational throughout the migration.

### 2.2 Repository rules

The repository MUST introduce explicit structure for:

- realtime logic
- event contracts
- worker consumers
- migration-only glue
- parity checks
- reconciliation jobs

At minimum, the codebase SHOULD evolve toward a structure similar to:

```text
apps/chat/
  domain/
  realtime/
  events/
  projections/
  migration/
  infrastructure/

apps/workers/
docs/
tests/
````

### 2.3 Feature-flag rules

The following feature flags MUST exist before any production cutover milestone:

* `redis_presence_enabled`
* `redis_fanout_enabled`
* `redis_stream_publish_enabled`
* `async_persistence_enabled`

Optional but recommended flags:

* `legacy_sql_presence_enabled`
* `legacy_sql_fanout_enabled`
* `stream_fallback_to_sync_sql_enabled`
* `parity_verification_enabled`

### 2.4 Operational rules

Before cutover to any new path, the system MUST expose metrics for:

* WebSocket send latency
* fanout latency
* PostgreSQL queries per send
* PostgreSQL latency per send
* Redis stream lag
* worker processing rate
* duplicate message rate
* missing message rate
* reconnect gap-fill rate

### 2.5 Design rules

The migration MUST preserve these architectural outcomes:

* PostgreSQL remains the durable source of truth
* Redis becomes the primary live coordination layer
* live delivery MUST NOT depend on synchronous PostgreSQL commit in the final state
* presence and typing MUST NOT remain PostgreSQL-first in the final state

---

## 3. Milestone overview

The migration MUST be executed in the following order unless a more conservative sub-splitting is required:

* Milestone 0 — Baseline, flags, and observability
* Milestone 1 — Canonical event contract
* Milestone 2 — Redis presence and connection registry
* Milestone 3 — Redis-backed live fanout
* Milestone 4 — Stream publishing in shadow mode
* Milestone 5 — Persistence workers and dual-write parity
* Milestone 6 — Async persistence cutover
* Milestone 7 — Derived-write removal from hot path
* Milestone 8 — Reconciliation hardening and backfill tooling
* Milestone 9 — Legacy path retirement

No milestone MAY be considered complete until all acceptance criteria for that milestone have been met.

---

## 4. Milestone 0 — Baseline, flags, and observability

## 4.1 Objective

The system MUST establish operational guardrails before changing behavior.

## 4.2 Required scope

This milestone MUST add:

* feature flags for all planned migration toggles
* tracing or structured logging for the send-message path
* metrics for PostgreSQL load caused by chat traffic
* metrics for WebSocket latency and fanout timing
* an explicit migration package in the repository
* migration documentation scaffolding

## 4.3 Required repository changes

At minimum, the repo MUST add or prepare:

```text
apps/chat/migration/
docs/MIGRATION_PLAN.md
docs/ROLLBACK.md
docs/MILESTONES.md
tests/load/
tests/integration/
```

## 4.4 Required implementation tasks

The team MUST:

1. identify the current send-message call chain
2. measure PostgreSQL queries triggered by one sent message
3. measure PostgreSQL queries triggered by presence/typing/session-list loads
4. add feature flags with safe defaults disabled
5. add dashboards or equivalent visibility for the metrics listed above
6. document the current architecture pain points in migration notes

## 4.5 Forbidden changes

This milestone MUST NOT:

* change live delivery semantics
* change persistence semantics
* remove any existing behavior
* move any hot-path logic yet

## 4.6 Exit criteria

This milestone is complete only when:

* every required migration flag exists
* current PostgreSQL hot spots are measurable
* current fanout latency is measurable
* rollback documentation exists
* a migration package exists in the repo

## 4.7 Rollback

Rollback MUST be trivial because behavior change is not yet introduced.

---

## 5. Milestone 1 — Canonical event contract

## 5.1 Objective

The system MUST define one canonical internal chat event format before introducing Redis-driven fanout or asynchronous persistence.

## 5.2 Required scope

This milestone MUST add:

* canonical event envelope schema
* schema versioning
* event publisher abstraction
* stream and topic naming conventions
* contract tests

## 5.3 Required repository changes

The repo MUST add:

```text
apps/chat/events/
  envelopes.py
  schemas.py
  publishers.py
  stream_names.py

docs/EVENT_CONTRACT.md
tests/contract/
```

## 5.4 Required implementation tasks

The team MUST define at least the following canonical events:

* `message.created`
* `message.stored`
* `message.delivery_updated` or equivalent if needed
* `message.read_updated` or equivalent if needed

The minimum `message.created` envelope MUST include:

* `event_type`
* `schema_version`
* `message_id`
* `client_msg_id` or `null`
* `conversation_id`
* `sender_id`
* `body`
* `attachments`
* `created_at`

## 5.5 Required tests

The repo MUST include tests that verify:

* event schema serialization
* required field presence
* schema version presence
* invalid envelope rejection
* stable publisher behavior

## 5.6 Forbidden changes

This milestone MUST NOT:

* change the production hot path yet
* make Redis the authoritative transport yet
* remove legacy payload builders before parity support exists

## 5.7 Exit criteria

This milestone is complete only when:

* a canonical event contract exists
* event contract tests pass
* internal publishers can emit the canonical event format
* event naming and stream naming are documented

## 5.8 Rollback

The publisher abstraction MAY remain unused in production until later milestones. No live rollback complexity is introduced yet.

---

## 6. Milestone 2 — Redis presence and connection registry

## 6.1 Objective

The system MUST move presence, typing, and active connection routing out of PostgreSQL first.

## 6.2 Required scope

This milestone MUST introduce Redis-backed handling for:

* user presence
* connection tracking
* typing indicators
* optional room membership cache
* TTL-based heartbeat expiration

## 6.3 Required repository changes

The repo MUST add or evolve:

```text
apps/chat/realtime/
  presence.py
  connection_registry.py
  typing.py
  groups.py

apps/chat/infrastructure/redis/
  keys.py
  client.py

apps/chat/migration/
  parity_checks.py

docs/REDIS_KEYS.md
tests/integration/test_presence.py
```

## 6.4 Required implementation tasks

The team MUST implement:

1. a Redis key convention for presence and typing
2. TTL-backed heartbeats
3. connection registration on connect
4. connection cleanup on disconnect
5. parity checks comparing Redis state to any legacy SQL state if legacy SQL presence still exists

## 6.5 Compatibility rules

During migration:

* legacy SQL presence MAY remain enabled temporarily for verification
* new application code MUST target the Redis presence abstraction only
* direct writes to SQL presence tables SHOULD begin deprecation in this milestone

## 6.6 Forbidden changes

This milestone MUST NOT:

* make PostgreSQL the fallback-first presence store going forward
* add new presence or typing features on top of SQL tables
* hard-delete legacy presence code before parity data is gathered

## 6.7 Exit criteria

This milestone is complete only when:

* presence is written and read through Redis abstractions
* typing is written and read through Redis abstractions
* connection routing exists outside PostgreSQL
* parity metrics exist if legacy SQL presence remains
* TTL expiry behavior is verified in tests

## 6.8 Rollback

Rollback MUST be possible by disabling `redis_presence_enabled` and restoring legacy presence behavior if needed.

---

## 7. Milestone 3 — Redis-backed live fanout

## 7.1 Objective

The system MUST move live room and user fanout off PostgreSQL-centric coordination and onto Redis-backed Channels groups.

## 7.2 Required scope

This milestone MUST add:

* room group naming
* user group naming
* WebSocket consumer integration with group fanout
* live-delivery abstraction independent from direct SQL polling or rereads
* delivery-path integration tests

## 7.3 Required repository changes

The repo MUST add or evolve:

```text
apps/chat/realtime/
  fanout.py
  groups.py
  routing.py
  serializers.py

config/routing.py

tests/integration/test_realtime_fanout.py
tests/e2e/test_websocket_delivery.py
```

## 7.4 Required implementation tasks

The team MUST implement:

1. `conv.{conversation_id}` or equivalent room-group naming
2. `user.{user_id}` or equivalent user-group naming
3. WebSocket connect/disconnect group membership management
4. live message publish path to Redis-backed groups
5. parity verification between legacy and new fanout where feasible

## 7.5 Compatibility rules

During the migration window:

* Redis fanout MAY run in shadow mode first
* sampled or internal traffic MAY be used to verify delivery parity
* legacy fanout MUST remain available until Redis fanout is proven

## 7.6 Forbidden changes

This milestone MUST NOT:

* remove history reads from PostgreSQL
* remove legacy fanout before verification
* couple live delivery to worker-based PostgreSQL persistence yet

## 7.7 Exit criteria

This milestone is complete only when:

* live delivery can occur through Redis-backed groups
* delivery integration tests pass
* user and room fanout naming conventions are stable
* rollback switch behavior is tested

## 7.8 Rollback

Rollback MUST be possible by disabling `redis_fanout_enabled` and routing live delivery back to the legacy mechanism.

---

## 8. Milestone 4 — Stream publishing in shadow mode

## 8.1 Objective

The system MUST begin publishing canonical events to Redis Streams without yet making Streams the authoritative persistence path.

## 8.2 Required scope

This milestone MUST add:

* stream publisher implementation
* stream naming constants
* shadow-mode publishing from the live send path
* stream lag metrics
* event-publish failure visibility

## 8.3 Required repository changes

The repo MUST add or evolve:

```text
apps/chat/events/
  publishers.py
  stream_names.py

apps/chat/migration/
  shadow_mode.py

tests/integration/test_stream_publish.py
```

## 8.4 Required implementation tasks

The team MUST implement:

1. append of canonical `message.created` events to `stream:chat_events` or equivalent
2. publishing behind `redis_stream_publish_enabled`
3. structured error reporting on stream append failures
4. dashboards or alerts for stream append rate and failure rate

## 8.5 Behavioral rules

During this milestone:

* the legacy persistence path MUST remain authoritative
* stream publishing MUST be additive only
* stream publish failure MUST NOT silently corrupt send-path observability

## 8.6 Forbidden changes

This milestone MUST NOT:

* remove synchronous PostgreSQL persistence
* make Streams authoritative for durability yet
* acknowledge message storage based solely on successful stream append

## 8.7 Exit criteria

This milestone is complete only when:

* canonical chat events are published to Redis Streams in production shadow mode
* stream append success/failure is measurable
* stream lag is measurable
* no durable ownership changes have been made yet

## 8.8 Rollback

Rollback MUST be possible by disabling `redis_stream_publish_enabled`.

---

## 9. Milestone 5 — Persistence workers and dual-write parity

## 9.1 Objective

The system MUST introduce persistence workers that consume stream events and write to PostgreSQL, while the legacy synchronous path still remains authoritative or co-authoritative during a parity window.

## 9.2 Required scope

This milestone MUST add:

* persistence worker process
* consumer-group setup
* idempotent durable write logic
* parity comparison logic
* duplicate and missing event detection

## 9.3 Required repository changes

The repo MUST add or evolve:

```text
apps/workers/
  persistence_worker.py

apps/chat/migration/
  parity_checks.py
  reconciliation.py
  backfill.py

tests/integration/test_persistence_worker.py
tests/contract/test_persistence_idempotency.py
```

## 9.4 Required implementation tasks

The team MUST implement:

1. Redis Stream consumer group creation for persistence workers
2. idempotent durable write handling keyed by `message_id`
3. durable write retry safety
4. `XACK` only after successful PostgreSQL commit
5. parity comparison between:

    * legacy sync writes
    * worker-produced writes or verification outputs

## 9.5 Data rules

The PostgreSQL message schema MUST support:

* unique `message_id`
* optional `client_msg_id`
* safe retry behavior
* storage timestamps

## 9.6 Compatibility modes

One of the following MUST be used:

### Mode A — Verification mode

* worker performs all transforms and validations but does not become authoritative

### Mode B — Dual-write mode

* legacy path writes synchronously
* worker also writes or verifies equivalent outcomes
* parity checks compare results continuously

The implementation team MUST choose one explicitly and document it.

## 9.7 Required parity checks

The system MUST compare:

* accepted vs stored counts
* duplicate message count
* missing message count
* per-conversation ordering consistency
* attachment persistence parity if attachments are in scope

## 9.8 Forbidden changes

This milestone MUST NOT:

* remove synchronous PostgreSQL hot-path write yet
* remove parity tooling
* skip idempotency protections

## 9.9 Exit criteria

This milestone is complete only when:

* persistence workers run reliably
* stream consumer lag is measurable
* worker writes are idempotent
* parity checks are passing for the required migration window
* duplicate and missing message alerts exist

## 9.10 Rollback

Rollback MUST be possible by:

* disabling worker authority
* stopping worker consumption if needed
* continuing with legacy synchronous PostgreSQL persistence

---

## 10. Milestone 6 — Async persistence cutover

## 10.1 Objective

The system MUST remove synchronous PostgreSQL persistence from the live send critical path and make stream-driven worker persistence authoritative for durable storage.

## 10.2 Required scope

This milestone MUST change send semantics so that:

* the gateway accepts and publishes live delivery
* the gateway appends to Redis Stream
* persistence workers perform the durable PostgreSQL write
* sender state transitions distinguish `accepted` from `stored`

## 10.3 Required repository changes

The repo MUST update:

```text
apps/chat/realtime/
  consumers/
  fanout.py

apps/chat/events/
  publishers.py

apps/workers/
  persistence_worker.py

tests/e2e/test_async_persistence_flow.py
tests/integration/test_message_state_transitions.py
```

## 10.4 Required implementation tasks

The team MUST implement:

1. authoritative stream append on send
2. authoritative worker-based durable write
3. sender acknowledgement semantics for:

    * accepted
    * stored
4. explicit operational backpressure if stream lag or PostgreSQL lag grows beyond threshold

## 10.5 Optional temporary fallback

During the cutover window only:

* a guarded fallback synchronous SQL write MAY exist if stream append fails
* this fallback MUST be behind `stream_fallback_to_sync_sql_enabled`
* this fallback MUST be documented as temporary and removable

## 10.6 Forbidden changes

This milestone MUST NOT:

* claim a message is durably stored before PostgreSQL commit succeeds
* acknowledge stream entries before durable write succeeds
* silently fall back without metrics and logging

## 10.7 Exit criteria

This milestone is complete only when:

* synchronous PostgreSQL write is no longer required for live send success
* worker-based durable storage is authoritative
* message state transitions are explicit and tested
* fallback behavior is controlled and observable if still enabled

## 10.8 Rollback

Rollback MUST be possible by:

* disabling `async_persistence_enabled`
* restoring the legacy sync write path
* optionally keeping stream publish enabled in shadow mode

---

## 11. Milestone 7 — Derived-write removal from hot path

## 11.1 Objective

The system MUST remove derived side effects from the live send path and move them to asynchronous consumers.

## 11.2 Required scope

Derived side effects include, at minimum where applicable:

* unread count updates
* session summary updates
* push notification generation
* analytics emission
* moderation side effects
* indexing side effects

## 11.3 Required repository changes

The repo MUST add or evolve:

```text
apps/chat/projections/
  unread_counts.py
  session_summary.py
  recent_tail.py

apps/workers/
  projection_worker.py
  notification_worker.py
  moderation_worker.py

tests/integration/test_projection_updates.py
```

## 11.4 Required implementation tasks

The team MUST implement:

1. projection workers or equivalent consumers
2. idempotent projection updates
3. reconciliation jobs for drifted projections
4. metrics for projection lag and failures

## 11.5 Behavioral rules

The send hot path MUST stop performing synchronous:

* unread fanout updates
* session summary recalculations
* downstream side-effect writes unrelated to core acceptance/publish/stream append

## 11.6 Forbidden changes

This milestone MUST NOT:

* move durable history ownership out of PostgreSQL
* hide projection failures
* create projections that cannot be rebuilt from PostgreSQL truth

## 11.7 Exit criteria

This milestone is complete only when:

* derived writes are no longer blocking live sends
* projection rebuild tooling exists
* projection lag is measurable
* drift reconciliation exists

## 11.8 Rollback

Rollback MUST be possible per projection family or worker family through targeted flags or routing controls.

---

## 12. Milestone 8 — Reconciliation hardening and backfill tooling

## 12.1 Objective

The system MUST harden operational recovery before legacy path retirement.

## 12.2 Required scope

This milestone MUST add:

* backfill jobs
* cache rebuild jobs
* projection repair jobs
* missing-message replay or repair tools
* operational runbooks

## 12.3 Required repository changes

The repo MUST add or evolve:

```text
apps/chat/migration/
  reconciliation.py
  backfill.py
  cutover.py

scripts/
  run_migration_parity.sh
  backfill_presence_cache.sh
  rebuild_projections.sh

docs/OPERATIONS.md
docs/ROLLBACK.md
```

## 12.4 Required implementation tasks

The team MUST implement:

1. Redis cache rebuild from PostgreSQL truth
2. projection rebuild from PostgreSQL truth
3. missing message detection and repair tooling
4. backfill tooling for any newly materialized state required by the architecture
5. on-call instructions for stream lag, worker failure, and cutover rollback

## 12.5 Exit criteria

This milestone is complete only when:

* reconciliation tooling exists and has been exercised
* backfill tooling exists and has been exercised
* operational runbooks exist
* on-call response paths are documented

## 12.6 Rollback

Rollback is operational rather than architectural in this milestone; tools created here MUST support rollback and recovery in later milestones.

---

## 13. Milestone 9 — Legacy path retirement

## 13.1 Objective

The system MUST remove obsolete PostgreSQL-hot-path logic only after the new architecture is stable and proven.

## 13.2 Preconditions

This milestone MUST NOT begin until all of the following are true:

* async persistence is authoritative
* parity has remained stable for the required migration window
* reconciliation jobs are proven
* rollback has been tested
* production metrics demonstrate acceptable lag and error rates

## 13.3 Required scope

This milestone MUST remove or retire:

* SQL presence heartbeats
* SQL typing writes
* legacy DB-centric fanout
* polling-based live delivery logic
* synchronous derived writes in send path
* no-longer-needed dual-write glue

## 13.4 Required repository changes

The repo MUST:

* delete obsolete migration code that is no longer needed
* keep only the migration code still necessary for rollback or recovery
* simplify permanent service boundaries
* update architecture and operations docs to reflect the final state

## 13.5 Documentation updates

The team MUST update:

* `ARCHITECTURE.md`
* `OPERATIONS.md`
* `ROLLBACK.md`
* deployment docs
* developer onboarding docs for chat architecture

## 13.6 Forbidden changes

This milestone MUST NOT:

* remove recovery tooling
* remove observability that remains operationally necessary
* remove rollback controls before they are intentionally retired by decision

## 13.7 Exit criteria

This milestone is complete only when:

* legacy PostgreSQL-hot-path logic is removed
* new architecture is the only production path for realtime chat
* documentation reflects the final state
* recovery and observability remain intact

## 13.8 Rollback

If rollback to legacy architecture is no longer intended after this milestone, that decision MUST be explicit, documented, and approved. Rollback retirement MUST NOT happen accidentally.

---

## 14. Cross-milestone acceptance rules

The migration as a whole MUST NOT be considered complete until all of the following are true:

1. live delivery no longer requires synchronous PostgreSQL commit
2. presence and typing no longer depend on PostgreSQL-first storage
3. fanout no longer depends on PostgreSQL polling or equivalent DB-centric coordination
4. worker-based persistence is authoritative
5. derived writes are no longer blocking the send hot path
6. reconciliation tooling exists and is proven
7. rollback procedures have been tested during at least one real cutover phase
8. production observability covers Redis, workers, and PostgreSQL sufficiently

---

## 15. Recommended execution notes

### 15.1 Preferred implementation order

The team SHOULD execute work in the following order inside each milestone:

1. contract
2. abstractions
3. feature flags
4. metrics
5. dark launch
6. parity checks
7. cutover
8. cleanup

### 15.2 Preferred repository priority

The team SHOULD prioritize adding these packages early:

```text
apps/chat/events/
apps/chat/realtime/
apps/chat/migration/
apps/workers/
docs/
tests/contract/
tests/integration/
```

### 15.3 Preferred deletion policy

Migration glue MUST be explicit and temporary.
Permanent code MUST NOT depend indefinitely on migration-only helpers once the migration is complete.

---

## 16. Definition of done

The milestone program is complete only when:

* `MIGRATION_PLAN.md` matches the deployed production architecture
* `MIGRATION_TASKS.md` has all milestones marked achieved internally
* legacy PostgreSQL-hot-path behavior has been removed or intentionally retained only where justified
* Redis-backed realtime coordination is standard production behavior
* PostgreSQL remains the durable source of truth
* the team can operate the system confidently using documented metrics, alerts, and recovery tools

---

```
