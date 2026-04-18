# ARCHITECTURE.md

## 1. Purpose

This document defines the minimum architecture boundaries for the Online Chat Server implementation.

It exists to keep the repository aligned with:

- `AGENTS.md`
- `API_CONTRACT.md`
- `SCHEMA.md`

This initial architecture is deliberately conservative and optimized for correctness and local development.

---

## 2. Runtime Topology

The system is composed of four primary runtime services:

- `frontend` - React + TypeScript web client
- `backend` - Django + DRF + Channels application
- `postgres` - primary relational database
- `redis` - Channels broker and transient coordination store

The frontend and backend MUST remain separate services in local Docker execution.

---

## 3. Backend Boundaries

The backend is the source of truth for:

- authentication and session control
- authorization
- persistence
- room and dialog business rules
- moderation rules
- attachment access control
- presence aggregation
- WebSocket event authorization and fan-out

The backend MUST expose:

- REST APIs under `/api/v1`
- WebSocket traffic under `/ws/v1`

The backend MUST persist state before broadcasting contract-visible events.

---

## 4. Application Layers

The backend SHOULD preserve the following layers:

1. configuration and entrypoints
2. domain apps and models
3. service-layer business logic
4. REST serializers and views
5. WebSocket consumers and routing

Authorization and validation logic MUST live in backend code, not in the frontend.

---

## 5. Real-Time Flow

WebSocket connections terminate at Django Channels.

Redis is used for:

- channel layer coordination
- multi-process message fan-out
- short-lived real-time state that does not replace persistent records

Persistent chat state, session metadata, and moderation state MUST remain in PostgreSQL.

---

## 6. Frontend Responsibilities

The frontend is responsible for:

- authentication screens
- classic chat navigation
- API consumption
- WebSocket session usage
- rendering server-authorized state

The frontend MUST NOT be treated as an authorization boundary.

---

## 7. M1 Foundation Scope

For milestone M1, the repository foundation MUST provide:

- bootable backend project scaffold
- ASGI entrypoint wired for Channels
- Docker Compose orchestration for backend, frontend, postgres, and redis
- environment-variable driven configuration
- baseline quality tooling and smoke tests

Later milestones will add contract-specific endpoints, models, and WebSocket protocol details without changing these service boundaries.
