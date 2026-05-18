# ZWAN-CODEX-V2

## Local setup

### Prerequisites
- Docker and Docker Compose
- Python 3.12
- `pnpm`
- `.env` file with required secrets and database credentials

### Recommended (Docker Compose)

From the repository root:

```bash
cd /home/zwanski/ZWAN-CODEX-V2
docker compose up --build
```

This starts:
- `postgres` on `127.0.0.1:5432`
- `redis` on `127.0.0.1:6379`
- `qdrant` on `127.0.0.1:6333`
- backend on `http://127.0.0.1:8731`
- frontend on `http://127.0.0.1:3000`

### Manual development

#### Backend

```bash
cd /home/zwanski/ZWAN-CODEX-V2/backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
export $(grep -v '^#' ../.env | xargs)
uvicorn app.main:app --host 0.0.0.0 --port 8731 --reload
```

#### Worker

In another terminal:

```bash
cd /home/zwanski/ZWAN-CODEX-V2/backend
source .venv/bin/activate
export $(grep -v '^#' ../.env | xargs)
python -m arq worker.tasks.WorkerSettings
```

#### Frontend

```bash
cd /home/zwanski/ZWAN-CODEX-V2/frontend
pnpm install
pnpm dev
```

### Notes
- Backend requires Python `>=3.12`.
- Frontend uses `pnpm` and Next.js.
- Docker Compose is the easiest way to run the full stack together.
