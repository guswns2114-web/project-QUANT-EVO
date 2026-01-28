import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

DB_PATH = Path(__file__).resolve().parents[1] / "shared" / "data" / "trading.db"

def get_kst_date():
    """
    KST(UTC+9) 기준 오늘 날짜를 YYYY-MM-DD 형식으로 반환.
    """
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst).strftime("%Y-%m-%d")

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def _column_exists(conn, table_name, column_name):
    """Check if column exists in table (idempotency check)."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def init_schema(conn):
    """
    스키마 초기화 및 마이그레이션 (완전 이등분성: 여러 번 안전).
    - orders_intent: ts, created_at, trade_day, symbol, action, ai_score, ttl_ms, params_version_id, status
    - execution_log: ts, module, symbol, action, decision, rejection_reason, ai_score, params_version_id, order_id, context
    """
    # CREATE TABLE: 스키마 완전 정의 (IF NOT EXISTS 안전)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS orders_intent (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        created_at TEXT,
        trade_day TEXT,
        symbol TEXT NOT NULL,
        action TEXT NOT NULL,
        ai_score REAL NOT NULL,
        ttl_ms INTEGER NOT NULL,
        params_version_id TEXT NOT NULL,
        status TEXT NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS execution_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        module TEXT NOT NULL,
        symbol TEXT NOT NULL,
        action TEXT NOT NULL,
        decision TEXT NOT NULL,
        rejection_reason TEXT,
        ai_score REAL NOT NULL,
        params_version_id TEXT NOT NULL,
        order_id TEXT,
        context TEXT
    );
    """)
    
    # 마이그레이션 1: orders_intent에 created_at 추가 (이미 있으면 무시)
    if not _column_exists(conn, 'orders_intent', 'created_at'):
        try:
            conn.execute("ALTER TABLE orders_intent ADD COLUMN created_at TEXT;")
            print("[DB] Migrated: Added created_at column to orders_intent")
        except sqlite3.OperationalError as e:
            print(f"[DB] Skipped created_at migration: {e}")
    
    # 마이그레이션 2: orders_intent에 trade_day 추가 (이미 있으면 무시)
    if not _column_exists(conn, 'orders_intent', 'trade_day'):
        try:
            conn.execute("ALTER TABLE orders_intent ADD COLUMN trade_day TEXT;")
            print("[DB] Migrated: Added trade_day column to orders_intent")
        except sqlite3.OperationalError as e:
            print(f"[DB] Skipped trade_day migration: {e}")
    
    # 마이그레이션 3: execution_log에 order_id 추가 (이미 있으면 무시)
    if not _column_exists(conn, 'execution_log', 'order_id'):
        try:
            conn.execute("ALTER TABLE execution_log ADD COLUMN order_id TEXT;")
            print("[DB] Migrated: Added order_id column to execution_log")
        except sqlite3.OperationalError as e:
            print(f"[DB] Skipped order_id migration: {e}")
    
    # 마이그레이션 4: 기존 NULL trade_day 값 백필 (KST 기준)
    try:
        null_count = conn.execute(
            "SELECT COUNT(*) FROM orders_intent WHERE trade_day IS NULL"
        ).fetchone()[0]
        if null_count > 0:
            # ts에서 DATE 추출 (KST 기준 일자)
            conn.execute(
                "UPDATE orders_intent SET trade_day = DATE(ts) WHERE trade_day IS NULL"
            )
            conn.commit()
            print(f"[DB] Backfilled {null_count} NULL trade_day values from ts")
    except sqlite3.OperationalError as e:
        print(f"[DB] Skipped trade_day backfill: {e}")
    
    # 인덱스: DAILY_LIMIT 쿼리 최적화 (IF NOT EXISTS 안전)
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_intent_trade_day_status_action "
            "ON orders_intent (trade_day, status, action);"
        )
    except sqlite3.OperationalError as e:
        print(f"[DB] Skipped index creation: {e}")

