# AI Agent Rules for BetSync API

These rules are mandatory for any AI agent or human using AI assistance to change this repository. They are written to be enforceable in code review and to protect the system's main bottleneck: the database.

## Core principle

**`Pick` is the central entity.** Every change that reads, writes, lists, aggregates, caches, or joins betting data must be reviewed from the perspective of its effect on `picks` table read volume, write amplification, and query shape.

---

## 1. DB rules

### Rule 1.1
**Rule:** Do not add a new table, column, foreign key, trigger, or index unless the change names the `Pick` access pattern it supports.

**Why:** The system is read-heavy and the database is the bottleneck. Schema growth without an explicit `Pick`-centric query need creates unused write overhead and encourages accidental joins.

**Bad example:**
- Add `pick_tags`, `tag_groups`, and `pick_tag_audit` because the feature "might need tags later."
- Add an index without naming the exact `WHERE`, `ORDER BY`, or join it serves.

**Good example:**
- Add a composite index on `picks (status, run_date, created_at)` and document that it supports `GET /picks` filtering by `pick_status` and `run_date` with newest-first ordering.

### Rule 1.2
**Rule:** Do not denormalize or duplicate `Pick` data into another persistent table unless the source of truth remains `picks` and the duplication is justified by a measured read-path need.

**Why:** Duplicate `Pick` state creates drift, doubles write cost, and makes result resolution harder to reason about.

**Bad example:**
- Store `pick_status`, `grade`, and `odds_decimal` again in a reporting table that is updated on every pick edit.

**Good example:**
- Keep `picks` as source of truth and cache dashboard responses in Redis instead of persisting duplicate summary rows when a short-lived cache solves the read problem.

### Rule 1.3
**Rule:** Every new foreign key to `picks` must answer two code-review questions: "What is the delete/update behavior?" and "How does this affect `Pick` read paths?"

**Why:** `Pick` is the hub of the domain model. Unchecked references increase join depth and can turn simple `Pick` reads into multi-table dependency chains.

**Bad example:**
- Add a table referencing `picks` without documenting cascade behavior or how it will be loaded.

**Good example:**
- Add a junction table only when the relationship is required by an API contract, keep the join narrow, and document how the linked rows will be queried.

### Rule 1.4
**Rule:** Migrations must be additive-first and safe on production-sized `picks` data.

**Why:** Long table rewrites or non-batched backfills on `picks` can block the hottest table in the system.

**Bad example:**
- Add a non-null column to `picks` with an expensive default that forces a full table rewrite in one migration.

**Good example:**
- Add the column nullable, backfill in a controlled step, then tighten the constraint in a later migration after data is populated.

### Rule 1.5
**Rule:** Do not move derived `Pick` fields out of server-side calculation unless the new location has a stronger consistency guarantee.

**Why:** `odds_decimal`, `implied_prob`, `grade`, and `clv` are derived from canonical inputs and should stay consistent for every read path.

**Bad example:**
- Let clients submit arbitrary `implied_prob` values and store them directly.

**Good example:**
- Continue deriving `Pick` computed fields in the service layer from canonical request fields and persisted odds values.

---

## 2. Query rules

### Rule 2.1
**Rule:** Every query that returns `Pick` rows must be bounded by explicit pagination or by a single-record lookup.

**Why:** Unbounded reads are the fastest way to overload the DB in a read-heavy system.

**Bad example:**
- Add a new endpoint or service method that returns all picks for a sport with no `limit` and no hard cap.

**Good example:**
- Require `limit`/`offset` or an equivalent cursor, keep a sane default, and preserve a maximum page size in schema validation or route logic.

### Rule 2.2
**Rule:** Do not introduce a query parameter unless there is a matching filter in the SQLAlchemy query or a deliberate reason it is rejected.

**Why:** Fake filters trick clients into broad scans while appearing selective in the API contract.

**Bad example:**
- Accept `sport_id` or `competition_id` on `/picks` but never join/filter on those fields in the underlying query.

**Good example:**
- Only expose filters that are actually applied in the query, or remove the parameter until the implementation is complete.

### Rule 2.3
**Rule:** Avoid joins from `picks` to additional tables unless the response contract requires fields from those tables right now.

**Why:** `Pick` is the central entity and every extra join multiplies DB work on the hottest read path.

**Bad example:**
- Join `matches`, `competitions`, and `sportsbooks` in the base list query "just in case" the frontend needs labels later.

**Good example:**
- Return core `Pick` fields from the list endpoint and fetch expanded related data only in endpoints that explicitly promise it.

### Rule 2.4
**Rule:** Use ORM loading intentionally; no lazy-loading behavior may be relied on inside loops over `Pick` rows.

**Why:** Loop-triggered queries create N+1 read explosions that are hard to notice in review and brutal in production.

**Bad example:**
- Iterate through picks and touch `pick.match`, `pick.sportsbook`, or `pick.parlay_picks` without eager-loading them.

**Good example:**
- Keep the query to one round trip when possible, or add explicit `selectinload`/targeted follow-up queries when related data is truly required.

### Rule 2.5
**Rule:** Count queries on `picks` must be justified and paired with the same filter set as the page query.

**Why:** A separate count is another DB hit; an inconsistent count also breaks client pagination.

**Bad example:**
- Add `total` to every read endpoint by default, even when the UI never uses it.

**Good example:**
- Only compute `total` where the response contract requires it, and keep the count query aligned with the exact applied filters.

### Rule 2.6
**Rule:** Never hide expensive `Pick` scans behind convenience helpers.

**Why:** Reviewers must be able to see query shape from the service code.

**Bad example:**
- Add `get_all_active_picks()` in a helper module that silently loads thousands of rows.

**Good example:**
- Keep query builders near the service method, with obvious filters, ordering, limits, and eager-loading decisions.

---

## 3. API rules

### Rule 3.1
**Rule:** New API endpoints must justify why an existing `Pick` endpoint cannot serve the use case.

**Why:** Extra endpoints usually become extra read patterns against the same hot data.

**Bad example:**
- Add `/picks/recent`, `/picks/latest`, and `/picks/by-date` as separate handlers that all query the same table differently.

**Good example:**
- Extend `GET /picks` only when the new filter/order is valid and efficient, or add a new endpoint only when the response contract is materially different.

### Rule 3.2
**Rule:** Read endpoints must return the smallest response that satisfies the contract; no speculative expansion of related objects.

**Why:** Over-fetching at the API layer creates avoidable DB work and larger payloads.

**Bad example:**
- Return full `match`, `competition`, `sport`, `sportsbook`, and `parlay` trees on every pick list response.

**Good example:**
- Return the `Pick` fields the client needs for the view, and defer expanded related reads to detail endpoints or explicitly separate responses.

### Rule 3.3
**Rule:** API writes that mutate `Pick` state must preserve existing server-side invariants before adding side effects.

**Why:** Pick correctness is more important than secondary features such as notifications or reporting.

**Bad example:**
- Resolve a pick and asynchronously compute canonical fields later.

**Good example:**
- Update `Pick` status and derived values inside the main service flow, then trigger secondary work after the core state is valid.

### Rule 3.4
**Rule:** Expensive aggregation or analytics must not be added to transactional `Pick` endpoints.

**Why:** Mixing OLTP reads/writes with dashboard-style aggregation on the same request path increases latency and DB contention.

**Bad example:**
- Make `POST /picks` also recalculate dashboard summaries synchronously from the database.

**Good example:**
- Keep transactional endpoints focused on the pick operation and use cache invalidation or separate read models for aggregate views.

### Rule 3.5
**Rule:** Any new filter, sort, or include option on a `Pick` endpoint must document the exact query change required to support it.

**Why:** API surface area is cheap to add but expensive to support on a bottlenecked DB.

**Bad example:**
- Add `sort_by=clv` to the schema without proving the query path and pagination remain safe.

**Good example:**
- Add the option only alongside the SQLAlchemy ordering, validation guardrails, and review notes on index/query impact.

---

## 4. Performance rules

### Rule 4.1
**Rule:** Cache read-heavy aggregate views before adding more database reads.

**Why:** The database is already the bottleneck, while Redis is designed to absorb repeated dashboard-style reads.

**Bad example:**
- Recompute dashboard summaries from PostgreSQL on every request because the query is "only a few joins."

**Good example:**
- Prefer cache-aside for repeated aggregate responses and invalidate cache on the `Pick` mutations that actually change those aggregates.

### Rule 4.2
**Rule:** Every PR that changes a `Pick` read path must state whether DB round trips increased, decreased, or stayed flat.

**Why:** This is simple to enforce in code review and catches hidden query explosions.

**Bad example:**
- Add relationship access in serializers without mentioning the extra SQL generated.

**Good example:**
- Note that the change keeps the list endpoint at two queries (count + page) or reduces it by removing an unnecessary lookup.

### Rule 4.3
**Rule:** Keep synchronous request paths free of external network calls and long-running computations when they already touch `picks`.

**Why:** Slow app-layer work increases concurrent DB pressure and ties up the hottest flows.

**Bad example:**
- Call an external odds provider inline while serving a pick write or list request.

**Good example:**
- Push slow enrichment to Celery or a separate pipeline path, and keep the API request centered on local validation plus DB work.

### Rule 4.4
**Rule:** Prefer invalidation over eager recomputation for data derived from `Pick` changes.

**Why:** Invalidation is cheap; recomputation on every write amplifies load on the bottlenecked DB.

**Bad example:**
- After every pick update, run all dashboard queries immediately and write new summary rows.

**Good example:**
- Invalidate the relevant cache key and let the next read rebuild the aggregate once.

### Rule 4.5
**Rule:** Do not add background jobs that scan the full `picks` table on a schedule unless the job is incremental by design.

**Why:** Periodic full scans compete directly with user-facing reads.

**Bad example:**
- Hourly task that regrades every historical pick whether it changed or not.

**Good example:**
- Process only picks changed since the last checkpoint, or trigger work from explicit mutations.

---

## 5. Anti-patterns

### Rule 5.1
**Rule:** Never approve "future-proofing" that widens `Pick` queries, schemas, or payloads without a current contract.

**Why:** Premature flexibility usually becomes permanent DB cost.

**Bad example:**
- "Let's include sportsbook, match, and competition on every pick response in case a future screen needs them."

**Good example:**
- Keep the response narrow today and add fields only when a real client requirement arrives.

### Rule 5.2
**Rule:** Never approve an endpoint or service that loads many `Pick` rows into Python just to filter, sort, or aggregate them in memory.

**Why:** The DB should do selective retrieval; Python-side post-processing wastes memory and network bandwidth.

**Bad example:**
- Fetch 10,000 picks, then filter by status and sort by `created_at` in Python.

**Good example:**
- Push filtering, ordering, limits, and counts into SQLAlchemy/PostgreSQL.

### Rule 5.3
**Rule:** Never accept hidden N+1 patterns in serializers, response builders, or background tasks.

**Why:** These are common AI-generated mistakes and are especially dangerous in a read-heavy system.

**Bad example:**
- Serialize each pick and separately query parlay membership per row.

**Good example:**
- Batch related reads or eager-load the exact relationship set once.

### Rule 5.4
**Rule:** Never add optional filters or sort orders that are not covered by tests or review notes describing query safety.

**Why:** "Optional" API features often become the heaviest production query.

**Bad example:**
- Merge a new `include_history=true` flag with no test coverage and no explanation of how many rows it can touch.

**Good example:**
- Add tests for the parameter behavior, document its limit/cap behavior, and describe its DB impact in the PR.

### Rule 5.5
**Rule:** Never bypass the service layer for `Pick` reads or writes in routers, tasks, or helpers.

**Why:** Centralizing `Pick` logic is the only realistic way to keep invariants and query discipline enforceable in review.

**Bad example:**
- Write ad-hoc `select(Pick)` statements directly inside a router because the endpoint is "small."

**Good example:**
- Route all `Pick` access through service functions where query shape, validation, and side effects can be reviewed consistently.

---

## Code review checklist

Reject the change if any answer below is unclear or negative:

1. Does the change name the exact `Pick` access pattern it introduces or modifies?
2. Does every `Pick` list/read path stay bounded by pagination, a hard cap, or a single-record lookup?
3. Are all query params on `Pick` endpoints actually enforced in SQLAlchemy?
4. Is related data loaded only when the response contract requires it?
5. Did DB round trips for the affected path stay flat or improve?
6. Did the change avoid new synchronous aggregations, full-table scans, and Python-side filtering of large `Pick` sets?
7. If caching changed, is invalidation tied to the `Pick` mutations that actually affect the cached view?
8. Is `picks` still the source of truth for `Pick` state and derived fields?
