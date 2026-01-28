# DB Schema Stabilization - SQL Reference

**For database administrators and auditors**

---

## Schema Definition Changes

### orders_intent Table

#### BEFORE (app32/db.py only)
```sql
CREATE TABLE IF NOT EXISTS orders_intent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    trade_day TEXT,                    -- ⚠️ No created_at column here
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    ai_score REAL NOT NULL,
    ttl_ms INTEGER NOT NULL,
    params_version_id TEXT NOT NULL,
    status TEXT NOT NULL
);
```

#### AFTER (both app32 and app64)
```sql
CREATE TABLE IF NOT EXISTS orders_intent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    created_at TEXT,                   -- ✅ NEW: Added (was missing in app32)
    trade_day TEXT,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    ai_score REAL NOT NULL,
    ttl_ms INTEGER NOT NULL,
    params_version_id TEXT NOT NULL,
    status TEXT NOT NULL
);
```

**Changes**: Added `created_at TEXT` column after `ts` column

---

## Migration Operations

### Migration 1: Add created_at to orders_intent

```sql
-- Check: Does column exist?
PRAGMA table_info(orders_intent);
-- Look for: created_at in result set

-- Migration (only if not present):
ALTER TABLE orders_intent ADD COLUMN created_at TEXT;

-- Verify:
PRAGMA table_info(orders_intent);
```

**Impact**:
- **Fresh DB**: Skipped (column already in CREATE TABLE)
- **Existing DB (before)**: EXECUTES (column missing)
- **Existing DB (after)**: Skipped (column already exists)
- **Data impact**: Zero (new column defaults to NULL)

---

### Migration 2: Add trade_day to orders_intent

```sql
-- Check: Does column exist?
PRAGMA table_info(orders_intent);
-- Look for: trade_day in result set

-- Migration (only if not present):
ALTER TABLE orders_intent ADD COLUMN trade_day TEXT;

-- Verify:
PRAGMA table_info(orders_intent);
```

**Impact**:
- **Fresh DB**: Skipped (column already in CREATE TABLE)
- **Existing DB**: Usually skipped (column likely already exists from previous migration)
- **Data impact**: Zero (new column defaults to NULL)

---

### Migration 3: Add order_id to execution_log

```sql
-- Check: Does column exist?
PRAGMA table_info(execution_log);
-- Look for: order_id in result set

-- Migration (only if not present):
ALTER TABLE execution_log ADD COLUMN order_id TEXT;

-- Verify:
PRAGMA table_info(execution_log);
```

**Impact**:
- **Fresh DB**: Skipped (column already in CREATE TABLE)
- **Existing DB**: May EXECUTE (depends on when execution_log was created)
- **Data impact**: Zero (new column defaults to NULL)

---

### Migration 4: Backfill NULL trade_day values

```sql
-- Step 1: Count NULL values
SELECT COUNT(*) FROM orders_intent WHERE trade_day IS NULL;
-- Example result: 1523 (depends on data)

-- Step 2: Backfill (only if count > 0)
UPDATE orders_intent SET trade_day = DATE(ts) WHERE trade_day IS NULL;

-- Step 3: Verify backfill
SELECT COUNT(*) FROM orders_intent WHERE trade_day IS NULL;
-- After: 0

-- Step 4: Sample verification
SELECT ts, trade_day FROM orders_intent WHERE id <= 5;
-- Example result:
-- ts                    | trade_day
-- 2026-01-15 10:30:00   | 2026-01-15
-- 2026-01-15 11:45:00   | 2026-01-15
-- 2026-01-16 09:00:00   | 2026-01-16
```

**Details**:
- Uses SQLite `DATE()` function to extract date from timestamp
- Works because `ts` format is "YYYY-MM-DD HH:MM:SS" (SQLite DATE() compatible)
- Only executes if NULL values exist

**Impact**:
- **Fresh DB**: Skipped (no NULL values)
- **Existing DB with NULLs**: EXECUTES (backfills all NULL values)
- **Existing DB without NULLs**: Skipped (COUNT = 0)
- **Data impact**: POSITIVE (populates missing dates)

---

### Index Creation: DAILY_LIMIT Optimization

#### BEFORE (app64 only - unsafe)
```sql
-- ❌ Dangerous: No IF NOT EXISTS
CREATE INDEX idx_orders_intent_trade_day_status_action 
ON orders_intent (trade_day, status, action);

-- Problem: Calling twice will error: "index ... already exists"
```

#### AFTER (both app32 and app64 - safe)
```sql
-- ✅ Safe: IF NOT EXISTS prevents re-creation errors
CREATE INDEX IF NOT EXISTS idx_orders_intent_trade_day_status_action 
ON orders_intent (trade_day, status, action);

-- Safe: Can call any number of times without error
```

**Index Details**:
- **Name**: `idx_orders_intent_trade_day_status_action`
- **Table**: `orders_intent`
- **Columns**: `(trade_day, status, action)`
- **Purpose**: Optimizes DAILY_LIMIT queries
- **Type**: B-tree (default)

**Usage in Queries**:
```sql
-- This query will use the index:
SELECT COUNT(*) FROM orders_intent 
WHERE trade_day = '2026-01-28' 
  AND status = 'SENT' 
  AND action = 'BUY';

-- Index acceleration: ✅ YES (covers all WHERE conditions)

-- This query will NOT use the index:
SELECT COUNT(*) FROM orders_intent 
WHERE ts LIKE '2026-01-28%';

-- Better alternative:
SELECT COUNT(*) FROM orders_intent 
WHERE trade_day = '2026-01-28';

-- Index acceleration: ✅ YES (uses trade_day column)
```

---

## Complete Migration Script (Standalone)

If you need to manually run all migrations:

```sql
-- ===== MANUAL MIGRATION SCRIPT =====
-- Run this if init_schema() is not being called

-- 1. Check current schema
.headers on
PRAGMA table_info(orders_intent);
PRAGMA table_info(execution_log);

-- 2. Add created_at to orders_intent (if missing)
BEGIN TRANSACTION;
ALTER TABLE orders_intent ADD COLUMN created_at TEXT;
COMMIT;
-- Note: If column exists, will error - can safely ignore

-- 3. Verify created_at added
PRAGMA table_info(orders_intent);

-- 4. Backfill NULL trade_day values
BEGIN TRANSACTION;
UPDATE orders_intent SET trade_day = DATE(ts) WHERE trade_day IS NULL;
COMMIT;

-- 5. Verify backfill
SELECT COUNT(*) FROM orders_intent WHERE trade_day IS NULL;

-- 6. Create index
CREATE INDEX IF NOT EXISTS idx_orders_intent_trade_day_status_action 
ON orders_intent (trade_day, status, action);

-- 7. Verify all migrations complete
SELECT 'orders_intent columns:' as check_type;
PRAGMA table_info(orders_intent);
SELECT '' as separator;
SELECT 'execution_log columns:' as check_type;
PRAGMA table_info(execution_log);
SELECT '' as separator;
SELECT 'Indexes:' as check_type;
SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';
SELECT '' as separator;
SELECT 'Data integrity:' as check_type;
SELECT COUNT(*) as null_trade_day FROM orders_intent WHERE trade_day IS NULL;
```

---

## Schema Audit Queries

### Table Structure Verification

```sql
-- Check orders_intent columns
PRAGMA table_info(orders_intent);

-- Expected columns (ALL should be present):
-- cid | name                 | type | notnull | dflt_value | pk
-- 0   | id                   | INT  | 0       | NULL       | 1
-- 1   | ts                   | TEXT | 1       | NULL       | 0
-- 2   | created_at           | TEXT | 0       | NULL       | 0  ← Check this
-- 3   | trade_day            | TEXT | 0       | NULL       | 0
-- 4   | symbol               | TEXT | 1       | NULL       | 0
-- 5   | action               | TEXT | 1       | NULL       | 0
-- 6   | ai_score             | REAL | 1       | NULL       | 0
-- 7   | ttl_ms               | INT  | 1       | NULL       | 0
-- 8   | params_version_id    | TEXT | 1       | NULL       | 0
-- 9   | status               | TEXT | 1       | NULL       | 0

-- Check execution_log columns
PRAGMA table_info(execution_log);

-- Expected columns (ALL should be present):
-- cid | name                 | type | notnull | dflt_value | pk
-- 0   | id                   | INT  | 0       | NULL       | 1
-- 1   | ts                   | TEXT | 1       | NULL       | 0
-- 2   | module               | TEXT | 1       | NULL       | 0
-- 3   | symbol               | TEXT | 1       | NULL       | 0
-- 4   | action               | TEXT | 1       | NULL       | 0
-- 5   | decision             | TEXT | 0       | NULL       | 0
-- 6   | rejection_reason     | TEXT | 0       | NULL       | 0
-- 7   | ai_score             | REAL | 0       | NULL       | 0
-- 8   | params_version_id    | TEXT | 1       | NULL       | 0
-- 9   | order_id             | TEXT | 0       | NULL       | 0  ← Check this
-- 10  | context              | TEXT | 0       | NULL       | 0
```

### Index Verification

```sql
-- List all indexes
SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='orders_intent';

-- Should show:
-- type  | name                                         | tbl_name      | rootpage | sql
-- index | idx_orders_intent_trade_day_status_action   | orders_intent | NNN      | CREATE INDEX IF NOT EXISTS...

-- Check index columns
PRAGMA index_info(idx_orders_intent_trade_day_status_action);

-- Should show:
-- seqno | cid | name
-- 0     | 3   | trade_day    ← Column 3 (trade_day)
-- 1     | 9   | status       ← Column 9 (status)
-- 2     | 5   | action       ← Column 5 (action)
```

### Data Integrity Checks

```sql
-- Count NULL values in critical columns
SELECT 
    COUNT(*) as total_orders,
    SUM(CASE WHEN created_at IS NULL THEN 1 ELSE 0 END) as null_created_at,
    SUM(CASE WHEN trade_day IS NULL THEN 1 ELSE 0 END) as null_trade_day
FROM orders_intent;

-- Should show:
-- total_orders | null_created_at | null_trade_day
-- 12345        | 0 (or N > 0)    | 0              ← CRITICAL: trade_day must be 0

-- Sample data
SELECT id, ts, created_at, trade_day, symbol, action, status 
FROM orders_intent 
ORDER BY id DESC 
LIMIT 10;

-- Check daily limits working (using trade_day)
SELECT trade_day, action, status, COUNT(*) as count
FROM orders_intent
WHERE trade_day >= date('now', '-7 days')
GROUP BY trade_day, action, status
ORDER BY trade_day DESC;
```

---

## Performance Impact

### Before Migration
```sql
-- Query WITHOUT index (older app32 without index)
EXPLAIN QUERY PLAN 
SELECT COUNT(*) FROM orders_intent 
WHERE trade_day = '2026-01-28' AND status = 'SENT' AND action = 'BUY';

-- Result: SCAN TABLE orders_intent (full table scan - SLOW)
```

### After Migration
```sql
-- Query WITH index (both app32 and app64 now have index)
EXPLAIN QUERY PLAN 
SELECT COUNT(*) FROM orders_intent 
WHERE trade_day = '2026-01-28' AND status = 'SENT' AND action = 'BUY';

-- Result: SEARCH TABLE orders_intent USING INDEX idx_orders_intent_trade_day_status_action (FAST)
```

**Performance Improvement**: ~100-1000x faster on large tables (100k+ rows)

---

## Migration Timeline

### Execution Order
```
init_schema() called
├─ CREATE TABLE IF NOT EXISTS (skips if exists)
├─ Migration 1: created_at (check with PRAGMA, add if missing)
├─ Migration 2: trade_day (check with PRAGMA, add if missing)
├─ Migration 3: order_id (check with PRAGMA, add if missing)
├─ Migration 4: Backfill NULL trade_day (count and update if count > 0)
└─ Index creation (IF NOT EXISTS safe)

Total time: 50-200ms (depending on backfill size)
```

### Idempotency
```
Call 1: All stages execute (or skip if already done)
Call 2: All PRAGMA gates skip migrations, IF NOT EXISTS skips index
Call 3+: Same as Call 2

Result: ✅ Safe to call multiple times
```

---

## Rollback SQL

If you need to manually rollback (not recommended):

```sql
-- ⚠️ WARNING: This removes columns - data loss!

-- DO NOT RUN these unless absolutely necessary

-- Remove created_at from orders_intent (loses column data!)
-- ALTER TABLE orders_intent DROP COLUMN created_at;

-- Better approach: Create new table without column
-- CREATE TABLE orders_intent_new AS 
-- SELECT id, ts, trade_day, symbol, action, ai_score, ttl_ms, params_version_id, status
-- FROM orders_intent;
-- DROP TABLE orders_intent;
-- ALTER TABLE orders_intent_new RENAME TO orders_intent;

-- Drop index (safe, no data loss)
DROP INDEX IF EXISTS idx_orders_intent_trade_day_status_action;

-- Restore index creation without IF NOT EXISTS (NOT RECOMMENDED)
CREATE INDEX idx_orders_intent_trade_day_status_action 
ON orders_intent (trade_day, status, action);
```

---

## Verification Queries

Run these after deployment to verify all changes:

```sql
-- 1. Verify created_at column exists
SELECT COUNT(*) as created_at_exists 
FROM pragma_table_info('orders_intent') 
WHERE name = 'created_at';
-- Expected: 1

-- 2. Verify trade_day column exists
SELECT COUNT(*) as trade_day_exists 
FROM pragma_table_info('orders_intent') 
WHERE name = 'trade_day';
-- Expected: 1

-- 3. Verify order_id column exists
SELECT COUNT(*) as order_id_exists 
FROM pragma_table_info('execution_log') 
WHERE name = 'order_id';
-- Expected: 1

-- 4. Verify NO NULL trade_day values
SELECT COUNT(*) as null_trade_day_count 
FROM orders_intent 
WHERE trade_day IS NULL;
-- Expected: 0

-- 5. Verify index exists
SELECT COUNT(*) as index_exists 
FROM sqlite_master 
WHERE type = 'index' AND name = 'idx_orders_intent_trade_day_status_action';
-- Expected: 1

-- 6. Verify all checks passed
SELECT 
    (SELECT COUNT(*) FROM pragma_table_info('orders_intent') WHERE name = 'created_at') as created_at_col,
    (SELECT COUNT(*) FROM pragma_table_info('orders_intent') WHERE name = 'trade_day') as trade_day_col,
    (SELECT COUNT(*) FROM pragma_table_info('execution_log') WHERE name = 'order_id') as order_id_col,
    (SELECT COUNT(*) FROM orders_intent WHERE trade_day IS NULL) as null_trade_day,
    (SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' AND name = 'idx_orders_intent_trade_day_status_action') as index_exists;

-- Expected result:
-- created_at_col | trade_day_col | order_id_col | null_trade_day | index_exists
-- 1              | 1             | 1            | 0              | 1
```

---

## Emergency: Connection String

If you need to access the database directly:

```
Location: shared/data/trading.db
Type: SQLite3
Encoding: UTF-8
```

**Using sqlite3 CLI**:
```bash
sqlite3 shared/data/trading.db
```

**Using Python**:
```python
import sqlite3
conn = sqlite3.connect('shared/data/trading.db')
cursor = conn.cursor()
cursor.execute("SELECT * FROM orders_intent LIMIT 1")
print(cursor.fetchone())
```

---

**Reference**: DB_SCHEMA_STABILIZATION_REPORT.md (full technical details)
