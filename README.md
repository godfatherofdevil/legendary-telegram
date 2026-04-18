# Online Chat Server Monorepo

## 1. Overview

This repository contains a monorepo implementation skeleton for a classic web-based online chat application.

It is designed to support:

- user registration and authentication
- public and private chat rooms
- one-to-one dialogs
- contacts / friends
- attachments
- moderation
- persistent message history
- unread tracking
- online / AFK / offline presence
- session management
- REST APIs
- WebSocket real-time messaging

This monorepo keeps backend and frontend in one repository while preserving clear service boundaries.

---

## 2. Repository Structure

```text
chat-app/
├── AGENTS.md
├── API_CONTRACT.md
├── SCHEMA.md
├── DJANGO_MODELS_MAPPING.md
├── ARCHITECTURE.md
├── DEPLOYMENT.md
├── DEPLOYEMENT.md
├── TASKS.md
├── README.md
├── .env.example
├── docker-compose.yml
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── manage.py
│   ├── config/
│   └── apps/
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
│
└── scripts/
````

### Repository Boundaries

* `backend/` contains the Django + DRF + Channels application
* `frontend/` contains the React + TypeScript application
* repository root contains shared specs, deployment config, and orchestration files

---

## 3. Authoritative Documents

The following files define project behavior and implementation expectations:

* `AGENTS.md` — agent behavior and implementation rules
* `API_CONTRACT.md` — REST and WebSocket contract
* `SCHEMA.md` — initial logical database schema
* `DJANGO_MODELS_MAPPING.md` — Django model mapping guidance
* `ARCHITECTURE.md` — architecture rules and system boundaries
* `DEPLOYMENT.md` — local Docker-based deployment instructions
* `TASKS.md` — implementation sequencing plan

If any implementation detail is unclear, these documents must be consulted in precedence order defined by `AGENTS.md`.

---

## 4. Tech Stack

### Backend

* Python 3.12+
* Django
* Django REST Framework
* Django Channels
* Redis
* PostgreSQL

### Frontend

* TypeScript
* React
* Vite

### Local Infrastructure

* Docker
* Docker Compose

---

## 5. Monorepo Goals

This repository structure exists to keep development simple while preserving clear separation of responsibilities.

### Why this monorepo exists

* backend and frontend evolve together
* shared specs remain in one place
* Docker orchestration is simpler
* contract-driven development is easier
* onboarding is simpler than maintaining separate repos

### What this monorepo does not mean

* backend and frontend are not merged into one app
* frontend is not served from the backend container by default
* backend and frontend still run as separate services
* API contract remains explicit and versioned

---

## 6. Service Layout

The local system consists of four main services:

* `postgres` — relational database
* `redis` — cache and Channels broker
* `backend` — Django application
* `frontend` — React application

Backend and frontend MUST remain separate services even though they live in one repository.

---

## 7. Directory Details

## 7.1 Root

The root of the repository contains project-wide files:

* specs and contracts
* Docker Compose file
* shared environment examples
* top-level scripts
* this README

## 7.2 `backend/`

The backend is responsible for:

* authentication
* session lifecycle
* presence computation
* friend requests and friendships
* peer bans
* room lifecycle
* room moderation
* dialogs
* message persistence
* attachment authorization
* REST API
* WebSocket API

Recommended backend app structure:

* `accounts`
* `presence`
* `social`
* `chat`
* `attachments`
* `audit`

## 7.3 `frontend/`

The frontend is responsible for:

* authentication screens
* classic chat layout
* room and dialog lists
* member lists
* message rendering
* reply flow
* attachment uploads
* unread indicators
* session management UI
* REST API consumption
* WebSocket event handling

---

## 8. Local Development Requirements

You need the following installed locally:

* Docker
* Docker Compose

Optional but useful:

* Python 3.12+
* Node.js 20+
* npm

Docker is enough for the standard local workflow.

Once the backend is running, Swagger documentation is available at `http://localhost:8000/api/docs/` and the machine-readable OpenAPI document is available at `http://localhost:8000/api/schema/`.

---

## 9. Environment Configuration

Create a root `.env` file based on `.env.example`.

Minimal example:

```env
POSTGRES_DB=chat_app
POSTGRES_USER=chat_user
POSTGRES_PASSWORD=chat_password
POSTGRES_PORT=5432

REDIS_PORT=6379

BACKEND_PORT=8000
FRONTEND_PORT=3000

DJANGO_SECRET_KEY=local-dev-secret-key
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,backend

DATABASE_URL=postgresql://chat_user:chat_password@postgres:5432/chat_app
REDIS_URL=redis://redis:6379/0

FRONTEND_API_BASE_URL=http://localhost:8000/api/v1
FRONTEND_WS_BASE_URL=ws://localhost:8000/ws/v1/chat
```

### Notes

* local secrets must not be reused in production
* backend container should use service hostnames like `postgres` and `redis`
* frontend should point to backend via localhost-exposed port in browser context

---

## 10. Quick Start

## 10.1 Prepare environment

```bash
cp .env.example .env
```

## 10.2 Start everything

From repository root:

```bash
docker compose up --build
```

The backend Compose service enables guarded local recovery for a stale Postgres volume that still records `admin.0001_initial` before `accounts.0001_initial`. In that exact case, startup resets the local database schema and reapplies migrations so the custom user model boots cleanly.

## 10.3 Verify services

- Frontend: `http://localhost:3000`
- Backend admin route: `http://localhost:8000/admin/`

## 10.4 Backend test workflow

From `backend/`:

```bash
python -m pytest
ruff check .
```

### Expected local URLs

* frontend: `http://localhost:3000`
* backend: `http://localhost:8000`

---

## 10.2 Start infrastructure only

```bash
docker compose up -d postgres redis
```

---

## 10.3 Start backend only

```bash
docker compose up backend
```

---

## 10.4 Start frontend only

```bash
docker compose up frontend
```

---

## 11. Typical Development Workflow

### Step 1

Read the authoritative docs:

* `AGENTS.md`
* `API_CONTRACT.md`
* `SCHEMA.md`
* `TASKS.md`

### Step 2

Create `.env` from `.env.example`.

### Step 3

Bring up infrastructure:

```bash
docker compose up -d postgres redis
```

### Step 4

Run backend:

```bash
docker compose up backend
```

### Step 5

Run frontend:

```bash
docker compose up frontend
```

### Step 6

Verify:

* frontend loads
* backend API responds
* backend can connect to postgres
* backend can connect to redis
* WebSocket endpoint is reachable

---

## 12. Backend Notes

The backend lives in `backend/`.

Expected responsibilities include:

* Django project config in `backend/config/`
* domain apps in `backend/apps/`
* migrations inside each app
* REST endpoints under `/api/v1`
* WebSocket endpoint under `/ws/v1/chat`

Typical backend commands:

```bash
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py createsuperuser
docker compose run --rm backend python manage.py test
```

---

## 13. Frontend Notes

The frontend lives in `frontend/`.

Expected responsibilities include:

* React application bootstrap
* route definitions
* feature modules
* REST client
* WebSocket client
* chat UI components
* auth pages
* rooms/dialogs UI

Typical frontend commands inside containerized workflow are driven by Docker Compose.

If running locally outside Docker, typical commands are:

```bash
npm install
npm run dev
npm run build
npm run test
```

---

## 14. Testing

## 14.1 Backend tests

Run backend tests:

```bash
docker compose run --rm backend python manage.py test
```

If pytest is used instead:

```bash
docker compose run --rm backend pytest
```

## 14.2 Frontend tests

Run frontend tests:

```bash
docker compose run --rm frontend npm test
```

## 14.3 Contract verification

The project should include tests for:

* API contract compliance
* WebSocket event contract compliance
* permissions and authorization
* room access revocation
* peer-ban frozen dialog behavior
* attachments access control

---

## 15. Core Development Rules

All contributors and coding agents must follow these principles:

* implement the smallest correct change
* keep backend and frontend contracts aligned
* preserve API field names and endpoint behavior
* do not invent product features outside spec
* keep backend and frontend as separate services
* add or update tests for behavior changes
* update docs when behavior changes

See `AGENTS.md` for the full rule set.

---

## 16. Suggested Implementation Order

Use `TASKS.md` as the main execution plan.

High-level order:

1. scaffold repository and Docker flow
2. implement backend data model and migrations
3. implement authentication and sessions
4. implement rooms and dialogs
5. implement messaging and history
6. implement attachments
7. implement presence and unread state
8. implement moderation and bans
9. implement WebSocket protocol
10. implement frontend integration
11. harden deployment and tests

---

## 17. Minimal Health Check

The local setup is considered healthy only if all of the following are true:

* postgres is running
* redis is running
* backend starts successfully
* migrations apply successfully
* frontend starts successfully
* frontend can call backend REST API
* frontend can connect to backend WebSocket endpoint

---

## 18. Common Commands

## 18.1 Build all services

```bash
docker compose build
```

## 18.2 Start all services

```bash
docker compose up
```

## 18.3 Start all services detached

```bash
docker compose up -d
```

## 18.4 Stop all services

```bash
docker compose down
```

## 18.5 Stop and remove volumes

```bash
docker compose down -v
```

## 18.6 View logs

```bash
docker compose logs -f
```

## 18.7 View backend logs

```bash
docker compose logs -f backend
```

## 18.8 View frontend logs

```bash
docker compose logs -f frontend
```

---

## 19. Initial Milestone Checklist

A good initial repository state should include:

* root specs present
* `docker-compose.yml` present
* backend Dockerfile present
* frontend Dockerfile present
* backend scaffold present
* frontend scaffold present
* `.env.example` present
* README present

---

## 20. What to Implement First

The minimum useful starting point is:

### Backend

* custom user model
* session metadata model
* room model
* dialog model
* message models
* auth endpoints
* room listing endpoints
* WebSocket connection scaffold

### Frontend

* Vite + React + TypeScript scaffold
* router
* auth pages
* chat shell layout
* API client
* WebSocket client scaffold

---

## 21. Non-Goals for the Initial Skeleton

This repository skeleton does not yet imply:

* full production deployment setup
* CI/CD configuration
* Kubernetes deployment
* object storage integration
* push notification system
* XMPP/Jabber federation
* load testing harness
* analytics pipeline

Those may be added later.

---

## 22. Contribution Guidance

When contributing:

* read the specs first
* follow `TASKS.md`
* do not break `API_CONTRACT.md`
* keep changes scoped
* add tests
* update docs when needed

If you change any externally visible contract behavior, you must update the relevant authoritative document in the same change.

---

## 23. Final Rule

This monorepo is correct only if it preserves all of the following:

* separate backend and frontend services
* a single shared source of truth for specs
* Docker-based local development from repository root
* clear implementation boundaries
* contract-first development discipline

If simplicity and correctness conflict with unnecessary complexity, prefer simplicity.

---

```
