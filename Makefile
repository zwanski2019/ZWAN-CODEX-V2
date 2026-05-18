.PHONY: up down purge logs shell test seed migrate lint fmt help dev stop restart status

COMPOSE   = docker compose
BACKEND   = $(COMPOSE) exec backend
FRONTEND  = $(COMPOSE) exec frontend
PID_DIR   = .pids
LOG_DIR   = .logs
BPORT    ?= $(shell grep BACKEND_PORT .env 2>/dev/null | cut -d= -f2 || echo 8732)
FPORT    ?= $(shell grep FRONTEND_PORT .env 2>/dev/null | cut -d= -f2 || echo 3001)

# ── Native dev mode (no Docker needed — uses whatever infra is running) ───────

dev: _check_env _mkdirs
	@echo "Starting ZWAN-CODEX-V2 (native mode)..."
	@cd backend && \
	  set -a && . ../.env && set +a && \
	  .venv/bin/uvicorn app.main:app \
	    --host 127.0.0.1 --port $(BPORT) --reload \
	    > ../$(LOG_DIR)/backend.log 2>&1 & echo $$! > ../$(PID_DIR)/backend.pid
	@cd backend && \
	  set -a && . ../.env && set +a && \
	  .venv/bin/python -m arq worker.tasks.WorkerSettings \
	    > ../$(LOG_DIR)/worker.log 2>&1 & echo $$! > ../$(PID_DIR)/worker.pid
	@cd frontend && \
	  NEXT_PUBLIC_API_URL=http://127.0.0.1:$(BPORT) \
	  NEXT_PUBLIC_WS_URL=ws://127.0.0.1:$(BPORT) \
	  pnpm dev --port $(FPORT) \
	    > ../$(LOG_DIR)/frontend.log 2>&1 & echo $$! > ../$(PID_DIR)/frontend.pid
	@sleep 3
	@echo ""
	@echo "  ✓ Backend  → http://127.0.0.1:$(BPORT)"
	@echo "  ✓ Frontend → http://127.0.0.1:$(FPORT)"
	@echo "  ✓ API docs → http://127.0.0.1:$(BPORT)/docs"
	@echo ""
	@echo "  Logs: make logs-backend | make logs-worker | make logs-frontend"
	@echo "  Stop: make stop"

stop:
	@echo "Stopping ZWAN-CODEX-V2..."
	@for svc in backend worker frontend; do \
	  if [ -f $(PID_DIR)/$$svc.pid ]; then \
	    PID=$$(cat $(PID_DIR)/$$svc.pid); \
	    if kill -0 $$PID 2>/dev/null; then \
	      kill $$PID && echo "  ✓ stopped $$svc (PID $$PID)"; \
	    else \
	      echo "  - $$svc not running"; \
	    fi; \
	    rm -f $(PID_DIR)/$$svc.pid; \
	  fi; \
	done
	@pkill -f "uvicorn app.main:app" 2>/dev/null || true
	@pkill -f "arq worker.tasks.WorkerSettings" 2>/dev/null || true
	@pkill -f "pnpm dev --port $(FPORT)" 2>/dev/null || true
	@echo "Done."

restart: stop
	@sleep 1
	@$(MAKE) dev

status:
	@echo "Service status:"
	@curl -sf http://127.0.0.1:$(BPORT)/health > /dev/null 2>&1 \
	  && echo "  ✓ backend  UP  (http://127.0.0.1:$(BPORT))" \
	  || echo "  ✗ backend  DOWN"
	@curl -sf http://127.0.0.1:$(FPORT)/ > /dev/null 2>&1 \
	  && echo "  ✓ frontend UP  (http://127.0.0.1:$(FPORT))" \
	  || echo "  ✗ frontend DOWN"
	@[ -f $(PID_DIR)/worker.pid ] && kill -0 $$(cat $(PID_DIR)/worker.pid) 2>/dev/null \
	  && echo "  ✓ worker   UP" \
	  || echo "  ✗ worker   DOWN"

logs-backend:
	@tail -f $(LOG_DIR)/backend.log

logs-worker:
	@tail -f $(LOG_DIR)/worker.log

logs-frontend:
	@tail -f $(LOG_DIR)/frontend.log

# ── Docker Compose mode ───────────────────────────────────────────────────────

up: _check_env
	$(COMPOSE) up -d --build
	@echo ""
	@echo "  Backend:  http://127.0.0.1:$(BPORT)"
	@echo "  Frontend: http://127.0.0.1:$(FPORT)"

down:
	$(COMPOSE) down

purge:
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f $(s)

migrate:
	@cd backend && set -a && . ../.env && set +a && .venv/bin/alembic upgrade head

seed:
	@cd backend && set -a && . ../.env && set +a && .venv/bin/python -m app.db.seed

test:
	@cd backend && set -a && . ../.env && set +a && .venv/bin/pytest tests/ -v

lint:
	@cd backend && .venv/bin/ruff check app/ && .venv/bin/mypy app/

fmt:
	@cd backend && .venv/bin/ruff format app/

shell:
	$(COMPOSE) exec $${s:-backend} bash

# ── Helpers ───────────────────────────────────────────────────────────────────

_check_env:
	@[ -f .env ] || (cp .env.example .env && echo "⚠  Created .env — fill in ANTHROPIC_API_KEY and POSTGRES_PASSWORD" && exit 1)

_mkdirs:
	@mkdir -p $(PID_DIR) $(LOG_DIR)

help:
	@echo ""
	@echo "ZWAN-CODEX-V2  ─  bug bounty agentic platform"
	@echo ""
	@echo "  NATIVE DEV (fastest):"
	@echo "    make dev       start backend + worker + frontend"
	@echo "    make stop      stop everything"
	@echo "    make restart   stop then start"
	@echo "    make status    check what's running"
	@echo ""
	@echo "  LOGS:"
	@echo "    make logs-backend"
	@echo "    make logs-worker"
	@echo "    make logs-frontend"
	@echo ""
	@echo "  DOCKER:"
	@echo "    make up        docker compose up"
	@echo "    make down      docker compose down"
	@echo "    make purge     down + delete volumes"
	@echo ""
	@echo "  DEV:"
	@echo "    make migrate   run alembic migrations"
	@echo "    make test      pytest"
	@echo "    make lint      ruff + mypy"
