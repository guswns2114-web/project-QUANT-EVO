# Execution Logging Schema

## Overview
Structured execution logs for signal quality analysis and AI prompt evaluation.

## Database Table: `execution_log`

```sql
CREATE TABLE execution_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,                    -- Timestamp (YYYY-MM-DD HH:MM:SS.mmm)
    module TEXT NOT NULL,                -- "APP32" or "APP64"
    symbol TEXT NOT NULL,                -- Ticker code (e.g., "005930")
    action TEXT NOT NULL,                -- "BUY" / "SELL" / "HOLD"
    decision TEXT NOT NULL,              -- "SENT" / "REJECTED" / "CREATED"
    rejection_reason TEXT,               -- NULL or specific reason code
    ai_score REAL NOT NULL,              -- Signal confidence (0.0-1.0)
    params_version_id TEXT NOT NULL,     -- Strategy version for traceability
    context TEXT                         -- JSON context data
);
```

---

## Field Descriptions

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| `ts` | TEXT | Execution timestamp with millisecond precision | `2026-01-28 14:35:42.123` |
| `module` | TEXT | Source module (signal generator or executor) | `APP64` or `APP32` |
| `symbol` | TEXT | Stock ticker code | `005930`, `035420` |
| `action` | TEXT | Trading action proposed | `BUY`, `SELL`, `HOLD` |
| `decision` | TEXT | Final decision outcome | `CREATED`, `SENT`, `REJECTED` |
| `rejection_reason` | TEXT | Why signal was rejected (NULL if approved) | `ttl_expired`, `daily_limit`, `cooldown`, `one_position` |
| `ai_score` | REAL | AI confidence/score from signal engine | `0.75`, `0.82` |
| `params_version_id` | TEXT | Config version applied | `2026-01-28_01` |
| `context` | TEXT | JSON with additional decision context | `{"age_ms": 5200, "ttl_ms": 5000}` |

---

## Signal Flow & Log Points

### APP64 (Signal Engine)
```
Signal Generated → log_signal()
└─ decision: "CREATED"
└─ rejection_reason: NULL
└─ context: {"score_range": [0.55, 0.90], "ai_score_cut": 0.70, ...}
```

### APP32 (Execution Engine)
```
Orders Intent Query
├─ TTL Check → REJECTED (ttl_expired)
│  └─ context: {"age_ms": 5200, "ttl_ms": 5000}
├─ Daily Limit Check → REJECTED (daily_limit)
│  └─ context: {"buys_today": 8, "max_orders_per_day": 8}
├─ Cooldown Check → REJECTED (cooldown)
│  └─ context: {"elapsed_sec": 20.5, "remaining_sec": 9.5, "cooldown_sec": 30}
├─ One Position Check → REJECTED (one_position)
│  └─ context: {"has_position": true}
└─ All Checks Pass → SENT (None)
   └─ context: "" (empty)
```

---

## Rejection Reasons (Comprehensive)

| Reason | Module | Trigger | When Used |
|--------|--------|---------|-----------|
| `ttl_expired` | APP32 | Signal age > TTL | Market condition changed |
| `daily_limit` | APP32 | BUY count ≥ max_orders_per_day | Risk management limit |
| `cooldown` | APP32 | Time since last BUY < cooldown_sec | Anti-overtrading |
| `one_position` | APP32 | Already holding position + BUY action | Single position constraint |

---

## Analysis Use Cases

### 1. Signal Quality Evaluation
```sql
-- BUY signals that were actually executed
SELECT symbol, ai_score, params_version_id, COUNT(*) 
FROM execution_log 
WHERE module='APP32' AND action='BUY' AND decision='SENT'
GROUP BY symbol, ai_score;

-- Rejection rate by reason
SELECT rejection_reason, COUNT(*) as count 
FROM execution_log 
WHERE decision='REJECTED' 
GROUP BY rejection_reason;
```

### 2. AI Prompt Tuning
```sql
-- Compare signal generation rates across param versions
SELECT params_version_id, COUNT(*) as signals_created
FROM execution_log 
WHERE module='APP64' AND decision='CREATED'
GROUP BY params_version_id;
```

### 3. Risk Rule Effectiveness
```sql
-- How many signals filtered by each rule?
SELECT rejection_reason, 
       COUNT(*) as filtered_count,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM execution_log WHERE decision='REJECTED'), 2) as pct
FROM execution_log 
WHERE decision='REJECTED'
GROUP BY rejection_reason;
```

### 4. Parameter Version Comparison
```sql
-- Execution efficiency by version
SELECT params_version_id, 
       SUM(CASE WHEN decision='SENT' THEN 1 ELSE 0 END) as approved,
       SUM(CASE WHEN decision='REJECTED' THEN 1 ELSE 0 END) as rejected
FROM execution_log 
WHERE module='APP32'
GROUP BY params_version_id;
```

---

## Console Output (Legacy)

For real-time monitoring, console prints are preserved:

**APP64 (Signal Creation):**
```
[2026-01-28 14:35:42.123] [APP64] [CREATED] BUY 005930 score=0.75 ver=2026-01-28_01
```

**APP32 (Execution - Approved):**
```
[2026-01-28 14:35:42.500] [APP32] [SENT] BUY 005930 score=0.75 ver=2026-01-28_01
```

**APP32 (Execution - Rejected):**
```
[2026-01-28 14:35:42.501] [APP32] [REJECTED] 005930 BUY reason=cooldown score=0.75 ver=2026-01-28_01
```

---

## Notes

- **No data deletion:** All logs preserved for complete audit trail
- **Millisecond precision:** `now_ms()` captures execution timing
- **JSON context:** Additional decision parameters stored as JSON for flexible analysis
- **Version tracking:** All decisions tied to strategy params version
- **Traceability:** Every signal tracked from creation → execution/rejection
