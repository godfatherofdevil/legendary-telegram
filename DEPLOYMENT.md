# DEPLOYMENT.md

## 1. Purpose

This document defines the minimal local Docker-based deployment flow for the Online Chat Server.

It is intentionally limited to local development and validation.

This deployment model includes:

- backend deployment
- frontend deployment
- PostgreSQL
- Redis

The backend and frontend MUST be deployed as separate services.

This document assumes:

- Docker is installed
- Docker Compose is installed
- repository root contains the required backend and frontend source directories
- backend and frontend each have their own Dockerfile

---

## 2. Deployment Topology

Local deployment consists of four services:

- `postgres` — primary relational database
- `redis` — cache / channels broker
- `backend` — Django + DRF + Channels application
- `frontend` — web client application

The backend and frontend MUST run in separate containers.

The frontend MUST communicate with the backend over HTTP and WebSocket using container-exposed ports.

---

## 3. Directory Assumptions

This document assumes the repository has a structure similar to:

```text
/
├── docker-compose.yml
├── .env
├── backend/
│   ├── Dockerfile
│   ├── manage.py
│   └── ...
└── frontend/
    ├── Dockerfile
    └── ...
````

If the actual directory names differ, update the Compose file accordingly.

---

## 4. Required Environment Variables

A root `.env` file SHOULD exist for local deployment.

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
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
DJANGO_CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

DATABASE_URL=postgresql://chat_user:chat_password@postgres:5432/chat_app
REDIS_URL=redis://redis:6379/0

FRONTEND_API_BASE_URL=http://localhost:8000/api/v1
FRONTEND_WS_BASE_URL=ws://localhost:8000/ws/v1/chat
```

### Rules

* Local secrets in `.env` MUST NOT be reused in production.
* `DATABASE_URL` MUST point to the `postgres` service hostname.
* `REDIS_URL` MUST point to the `redis` service hostname.
* Frontend API and WebSocket URLs SHOULD target the backend’s exposed local port.

---

## 5. Minimal docker-compose.yml

Create a root-level `docker-compose.yml` similar to the following:

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16
    container_name: chat_postgres
    restart: unless-stopped
    env_file:
      - .env
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7
    container_name: chat_redis
    restart: unless-stopped
    ports:
      - "${REDIS_PORT:-6379}:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: chat_backend
    restart: unless-stopped
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    volumes:
      - ./backend:/app
    command: ["/app/entrypoint.sh"]

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: chat_frontend
    restart: unless-stopped
    env_file:
      - .env
    depends_on:
      - backend
    ports:
      - "${FRONTEND_PORT:-3000}:3000"
    volumes:
      - ./frontend:/app
      - frontend_node_modules:/app/node_modules
    command: ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]

volumes:
  postgres_data:
  redis_data:
  frontend_node_modules:
```

---

## 6. Minimal Backend Dockerfile

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
```

### Backend Notes

* The backend container MUST include all Python dependencies.
* The backend MUST bind to `0.0.0.0`.
* Local startup MAY use Django `runserver`, but this repository uses Daphne so the ASGI entrypoint is exercised from the first milestone.
* Production-grade WSGI/ASGI process management is out of scope for this minimal local deployment doc.

---

## 7. Minimal Frontend Dockerfile

Create `frontend/Dockerfile`:

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package*.json /app/
RUN npm install

COPY . /app

EXPOSE 3000
```

### Frontend Notes

* The frontend container MUST run separately from backend.
* The frontend MUST bind to `0.0.0.0`.
* The frontend MUST be configured to call the backend over the backend host port exposed on localhost.

---

## 8. Backend Local Deployment Instructions

The backend MUST be deployable independently from the frontend.

### Step 1: Build backend container

```bash
docker compose build backend
```

### Step 2: Start backend dependencies

```bash
docker compose up -d postgres redis
```

### Step 3: Start backend

```bash
docker compose up backend
```

### Step 4: Verify backend

Open:

```text
http://localhost:8000
```

If the project exposes API routes only, verify an API endpoint such as:

```text
http://localhost:8000/api/v1/auth/me
```

Expected behavior:

* unauthenticated request returns `401 Unauthorized` or project-defined equivalent
* backend logs show successful DB and Redis connection

---

## 9. Frontend Local Deployment Instructions

The frontend MUST be deployable independently from the backend application process, but it depends on the backend being available.

### Step 1: Build frontend container

```bash
docker compose build frontend
```

### Step 2: Ensure backend is running

```bash
docker compose up -d postgres redis backend
```

### Step 3: Start frontend

```bash
docker compose up frontend
```

### Step 4: Verify frontend

Open:

```text
http://localhost:3000
```

Expected behavior:

* frontend loads in browser
* frontend can call backend APIs on `http://localhost:8000`
* frontend can connect to backend WebSocket at `ws://localhost:8000/ws/v1/chat`

---

## 10. Full Local Deployment

To start all services together:

```bash
docker compose up --build
```

To start all services in detached mode:

```bash
docker compose up --build -d
```

### Expected local ports

* frontend: `http://localhost:3000`
* backend: `http://localhost:8000`
* postgres: `localhost:5432`
* redis: `localhost:6379`

---

## 11. Database Migration Step

The backend container command in the sample Compose file runs migrations on startup:

```bash
python manage.py migrate
```

For local Docker Compose only, the backend also enables guarded recovery for one specific stale-volume case:

* if PostgreSQL still contains the old migration history where `admin.0001_initial` was applied before `accounts.0001_initial`
* startup resets the local database schema and reapplies migrations
* this recovery is controlled by `DJANGO_RESET_INCONSISTENT_MIGRATIONS=1` in the Compose backend service

This is intended for local development after introducing the custom `accounts.User` model. It should not be enabled for environments where preserving database contents matters.

If manual migration execution is preferred, use:

```bash
docker compose run --rm backend python manage.py migrate
```

If a superuser is needed for local admin testing:

```bash
docker compose run --rm backend python manage.py createsuperuser
```

---

## 12. Static and Media Files

For minimal local deployment:

* static files MAY be served by Django directly in debug mode
* uploaded media/files MUST be stored in a backend-accessible local filesystem path
* media storage SHOULD use a Docker volume if persistence across container recreation is needed

Minimal optional backend volume example:

```yaml
backend:
  volumes:
    - ./backend:/app
    - media_data:/app/media
```

Optional root volume declaration:

```yaml
volumes:
  postgres_data:
  redis_data:
  media_data:
```

---

## 13. Logs and Debugging

### View all logs

```bash
docker compose logs -f
```

### View backend logs

```bash
docker compose logs -f backend
```

### View frontend logs

```bash
docker compose logs -f frontend
```

### View postgres logs

```bash
docker compose logs -f postgres
```

### View redis logs

```bash
docker compose logs -f redis
```

---

## 14. Stopping Services

Stop all running containers:

```bash
docker compose down
```

Stop and remove volumes also:

```bash
docker compose down -v
```

### Warning

The following command deletes local Postgres data volume:

```bash
docker compose down -v
```

Use it only when data reset is intended.

---

## 15. Rebuild Flow

If backend or frontend dependencies change, rebuild containers:

```bash
docker compose build backend frontend
```

Then restart:

```bash
docker compose up -d
```

For a full clean rebuild:

```bash
docker compose down
docker compose build --no-cache
docker compose up
```

---

## 16. Minimal Health Checklist

Local deployment is considered healthy only if all of the following are true:

* `postgres` container is healthy
* `redis` container is healthy
* backend starts successfully
* backend migrations apply successfully
* frontend starts successfully
* frontend can reach backend API
* frontend can reach backend WebSocket endpoint

---

## 17. Common Failure Cases

### Backend cannot connect to database

Check:

* `DATABASE_URL` uses hostname `postgres`
* Postgres container is healthy
* credentials in `.env` match Compose config

### Backend cannot connect to Redis

Check:

* `REDIS_URL` uses hostname `redis`
* Redis container is healthy

### Frontend cannot reach backend

Check:

* backend is running on port `8000`
* frontend environment variables point to `http://localhost:8000`
* browser console for CORS or network errors

### WebSocket connection fails

Check:

* backend ASGI application is correctly configured
* Channels is installed and configured
* Redis channel layer is reachable
* frontend WebSocket URL is `ws://localhost:8000/ws/v1/chat`

---

## 18. Minimal Production Separation Note

This document is only for local Docker-based deployment.

For local deployment:

* backend runs in its own container
* frontend runs in its own container

That separation is mandatory and MUST be preserved in any more advanced deployment setup as well.

---

## 19. Final Rule

The local deployment is valid only if:

* backend is deployed separately
* frontend is deployed separately
* postgres is deployed separately
* redis is deployed separately
* the full stack can be started with Docker Compose from repository root
* frontend communicates with backend over HTTP/WebSocket, not by being bundled into the backend container

---

```
