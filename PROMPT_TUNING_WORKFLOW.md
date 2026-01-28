# AI Prompt Tuning Workflow

## 📋 개요

이 워크플로우는 실행 로그만을 사용하여 AI 거래 프롬프트를 평가하고 개선하는 **데이터 기반 방법론**입니다.

**원칙:**
- ✅ Dry-run only (실제 자금 없음)
- ✅ 로그 데이터 기반 (과학적 분석)
- ✅ 복잡한 ML 불필요 (간단한 통계)
- ✅ 자동화된 진단 (actionable feedback)

---

## 🚀 5단계 워크플로우

### Step 1: 데이터 수집 (1-2일)

**목표:** 충분한 신호 데이터 축적

```bash
# Terminal 1
python app64/signal_engine.py

# Terminal 2
python app32/main.py

# 최소 500개 신호 생성 대기 (충분한 통계 확보)
```

**체크:** 
```sql
SELECT COUNT(*) FROM execution_log WHERE module='APP64' AND decision='CREATED';
-- 결과: 500+
```

---

### Step 2: 프롬프트 건강도 진단

```bash
python scripts/evaluate_prompt.py
```

**출력 해석:**

#### 2-1. Signal Distribution Analysis
```
Mean score:        0.72
Std deviation:     0.10
Score range:       0.50 ~ 0.95
```

**진단:**

| 결과 | 의미 | 액션 |
|------|------|------|
| **mean 0.70-0.75** | ✅ 적절 | 유지 |
| **mean > 0.80** | ❌ 공격적 | 낮은 점수 신호 생성 장려 |
| **mean < 0.60** | ❌ 보수적 | 신호 생성 개수 증가 |
| **std < 0.05** | ⚠️ 단조 | 평가 기준 명확화 |
| **std > 0.15** | ⚠️ 불일관 | 기준 일정화 |

#### 2-2. Discrimination Index
```
DI: 1.18
SENT avg:     0.762
REJECTED avg: 0.635
```

**진단:**

| 결과 | 의미 | 액션 |
|------|------|------|
| **DI > 1.0** | ✅ 좋은 판별력 | AI 유효함 |
| **DI 0.5-1.0** | ⚠️ 중간 판별력 | 프롬프트 개선 고려 |
| **DI < 0.5** | ❌ 판별력 없음 | 프롬프트 재평가 필요 |

#### 2-3. Rejection Reason Analysis
```
TTL_EXPIRED:  87 (20%)  avg=0.758  ← 높음!
DAILY_LIMIT:  186 (43%) avg=0.742
COOLDOWN:     147 (34%) avg=0.751  ← 높음!
ONE_POSITION: 14 (3%)   avg=0.763
```

**진단:**

```
TTL_EXPIRED avg > 0.75 & 20%
→ 좋은 신호들이 시간초과로 만료 중
→ 프롬프트 문제 아님, 필터 문제 (signal_ttl_ms 증가)

COOLDOWN avg > 0.75 & 34%
→ 좋은 신호들이 쿨다운으로 차단 중
→ 필터 문제 (cooldown_sec 감소)
```

#### 2-4. Symbol Bias Analysis
```
005930: avg=0.763 (415 signals)
035420: avg=0.745 (446 signals)
068270: avg=0.722 (373 signals)

Bias Index: 0.041
```

**진단:**

| Bias Index | 의미 | 액션 |
|-----------|------|------|
| **< 0.03** | ✅ 중립적 | 종목 편향 없음 |
| **0.03-0.05** | ⚠️ 약한 편향 | 모니터링 |
| **> 0.05** | ❌ 심한 편향 | 프롬프트 종목별 기준 추가 |

#### 2-5. Time-of-Day Bias Analysis
```
Hour  Count  AvgScore
09    50     0.765
10    120    0.751
11    85     0.742
...
Time Bias Index: 0.028 ✅
```

**진단:**

| Time Bias | 의미 | 액션 |
|-----------|------|------|
| **< 0.03** | ✅ 시간 중립 | OK |
| **0.03-0.05** | ⚠️ 약한 시간 편향 | 모니터링 |
| **> 0.05** | ❌ 심한 편향 | 프롬프트 시간 독립화 |

#### 2-6. Automatic Diagnosis
```
발견된 문제: 2개

❌ [OVER_AGGRESSIVE] 평균 점수가 0.81로 과도하게 높음
   → 프롬프트: 낮은 점수 신호 생성 장려

⚠️  [GOOD_SIGNALS_REJECTED] COOLDOWN으로 거절된 신호의 
     평균 점수 0.751
   → 필터 설정 검토 필요 (COOLDOWN 임계값 완화?)
```

---

### Step 3: 근본 원인 분석

**프롬프트 문제 vs 필터 문제 구분:**

#### 프롬프트 문제 신호
```
✗ mean_score > 0.80
✗ std < 0.05 (단조)
✗ DI < 0.5
✗ 특정 시간/종목 편향 큼
```

#### 필터 문제 신호
```
✓ mean_score 0.65-0.75 (정상)
✓ DI > 1.0 (판별력 좋음)
✗ TTL_EXPIRED avg >> 0.75
✗ COOLDOWN avg >> 0.75
```

**예시:**
```
진단 결과:
- mean_score: 0.72 ✓ (정상)
- DI: 1.18 ✓ (좋음)
- TTL_EXPIRED avg: 0.78 ✗ (높음)
- COOLDOWN avg: 0.75 ✗ (높음)

결론: 필터 문제 (프롬프트 아님)
액션: strategy_params.json 조정
```

---

### Step 4: 개선 및 버전 관리

#### 옵션 A: 프롬프트 개선 (APP64)

**문제:** mean_score 0.82, std 0.03 (과도하게 공격적)

**현재 프롬프트:**
```python
# signal_engine.py
"Score signal strength 0.70-0.90"
"Only high-conviction signals"
```

**개선된 프롬프트:**
```python
# signal_engine.py - 수정
"""
Score signal strength on full 0.50-1.00 scale:

0.50-0.60: Weak signals with potential issues
  - Questionable market conditions
  - Uncertain technical indicators
  
0.60-0.70: Moderate signals with some uncertainty
  - Mixed technical indicators
  - Moderate volume confirmation
  
0.70-0.80: Strong signals with good confidence
  - Clear technical setup
  - Strong volume
  
0.80-0.90: Very strong signals with high confidence
  - Excellent technical alignment
  - Exceptional volume
  
0.90-1.00: Exceptional signals (rare)
  - Perfect or near-perfect conditions
  - Multiple confirming indicators
"""
```

**버전 업데이트:**
```json
// strategy_params.json
{
  "version": "2026-01-28_02",  // ← 증가
  // ... (다른 설정)
}
```

#### 옵션 B: 필터 개선 (strategy_params.json)

**문제:** TTL_EXPIRED 20%, COOLDOWN 34% (필터가 좋은 신호 차단)

**현재 설정:**
```json
{
  "signal": {
    "signal_ttl_ms": 5000,    // 5초
  },
  "execution": {
    "cooldown_sec": 30,       // 30초
  }
}
```

**개선된 설정:**
```json
{
  "version": "2026-01-28_02",  // ← 증가
  "signal": {
    "signal_ttl_ms": 10000,   // 5000 → 10000 (2배)
  },
  "execution": {
    "cooldown_sec": 15,       // 30 → 15 (반으로)
  }
}
```

**검증 기록:**
```
버전: 2026-01-28_02
변경:
  - signal_ttl_ms 5000 → 10000 (TTL_EXPIRED 신호 손실 방지)
  - cooldown_sec 30 → 15 (COOLDOWN 거절 감소)
기대 효과:
  - TTL_EXPIRED % 감소 (20% → ~5-10%)
  - COOLDOWN % 감소 (34% → ~20%)
  - 전체 실행율 증가 (65% → 75%+)
```

---

### Step 5: 효과 검증 (A/B 비교)

**새 버전 실행:**
```bash
# 기존 데이터는 그대로 유지
# 새로운 버전부터는 version="2026-01-28_02" 기록됨

python app64/signal_engine.py
python app32/main.py

# 충분한 데이터 수집 (500+ 신호)
```

**비교 분석:**
```bash
python scripts/evaluate_prompt.py
```

**비교 쿼리:**
```sql
-- 버전별 성능 비교
SELECT 
    params_version_id,
    COUNT(*) as total_signals,
    ROUND(AVG(ai_score), 4) as mean_score,
    ROUND(STDDEV(ai_score), 4) as std_score,
    SUM(CASE WHEN decision='SENT' THEN 1 ELSE 0 END) as sent,
    ROUND(100.0 * SUM(CASE WHEN decision='SENT' THEN 1 ELSE 0 END) / COUNT(*), 2) as exec_rate
FROM execution_log
WHERE module='APP32'
GROUP BY params_version_id
ORDER BY params_version_id DESC;

결과:
version              | signals | mean  | std   | sent | exec_rate
2026-01-28_02        | 650     | 0.71  | 0.11  | 520  | 80.00%  ← 새
2026-01-28_01        | 1200    | 0.72  | 0.10  | 800  | 66.67%  ← 이전

분석:
- 실행율 66.67% → 80.00% ✅ (개선!)
- mean_score 안정적 (0.72 → 0.71) ✅
- std 개선 (0.10 → 0.11) ✓
→ 새 버전이 더 나음! 채택
```

---

## 🔍 고급 분석: SQL 쿼리

### 프롬프트 품질 한눈에 보기
```sql
-- 핵심 메트릭 비교
WITH current_version AS (
    SELECT 
        params_version_id,
        ROUND(AVG(CASE WHEN module='APP64' THEN ai_score END), 4) as signal_mean,
        ROUND(STDDEV(CASE WHEN module='APP64' THEN ai_score END), 4) as signal_std,
        ROUND(AVG(CASE WHEN module='APP32' AND decision='SENT' THEN ai_score END), 4) as sent_mean,
        ROUND(AVG(CASE WHEN module='APP32' AND decision='REJECTED' THEN ai_score END), 4) as rejected_mean
    FROM execution_log
    WHERE params_version_id = (SELECT MAX(params_version_id) FROM execution_log)
    GROUP BY params_version_id
)
SELECT 
    'Signal Distribution' as metric,
    signal_mean as value,
    signal_std as variance
FROM current_version
UNION ALL
SELECT 
    'SENT-REJECTED Gap',
    ROUND(sent_mean - rejected_mean, 4),
    ROUND((sent_mean - rejected_mean) / (0.01 + ROUND(STDDEV(CASE WHEN module='APP32' AND decision='SENT' THEN ai_score END), 4) + ROUND(STDDEV(CASE WHEN module='APP32' AND decision='REJECTED' THEN ai_score END), 4)), 4)
FROM current_version;
```

### 거절 신호의 질 분석
```sql
-- 각 거절 이유별로 차단되는 신호의 평균 품질
SELECT 
    rejection_reason,
    COUNT(*) as count,
    ROUND(AVG(ai_score), 4) as mean_score,
    CASE 
        WHEN ROUND(AVG(ai_score), 4) > 0.76 THEN '⚠️  GOOD signals rejected'
        WHEN ROUND(AVG(ai_score), 4) > 0.70 THEN '→ Medium quality'
        ELSE '✓ Low quality (normal)'
    END as quality_verdict
FROM execution_log
WHERE decision='REJECTED'
GROUP BY rejection_reason
ORDER BY mean_score DESC;
```

### 버전별 거절 패턴 추적
```sql
-- 파라미터 변경이 거절 패턴에 미친 영향
SELECT 
    params_version_id,
    rejection_reason,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM execution_log e2 
          WHERE e2.params_version_id = execution_log.params_version_id AND decision='REJECTED'), 2) as pct
FROM execution_log
WHERE decision='REJECTED'
GROUP BY params_version_id, rejection_reason
ORDER BY params_version_id DESC, count DESC;

-- 해석:
-- version_02에서 COOLDOWN % 감소 → cooldown_sec 감소 성공 ✅
-- version_02에서 TTL_EXPIRED % 감소 → signal_ttl_ms 증가 성공 ✅
```

---

## 📌 튜닝 체크리스트

### 시작 전
```
[ ] 최소 500개 신호 수집? (evaluate_prompt.py로 확인)
[ ] 현재 버전의 건강도 진단 완료?
[ ] 프롬프트 vs 필터 문제 파악?
```

### 개선 중
```
[ ] strategy_params.json의 "version" 증가?
[ ] 변경 사항을 주석으로 기록?
[ ] 새 버전에서 최소 500개 신호 수집?
```

### 검증 후
```
[ ] evaluate_prompt.py로 새 버전 분석?
[ ] 버전 비교 쿼리 실행?
[ ] 예상한 개선이 실제로 나타났나?
[ ] 개선 버전을 선택 (또는 추가 튜닝)?
```

---

## 💡 실제 사례

### Case 1: 공격적 프롬프트
```
진단: mean=0.82, std=0.03, DI=0.4

원인: 프롬프트가 거의 모든 신호를 높게 평가

개선: "점수 범위를 0.50-1.00으로 확대, 
       각 범위별 명확한 기준 정의"

결과: mean=0.70, std=0.11, DI=1.05
     → 판별력 2.6배 향상! ✅
```

### Case 2: 필터 과도
```
진단: TTL_EXPIRED 30%, avg=0.81
     COOLDOWN 40%, avg=0.78

원인: signal_ttl_ms 너무 짧음 (5초)
      cooldown_sec 너무 길음 (30초)

개선: signal_ttl_ms 10000
      cooldown_sec 15

결과: TTL_EXPIRED 8%, COOLDOWN 25%
     실행율 60% → 75% ✅
```

### Case 3: 종목 편향
```
진단: 종목 편향 지수 0.071 (>0.05)
     005930: 0.78, 068270: 0.71

원인: 프롬프트가 특정 종목을 선호

개선: "모든 종목에 대해 동등한 평가 기준 적용,
       종목별 특수 조건 제거"

결과: 편향 지수 0.032 ✅
```

---

## 🎯 핵심 원칙

1. **측정**: 로그 데이터로 현상 파악
2. **진단**: 프롬프트 vs 필터 문제 정확히 구분
3. **행동**: 한 가지씩만 변경 (A/B 테스트)
4. **검증**: 버전별 비교로 효과 정량화
5. **반복**: 더 나은 버전까지 지속적 개선

**기억:** 모든 데이터는 영구 보관되므로 언제든 과거 버전과 비교 가능하며, 최적의 설정을 찾을 때까지 안전하게 실험할 수 있습니다.

---

## 🚀 빠른 시작

```bash
# 1. 데이터 수집
python app64/signal_engine.py &
python app32/main.py &
# ... 1-2일 대기 (500+ 신호)

# 2. 진단
python scripts/evaluate_prompt.py

# 3. 개선 (필요시)
# - 프롬프트 수정 또는
# - strategy_params.json 조정

# 4. 검증
python scripts/evaluate_prompt.py
```

모든 분석은 자동화되고 데이터 기반이므로, 객관적인 의사결정이 가능합니다.
