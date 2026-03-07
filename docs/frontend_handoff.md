# BetSync MVP v1.0.0 — Frontend Handoff & Performance Guide

**Fecha:** 7 de marzo de 2026 | **Status:** MVP Backend completo
**Base URL:** `/api/v1` | **CORS:** `allow_origins=["*"]` — Sin restricciones para desarrollo local

---

## Variables de entorno (configurar antes de empezar)

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_POLLING_INTERVAL_MS=2000
NEXT_PUBLIC_PIPELINE_TIMEOUT_MS=60000
```

---

## Stack recomendado

| Capa | Tecnología | Razón |
|---|---|---|
| Framework | Next.js 14 (App Router) + TypeScript | SSR para dashboard, escala bien |
| Estilos | Tailwind CSS + shadcn/ui | Componentes listos, dark mode gratis |
| Server state | TanStack Query | Cache, polling y loading states con mínimo código |
| Gráficas | Recharts o Chart.js | Ligeras, responsivas |
| Virtualización | @tanstack/react-virtual | Para listas largas en móvil |

---

## Formato de errores (aplica a toda la API)

**Todos** los endpoints devuelven errores con este envelope:

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

El frontend debe leer **`response.data.error.code`** para decidir qué toast, banner o mensaje mostrar. Nunca parsear `message` como string libre — usar `code` como discriminador.

---

## PARTE 1: Pantallas, Endpoints y UX/UI

### 1. Panel de Control (Dashboard)

**Objetivo:** Pantalla principal de aterrizaje con métricas financieras y gráficas analíticas.

**Endpoints:**
```
GET /dashboard/summary?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&sport_id=uuid&competition_id=uuid&market=1X2&sportsbook_id=uuid&grade=A
GET /dashboard/segments?group_by=market
```

`group_by` soporta: `selection | market | competition | sportsbook | grade`

**Campos que devuelve `summary`:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `total_picks` | int | Total de picks registrados |
| `resolved_picks` | int | Picks con resultado (won + lost + push) |
| `won` | int | Picks ganados |
| `lost` | int | Picks perdidos |
| `push` | int | Picks empatados |
| `hit_rate` | float | `won / (won + lost)`, ej. `0.598` |
| `total_stake` | float | Suma de unidades apostadas |
| `total_return` | float | Suma de retornos (ganados × odds + push devueltos) |
| `roi` | float | `(total_return - total_stake) / total_stake`, ej. `0.1306` |
| `current_streak` | object | `{ "type": "won", "count": 4 }` |
| `avg_odds_decimal` | float | Promedio de cuotas decimales |
| `avg_clv` | float\|null | Promedio de CLV (null si no hay datos) |
| `cache_hit` | bool | `true` si los datos vienen del caché Redis |

> No existe un campo `generated_at` ni `net_profit`. Para mostrar ganancia neta, calcular client-side: `net_profit = total_return - total_stake`. Para indicar antigüedad del caché, mostrar un badge genérico "datos cacheados" cuando `cache_hit` es `true`.

**Campos que devuelve `segments`:**

| Campo | Tipo |
|-------|------|
| `segment` | string — nombre del segmento (ej. "Arsenal FC ML") |
| `picks` | int |
| `hit_rate` | float |
| `roi` | float |
| `avg_odds` | float |

**UX/UI:**
- **Semántica de color en KPI cards:** ROI positivo → verde, negativo → rojo. Hit rate > 55% → badge "En racha"
- **Skeleton loading (no spinners):** Usar `animate-pulse` de Tailwind en las cards mientras cargan. Los spinners generan ansiedad cuando los números son de dinero; los skeletons comunican que la estructura ya está lista
- **Indicador de caché:** Si `cache_hit: true`, mostrar "Datos cacheados" con botón de refrescar manual
- **Gráficas:** Barras horizontales para segments — más legible en móvil que pie charts cuando hay 5+ categorías
- **Selector de rango rápido:** Shortcuts "Esta semana / Este mes / Todo" encima del date picker
- **Grid responsivo:** KPI cards en 2×2 en móvil, 4×1 en desktop
- **Detección de backend caído:** Hacer un `GET /health` al iniciar la app. Si falla, mostrar banner "Sistema temporalmente no disponible" en lugar de la UI vacía

---

### 2. Radar de Oportunidades (Pipeline)

**Objetivo:** Escanear cuotas y presentar sugerencias del motor de IA para aceptar o descartar.

**Endpoints:**
```
POST  /pipeline/run                      ← body: { "run_date": "YYYY-MM-DD", "force": false }
                                           ← responde 202: { "job_id": "uuid", "status": "queued", "message": "..." }

GET   /pipeline/jobs/{job_id}            ← polling cada 2s
                                           ← responde: { "job_id", "status": "queued|running|completed|failed",
                                              "picks_suggested", "parlays_suggested", "completed_at", "duration_sec" }

GET   /pipeline/suggestions              ← lista de picks con source=pipeline, status=pending
                                           ← responde: array de PickResponse

PATCH /picks/{pick_id}/confirm           ← body: { "confirmed": true | false }
```

**UX/UI:**
- **Botón con estados visuales:**
  - Idle → "Escanear cuotas"
  - Running → spinner + "Analizando mercados..."
  - Done → "X oportunidades encontradas"
- **Manejo del `409 PIPELINE_ALREADY_RAN`:** Mostrar toast "Ya se ejecutó el escaneo para hoy. Usa 'forzar' para repetirlo" y deshabilitar el botón. El error llega en `response.error.code === "PIPELINE_ALREADY_RAN"`
- **Timeout del polling:** Si después de 60s el job no completa, mostrar "Está tomando más de lo esperado. Revisa la Libreta en unos minutos" y detener el polling
- **Tarjetas tipo swipe (móvil):** Mostrar `market`, `selection`, `odds_american`, `grade`, `implied_prob` como badge. Colores por grado: A → verde, B → azul, C → amarillo
- **`confirmed: false`** marca el pick como `void` internamente — solo desaparecer la tarjeta del Radar

---

### 3. Libreta de Apuestas (Picks & Parlays)

**Objetivo:** Dos pestañas — historial de picks simples y parlays. Modales para crear y resolver.

**Endpoints Picks:**
```
GET   /picks?pick_status=pending&limit=50&offset=0
                                           ← responde: { "items": [...], "total": N, "limit": N, "offset": N }

POST  /picks                              ← body: { "match_id": "uuid", "sportsbook_id": "uuid",
                                              "market": "1X2", "selection": "Arsenal FC",
                                              "odds_american": -143, "stake": 1.0 }
                                           ← responde 201: PickResponse (con odds_decimal, implied_prob, grade calculados)

PATCH /picks/{pick_id}/result             ← body: { "status": "won|lost|push|void",
                                              "closing_odds_decimal": 1.55 }
                                           ← responde: PickResponse (con clv calculado si closing_odds_decimal fue enviado)

PATCH /picks/{pick_id}/confirm            ← body: { "confirmed": true }
```

> **Nota sobre paginación de picks:** La respuesta es un objeto envolvente con `items` (array), `total`, `limit`, `offset`. Para iterar los picks usar `response.items`.

**Filtros disponibles en `GET /picks`:** `run_date`, `pick_status`, `sport_id`, `competition_id`, `market`, `grade`, `source`. El param de status es `pick_status` (no `status`).

**Endpoints Parlays:**
```
GET  /parlays?parlay_status=pending&limit=20&offset=0
                                           ← responde: array directo de ParlayResponse

POST /parlays                             ← body: { "pick_ids": ["uuid", ...], "sportsbook_id": "uuid",
                                              "stake": 75.00, "type": "regular" }
                                           ← responde 201: ParlayResponse con picks[] incluidos

GET  /parlays/{parlay_id}                 ← ParlayResponse con picks[] incluidos
```

> **Nota sobre paginación de parlays:** La respuesta es un **array directo** (sin wrapper `items`). El filtro de status usa `parlay_status` (no `status`).

**Campos clave del Pick:**

| Campo | Tipo | Notas |
|-------|------|-------|
| `pick_id` | UUID | |
| `match_id` | UUID | |
| `sportsbook_id` | UUID | |
| `run_date` | date | Fecha de registro |
| `market` | string | "1X2", "BTTS", "Over/Under", etc. |
| `selection` | string | "Arsenal FC", "Over 2.5", "Yes" |
| `odds_american` | int | Ej: -143, +120 |
| `odds_decimal` | decimal | Calculado server-side |
| `implied_prob` | decimal | Calculado server-side |
| `grade` | enum | `A \| B \| C` |
| `stake` | decimal\|null | Unidades apostadas |
| `status` | enum | `pending \| won \| lost \| push \| void` |
| `source` | enum | `manual \| pipeline` |
| `clv` | decimal\|null | Calculado cuando se envía `closing_odds_decimal` en resolve |
| `closing_odds_decimal` | decimal\|null | Cuota de cierre (para CLV) |
| `confirmed_at` | datetime\|null | Solo para picks del pipeline |
| `resolved_at` | datetime\|null | Cuándo se registró resultado |
| `created_at` | datetime | |
| `updated_at` | datetime | |

**Campos clave del Parlay:**

| Campo | Tipo | Notas |
|-------|------|-------|
| `parlay_id` | UUID | |
| `sportsbook_id` | UUID | |
| `run_date` | date | |
| `type` | enum | `regular \| bonus` |
| `stake` | decimal | |
| `odds_total` | decimal | Producto de cuotas (calculado) |
| `potential_return` | decimal | `stake × odds_total` (calculado) |
| `actual_return` | decimal\|null | Solo cuando está resuelto |
| `status` | enum | `pending \| won \| lost` |
| `picks` | array | Lista de `{ pick_id, market, selection, odds_decimal, status }` |

**Estados de `status` y su representación visual:**

| Status | Color | Estilo |
|---|---|---|
| `pending` | Gris azulado | Normal |
| `won` | Verde | Bold |
| `lost` | Rojo | Normal |
| `push` | Naranja | Normal |
| `void` | Gris | Tachado |

> `void` ocurre cuando el usuario descarta un pick desde el Radar (`confirmed: false`). No olvidar este estado en la UI.

**UX/UI:**
- **Validación inline de odds:** Si el valor está entre -99 y +99, mostrar error de UI instantáneamente sin esperar al servidor (el backend devolverá `422 VALIDATION_ERROR`). Mostrar debajo del input "= $X ganancia potencial" mientras el usuario escribe
- **Filtros rápidos con chips:** `Todos | Pendiente | Ganados | Perdidos` — sin dropdowns
- **Badge CLV:** Si `clv > 0`, mostrar "+X% CLV" en verde. Es la métrica que diferencia al apostador analítico. Si `clv < 0`, mostrar en rojo sin signo de alerta (no alarmar, solo informar)
- **Fila expandible:** Al hacer click, revelar `implied_prob`, `closing_odds_decimal`, `clv`, `source`
- **Parlay builder:** Checkboxes en la tabla de picks pendientes → botón "Crear parlay con X picks". Deshabilitar el botón si hay menos de 2 seleccionados. Máximo 8

---

### 4. Configuración (Settings)

**Objetivo:** Gestionar casas de apuestas y editar reglas del motor de IA.

**Endpoints:**
```
GET   /sportsbooks                        ← array de SportsbookResponse
POST  /sportsbooks                        ← body: { "name": "Betmaster", "currency": "MXN",
                                              "odds_format_default": "american" }
PATCH /sportsbooks/{sportsbook_id}        ← body parcial: { "is_active": false }

GET   /config                             ← array de ConfigResponse: { config_id, key, value, description, updated_at }
PATCH /config/{key}                       ← body: { "value": "0.60" }
```

**UX/UI:**
- **Edición inline:** Editar valores de config directamente en la tabla con input + botón guardar por fila, sin modales
- **Traducción de keys:** Los nombres del backend son técnicos. Mostrarlos con texto amigable y tooltip:

| Key del backend | Texto en UI | Tooltip |
|---|---|---|
| `min_implied_prob_class_a` | Umbral Grado A | Probabilidad implícita mínima para clasificar como Grado A (default: 0.55) |
| `min_implied_prob_class_b` | Umbral Grado B | Probabilidad implícita mínima para clasificar como Grado B (default: 0.50) |
| `min_parlay_odds_total` | Cuota mínima de parlay | Cuota total mínima para sugerir un parlay (default: 1.80) |
| `active_competition_tiers` | Tiers activos | Tiers de competición que el pipeline considera (default: "A,B") |
| `pipeline_min_grade` | Grado mínimo del pipeline | Grado mínimo de pick para que el pipeline lo sugiera (default: "B") |

- **Sportsbook:** Dejar espacio en la card para `logo_url` aunque el campo aún no esté en el backend — lo agradecerán en V2

---

## Flujos críticos para QA

| Flujo | Happy path | Error a manejar |
|---|---|---|
| Crear pick | `POST /picks` → 201 → aparece en tabla | `422 VALIDATION_ERROR` (odds entre -99 y +99) |
| Resolver pick | `PATCH /picks/{id}/result` → actualiza fila + CLV | `409 PICK_ALREADY_RESOLVED` |
| Pipeline run | `POST /pipeline/run` → 202 → polling → suggestions | `409 PIPELINE_ALREADY_RAN` |
| Crear parlay | Seleccionar 2+ picks → `POST /parlays` → 201 → aparece en pestaña | `422 VALIDATION_ERROR` (< 2 picks), `400 PARLAY_DUPLICATE_MATCH`, `400 PICK_NOT_PENDING` |
| Descartar sugerencia | `PATCH /picks/{id}/confirm` con `false` → pick queda en `void` | Pick desaparece del Radar |
| Config update | `PATCH /config/{key}` → valor actualizado | `404 CONFIG_NOT_FOUND` |
| Crear sportsbook | `POST /sportsbooks` → 201 | `409 SPORTSBOOK_EXISTS` (nombre duplicado) |

---

## PARTE 2: Guía de Rendimiento

### 1. No bloquear el hilo principal (evitar Reflow)

Las animaciones de las tarjetas swipe del Radar **nunca** deben usar `margin-left`, `top`, o `left`. Usar exclusivamente:

```css
transform: translateX(120%);   /* GPU layer */
margin-left: 120%;              /* fuerza Reflow — no usar */
```

`transform` delega el movimiento a la GPU y evita que el navegador recalcule el layout de toda la página.

---

### 2. Observer API en lugar de eventos globales

**Scroll infinito en la Libreta:** No usar `window.onscroll`. Colocar un elemento fantasma al final de la lista y usar `IntersectionObserver` para disparar la siguiente página:

```js
const observer = new IntersectionObserver(([entry]) => {
  if (entry.isIntersecting) fetchNextPage(); // TanStack Query
});
observer.observe(sentinelRef.current);
```

Es significativamente más eficiente porque corre fuera del hilo principal, a diferencia de `onscroll` que se dispara en cada pixel.

**Gráficas responsivas:** Usar `ResizeObserver` directamente sobre el contenedor de la gráfica, nunca `window.resize`.

---

### 3. Virtualización del DOM (vital para móviles)

Conforme el usuario acumule cientos de picks, el DOM colapsará si se renderizan todos los `<tr>` a la vez. Usar `@tanstack/react-virtual`:

- **Móvil:** renderizar ~15-20 filas a la vez
- **Desktop:** se puede relajar a 50-100 filas

---

### 4. Diseño del estado

**Dónde guardar cada cosa:**

| Dato | Dónde |
|---|---|
| Tema oscuro, preferencias UI | `localStorage` |
| Picks, parlays, dashboard | TanStack Query (memoria RAM) |
| Modo offline pesado (V2+) | `IndexedDB` |

**Normalización:** Almacenar picks y parlays como diccionario por ID, no como array:

```js
// Búsqueda O(1)
const picksById = { "uuid-1": {...}, "uuid-2": {...} }

// Búsqueda O(n) — lento con miles de registros
const picks = [{id: "uuid-1"}, {id: "uuid-2"}]
```

---

### 5. Polling — alcance real y deuda técnica consciente

El polling a `GET /pipeline/jobs/{job_id}` **está acotado al tiempo de vida del job (~30-60 segundos)**. No es un polling permanente, por lo que no representa un problema real de batería o datos en V1.

> **Deuda técnica documentada para V2:** Si en versiones futuras se agrega seguimiento de odds en tiempo real o notificaciones live, migrar ese endpoint a **Server-Sent Events (SSE)**. Es la solución más eficiente para conexiones unidireccionales (servidor → cliente) sin el costo de infraestructura de WebSockets. El polling acotado del pipeline actual no justifica ese cambio todavía.

---

### 6. Bundling y carga de assets

- **Target ES6+:** Next.js 14 ya lo hace por defecto. No agregar polyfills para navegadores viejos innecesariamente
- **`defer` en scripts de analíticas:** Para que el LCP (Largest Contentful Paint) de las métricas financieras ocurra en menos de 2 segundos
- **Tailwind no anida selectores** de forma innecesaria — el CSSOM se construye rápido. No sobreescribir estilos con CSS custom si Tailwind ya lo cubre

> **Nota:** La compresión Brotli/Gzip es responsabilidad del servidor de deployment (Vercel la aplica automáticamente, nginx requiere configuración). No es tarea del equipo frontend.

---

*Documento generado por Tech Lead — BetSync MVP v1.0.0*
*Validado contra la API real el 7 de marzo de 2026*
