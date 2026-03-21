.PHONY: up down logs backend frontend test lint format install migrate

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f

backend:
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
