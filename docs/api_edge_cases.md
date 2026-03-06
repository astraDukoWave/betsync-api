# API Edge Cases — betsync-api

Documents the critical edge cases from Paso 8 of the System Design.
Every case here is covered by validation in the service layer or at the DB level.

---

## Picks

### `odds_american` in range (-100, 100) is invalid
- **Endpoint:** `POST /picks`
- **Reason:** American odds of -99 to +99 don't exist in real bookmakers and would break `implied_prob = 1 / decimal`.
- **Response:** `400 BAD_REQUEST` — code `PICK_INVALID_ODDS`
- **Validation:** Pydantic `model_validator` on `PickCreate`.

### DELETE pick that belongs to a parlay
- **Endpoint:** `DELETE /picks/{pick_id}`
- **Reason:** Deleting a pick inside an active parlay would leave the parlay with orphaned references.
- **Response:** `409 CONFLICT` — code `PICK_IN_ACTIVE_PARLAY`
- **Decision:** Block the delete; user must dissolve or void the parlay first.

### Resolve pick with `status=pending`
- **Endpoint:** `PATCH /picks/{pick_id}/result`
- **Reason:** Resolving is only meaningful for non-pending statuses (won/lost/push/void).
- **Response:** `400 BAD_REQUEST` — code `PICK_INVALID_STATUS`
- **Validation:** `PickResolve.status` rejects `pending` explicitly.

---

## Pipeline

### Pipeline already ran today
- **Endpoint:** `POST /pipeline/run`
- **Reason:** Idempotency guard — running twice the same day creates duplicate picks.
- **Response:** `409 CONFLICT` — code `PIPELINE_ALREADY_RAN`
- **Bypass:** Client can pass `force=true` to override.
- **Implementation:** Redis key `pipeline:ran:{date}` checked before enqueueing.

### Odds API is down / returns 5xx
- **Endpoint:** `POST /pipeline/run` (async side)
- **Reason:** External API failures should not silently skip picks.
- **Response:** `202 Accepted` immediately (job is async). Job status transitions to `failed`.
- **Implementation:** `tenacity` retries 3x with exponential backoff. After exhaustion, job status = `failed`, error stored in Redis.

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

### Parlay with fewer than 2 picks
- **Endpoint:** `POST /parlays`
- **Reason:** A single pick is not a parlay.
- **Response:** `422 Unprocessable Entity` (Pydantic) — `pickids` field has `min_length=2`.

---

## Config

### `PATCH /config/{key}` with value outside expected range
- **Endpoint:** `PATCH /config/{key}`
- **Reason:** Setting `min_implied_prob_class_a=2.0` would classify no picks ever; setting it to `-0.5` would classify all picks.
- **Response:** `400 BAD_REQUEST` — code `CONFIG_VALUE_INVALID`
- **Implementation:** `ConfigService.validate_value(key, value)` checks type and range per key.

---

## Health & Degraded Mode

### `GET /health` when Redis is down
- **Response:** `200 OK` with `status: degraded`, `redis: false`
- **Reason:** API still serves reads from PostgreSQL. Caching falls back to direct DB queries.
- **Decision:** Never return 503 on cache failure — picks registration must always work.

### `GET /health` when PostgreSQL is down
- **Response:** `503 Service Unavailable`
- **Reason:** Without the DB the API cannot serve any meaningful response.

---

## `confirmed_at` vs `status` for pipeline picks

Pipeline-generated picks arrive with:
- `status = pending`
- `source = pipeline`
- `confirmed_at = NULL`

When the user confirms via `PATCH /picks/{pick_id}/confirm`:
- `confirmed_at = NOW()` is set
- `status` remains `pending` (the result doesn't exist yet)

This avoids ambiguity between *"awaiting user review"* and *"approved for betting"*
without adding a 5th enum value to `pick_status`.
