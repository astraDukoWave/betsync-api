# Scaling Strategy

This document proposes a phased scaling plan for BetSync API based on the current monolith architecture: FastAPI for synchronous request handling, PostgreSQL for system-of-record writes, Redis for both cache and Celery transport, and a single Celery worker for the async betting pipeline.[^current-arch]

## Current bottlenecks identified

1. **Dashboard reads become expensive as pick volume grows.**
   `dashboard_service.get_summary()` issues multiple aggregate queries (`count`, status counts, sums, averages, streak lookup) per cache miss, so a single uncached dashboard request fans out into several database round trips.[^dashboard]
2. **Cache invalidation is O(N) and uses Redis `KEYS`.**
   Every pick create/update invalidates dashboard cache by scanning `dashboard:summary:*`, which is acceptable at low scale but becomes a blocking Redis anti-pattern with a large keyspace.[^cache]
3. **The async pipeline is serialized behind one queue/worker shape and stores transient status in Redis only.**
   Pipeline runs are enqueued onto a single `pipeline` queue, with job state saved as Redis keys that expire after 24 hours.[^pipeline-router][^worker]
4. **Pipeline writes are row-by-row and re-query shared reference data.**
   The runner inserts picks and parlays in loops and repeatedly resolves defaults, which will amplify write bursts as more matches and sportsbook data are processed per run.[^runner]
5. **External odds ingestion depends on one upstream API with request/retry overhead inside each job.**
   The pipeline performs synchronous HTTP calls with retries against The Odds API, so upstream rate limits or latency directly elongate job runtime and backlog growth.[^odds]
6. **The database topology is single-primary only.**
   The app uses one PostgreSQL instance with a moderate async pool and one sync engine for workers; there are no read replicas, partitioning, or workload isolation mechanisms yet.[^db]
7. **Redis currently carries three responsibilities.**
   Redis is used for API caching, Celery broker, and Celery result/job state, so cache churn and queue pressure can compete for the same infrastructure footprint.[^compose]

These bottlenecks can be addressed while staying monolithic through all three phases; microservices are unnecessary unless organizational boundaries or independently scaled product domains emerge later.

## Phase 1 (0–1k users)

### Architecture changes
- Keep the **modular monolith**: one FastAPI deployment plus one Celery worker deployment.
- Run the API behind a load balancer with **2–3 stateless API instances** to absorb read-heavy traffic spikes.
- Separate runtime concerns operationally, not architecturally:
  - API pods/containers for synchronous requests.
  - Worker pods/containers for pipeline jobs.
  - Managed PostgreSQL and managed Redis if possible.
- Add **basic observability** now: request latency, cache hit rate, DB query timings, queue depth, pipeline duration, odds API latency, and 429/5xx upstream error rates.
- Introduce **rate limiting and concurrency caps** on `POST /pipeline/run` so manual retries cannot create bursty background load beyond the current idempotency guard.

### DB strategy
- Stay on a **single PostgreSQL primary**.
- Add or verify indexes for the hottest filters and ordering paths used by dashboard and pick listing queries, especially on:
  - `picks(run_date)`
  - `picks(status, resolved_at)`
  - `picks(source, status)`
  - `picks(match_id)`
  - optional composite indexes for the most common dashboard filters.
- Replace repeated live aggregates for common dashboards with a **small summary table or materialized view** refreshed by the pipeline and pick result updates. This is the biggest DB win in the first phase because it removes the many-query fan-out on cache misses.
- Tune connection pools conservatively; the app pool is already fixed-size, so keep API and worker concurrency aligned with database capacity rather than simply increasing worker count.[^db]

### Caching strategy
- Keep **Redis cache-aside**, but change invalidation from global `KEYS` deletion to **versioned namespaces** or **targeted key registries** so writes remain O(1) or O(log N) instead of scanning all dashboard keys.[^cache]
- Cache the most requested dashboard payloads and config lookups.
- Use **stale-while-revalidate semantics** for read-heavy dashboard endpoints: serve slightly stale summaries for a short window while asynchronously refreshing them.
- Split Redis logically at minimum by deployment role:
  - cache Redis/database
  - queue/result Redis/database
  This avoids queue traffic evicting hot cache entries.

### Async processing changes
- Keep Celery and a **single queue**, but run **multiple worker processes** for headroom if jobs are independent.
- Persist job metadata in PostgreSQL for audit/history if job visibility longer than 24h matters; Redis can remain the fast status cache.[^pipeline-router][^worker]
- Add **upstream request budget controls**:
  - one in-flight odds sync per sport/date
  - exponential backoff with jitter
  - circuit breaker/degraded mode when the odds provider is unhealthy.
- Precompute and store reusable upstream payload snapshots per run so retries or forced reruns do not repeatedly hit the external API when source data has not changed.

## Phase 2 (1k–10k users)

### Architecture changes
- Continue with the monolith, but scale it into **independently deployable workloads**:
  - horizontally scaled API deployment
  - dedicated worker deployment for pipeline jobs
  - optional dedicated beat/scheduler process if recurring runs are added.
- Put the API behind an **ingress/load balancer + autoscaling** based on CPU and latency.
- Add **read/write workload isolation inside the monolith**:
  - API reads preferentially use replicas for safe endpoints.
  - writes and transactional updates stay on primary.
- Introduce a **workflow coordinator inside the monolith** for pipeline steps if needed, but do not break out services yet.

### DB strategy
- Add at least **one PostgreSQL read replica** for dashboard, config, and suggestions reads.
- Move from raw live aggregations toward **incremental rollups**:
  - daily pick performance table
  - per-sport/per-market aggregates
  - current streak snapshot
- Partition high-growth tables such as `picks` by `run_date` or month once row counts justify it, mainly to keep vacuum/index maintenance predictable and historical scans cheaper.
- Use **bulk inserts/upserts** in the pipeline instead of ORM row-by-row adds for picks and parlays.[^runner]
- Add query observability (`pg_stat_statements`, slow-query thresholds) and capacity SLOs for primary vs replica lag.

### Caching strategy
- Move to a **two-layer cache** for hottest reads:
  - short in-process cache for ultra-hot config/reference reads
  - Redis for cross-instance shared dashboards and suggestion lists.
- Pre-warm common dashboard keys after pipeline completion or major write bursts.
- Add **negative caching** or short-TTL empty-result caching for endpoints frequently queried before data lands.
- Enforce cache key cardinality controls for heavily filtered dashboard requests; not every arbitrary filter combination should be cached indefinitely.

### Async processing changes
- Split Celery workloads into **at least two queues** inside the monolith:
  - `pipeline-ingest` for external odds fetch/snapshot
  - `pipeline-compute` for scoring, pick generation, and parlay generation.
  This is justified because upstream I/O latency and internal compute have different scaling characteristics, but it does not require microservices.
- Add **job deduplication by natural key** (`sport + run_date + market scope`) rather than only by a per-day Redis flag, so forced reruns can still avoid redundant sub-steps.
- Save raw odds snapshots in PostgreSQL/object storage for replay, debugging, and reprocessing without re-calling the provider.
- Introduce **dead-letter handling** for repeated upstream failures and alerts on backlog age, retry count, and time-to-completion.

## Phase 3 (10k–100k users)

### Architecture changes
- Keep the product as a monolith unless one of these becomes true:
  1. the pipeline must scale on a drastically different reliability envelope than the API,
  2. a separate team owns ingestion/analytics independently,
  3. external partner integrations create isolated compliance or blast-radius needs.
- The recommended shape at this stage is still a **scaled monolith with separated runtime planes**:
  - API plane for user reads/writes
  - worker plane for async processing
  - analytics/rollup plane for scheduled data prep.
- Add **regional edge caching/CDN** only for safe GET endpoints if user geography broadens.
- Use **autoscaling policies tied to queue depth, DB saturation, and cache hit rate**, not only CPU.

### DB strategy
- Run PostgreSQL with **primary + multiple replicas**, with explicit routing for dashboard/analytics reads.
- Make rollups the primary source for dashboard endpoints; raw `picks` queries should become fallback/drill-down paths rather than powering every top-level metric.
- Partition `picks` and other append-heavy tables, archive cold partitions, and consider **time-series style retention tiers** for historical analytics.
- If analytics complexity keeps increasing, add a **separate analytical store or warehouse** fed asynchronously from PostgreSQL. This is preferable before microservices because it isolates heavy read analytics without fragmenting the write path.
- Use idempotent bulk loaders and batched status updates to absorb write bursts from major betting windows.

### Caching strategy
- Treat cache as a product feature with **tiered freshness classes**:
  - near-real-time (seconds) for job status and active suggestions
  - warm (1–5 min) for dashboards
  - cold/precomputed for historical analytics.
- Use **event-driven invalidation** from write paths and pipeline completion events instead of blanket cache clears.
- Introduce **request coalescing/single-flight** for expensive cache misses so dozens of identical dashboard misses do not stampede the database.
- Consider a dedicated Redis cluster or managed cache tier if queue and cache workloads are still sharing infrastructure.

### Async processing changes
- Formalize the pipeline as staged asynchronous work within Celery or an equivalent queue system:
  1. fetch external odds
  2. persist raw snapshot
  3. normalize/match to internal events
  4. score/generate picks
  5. generate parlays
  6. refresh rollups and cache pre-warm.
- Scale workers by queue type and add **backpressure** rules so upstream rate limits do not cause unbounded retries or DB write storms.
- Implement **provider-aware throttling**, quota forecasting, and fallback behaviors when the odds API is unavailable (reuse latest snapshot, mark suggestions stale, postpone recompute).
- If the external dependency becomes the dominant constraint, the first justified service split is **ingestion**, not the entire application. That split would only be warranted once the provider integration, replay logic, and rate-limited scheduling need an independent lifecycle.

## Recommended path

- **Immediately:** fix cache invalidation, add dashboard rollups, add indexes, and separate Redis cache from queue usage logically.
- **Next:** introduce read replicas, bulk pipeline writes, staged Celery queues, and persisted odds snapshots.
- **Later:** shift dashboards to precomputed aggregates, add partitioning, and only consider a service split around ingestion if scaling/operational data proves the monolith boundary is the bottleneck.

This path directly addresses the bottlenecks already visible in the codebase without introducing premature microservices.

[^current-arch]: See the current architecture and runtime topology in `README.md`.
[^dashboard]: `app/services/dashboard_service.py` performs multiple aggregate queries and only avoids them on Redis hits.
[^cache]: `app/services/cache_service.py` invalidates dashboard cache via Redis `KEYS`, and pick mutations call that invalidation path.
[^pipeline-router]: `app/routers/pipeline.py` uses Redis keys for per-job status plus a Redis idempotency key.
[^worker]: `app/worker/tasks.py` stores job state in Redis and executes the full pipeline in one Celery task.
[^runner]: `app/worker/pipeline/runner.py` loops through inserts and does the full ingestion/compute flow inline.
[^odds]: `app/worker/pipeline/odds_client.py` performs synchronous external API calls with retries.
[^db]: `app/core/database.py` shows the current single-primary engine/pool setup.
[^compose]: `docker-compose.yml` shows Redis serving as cache, broker, and result backend.
