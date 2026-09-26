# BeanChat repository guide

BeanChat is a multi-user conversational bookkeeping web app. Comments, docstrings, and user-facing text should normally be Chinese.

## Commands

```bash
.venv/bin/python -m pytest
.venv/bin/python -m mypy beanbot
cd web && npm run build
.venv/bin/python -m beanbot serve
```

The application reads environment variables through `beanbot/config.py`; never print or commit `.env` or the legacy ignored `config.yaml`.

`api` owns HTTP/auth/SSE behavior, `services/agent` owns LangGraph orchestration and deterministic routing, `gateways/ledger.py` owns all Beancount and git I/O, and `storage` owns non-financial SQLite records. Ledger files are the sole financial source of truth.

Repositories and vector indexes are resolved per user through factories. Never introduce a process-global ledger. Writes are append-only, stage one exact file, and run behind a per-ledger lock. The service must use one Uvicorn worker.

Tests live in top-level `tests/`; the real-LLM classification evaluator under `tests/eval/` is a manual tool and does not run in pytest. Specs and tickets live under `.scratch/`. Domain terms are in `CONTEXT.md`, and architecture decisions are in `docs/adr/`.
