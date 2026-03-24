# BetSync Scaling Strategy

> **Status:** LOCKED — Changes require Principal Architect sign-off and RFC process.
> **Last updated:** 2026-03-20

---

## Financial Integrity Rules (LOCKED)

These rules govern all monetary state in BetSync. They are **normative** for application and database design; exceptions require Principal Architect sign-off and an RFC.

1. **NO LEDGER, NO MONEY:** No mutation of economic value exists outside a **Ledger Entry**. Deposits, locks, releases, settlements, and corrections are expressed only as append-only ledger rows (plus explicit balance cache updates in the same transaction).

2. **SERIALIZED WRITES:** Every financial operation **must** begin with **`SELECT … FOR UPDATE`** on the user’s **`user_balances`** row (the lockable balance cache). No other row may be the primary serialization point for wallet mutations.

3. **ATOMIC TRANSACTIONS:** The domain fact (e.g. a **Pick**) and its accounting (**Ledger** row(s), balance cache update, **Outbox** event when used) **must** occur in the **same** database transaction.

4. **IMMUTABILITY:** **Ledger** rows are read-only after insert. Mistakes are corrected only via **Reversal** (or compensating) ledger entries, never by `UPDATE`/`DELETE` on original entries.

5. **SOURCE OF TRUTH:** The authoritative balance is the **sum of the Ledger** over time; **`available_balance` / `locked_balance`** on **`user_balances`** are a **lockable cache** maintained in lockstep with each ledger append. Application code **must not** compute or assert balances from ledger sums **without** holding **`FOR UPDATE`** on **`user_balances`** in the same transaction as any decision that depends on that balance.

**Corollary (operational):** Computing saldos in the application without **`FOR UPDATE`** on **`user_balances`** is **prohibited** for any path that authorizes or records a financial movement.

---

## Settlement Engine Rules (LOCKED)

Phase **6.2.1 v2** — single writer for terminal `Pick` transitions (`won`, `lost`, `push`, `void`). **No service or router may assign a terminal `Pick` status, `resolved_at`, or settlement fields except through** `app.services.settlement_engine.execute_settlement`.

### Contract

1. **Entry point:** `async def execute_settlement(db, pick_id, target_status: PickStatus, *, idempotency_key: str | None = None, closing_odds_decimal: Decimal | None = None)`.
2. **Deterministic lock order:** **`SELECT picks … FOR UPDATE` first** (serialization on the pick row). **`lock_and_get_balance` second** when the pick is financial (`user_id`, `stake > 0`). Balance work stays in the same DB transaction as the pick and ledger/outbox writes.
3. **State idempotency:** If `pick.status == target_status`, return success (**NO-OP**). If `pick.status` is already terminal and **not** equal to `target_status`, raise **`ConflictError("TERMINAL_STATE_CONFLICT")`**.
4. **Resolve over void:** Outcomes **`won` / `lost` / `push` take precedence over void.** If `target_status == void` and a **`PICK_PAYOUT`** or **`PICK_LOSS`** ledger row already exists for that `pick_id`, raise **`ConflictError("SETTLEMENT_ALREADY_DECIDED")`** (void cannot override a resolved monetary outcome).
5. **Race / uniqueness:** On PostgreSQL **unique violation** (`23505`) during the settlement transaction (e.g. concurrent ledger or outbox dedupe), raise **`ConflictError("SETTLEMENT_RACE_CONDITION")`**.
6. **Callers:** `resolve_pick`, `delete_pick` (void), and `confirm_pick` (reject → void) delegate terminal transitions to `execute_settlement`. Unstaked “soft delete” remains a void transition **without** balance movement, still executed inside the engine.

**Note:** For settlement specifically, the pick row is the primary **ordering** lock; the balance row is still updated under **`FOR UPDATE`** in the same transaction before any wallet mutation, preserving financial invariants (§ Financial Integrity Rules).

---

## DECISION-001: Aggregation Strategy (LOCKED)

### Statement

All Dashboard endpoints and all fiscal/analytics endpoints SHALL read exclusively from **aggregation tables** (`agg_*`) maintained asynchronously by background workers.

Direct aggregate queries (`SUM`, `COUNT`, `AVG`, `GROUP BY`, window functions, or any scan that touches more than a single row by primary key) against the `picks` table — or any other transactional table — in the synchronous request path are **PROHIBITED**.

### Rationale

The `picks` table is the write-hot center of the domain. Aggregate reads against it in the request path create lock contention, unpredictable latency, and a coupling between user-facing SLAs and table growth. This decision eliminates that coupling permanently.

### Scope

| Path | Allowed Source | Prohibited Source |
|---|---|---|
| `GET /dashboard/*` | `agg_dashboard_summary`, `agg_daily_performance`, `agg_streak` | Any live query on `picks` |
| `GET /fiscal/*`, `GET /analytics/*` | `agg_fiscal_*`, `agg_roi_*` | Any live query on `picks` |
| `GET /picks` (list, detail) | `picks` table directly (bounded, paginated) | Aggregate subqueries or inline stats |
| Pipeline / Celery tasks | `picks` (for row-level insert/update) | N/A — workers own the write path |
| Aggregation workers | `picks` (read for computation) → write to `agg_*` | N/A — this IS the async compute path |

### Constraints

1. **Materialized Views are PROHIBITED on the critical path.** They are not used for Dashboard reads, fiscal reads, or any endpoint that serves user-facing traffic. Materialized Views cannot be refreshed transactionally, their refresh timing is opaque to the application, and they create invisible coupling between read latency and refresh scheduling. Use explicit `agg_*` tables with application-controlled write logic instead.

2. **Every `agg_*` table MUST have a defined update trigger.** Acceptable triggers: Celery task on pick mutation, pipeline completion signal, scheduled periodic recomputation. Unacceptable: manual refresh, ad-hoc scripts, `REFRESH MATERIALIZED VIEW`.

3. **Every `agg_*` table MUST define a staleness SLA.** The maximum acceptable age of the aggregated data must be documented in the table's Alembic migration docstring and enforced by monitoring. Example: `agg_dashboard_summary` staleness SLA = 60 seconds.

4. **Cache layers read from `agg_*`, never from `picks`.** Redis cache-aside for Dashboard endpoints must be backed by `agg_*` reads. A cache miss must hit `agg_*`, never fall through to a live aggregate on `picks`.

---

## Bottleneck Context

These are the known bottlenecks that motivated DECISION-001. They are preserved here for traceability.

1. **Dashboard reads are expensive at scale.** `dashboard_service.get_summary()` issues multiple aggregate queries (`COUNT`, status counts, `SUM`, `AVG`, streak lookup) per cache miss — several DB round trips against `picks` on a single uncached request.[^dashboard]
2. **Cache invalidation uses Redis `KEYS`.** Every pick create/update invalidates dashboard cache by scanning `dashboard:summary:*` — an O(N) blocking anti-pattern that degrades with keyspace growth.[^cache]
3. **The async pipeline is serialized.** Pipeline runs use a single queue with transient Redis-only state expiring after 24h.[^pipeline-router][^worker]
4. **Pipeline writes are row-by-row.** The runner inserts picks/parlays in loops and re-resolves defaults per row.[^runner]
5. **External odds ingestion is synchronous and retry-heavy.** HTTP calls with retries against The Odds API inside each job — upstream latency directly extends job runtime.[^odds]
6. **Single-primary PostgreSQL topology.** No read replicas, no partitioning, no workload isolation.[^db]
7. **Redis carries three workloads.** API cache, Celery broker, and Celery result/job state compete for the same instance.[^compose]

---

## Transition Plan

The transition from live aggregates to `agg_*` tables follows four mandatory phases. No phase may be skipped. Each phase has explicit entry criteria, exit criteria, and a rollback path.

### Phase 1: Shadow Aggregates

**Objective:** Deploy `agg_*` tables and populate them asynchronously without changing any read path.

**Entry criteria:**
- DECISION-001 is ratified (this document).
- Alembic migrations for all initial `agg_*` tables are merged and applied.
- Celery tasks that compute and write aggregations are deployed.

**Work:**
1. Create `agg_dashboard_summary`, `agg_daily_performance`, `agg_streak`, and any fiscal aggregation tables required by current endpoints.
2. Each table includes: computed columns, `updated_at` timestamp, and a `computation_version` integer for schema evolution.
3. Deploy Celery tasks that recompute `agg_*` rows on pick mutation signals and on pipeline completion.
4. Add monitoring: aggregation task success rate, latency, and `updated_at` freshness per table.
5. **No read path changes.** Dashboard and fiscal endpoints continue reading from `picks` via live queries.

**Exit criteria:**
- `agg_*` tables are populated and updated continuously for >= 7 days in production.
- Aggregation task error rate < 0.1%.
- `updated_at` freshness meets the defined staleness SLA for each table.

**Rollback:** Drop `agg_*` tables. No user-facing impact.

---

### Phase 2: Dual-Read Validation (Internal Logs)

**Objective:** Read from both `agg_*` and live queries in parallel, compare results, and log discrepancies — without exposing `agg_*` data to users.

**Entry criteria:**
- Phase 1 exit criteria met.

**Work:**
1. Modify Dashboard and fiscal service methods to perform both reads: the existing live query (served to the user) and an `agg_*` read (logged, never returned).
2. Compare results and log deltas with structured fields: `endpoint`, `user_id`, `live_value`, `agg_value`, `delta`, `agg_updated_at`, `timestamp`.
3. Set up alerts on delta thresholds. Acceptable drift tolerance per metric must be defined before entering this phase (e.g., total count delta <= 1, ROI delta <= 0.01%).
4. **The live query remains the source of truth for all responses.** `agg_*` data is internal-only during this phase.

**Exit criteria:**
- Dual-read deployed for >= 14 days in production.
- Delta alerts are configured and operational.
- Observed delta rate is below the defined tolerance for every metric for >= 7 consecutive days.
- No aggregation task failures that caused stale data beyond the staleness SLA during the observation window.

**Rollback:** Remove the dual-read code path. Service reverts to live-query-only. No user-facing impact.

---

### Phase 3: Full Cutover

**Objective:** Switch all Dashboard and fiscal endpoints to read exclusively from `agg_*` tables. Live aggregate queries on `picks` are removed from the request path.

**Entry criteria:**
- Phase 2 exit criteria met.
- Sign-off from Principal Architect confirming dual-read validation data is satisfactory.

**Work:**
1. Update Dashboard and fiscal service methods to read from `agg_*` tables only.
2. Remove all live aggregate queries (`SUM`, `COUNT`, `AVG`, `GROUP BY`) on `picks` from the synchronous request path.
3. Update Redis cache-aside to back cache misses with `agg_*` reads.
4. Replace Redis `KEYS`-based invalidation with targeted key deletion or versioned namespaces (O(1) per invalidation).
5. Deploy and monitor. Track: endpoint latency p50/p95/p99, `agg_*` freshness, cache hit rate, DB query count per request.

**Exit criteria:**
- All Dashboard and fiscal endpoints serve data from `agg_*` exclusively for >= 14 days.
- No live aggregate query on `picks` exists in the request path (verified by code audit and query log analysis).
- Endpoint latency p95 is improved or unchanged compared to pre-cutover baseline.
- No user-reported data discrepancy attributable to aggregation staleness.

**Rollback:** Revert service methods to live queries (Phase 2 dual-read code can be re-enabled as an intermediate step). Cache invalidation reverts to previous strategy.

---

### Phase 4: Cleanup

**Objective:** Remove all dead code, legacy query paths, and transitional infrastructure.

**Entry criteria:**
- Phase 3 exit criteria met.
- >= 30 days since full cutover with no rollback.

**Work:**
1. Delete all legacy live aggregate query code from Dashboard and fiscal services.
2. Remove dual-read comparison logic and logging infrastructure.
3. Remove any temporary flags, feature toggles, or environment variables used during the transition.
4. Update `docs/ai_agent_rules.md` to reference `agg_*` tables as the canonical read source for aggregated data.
5. Archive this transition plan section as completed.

**Exit criteria:**
- No reference to live aggregate queries on `picks` in the request path exists in the codebase.
- CI passes. All tests updated to reflect `agg_*`-backed reads.

**Rollback:** Not applicable. Phase 4 is cosmetic cleanup after proven stability.

---

## Runtime Safeguards

These rules apply to the dashboard (and similar) aggregate read path before stress testing and in production. They complement DECISION-001 by constraining **when** `agg_pick_daily` (and peers) may be trusted for a response.

### Staleness by `min(updated_at)` (weakest link)

For a requested date range, load all `agg_pick_daily` rows covering that range. Freshness is **not** the newest row in the range; it is the **oldest** `updated_at` among those rows (`min(updated_at)`). If `now - min(updated_at)` exceeds the staleness SLA (10 minutes for `agg_pick_daily` in the current implementation), the handler must **not** serve totals from aggregates for that request: abort aggregate use and fall back to the RAW `picks` path for that summary.

Rationale: one stale day in the window poisons blended KPIs; `max(updated_at)` would hide a lagging day.

### Internal consistency (status partition)

Each `agg_pick_daily` row must satisfy:

`pick_count == won_count + lost_count + push_count + pending_count + void_count`

(`void_count` is required so the identity partitions every `PickStatus`.) If **any** row in the requested range fails this check, abort aggregate reads for that request and fall back entirely to RAW. Do not partially blend agg and raw.

### Circuit breaker after aggregate fallback (throttled cache pressure)

When a request falls back to RAW because aggregate validation failed (staleness, missing days, or internal inconsistency), set Redis key `agg_fail_circuit_open` with a **60 second** TTL. While that key exists:

- Do **not** query `agg_pick_daily` for dashboard summary (use RAW immediately).
- Do **not** perform per-request cache invalidation tied to that fallback loop (avoid amplifying Redis/DB load into an auto–DDoS pattern).

After TTL expiry, normal aggregate reads may resume so workers can catch up without permanent deadlock.

---

## Domain Integrity Rules

These rules apply to **all** `Pick` persistence paths (REST services **and** the synchronous pipeline worker). Invalid monetary state must be rejected **before** `flush`/`commit` so the database never becomes the system of record for inconsistent ledger data.

### Financial invariants

1. **Positive stake when present:** If `stake` is not `NULL`, it MUST be strictly greater than zero.
2. **Settlement consistency:** For statuses `won`, `lost`, and `push`, `profit` MUST match the implied value from `(stake, odds_decimal)` within a configurable business tolerance (`PICK_PROFIT_TOLERANCE`, default `0.02` currency units). Exact floating equality is NOT required.
3. **`void` profit:** `void` picks MUST have `profit = 0` exactly (not `NULL`).
4. **`pending` settlement:** `pending` picks MUST NOT carry a definitive `profit` or `settled_return` (both `NULL`).

### Lifecycle and immutability

1. **Terminal statuses:** `won`, `lost`, `push`, and `void` are terminal. Status MUST NOT change after resolution.
2. **No retroactive price edits:** After resolution, `stake`, `odds_american`, `odds_decimal`, and `market` MUST NOT change.
3. **Valid transitions:** From `pending`, only transitions to `won`, `lost`, `push`, or `void` are allowed (e.g. never `won` → `pending`).

### RAW path as last resort

Aggregate reads may fall back to RAW `picks` when runtime safeguards fire (see above). Domain validation is independent: even when reads use RAW, **writes** still pass through the same `DomainValidator` so invalid money never lands in `picks`.

---

## API Integrity Rules

These rules define the **public HTTP contract** for pick writes and complement `DomainValidator` (domain layer).

1. **`extra="forbid"` on input schemas:** `PickCreate` and `PickUpdate` use Pydantic `model_config = ConfigDict(extra="forbid")`. Any field not declared on the schema — including system-controlled attributes such as `profit`, `settled_return`, or `odds_decimal` on create — MUST be rejected with **422** (no silent stripping).

2. **Atomic idempotency for `POST /api/v1/picks/`:** When the client sends `Idempotency-Key`, the API acquires a short-lived exclusive lock in Redis via **`SET` with `NX`**, stores `"processing"` with a brief TTL, and after a **successful DB commit** persists the response JSON plus HTTP status under the same key for **30 minutes** (`IDEMPOTENCY_RESULT_TTL_SECONDS`, overridable via env). Concurrent retries: if the key still holds `"processing"`, respond **409**; if the key holds a completed payload, replay that response; if the same key is reused with a different canonical body fingerprint, respond **409** (`IDEMPOTENCY_BODY_MISMATCH`). Requests **without** `Idempotency-Key` are processed normally (no Redis deduplication).

3. **Temporal invariants (UTC):** All persisted pick timestamps exposed to validation (`created_at`, `updated_at`, `resolved_at`, `confirmed_at` when set) MUST be timezone-aware with **UTC offset zero**. `resolved_at` MUST be `>= created_at`. **Terminal** statuses (`won`, `lost`, `push`, `void`) MUST have `resolved_at` set; **`pending`** MUST have `resolved_at` NULL. Once `resolved_at` is set, **`stake`**, **odds** (American and decimal), and **`market`** MUST NOT change.

---

## External Dependency Resilience

The Odds API client (`app/worker/pipeline/odds_client.py`) MUST treat upstream failures as normal operating conditions.

### Retries

- Use **tenacity** with **exponential backoff + jitter** (`wait_random_exponential`) for transient errors (connection/timeouts and retryable HTTP statuses including `429`, `5xx`).
- Non-retryable client errors (`401`, `422`) MUST fail fast without retry storms.

### Internal rate limiting

- Enforce a configurable maximum **requests per minute** (`ODDS_API_MAX_REQUESTS_PER_MINUTE`) via a minimum inter-request interval so the worker does not self-inflict `429` responses under load.

### Idempotency

- Successful `get_odds` responses MAY be cached in Redis under an **idempotency key** (e.g. hash of run date + sport + markets + regions) for a TTL (`ODDS_API_IDEMPOTENCY_TTL_SECONDS`). If the HTTP client appears to time out after the server already responded, a retry MUST reuse the same payload instead of implying duplicate downstream writes.

### Operational SLO signals

The following MUST be observable via structured logs and/or Redis counters (`OPERATIONAL_METRICS_ENABLED`):

| Signal | Meaning |
|--------|---------|
| `agg_hit_ratio` | Rolling ratio of dashboard summary requests served from `agg_pick_daily` vs raw computation (uncached path). |
| `fallback_ratio` | Rolling ratio of aggregate **fallback** events (staleness, inconsistency, circuit, or runtime raw toggle while aggregates were desired) vs total uncached summary reads. |
| `data_freshness_seconds` | When serving from aggregates: `now − min(updated_at)` across the requested `agg_pick_daily` rows (weakest link). |
| `external_api_success_rate` | Rolling success vs failure counts for Odds API calls (after retries exhausted). |

---

## Prohibited Patterns (Post-Cutover)

After Phase 3 completion, the following are permanently prohibited:

| Pattern | Status |
|---|---|
| `SELECT COUNT(*) FROM picks` in any endpoint handler or service called by an endpoint | **PROHIBITED** |
| `SELECT SUM(units) FROM picks` or any aggregate function on `picks` in the request path | **PROHIBITED** |
| `REFRESH MATERIALIZED VIEW` called by or blocking any user-facing request | **PROHIBITED** |
| Redis `KEYS` command in production code | **PROHIBITED** |
| Cache miss fallthrough that runs a live aggregate on `picks` | **PROHIBITED** |
| New Dashboard/fiscal metric without a corresponding `agg_*` column or table | **PROHIBITED** |

---

## References

[^dashboard]: `app/services/dashboard_service.py` — multiple aggregate queries per cache miss.
[^cache]: `app/services/cache_service.py` — `KEYS`-based invalidation on pick mutations.
[^pipeline-router]: `app/routers/pipeline.py` — Redis keys for per-job status and idempotency.
[^worker]: `app/worker/tasks.py` — job state in Redis, full pipeline in one Celery task.
[^runner]: `app/worker/pipeline/runner.py` — row-by-row inserts, inline ingestion/compute flow.
[^odds]: `app/worker/pipeline/odds_client.py` — synchronous external API calls with retries.
[^db]: `app/core/database.py` — single-primary engine/pool setup.
[^compose]: `docker-compose.yml` — Redis serving cache, broker, and result backend.
