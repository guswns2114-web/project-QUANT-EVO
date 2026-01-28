# Signal Quality Analysis Guide

## 개요

`scripts/analyze_signals.py`는 거래 신호의 품질을 평가하기 위한 **읽기 전용 분석 도구**입니다.

- 데이터베이스 변경 없음 (완전한 감시 추적)
- 실시간 거래와 독립적으로 실행 가능
- AI 프롬프트 및 전략 파라미터 최적화의 근거 제공

---

## 실행 방법

```bash
cd c:\project\QUANT-EVO
python scripts/analyze_signals.py
```

---

## 분석 지표 및 해석

### 1️⃣ Signal Generation Overview
**메트릭:** 총 신호 생성 개수 (APP64)

**의미:**
- AI가 활발한가? (적절한 신호 빈도)
- 과거 거래 기간 동안 총 얼마나 많은 기회가 있었는가?

**해석:**
```
Total signals generated (APP64):      1234
```
- 며칠 데이터인지 알면 시간당 신호 빈도 계산 가능
- 신호 생성이 너무 적으면: AI 프롬프트가 보수적일 수 있음
- 신호 생성이 너무 많으면: AI 프롬프트가 과민할 수 있음

---

### 2️⃣ Execution vs Rejection Rate
**메트릭:** SENT (승인), REJECTED (거절) 비율

**의미:**
- 얼마나 많은 신호가 실제로 거래되는가?
- 위험 필터가 얼마나 효과적인가?

**해석:**
```
SENT (approved):                    800 (64.95%)
REJECTED (filtered):                434 (35.05%)
```

| 실행율 | 의미 | 액션 |
|--------|------|------|
| **> 80%** | 필터가 너무 느슨함 | 위험 규칙 강화 또는 필터 추가 |
| **60-80%** | 적절한 균형 | 현재 설정 유지 |
| **30-60%** | 중간 정도 거절 | 필터 적절성 검토 |
| **< 30%** | 필터가 너무 엄격함 | 필터 완화 또는 임계값 조정 |

**AI 평가 관점:**
- 높은 실행율 + 높은 신호 점수 = AI가 잘 작동 중
- 낮은 실행율 + 낮은 신호 점수 = AI 프롬프트 개선 필요

---

### 3️⃣ Rejection Reason Distribution
**메트릭:** 거절 이유별 분포

**의미:**
- 어떤 위험 규칙이 가장 많이 작동하는가?
- 과도한 필터가 있는가?

**예시:**
```
DAILY_LIMIT           186 (42.87%)
COOLDOWN              147 (33.87%)
TTL_EXPIRED           87  (20.05%)
ONE_POSITION          14  (3.22%)
```

**해석 가이드:**

| 거절 이유 | 높으면 | 낮으면 |
|----------|--------|--------|
| **TTL_EXPIRED** | 신호가 너무 오래 대기 중 | 신호가 빠르게 실행됨 |
| **DAILY_LIMIT** | 일일 한도가 제한적 | 많은 거래 기회 |
| **COOLDOWN** | 과도한 안전 대기 | 빈번한 거래 (과매매 위험) |
| **ONE_POSITION** | 동시 포지션 제약 | 대부분 단일 포지션만 진입 |

**최적화 방향:**
```python
# TTL_EXPIRED가 50% 이상 → signal_ttl_ms 증가
"signal_ttl_ms": 5000  # → 10000

# COOLDOWN이 60% 이상 → cooldown_sec 감소
"cooldown_sec": 30     # → 15

# DAILY_LIMIT이 70% 이상 → max_orders_per_day 증가
"max_orders_per_day": 8  # → 12
```

---

### 4️⃣ AI Score Distribution
**메트릭:** 신호 점수 분포 (승인 vs 거절)

**의미:**
- AI가 생성하는 신호 점수가 효과적인가?
- 승인된 신호가 정말 더 높은 품질인가?

**예시:**
```
SENT Signals:
  Count:        800
  Avg Score: 0.7523
  Min Score: 0.7001
  Max Score: 0.8912

REJECTED Signals:
  Count:        434
  Avg Score: 0.6891
  Min Score: 0.5501
  Max Score: 0.7999
```

**해석:**

| 상황 | 의미 | 액션 |
|------|------|------|
| **SENT avg > REJECTED avg** | AI 필터 작동 중 | ✅ 좋음. 계속 진행 |
| **SENT avg ≈ REJECTED avg** | 점수로 구분 안 됨 | 🔧 ai_score_cut 조정 필요 |
| **SENT avg < REJECTED avg** | 역설적 상황 | ❌ 데이터 검토 필요 |
| **고분산 (min-max 크면)** | 신호 불안정 | 🔧 AI 프롬프트 개선 |

**AI 프롬프트 최적화:**
```python
# 점수 분리가 명확하면 현재 프롬프트 우수
# 점수 분리가 애매하면:
#   1. 프롬프트에 명확한 기준 추가
#   2. 데이터 품질 재검토
#   3. ai_score_cut 임계값 재조정

# 예: strategy_params.json
"ai_score_cut": 0.70  # SENT avg가 0.75이면, 0.72로 낮추기
```

---

### 5️⃣ Per-Symbol Signal Frequency
**메트릭:** 종목별 신호 빈도 및 실행율

**의미:**
- 거래 종목이 균형잡혀 있는가?
- 특정 종목에 편중되지 않았는가?

**예시:**
```
Symbol       SENT REJECTED Total Exec %
------       ---- -------- ----- ------
005930        267      148   415  64.34%
035420        290      156   446  65.02%
068270        243      130   373  65.14%
```

**해석:**

| 패턴 | 의미 | 액션 |
|------|------|------|
| **균등 분포** | 우주 설정 적절 | ✅ 좋음 |
| **한 종목 편중** | 특정 종목 선호 | 🔧 AI 바이어스 검토 |
| **실행율 불균형** | 종목별 필터 차이 | 🔧 거절 이유 분석 필요 |

**우주 최적화:**
```python
# 편중된 경우:
"max_symbols": 3
# → 더 많은 종목 추가 고려
"max_symbols": 5

# 또는 특정 종목 제외:
"allowed_symbols": ["005930", "035420"]  # 068270 제외
```

---

### 6️⃣ Per-Version Statistics
**메트릭:** 파라미터 버전별 성능 비교 (A/B 테스트)

**의미:**
- 어떤 파라미터 버전이 더 나은 결과를 낼까?
- 최근 변경이 개선했는가?

**예시:**
```
Version              Created  Sent Rejected Exec %
------               -------  ---- -------- ------
2026-01-28_02           500   340      160  68.00%
2026-01-28_01          1234   800      434  64.87%
```

**해석:**

| 발견 | 의미 | 액션 |
|------|------|------|
| **최신 > 이전** | 파라미터 개선 성공 | ✅ 변경 유지 |
| **최신 < 이전** | 파라미터 악화 | ⚠️ 이전 버전 복구 또는 디버깅 |
| **신호 개수 크게 차이** | 신호 빈도 변경 | 🔧 의도한 변경인지 확인 |

**버전 관리:**
```python
# strategy_params.json에서 버전 증가
"version": "2026-01-28_01"  # → "2026-01-28_02"

# 변경 사항 기록
# "2026-01-28_02": cooldown_sec 30→15, max_orders_per_day 8→10
# "2026-01-28_01": 초기 설정
```

---

### 7️⃣ Rejection Reasons by Version
**메트릭:** 버전별 거절 이유 패턴

**의미:**
- 파라미터 변경이 거절 패턴을 어떻게 바꿨는가?
- 의도한 효과가 나타났는가?

**예시:**
```
2026-01-28_02:
  COOLDOWN              80
  DAILY_LIMIT           55
  TTL_EXPIRED           20
  ONE_POSITION          5

2026-01-28_01:
  DAILY_LIMIT          186
  COOLDOWN             147
  TTL_EXPIRED           87
  ONE_POSITION          14
```

**변경 검증:**
```python
# 만약 cooldown_sec를 30초 → 15초로 감소했다면:
# COOLDOWN 비율이 낮아져야 함 ✅

# 만약 max_orders_per_day를 8 → 10으로 증가했다면:
# DAILY_LIMIT 비율이 낮아져야 함 ✅

# 기대한 결과가 안 나타나면 설정 재검토 필요
```

---

## 신호 품질 평가 프로세스

### 단계 1: 기본 체크
```
1. total signals > 0인가? (신호 생성 확인)
2. execution rate 20-80% 범위인가? (필터 적절성)
3. SENT avg > REJECTED avg인가? (AI 효과성)
```

### 단계 2: 거절 분석
```
1. 지배적 거절 이유 파악
2. 예상과 일치하는가?
3. 파라미터 조정이 필요한가?
```

### 단계 3: 버전 비교
```
1. 최신 버전이 개선했는가?
2. 거절 패턴이 변했는가?
3. 신호 품질이 일관성 있는가?
```

### 단계 4: 프롬프트 개선
```
1. AI 점수 분포 분석
2. 이상 신호 패턴 검토
3. 프롬프트 수정 및 테스트
```

---

## SQL 쿼리 예제 (고급 분석)

### 시간대별 신호 분석
```sql
SELECT 
    strftime('%H', ts) as hour,
    COUNT(*) as signal_count,
    SUM(CASE WHEN decision='SENT' THEN 1 ELSE 0 END) as sent,
    SUM(CASE WHEN decision='REJECTED' THEN 1 ELSE 0 END) as rejected
FROM execution_log
WHERE module='APP32'
GROUP BY hour
ORDER BY hour;
```

### 특정 거절 이유의 컨텍스트 분석
```sql
SELECT symbol, action, ai_score, context
FROM execution_log
WHERE decision='REJECTED' AND rejection_reason='TTL_EXPIRED'
ORDER BY ts DESC
LIMIT 10;
```

### 버전별 평균 점수 변화
```sql
SELECT 
    params_version_id,
    decision,
    ROUND(AVG(ai_score), 4) as avg_score,
    COUNT(*) as count
FROM execution_log
WHERE module='APP32'
GROUP BY params_version_id, decision
ORDER BY params_version_id DESC;
```

---

## 주의사항

⚠️ **로그 유지 원칙**
- 분석 후에도 데이터 삭제 금지
- 모든 로그는 완전한 감시 추적 목적
- 언제든 과거 데이터 재분석 가능

⚠️ **통계 유효성**
- 충분한 데이터 확보 후 분석 (최소 100개 신호 권장)
- 단기 변동성 vs 장기 트렌드 구분
- 시장 조건 변화 고려

⚠️ **파라미터 변경 주의**
- 한 번에 하나씩만 변경 (A/B 테스트 원칙)
- 각 버전당 충분한 테스트 기간 필요 (최소 하루)
- 버전 번호 명확하게 기록

---

## 결론

이 분석 도구는 **데이터 기반 의사결정**을 가능하게 합니다:

✅ AI 프롬프트 효과성 검증  
✅ 위험 규칙 최적화  
✅ 파라미터 세트 비교  
✅ 거래 신호 품질 평가  

**기억:** 모든 결정은 로그 데이터에 기반하며, 로그는 영구 보관됩니다.
