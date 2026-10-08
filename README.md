# BeanChat / LedgerSage

BeanChat turns natural-language messages into auditable Beancount entries. It supports multiple users, one isolated git-backed ledger per user, clarifying questions, fixed read-only query tools, budgets, live decision traces, dashboards, and run history.

Ledger files remain the only source of truth for financial data. SQLite stores users, sessions, LangGraph checkpoints, and decision traces.

## Run locally

Python 3.12+ and Node 20+ are required.

```bash
cp .env.example .env
# Fill every required secret in .env.
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cd web && npm install && npm run build && cd ..
.venv/bin/python -m beanbot serve
```

Open <http://localhost:8000>. Create more invitation codes with `.venv/bin/python -m beanbot invite --count 3`.

Configuration comes only from environment variables. `JWT_SECRET`, `INVITE_CODE`, `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` are required; startup fails with the missing field names. See `.env.example` for optional embedding settings.

## Architecture

- `beanbot/api/`: FastAPI routes, authentication, SSE, dashboard, and run history.
- `beanbot/services/agent/`: LangGraph classify/extract/ask/tool/reply graph and fixed query tools.
- `beanbot/gateways/ledger.py`: per-user Beancount loading, append-only writes, git commits, and undo.
- `beanbot/storage/`: versioned SQLite business schema. LangGraph checkpoint tables share the database.
- `beanbot/services/vector_index.py`: per-user incremental vector indexes.
- `web/`: React, Vite, and TypeScript client. `frontend/index.html` remains the visual reference.

Every ledger write takes an in-process lock, appends canonical text, stages only the target file, and creates one git commit. Run Uvicorn with exactly one worker. Multiple workers do not share these locks and can lose concurrent writes.

## Tests

```bash
.venv/bin/python -m pytest
.venv/bin/python -m mypy beanbot
cd web && npm run build
```

The test suite uses no API key. The opt-in real-model classification evaluation is `python -m tests.eval.classify`.

## Docker

Run `docker compose up --build` after creating `.env`. The image builds the React client, includes git, and runs one Uvicorn worker. `beanchat-ledgers` is the financial source-of-truth volume; arrange an external backup before production use. A backup transport is intentionally not selected yet.

For legacy account comments, run `python -m beanbot migrate-account-names /path/to/ledger` to preview display-name changes. Supply `--names names.json` for approved manual names (an account-to-name mapping). After reviewing the names and committing existing ledger changes, add `--apply` to migrate, validate, and create a separate ledger commit. Existing display names are preserved; validation failure restores the original files.
