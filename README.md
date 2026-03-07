# BetSync API

REST API for tracking sports betting picks, managing parlays, and running an automated suggestion pipeline. Built with FastAPI, PostgreSQL, Redis, and Celery.

---

## Architecture

```
Client (Browser / Swagger UI)
        │
        ▼
   ┌─────────┐
   │  Nginx  │  (optional — reverse proxy / TLS termination)
   └────┬────┘
        │
        ▼
   ┌──────────┐       ┌───────────┐
   │  FastAPI  │──────▶│ PostgreSQL │  ACID writes, dataset storage
   │  (async)  │       │   16      │
   └────┬──┬──┘       └───────────┘
        │  │
        │  └──────────▶┌───────┐
        │              │ Redis │  Cache (DB 0) + Celery broker (DB 1)
        │              │   7   │
        │              └───┬───┘
        │                  │
        ▼                  ▼
   ┌──────────────────────────┐
   │     Celery Worker        │  Async pipeline: odds fetch, pick
   │  (acks_late, sync)       │  suggestions, parlay generation
   └──────────────────────────┘
```

**Design principles:**

- **Monolith-first** — single API server, no premature microservices.
- **CP over AP** — consistency is critical; an incorrect pick or duplicate result destroys the dataset.
- **Cache-aside** — Redis caches dashboard aggregations; API still works if Redis goes down (degraded mode).
- **Async pipeline, sync API** — expensive odds-fetching runs in Celery; the API never blocks on external calls.

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Web framework | FastAPI | 0.115.6 |
| ASGI server | Uvicorn | 0.32.1 |
| Validation | Pydantic v2 | 2.10.3 |
| ORM | SQLAlchemy 2.0 | 2.0.36 |
| Async DB driver | asyncpg | 0.30.0 |
| Sync DB driver | psycopg2-binary | 2.9.10 |
| Migrations | Alembic | 1.14.0 |
| Cache / Broker | Redis + hiredis | 5.2.0 |
| Task queue | Celery | 5.4.0 |
| HTTP client | httpx + tenacity | 0.28.1 / 9.0.0 |
| Database | PostgreSQL | 16 |
| Container runtime | Docker Compose | 3.9 |

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- (Optional) An API key from [The Odds API](https://the-odds-api.com) for the suggestion pipeline

### 1. Clone and configure

```bash
git clone https://github.com/astraDukoWave/betsync-api.git
cd betsync-api
cp .env.example .env
```

Edit `.env` and set at minimum:

```
POSTGRES_PASSWORD=<strong-password>
SECRET_KEY=<random-hex-32>
```

### 2. Start the stack

```bash
docker compose up --build -d
```

This starts four services: **postgres**, **redis**, **api**, and **worker**. The API container automatically runs `alembic upgrade head` on startup to create or migrate the database schema.

### 3. Verify

```bash
# Health check
curl http://localhost:8000/health

# Swagger UI
open http://localhost:8000/docs
```

Expected health response:

```json
{
  "status": "healthy",
  "service": "betsync-api",
  "version": "1.0.0",
  "components": { "redis": "up" }
}
```

### 4. Generate a new migration (after model changes)

```bash
docker compose exec api alembic revision --autogenerate -m "describe_change"
docker compose exec api alembic upgrade head
```

---

## API Endpoints

All endpoints are prefixed with `/api/v1` except `/health`.

### Picks (central entity)

| Method | Path | Description | FR |
|--------|------|-------------|-----|
| `POST` | `/picks/` | Register a new pick | FR-01 |
| `GET` | `/picks/` | List picks with filters | FR-03 |
| `GET` | `/picks/{pick_id}` | Get pick by ID | — |
| `PATCH` | `/picks/{pick_id}` | Edit pending pick | FR-02 |
| `PATCH` | `/picks/{pick_id}/result` | Record result (won/lost/push/void) | FR-04 |
| `DELETE` | `/picks/{pick_id}` | Soft-delete pending pick | FR-05 |
| `PATCH` | `/picks/{pick_id}/confirm` | Confirm/discard pipeline suggestion | FR-16 |

Server-side calculations on `POST /picks/`:
- `odds_decimal` from `odds_american` (FR-06)
- `implied_prob = 1 / odds_decimal` (FR-06)
- `grade` (A/B/C) from implied probability thresholds

On `PATCH /picks/{id}/result`:
- `clv` calculated if `closing_odds_decimal` is provided (FR-13)
- Parlays containing this pick are auto-resolved (FR-09)

### Parlays

| Method | Path | Description | FR |
|--------|------|-------------|-----|
| `POST` | `/parlays/` | Create parlay from 2-8 picks | FR-07 |
| `GET` | `/parlays/` | List parlays with filters | FR-10 |
| `GET` | `/parlays/{parlay_id}` | Get parlay with pick details | — |

Server-side: `odds_total` (product of pick odds) and `potential_return` are calculated automatically (FR-08).

### Dashboard

| Method | Path | Description | FR |
|--------|------|-------------|-----|
| `GET` | `/dashboard/summary` | Global metrics (hit rate, ROI, streak) | FR-11, FR-12 |
| `GET` | `/dashboard/segments` | Performance by segment | FR-14 |

Supports filters: `date_from`, `date_to`, `sport_id`, `competition_id`, `market`, `sportsbook_id`, `grade`.

### Pipeline

| Method | Path | Description | FR |
|--------|------|-------------|-----|
| `POST` | `/pipeline/run` | Trigger async suggestion pipeline | FR-15 |
| `GET` | `/pipeline/jobs/{job_id}` | Poll job status | — |
| `GET` | `/pipeline/suggestions` | View pending suggestions | FR-15, FR-17 |

The pipeline runs asynchronously via Celery. `POST` returns `202 Accepted` immediately. An idempotency guard prevents duplicate runs for the same date.

### Configuration

| Method | Path | Description | FR |
|--------|------|-------------|-----|
| `GET` | `/config/` | List all config entries | FR-18 |
| `PATCH` | `/config/{key}` | Update a threshold value | FR-18 |

### Sportsbooks

| Method | Path | Description | FR |
|--------|------|-------------|-----|
| `GET` | `/sportsbooks/` | List sportsbooks | FR-19 |
| `POST` | `/sportsbooks/` | Register sportsbook | FR-19 |
| `PATCH` | `/sportsbooks/{id}` | Update sportsbook | FR-19 |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health with component status |

Returns `"healthy"` or `"degraded"` (if Redis is down but API still functions).

---

## Data Model

```
SPORT ──1:N──▶ COMPETITION ──1:N──▶ MATCH ──1:N──▶ PICK ◀──N:M──▶ PARLAY
                                                     │               │
                                             SPORTSBOOK ◀──FK────────┘

CONFIG  (independent key-value store)
```

All primary keys are UUIDs. All timestamps use `TIMESTAMP WITH TIME ZONE`.

| Table | Key Columns |
|-------|-------------|
| `sports` | sport_id, name, slug, is_active |
| `competitions` | competition_id, sport_id (FK), name, country, tier, is_active |
| `matches` | match_id, competition_id (FK), home_team, away_team, kickoff_at, status |
| `sportsbooks` | sportsbook_id, name, currency, odds_format_default, is_active |
| `picks` | pick_id, match_id (FK), sportsbook_id (FK), run_date, market, selection, odds_american, odds_decimal, implied_prob, grade, stake, status, source, clv, closing_odds_decimal, confirmed_at, resolved_at |
| `parlays` | parlay_id, sportsbook_id (FK), run_date, type, stake, odds_total, potential_return, actual_return, status |
| `parlay_picks` | parlay_pick_id, parlay_id (FK), pick_id (FK) |
| `config` | config_id, key (unique), value, description |

---

## Project Structure

```
betsync-api/
├── app/
│   ├── core/
│   │   ├── config.py              Settings (pydantic-settings, env vars)
│   │   ├── database.py            Async + sync engine, session factories
│   │   ├── dependencies.py        get_db, get_redis (FastAPI Depends)
│   │   ├── exceptions.py          Domain exceptions (NotFound, Conflict, BadRequest)
│   │   └── exception_handlers.py  Exception → HTTP response mapping
│   ├── models/                    SQLAlchemy 2.0 ORM (Mapped[] syntax)
│   │   ├── sport.py
│   │   ├── competition.py
│   │   ├── match.py
│   │   ├── sportsbook.py
│   │   ├── pick.py                Central entity with enums (PickStatus, PickGrade, PickSource)
│   │   ├── parlay.py
│   │   ├── parlay_pick.py         N:M junction table
│   │   └── config.py              SystemConfig key-value store
│   ├── schemas/                   Pydantic v2 request/response contracts
│   │   ├── pick.py                PickCreate, PickUpdate, PickResolve, PickResponse
│   │   ├── parlay.py              ParlayCreate, ParlayResponse, ParlayPickDetail
│   │   ├── dashboard.py           DashboardSummary, SegmentResponse
│   │   ├── pipeline.py            PipelineRunRequest, PipelineJobResponse
│   │   ├── config.py              ConfigResponse, ConfigUpdate
│   │   ├── errors.py              Standardized ErrorResponse envelope
│   │   ├── sport.py
│   │   ├── competition.py
│   │   ├── match.py
│   │   └── sportsbook.py
│   ├── services/                  Business logic (no HTTP, no FastAPI imports)
│   │   ├── pick_service.py        CRUD + odds calculation + grade classification
│   │   ├── parlay_service.py      Create + auto-resolve on pick result
│   │   ├── dashboard_service.py   Cache-aside aggregation queries
│   │   ├── cache_service.py       Redis ops with degraded-mode fallback
│   │   ├── config_service.py      System config CRUD
│   │   └── match_service.py       Match CRUD
│   ├── routers/                   FastAPI route handlers (async)
│   │   ├── picks.py
│   │   ├── parlays.py
│   │   ├── dashboard.py
│   │   ├── pipeline.py
│   │   ├── config.py
│   │   ├── health.py
│   │   └── sportsbooks.py
│   ├── worker/
│   │   ├── celery_app.py          Celery configuration
│   │   ├── tasks.py               run_pipeline_task (acks_late, sync)
│   │   └── pipeline/
│   │       ├── calculator.py      Pure functions: odds conversion, CLV, parlay combos
│   │       ├── odds_client.py     HTTP client with tenacity retry
│   │       ├── predictor.py       EV-based grade assignment
│   │       └── runner.py          6-step pipeline orchestrator
│   └── main.py                    App factory, lifespan, router mounting
├── alembic/
│   ├── env.py                     Async migration runner
│   └── versions/                  Migration files
├── tests/
│   ├── test_calculator.py         22 pure unit tests
│   └── test_pipeline.py           Predictor tests
├── docs/
│   └── api_edge_cases.md          Edge case documentation
├── docker-compose.yml             4 services: postgres, redis, api, worker
├── Dockerfile                     Multi-stage: api + worker targets
├── alembic.ini
├── requirements.txt
├── .env.example
└── .gitignore
```

**Layered architecture rules:**

| Layer | Allowed | Forbidden |
|-------|---------|-----------|
| Routers | FastAPI, schemas, services | Direct DB access, business logic |
| Services | SQLAlchemy, models, exceptions | FastAPI imports, HTTP concerns |
| Models | SQLAlchemy only | Pydantic |
| Schemas | Pydantic only | SQLAlchemy |

---

## Configuration

All configuration comes from environment variables (no hardcoded values). See `.env.example` for the full list.

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_PASSWORD` | Yes | PostgreSQL password |
| `SECRET_KEY` | Yes | Application secret for future auth |
| `DATABASE_URL` | Auto | Async connection string (asyncpg) |
| `DATABASE_URL_SYNC` | Auto | Sync connection string (psycopg2) |
| `REDIS_URL` | Auto | Redis cache connection (DB 0) |
| `CELERY_BROKER_URL` | Auto | Celery broker (Redis DB 1) |
| `ODDS_API_KEY` | No | The Odds API key (pipeline feature) |
| `DASHBOARD_CACHE_TTL` | No | Cache TTL in seconds (default: 300) |

In Docker Compose, `DATABASE_URL` and `DATABASE_URL_SYNC` are constructed automatically from `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`.

---

## Development

### Run tests

```bash
# Unit tests (no DB required)
python -m pytest tests/ -v

# Inside Docker
docker compose exec api python -m pytest tests/ -v
```

### Lint

```bash
python -m ruff check app/
```

### Logs

```bash
docker compose logs -f api
docker compose logs -f worker
```

### Reset database

```bash
docker compose down -v
docker compose up --build -d
docker compose exec api alembic upgrade head
```

---

## Error Response Format

All errors follow a standardized envelope:

```json
{
  "error": {
    "code": "PICK_ALREADY_RESOLVED",
    "message": "Pick already has a final status",
    "field": "status",
    "meta": { "current_status": "won", "pick_id": "..." }
  }
}
```

| HTTP Status | Error Codes |
|-------------|-------------|
| 400 | `PICKS_NOT_FOUND`, `PARLAY_DUPLICATE_MATCH`, `PICK_NOT_PENDING`, `PICK_NOT_FROM_PIPELINE`, `CONFIG_VALUE_INVALID` |
| 404 | `PICK_NOT_FOUND`, `PARLAY_NOT_FOUND`, `MATCH_NOT_FOUND`, `SPORTSBOOK_NOT_FOUND`, `CONFIG_NOT_FOUND`, `JOB_NOT_FOUND` |
| 409 | `PICK_ALREADY_RESOLVED`, `PICK_IN_PARLAY`, `SPORTSBOOK_EXISTS`, `PIPELINE_ALREADY_RAN` |
| 422 | `VALIDATION_ERROR` (Pydantic) |

---

## License

Private repository. All rights reserved.
