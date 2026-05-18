# ZWAN-CODEX V2

Agentic bug bounty platform. Input: scope URLs. Output: submission-ready findings that survive a senior triager.

**Valid rate goal: >60%** (BBS current: ~17%)

---

## Quick start

```bash
cp .env.example .env
# Fill in: POSTGRES_PASSWORD, ANTHROPIC_API_KEY, FERNET_KEY
# Generate FERNET_KEY: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

make up
```

- Backend: http://127.0.0.1:8731
- Frontend: http://127.0.0.1:3000
- mitmweb: http://127.0.0.1:8081

---

## Architecture

| Service | Role |
|---|---|
| `backend` | FastAPI + agent runtime |
| `worker` | Arq async task queue (Redis-backed) |
| `postgres` | Findings, engagements, assets, secrets |
| `redis` | Queue + WebSocket pubsub |
| `qdrant` | Vector DB for duplicate detection |
| `proxy` | mitmproxy traffic capture |
| `frontend` | Next.js 15 dashboard |

## Agents (10 total)

| Agent | Milestone | What it does |
|---|---|---|
| `recon` | M2 | subfinder + httpx + crt.sh subdomain/host enumeration |
| `js_miner` | M2 | JS bundle fetch, source map detection, LLM secret/endpoint extraction |
| `oauth_chain` | M3 | Dynamic registration, PKCE strip, redirect_uri bypass |
| `desync` | M3 | CL.0 / CL.TE HTTP request smuggling |
| `race` | M3 | Race condition candidates + Turbo Intruder script generation |
| `ssrf` | M3 | PDF/webhook/image SSRF probing with Interactsh OAST |
| `agentic_target` | M3 | LLM feature detection + prompt injection testing |
| `chain_hunter` | M4 | Cross-finding chain detection (3–10x payout multiplier) |
| `validator` | M4 | **THE GATE** — adversarial review, auto-kill, duplicate check |
| `report` | M5 | Submission-ready markdown in Mohamed's voice |

## Make targets

```bash
make up          # bring stack online
make down        # stop (keep volumes)
make purge       # stop + delete volumes
make migrate     # run alembic migrations
make logs        # tail all logs
make test        # pytest
make lint        # ruff + mypy
make shell       # bash into backend
```

## Workflow

1. Open http://127.0.0.1:3000/engagements/new
2. Paste scope URLs, set platform, set budget
3. Click **Start hunt**
4. Watch agent trace stream live
5. Findings appear as ValidatorAgent passes them
6. Click any finding → copy submission-ready report

## Anti-patterns (enforced)

- No Streamlit/Gradio — Next.js only
- No LangChain — Pydantic-AI + manual ReAct
- No auto-submit — Mohamed reviews manually
- No generic OWASP checks — Tier S only
- No hardcoded prompts — all in `backend/app/prompts/*.md`
- No plaintext API keys — Fernet-encrypted at rest
