# Signal Quality Analysis Implementation

## 📋 Summary

Created a **read-only analysis tool** (`scripts/analyze_signals.py`) to evaluate trading signal quality using execution logs. This tool enables data-driven optimization of AI prompts and strategy parameters without touching live trading logic.

---

## 📊 Deliverables

### 1. Analysis Script: `scripts/analyze_signals.py`

**Purpose:** Generates comprehensive signal quality metrics from execution_log database

**Key Features:**
- ✅ Read-only analysis (no database modifications)
- ✅ Robust error handling (works even if no data exists)
- ✅ 7 analysis categories
- ✅ Structured insights with actionable interpretations
- ✅ No external dependencies beyond standard library + sqlite3

**Execution:**
```bash
python scripts/analyze_signals.py
```

---

## 📈 Analysis Metrics (7 Categories)

### Category 1: Signal Generation Overview
```
Metric: Total signals generated (APP64)
Purpose: Measure AI activation frequency and opportunity volume
Output: Raw count of APP64 CREATED events
```

**왜 중요한가?**
- AI가 얼마나 자주 작동하는지 파악
- 일정 기간 동안 거래 기회 규모 측정
- 신호 생성 빈도 검증

---

### Category 2: Execution vs Rejection Rate
```
Metric: SENT count, REJECTED count, execution rate %
Purpose: Measure filter effectiveness and signal viability
Output: Absolute counts and percentages
```

**해석 가이드:**

| 실행률 | 진단 | 조치 |
|--------|------|------|
| > 80% | 필터 과도하게 느슨함 | 위험 규칙 강화 |
| 60-80% | ✅ 이상적 균형 | 유지 |
| 30-60% | 중간 정도 거절 | 필터 검토 |
| < 30% | 필터 과도하게 엄격함 | 임계값 완화 |

**AI 평가:**
- 높은 실행율 + 높은 신호점수 = AI 효과적
- 낮은 실행율 + 낮은 신호점수 = 프롬프트 개선 필요

---

### Category 3: Rejection Reason Distribution
```
Metric: Count and % for each rejection reason (TTL_EXPIRED, DAILY_LIMIT, COOLDOWN, ONE_POSITION)
Purpose: Identify dominant risk filters and optimization targets
Output: Detailed breakdown showing which rules block most signals
```

**각 이유별 최적화:**

| 이유 | 의미 | 높으면 | 대응 |
|------|------|--------|------|
| **TTL_EXPIRED** | 신호 유효시간 초과 | 신호 대기 시간 길음 | signal_ttl_ms ↑ |
| **DAILY_LIMIT** | 일일 한도 도달 | 거래 기회 제한 | max_orders_per_day ↑ |
| **COOLDOWN** | 쿨다운 기간 미경과 | 과도한 안전 대기 | cooldown_sec ↓ |
| **ONE_POSITION** | 포지션 중복 제한 | 단일 포지션 강제 | one_position_only: false 검토 |

---

### Category 4: AI Score Distribution
```
Metric: SENT vs REJECTED - count, average, min, max scores
Purpose: Validate AI model quality and threshold effectiveness
Output: Comparative statistics showing score separation
```

**해석:**

```
SENT avg > REJECTED avg
  ↓
✅ AI 필터 정상 작동
```

```
SENT avg ≈ REJECTED avg
  ↓
⚠️ ai_score_cut 임계값 조정 필요
```

```
SENT avg < REJECTED avg
  ↓
❌ 비정상 상황 → 데이터 재검토
```

**프롬프트 튜닝 방향:**
- 점수 분리 명확 → 현재 프롬프트 우수
- 점수 분리 애매 → 프롬프트에 명확한 기준 추가
- 고분산 (범위 큼) → 신호 생성 불일관 → 프롬프트 정제

---

### Category 5: Per-Symbol Signal Frequency
```
Metric: SENT/REJECTED/Total/Exec% per symbol
Purpose: Detect universe balance and symbol-specific biases
Output: Breakdown showing which symbols dominate
```

**균형 평가:**
```
Symbol   SENT  REJECTED  Total  Exec %
005930    267    148      415   64.34%
035420    290    156      446   65.02%
068270    243    130      373   65.14%
```

✅ 균등분포 (약 ±3%) → 우주 설정 적절
⚠️ 심한 편중 (>10%) → AI 바이어스 또는 시장 특성

---

### Category 6: Per-Version Statistics
```
Metric: Created/Sent/Rejected/Exec% per params_version_id
Purpose: Enable A/B testing and track parameter optimization
Output: Version-by-version performance comparison
```

**버전 비교 (A/B 테스트):**
```
Version              Created  Sent  Rejected  Exec %
2026-01-28_02          500   340      160    68.00%  ← 최신
2026-01-28_01         1234   800      434    64.87%  ← 이전
```

**의사결정:**
- 최신 버전 exec% ↑ → 파라미터 개선 ✅
- 최신 버전 exec% ↓ → 파라미터 악화 ❌
- 신호 개수 급변 → 의도한 변경인지 확인

---

### Category 7: Rejection Reasons by Version
```
Metric: Rejection reason counts grouped by params_version_id
Purpose: Correlate parameter changes with filter effectiveness
Output: Per-version breakdown of what blocked signals
```

**검증 예시:**
```
If changed: cooldown_sec 30 → 15
Expected: COOLDOWN 비율 감소 ✅
If not observed: 설정 재검토 필요

If changed: max_orders_per_day 8 → 10
Expected: DAILY_LIMIT 비율 감소 ✅
If not observed: 캐시 또는 재시작 필요
```

---

## 📐 Database Schema (execution_log table)

```sql
CREATE TABLE execution_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,                    -- 타임스탬프 (YYYY-MM-DD HH:MM:SS.mmm)
    module TEXT NOT NULL,                -- "APP32" (실행) 또는 "APP64" (신호)
    symbol TEXT NOT NULL,                -- 종목 코드
    action TEXT NOT NULL,                -- "BUY" / "SELL"
    decision TEXT NOT NULL,              -- "SENT" / "REJECTED" / "CREATED"
    rejection_reason TEXT,               -- 거절 이유 또는 NULL
    ai_score REAL NOT NULL,              -- 신호 점수 (0.0-1.0)
    params_version_id TEXT NOT NULL,     -- 파라미터 버전
    context TEXT                         -- JSON 추가 정보
);
```

---

## 🎯 Signal Quality Evaluation Process

### Step 1: Basic Health Check
```python
✓ total_signals > 0
  └─ 신호 생성 확인

✓ execution_rate 20-80%
  └─ 필터 균형 적절성

✓ SENT_avg_score > REJECTED_avg_score
  └─ AI 필터 작동 확인
```

### Step 2: Rejection Analysis
```python
1. 지배적 거절 이유 파악 (예: COOLDOWN 50%)
2. 파라미터 기대값과 비교
3. 임계값 조정 필요성 판단
```

### Step 3: Version Comparison
```python
1. 최신 버전이 개선했는가?
2. 거절 패턴이 예상대로 변했는가?
3. 신호 품질 일관성 유지?
```

### Step 4: AI Prompt Refinement
```python
1. 점수 분포 불량 → 프롬프트 명확도 개선
2. 편중된 종목 → AI 바이어스 감지 및 수정
3. 높은 분산 → 프롬프트 정제 및 일관성 강화
```

---

## 💻 Advanced SQL Queries

### Time-Series Signal Analysis
```sql
SELECT 
    strftime('%H', ts) as hour,
    COUNT(*) as signal_count,
    SUM(CASE WHEN decision='SENT' THEN 1 ELSE 0 END) as sent,
    ROUND(100.0 * SUM(CASE WHEN decision='SENT' THEN 1 ELSE 0 END) / COUNT(*), 2) as exec_pct
FROM execution_log
WHERE module='APP32'
GROUP BY hour
ORDER BY hour;
```

### Per-Rejection-Reason Context Analysis
```sql
SELECT symbol, action, ai_score, context
FROM execution_log
WHERE decision='REJECTED' AND rejection_reason='TTL_EXPIRED'
ORDER BY ts DESC
LIMIT 20;
```

### Score Evolution by Version
```sql
SELECT 
    params_version_id,
    decision,
    COUNT(*) as count,
    ROUND(AVG(ai_score), 4) as avg_score,
    ROUND(MIN(ai_score), 4) as min_score,
    ROUND(MAX(ai_score), 4) as max_score
FROM execution_log
WHERE module='APP32'
GROUP BY params_version_id, decision
ORDER BY params_version_id DESC;
```

---

## 📋 Analysis Output Example

```
============================================================
  QUANT-EVO Signal Quality Analysis
  Generated: 2026-01-28 13:55:35
============================================================

1. Signal Generation Overview
   Total signals generated (APP64):      1234

2. Execution vs Rejection Rate
   SENT (approved):                       800 (64.95%)
   REJECTED (filtered):                   434 (35.05%)
   
3. Rejection Reason Distribution
   DAILY_LIMIT           186 (42.87%)
   COOLDOWN              147 (33.87%)
   TTL_EXPIRED           87  (20.05%)
   ONE_POSITION          14  (3.22%)

4. AI Score Distribution
   SENT avg score:       0.7523
   REJECTED avg score:   0.6891
   → AI filter working correctly ✅

5. Per-Symbol Frequency
   005930    267 sent (64.34%)
   035420    290 sent (65.02%)
   068270    243 sent (65.14%)
   → Balanced distribution ✅

6. Per-Version Statistics
   2026-01-28_02  exec_rate: 68.00%
   2026-01-28_01  exec_rate: 64.87%
   → Latest version improved ✅
```

---

## 🔐 Data Preservation

**중요한 원칙:**
- ✅ 모든 로그는 영구 보관
- ✅ 분석 중 데이터 수정 금지
- ✅ 언제든 과거 데이터 재분석 가능
- ✅ 완전한 감시 추적 유지

---

## 🚀 Usage Workflow

### 1. Run Trading System
```bash
# Terminal 1: APP64 (신호 생성)
python app64/signal_engine.py

# Terminal 2: APP32 (실행)
python app32/main.py
```

### 2. Run Analysis
```bash
# 거래 실행 후 (충분한 데이터 수집 후)
python scripts/analyze_signals.py
```

### 3. Review Results
```
- 거절 이유 분포 확인
- AI 점수 비교 검토
- 버전별 성능 비교
- 최적화 필요 항목 식별
```

### 4. Adjust Parameters
```python
# strategy_params.json 수정
{
  "version": "2026-01-28_02",  # 버전 증가
  "signal": {...},
  "execution": {...},
  "risk": {...}
}
```

### 5. Repeat (A/B Testing)
```
이전 버전과 새 버전 데이터 비교
→ 개선 여부 검증
→ 더 나은 버전 선택 또는 추가 최적화
```

---

## 📌 Key Takeaways

| 지표 | 양호 | 경고 | 위험 |
|------|------|------|------|
| **Exec Rate** | 60-80% | 30-60% | <30% 또는 >80% |
| **Score Separation** | SENT > REJECTED | ≈ 같음 | SENT < REJECTED |
| **Symbol Distribution** | ±5% 이내 | ±5-10% | >10% 편중 |
| **Rejection Dominance** | 균형 | 하나 >50% | 하나 >70% |

모든 데이터는 완전하게 보관되며, 필요시 더 깊은 분석을 위해 SQL 직접 쿼리 가능합니다.
