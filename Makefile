.PHONY: up down logs shell test seed migrate lint fmt help

COMPOSE = docker compose
BACKEND = $(COMPOSE) exec backend
FRONTEND = $(COMPOSE) exec frontend

help:
	@echo "ZWAN-CODEX-V2 — bug bounty agentic platform"
	@echo ""
	@echo "  make up        bring full stack online"
	@echo "  make down      stop and remove containers (keep volumes)"
	@echo "  make purge     stop + remove containers AND volumes"
	@echo "  make logs      tail all service logs"
	@echo "  make migrate   run alembic migrations"
	@echo "  make seed      seed qdrant with disclosed reports"
	@echo "  make test      run backend pytest suite"
	@echo "  make lint      ruff + mypy on backend"
	@echo "  make fmt       ruff format on backend"
	@echo "  make shell s=backend   open shell in service (default: backend)"

up:
	@[ -f .env ] || (cp .env.example .env && echo "Created .env from .env.example — set POSTGRES_PASSWORD and ANTHROPIC_API_KEY before continuing" && exit 1)
	$(COMPOSE) up -d --build
	@echo ""
	@echo "  Backend:  http://127.0.0.1:$$(grep BACKEND_PORT .env | cut -d= -f2 || echo 8731)"
	@echo "  Frontend: http://127.0.0.1:$$(grep FRONTEND_PORT .env | cut -d= -f2 || echo 3000)"

down:
	$(COMPOSE) down

purge:
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f $(s)

migrate:
	$(BACKEND) alembic upgrade head

seed:
	$(BACKEND) python -m app.db.seed

test:
	$(BACKEND) pytest tests/ -v

lint:
	$(BACKEND) ruff check app/ && $(BACKEND) mypy app/

fmt:
	$(BACKEND) ruff format app/

shell:
	$(COMPOSE) exec $${s:-backend} bash
