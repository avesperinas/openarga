.PHONY: up down migrate provision modules identity resolve seed seed-clear test-db check lint test fmt hooks new-module

up:
	docker compose up -d --build

down:
	docker compose down

migrate:
	uv run alembic -c kernel/alembic.ini upgrade head

provision:
	uv run python -m kernel.provision $(id)

modules:
	uv run python -m kernel.modules

identity:
	uv run python kernel/tests/corpus.py

resolve:
	uv run python -m kernel.resolver

seed:
	uv run python -m kernel.seed

seed-clear:
	uv run python -m kernel.seed --clear

test-db:
	docker rm -f arga-pg-test 2>/dev/null || true
	docker run -d --name arga-pg-test -e POSTGRES_USER=openarga -e POSTGRES_PASSWORD=changeme -e POSTGRES_DB=openarga -p 5433:5432 postgres:16-alpine

check: lint test

lint:
	uv run ruff check .
	uv run ruff format --check .
	pnpm -r lint
	pnpm run lint:tokens

test:
	uv run pytest
	pnpm -r test

fmt:
	uv run ruff check --fix .
	uv run ruff format .

hooks:
	uv run pre-commit install

new-module:
	./scripts/new-module.sh $(id)
