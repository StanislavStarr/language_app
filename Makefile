COMPOSE := docker compose -f infra/docker-compose.yml
OPENAPI_FILE := backend/openapi.json

.PHONY: up down db-reset backend-dev backend-check backend-fix migrate migration \
	mobile-dev mobile-check api-types

up:
	$(COMPOSE) up -d --wait postgres

down:
	$(COMPOSE) down

db-reset:
	$(COMPOSE) down --volumes
	$(COMPOSE) up -d --wait postgres

backend-dev:
	cd backend && uv run fastapi dev

backend-check:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest

backend-fix:
	cd backend && uv run ruff format . && uv run ruff check --fix .

migrate:
	cd backend && uv run alembic upgrade head

migration:
	@test -n "$(name)" || (echo "usage: make migration name=<migration_name>" && exit 1)
	cd backend && uv run alembic revision --autogenerate -m "$(name)"

mobile-dev:
	cd mobile && npx expo start

mobile-check:
	cd mobile && npx tsc --noEmit && npx eslint . && npx steiger ./src && npx jest

api-types:
	cd backend && uv run python scripts/export_openapi.py
	cd mobile && npx openapi-typescript ../$(OPENAPI_FILE) -o src/shared/api/schema.d.ts
