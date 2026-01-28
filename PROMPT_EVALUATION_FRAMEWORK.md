# AI Trading Prompt Evaluation Framework

## 개요

실행 로그(`execution_log`)를 사용하여 AI 거래 프롬프트의 품질을 **정량적으로 평가**하고 개선하는 방법.

**핵심 아이디어:**
- AI는 신호 점수(`ai_score`)를 생성
- 필터(`execution` 규칙)가 그 신호를 받아 SENT/REJECTED 결정
- 실행 로그에서 프롬프트의 성향(공격적/보수적)과 품질(정확도)을 측정 가능

---

## 📐 평가 프레임워크

### 1️⃣ 신호 점수 분포 분석 (Signal Score Distribution)

**목적:** 프롬프트가 얼마나 공격적 또는 보수적인가?

**측정:**
```sql
SELECT 
    'APP64' as module,
    COUNT(*) as total_signals,
    ROUND(AVG(ai_score), 4) as mean_score,
    ROUND(MIN(ai_score), 4) as min_score,
    ROUND(MAX(ai_score), 4) as max_score,
    ROUND(
        SQRT(SUM((ai_score - (SELECT AVG(ai_score) FROM execution_log WHERE module='APP64'))*(ai_score - (SELECT AVG(ai_score) FROM execution_log WHERE module='APP64'))) / COUNT(*)),
        4
    ) as std_dev
FROM execution_log 
WHERE module='APP64' AND decision='CREATED';
```

**해석:**

| 지표 | 의미 | 액션 |
|------|------|------|
| **mean_score 높음 (>0.75)** | 프롬프트가 공격적 | 필터링 기준 강화 고려 |
| **mean_score 낮음 (<0.60)** | 프롬프트가 보수적 | 더 많은 신호 생성 촉구 |
| **std_dev 높음 (>0.10)** | 신호 품질 불일관 | 프롬프트 기준 명확화 |
| **std_dev 낮음 (<0.05)** | 신호 품질 일관적 | ✅ 좋음 |

**프롬프트 진단:**
```
mean=0.72, std=0.08
→ 적절한 공격성 + 일관된 품질 ✅

mean=0.82, std=0.03
→ 과도하게 공격적 + 단조로운 점수 ⚠️
(프롬프트가 거의 모든 신호를 높게 평가 → 판별력 없음)

mean=0.55, std=0.15
→ 과도하게 보수적 + 불일관한 평가 ⚠️
(신호 생성이 너무 적고 편차가 큼 → 평가 기준 불명확)
```

---

### 2️⃣ 실행 점수 vs 거절 점수 비교 (Execution Efficiency)

**목적:** 필터가 정말 낮은 점수 신호를 거절하는가? (AI 신호가 유효한가?)

**측정:**
```sql
SELECT 
    decision,
    COUNT(*) as count,
    ROUND(AVG(ai_score), 4) as avg_score,
    ROUND(
        SQRT(SUM((ai_score - (SELECT AVG(ai_score) FROM execution_log WHERE module='APP32' AND decision=decision))*(ai_score - (SELECT AVG(ai_score) FROM execution_log WHERE module='APP32' AND decision=decision))) / COUNT(*)),
        4
    ) as std_score
FROM execution_log 
WHERE module='APP32'
GROUP BY decision;
```

**결과 예시:**
```
SENT:     avg=0.762, std=0.032, count=800
REJECTED: avg=0.635, std=0.078, count=434
```

**판별력 지수 (Discrimination Index):**
```
DI = (SENT_avg - REJECTED_avg) / (SENT_std + REJECTED_std)
   = (0.762 - 0.635) / (0.032 + 0.078)
   = 1.18

해석:
- DI > 1.0: ✅ 좋은 판별력 (점수로 SENT/REJECTED 구분 명확)
- DI 0.5-1.0: ⚠️ 중간 판별력 (점수 분리 애매)
- DI < 0.5: ❌ 나쁜 판별력 (프롬프트 신호 품질 낮음)
```

**진단:**
```
DI 높음 (>1.0)
→ AI 신호 유효 + 필터 정상 작동 ✅
→ 신호 품질 개선 불필요

DI 낮음 (<0.5)
→ AI 점수로 구분 안 됨
→ 프롬프트: 평가 기준 명확화 필요
   또는
→ 필터: ai_score_cut 조정 필요
```

---

### 3️⃣ 거절 이유별 점수 분석 (Rejection Pattern Analysis)

**목적:** 각 필터가 어떤 점수 신호를 거절하는가? (필터 vs 프롬프트 문제 파악)

**측정:**
```sql
SELECT 
    rejection_reason,
    COUNT(*) as count,
    ROUND(AVG(ai_score), 4) as avg_score,
    ROUND(MIN(ai_score), 4) as min_score,
    ROUND(MAX(ai_score), 4) as max_score,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM execution_log WHERE decision='REJECTED'), 2) as pct
FROM execution_log 
WHERE decision='REJECTED'
GROUP BY rejection_reason
ORDER BY count DESC;
```

**결과 예시:**
```
TTL_EXPIRED:  avg=0.758, min=0.701, max=0.891, count=87 (20%)
DAILY_LIMIT:  avg=0.742, min=0.708, max=0.819, count=186 (43%)
COOLDOWN:     avg=0.751, min=0.705, max=0.876, count=147 (34%)
ONE_POSITION: avg=0.763, min=0.712, max=0.841, count=14 (3%)
```

**해석 및 액션:**

| 거절 이유 | 평균 점수 | 의미 | 액션 |
|----------|----------|------|------|
| **TTL_EXPIRED** | 높음 (>0.75) | 좋은 신호가 시간초과 | signal_ttl_ms ↑ |
| **TTL_EXPIRED** | 낮음 (<0.70) | 나쁜 신호가 시간초과 | 프롬프트가 낮은 점수 생성 |
| **COOLDOWN** | 높음 (>0.75) | 쿨다운이 좋은 신호 차단 | cooldown_sec ↓ |
| **COOLDOWN** | 낮음 (<0.70) | 쿨다운이 나쁜 신호 방어 | ✅ 정상 |
| **DAILY_LIMIT** | 높음 (>0.75) | 일일한도가 우수 신호 차단 | max_orders_per_day ↑ |
| **ONE_POSITION** | 높음 (>0.75) | 포지션 제약이 좋은 신호 놓침 | one_position_only: false 검토 |

**프롬프트 진단:**
```
예시 1: TTL_EXPIRED avg = 0.801, 다른 이유 avg = 0.72
→ 높은 점수 신호가 TTL로 만료됨
→ 신호 생성은 양호하나 대기 시간 부족
→ 필터 문제 (signal_ttl_ms 증가), 프롬프트 문제 아님

예시 2: 모든 이유의 avg ≈ 0.64
→ 거절되는 신호가 대부분 낮은 점수
→ 프롬프트가 낮은 점수 신호를 과다 생성
→ 프롬프트 문제 (평가 기준 낮춤)
```

---

### 4️⃣ 시간대별 성향 분석 (Timing Pattern Analysis)

**목적:** 신호 생성이 시간대에 따라 편중되지 않았는가? (타이밍 바이어스)

**측정:**
```sql
SELECT 
    strftime('%H', ts) as hour,
    COUNT(*) as signals,
    ROUND(AVG(ai_score), 4) as avg_score,
    SUM(CASE WHEN decision='SENT' THEN 1 ELSE 0 END) as sent,
    SUM(CASE WHEN decision='REJECTED' THEN 1 ELSE 0 END) as rejected
FROM execution_log 
WHERE module='APP32'
GROUP BY hour
ORDER BY hour;
```

**결과 예시:**
```
Hour  Signals  AvgScore  Sent  Rejected
00    12       0.705     7     5
01    11       0.698     6     5
...
10    125      0.762     85    40  ← 이상 수치
...
```

**분석:**

| 패턴 | 의미 | 액션 |
|------|------|------|
| **균등 분포** | 타이밍 바이어스 없음 ✅ | 프롬프트 중립적 |
| **특정 시간 spike** | 시장 조건 반응 | ✅ 정상 (특정 시간에 거래 기회 많음) |
| **점수 시간대 편차 큼** | 신호 품질 불일관 | 프롬프트: 시간 독립성 개선 필요 |

---

### 5️⃣ 종목별 편향 분석 (Symbol Bias Detection)

**목적:** 프롬프트가 특정 종목을 선호하지 않는가?

**측정:**
```sql
SELECT 
    symbol,
    COUNT(*) as signals,
    ROUND(AVG(ai_score), 4) as avg_score,
    ROUND(STDDEV(ai_score), 4) as std_score,
    SUM(CASE WHEN decision='SENT' THEN 1 ELSE 0 END) as sent
FROM execution_log 
WHERE module='APP32'
GROUP BY symbol
ORDER BY avg_score DESC;
```

**결과 예시:**
```
Symbol  Signals  AvgScore  StdScore  Sent
005930  415      0.763     0.045     267
035420  446      0.745     0.051     290
068270  373      0.722     0.068     243
```

**편향 지수 (Bias Index):**
```
BI = MAX(avg_score) - MIN(avg_score)
   = 0.763 - 0.722
   = 0.041 (4.1%)

해석:
- BI < 3%: ✅ 종목 중립적
- BI 3-5%: ⚠️ 약간의 편향
- BI > 5%: ❌ 심한 편향
```

**진단:**
```
005930만 avg=0.80, 다른 종목 avg=0.70
→ 특정 종목 선호 감지
→ 프롬프트: 종목별 동등 평가 기준 재검토
```

---

## 🎯 프롬프트 문제 vs 필터 문제 구분법

### 프롬프트 문제 신호

```
1. ai_score 분포가 극단적
   - 대부분 >0.80 또는 <0.60
   - std < 0.05 (단조로움)

2. SENT vs REJECTED 점수 비교 낮음
   - DI < 0.5
   - 점수로 구분 안 됨

3. 시간/종목별 편향 큼
   - 특정 시간대 bias
   - 특정 종목 편향

4. 거절 이유별 점수 모두 유사
   - TTL vs COOLDOWN vs DAILY_LIMIT 평균 같음
   - 신호 품질이 균등하게 낮음 → 프롬프트 기준 불명확
```

**개선 방법:**
```python
# 현재 프롬프트 (문제)
"Score range: 0.70 - 0.90 (너무 좁음)"
"Very few signals with 0.60-0.70 range"

# 개선된 프롬프트
"Generate scores across full 0.50 - 1.00 range"
"Use distinct criteria for 0.50-0.60 vs 0.70-0.80 vs 0.90+ ranges"
"Include reasoning for each score band"
```

### 필터 문제 신호

```
1. ai_score 분포는 정상 (평균 0.65-0.75, std 0.08-0.12)
2. DI 높음 (>1.0)
3. TTL_EXPIRED avg >> DAILY_LIMIT avg
   → 좋은 신호가 TTL로 만료되는 중
   → 필터 설정 문제 (signal_ttl_ms 부족)

4. COOLDOWN avg >> 다른 이유 avg
   → 쿨다운이 좋은 신호 차단
   → 필터 설정 문제 (cooldown_sec 과도)
```

**개선 방법:**
```python
# strategy_params.json 조정 (프롬프트 아님)
"signal_ttl_ms": 5000,  # → 10000
"cooldown_sec": 30,     # → 15
```

---

## 📊 실제 튜닝 프로세스

### Phase 1: 데이터 수집 (1-2일)
```
APP64 + APP32 실행
→ 최소 500개 신호 수집
→ 데이터 기반 분석 시작
```

### Phase 2: 현재 상태 진단
```sql
-- 1. 신호 분포 확인
SELECT COUNT(*), ROUND(AVG(ai_score), 4), ROUND(STDDEV(ai_score), 4)
FROM execution_log WHERE module='APP64';

-- 2. 판별력 확인
SELECT decision, COUNT(*), ROUND(AVG(ai_score), 4)
FROM execution_log WHERE module='APP32'
GROUP BY decision;

-- 3. 거절 이유 확인
SELECT rejection_reason, COUNT(*), ROUND(AVG(ai_score), 4)
FROM execution_log WHERE decision='REJECTED'
GROUP BY rejection_reason;

-- 4. 종목 편향 확인
SELECT symbol, COUNT(*), ROUND(AVG(ai_score), 4)
FROM execution_log WHERE module='APP32'
GROUP BY symbol;
```

### Phase 3: 문제 식별
```
위 쿼리 결과를 프레임워크와 대조
→ 프롬프트 문제 vs 필터 문제 판단
→ 우선순위 결정
```

### Phase 4: 개선 (A/B 테스트)

**옵션 A: 프롬프트 튜닝**
```
변경: signal_engine.py의 AI 프롬프트
검증: 새로운 버전에서 ai_score 분포 변화
측정: SENT vs REJECTED 판별력 개선 여부
```

**옵션 B: 필터 튜닝**
```
변경: strategy_params.json의 execution/risk 설정
검증: 새로운 버전에서 rejection_reason 분포 변화
측정: 실행률 및 거절 패턴 개선 여부
```

### Phase 5: 효과 검증
```
이전 버전 vs 새 버전 비교
→ 거절 이유 분포 변화 확인
→ 점수 분포 변화 확인
→ 실행률 변화 확인
→ 예상한 개선이 실제로 나타났는가?
```

---

## 🔍 구체적 튜닝 예제

### 예제 1: 과도하게 공격적인 프롬프트

**진단:**
```
mean_score: 0.82, std: 0.03
DI: 0.4 (낮음)
SENT avg: 0.81, REJECTED avg: 0.77 (차이 작음)
```

**원인:** 프롬프트가 거의 모든 신호를 높게 평가

**개선:**
```
# 프롬프트 수정 (신호 생성 쪽)
# 이전:
"Evaluate signal strength on scale 0.70-0.90"

# 개선된:
"Evaluate signal strength on scale 0.50-1.00
- 0.50-0.60: Weak signals with minor red flags
- 0.60-0.75: Moderate signals, some uncertainty
- 0.75-0.85: Strong signals, high confidence
- 0.85-1.00: Exceptional signals, rare occurrence"
```

**기대 결과:**
```
mean_score: 0.68-0.72 (하향)
std: 0.12-0.15 (상향)
DI: 0.8+ (개선)
SENT avg > REJECTED avg 명확 (판별력 개선)
```

### 예제 2: 과도하게 보수적인 프롬프트

**진단:**
```
mean_score: 0.58, std: 0.14
신호가 너무 적음 (하루 50개 미만)
```

**원인:** 프롬프트 평가 기준이 너무 엄격

**개선:**
```
# 프롬프트 수정
# 이전:
"Only score 0.75+ if all conditions met perfectly"

# 개선된:
"Score 0.60+ if most key conditions are met
- Include partially aligned signals
- Lower bar for entry opportunities"
```

**기대 결과:**
```
mean_score: 0.65-0.70 (상향)
신호 개수: 2배 이상 증가
std: 0.10-0.12 (안정화)
```

### 예제 3: 특정 시간대 편향

**진단:**
```
09:00-10:00: mean=0.75, signals=120
11:00-12:00: mean=0.62, signals=50
```

**원인:** 프롬프트가 시간 영향을 받음 (예: 개장 직후 신호 품질 높음)

**개선:**
```
# 프롬프트 수정
# 이전:
"Consider market open momentum"

# 개선된:
"Evaluate signal quality independent of time of day
- Same criteria apply 09:00-16:00
- Do not bias toward opening hour"
```

---

## 📈 효과 측정 메트릭

### 메인 지표

| 지표 | 계산식 | 목표 | 해석 |
|------|--------|------|------|
| **판별력 지수** | (SENT_avg - REJECTED_avg) / (SENT_std + REJECTED_std) | >0.8 | AI 신호 유효성 |
| **신호 분포** | mean ± std | 0.65-0.72 ± 0.09-0.12 | 프롬프트 특성 |
| **거절 이유 균형** | 최대/최소 비율 | <2.0 | 필터 불균형 |
| **종목 편향** | max_avg - min_avg | <0.05 | 프롬프트 중립성 |
| **시간 편향** | 시간대별 std | <0.03 | 타이밍 중립성 |

---

## 📋 튜닝 체크리스트

```
[ ] 데이터 충분한가? (최소 500 신호)
[ ] ai_score 분포를 확인했는가?
[ ] SENT vs REJECTED 점수를 비교했는가?
[ ] 거절 이유별 점수를 분석했는가?
[ ] 종목/시간 편향을 체크했는가?
[ ] 프롬프트 vs 필터 문제를 구분했는가?
[ ] 변경 사항을 params_version_id에 기록했는가?
[ ] 이전 버전과 비교했는가?
[ ] 예상한 개선이 나타났는가?
```

---

## 🚀 완전한 분석 쿼리 모음

### 원라이너: 프롬프트 건강도 진단

```sql
-- 핵심 메트릭 한눈에
SELECT 
    'Signal Distribution' as metric,
    ROUND(AVG(ai_score), 4) as mean,
    ROUND(STDDEV(ai_score), 4) as std
FROM execution_log WHERE module='APP64'
UNION ALL
SELECT 
    'Discrimination Index',
    ROUND((SELECT AVG(ai_score) FROM execution_log WHERE module='APP32' AND decision='SENT') - 
          (SELECT AVG(ai_score) FROM execution_log WHERE module='APP32' AND decision='REJECTED'), 4),
    ROUND(((SELECT AVG(ai_score) FROM execution_log WHERE module='APP32' AND decision='SENT') - 
           (SELECT AVG(ai_score) FROM execution_log WHERE module='APP32' AND decision='REJECTED')) /
          ((SELECT STDDEV(ai_score) FROM execution_log WHERE module='APP32' AND decision='SENT') +
           (SELECT STDDEV(ai_score) FROM execution_log WHERE module='APP32' AND decision='REJECTED')), 4)
UNION ALL
SELECT 
    'Execution Rate %',
    ROUND(100.0 * COUNT(CASE WHEN decision='SENT' THEN 1 END) / COUNT(*), 2),
    0
FROM execution_log WHERE module='APP32';
```

### 상세 분석: 어디가 문제인가?

```sql
-- 거절 이유별 상세 분석
WITH rejection_analysis AS (
    SELECT 
        rejection_reason,
        COUNT(*) as count,
        ROUND(AVG(ai_score), 4) as avg_score,
        ROUND(MIN(ai_score), 4) as min_score,
        ROUND(MAX(ai_score), 4) as max_score,
        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM execution_log WHERE decision='REJECTED'), 2) as pct
    FROM execution_log 
    WHERE decision='REJECTED'
    GROUP BY rejection_reason
)
SELECT 
    rejection_reason,
    count,
    avg_score,
    CASE 
        WHEN avg_score > 0.75 THEN '⚠️ High-quality signals rejected (filter problem)'
        WHEN avg_score < 0.65 THEN '✓ Low-quality signals rejected (filter working)'
        ELSE '→ Medium quality (normal)'
    END as diagnosis,
    pct
FROM rejection_analysis
ORDER BY count DESC;
```

---

## 결론

**프롬프트 개선의 핵심 원칙:**

1. **측정** – 로그 데이터로 현상 파악
2. **진단** – 프롬프트 vs 필터 문제 구분
3. **가설** – 어떤 변경이 개선할 것인가?
4. **검증** – 버전별 비교로 효과 측정
5. **반복** – 지속적인 A/B 테스트

모든 데이터는 영구 보관되므로, 언제든 이전 버전과의 비교 분석 가능하며, 효과 검증 후 더 나은 버전만 선택할 수 있습니다.
