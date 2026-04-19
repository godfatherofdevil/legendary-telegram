# MIGRATION_PLAN.md

## 1. Purpose

This document defines the target architecture and migration rules for moving the chat service off a PostgreSQL-hot-path design to a Redis-backed realtime architecture with PostgreSQL retained as the durable system of record. PostgreSQL explicitly limits concurrent connections through `max_connections`, which is typically 100 by default, so it MUST NOT be used as the primary internal coordination bus for live chat traffic. :contentReference[oaicite:0]{index=0}

Current Architecture Document lives in [ARCHITECTURE.md](ARCHITECTURE.md).

This document is normative. Terms such as MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as strict implementation requirements.

---

## 2. Scope

This architecture applies to:

- WebSocket message send and receive flows
- Internal fanout and inter-process communication
- Presence, typing, and other ephemeral chat state
- Durable message persistence
- Migration from the legacy PostgreSQL-centric design
- Reconnect and history-read behavior
- Worker-based derived projections

This architecture does not replace PostgreSQL as the durable chat datastore. PostgreSQL remains the authoritative storage engine for persisted messages, sessions, attachments metadata, and other durable business data.

---

## 3. Architecture goals

The system MUST satisfy all of the following:

1. Live message delivery MUST NOT depend on a synchronous PostgreSQL write.
2. Internal service-to-service chat coordination MUST NOT use PostgreSQL as the primary message bus.
3. Presence, typing, connection routing, and similar ephemeral state MUST NOT be stored primarily in PostgreSQL.
4. Persisted message history MUST remain durably stored in PostgreSQL.
5. The migration MUST be incremental, reversible, and safe to roll back.
6. The system MUST support horizontal scaling of WebSocket servers and worker processes.

Channels’ production channel layer is Redis-backed via `channels_redis`, and Channels documents that ASGI server processes can be scaled horizontally. :contentReference[oaicite:1]{index=1}

---

## 4. Non-goals

The migration MUST NOT assume or require:

- a full application rewrite
- a big-bang cutover
- replacing PostgreSQL with Redis for durable message history
- exactly-once delivery across all system boundaries
- permanent storage of transient state in Redis

---

## 5. Current-state problem statement

The legacy system currently uses PostgreSQL as the hot path for most or all of the following:

- synchronous message writes before delivery
- room membership reads during send
- presence writes
- typing writes
- session summary updates
- unread counter updates
- polling or notification-driven delivery coordination

This design MUST be treated as the architecture to replace because PostgreSQL connection count and process/resource usage are bounded, and scaling chat fanout through database round-trips does not fit those constraints. PostgreSQL documents both the connection limit and the kernel/resource impact associated with allowed connections and background processes. :contentReference[oaicite:2]{index=2}

---

## 6. Target end-state architecture

```text
Clients
  -> HTTPS / WebSocket
    -> ASGI Gateway (Django + Channels)
      -> Redis Channel Layer (live fanout)
      -> Redis Cache / Presence / Connection Map (ephemeral state)
      -> Redis Streams (internal event log)
        -> Persistence Workers
        -> Notification Workers
        -> Projection / Index / Moderation Workers
          -> PgBouncer / pooler
            -> PostgreSQL
````

### 6.1 Component responsibilities

#### ASGI Gateway

The ASGI gateway MUST:

* authenticate requests and WebSocket connections
* validate message payloads
* generate or validate message identifiers
* publish live events to Redis-backed channel groups
* append canonical events to Redis Streams
* avoid blocking live delivery on synchronous PostgreSQL writes

Channels defines the channel layer as the cross-process communication mechanism between consumer instances and other Django parts, with Redis as the official production backend. ([Django Channels][1])

#### Redis Channel Layer

The live fanout layer MUST use the official Redis-backed Channels layer in production. Channels states that `channels_redis` is the only official Django-maintained production channel layer, and that it supports group messaging and sharded configurations. ([Django Channels][1])

#### Redis Streams

Internal event processing MUST use Redis Streams with consumer groups for persistence and asynchronous downstream processing. Redis documents Streams as an append-only log-like structure suitable for recording and syndicating events in real time, including consumer-group-based processing. ([Redis][2])

#### PostgreSQL

PostgreSQL MUST remain the authoritative durable store for:

* conversations
* participants
* persisted messages
* attachment metadata
* durable receipts where required
* historical queries and reconnect recovery

PostgreSQL MUST NOT be used as the primary internal fanout or transient coordination mechanism.

---

## 7. Canonical design rules

### 7.1 Hot-path rules

The message send hot path MUST include only:

* authentication
* authorization
* validation
* message envelope creation
* live publish to Redis channel groups
* append to Redis Stream
* acknowledgement to sender

The message send hot path MUST NOT include:

* synchronous PostgreSQL write required for live fanout
* synchronous unread updates for all recipients
* synchronous typing/presence writes to PostgreSQL
* synchronous session summary recalculation
* polling PostgreSQL for new live events

### 7.2 Data ownership rules

#### Redis MUST own

* active connection routing
* presence state
* typing indicators
* room subscription state
* transient recent-message tail cache
* internal event transport
* short-lived idempotency/deduplication keys

#### PostgreSQL MUST own

* durable conversations
* durable participants
* persisted messages
* attachment metadata
* durable read/receipt records, if product-required
* historical replay and gap fill

#### Redis MUST NOT become the permanent source of truth for durable chat history.

### 7.3 Realtime rules

Live message delivery MUST be handled through Redis-backed fanout groups and NOT through PostgreSQL polling or PostgreSQL-trigger-driven coordination. Channels group support is part of the Redis-backed production channel layer. ([Django Channels][1])

### 7.4 Worker rules

Worker processing MUST be horizontally scalable and MUST use consumer groups. Redis documents that consumers in a group divide entries among themselves and acknowledge completed processing. ([Redis][3])

---

## 8. Message lifecycle

Every message MUST follow a lifecycle compatible with the following states:

```text
accepted -> published_live -> stored -> delivered -> read
```

### 8.1 Required semantics

* `accepted` means the gateway validated the message and accepted it for processing.
* `published_live` means the message was sent to the live fanout system.
* `stored` means the message was durably committed to PostgreSQL.
* `delivered` means at least one intended recipient connection received it.
* `read` means the application recorded a read state, if supported.

### 8.2 Client contract

Clients MUST NOT assume `accepted` implies durable storage.
Clients SHOULD surface a difference between `accepted` and `stored` where the product allows it.

---

## 9. Canonical event envelope

All internal chat events MUST use a canonical envelope.

Minimum required fields:

```json
{
  "event_type": "message.created",
  "schema_version": 1,
  "message_id": "string",
  "client_msg_id": "string-or-null",
  "conversation_id": "string",
  "sender_id": "string",
  "body": "string",
  "attachments": [],
  "created_at": "ISO-8601 timestamp"
}
```

### 9.1 Envelope rules

* `message_id` MUST be globally unique.
* `schema_version` MUST be present.
* all downstream consumers MUST consume the same canonical envelope
* downstream systems MUST NOT invent incompatible side-channel payload formats for the same event

---

## 10. Redis layout

The implementation MUST maintain separate logical responsibilities for live fanout, ephemeral state, and streams.

Illustrative key/stream naming:

```text
presence:user:{user_id}
conn:user:{user_id}
room:members:{conversation_id}
room:tail:{conversation_id}
typing:{conversation_id}:{user_id}

stream:chat_events
stream:notification_events
stream:projection_events
```

### 10.1 Presence and TTL rules

Presence and typing indicators MUST use TTL-backed keys and MUST expire automatically when heartbeats stop.

### 10.2 Connection routing rules

Per-user active channel mappings MUST be stored in Redis and MUST be removed or allowed to expire on disconnect/failure.

### 10.3 Stream rules

Consumer groups MUST be created explicitly. Redis documents `XGROUP CREATE` with an explicit starting ID such as `$` or `0`, depending on whether consumers should begin at the end or the beginning of the stream. ([Redis][4])

---

## 11. PostgreSQL rules

### 11.1 PostgreSQL role

PostgreSQL MUST serve as:

* the authoritative durable datastore
* the reconnect/history source
* the recovery source for rebuilding caches and projections
* the basis for audit and compliance data

### 11.2 PostgreSQL anti-patterns

The implementation MUST NOT use PostgreSQL for:

* presence heartbeats
* typing indicators
* live connection routing
* hot-path fanout coordination
* room message polling for active delivery

### 11.3 Pooling

A connection pooler such as PgBouncer SHOULD be placed in front of PostgreSQL because PostgreSQL connection count is bounded and expensive relative to lightweight in-memory coordination. PostgreSQL documents `max_connections` as a hard concurrent connection limit. ([PostgreSQL][5])

---

## 12. Required migration strategy

The migration MUST use an incremental strangler pattern.
The legacy path and the new path MUST coexist during migration until parity and rollback confidence are achieved.

### 12.1 Migration phases

#### Phase 0 — Instrumentation

The system MUST first add instrumentation and feature flags before behavior changes.

Required metrics:

* database query count per send
* database latency per send
* WebSocket end-to-end latency
* fanout latency
* Redis stream lag
* persistence lag
* duplicate message rate
* missing message rate
* reconnect gap-fill rate

Required feature flags:

* `redis_presence_enabled`
* `redis_fanout_enabled`
* `redis_stream_publish_enabled`
* `async_persistence_enabled`

#### Phase 1 — Dark launch Redis event publishing

The existing app MUST continue to behave as before, but MUST additionally publish canonical events to Redis in shadow mode.

Rollback requirement:

* disabling `redis_stream_publish_enabled` MUST restore legacy behavior without functional loss

#### Phase 2 — Migrate presence and typing

Presence, typing, and connection routing MUST move to Redis before live message persistence cutover.

Temporary compatibility:

* legacy SQL presence MAY remain for parity comparison for a limited migration window
* new development MUST target Redis presence APIs only

#### Phase 3 — Migrate live fanout

Live room/user fanout MUST move to Redis-backed Channels groups.

Channels documents groups and the Redis-backed production channel layer for cross-process messaging. ([Django Channels][1])

Rollback requirement:

* disabling `redis_fanout_enabled` MUST restore the legacy live delivery path

#### Phase 4 — Introduce persistence workers

Persistence workers MUST consume chat events from Redis Streams and write them durably to PostgreSQL.

Worker ack rule:

* workers MUST acknowledge stream entries only after successful durable PostgreSQL commit

Redis documents that consumer-group-based processing requires acknowledgements of processed entries. ([Redis][3])

#### Phase 5 — Dual-write verification

Before removing synchronous PostgreSQL writes from the hot path, the system MUST run a parity window where:

* the legacy sync write remains authoritative
* stream-based persistence runs in verification mode or dual-write mode
* outputs are compared continuously

#### Phase 6 — Async persistence cutover

Once parity is proven, the hot path MUST append to Redis Streams and MUST NOT require a synchronous PostgreSQL write for live delivery.

Optional temporary fallback:

* if stream append fails, a guarded fallback synchronous SQL write MAY be used during the migration window
* this fallback MUST be feature-flagged and removable

#### Phase 7 — Remove legacy database hot-path logic

After parity stability and rollback rehearsal, the system MUST remove:

* SQL presence writes
* SQL typing writes
* polling-based fanout
* synchronous unread fanout updates
* other live-only database coordination paths

---

## 13. Required parity and reconciliation controls

### 13.1 Parity checks

The system MUST continuously compare the legacy and new paths for:

* accepted vs stored message counts
* duplicate `message_id` rate
* missing persisted messages
* message ordering by conversation
* fanout recipient count parity
* session summary parity
* unread count parity where applicable

### 13.2 Reconciliation jobs

The system MUST provide reconciliation jobs for:

* rebuilding Redis membership/projection caches from PostgreSQL
* detecting and replaying missing persistence events
* recomputing unread/session summary projections
* repairing drift between derived projections and PostgreSQL truth

### 13.3 Recovery source

PostgreSQL MUST be treated as the authoritative recovery source during migration.

---

## 14. Idempotency and ordering

### 14.1 Idempotency

Persistence and downstream consumers MUST be idempotent.

Required minimums:

* `message_id` MUST be unique
* database writes MUST be safe under retry
* consumer reprocessing MUST NOT create duplicate durable messages

### 14.2 Ordering

The system SHOULD preserve conversation-local ordering semantics.
If strict global ordering is not feasible, the implementation MUST define and document the ordering guarantee actually provided.

### 14.3 Schema support

The PostgreSQL schema MUST support safe deduplication and retries.
At minimum, the durable message table SHOULD include:

* unique `message_id`
* optional `client_msg_id`
* `created_at`
* `stored_at`
* optional conversation-local sequence field

---

## 15. Read-path rules

### 15.1 Reconnect and history

Reconnect and historical message retrieval MUST read from PostgreSQL.
PostgreSQL hot standby/read-only replicas MAY be used for read-heavy history workloads; PostgreSQL documents hot standby as supporting read-only queries on standby systems. ([PostgreSQL][6])

### 15.2 Cache rules

Short-lived room-tail caching MAY exist in Redis, but Redis cache MUST NOT be considered authoritative durable history.

### 15.3 Membership rules

Membership MAY be cached in Redis, but PostgreSQL MUST remain the source of truth for durable membership state.

---

## 16. Failure handling requirements

### 16.1 Redis live fanout failure

If Redis live fanout is unavailable:

* the system MUST NOT pretend live delivery succeeded
* the system MUST either fall back to the legacy path or fail clearly
* reconnect/history from PostgreSQL MUST remain available

### 16.2 Stream consumer lag

The system MUST monitor stream lag. Redis provides consumer-group lag visibility through stream/group introspection, including lag reporting. ([Redis][7])

If persistence lag exceeds the configured threshold:

* autoscaling or backpressure MUST engage
* nonessential downstream consumers SHOULD be deprioritized before critical persistence consumers

### 16.3 PostgreSQL slowdown

If PostgreSQL slows down:

* live delivery MAY continue briefly for connected users if accepted into the stream
* persistence backlog MUST be surfaced operationally
* backpressure MUST prevent unbounded Redis memory growth

### 16.4 Ack correctness

A stream entry MUST NOT be acknowledged before the corresponding durable action has succeeded.

---

## 17. Deployment requirements

### 17.1 ASGI deployment

The service MUST run as an ASGI application. Channels deployment guidance states that Channels applications are deployed similarly to WSGI apps, typically behind an ASGI server such as Daphne, and can scale process counts horizontally. ([Django Channels][8])

### 17.2 Production channel layer

Production channel-layer deployment MUST use `channels_redis`. The in-memory channel layer MUST NOT be used in production because it does not provide the necessary cross-process semantics for a distributed deployment. Channels explicitly identifies `channels_redis` as the official production backend. ([Django Channels][1])

### 17.3 Redis topology

Redis SHOULD separate, logically or physically:

* channel-layer fanout traffic
* ephemeral cache/presence traffic
* stream-based worker traffic

A sharded Redis topology MAY be adopted as scale requires; Channels notes support for sharded channel-layer configurations. ([Django Channels][1])

### 17.4 Worker topology

Persistence workers MUST be independently scalable from WebSocket servers.

---

## 18. Security and access rules

* Redis and PostgreSQL MUST NOT be exposed publicly without network controls.
* internal events MUST NOT omit required authorization context
* consumers MUST validate that a sender is allowed to publish into a conversation
* reconnect/history endpoints MUST continue enforcing durable authorization against the authoritative source

---

## 19. Rollback requirements

Every migration phase MUST have a rollback switch.

Minimum rollback switches:

* `redis_presence_enabled = false`
* `redis_fanout_enabled = false`
* `redis_stream_publish_enabled = false`
* `async_persistence_enabled = false`

Rollback readiness MUST be proven before removing the legacy implementation.

The legacy path MUST NOT be deleted until all of the following are true:

* parity has been stable for the configured migration window
* rollback has been tested
* reconnect and recovery flows have been verified
* operational alerts and lag metrics are in place

---

## 20. Forbidden designs

The implementation MUST NOT introduce or preserve the following as primary production patterns:

* PostgreSQL polling for live chat fanout
* PostgreSQL as the primary inter-process realtime bus
* PostgreSQL presence heartbeats
* PostgreSQL typing-indicator writes
* mandatory synchronous SQL commit before any live delivery
* non-idempotent persistence workers
* production use of in-memory-only channel layers in a multi-instance deployment

---

## 21. Minimal end-state sequence

```text
1. Client sends message over WebSocket
2. Gateway authenticates and validates
3. Gateway checks membership using cache and/or authoritative state
4. Gateway creates canonical message envelope
5. Gateway publishes to Redis channel group(s)
6. Gateway appends event to Redis Stream
7. Gateway returns message.accepted
8. Persistence worker reads event from stream consumer group
9. Persistence worker writes durably to PostgreSQL
10. Persistence worker acknowledges the stream entry
11. Persistence worker emits message.stored event if required
12. Reconnect/history requests read from PostgreSQL
```

This sequence is REQUIRED for the end state.

---

## 22. Acceptance criteria

The migration MUST NOT be considered complete until all of the following are true:

1. live delivery no longer requires synchronous PostgreSQL commit
2. presence and typing no longer write to PostgreSQL
3. fanout no longer depends on PostgreSQL polling or equivalent
4. persistence occurs through Redis Stream consumers
5. PostgreSQL remains the authoritative durable store
6. rollback switches still exist or are intentionally retired after stabilization
7. parity and reconciliation controls have passed the migration window
8. operational visibility exists for stream lag, persistence lag, duplicate rate, and reconnect recovery

---

## 23. Summary

The required architecture is:

* Channels + ASGI for connection handling
* official Redis-backed channel layer for live fanout
* Redis ephemeral state for presence and routing
* Redis Streams with consumer groups for asynchronous internal processing
* PostgreSQL for durable storage and history
* incremental migration with parity, rollback, and reconciliation

This design aligns with the documented production model for Channels, the event-log and consumer-group model of Redis Streams, and PostgreSQL’s own documented connection/resource limits. ([Django Channels][1])

```
::contentReference[oaicite:18]{index=18}
```

[1]: https://channels.readthedocs.io/en/latest/topics/channel_layers.html?utm_source=chatgpt.com "Channel Layers — Channels 4.3.2 documentation"
[2]: https://redis.io/docs/latest/develop/data-types/streams/?utm_source=chatgpt.com "Redis Streams | Docs"
[3]: https://redis.io/docs/latest/develop/tools/insight/insight-stream-consumer/?utm_source=chatgpt.com "Manage streams and consumer groups in Redis Insight"
[4]: https://redis.io/docs/latest/commands/xgroup-create/?utm_source=chatgpt.com "XGROUP CREATE | Docs"
[5]: https://www.postgresql.org/docs/current/runtime-config-connection.html?utm_source=chatgpt.com "Documentation: 18: 19.3. Connections and Authentication"
[6]: https://www.postgresql.org/docs/current/hot-standby.html?utm_source=chatgpt.com "Documentation: 18: 26.4. Hot Standby"
[7]: https://redis.io/docs/latest/commands/xinfo-groups/?utm_source=chatgpt.com "XINFO GROUPS | Docs"
[8]: https://channels.readthedocs.io/en/latest/deploying.html?utm_source=chatgpt.com "Deploying — Channels 4.3.2 documentation"
