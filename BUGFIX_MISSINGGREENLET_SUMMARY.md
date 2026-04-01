# 🐛 SQLAlchemy MissingGreenlet Bug Fix — Settlement Endpoint

## Problem Statement

The endpoint `PATCH /api/v1/picks/{pick_id}/result` was failing with:
```
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called; 
can't call await_only() here. Was IO attempted in an unexpected place?
```

## Root Cause Analysis

### The Exact Line That Caused the Error:

**File:** `app/services/pick_service.py`  
**Line:** 110 (inside `DomainValidator.validate()` method)  
**Code:**
```python
for label, ts in (
    ("created_at", pick.created_at),
    ("updated_at", pick.updated_at),      # ← THIS LINE TRIGGERED LAZY LOAD
    ("resolved_at", pick.resolved_at),
    ("confirmed_at", pick.confirmed_at),
):
```

### Why It Failed:

1. **Nested Transaction Context:** In `settlement_engine.py` line 71, we use `async with db.begin_nested()` to create a savepoint
2. **Attribute Expiration:** After database flush operations, SQLAlchemy marks object attributes as "expired"
3. **Lazy Loading in Async:** When `DomainValidator.validate()` tried to access `pick.updated_at` at line 110, SQLAlchemy attempted to lazy-load the attribute
4. **Async Context Lost:** The lazy load tried to execute a synchronous database query in an async session, causing the MissingGreenlet error

### The Error Chain:

```
routers/picks.py:155 (resolve_pick endpoint)
  → services/pick_service.py:444 (resolve_pick)
    → services/settlement_engine.py:146 (execute_settlement > record_settlement)
      → services/ledger_service.py:246 (record_settlement > validate)
        → services/pick_service.py:110 (DomainValidator.validate)
          ❌ pick.updated_at access triggers lazy load
            → MissingGreenlet exception
```

## Solution Applied

### Change #1: Add Eager Loading to Query (settlement_engine.py)

**File:** `app/services/settlement_engine.py`  
**Lines:** 9-11, 72-79

```python
# Added import
from sqlalchemy.orm import selectinload

# Modified query to eager-load relationships
async with db.begin_nested():
    result = await db.execute(
        select(Pick)
        .options(selectinload(Pick.match))
        .options(selectinload(Pick.sportsbook))
        .where(Pick.pick_id == pick_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    pick = result.scalar_one_or_none()
```

**Purpose:** Preload `match` and `sportsbook` relationships to prevent lazy loading later.

### Change #2: Refresh Timestamp Attributes Before Validation (ledger_service.py)

**File:** `app/services/ledger_service.py`  
**Lines:** 232-235

```python
now = datetime.now(timezone.utc)

# Ensure timestamp attributes are loaded before we modify them (avoid lazy load in async)
await db.refresh(pick, attribute_names=['created_at', 'updated_at', 'confirmed_at'])

pick.status = status
pick.resolved_at = now
# ... rest of settlement logic
```

**Purpose:** Explicitly refresh the timestamp attributes that `DomainValidator.validate()` will access, preventing lazy loading.

**Why This Works:**
- `db.refresh()` with `attribute_names` parameter loads only the specified attributes
- We refresh BEFORE setting `resolved_at`, so we don't overwrite our own changes
- This ensures all attributes accessed by the validator are already loaded in memory

## Testing

### Test Case: Settlement Flow
```bash
# Create pick
POST /api/v1/picks/
{
  "user_id": "00000000-0000-4000-8000-000000000001",
  "match_id": "2db8501a-a778-482c-b7af-0f83989a172b",
  "sportsbook_id": "2c723279-7108-43c2-a655-fbefcf12b616",
  "market": "moneyline",
  "selection": "Away 1",
  "odds_american": 150,
  "stake": 5.00
}

# Settle pick (THIS NOW WORKS! ✅)
PATCH /api/v1/picks/4e262621-e361-4c97-ad36-0cd73135bf9e/result
{
  "status": "won",
  "closing_odds_decimal": "2.40"
}
```

### Results:
- ✅ Pick settled successfully
- ✅ Status changed from `pending` to `won`
- ✅ Financial operations executed atomically
- ✅ Ledger entries created correctly
- ✅ Balance updates reflected accurately

## Key Learnings

1. **SQLAlchemy 2.0 Async Pitfall:** In async sessions, accessing expired attributes triggers lazy loading, which fails if not in an async context
   
2. **Nested Transactions:** `db.begin_nested()` creates a savepoint but doesn't prevent attribute expiration after flush operations

3. **The Fix Pattern:** For async SQLAlchemy operations that access object attributes after modifications:
   - Use `await db.refresh(obj, attribute_names=[...])` before accessing attributes
   - OR use `.execution_options(populate_existing=True)` in the initial query
   - OR eager-load relationships with `.options(selectinload(...))`

4. **When to Apply:**
   - Inside nested transactions that modify database state
   - Before validation logic that accesses multiple object attributes
   - When passing objects between service layers after flush operations

## Files Modified

1. `app/services/settlement_engine.py` (Added eager loading + populate_existing)
2. `app/services/ledger_service.py` (Added explicit refresh before validation)

## Impact

- **Before:** Settlement endpoint completely non-functional (HTTP 500)
- **After:** Settlement endpoint fully operational with correct financial atomicity
- **Performance:** Minimal impact (one additional refresh query per settlement)
- **Safety:** No changes to business logic or financial calculations

---

**Fixed by:** Senior Python/SQLAlchemy Expert Engineer (Copilot AI)  
**Date:** 2026-03-31  
**Validated:** Game Day 6.4 settlement tests passing ✅
