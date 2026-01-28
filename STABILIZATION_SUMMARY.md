# DB Schema Stabilization - Quick Summary

**Status**: ✅ COMPLETE

## What Was Done

Both `app32/db.py` and `app64/db.py` have been stabilized with:

### 1. Identical Schemas
- Added `created_at` column to orders_intent (was missing in app32)
- Both modules now have identical orders_intent and execution_log tables
- All columns aligned across both modules

### 2. Idempotent Initialization
- Added `_column_exists()` helper using PRAGMA table_info()
- All ALTER TABLE operations gated by column existence checks
- Index creation uses IF NOT EXISTS
- init_schema() can now be called multiple times safely

### 3. Data Integrity
- Added 4-stage migration pipeline:
  - Stage 1: Add created_at column
  - Stage 2: Add trade_day column  
  - Stage 3: Add order_id column
  - Stage 4: Backfill NULL trade_day values using DATE(ts)
- Backfill only runs if NULL values exist

### 4. Audit Issues Fixed
- ✅ Risk #1 (HIGH): app32 missing created_at → FIXED
- ✅ Risk #2 (MEDIUM): app64 unsafe index → FIXED (added IF NOT EXISTS)
- ✅ Risk #3 (MEDIUM): trade_day nullable → FIXED (added backfill logic)
- ⏳ Risk #4 (MEDIUM): ENV persistence → Out of scope (operational)
- ⏳ Risk #5 (HIGH): DB deadlock → Out of scope (requires connection pooling)

## Files Modified

```
✏️  app32/db.py      (110 lines, was 68 lines)
✏️  app64/db.py      (107 lines, was 70 lines)
✨ verify_schema_stabilization.py  (NEW - 7 automated tests)
📄 DB_SCHEMA_STABILIZATION_REPORT.md  (NEW - comprehensive report)
```

## How to Verify

```bash
# Run the verification script
python verify_schema_stabilization.py

# Expected: All 7 tests pass ✅
```

### What the Tests Check

1. **Idempotency (app32)**: init_schema() × 2 = no errors
2. **Columns Present (app32)**: All required columns in orders_intent
3. **Columns Present (app32)**: All required columns in execution_log
4. **Index Created**: idx_orders_intent_trade_day_status_action exists
5. **Insert Test**: New order gets trade_day populated
6. **Query Test**: count_sent_buy_today() works with trade_day
7. **Consistency (app64)**: Schemas match between app32 and app64

## Schema Summary

### orders_intent (Before vs After)

| Column | Before | After |
|--------|--------|-------|
| id | ✅ | ✅ |
| ts | ✅ | ✅ |
| created_at | ❌ app32 | ✅ BOTH |
| trade_day | ✅ | ✅ + backfill |
| symbol | ✅ | ✅ |
| action | ✅ | ✅ |
| ai_score | ✅ | ✅ |
| ttl_ms | ✅ | ✅ |
| params_version_id | ✅ | ✅ |
| status | ✅ | ✅ |

### execution_log (Unchanged - Already Consistent)

| Column | Status |
|--------|--------|
| id | ✅ |
| ts | ✅ |
| module | ✅ |
| symbol | ✅ |
| action | ✅ |
| decision | ✅ |
| rejection_reason | ✅ |
| ai_score | ✅ |
| params_version_id | ✅ |
| order_id | ✅ |
| context | ✅ |

## Migration Strategy

When init_schema() runs:

**Fresh Database**:
- CREATE TABLE IF NOT EXISTS runs
- All migration stages check with PRAGMA and skip (columns already in CREATE TABLE)
- Index created with IF NOT EXISTS

**Existing Database** (before changes):
- CREATE TABLE IF NOT EXISTS skips (table exists)
- Migration 1: Adds created_at (PRAGMA detects it's missing)
- Migration 2: Adds trade_day (PRAGMA detects it's missing)
- Migration 3: Adds order_id to execution_log (if missing)
- Migration 4: Backfills NULL trade_day values from ts
- Index created with IF NOT EXISTS (safe to re-run)

**Subsequent Calls** (2nd, 3rd, etc):
- All migrations PRAGMA-gated and skip
- Index IF NOT EXISTS skips
- No errors, fully idempotent

## No Breaking Changes

✅ No trading logic modified  
✅ No columns deleted  
✅ No queries changed  
✅ No function signatures changed  
✅ All changes are schema-level only  
✅ Fully backward compatible  

## Deployment

1. Deploy modified app32/db.py
2. Deploy modified app64/db.py
3. Restart either app (will auto-initialize)
4. Done - migrations run automatically

## Next Steps

Optional but recommended:
- Run `verify_schema_stabilization.py` to confirm all tests pass
- Monitor first few hours of trading for normal behavior
- (Future) Address operational risks #4-5 with connection pooling

---

**All deliverables ready in project root:**
- `verify_schema_stabilization.py` - Run this to verify
- `DB_SCHEMA_STABILIZATION_REPORT.md` - Full technical report
