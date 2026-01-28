# DB Schema Stabilization - Deployment Checklist

**Project**: QUANT-EVO Trading System  
**Date**: 2026-01-28  
**Status**: ✅ READY FOR DEPLOYMENT

---

## Pre-Deployment Verification

### Step 1: Code Review
- [ ] Read `BEFORE_AFTER_COMPARISON.md` for detailed changes
- [ ] Verify both db.py files have `_column_exists()` helper (lines 20-25)
- [ ] Verify both db.py files have expanded `init_schema()` (lines 27-110)
- [ ] Verify app64/db.py index uses `CREATE INDEX IF NOT EXISTS`
- [ ] Confirm all migrations are PRAGMA-gated

**Command to verify**:
```bash
grep -A 5 "def _column_exists" app32/db.py app64/db.py
grep "CREATE INDEX IF NOT EXISTS" app32/db.py app64/db.py
```

### Step 2: Automated Testing
- [ ] Run verification script: `python verify_schema_stabilization.py`
- [ ] Confirm all 7 tests PASS ✅
- [ ] Check for any error messages

**Expected output**:
```
✅ ALL TESTS PASSED - Schema stabilization successful
```

### Step 3: Manual Inspection
- [ ] Open app32/db.py in editor
  - [ ] Line 24: Verify `created_at TEXT,` in CREATE TABLE
  - [ ] Line 70: Verify `_column_exists(conn, 'orders_intent', 'created_at')`
  - [ ] Line 99: Verify `UPDATE orders_intent SET trade_day = DATE(ts)`
- [ ] Open app64/db.py in editor
  - [ ] Line 24: Verify `created_at TEXT,` in CREATE TABLE (should already be there)
  - [ ] Line 101: Verify `CREATE INDEX IF NOT EXISTS` (now fixed)
  - [ ] Line 95: Verify `UPDATE orders_intent SET trade_day = DATE(ts)`

### Step 4: No Regression Check
- [ ] Verify `connect()` function unchanged
- [ ] Verify `get_kst_date()` function unchanged
- [ ] Verify no changes to app32/main.py trading logic
- [ ] Verify no changes to app64/signal_engine.py signal logic

---

## Deployment Steps

### Step 1: Backup Current Database
```bash
# Create backup of current database
cp shared/data/trading.db shared/data/trading.db.backup.$(date +%s)

# Verify backup exists
ls -lh shared/data/trading.db*
```

### Step 2: Deploy Code Changes

**Option A: Manual Copy**
```bash
# Backup original files
cp app32/db.py app32/db.py.backup
cp app64/db.py app64/db.py.backup

# Copy new versions (already updated in workspace)
# No action needed - files are ready
```

**Option B: Git Deploy**
```bash
git status  # Should show app32/db.py and app64/db.py modified
git diff app32/db.py  # Review changes
git diff app64/db.py  # Review changes
git add app32/db.py app64/db.py
git commit -m "DB schema stabilization: idempotent migrations, identical schemas"
git push
```

### Step 3: Restart Services

**Option A: Restart app32/main.py**
```bash
# Kill current process
pkill -f app32/main.py

# Restart with new db.py (will auto-initialize schema)
python app32/main.py &

# Monitor startup logs
tail -f logs/app32.log  # or check console output
```

**Option B: Restart app64/signal_engine.py**
```bash
# Kill current process
pkill -f app64/signal_engine.py

# Restart with new db.py (will auto-initialize schema)
python app64/signal_engine.py &

# Monitor startup logs
tail -f logs/app64.log  # or check console output
```

### Step 4: Verify Database Migrations

After restart, check database state:

```python
import sqlite3

conn = sqlite3.connect('shared/data/trading.db')
cursor = conn.execute("PRAGMA table_info(orders_intent)")
columns = {row[1]: row[2] for row in cursor.fetchall()}

print("orders_intent columns:")
for col in sorted(columns.keys()):
    print(f"  - {col}")

# Should include:
# - created_at
# - trade_day
# All columns should be present

# Check for NULL trade_day values
null_count = conn.execute("SELECT COUNT(*) FROM orders_intent WHERE trade_day IS NULL").fetchone()[0]
print(f"\nNULL trade_day values: {null_count}")
# Should be: 0 (all backfilled)

# Check index exists
index = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_orders_intent_trade_day_status_action'"
).fetchone()
print(f"\nIndex exists: {index is not None}")
# Should be: True

conn.close()
```

### Step 5: Monitor Trading Operations

After deployment, monitor for issues:

- [ ] Trading orders placing normally
- [ ] No database errors in logs
- [ ] Daily limits (`count_sent_buy_today()`) working
- [ ] Order status updates working
- [ ] Execution log recording events
- [ ] No NULL values in trade_day column

**Sample monitoring queries**:
```python
import sqlite3

conn = sqlite3.connect('shared/data/trading.db')

# Count orders by status
status_counts = conn.execute(
    "SELECT status, COUNT(*) FROM orders_intent GROUP BY status"
).fetchall()
print("Orders by status:")
for status, count in status_counts:
    print(f"  {status}: {count}")

# Check today's buy orders
today = "2026-01-28"
buy_count = conn.execute(
    "SELECT COUNT(*) FROM orders_intent WHERE trade_day=? AND action='BUY' AND status='SENT'",
    (today,)
).fetchone()[0]
print(f"\nBUY orders today: {buy_count}")

# Check for NULL values (should be 0)
null_trade_day = conn.execute("SELECT COUNT(*) FROM orders_intent WHERE trade_day IS NULL").fetchone()[0]
null_created_at = conn.execute("SELECT COUNT(*) FROM orders_intent WHERE created_at IS NULL").fetchone()[0]
print(f"\nData integrity:")
print(f"  NULL trade_day: {null_trade_day} (should be 0)")
print(f"  NULL created_at: {null_created_at} (OK if 0 or >0)")

conn.close()
```

---

## Post-Deployment Verification

### Checklist
- [ ] App starts without errors
- [ ] Database migrations run (check console output for "[DB]" messages)
- [ ] Trading continues normally
- [ ] No NULL values in trade_day column
- [ ] Daily limits working (`count_sent_buy_today()` accurate)
- [ ] New orders have created_at populated
- [ ] Execution log records properly
- [ ] Monitor for 1+ hour of trading

### Success Indicators
```
✅ App starts up
✅ Console shows: "[DB] Backfilled X NULL trade_day values"
✅ No SQLite errors in logs
✅ Trading orders placing normally
✅ DAILY_LIMIT checks working
✅ Database queries completing fast (<100ms)
```

### Failure Indicators
```
❌ App crashes on startup
❌ "CREATE INDEX already exists" error
❌ "column already exists" error (should be skipped)
❌ Trading orders failing to place
❌ Query timeout errors
```

---

## Rollback Procedure

If issues occur:

### Quick Rollback
```bash
# Restore backup database
cp shared/data/trading.db.backup.TIMESTAMP shared/data/trading.db

# Restore original db.py files
cp app32/db.py.backup app32/db.py
cp app64/db.py.backup app64/db.py

# Restart app
pkill -f app32/main.py
python app32/main.py &
```

### Via Git
```bash
# Revert database files
git checkout app32/db.py app64/db.py

# Restart
pkill -f app32/main.py
python app32/main.py &
```

---

## Support Information

### Key Contacts
- Database changes: See `DB_SCHEMA_STABILIZATION_REPORT.md`
- Testing: Run `verify_schema_stabilization.py`
- Troubleshooting: See section below

### Troubleshooting

**Issue**: "sqlite3.OperationalError: table orders_intent already has a column named created_at"

**Solution**: 
- This error should NOT occur (PRAGMA gate prevents it)
- If it does occur, it indicates the PRAGMA check failed
- Check: `PRAGMA table_info(orders_intent)` output
- If created_at is already present, safe to ignore
- Run `verify_schema_stabilization.py` to diagnose

---

**Issue**: "sqlite3.OperationalError: index idx_orders_intent_trade_day_status_action already exists"

**Solution**:
- This error should NOT occur in app32 (IF NOT EXISTS added)
- In app64 (before fix), this was a known issue - now fixed
- If it occurs after deployment, something went wrong
- Verify: `grep "CREATE INDEX IF NOT EXISTS" app64/db.py`
- Should show: `CREATE INDEX IF NOT EXISTS idx_orders_intent_trade_day_status_action`

---

**Issue**: "AttributeError: module 'app32.db' has no attribute '_column_exists'"

**Solution**:
- Module cache may be stale
- Restart Python/app completely
- Verify: `grep "def _column_exists" app32/db.py`
- Should show function at line 20

---

**Issue**: Database very slow after deployment

**Solution**:
- Check if backfill is still running (LARGE NULL backfill can take time)
- Check: `SELECT COUNT(*) WHERE trade_day IS NULL` (should decrease over time)
- If backfill complete and still slow:
  - Verify index created: `PRAGMA index_info(idx_orders_intent_trade_day_status_action)`
  - Reindex if needed: `REINDEX idx_orders_intent_trade_day_status_action`

---

## Deployment Sign-Off

- [ ] All pre-deployment checks passed
- [ ] Code changes reviewed and approved
- [ ] Automated tests passed (7/7)
- [ ] Database backup created
- [ ] Code deployed to both app32/ and app64/
- [ ] Services restarted
- [ ] Post-deployment monitoring complete (1+ hour)
- [ ] No issues detected
- [ ] Ready for operational use

---

**Deployment Date**: _____________  
**Deployed By**: _____________  
**Reviewed By**: _____________  
**Verified By**: _____________  

---

## Reference Documents

- [DB Schema Stabilization Report](DB_SCHEMA_STABILIZATION_REPORT.md) - Full technical details
- [Before/After Comparison](BEFORE_AFTER_COMPARISON.md) - Code change details
- [Quick Summary](STABILIZATION_SUMMARY.md) - Executive summary
- [Verification Script](verify_schema_stabilization.py) - Automated tests

---

**Status**: ✅ Ready for deployment  
**Risk Level**: 🟢 LOW (fully backward compatible, additive changes only)  
**Estimated Downtime**: 0-5 minutes (service restart)  
**Rollback Difficulty**: 🟢 EASY (backup + git revert)
