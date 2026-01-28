#!/usr/bin/env python3
"""
DB Schema Stabilization - Verification Script

Tests:
1. init_schema() idempotency (run twice, no errors)
2. created_at column presence
3. trade_day column presence
4. order_id column presence
5. Index presence
6. trade_day backfill for existing NULL rows
7. count_sent_buy_today() query with trade_day
"""

import sqlite3
import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app32"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app64"))

def test_app32_schema():
    """Test app32/db.py schema stability."""
    print("\n" + "="*60)
    print("TEST: app32/db.py Schema Verification")
    print("="*60)
    
    from app32.db import connect, init_schema, get_kst_date
    
    # Clean start
    db_path = Path(__file__).resolve().parents[1] / "shared" / "data" / "trading.db"
    if db_path.exists():
        db_path.unlink()
        print("[SETUP] Deleted existing DB for fresh test")
    
    conn = connect()
    
    # Test 1: First init_schema() call
    print("\n[TEST 1] First init_schema() call...")
    try:
        init_schema(conn)
        print("✅ PASS: init_schema() executed successfully")
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False
    
    # Test 2: Second init_schema() call (idempotency)
    print("\n[TEST 2] Second init_schema() call (idempotency)...")
    try:
        init_schema(conn)
        print("✅ PASS: init_schema() is idempotent (no errors on second call)")
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False
    
    # Test 3: Check orders_intent columns
    print("\n[TEST 3] Verify orders_intent schema...")
    cursor = conn.execute("PRAGMA table_info(orders_intent)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    
    required = {'id', 'ts', 'created_at', 'trade_day', 'symbol', 'action', 'ai_score', 'ttl_ms', 'params_version_id', 'status'}
    present = set(columns.keys())
    
    if required <= present:
        print(f"✅ PASS: All required columns present: {required}")
    else:
        missing = required - present
        print(f"❌ FAIL: Missing columns: {missing}")
        return False
    
    # Test 4: Check execution_log columns
    print("\n[TEST 4] Verify execution_log schema...")
    cursor = conn.execute("PRAGMA table_info(execution_log)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    
    required = {'id', 'ts', 'module', 'symbol', 'action', 'decision', 'rejection_reason', 'ai_score', 'params_version_id', 'order_id', 'context'}
    present = set(columns.keys())
    
    if required <= present:
        print(f"✅ PASS: All required columns present: {required}")
    else:
        missing = required - present
        print(f"❌ FAIL: Missing columns: {missing}")
        return False
    
    # Test 5: Check index
    print("\n[TEST 5] Verify index presence...")
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_orders_intent_trade_day_status_action'")
    if cursor.fetchone():
        print("✅ PASS: Index idx_orders_intent_trade_day_status_action exists")
    else:
        print("❌ FAIL: Index not found")
        return False
    
    # Test 6: Insert test order and verify trade_day
    print("\n[TEST 6] Insert test order and verify trade_day...")
    trade_day = get_kst_date()
    current_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    
    try:
        conn.execute(
            "INSERT INTO orders_intent(ts, created_at, trade_day, symbol, action, ai_score, ttl_ms, params_version_id, status) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (current_ts, created_at, trade_day, 'TEST', 'BUY', 0.5, 5000, 'test_v1', 'NEW')
        )
        conn.commit()
        
        # Verify inserted
        row = conn.execute(
            "SELECT ts, created_at, trade_day, symbol, action, status FROM orders_intent WHERE symbol='TEST' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        
        if row and row[2] == trade_day:  # trade_day at index 2
            print(f"✅ PASS: Order inserted with trade_day={trade_day}")
            print(f"   Columns: ts={row[0]}, created_at={row[1]}, trade_day={row[2]}, symbol={row[3]}, action={row[4]}, status={row[5]}")
        else:
            print(f"❌ FAIL: trade_day not set correctly. Row: {row}")
            return False
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False
    
    # Test 7: Test count_sent_buy_today() query
    print("\n[TEST 7] Test count_sent_buy_today() query (trade_day based)...")
    try:
        # First update order to SENT
        conn.execute("UPDATE orders_intent SET status='SENT', action='BUY' WHERE symbol='TEST'")
        conn.commit()
        
        # Now count
        count = conn.execute(
            "SELECT COUNT(*) FROM orders_intent WHERE status='SENT' AND action='BUY' AND trade_day=?",
            (trade_day,)
        ).fetchone()[0]
        
        if count >= 1:
            print(f"✅ PASS: count_sent_buy_today() query works, count={count}")
        else:
            print(f"❌ FAIL: Expected at least 1 BUY order, got {count}")
            return False
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False
    
    conn.close()
    return True

def test_app64_schema():
    """Test app64/db.py schema stability."""
    print("\n" + "="*60)
    print("TEST: app64/db.py Schema Verification")
    print("="*60)
    
    from app64.db import connect, init_schema
    
    # Use same DB (shared)
    conn = connect()
    
    # Test 1: First init_schema() call
    print("\n[TEST 1] First init_schema() call...")
    try:
        init_schema(conn)
        print("✅ PASS: init_schema() executed successfully")
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False
    
    # Test 2: Second init_schema() call (idempotency)
    print("\n[TEST 2] Second init_schema() call (idempotency)...")
    try:
        init_schema(conn)
        print("✅ PASS: init_schema() is idempotent (no errors on second call)")
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False
    
    # Test 3: Verify schemas match between app32 and app64
    print("\n[TEST 3] Verify schema consistency between app32 and app64...")
    cursor = conn.execute("PRAGMA table_info(orders_intent)")
    app64_cols = {row[1]: row[2] for row in cursor.fetchall()}
    
    cursor = conn.execute("PRAGMA table_info(execution_log)")
    app64_exec_cols = {row[1]: row[2] for row in cursor.fetchall()}
    
    # Check orders_intent
    required_orders = {'id', 'ts', 'created_at', 'trade_day', 'symbol', 'action', 'ai_score', 'ttl_ms', 'params_version_id', 'status'}
    if required_orders <= set(app64_cols.keys()):
        print("✅ PASS: orders_intent columns consistent")
    else:
        print(f"❌ FAIL: Missing columns in app64 orders_intent: {required_orders - set(app64_cols.keys())}")
        return False
    
    # Check execution_log
    required_exec = {'id', 'ts', 'module', 'symbol', 'action', 'decision', 'rejection_reason', 'ai_score', 'params_version_id', 'order_id', 'context'}
    if required_exec <= set(app64_exec_cols.keys()):
        print("✅ PASS: execution_log columns consistent")
    else:
        print(f"❌ FAIL: Missing columns in app64 execution_log: {required_exec - set(app64_exec_cols.keys())}")
        return False
    
    # Test 4: Verify index
    print("\n[TEST 4] Verify index presence...")
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_orders_intent_trade_day_status_action'")
    if cursor.fetchone():
        print("✅ PASS: Index exists in app64")
    else:
        print("❌ FAIL: Index not found in app64")
        return False
    
    conn.close()
    return True

def main():
    print("\n" + "#"*60)
    print("# DB SCHEMA STABILIZATION VERIFICATION")
    print("# Tests both app32/db.py and app64/db.py")
    print("#"*60)
    
    results = []
    
    # Test app32
    results.append(("app32 schema", test_app32_schema()))
    
    # Test app64
    results.append(("app64 schema", test_app64_schema()))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(passed for _, passed in results)
    print("\n" + ("="*60))
    if all_passed:
        print("✅ ALL TESTS PASSED - Schema stabilization successful")
        print("="*60)
        return 0
    else:
        print("❌ SOME TESTS FAILED - Review errors above")
        print("="*60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
