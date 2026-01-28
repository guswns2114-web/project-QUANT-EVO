# AI Trading Prompt Evaluation - Complete Solution

## 🎯 프로젝트 완성도

이 프로젝트는 **로그 데이터만을 사용한 AI 거래 프롬프트 평가 및 개선 시스템**을 제공합니다.

### 핵심 특징

✅ **로그 기반 평가** – 실행 로그만으로 프롬프트 품질 측정  
✅ **자동 진단** – 프롬프트 vs 필터 문제 자동 구분  
✅ **데이터 보관** – 모든 데이터 영구 보관, 버전 비교 가능  
✅ **Dry-run 전용** – 실제 자금 사용 없음, 완전히 안전  
✅ **간단한 도구** – 복잡한 ML/RL 불필요, 기본 통계만 사용  

---

## 📦 제공 파일

### 1. 분석 스크립트

| 파일 | 기능 | 사용 시점 |
|------|------|----------|
| `scripts/analyze_signals.py` | 기본 신호 통계 | 초기 분석 |
| `scripts/evaluate_prompt.py` | 프롬프트 품질 진단 (자동) | 데이터 충분 시 |

### 2. 설명 문서 (5종)

| 파일 | 내용 | 대상 |
|------|------|------|
| `LOGGING_SCHEMA.md` | 로그 데이터 구조 | 분석가 |
| `SIGNAL_ANALYSIS_GUIDE.md` | 기본 신호 분석 해석 | 초보자 |
| `PROMPT_EVALUATION_FRAMEWORK.md` | 프롬프트 평가 방법론 (상세) | 전문가 |
| `PROMPT_TUNING_WORKFLOW.md` | 5단계 개선 프로세스 | 실무자 |
| `PROMPT_SYSTEM_README.md` | 통합 가이드 | 모두 |

---

## 🚀 빠른 시작 (5분)

```bash
# 1. 신호 데이터 수집 (1-2일 필요)
python app64/signal_engine.py
python app32/main.py

# 2. 프롬프트 진단 (자동)
python scripts/evaluate_prompt.py

# 3. 결과 해석 & 개선 (가이드 참고)
# PROMPT_TUNING_WORKFLOW.md 참고
```

---

## 📊 분석 방법

### 방법 1: 자동 진단 (권장)

```bash
python scripts/evaluate_prompt.py
```

**출력:**
```
📊 1. Signal Distribution
  Mean score: 0.72 ✅
  Std dev: 0.10 ✅
  
🎯 2. Discrimination Index
  DI: 1.18 ✅ (좋은 판별력)
  
🚫 3. Rejection Reasons
  TTL_EXPIRED avg: 0.758 ⚠️ (높음)
  
🔍 6. Automatic Diagnosis
  ❌ COOLDOWN avg 너무 높음
     → 필터 설정 검토 필요
```

### 방법 2: 기본 통계

```bash
python scripts/analyze_signals.py
```

### 방법 3: 직접 SQL 쿼리

```sql
-- 판별력 지수 계산
SELECT 
    ROUND(
        (SELECT AVG(ai_score) FROM execution_log 
         WHERE module='APP32' AND decision='SENT')
        -
        (SELECT AVG(ai_score) FROM execution_log 
         WHERE module='APP32' AND decision='REJECTED'),
        4
    ) as discrimination_gap;
```

---

## 🎯 프롬프트 평가 5가지 지표

### 1. Signal Distribution (신호 분포)
```
측정: mean, std, min, max
진단:
  ✅ mean 0.65-0.75, std 0.08-0.12
  ⚠️  mean > 0.80 (공격적)
  ⚠️  std < 0.05 (단조)
```

### 2. Discrimination Index (판별력)
```
계산: (SENT_mean - REJECTED_mean) / (SENT_std + REJECTED_std)
진단:
  ✅ DI > 1.0 (좋음)
  ⚠️  DI 0.5-1.0 (중간)
  ❌ DI < 0.5 (나쁨)
```

### 3. Rejection Reason Analysis (거절 이유)
```
측정: 각 이유별 평균 점수
진단:
  ✅ 낮은 점수 신호 거절 (정상)
  ⚠️  높은 점수 신호 거절 (필터 과도)
```

### 4. Symbol Bias (종목 편향)
```
계산: max_avg - min_avg
진단:
  ✅ < 0.03 (중립)
  ⚠️  0.03-0.05 (약한 편향)
  ❌ > 0.05 (심한 편향)
```

### 5. Time Bias (시간 편향)
```
계산: 시간대별 평균 점수 편차
진단:
  ✅ < 0.03 (시간 중립)
  ⚠️  > 0.05 (시간 편향)
```

---

## 🔍 프롬프트 vs 필터 문제 구분

### 프롬프트 문제 신호
```
✗ mean > 0.80 or < 0.60
✗ std < 0.05 (평가 기준 불명확)
✗ DI < 0.5 (판별 불가)
✗ 시간/종목 편향
```
**해결:** signal_engine.py 프롬프트 수정

### 필터 문제 신호
```
✓ mean 정상, DI > 1.0
✗ TTL_EXPIRED avg > 0.75 (좋은 신호 손실)
✗ COOLDOWN avg > 0.75 (좋은 신호 차단)
```
**해결:** strategy_params.json 설정 조정

---

## 📈 개선 프로세스 (5단계)

### Step 1: 데이터 수집
```
최소 500개 신호 필요
→ 충분한 통계 데이터 확보
```

### Step 2: 진단
```bash
python scripts/evaluate_prompt.py
→ 프롬프트/필터 문제 파악
```

### Step 3: 근본 원인 분석
```
프롬프트 문제?  → signal_engine.py 검토
필터 문제?      → strategy_params.json 검토
```

### Step 4: 개선
```python
# 옵션 A: 프롬프트 (예)
"Score range: 0.50-1.00 (기존: 0.70-0.90)"

# 옵션 B: 필터 (예)
"signal_ttl_ms": 10000  # 5000 → 10000
"cooldown_sec": 15      # 30 → 15
```

### Step 5: 검증
```bash
python scripts/evaluate_prompt.py
→ 이전 버전과 비교
→ 개선 여부 확인
```

---

## 💡 실제 튜닝 사례

### Case: 판별력 없는 프롬프트

**진단:**
```
Mean: 0.82, Std: 0.03, DI: 0.4 ❌
```

**문제:** 거의 모든 신호를 높게 평가

**개선:**
```python
# 프롬프트 명확화
"0.50-0.60: Weak signals (낮은 신뢰)
 0.60-0.75: Moderate signals (중간 신뢰)
 0.75-0.85: Strong signals (높은 신뢰)
 0.85-1.00: Exceptional (매우 높음)"
```

**결과:**
```
Mean: 0.71 ✅, Std: 0.11 ✅, DI: 1.05 ✅
→ 판별력 2.6배 향상!
```

---

## 📊 데이터 구조

### execution_log 테이블
```sql
CREATE TABLE execution_log (
    id INTEGER PRIMARY KEY,
    ts TEXT,                        -- 타임스탬프
    module TEXT,                    -- "APP32" / "APP64"
    symbol TEXT,                    -- 종목 코드
    action TEXT,                    -- "BUY" / "SELL"
    decision TEXT,                  -- "SENT" / "REJECTED" / "CREATED"
    rejection_reason TEXT,          -- TTL_EXPIRED / COOLDOWN / ...
    ai_score REAL,                  -- 신호 점수 (0.0-1.0)
    params_version_id TEXT,         -- 파라미터 버전
    context TEXT                    -- JSON 추가 정보
);
```

### 핵심 거절 이유
```
TTL_EXPIRED       → 신호 유효시간 초과
DAILY_LIMIT       → 일일 진입 한도 도달
COOLDOWN          → 마지막 거래 후 쿨다운 대기 중
ONE_POSITION      → 포지션 중복 제한 위반
```

---

## 🎓 학습 경로

### Beginner
1. `PROMPT_SYSTEM_README.md` – 전체 개요
2. `scripts/evaluate_prompt.py` – 자동 진단 실행
3. `SIGNAL_ANALYSIS_GUIDE.md` – 기본 지표 이해

### Intermediate
4. `PROMPT_EVALUATION_FRAMEWORK.md` – 상세 방법론
5. `PROMPT_TUNING_WORKFLOW.md` – 실제 프로세스
6. SQL 쿼리로 심화 분석

### Advanced
7. 프롬프트 직접 수정 & A/B 테스트
8. 버전별 성능 비교 & 최적화
9. 커스텀 분석 쿼리 작성

---

## ✨ 주요 장점

| 특징 | 이점 |
|------|------|
| **로그 기반** | 복잡한 계산 불필요, 간단하고 명확 |
| **자동 진단** | 프롬프트/필터 문제 자동 구분 |
| **데이터 보관** | 버전별 비교 분석 가능 |
| **Dry-run** | 위험 없이 안전한 실험 |
| **추적 가능** | 완전한 감시 추적(audit trail) |
| **확장 가능** | SQL로 커스텀 분석 가능 |

---

## 🔐 데이터 안정성

**중요 원칙:**
```
✅ 모든 로그 영구 보관
✅ 데이터 삭제 금지
✅ 버전별 분리 저장
✅ 언제든 과거 분석 재현 가능
✅ 롤백 가능 (이전 버전 복구)
```

**예:**
```sql
-- 이전 버전으로 되돌아가기
SELECT * FROM execution_log 
WHERE params_version_id = '2026-01-28_01'
→ 이전 버전의 모든 데이터 접근 가능
```

---

## 📋 체크리스트

### 초기 설정
```
[ ] app64/signal_engine.py 실행 확인
[ ] app32/main.py 실행 확인
[ ] 500+ 신호 생성 대기
```

### 분석
```
[ ] python scripts/evaluate_prompt.py 실행
[ ] 진단 결과 검토
[ ] 프롬프트 vs 필터 구분
```

### 개선
```
[ ] strategy_params.json version 증가
[ ] 변경 사항 기록
[ ] 새 버전 재실행 & 데이터 수집
[ ] 개선 효과 검증
```

---

## 🚀 핵심 명령어

```bash
# 신호 생성
python app64/signal_engine.py

# 거래 실행
python app32/main.py

# 자동 진단 (★ 가장 중요)
python scripts/evaluate_prompt.py

# 기본 통계
python scripts/analyze_signals.py

# SQL 직접 쿼리 (심화)
sqlite3 shared/data/trading.db "SELECT ..."
```

---

## 📞 주요 문서

```
시작 → PROMPT_SYSTEM_README.md
     ↓
기본 이해 → SIGNAL_ANALYSIS_GUIDE.md
     ↓
심화 학습 → PROMPT_EVALUATION_FRAMEWORK.md
     ↓
실제 적용 → PROMPT_TUNING_WORKFLOW.md
     ↓
기술 상세 → LOGGING_SCHEMA.md
```

---

## 🎯 결론

**이 시스템은:**

1. **로그 데이터만으로** AI 프롬프트 품질 측정
2. **자동 진단**으로 개선 방향 제시
3. **안전한 환경**에서 다양한 실험
4. **데이터 기반**으로 객관적 의사결정
5. **완전히 추적 가능**한 모든 결정 기록

**시작하기:**
```bash
python scripts/evaluate_prompt.py
```

모든 것이 로그에 기록되고, 모든 데이터는 영구 보관되므로,
**언제든 안전하게 개선을 시도**할 수 있습니다!

---

**마지막 조언:** 한 번에 하나씩만 변경하고, 충분한 데이터 수집 후에 효과를 측정하세요.
