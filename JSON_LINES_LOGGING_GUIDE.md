# JSON Lines 로깅 구현 가이드 (Task 3)

## 개요

QUANT-EVO 거래 시스템에 **구조화된 JSON Lines 로깅**을 추가했습니다. 이는 기존 SQLite 데이터베이스 로깅을 **보완**합니다 (대체 아님).

### 주요 특징
- ✅ **순차 추가형** (Append-only) JSON Lines 형식
- ✅ **파라미터 스냅샷** 포함 (거래 필터 파라미터 추적)
- ✅ **4가지 이벤트 타입**: SIGNAL_CREATED, INTENT_INSERTED, EXEC_SENT, EXEC_REJECTED
- ✅ **새로운 분석 지표**: 프롬프트 공격성 지수 (aggressiveness index)
- ✅ **자동 삭제 없음** (완전한 데이터 보존)
- ✅ **거래 로직 미변경** (로깅만 추가)

---

## 1. 파일 구조

```
shared/
  logs/                    # JSON Lines 로그 파일 저장
    app64_20260128.jsonl  # APP64 로그 (날짜별)
    app32_20260128.jsonl  # APP32 로그 (날짜별)
  reports/                # CSV 리포트 저장
    metrics.csv
    rejection_analysis.csv
    aggressiveness_index.csv
    per_symbol.csv
    per_version.csv
```

---

## 2. JSON Lines 로그 포맷

각 라인은 **독립적인 JSON 객체**입니다. (배열 아님)

### 2.1 SIGNAL_CREATED (APP64)

신호가 생성되어 orders_intent 테이블에 삽입될 때 기록됩니다.

```json
{
  "ts": "2026-01-28T14:35:42.123Z",
  "module": "APP64",
  "event_type": "SIGNAL_CREATED",
  "symbol": "005930",
  "action": "BUY",
  "ai_score": 0.75,
  "params_version_id": "2026-01-28_01",
  "ttl_ms": 5000,
  "context_desc": "BUY signal generated and inserted to orders_intent"
}
```

**필드 설명:**
- `ts`: ISO 8601 타임스탐프 (UTC)
- `module`: "APP64" (신호 엔진)
- `event_type`: "SIGNAL_CREATED"
- `symbol`: 종목 코드 (예: "005930")
- `action`: "BUY" 또는 "HOLD" (HOLD는 로깅되지 않음)
- `ai_score`: AI 신뢰도 점수 (0.00 ~ 1.00)
- `params_version_id`: 전략 버전
- `ttl_ms`: 신호 유효시간 (밀리초)

### 2.2 INTENT_INSERTED (APP64)

```json
{
  "ts": "2026-01-28T14:35:42.123Z",
  "module": "APP64",
  "event_type": "INTENT_INSERTED",
  "symbol": "005930",
  "action": "BUY",
  "ai_score": 0.75,
  "params_version_id": "2026-01-28_01",
  "ttl_ms": 5000
}
```

현재 구현에서는 SIGNAL_CREATED와 동일한 시점에 로깅됩니다.

### 2.3 EXEC_SENT (APP32)

신호가 모든 필터를 통과하여 실행되었을 때 기록됩니다.

```json
{
  "ts": "2026-01-28T14:35:43.456Z",
  "module": "APP32",
  "event_type": "EXEC_SENT",
  "symbol": "005930",
  "action": "BUY",
  "ai_score": 0.75,
  "params_version_id": "2026-01-28_01",
  "params_snapshot": {
    "cooldown_sec": 30,
    "max_orders_per_day": 5,
    "one_position_only": true
  }
}
```

**params_snapshot**: 실행 시점의 실행 필터 파라미터

### 2.4 EXEC_REJECTED (APP32)

신호가 필터에 의해 거절되었을 때 기록됩니다.

```json
{
  "ts": "2026-01-28T14:35:43.456Z",
  "module": "APP32",
  "event_type": "EXEC_REJECTED",
  "symbol": "005930",
  "action": "BUY",
  "ai_score": 0.75,
  "params_version_id": "2026-01-28_01",
  "rejection_reason": "COOLDOWN",
  "context": {
    "elapsed_sec": 5.2,
    "remaining_sec": 24.8,
    "cooldown_sec": 30
  }
}
```

**rejection_reason** (4가지):
- `TTL_EXPIRED`: 신호 유효시간 초과
- `DAILY_LIMIT`: 일일 거래 한도 도달
- `COOLDOWN`: 마지막 거래 후 쿨다운 미경과
- `ONE_POSITION`: 기존 포지션 존재

---

## 3. 구현 상세

### 3.1 APP64 수정 사항 (app64/signal_engine.py)

#### 새로운 함수:

```python
def now_iso():
    """ISO 8601 타임스탐프 생성"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def log_jsonl(event_type, symbol, action, ai_score, params_version_id, ttl_ms, **kwargs):
    """JSON Lines 포맷으로 로그 파일에 이벤트 추가"""
    # shared/logs/app64_YYYYMMDD.jsonl에 한 줄의 JSON 추가
```

#### 사용 예:

```python
# SIGNAL_CREATED 이벤트 로깅
log_jsonl('SIGNAL_CREATED', sym, action, score, ver, ttl, 
         context_desc="BUY signal generated and inserted to orders_intent")
```

### 3.2 APP32 수정 사항 (app32/main.py)

#### 새로운 함수:

```python
def log_jsonl(event_type, symbol, action, ai_score, params_version_id, 
              rejection_reason=None, cooldown_sec=0, max_orders_per_day=0, 
              one_position_only=False, **kwargs):
    """JSON Lines 포맷으로 로그 파일에 이벤트 추가"""
    # shared/logs/app32_YYYYMMDD.jsonl에 한 줄의 JSON 추가

def log_execution_with_jsonl(conn, ts, symbol, action, decision, rejection_reason, 
                             ai_score, params_version_id, context="", cooldown_sec=0, 
                             max_orders_per_day=0, one_position_only=False):
    """DB 로깅 + JSON Lines 로깅 통합 함수"""
    # 1. DB 로깅 (기존)
    # 2. JSON Lines 로깅 (새로움)
```

#### 사용 예:

```python
# 거절 로깅
log_execution_with_jsonl(
    conn, current_ts, symbol, action, "REJECTED", 
    RejectionReason.TTL_EXPIRED, score, ver, 
    context=context, cooldown_sec=cooldown_sec, 
    max_orders_per_day=max_orders_per_day, 
    one_position_only=one_position_only
)

# 승인 로깅
log_execution_with_jsonl(
    conn, current_ts, symbol, action, "SENT", None, 
    score, ver, context="", cooldown_sec=cooldown_sec, 
    max_orders_per_day=max_orders_per_day, 
    one_position_only=one_position_only
)
```

---

## 4. 분석 도구: tools/analyze_logs.py

### 4.1 사용법

```bash
python tools/analyze_logs.py
```

자동으로:
1. `shared/logs/` 디렉토리의 모든 `.jsonl` 파일 읽기
2. 이벤트 분석 및 메트릭 계산
3. 콘솔에 요약 리포트 출력
4. `shared/reports/` 디렉토리에 CSV 파일 생성

### 4.2 콘솔 출력 예

```
======================================================================
QUANT-EVO TRADING SYSTEM - JSON LINES LOG ANALYSIS
======================================================================

[EVENT COUNTS]
  Total Events:           1523
  SIGNAL_CREATED:         500
  INTENT_INSERTED:        500
  EXEC_SENT:              450
  EXEC_REJECTED:          50

[EXECUTION RATES]
  Sent Rate:              90.0%
  Rejected Rate:          10.0%

[REJECTION REASONS]
  COOLDOWN            :   25 ( 50.0%)
  TTL_EXPIRED         :   20 ( 40.0%)
  DAILY_LIMIT         :    5 ( 10.0%)

[AI SCORE STATISTICS]
  SENT:
    Count:    450
    Mean:     0.7523
    StdDev:   0.0821
    Min/Max:  0.5512 / 0.8994
  REJECTED:
    Count:    50
    Mean:     0.6234
    StdDev:   0.0945
    Min/Max:  0.5234 / 0.7821

[ACTION DISTRIBUTION (SENT)]
  BUY:                    315 (70.0%)
  SELL:                   135 (30.0%)

[PROMPT AGGRESSIVENESS INDEX]
  Time Window:            60.0 minutes
  Intents per Minute:     8.3333
  Buy Ratio:              0.7000 (70.0%)
  Aggressiveness Score:   87.17

[PER-SYMBOL SUMMARY]
  005930: Created=200, Sent=180, Rejected=20
  035420: Created=150, Sent=135, Rejected=15
  068270: Created=150, Sent=135, Rejected=15

[PER-VERSION SUMMARY]
  2026-01-28_01: Created=500, Sent=450, Rejected=50

======================================================================
```

### 4.3 생성되는 CSV 파일

#### metrics.csv
```csv
metric_name,value
total_events,1523
signal_created,500
intent_inserted,500
exec_sent,450
exec_rejected,50
sent_rate_percent,90.00
rejected_rate_percent,10.00
buy_actions,315
sell_actions,135
ai_score_sent_mean,0.7523
ai_score_rejected_mean,0.6234
```

#### rejection_analysis.csv
```csv
rejection_reason,count,percentage
COOLDOWN,25,50.00
TTL_EXPIRED,20,40.00
DAILY_LIMIT,5,10.00
```

#### aggressiveness_index.csv
```csv
metric,value
time_window_minutes,60.00
intents_per_minute,8.3333
buy_ratio,0.7000
aggressiveness_score,87.17
```

#### per_symbol.csv
```csv
symbol,created,sent,rejected
005930,200,180,20
035420,150,135,15
068270,150,135,15
```

#### per_version.csv
```csv
version,created,sent,rejected
2026-01-28_01,500,450,50
```

---

## 5. 프롬프트 공격성 지수 (Aggressiveness Index)

### 정의

프롬프트 공격성 지수는 AI 신호 생성의 **적극성 정도**를 측정합니다.

### 5.1 지수 1: 분당 인텐트율 (Intents per Minute)

```
intents_per_minute = intent_inserted_count / elapsed_minutes
```

**의미:**
- 높을수록: 더 자주 신호 생성 → 공격적 프롬프트
- 낮을수록: 드문 신호 → 보수적 프롬프트

**예:**
- 60분 동안 500개 인텐트 → 8.33 per minute (공격적)
- 60분 동안 100개 인텐트 → 1.67 per minute (보수적)

### 5.2 지수 2: BUY 비율 (Buy Ratio)

```
buy_ratio = buy_actions / total_intents
```

**의미:**
- 높을수록: BUY 신호가 많음 → 매수 기울기 강함
- 낮을수록: SELL 신호가 많음 또는 HOLD만 생성

**예:**
- 500개 중 350 BUY → 0.70 (70% 매수 기울기)
- 500개 중 100 BUY → 0.20 (20% 매수 기울기)

### 5.3 종합 공격성 점수 (Aggressiveness Score)

```
aggressiveness_score = 
  intents_per_minute * 0.5 + 
  (buy_ratio * 100) * 0.5
```

**정규화 방식:**
- `intents_per_minute`: 직접 사용 (0 ~ ∞)
- `buy_ratio * 100`: 0 ~ 100 범위로 변환

**해석:**
- 0 ~ 30: 보수적 프롬프트
- 30 ~ 70: 중간 수준 프롬프트
- 70 ~ 100: 공격적 프롬프트
- 100+: 매우 공격적 프롬프트

---

## 6. 데이터 보존 정책

### ✅ 보존
- 모든 `.jsonl` 파일: 영구 보존
- 모든 거래 기록: 삭제 불가

### ❌ 자동 삭제 없음
- `analyze_logs.py`는 **읽기 전용** (분석만 수행)
- 로그 파일 삭제 로직: **없음**
- 사용자가 직접 관리해야 함

---

## 7. 거래 로직 변경 사항

### ❌ 변경 없음
- 신호 생성 로직: 동일
- 필터 로직: 동일
- 포지션 관리: 동일
- 리스크 제어: 동일

### ✅ 추가사항
- JSON Lines 로깅 함수 호출 (로깅만)
- 파라미터 스냅샷 수집 (메타데이터)

---

## 8. 사용 예시

### 8.1 시나리오: 프롬프트 버전 비교

두 개의 다른 프롬프트를 테스트하려면:

**단계 1:** 프롬프트 A로 1시간 실행
```bash
# strategy_params.json에서 signal.ai_score_cut 조정
# APP64 실행: 500개 신호 생성
# APP32 실행: 450개 신호 승인, 50개 거절
```

**단계 2:** 분석
```bash
python tools/analyze_logs.py
# aggressiveness_score 기록: 85.3
```

**단계 3:** 프롬프트 B로 변경 후 1시간 실행
```bash
# 같은 방식으로 재실행
# aggressiveness_score 기록: 72.1
```

**단계 4:** 비교
- 프롬프트 A: 85.3 (더 공격적, 높은 신호율)
- 프롬프트 B: 72.1 (더 보수적, 낮은 신호율)
- 선택: 거절률, 실행률, 심볼 편향 등을 함께 검토

---

## 9. 통합 워크플로우

```
┌─────────────────────────────────────────┐
│  1. 전략 파라미터 설정                   │
│     (strategy_params.json)              │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  2. APP64 신호 생성                     │
│     → shared/logs/app64_*.jsonl         │
│     → SIGNAL_CREATED 이벤트            │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  3. APP32 거래 실행                     │
│     → shared/logs/app32_*.jsonl         │
│     → EXEC_SENT / EXEC_REJECTED         │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  4. 분석 및 리포팅                      │
│     python tools/analyze_logs.py        │
│     → shared/reports/*.csv              │
│     → 콘솔 요약 리포트                  │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  5. 프롬프트 튜닝                       │
│     (aggressiveness_index 기반)         │
│     → 신호율, BUY 비율, 거절 분석       │
└─────────────────────────────────────────┘
```

---

## 10. 주요 이점

✅ **구조화된 형식**: 쉽게 파싱 가능한 JSON 라인 형식  
✅ **파라미터 추적**: 각 이벤트마다 파라미터 스냅샷 보존  
✅ **다양한 분석**: 이벤트 타입, 거절 이유, AI 점수 분포 등  
✅ **공격성 지수**: 프롬프트 성향 정량화  
✅ **보존 정책**: 모든 데이터 영구 보존  
✅ **비파괴 분석**: 읽기 전용 분석 도구  
✅ **자동 리포팅**: CSV 생성으로 스프레드시트 연동 용이

---

## 11. 트러블슈팅

### Q1: JSON Lines 파일이 생성되지 않음
**A:** shared/logs/ 디렉토리 권한 확인
```bash
python -c "from pathlib import Path; Path('shared/logs').mkdir(parents=True, exist_ok=True)"
```

### Q2: 분석 결과가 비어있음
**A:** 이벤트가 아직 없거나 파일명 확인
```bash
ls -la shared/logs/
```

### Q3: aggressiveness_score가 0
**A:** intent_inserted 이벤트가 없거나 elapsed_minutes가 0
- APP64가 정상 실행 중인지 확인
- 실행 시간이 충분한지 확인 (최소 1분 이상)

---

## 부록: 코드 스니펫

### APP64에서 로깅 추가

```python
# app64/signal_engine.py
if action != "HOLD":
    conn.execute(
        "INSERT INTO orders_intent(...) VALUES (...)",
        (...)
    )
    log_signal(conn, current_ts, sym, action, score, ver, context)
    
    # ✅ 새로운 로깅
    log_jsonl('SIGNAL_CREATED', sym, action, score, ver, ttl, 
             context_desc="BUY signal generated and inserted to orders_intent")
```

### APP32에서 로깅 추가

```python
# app32/main.py - 거절
log_execution_with_jsonl(
    conn, current_ts, symbol, action, "REJECTED", 
    RejectionReason.COOLDOWN, score, ver, 
    context=context, cooldown_sec=cooldown_sec, 
    max_orders_per_day=max_orders_per_day, 
    one_position_only=one_position_only
)

# 승인
log_execution_with_jsonl(
    conn, current_ts, symbol, action, "SENT", None, score, ver, 
    context="", cooldown_sec=cooldown_sec, 
    max_orders_per_day=max_orders_per_day, 
    one_position_only=one_position_only
)
```
