# API Edge Cases — betsync-api

Documents the critical edge cases covered by validation in the service layer, Pydantic schemas, or at the DB level.

---

## Picks

### `odds_american` in range (-100, 100) is invalid
- **Endpoint:** `POST /picks`, `PATCH /picks/{id}`
- **Reason:** American odds of -99 to +99 don't exist in real bookmakers and would break `implied_prob = 1 / decimal`.
- **Response:** `422 VALIDATION_ERROR` — Pydantic `model_validator` on `PickCreate` / `PickUpdate`.
- **Frontend:** Validate client-side before submitting to avoid round-trip.

### DELETE pick that belongs to a parlay
- **Endpoint:** `DELETE /picks/{pick_id}`
- **Reason:** Deleting a pick inside an active parlay would leave the parlay with orphaned references.
- **Response:** `409 CONFLICT` — code `PICK_IN_PARLAY`
- **Decision:** Block the delete; user must dissolve or void the parlay first.

### DELETE pick that is already resolved
- **Endpoint:** `DELETE /picks/{pick_id}`
- **Reason:** Only pending picks can be soft-deleted (set to void).
- **Response:** `409 CONFLICT` — code `PICK_NOT_PENDING`

### Resolve pick with `status=pending`
- **Endpoint:** `PATCH /picks/{pick_id}/result`
- **Reason:** Resolving is only meaningful for non-pending statuses (won/lost/push/void).
- **Response:** `422 VALIDATION_ERROR` — Pydantic `model_validator` on `PickResolve` rejects `pending`.

### Resolve pick that already has a final status
- **Endpoint:** `PATCH /picks/{pick_id}/result`
- **Reason:** A pick can only be resolved once.
- **Response:** `409 CONFLICT` — code `PICK_ALREADY_RESOLVED`

### Edit pick that is already resolved
- **Endpoint:** `PATCH /picks/{pick_id}`
- **Reason:** Only pending picks can be edited.
- **Response:** `409 CONFLICT` — code `PICK_ALREADY_RESOLVED`

### Confirm a manually-created pick
- **Endpoint:** `PATCH /picks/{pick_id}/confirm`
- **Reason:** Only pipeline-sourced picks can be confirmed/discarded.
- **Response:** `400 BAD_REQUEST` — code `PICK_NOT_FROM_PIPELINE`

---

## Pipeline

### Pipeline already ran today
- **Endpoint:** `POST /pipeline/run`
- **Reason:** Idempotency guard — running twice the same day creates duplicate picks.
- **Response:** `409 CONFLICT` — code `PIPELINE_ALREADY_RAN`
- **Bypass:** Client can pass `"force": true` in request body to override.
- **Implementation:** Redis key `pipeline:ran:{date}` checked before enqueueing.

### Odds API is down / returns 5xx
- **Endpoint:** `POST /pipeline/run` (async side)
- **Reason:** External API failures should not silently skip picks.
- **Response:** `202 Accepted` immediately (job is async). Job status transitions to `"failed"`.
- **Implementation:** `tenacity` retries 3x with exponential backoff. After exhaustion, job status = `"failed"`, error stored in Redis.

### Odds API returns 429 (rate limit)
- **Same as above** — retried with backoff.
- **Logged:** `x-requests-remaining` header is logged to monitor quota.

---

## Parlays

### Two picks from the same match in one parlay
- **Endpoint:** `POST /parlays`
- **Reason:** Same-match correlation has no statistical value and inflates perceived parlay edge.
- **Response:** `400 BAD_REQUEST` — code `PARLAY_DUPLICATE_MATCH`
- **Validation:** Service layer checks `{pick.match_id}` uniqueness across all `pick_ids`.

### Parlay with fewer than 2 or more than 8 picks
- **Endpoint:** `POST /parlays`
- **Reason:** A single pick is not a parlay; more than 8 is impractical.
- **Response:** `422 VALIDATION_ERROR` — Pydantic `Field(min_length=2, max_length=8)` on `pick_ids`.

### Parlay with non-pending picks
- **Endpoint:** `POST /parlays`
- **Reason:** Only pending picks can be grouped into a parlay.
- **Response:** `400 BAD_REQUEST` — code `PICK_NOT_PENDING`

### Non-existent pick IDs in parlay
- **Endpoint:** `POST /parlays`
- **Reason:** One or more UUIDs don't correspond to existing picks.
- **Response:** `400 BAD_REQUEST` — code `PICKS_NOT_FOUND`

---

## Config

### `PATCH /config/{key}` with non-existent key
- **Endpoint:** `PATCH /config/{key}`
- **Response:** `404 NOT_FOUND` — code `CONFIG_NOT_FOUND`

---

## Sportsbooks

### Duplicate sportsbook name
- **Endpoint:** `POST /sportsbooks`
- **Response:** `409 CONFLICT` — code `SPORTSBOOK_EXISTS`

---

## Health & Degraded Mode

### `GET /health` when Redis is down
- **Response:** `200 OK` with `"status": "degraded"`, `"components": { "redis": "down" }`
- **Reason:** API still serves reads from PostgreSQL. Caching falls back to direct DB queries.
- **Decision:** Never return 503 on cache failure — picks registration must always work.

---

## `confirmed_at` vs `status` for pipeline picks

Pipeline-generated picks arrive with:
- `status = "pending"`
- `source = "pipeline"`
- `confirmed_at = null`

When the user confirms via `PATCH /picks/{pick_id}/confirm`:
- If `confirmed: true` → `confirmed_at = NOW()`, `status` remains `"pending"` (the match result doesn't exist yet)
- If `confirmed: false` → `status` changes to `"void"` (discarded)

This avoids ambiguity between *"awaiting user review"* and *"approved for betting"*
without adding a 5th enum value to `pick_status`.
