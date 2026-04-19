# REDIS_KEYS.md

## Purpose

This document defines the Redis key layout introduced for migration milestone `T12.2`.

## Keys

`presence:user:{user_id}`
- Aggregate user presence snapshot JSON.
- TTL-backed.
- Example payload: `{"user_id":"...","presence":"online","last_changed_at":"2026-04-19T12:00:00Z"}`

`conn:user:{user_id}`
- Set of active WebSocket connection keys for a user.
- TTL-backed.
- Used to rebuild aggregate presence from currently live connections.

`presence:connection:{connection_key}`
- Per-connection heartbeat record JSON.
- TTL-backed.
- Stores `tab_id`, `session_id`, `is_active`, `last_interaction_at`, `last_heartbeat_at`, and `connected_at`.

`typing:{chat_type}:{chat_id}:{user_id}`
- Reserved typing indicator key.
- TTL-backed.
- Used for future typing fanout without reintroducing SQL-first ephemeral state.

## Rules

- Presence and typing keys MUST expire automatically when heartbeats stop.
- PostgreSQL remains the durable store for user/session records.
- Redis is the source of truth for live connection and heartbeat state when `CHAT_REDIS_PRESENCE_ENABLED=1`.
- Legacy SQL presence rows may be dual-written temporarily when `CHAT_LEGACY_SQL_PRESENCE_ENABLED=1`.
