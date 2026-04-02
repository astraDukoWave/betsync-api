# API Contracts for Frontend — BetSync

> Auto-generated from backend source analysis.
> Base URL: `{VITE_API_BASE_URL}/api/v1`

---

## Table of Contents

1. [Dashboard Financiero](#1-dashboard-financiero)
2. [Ledger (Libro Mayor)](#2-ledger-libro-mayor)
3. [Reconciliación (Admin)](#3-reconciliación-admin)
4. [Fiscal](#4-fiscal)
5. [Picks](#5-picks)
6. [Reglas Transversales de UI](#6-reglas-transversales-de-ui)
7. [Catálogo de Errores](#7-catálogo-de-errores)

---

## 1. Dashboard Financiero

### 1.1 Resumen de Performance — `GET /api/v1/dashboard/summary`

Devuelve las métricas agregadas de rendimiento de apuestas. **No** devuelve saldos de wallet (`available_balance`, `locked_balance`); para esos campos usar `GET /api/v1/wallet/balance` (ver sección 1.3).

**Query Parameters** (todos opcionales):

| Param            | Type   | Example                                |
|------------------|--------|----------------------------------------|
| `date_from`      | `date` | `2025-01-01`                           |
| `date_to`        | `date` | `2025-12-31`                           |
| `sport_id`       | `UUID` | `c0a80164-...`                         |
| `competition_id` | `UUID` | `c0a80164-...`                         |
| `market`         | `str`  | `moneyline`                            |
| `sportsbook_id`  | `UUID` | `c0a80164-...`                         |
| `grade`          | `str`  | `A`                                    |

**Response `200 OK`** — `DashboardSummary`:

```json
{
  "total_picks": 142,
  "resolved_picks": 130,
  "won": 78,
  "lost": 48,
  "push": 4,
  "hit_rate": 0.619,
  "total_stake": 26400.00,
  "total_return": 31250.50,
  "roi": 0.1837,
  "current_streak": {
    "type": "won",
    "count": 5
  },
  "avg_odds_decimal": 1.92,
  "avg_clv": 0.034,
  "cache_hit": false
}
```

**Mapping para el frontend:**

| Frontend mock field | API field        | Notes                                     |
|---------------------|------------------|--------------------------------------------|
| `profit`            | Calcular: `total_return - total_stake` | El backend no devuelve un campo `profit` directamente en el dashboard |
| `hitRate`           | `hit_rate`       | Ratio 0–1; multiplicar por 100 para %      |
| `roi`               | `roi`            | Ratio; multiplicar por 100 para %           |
| `streak`            | `current_streak` | `{ type: "won"|"lost"|"none", count: N }`  |

### 1.2 Flujo de Caja (Balance por Sportsbook) — `GET /api/v1/transactions/cashflow`

Este es el endpoint más cercano a un "balance financiero". Devuelve depósitos, retiros y saldo estimado **por casa de apuestas** en un rango de fechas.

**Query Parameters** (requeridos):

| Param       | Type   | Example      |
|-------------|--------|--------------|
| `date_from` | `date` | `2025-01-01` |
| `date_to`   | `date` | `2025-12-31` |

**Response `200 OK`** — `CashflowSummary`:

```json
{
  "period_start": "2025-01-01",
  "period_end": "2025-12-31",
  "total_in_mxn": "45000.00",
  "total_out_mxn": "12000.00",
  "net_cashflow_mxn": "33000.00",
  "by_sportsbook": [
    {
      "sportsbook_id": "a1b2c3d4-...",
      "sportsbook_name": "Caliente",
      "currency": "MXN",
      "total_deposits_mxn": "30000.00",
      "total_withdrawals_mxn": "8000.00",
      "total_bonuses_mxn": "500.00",
      "estimated_balance_mxn": "22500.00"
    }
  ]
}
```

### 1.3 Balance del Usuario (Wallet) — `GET /api/v1/wallet/balance`

Devuelve el saldo actual de la billetera del usuario: fondos disponibles y fondos bloqueados en escrow (picks pendientes). El parámetro `user_id` se inyecta vía `Query(default=DEFAULT_USER_ID)` desde `app/core/config.py`.

**Query Parameters** (opcionales):

| Param     | Type   | Default                                  |
|-----------|--------|------------------------------------------|
| `user_id` | `UUID` | `DEFAULT_USER_ID` de `config.py` (`00000000-0000-4000-8000-000000000001`) |

**Response `200 OK`** — `WalletBalanceResponse`:

```json
{
  "user_id": "00000000-0000-4000-8000-000000000001",
  "available_balance": "15340.50",
  "locked_balance": "2500.00",
  "updated_at": "2025-06-15T14:30:00Z"
}
```

**Mapping para el frontend:**

| Frontend mock field  | API field            | Notes                                          |
|----------------------|----------------------|-------------------------------------------------|
| `available_balance`  | `available_balance`  | Fondos libres para nuevas apuestas              |
| `locked_balance`     | `locked_balance`     | Stake bloqueado en picks pendientes (escrow)    |
| `total_balance`      | Calcular: `available_balance + locked_balance` | El backend no devuelve un total explícito |

**Errores posibles:**

| HTTP | Code                     | Cuándo                                       |
|------|--------------------------|----------------------------------------------|
| 404  | `USER_BALANCE_NOT_FOUND` | No existe fila de balance para ese `user_id` |

### 1.4 Segmentos — `GET /api/v1/dashboard/segments`

Desglose de rendimiento agrupado por una dimensión.

**Query Parameters:**

| Param      | Type  | Default       | Allowed values                                       |
|------------|-------|---------------|------------------------------------------------------|
| `group_by` | `str` | `"selection"` | `selection`, `market`, `competition`, `sportsbook`, `grade` |

**Response `200 OK`** — `SegmentResponse[]`:

```json
[
  {
    "segment": "Over 2.5",
    "picks": 34,
    "hit_rate": 0.6765,
    "roi": 0.0,
    "avg_odds": 1.87
  }
]
```

---

## 2. Ledger (Libro Mayor)

### 2.1 Historial del Ledger — `GET /api/v1/wallet/ledger`

Devuelve el historial de movimientos del libro mayor para un usuario, ordenado del más reciente al más antiguo. Cada entrada refleja un cambio atómico en los balances (stake lock, payout, loss, refund). El parámetro `user_id` se inyecta vía `Query(default=DEFAULT_USER_ID)` desde `app/core/config.py`.

**Query Parameters** (opcionales):

| Param     | Type   | Default                                  | Validación |
|-----------|--------|------------------------------------------|------------|
| `user_id` | `UUID` | `DEFAULT_USER_ID` de `config.py` (`00000000-0000-4000-8000-000000000001`) |  |
| `limit`   | `int`  | `50`                                     | 1–200      |

**Response `200 OK`** — `LedgerHistoryResponse`:

```json
{
  "items": [
    {
      "ledger_entry_id": "e4f5a6b7-...",
      "amount": "500.00",
      "type": "PICK_PAYOUT",
      "reference_id": "d3c2b1a0-...",
      "balance_after": "15840.50",
      "locked_after": "2000.00",
      "created_at": "2025-06-15T14:30:00Z"
    },
    {
      "ledger_entry_id": "a1b2c3d4-...",
      "amount": "200.00",
      "type": "PICK_STAKE_LOCK",
      "reference_id": "f9e8d7c6-...",
      "balance_after": "15340.50",
      "locked_after": "2500.00",
      "created_at": "2025-06-15T12:00:00Z"
    }
  ],
  "total": 42
}
```

**Mapping para el frontend:**

| Frontend mock field | API field        | Notes                                          |
|---------------------|------------------|-------------------------------------------------|
| `balance_after`     | `balance_after`  | Saldo disponible tras este movimiento           |
| `locked_after`      | `locked_after`   | Saldo bloqueado tras este movimiento            |
| `type`              | `type`           | Enum: ver tabla abajo                           |
| `amount`            | `amount`         | Monto del movimiento                            |
| `reference_id`      | `reference_id`   | UUID del pick asociado (nullable)               |

**Errores posibles:**

| HTTP | Code                     | Cuándo                                       |
|------|--------------------------|----------------------------------------------|
| 404  | `USER_BALANCE_NOT_FOUND` | No existe fila de balance para ese `user_id` |

**Tipos de entrada del ledger** (`LedgerEntryType`):

| Enum value        | Significado                          | Efecto en balances                       |
|-------------------|--------------------------------------|------------------------------------------|
| `PICK_STAKE_LOCK` | Se bloquea stake al crear un pick    | `available -= stake`, `locked += stake`  |
| `PICK_PAYOUT`     | Pick ganado: se desbloquea + paga    | `locked -= stake`, `available += payout` |
| `PICK_LOSS`       | Pick perdido: se pierde el stake     | `locked -= stake`                        |
| `PICK_REFUND`     | Push/void: se devuelve el stake      | `locked -= stake`, `available += stake`  |

### 2.2 Transacciones Contables — `GET /api/v1/transactions/`

Historial de transacciones externas (depósitos, retiros, bonos). Complementa al ledger interno (sección 2.1) que solo registra movimientos de picks.

**Query Parameters** (todos opcionales):

| Param              | Type               | Default | Notes                                          |
|--------------------|--------------------|---------|-------------------------------------------------|
| `sportsbook_id`    | `UUID`             | —       | Filtrar por casa                                |
| `transaction_type` | `TransactionType`  | —       | `deposit`, `withdrawal`, `bonus`, `commission`, `void_refund` |
| `date_from`        | `date`             | —       |                                                 |
| `date_to`          | `date`             | —       |                                                 |
| `tax_year`         | `int`              | —       |                                                 |
| `page`             | `int`              | `1`     | ≥ 1                                             |
| `page_size`        | `int`              | `50`    | 1–200                                           |

**Response `200 OK`** — `TransactionListResponse`:

```json
{
  "items": [
    {
      "transaction_id": "f1e2d3c4-...",
      "sportsbook_id": "a1b2c3d4-...",
      "type": "deposit",
      "amount": "5000.00",
      "currency": "MXN",
      "exchange_rate": "1.0000",
      "amount_mxn": "5000.00",
      "transaction_date": "2025-06-01",
      "tax_year": 2025,
      "reference_id": "TXN-CAL-001",
      "bank_reference": "SPEI-2025060100123",
      "description": "Depósito inicial Caliente",
      "created_at": "2025-06-01T10:00:00Z",
      "updated_at": "2025-06-01T10:00:00Z"
    }
  ],
  "total": 87,
  "page": 1,
  "page_size": 50
}
```

**Mapping para el frontend:**

| Frontend mock field | API field          | Notes                                     |
|---------------------|--------------------|--------------------------------------------|
| `balance_after`     | Usar `GET /wallet/ledger` | Disponible en el endpoint de ledger (sección 2.1) |
| `type`              | `type`             | Valores: `deposit`, `withdrawal`, `bonus`, `commission`, `void_refund` |
| `amount`            | `amount_mxn`       | Ya convertido a MXN                        |

**Tipos de transacción** (`TransactionType`):

| Valor         | Significado                   |
|---------------|-------------------------------|
| `deposit`     | Depósito en casa de apuestas  |
| `withdrawal`  | Retiro de casa de apuestas    |
| `bonus`       | Bono recibido                 |
| `commission`  | Comisión cobrada              |
| `void_refund` | Devolución por anulación      |

**Monedas soportadas** (`TransactionCurrency`): `MXN`, `EUR`, `USD`, `ARS`, `GBP`

---

## 3. Reconciliación (Admin)

> Todos los endpoints de esta sección requieren el header `X-Reconciliation-Secret` con el valor configurado en el backend (`ADMIN_RECONCILIATION_SECRET`). Sin él, retornan `401 Unauthorized`.

### 3.1 Estado Global del Sistema — `GET /api/v1/admin/financial-health`

Escaneo read-only que cuenta cuántos usuarios están en cada nivel de severidad.

**Headers requeridos:**

```
X-Reconciliation-Secret: <secret>
```

**Response `200 OK`** — `FinancialHealthSummarySchema`:

```json
{
  "total_users": 1,
  "ok_users": 1,
  "warning_users": 0,
  "critical_users": 0
}
```

**Severidades:**

| Nivel      | Significado                                                   | Acción                     |
|------------|---------------------------------------------------------------|----------------------------|
| `OK`       | Wallet y ledger cuadran perfectamente                        | Ninguna                    |
| `WARNING`  | Escrow desalineado pero ledger OK                            | Fix automático disponible  |
| `CRITICAL` | Ledger no cuadra con wallet; bloquea depósitos y retiros     | Auditoría SQL manual       |

**Mapping para UI:**

- Si `critical_users > 0` → badge rojo "CRITICAL" + deshabilitar botón de depósitos/retiros
- Si `warning_users > 0` → badge amarillo "WARNING" + habilitar botón "Reparar"
- Si todo `ok_users == total_users` → badge verde "HEALTHY"

### 3.2 Ejecutar Reconciliación Completa — `POST /api/v1/admin/reconciliation/run`

Ejecuta un escaneo completo de todos los usuarios y persiste anomalías en `reconciliation_audit`.

**Headers requeridos:**

```
X-Reconciliation-Secret: <secret>
```

**Response `200 OK`** — `ReconciliationSummarySchema`:

```json
{
  "total_users": 1,
  "ok_users": 1,
  "warning_users": 0,
  "critical_users": 0,
  "anomalies": [
    {
      "user_id": "00000000-0000-4000-8000-000000000001",
      "escrow_expected": "2500.00",
      "escrow_actual": "2700.00",
      "ledger_expected": "17840.50",
      "ledger_actual": "17840.50",
      "escrow_drift": "200.00",
      "ledger_drift": "0.00",
      "severity": "WARNING"
    }
  ],
  "duration_seconds": 0.342
}
```

### 3.3 Historial de Anomalías — `GET /api/v1/admin/reconciliation/anomalies`

**Headers requeridos:**

```
X-Reconciliation-Secret: <secret>
```

**Query Parameters:**

| Param   | Type  | Default | Max |
|---------|-------|---------|-----|
| `limit` | `int` | `100`   | 500 |

**Response `200 OK`** — `ReconciliationAnomaliesResponse`:

```json
{
  "items": [
    {
      "id": "b7a6c5d4-...",
      "user_id": "00000000-0000-4000-8000-000000000001",
      "escrow_drift": "200.00",
      "ledger_drift": "0.00",
      "severity": "WARNING",
      "detail": {
        "kind": "escrow_repair",
        "previous": { "available": "15340.50", "locked": "2700.00" },
        "new": { "available": "15540.50", "locked": "2500.00" }
      },
      "created_at": "2025-06-15T14:30:00Z"
    }
  ]
}
```

### 3.4 Reparar Balance de Usuario — `POST /api/v1/admin/reconciliation/{user_id}/fix`

Repara **solo desalineación de escrow** cuando el ledger aún cuadra. Si hay `LEDGER_MISMATCH` o `FULL_INCONSISTENT`, retorna `409 Conflict` y la reparación debe ser manual (SQL).

**Path Parameters:**

| Param     | Type   |
|-----------|--------|
| `user_id` | `UUID` |

**Headers requeridos:**

```
X-Reconciliation-Secret: <secret>
```

**Response `200 OK`** — `ReconciliationFixResponse`:

```json
{
  "user_id": "00000000-0000-4000-8000-000000000001",
  "drift_type_before": "ESCROW_MISMATCH",
  "repaired": true,
  "previous_available": "15340.50",
  "previous_locked": "2700.00",
  "new_available": "15540.50",
  "new_locked": "2500.00"
}
```

**Valores de `drift_type_before`:**

| Valor                | Reparable? | Significado                                    |
|----------------------|------------|------------------------------------------------|
| `NONE`               | N/A        | No había drift; `repaired: false`              |
| `ESCROW_MISMATCH`    | Sí         | Solo escrow desalineado; reparación automática |
| `LEDGER_MISMATCH`    | No (409)   | Ledger no cuadra; auditoría manual requerida   |
| `FULL_INCONSISTENT`  | No (409)   | Ambos desalineados; auditoría manual requerida |

**Errores posibles:**

| HTTP | Code                  | Cuándo                                            |
|------|-----------------------|---------------------------------------------------|
| 409  | `REPAIR_UNSAFE_STATE` | Drift involucra al ledger; reparación prohibida   |
| 404  | `USER_BALANCE_NOT_FOUND` | No existe fila de balance para ese `user_id`   |
| 401  | —                     | Header `X-Reconciliation-Secret` faltante/inválido |

---

## 4. Fiscal

### 4.1 Resumen Fiscal Anual — `GET /api/v1/fiscal/summary`

Calcula la base imponible estimada cruzando picks resueltos y transacciones del año fiscal. Todos los montos en MXN. Jurisdicción: SAT (México).

**Query Parameters** (requerido):

| Param      | Type  | Example | Validación    |
|------------|-------|---------|---------------|
| `tax_year` | `int` | `2025`  | 2000 ≤ x ≤ 2100 |

**Response `200 OK`** — `FiscalSummaryResponse`:

```json
{
  "tax_year": 2025,
  "jurisdiction": "MX_SAT",
  "gross_winnings_mxn": "48250.00",
  "gross_losses_mxn": "26400.00",
  "net_gambling_income_mxn": "21850.00",
  "total_picks_won": 78,
  "total_picks_lost": 48,
  "total_deposits_mxn": "45000.00",
  "total_withdrawals_mxn": "12000.00",
  "net_cashflow_mxn": "33000.00",
  "taxable_base_estimate_mxn": "21850.00",
  "currency": "MXN"
}
```

**Mapping para el frontend:**

| Frontend mock field     | API field                    | Notes                                |
|-------------------------|------------------------------|--------------------------------------|
| Base imponible          | `taxable_base_estimate_mxn`  | `max(net_gambling_income, 0)`        |
| Ganancias brutas        | `gross_winnings_mxn`         | Picks ganados × odds                 |
| Pérdidas brutas         | `gross_losses_mxn`           | Stake de picks perdidos              |
| Ingreso neto de juego   | `net_gambling_income_mxn`    | Puede ser negativo                   |
| Total depositado        | `total_deposits_mxn`         | Incluye bonos                        |
| Total retirado          | `total_withdrawals_mxn`      |                                      |
| Flujo neto              | `net_cashflow_mxn`           | `deposits - withdrawals`             |

### 4.2 Exportar CSV Fiscal — `GET /api/v1/fiscal/export/csv`

Descarga un archivo CSV con el detalle de todos los picks resueltos y transacciones del año fiscal.

**Query Parameters** (requerido):

| Param      | Type  | Example |
|------------|-------|---------|
| `tax_year` | `int` | `2025`  |

**Response `200 OK`** — `text/csv` (descarga directa):

```
Content-Type: text/csv
Content-Disposition: attachment; filename="betsync_fiscal_2025.csv"
X-Fiscal-Year: 2025
X-Total-Records: 215
```

**Columnas del CSV:**

| Columna          | Descripción                                      |
|------------------|--------------------------------------------------|
| `record_type`    | `pick` o `transaction`                           |
| `fiscal_date`    | Fecha del evento                                 |
| `tax_year`       | Año fiscal                                       |
| `description`    | Descripción del evento                           |
| `detail`         | Market+selection (picks) o tipo (transactions)   |
| `debit_mxn`      | Salidas: stake perdido / retiro                  |
| `credit_mxn`     | Entradas: ganancia / depósito / bono             |
| `net_mxn`        | `credit - debit`                                 |
| `currency`       | Moneda original                                  |
| `exchange_rate`  | TC al día del movimiento                         |
| `reference`      | ID de referencia                                 |
| `sportsbook_id`  | Casa de apuestas                                 |

---

## 5. Picks

### 5.1 Listar Picks — `GET /api/v1/picks/`

Devuelve los picks del usuario, paginados y con filtros opcionales.

> **`user_id` como query param:** Se inyecta vía `Query(default=DEFAULT_USER_ID)`. El valor de `DEFAULT_USER_ID` está definido en `app/core/config.py` como `UUID("00000000-0000-4000-8000-000000000001")`. El frontend no necesita enviarlo para el usuario por defecto.

**Query Parameters** (todos opcionales):

| Param            | Type         | Default                                | Notes                        |
|------------------|--------------|----------------------------------------|------------------------------|
| `user_id`        | `UUID`       | `DEFAULT_USER_ID` de `config.py`       | `00000000-0000-4000-8000-000000000001`. Filtra picks por propietario |
| `run_date`       | `date`       | —                                      | Filtra por fecha de operación|
| `pick_status`    | `PickStatus` | —                                      | `pending`, `won`, `lost`, `push`, `void` |
| `sport_id`       | `UUID`       | —                                      |                              |
| `competition_id` | `UUID`       | —                                      |                              |
| `market`         | `str`        | —                                      | e.g. `moneyline`             |
| `grade`          | `PickGrade`  | —                                      | `A`, `B`, `C`                |
| `source`         | `PickSource` | —                                      | `manual`, `pipeline`         |
| `limit`          | `int`        | `50`                                   |                              |
| `offset`         | `int`        | `0`                                    |                              |

**Response `200 OK`** — `PickListResponse`:

```json
{
  "items": [
    {
      "pick_id": "d3c2b1a0-...",
      "user_id": "00000000-0000-4000-8000-000000000001",
      "match_id": "a1b2c3d4-...",
      "sportsbook_id": "e5f6a7b8-...",
      "run_date": "2025-06-15",
      "market": "moneyline",
      "selection": "Over 2.5",
      "odds_american": -110,
      "odds_decimal": "1.9091",
      "implied_prob": "0.5238",
      "grade": "A",
      "stake": "200.00",
      "status": "pending",
      "source": "manual",
      "closing_odds_decimal": null,
      "clv": null,
      "confirmed_at": null,
      "resolved_at": null,
      "created_at": "2025-06-15T10:00:00Z",
      "updated_at": "2025-06-15T10:00:00Z"
    }
  ],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

### 5.2 Resolver Pick — `PATCH /api/v1/picks/{pick_id}/result`

Resuelve un pick a un estado terminal (`won`, `lost`, `push`, `void`). Toda la lógica de resolución se centraliza en `execute_settlement()` (`app/services/settlement_engine.py`).

> **El body NO incluye `user_id`.** La propiedad del pick se valida internamente: si `pick.user_id` no es `None` y difiere de `DEFAULT_USER_ID` (`app/core/config.py`), el engine rechaza con `409 PICK_OWNERSHIP_MISMATCH`. El frontend no necesita enviar ni gestionar este campo.

**Path Parameters:**

| Param     | Type   |
|-----------|--------|
| `pick_id` | `UUID` |

**Request Body** — `PickResolve`:

```json
{
  "status": "won",
  "closing_odds_decimal": "1.85"
}
```

| Field                  | Type         | Required | Notes                                      |
|------------------------|--------------|----------|--------------------------------------------|
| `status`               | `PickStatus` | Sí       | `won`, `lost`, `push`, `void` (no `pending`) |
| `closing_odds_decimal` | `Decimal`    | No       | Odds de cierre para cálculo de CLV         |

**Response `200 OK`** — `PickResponse` (pick actualizado con estado terminal):

```json
{
  "pick_id": "d3c2b1a0-...",
  "user_id": "00000000-0000-4000-8000-000000000001",
  "match_id": "a1b2c3d4-...",
  "sportsbook_id": "e5f6a7b8-...",
  "run_date": "2025-06-15",
  "market": "moneyline",
  "selection": "Over 2.5",
  "odds_american": -110,
  "odds_decimal": "1.9091",
  "implied_prob": "0.5238",
  "grade": "A",
  "stake": "200.00",
  "status": "won",
  "source": "manual",
  "closing_odds_decimal": "1.85",
  "clv": "0.034",
  "confirmed_at": "2025-06-15T11:00:00Z",
  "resolved_at": "2025-06-15T18:30:00Z",
  "created_at": "2025-06-15T10:00:00Z",
  "updated_at": "2025-06-15T18:30:00Z"
}
```

**Campos del `PickResponse`** (referencia: `app/schemas/pick.py`):

| Campo                  | Tipo               | Nullable | Notes                                  |
|------------------------|--------------------|----------|----------------------------------------|
| `pick_id`              | `UUID`             | No       | PK                                     |
| `user_id`              | `UUID`             | Sí       | `null` si no se asignó propietario     |
| `match_id`             | `UUID`             | No       |                                        |
| `sportsbook_id`        | `UUID`             | No       |                                        |
| `run_date`             | `date`             | No       | Fecha de operación                     |
| `market`               | `str`              | No       |                                        |
| `selection`            | `str`              | No       |                                        |
| `odds_american`        | `int`              | No       |                                        |
| `odds_decimal`         | `Decimal`          | No       |                                        |
| `implied_prob`         | `Decimal`          | No       |                                        |
| `grade`                | `PickGrade`        | No       | `A`, `B`, `C`                          |
| `stake`                | `Decimal`          | Sí       | `null` si no se definió stake          |
| `status`               | `PickStatus`       | No       | Estado terminal post-resolución        |
| `source`               | `PickSource`       | No       | `manual`, `pipeline`                   |
| `closing_odds_decimal` | `Decimal`          | Sí       | Presente si se envió en el request     |
| `clv`                  | `Decimal`          | Sí       | Calculado si hay `closing_odds_decimal`|
| `confirmed_at`         | `datetime`         | Sí       |                                        |
| `resolved_at`          | `datetime`         | Sí       | Timestamp de resolución                |
| `created_at`           | `datetime`         | No       |                                        |
| `updated_at`           | `datetime`         | No       |                                        |

**Errores posibles:**

| HTTP | Code                        | Cuándo                                               |
|------|-----------------------------|----------------------------------------------------- |
| 404  | `PICK_NOT_FOUND`            | No existe pick con ese ID                            |
| 409  | `TERMINAL_STATE_CONFLICT`   | Pick ya resuelto a otro estado terminal              |
| 409  | `PICK_OWNERSHIP_MISMATCH`   | `pick.user_id` no es `None` y difiere de `DEFAULT_USER_ID` |
| 409  | `SETTLEMENT_ALREADY_DECIDED`| Void no puede sobrescribir payout/loss ya registrado |
| 409  | `SETTLEMENT_RACE_CONDITION` | Settlement concurrente detectado (unique constraint) |

---

## 6. Reglas Transversales de UI

### 6.1 Idempotencia en Operaciones de Escritura

**Regla**: Todo `POST` que cree o mueva dinero **debe** incluir el header `X-Idempotency-Key` (o `Idempotency-Key` para picks).

**Estado actual del backend:**

| Endpoint                   | Header soportado    | Estado         |
|----------------------------|---------------------|----------------|
| `POST /api/v1/picks/`     | `Idempotency-Key`   | Implementado   |
| `POST /api/v1/transactions/` | `X-Idempotency-Key` | Pendiente (drift gate activo, idempotencia por implementar) |
| Depósitos/retiros futuros  | `X-Idempotency-Key` | Pendiente      |

**Implementación en frontend:**

```typescript
const idempotencyKey = crypto.randomUUID();

const response = await fetch(`${API_BASE}/api/v1/picks/`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Idempotency-Key": idempotencyKey,
  },
  body: JSON.stringify(pickPayload),
});

// Si el response incluye X-Idempotent-Replay: "true",
// la operación ya fue procesada previamente (safe replay)
const isReplay = response.headers.get("X-Idempotent-Replay") === "true";
```

**Errores de idempotencia:**

| HTTP | Code                       | Significado                                          | Acción del frontend                  |
|------|----------------------------|------------------------------------------------------|--------------------------------------|
| 409  | `IDEMPOTENCY_IN_PROGRESS`  | Request duplicado aún procesándose                   | Retry con backoff (misma key)        |
| 409  | `IDEMPOTENCY_BODY_MISMATCH`| Misma key con body diferente                         | Generar nueva key; alertar al usuario|
| 503  | —                          | Redis caído (fail closed — no se permite crear)      | Mostrar "Servicio temporalmente degradado" |

### 6.2 Drift Gate — Protección Financiera

**Regla**: Cuando el sistema detecta corrupción en el estado financiero (ledger no cuadra con balances), bloquea todas las operaciones de dinero.

**Cómo llega al frontend:**

```
HTTP 409 Conflict
```

```json
{
  "error": {
    "code": "FINANCIAL_STATE_CORRUPTED",
    "message": "Ledger-derived total does not match wallet row; manual audit required before money movement.",
    "field": null,
    "meta": {
      "user_id": "00000000-0000-4000-8000-000000000001",
      "ledger_drift": "150.00",
      "ledger_expected": "17840.50",
      "ledger_actual": "17690.50"
    }
  }
}
```

**Otro código de Drift Gate a nivel sistema:**

```
HTTP 409 Conflict
```

```json
{
  "error": {
    "code": "CASHFLOW_BLOCKED_CRITICAL_DRIFT",
    "message": "Deposits and withdrawals are disabled until all ledger mismatches are resolved (manual audit).",
    "field": null,
    "meta": {
      "critical_users": 1
    }
  }
}
```

**Acción del frontend cuando recibe `409` con estos códigos:**

1. Deshabilitar los botones de depósito/retiro.
2. Mostrar un banner de alerta: _"El sistema financiero está en modo protegido. Contacta al administrador."_
3. En el panel de admin: indicar con badge rojo y dirigir a la pantalla de reconciliación.

### 6.3 Formato Estándar de Error

Todos los errores del API siguen esta estructura (`ErrorResponse`):

```json
{
  "error": {
    "code": "ERROR_CODE_HERE",
    "message": "Human-readable description",
    "field": "optional_field_name",
    "meta": {}
  }
}
```

| HTTP | Tipo               | Códigos comunes                                          |
|------|--------------------|----------------------------------------------------------|
| 400  | `BadRequestError`  | Validación de negocio                                    |
| 404  | `NotFoundError`    | `PICK_NOT_FOUND`, `USER_BALANCE_NOT_FOUND`              |
| 409  | `ConflictError`    | `FINANCIAL_STATE_CORRUPTED`, `CASHFLOW_BLOCKED_CRITICAL_DRIFT`, `REPAIR_UNSAFE_STATE`, `IDEMPOTENCY_*`, `TERMINAL_STATE_CONFLICT`, `PICK_OWNERSHIP_MISMATCH`, `SETTLEMENT_ALREADY_DECIDED`, `SETTLEMENT_RACE_CONDITION` |
| 422  | `UnprocessableError` / `ValidationError` | `VALIDATION_ERROR`, `INSUFFICIENT_AVAILABLE_BALANCE`, `CRITICAL_INVARIANT_BROKEN` |
| 500  | Internal           | `INTERNAL_SERVER_ERROR`                                  |
| 503  | Service Unavailable | Redis caído (idempotency/cache)                         |

---

## 7. Catálogo de Errores

### Errores financieros

| Code                              | HTTP | Trigger                                              |
|-----------------------------------|------|------------------------------------------------------|
| `FINANCIAL_STATE_CORRUPTED`       | 409  | Drift gate: ledger no cuadra con wallet (por usuario)|
| `CASHFLOW_BLOCKED_CRITICAL_DRIFT` | 409  | Drift gate: al menos un usuario CRITICAL en sistema  |
| `REPAIR_UNSAFE_STATE`             | 409  | Intento de fix cuando hay ledger mismatch            |
| `INSUFFICIENT_AVAILABLE_BALANCE`  | 422  | Stake excede balance disponible                      |
| `CRITICAL_INVARIANT_BROKEN`       | 422  | Balances serían negativos tras operación             |

### Errores de idempotencia

| Code                         | HTTP | Trigger                                     |
|------------------------------|------|---------------------------------------------|
| `IDEMPOTENCY_IN_PROGRESS`    | 409  | Request duplicado en proceso                |
| `IDEMPOTENCY_BODY_MISMATCH`  | 409  | Misma key, body diferente                   |

### Errores de picks

| Code                             | HTTP | Trigger                                         |
|----------------------------------|------|-------------------------------------------------|
| `PICK_NOT_FOUND`                 | 404  | No existe pick con ese `pick_id`                |

### Errores de settlement

| Code                             | HTTP | Trigger                                                              |
|----------------------------------|------|----------------------------------------------------------------------|
| `TERMINAL_STATE_CONFLICT`        | 409  | Pick ya en estado terminal distinto al solicitado                    |
| `PICK_OWNERSHIP_MISMATCH`        | 409  | `pick.user_id != None` y difiere de `DEFAULT_USER_ID`               |
| `SETTLEMENT_ALREADY_DECIDED`     | 409  | Void no puede sobrescribir payout/loss ya registrado                 |
| `SETTLEMENT_RACE_CONDITION`      | 409  | Settlement concurrente detectado (unique constraint violation)        |
| `SETTLEMENT_LEDGER_TYPE_MISMATCH`| 409  | Pick ya liquidado con otro outcome en ledger                         |
| `SETTLEMENT_PICK_NOT_PENDING`    | 422  | Pick no está en `pending`                                            |
| `LEDGER_SETTLEMENT_AMBIGUOUS`    | 422  | Múltiples filas de settlement para un pick                           |

### Errores de admin

| Code                       | HTTP | Trigger                                              |
|----------------------------|------|------------------------------------------------------|
| `USER_BALANCE_NOT_FOUND`   | 404  | No existe fila de balance para ese user_id           |
| `REPAIR_INVARIANT_VIOLATION`| 422 | Reparación resultaría en valores negativos           |

---

## Apéndice: Headers Especiales

| Header                      | Dirección | Usado en                       | Propósito                                |
|-----------------------------|-----------|--------------------------------|------------------------------------------|
| `Idempotency-Key`           | Request   | `POST /picks/`                 | Prevenir duplicados de picks             |
| `X-Idempotency-Key`         | Request   | Futuro: depósitos/retiros      | Prevenir duplicados de transacciones     |
| `X-Idempotent-Replay`       | Response  | `POST /picks/`                 | `"true"` si fue un replay idempotente    |
| `X-Reconciliation-Secret`   | Request   | Todos los `/admin/*`           | Autenticación de admin                   |
| `X-Fiscal-Year`             | Response  | `GET /fiscal/export/csv`       | Año fiscal del CSV exportado             |
| `X-Total-Records`           | Response  | `GET /fiscal/export/csv`       | Total de filas en el CSV                 |
