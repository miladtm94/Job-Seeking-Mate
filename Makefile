.PHONY: up start stop restart status down logs rebuild quick-update update backend frontend test lint format install migrate

up:
	docker compose up -d --build

start:
	docker compose up -d

stop:
	docker compose stop

restart:
	docker compose restart

status:
	docker compose ps

down:
	docker compose down

logs:
	docker compose logs -f

rebuild:
	docker compose build --no-cache
	docker compose up -d

quick-update:
	git pull --ff-only
	docker compose up -d --build

update: quick-update

backend:
	-kill $$(lsof -ti :8000) 2>/dev/null; sleep 0.5
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

install:
	cd backend && pip install -e .[dev]
	cd frontend && npm install

test:
	cd backend && pytest -q

lint:
	cd backend && ruff check . && mypy app
	cd frontend && npm run lint

format:
	cd backend && ruff format .

migrate:
	cd backend && alembic upgrade head
