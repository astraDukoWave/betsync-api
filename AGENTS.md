# AGENTS.md — Agent memory for betsync-api

## Learned User Preferences
- Prefer minimal, safe changes
- Always explain why before changing code
- For non-trivial changes, present plan/files/risks and wait for approval before editing
- Follow `docs/ai_agent_rules.md` in full
- Use only the current architecture (routers → services → models)

## Learned Workspace Facts
- Pick is the central entity and single source of truth (`models/pick.py`)
- All aggregation rules are locked in DECISION-001 (see `docs/ai_agent_rules.md`)
- No aggregates (SUM, COUNT, GROUP BY, etc.) on synchronous paths — use `agg_*` tables or Celery tasks instead
- The `services/` layer is required for all business logic (`pick_service.py`, `parlay_service.py`, etc.)
- Routers only handle FastAPI + schemas (never touch the DB directly)
- Prediction and odds pipeline lives in `app/worker/pipeline/` (idempotent and async)
- Cache-aside with Redis: always invalidate after Pick mutations
- Alembic migrations must be additive and safe for large datasets
- Financial flows use the ledger: balance-changing work runs under `SELECT FOR UPDATE` on the user balance row; pick settlement and ledger lines commit in the same DB transaction; outbox rows carry asynchronous side effects
- Aggregate consistency is guarded end-to-end: per-day recomputation runs in Celery with Redis lock/coalescing, and dashboard reads honor `USE_AGGREGATES_FOR_DASHBOARD` with runtime overrides plus controlled fallback when `agg_*` rows are stale/inconsistent
- Reconciliation admin surface is secret-gated via `X-Reconciliation-Secret` / `ADMIN_RECONCILIATION_SECRET`
- Always use UUID primary keys and timezone-aware timestamps