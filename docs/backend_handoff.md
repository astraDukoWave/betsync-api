# Backend Handoff — BetSync API v1.0.0

**Fecha:** 7 de marzo de 2026 | **Autor:** Tech Lead | **Status:** MVP Backend completo

---

## Resumen ejecutivo

El backend está desplegado y funcional en GitHub Codespaces. Arquitectura: FastAPI + PostgreSQL + Redis + Celery. Todos los contratos de API están definidos y el esquema de base de datos está aplicado.

---

## Acceso

| Recurso | URL |
|---------|-----|
| Repo | github.com/astraDukoWave/betsync-api |
| Swagger UI | http://localhost:8000/docs |
| Health check | `GET /health` |
| OpenAPI JSON | `GET /openapi.json` |

---

## Stack técnico

| Capa | Tecnología |
|------|-----------|
| API | FastAPI 0.115.6 async |
| Base de datos | PostgreSQL 16 (UUID PKs) |
| Cache | Redis 7 (cache-aside, TTL 5 min) |
| Queue | Celery 5.4 + Redis broker |
| ORM | SQLAlchemy 2.0 async |
| Migraciones | Alembic (ya aplicadas) |
| Contenedores | Docker Compose v2 |

---

## ERD resumido (modelos relevantes al frontend)

```
Sport → Competition → Match
Sportsbook
Pick (market, selection, odds_american, odds_decimal, implied_prob, grade, stake, status, source, clv)
  └── ParlayPick (junction N:M)
Parlay (type, odds_total, potential_return, actual_return, status)
SystemConfig (key → value)
```

---

## Convenciones importantes

- **Base URL:** `/api/v1`
- **CORS:** `allow_origins=["*"]` — sin restricciones para desarrollo
- **Paginación picks:** `?limit=50&offset=0` (default limit = 50)
- **Paginación parlays:** `?limit=20&offset=0` (default limit = 20)
- **Picks list response:** envuelta en `{ "items": [...], "total": N, "limit": N, "offset": N }`
- **Parlays list response:** array directo `[...]`
- **Enums Pick status:** `pending | won | lost | push | void`
- **Enums Pick grade:** `A | B | C`
- **Enums Pick source:** `manual | pipeline`
- **Enums Parlay status:** `pending | won | lost`
- **Odds americanas:** valores entre -99 y +99 son rechazados → la API devuelve `422 VALIDATION_ERROR`
- **Parlay picks:** mínimo 2, máximo 8 (validado por Pydantic → `422 VALIDATION_ERROR`)
- **Query params de filtro de status:** usar `pick_status` para picks y `parlay_status` para parlays (no `status`)

---

## Formato de errores estandarizado

**Todos** los errores (400, 404, 409, 422, 500) usan el mismo envelope:

```json
{
  "error": {
    "code": "PICK_ALREADY_RESOLVED",
    "message": "Pick already has a final status",
    "field": "status",
    "meta": { "current_status": "won", "pick_id": "uuid..." }
  }
}
```

El frontend debe leer `response.error.code` para decidir qué mostrar al usuario.

### Catálogo de errores

| HTTP | code | Cuándo |
|------|------|--------|
| 400 | `PICKS_NOT_FOUND` | `POST /parlays` — uno o más `pick_ids` no existen |
| 400 | `PARLAY_DUPLICATE_MATCH` | `POST /parlays` — dos picks del mismo partido |
| 400 | `PICK_NOT_PENDING` | `POST /parlays` o `DELETE /picks` — pick ya resuelto |
| 400 | `PICK_NOT_FROM_PIPELINE` | `PATCH /picks/{id}/confirm` — pick manual, no del pipeline |
| 404 | `PICK_NOT_FOUND` | Pick no existe |
| 404 | `PARLAY_NOT_FOUND` | Parlay no existe |
| 404 | `SPORTSBOOK_NOT_FOUND` | Sportsbook no existe |
| 404 | `CONFIG_NOT_FOUND` | Config key no existe |
| 404 | `JOB_NOT_FOUND` | Job de pipeline no existe |
| 409 | `PICK_ALREADY_RESOLVED` | `PATCH /picks/{id}` o `/result` — pick ya tiene status final |
| 409 | `PICK_IN_PARLAY` | `DELETE /picks/{id}` — pick pertenece a un parlay |
| 409 | `SPORTSBOOK_EXISTS` | `POST /sportsbooks` — nombre duplicado |
| 409 | `PIPELINE_ALREADY_RAN` | `POST /pipeline/run` — ya corrió para esa fecha |
| 422 | `VALIDATION_ERROR` | Cualquier error de validación Pydantic (odds inválidos, parlay < 2 picks, campos faltantes) |
| 500 | `INTERNAL_SERVER_ERROR` | Error no controlado |

---

## Decisiones de diseño que el frontend debe conocer

### Cache-aside en dashboard
`/dashboard/summary` puede responder con `"cache_hit": true`. En ese caso los datos tienen hasta 5 min de antigüedad. No existe un campo `generated_at` — el frontend debe estimar la antigüedad del caché por contexto (ej. "datos cacheados") y ofrecer un botón de refrescar que haga la petición con un cache-buster o espere el TTL.

### Pipeline asíncrono
`POST /pipeline/run` no bloquea. Devuelve `202 Accepted` con `job_id`, `status: "queued"` y `message`. El frontend debe hacer polling a `GET /pipeline/jobs/{job_id}` cada 2s hasta `status: "completed"` o `"failed"`.

### Idempotencia del pipeline
Si se llama `POST /pipeline/run` cuando ya corrió para esa fecha, devuelve **409** con code `PIPELINE_ALREADY_RAN`. NO devuelve el mismo `job_id`. El frontend debe capturar el 409 y mostrar un toast informativo. El cliente puede enviar `"force": true` en el body para forzar una nueva ejecución.

### Auto-resolución de parlays
Cuando todos los picks de un parlay se resuelven, el parlay se resuelve automáticamente. El frontend no necesita hacer nada extra — solo refrescar la lista de parlays.

### Odds calculados server-side
Al crear un pick, el frontend envía solo `odds_american`. El server calcula y devuelve: `odds_decimal`, `implied_prob`, y `grade` (si no se envió explícitamente).

---

## Cómo levantar localmente

```bash
git clone https://github.com/astraDukoWave/betsync-api
cp .env.example .env
docker compose up --build -d
# Alembic upgrade head corre automáticamente al iniciar el container api
# → http://localhost:8000/docs
```
