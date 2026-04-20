SHELL := /bin/bash
.DEFAULT_GOAL := help

VENV := .venv
COMPOSE := docker compose
EXPORT_LOCAL_ENV = set -a; if [ -f .local/.env ]; then . ./.local/.env; fi; set +a

.PHONY: help venv backend-install frontend-install install backend-test frontend-test \
	backend-lint backend-lint-fix backend-format backend-format-check frontend-lint frontend-lint-fix lint lint-fix backend-migrate backend-local frontend-local \
	infra-up infra-down backend-build frontend-build stack-build backend-compose \
	frontend-compose backend-migrate-compose stack-up stack-up-detached stack-down \
	stack-down-volumes stack-logs

help:
	@printf '%s\n' \
		'Available targets:' \
		'  make venv                Create the local Python virtual environment at .venv' \
		'  make backend-install     Install backend dependencies into .venv' \
		'  make frontend-install    Install frontend dependencies with npm' \
		'  make install             Install both backend and frontend dependencies' \
		'  make backend-test        Run backend tests with pytest' \
		'  make frontend-test       Run frontend tests with vitest' \
		'  make backend-lint        Run backend lint and format checks with ruff' \
		'  make backend-lint-fix    Apply backend lint fixes and formatting with ruff' \
		'  make backend-format      Format backend Python files with ruff' \
		'  make backend-format-check  Check backend formatting with ruff' \
		'  make frontend-lint       Run frontend type checks' \
		'  make frontend-lint-fix   Run available frontend static fixes (typecheck only)' \
		'  make lint                Run backend and frontend static checks' \
		'  make lint-fix            Run backend and frontend lint-fix targets' \
		'  make backend-migrate     Run Django migrations locally from .venv' \
		'  make backend-local       Run the backend locally from .venv' \
		'  make frontend-local      Run the frontend locally with a localhost backend proxy' \
		'  make infra-up            Start postgres, redis, minio, and minio-init with Docker Compose' \
		'  make infra-down          Stop postgres, redis, minio, and minio-init' \
		'  make backend-build       Build the backend Docker image' \
		'  make frontend-build      Build the frontend Docker image' \
		'  make stack-build         Build backend and frontend Docker images' \
		'  make backend-compose     Run the backend service through Docker Compose' \
		'  make frontend-compose    Run the frontend service through Docker Compose' \
		'  make backend-migrate-compose  Run Django migrations in the backend Compose service' \
		'  make stack-up            Build and run the full Docker Compose stack' \
		'  make stack-up-detached   Build and run the full Docker Compose stack in the background' \
		'  make stack-down          Stop and remove the Docker Compose stack' \
		'  make stack-down-volumes  Stop the stack and remove volumes' \
		'  make stack-logs          Follow Docker Compose logs'

venv:
	python3 -m venv $(VENV)

backend-install: venv
	. $(VENV)/bin/activate && pip install -r backend/requirements.txt

frontend-install:
	cd frontend && npm install

install: backend-install frontend-install

backend-test:
	. $(VENV)/bin/activate && cd backend && python -m pytest

frontend-test:
	cd frontend && npm test

backend-lint:
	. $(VENV)/bin/activate && cd backend && ruff check . && ruff format --check .

backend-lint-fix:
	. $(VENV)/bin/activate && cd backend && ruff check --fix . && ruff format .

backend-format:
	. $(VENV)/bin/activate && cd backend && ruff format .

backend-format-check:
	. $(VENV)/bin/activate && cd backend && ruff format --check .

frontend-lint:
	cd frontend && npm run typecheck

frontend-lint-fix:
	cd frontend && npm run typecheck

lint: backend-lint frontend-lint

lint-fix: backend-lint-fix frontend-lint-fix

backend-migrate:
	. $(VENV)/bin/activate && cd backend && python manage.py migrate

backend-local:
	@$(EXPORT_LOCAL_ENV) && . $(VENV)/bin/activate && cd backend && python -m config.entrypoint

frontend-local:
	@$(EXPORT_LOCAL_ENV) && cd frontend && \
	exec env \
	FRONTEND_PROXY_TARGET="$${FRONTEND_PROXY_TARGET:-http://127.0.0.1:8000}" \
	FRONTEND_API_BASE_URL="$${FRONTEND_API_BASE_URL:-http://127.0.0.1:8000/api/v1}" \
	FRONTEND_WS_BASE_URL="$${FRONTEND_WS_BASE_URL:-ws://127.0.0.1:8000/ws/v1/chat}" \
	npm run dev -- --host 0.0.0.0 --port "$${FRONTEND_PORT:-3000}"

infra-up:
	$(COMPOSE) up -d postgres redis minio minio-init

infra-down:
	$(COMPOSE) stop postgres redis minio minio-init

backend-build:
	$(COMPOSE) build backend

frontend-build:
	$(COMPOSE) build frontend

stack-build:
	$(COMPOSE) build backend frontend

backend-compose:
	$(COMPOSE) up backend

frontend-compose:
	$(COMPOSE) up frontend

backend-migrate-compose:
	$(COMPOSE) run --rm backend python manage.py migrate

stack-up:
	$(COMPOSE) up --build

stack-up-detached:
	$(COMPOSE) up --build -d

stack-down:
	$(COMPOSE) down

stack-down-volumes:
	$(COMPOSE) down -v

stack-logs:
	$(COMPOSE) logs -f
