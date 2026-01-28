# QUANT-EVO Code Changes - Comprehensive Analysis Report

**Analysis Date**: 2026-01-28  
**Scope**: Complete diff audit, schema verification, risk assessment

---

## 1. CHANGED FILES LIST

### Total: 7 files modified

| # | File Path | Type | Lines Changed |
|---|-----------|------|----------------|
| 1 | `app32/db.py` | DB Schema | +30 lines |
| 2 | `app32/main.py` | Python Logic | +80 lines |
| 3 | `app32/brokers/__init__.py` | NEW | 18 lines |
| 4 | `app32/brokers/base.py` | NEW | 115 lines |
| 5 | `app32/brokers/mock.py` | NEW | 130 lines |
| 6 | `app64/db.py` | DB Schema | +35 lines |
| 7 | `app64/signal_engine.py` | Python Logic | +3 lines |

---

## 2. UNIFIED DIFFS (Git-Style)

### File 1: app32/db.py

```diff
--- app32/db.py (original)
+++ app32/db.py (modified)
@@ -1,8 +1,13 @@
 import sqlite3
 from pathlib import Path
+from datetime import datetime, timezone, timedelta
 
 DB_PATH = Path(__file__).resolve().parents[1] / "shared" / "data" / "trading.db"
 
+def get_kst_date():
+    """
+    KST(UTC+9) 기준 오늘 날짜를 YYYY-MM-DD 형식으로 반환.
+    """
+    kst = timezone(timedelta(hours=9))
+    return datetime.now(kst).strftime("%Y-%m-%d")
 
 def connect():
     DB_PATH.parent.mkdir(parents=True, exist_ok=True)
@@ -12,22 +17,31 @@
     return conn
 
 def init_schema(conn):
+    """
+    스키마 초기화 및 마이그레이션.
+    trade_day 컬럼이 없으면 추가.
+    """
     conn.executescript("""
     CREATE TABLE IF NOT EXISTS orders_intent (
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         ts TEXT NOT NULL,
+        trade_day TEXT,
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
+        order_id TEXT,
         context TEXT
     );
     """)
@@ -35,6 +49,20 @@
     # 마이그레이션: trade_day 컬럼 추가 (이미 있으면 무시)
     try:
         conn.execute("ALTER TABLE orders_intent ADD COLUMN trade_day TEXT;")
         print("[DB] Migrated: Added trade_day column to orders_intent")
     except sqlite3.OperationalError:
         # 컬럼이 이미 있음
         pass
+
+    # 마이그레이션: execution_log에 order_id 컬럼 추가
+    try:
+        conn.execute("ALTER TABLE execution_log ADD COLUMN order_id TEXT;")
+        print("[DB] Migrated: Added order_id column to execution_log")
+    except sqlite3.OperationalError:
+        # 컬럼이 이미 있음
+        pass
+
+    # 인덱스 추가 (DAILY_LIMIT 쿼리 최적화)
+    try:
+        conn.execute(
+            "CREATE INDEX IF NOT EXISTS idx_orders_intent_trade_day_status_action "
+            "ON orders_intent (trade_day, status, action);"
+        )
+    except:
+        pass
```

### File 2: app32/main.py (selected sections)

```diff
--- app32/main.py (original)
+++ app32/main.py (modified)
@@ -1,6 +1,7 @@
 import json, time, os
 from datetime import datetime, timezone
 from pathlib import Path
 import sys
 from db import connect, init_schema, get_kst_date
+from brokers import MockBroker
 
 CONFIG_PATH = Path(__file__).resolve().parents[1] / "shared" / "config" / "strategy_params.json"
 LOGS_PATH = Path(__file__).resolve().parents[1] / "shared" / "logs"
@@ -17,6 +18,7 @@
     DAILY_LIMIT = "DAILY_LIMIT"
     COOLDOWN = "COOLDOWN"
     ONE_POSITION = "ONE_POSITION"
+    BROKER_ERROR = "BROKER_ERROR"
 
 def now():
     return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
@@ -128,12 +130,16 @@
 
 def count_sent_buy_today(conn, trade_day=None):
     """
     오늘(SENT) 처리된 주문 중 BUY만 카운트.
-    ts는 "YYYY-MM-DD HH:MM:SS" 문자열이라고 가정.
+    trade_day column 기반 쿼리 (KST 타임존).
     """
+    if trade_day is None:
+        trade_day = get_kst_date()
     row = conn.execute(
         "SELECT COUNT(*) FROM orders_intent "
-        "WHERE status='SENT' AND action='BUY' AND ts LIKE ?",
-        (f"{prefix}%",)
+        "WHERE status='SENT' AND action='BUY' AND trade_day=?",
+        (trade_day,)
     ).fetchone()
     return int(row[0]) if row else 0
 
 def reset_daily_counters(conn):
     """
     테스트/디버깅용: 오늘 날짜의 SENT BUY 주문을 모두 'PROCESSED'로 변경하여
-    카운터를 0으로 리셋.
+    카운터를 0으로 리셋.
+    trade_day 컬럼 기반 업데이트 (KST 타임존).
     """
+    trade_day = get_kst_date()
     result = conn.execute(
         "UPDATE orders_intent SET status='PROCESSED' "
-        "WHERE status='SENT' AND action='BUY' AND ts LIKE ?",
-        (f"{prefix}%",)
+        "WHERE status='SENT' AND action='BUY' AND trade_day=?",
+        (trade_day,)
     )
     count = result.rowcount
     conn.commit()
+
+    # 리셋 이벤트를 JSONL에 기록 (감사자용)
+    log_jsonl('RESET_DAILY_COUNTERS', 'N/A', 'N/A', 0.0, 'SYSTEM',
+             rejection_reason=None, 
+             records_affected=count,
+             event_note=f"Reset {count} BUY orders from SENT to PROCESSED on {trade_day}")
+
-    print(f"[RESET] {count} BUY orders marked as PROCESSED (day={prefix})")
+    print(f"[RESET] {count} BUY orders marked as PROCESSED (trade_day={trade_day})")
     return count
 
+def create_broker_execution_callback(conn):
+    """
+    브로커의 주문 실행 결과를 DB에 기록하는 콜백 생성.
+    
+    MockBroker.place_order()가 성공하면 이 함수가 호출되어
+    execution_log에 기록함.
+    """
+    def callback(symbol: str, action: str, order_id: str, status: str, 
+                quantity: int, price: float, order_type: str):
+        current_ts = now()
+        ai_score = 0.0  # 브로커에서는 AI score 모름
+        params_version_id = load_params().get("metadata", {}).get("version_id", "1")
+        
+        # execution_log에 INSERT (decision이 실제 컬럼명)
+        conn.execute(
+            "INSERT INTO execution_log(ts, module, symbol, action, order_id, decision, ai_score, params_version_id) "
+            "VALUES (?,?,?,?,?,?,?,?)",
+            (current_ts, 'BROKER', symbol, action, order_id, status, ai_score, params_version_id)
+        )
+        conn.commit()
+        
+        print(f"[BROKER] {action} {symbol} @{order_id} logged to execution_log")
+    
+    return callback
 
 def main():
     conn = connect()
     init_schema(conn)
     print("[APP32] started", now())
+
+    # ✅ 브로커 초기화 (MOCK 모드)
+    broker = MockBroker(execution_log_callback=create_broker_execution_callback(conn))
+    print("[APP32] Broker initialized (MOCK mode)")
 
     has_position = False
     last_trade_ts = 0.0
 
     # ✅ 하루 BUY 주문 카운터(프로그램 재시작해도 유지되게 DB에서 로드)
     current_day = today_prefix()
-    buys_today = count_sent_buy_today(conn)
+    buys_today = count_sent_buy_today(conn)
     print(f"[LIMIT] loaded sent BUY orders today = {buys_today} (day={current_day})")
 
@@ -305,18 +315,51 @@
             # ✅ 드라이런 주문 실행 - 승인됨
-            log_execution_with_jsonl(
-                conn, current_ts, symbol, action, "SENT", None, score, ver, 
-                context="", cooldown_sec=cooldown_sec, max_orders_per_day=max_orders_per_day, 
-                one_position_only=one_position_only
-            )
+            # 1. 브로커에 주문 전송
+            broker_result = broker.place_order(
+                symbol=symbol,
+                action=action,
+                order_type='market',
+                quantity=1
+            )
+            
+            # 2. 주문 결과 로깅 및 DB 업데이트
+            if broker_result.success:
+                order_id = broker_result.order_id
+                print(f"[ORDER] {action} {symbol} executed -> {order_id}")
+                
+                # JSONL 로깅
+                log_execution_with_jsonl(
+                    conn, current_ts, symbol, action, "SENT", None, score, ver, 
+                    context=json.dumps(broker_result.context or {}), 
+                    cooldown_sec=cooldown_sec, max_orders_per_day=max_orders_per_day, 
+                    one_position_only=one_position_only
+                )
+                
+                # orders_intent 상태 업데이트
+                conn.execute(
+                    "UPDATE orders_intent SET status='SENT' WHERE id=?",
+                    (intent_id,)
+                )
+            else:
+                # 브로커 실행 실패
+                print(f"[ERROR] Broker order failed: {broker_result.reason}")
+                log_execution_with_jsonl(
+                    conn, current_ts, symbol, action, "REJECTED", 
+                    RejectionReason.BROKER_ERROR, score, ver, 
+                    context=f'{{"broker_error": "{broker_result.reason}"}}', 
+                    cooldown_sec=cooldown_sec, max_orders_per_day=max_orders_per_day, 
+                    one_position_only=one_position_only
+                )
+                conn.execute(
+                    "UPDATE orders_intent SET status='REJECTED' WHERE id=?",
+                    (intent_id,)
+                )
+                continue
 
-            conn.execute(
-                "UPDATE orders_intent SET status='SENT' WHERE id=?",
-                (intent_id,)
-            )
 
             # ✅ BUY가 실행되면: 포지션 보유 + 마지막 거래 시간 갱신 + 오늘 BUY 카운트 증가
             if action == "BUY":
                 has_position = True
@@ -331,6 +374,18 @@
     args = parser.parse_args()
     
     if args.reset_daily_counters:
+        # Safety guard: ALLOW_RESET 환경변수 검증
+        allow_reset = os.getenv('ALLOW_RESET', '0')
+        if allow_reset != '1':
+            print("[ERROR] --reset-daily-counters 실행 전에 ALLOW_RESET=1 환경변수 설정 필수")
+            print("[ERROR] Usage: $env:ALLOW_RESET = '1'; python app32/main.py --reset-daily-counters")
+            print("[ERROR] Safety guard: 의도하지 않은 리셋 방지")
+            sys.exit(1)
+        
+        print("[APP32] --reset-daily-counters 플래그로 실행 중 (ALLOW_RESET=1 확인됨)")
         conn = connect()
         init_schema(conn)
         reset_daily_counters(conn)
         conn.close()
-        print("[APP32] Daily counters reset complete. Restarting main loop...")
+        print("[APP32] Daily counters reset 완료. 메인 루프를 다시 시작합니다...")
```

### File 3: app64/db.py

```diff
--- app64/db.py (original)
+++ app64/db.py (modified)
@@ -1,8 +1,13 @@
 import sqlite3
 from pathlib import Path
+from datetime import datetime, timezone, timedelta
 
 DB_PATH = Path(__file__).resolve().parents[1] / "shared" / "data" / "trading.db"
 
+def get_kst_date():
+    """KST 기준 오늘 날짜 (YYYY-MM-DD)"""
+    kst = timezone(timedelta(hours=9))
+    return datetime.now(kst).strftime("%Y-%m-%d")
 
 def connect():
     DB_PATH.parent.mkdir(parents=True, exist_ok=True)
@@ -15,6 +20,7 @@
     conn.executescript("""
     CREATE TABLE IF NOT EXISTS orders_intent (
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         ts TEXT NOT NULL,
         created_at TEXT,
+        trade_day TEXT,
         symbol TEXT NOT NULL,
         action TEXT NOT NULL,
         ai_score REAL NOT NULL,
@@ -32,6 +38,7 @@
         rejection_reason TEXT,
         ai_score REAL NOT NULL,
         params_version_id TEXT NOT NULL,
+        order_id TEXT,
         context TEXT
     );
     """)
@@ -41,9 +48,22 @@
         conn.execute("ALTER TABLE orders_intent ADD COLUMN created_at TEXT")
     except sqlite3.OperationalError:
         pass
     
-    # Backfill schema for existing DBs
+    # Migration: Add trade_day column if missing
     try:
-        conn.execute("ALTER TABLE orders_intent ADD COLUMN created_at TEXT")
+        conn.execute("ALTER TABLE orders_intent ADD COLUMN trade_day TEXT")
+        print("[DB] Migrated: Added trade_day column to orders_intent")
+    except sqlite3.OperationalError:
+        pass
+    
+    # Migration: Add order_id column to execution_log if missing
+    try:
+        conn.execute("ALTER TABLE execution_log ADD COLUMN order_id TEXT")
+        print("[DB] Migrated: Added order_id column to execution_log")
     except sqlite3.OperationalError:
         pass
+    
+    # Create index for better DAILY_LIMIT query performance
+    try:
+        conn.execute(
+            "CREATE INDEX idx_orders_intent_trade_day_status_action ON orders_intent (trade_day, status, action)"
+        )
     except sqlite3.OperationalError:
         pass
```

### File 4: app64/signal_engine.py

```diff
--- app64/signal_engine.py (original)
+++ app64/signal_engine.py (modified)
@@ -1,7 +1,7 @@
 import json, random, time
 from datetime import datetime, timezone
 from pathlib import Path
 import os, sys, stat, subprocess, atexit
-from db import connect, init_schema
+from db import connect, init_schema, get_kst_date
 
 CONFIG_PATH = Path(__file__).resolve().parents[1] / "shared" / "config" / "strategy_params.json"
 LOGS_PATH = Path(__file__).resolve().parents[1] / "shared" / "logs"
@@ -260,12 +260,15 @@
         # Generate AI score from Gaussian distribution
         score = clamp(random.gauss(mock_ai_score_mean, mock_ai_score_std), 0.0, 1.0)
         
         # Generate action (BUY or SELL) based on ratio
         action = "BUY" if random.random() < mock_action_ratio_buy else "SELL"
         
+        # Get KST trade_day for DAILY_LIMIT tracking
+        trade_day = get_kst_date()
+        
         # Insert into database
         conn.execute(
-            "INSERT INTO orders_intent(ts, created_at, symbol, action, ai_score, ttl_ms, params_version_id, status) VALUES (?,?,?,?,?,?,?, 'NEW')",
-            (now(), created_at, sym, action, score, ttl, ver)
+            "INSERT INTO orders_intent(ts, created_at, trade_day, symbol, action, ai_score, ttl_ms, params_version_id, status) VALUES (?,?,?,?,?,?,?,?, 'NEW')",
+            (now(), created_at, trade_day, sym, action, score, ttl, ver)
         )
         
         # Log to database execution_log
```

### Files 5-7: New Broker Adapter Files (Not in previous version)

```diff
--- /dev/null
+++ app32/brokers/__init__.py (NEW - 18 lines)
@@ -0,0 +1,18 @@
+"""
+Broker adapters package.
+
+모든 거래소 로직을 여기에 수집:
+- BrokerInterface: 추상 인터페이스
+- MockBroker: 시뮬레이션용 (개발/테스트)
+- LiveBroker: 실제 거래용 (프로덕션)
+"""
+
+from .base import BrokerInterface, OrderResult, Position
+from .mock import MockBroker
+from .live import LiveBroker
+
+__all__ = [
+    'BrokerInterface',
+    'OrderResult',
+    'Position',
+    'MockBroker',
+    'LiveBroker',
+]

--- /dev/null
+++ app32/brokers/base.py (NEW - 115 lines)
@@ -0,0 +1,115 @@
+"""
+BrokerInterface: Abstract base class for broker adapters.
+
+목표:
+- MOCK과 LIVE 브로커를 동일한 인터페이스로 취급
+- 실행 로직 (place_order, cancel_order 등)을 구체적인 브로커 구현으로 분리
+- 테스트 시 MOCK, 실운영 시 LIVE로 쉽게 전환
+"""
+
+from abc import ABC, abstractmethod
+from dataclasses import dataclass
+from typing import Optional, Dict, Any, List
+
+
+@dataclass
+class OrderResult:
+    """주문 실행 결과"""
+    success: bool                    # True: 성공, False: 실패
+    order_id: Optional[str]         # 주문 ID (성공 시)
+    reason: Optional[str]           # 실패 이유 또는 참고사항
+    context: Optional[Dict[str, Any]] = None  # 추가 컨텍스트
+
+
+@dataclass
+class Position:
+    """포지션 정보"""
+    symbol: str
+    action: str  # BUY or SELL
+    quantity: int
+    avg_price: float
+    current_price: float
+    unrealized_pnl: float
+
+
+class BrokerInterface(ABC):
+    """
+    추상 브로커 인터페이스.
+    
+    모든 브로커 어댑터는 이 클래스를 상속하고 추상 메서드를 구현해야 함.
+    """
+    
+    @abstractmethod
+    def place_order(self, ...): pass
+    
+    @abstractmethod
+    def cancel_order(self, ...): pass
+    
+    @abstractmethod
+    def get_positions(self): pass
+    
+    @abstractmethod
+    def get_cash(self): pass
+    
+    def validate_order(self, ...): pass

--- /dev/null
+++ app32/brokers/mock.py (NEW - 130 lines)
@@ -0,0 +1,130 @@
+"""
+MockBroker: MOCK 브로커 구현 (드라이런/시뮬레이션용).
+
+기능:
+- 주문 생성 시 즉시 성공 응답 (네트워크 지연 없음)
+- execution_log에 주문 기록
+- 실제 자금이 소요되지 않음
+- 테스트/개발 환경에서 사용
+"""
+
+import json, time
+from datetime import datetime, timezone
+from typing import Optional, List
+from .base import BrokerInterface, OrderResult, Position
+
+# Import from parent package (app32.db)
+try:
+    from app32.db import connect, init_schema
+except ImportError:
+    # Fallback for local imports
+    import sys
+    from pathlib import Path
+    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
+    from db import connect, init_schema
+
+
+class MockBroker(BrokerInterface):
+    """MOCK 브로커: 주문을 즉시 성공시킴 (드라이런용)."""
+    
+    def __init__(self, execution_log_callback=None):
+        # ... initialization
+    
+    def place_order(self, symbol, action, order_type='market', quantity=1, price=None, **kwargs):
+        # Validation
+        # Mock ID generation
+        # Callback invocation
+        # Position tracking
+        # Return OrderResult(success=True, order_id=order_id, ...)
+    
+    def cancel_order(self, order_id):
+        # Return OrderResult(success=True, ...)
+    
+    def get_positions(self):
+        # Return List[Position]
+    
+    def get_cash(self):
+        # Return 1_000_000.0 (fixed for MOCK)
```

---

## 3. SCHEMA CHANGE TABLE

| Aspect | Table | Column(s) | Change Type | Migration Logic | Risk |
|--------|-------|-----------|-------------|-----------------|------|
| **orders_intent (app32)** | orders_intent | `trade_day TEXT` | ADD | ALTER TABLE (idempotent try-catch) | ✅ NULL-safe |
| **orders_intent (app32)** | orders_intent | `idx_orders_intent_trade_day_status_action` | INDEX ADD | CREATE INDEX IF NOT EXISTS | ✅ Duplicate-safe |
| **execution_log (app32)** | execution_log | `order_id TEXT` | ADD | ALTER TABLE (idempotent try-catch) | ✅ NULL-safe |
| **orders_intent (app64)** | orders_intent | `created_at TEXT` | ADD | ALTER TABLE (idempotent try-catch) | ✅ NULL-safe |
| **orders_intent (app64)** | orders_intent | `trade_day TEXT` | ADD | ALTER TABLE (idempotent try-catch) | ✅ NULL-safe |
| **orders_intent (app64)** | orders_intent | `idx_orders_intent_trade_day_status_action` | INDEX ADD | CREATE INDEX (no IF NOT EXISTS check) | ⚠️ **RISK** |
| **execution_log (app64)** | execution_log | `order_id TEXT` | ADD | ALTER TABLE (idempotent try-catch) | ✅ NULL-safe |

---

## 4. SCHEMA CONSISTENCY AUDIT

### 4.1 ORDERS_INTENT Table Definition

#### app32/db.py
```sql
CREATE TABLE IF NOT EXISTS orders_intent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    trade_day TEXT,                    ← NULLABLE
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    ai_score REAL NOT NULL,
    ttl_ms INTEGER NOT NULL,
    params_version_id TEXT NOT NULL,
    status TEXT NOT NULL
);
```

#### app64/db.py
```sql
CREATE TABLE IF NOT EXISTS orders_intent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    created_at TEXT,                   ← PRESENT
    trade_day TEXT,                    ← NULLABLE
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    ai_score REAL NOT NULL,
    ttl_ms INTEGER NOT NULL,
    params_version_id TEXT NOT NULL,
    status TEXT NOT NULL
);
```

**INCONSISTENCY #1** ⚠️
- **app32/db.py**: Missing `created_at` column in schema
- **app64/db.py**: Includes `created_at` column
- **Impact**: app32 won't be able to read `created_at` from APP64 signals
- **Fix Required**: Add `created_at TEXT` to app32/db.py CREATE TABLE

### 4.2 EXECUTION_LOG Table Definition

#### app32/db.py
```sql
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
    order_id TEXT,                     ← ADDED
    context TEXT
);
```

#### app64/db.py
```sql
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
    order_id TEXT,                     ← ADDED
    context TEXT
);
```

**CONSISTENCY**: ✅ MATCH - Both include `order_id`

### 4.3 Index Definitions

#### app32/db.py
```sql
CREATE INDEX IF NOT EXISTS idx_orders_intent_trade_day_status_action 
  ON orders_intent (trade_day, status, action);
```

#### app64/db.py
```sql
CREATE INDEX idx_orders_intent_trade_day_status_action 
  ON orders_intent (trade_day, status, action);
```

**INCONSISTENCY #2** ⚠️
- **app32/db.py**: Uses `CREATE INDEX IF NOT EXISTS` (safe)
- **app64/db.py**: Uses `CREATE INDEX` (unsafe - will fail if exists)
- **Impact**: Second migration run on app64 will throw error if index exists
- **Fix Required**: Add `IF NOT EXISTS` to app64/db.py index creation

---

## 5. TOP 5 RISKS & CONCRETE FIXES

### Risk #1: SCHEMA MISMATCH - Missing `created_at` in app32
**Severity**: 🔴 HIGH  
**Location**: `app32/db.py` line 31  
**Issue**: 
- app64 signals include `created_at` column
- app32 schema doesn't define it
- INSERT fails if APP32 tries to read it

**Fix**:
```python
# In app32/db.py, init_schema() CREATE TABLE:
CREATE TABLE IF NOT EXISTS orders_intent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    created_at TEXT,              ← ADD THIS
    trade_day TEXT,
    symbol TEXT NOT NULL,
    ...
);
```

**Verification**:
```bash
python -c "from app32.db import connect, init_schema; conn = connect(); init_schema(conn); \
  cols = conn.execute('PRAGMA table_info(orders_intent)').fetchall(); \
  print([c[1] for c in cols])"
# Expected: [..., 'created_at', 'trade_day', ...]
```

---

### Risk #2: INDEX CREATION FAILURE in app64
**Severity**: 🟡 MEDIUM  
**Location**: `app64/db.py` line 63  
**Issue**:
- app32 uses `CREATE INDEX IF NOT EXISTS` (idempotent)
- app64 uses `CREATE INDEX` (fails if exists)
- Second app64 init_schema() call will crash

**Fix**:
```python
# In app64/db.py, change line 63:
-        conn.execute(
-            "CREATE INDEX idx_orders_intent_trade_day_status_action ON orders_intent (trade_day, status, action)"
-        )

+        conn.execute(
+            "CREATE INDEX IF NOT EXISTS idx_orders_intent_trade_day_status_action ON orders_intent (trade_day, status, action)"
+        )
```

**Verification**:
```bash
# Run init_schema twice to ensure idempotency
python -c "from app64.db import connect, init_schema; conn = connect(); \
  init_schema(conn); init_schema(conn); print('OK')"
```

---

### Risk #3: TRADE_DAY NULLABLE - NULL VALUES CAN BREAK DAILY_LIMIT
**Severity**: 🟡 MEDIUM  
**Location**: `app32/main.py` line 135 & `app64/db.py`  
**Issue**:
- trade_day defined as nullable TEXT
- count_sent_buy_today() query: `WHERE trade_day=?`
- Old records with NULL trade_day won't be counted
- DAILY_LIMIT check may silently undercount

**Fix**:
```python
# Option A: Populate NULL trade_day on startup (Recommended)
def init_schema(conn):
    # ... existing code ...
    
    # Backfill NULL trade_day values
    try:
        conn.execute(
            "UPDATE orders_intent SET trade_day = DATE(ts) WHERE trade_day IS NULL"
        )
        print("[DB] Backfilled NULL trade_day values from ts")
    except sqlite3.OperationalError:
        pass

# Option B: Make trade_day NOT NULL with default
# ALTER TABLE orders_intent MODIFY trade_day TEXT NOT NULL DEFAULT (DATE('now'));
```

**Verification**:
```bash
python -c "from app32.db import connect; conn = connect(); \
  null_count = conn.execute('SELECT COUNT(*) FROM orders_intent WHERE trade_day IS NULL').fetchone()[0]; \
  print(f'NULL trade_day count: {null_count}')"
# Expected: 0
```

---

### Risk #4: ALLOW_RESET ENVIRONMENT VARIABLE NOT CLEARED
**Severity**: 🟡 MEDIUM  
**Location**: `app32/main.py` line 376  
**Issue**:
- ALLOW_RESET=1 persists in shell environment
- User forgets to unset after reset
- Accidental reset possible if flag somehow reused

**Fix**:
```python
# In app32/main.py, after reset_daily_counters() completion:
if args.reset_daily_counters:
    allow_reset = os.getenv('ALLOW_RESET', '0')
    if allow_reset != '1':
        # ... error handling ...
        sys.exit(1)
    
    conn = connect()
    init_schema(conn)
    reset_daily_counters(conn)
    conn.close()
    print("[APP32] Daily counters reset 완료...")
    
+   # Clear ALLOW_RESET to prevent accidental resets
+   if 'ALLOW_RESET' in os.environ:
+       del os.environ['ALLOW_RESET']
+       print("[WARN] ALLOW_RESET cleared from environment")
    
    sys.exit(0)  # Exit after reset, don't start main()
```

**Verification**:
```bash
$env:ALLOW_RESET = "1"
python app32/main.py --reset-daily-counters
$env:ALLOW_RESET
# Expected: (empty)
```

---

### Risk #5: ORDER_ID CALLBACK DEADLOCK - DB Connection Sharing
**Severity**: 🟡 MEDIUM  
**Location**: `app32/main.py` line 176-182  
**Issue**:
- `create_broker_execution_callback()` captures `conn`
- Callback tries to INSERT while main loop uses same `conn`
- SQLite WAL mode helps but concurrent writes still risky
- MockBroker callback is synchronous (blocks main loop)

**Fix**:
```python
# Option A: Use separate DB connection for callback (Recommended)
def create_broker_execution_callback():
    """
    브로커의 주문 실행 결과를 DB에 기록하는 콜백 생성.
    (separate connection to avoid contention)
    """
    def callback(symbol: str, action: str, order_id: str, status: str, 
                quantity: int, price: float, order_type: str):
        # Open separate connection for callback
        callback_conn = connect()  ← SEPARATE CONNECTION
        try:
            current_ts = now()
            ai_score = 0.0
            params_version_id = load_params().get("metadata", {}).get("version_id", "1")
            
            callback_conn.execute(
                "INSERT INTO execution_log(ts, module, symbol, action, order_id, decision, ai_score, params_version_id) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (current_ts, 'BROKER', symbol, action, order_id, status, ai_score, params_version_id)
            )
            callback_conn.commit()
        finally:
            callback_conn.close()
        
        print(f"[BROKER] {action} {symbol} @{order_id} logged to execution_log")
    
    return callback
```

**Verification**:
```bash
# Run both APP32 and APP64 for 60+ seconds
# Monitor for SQLite lock errors
grep -i "database is locked" shared/logs/*.jsonl
# Expected: (no results)
```

---

## SUMMARY TABLE

| Risk # | Component | Type | Severity | Action |
|--------|-----------|------|----------|--------|
| 1 | app32/db.py | Schema | 🔴 HIGH | Add `created_at TEXT` to orders_intent |
| 2 | app64/db.py | Index | 🟡 MEDIUM | Change to `CREATE INDEX IF NOT EXISTS` |
| 3 | trade_day column | Logic | 🟡 MEDIUM | Backfill NULL values or add DEFAULT |
| 4 | ALLOW_RESET env var | Operations | 🟡 MEDIUM | Clear env var after reset |
| 5 | DB Connection | Concurrency | 🟡 MEDIUM | Use separate connection in callback |

---

## 6. VERIFICATION CHECKLIST

- [ ] **Risk #1**: Verify `created_at` column exists in app32/db.py schema
- [ ] **Risk #2**: Verify `IF NOT EXISTS` added to app64/db.py index creation
- [ ] **Risk #3**: Verify no NULL trade_day values exist after backfill
- [ ] **Risk #4**: Verify ALLOW_RESET environment variable clears after reset
- [ ] **Risk #5**: Monitor logs for "database is locked" errors during concurrent execution
- [ ] **Integration**: Run full pipeline test (APP64 + APP32) for 5+ minutes
- [ ] **Regression**: Verify DAILY_LIMIT still rejects orders when threshold reached

---

**Report Generated**: 2026-01-28  
**Status**: 5 Issues Identified, 5 Fixes Provided  
**Recommended Action**: Apply all fixes before production deployment
