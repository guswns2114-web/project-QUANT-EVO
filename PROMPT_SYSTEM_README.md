# AI Prompt Evaluation & Tuning System

## 📊 시스템 구성

QUANT-EVO 프로젝트의 **AI 거래 프롬프트 평가 및 개선 시스템**입니다.

```
┌─────────────────┐
│  APP64          │  신호 생성 (AI 프롬프트)
│  signal_engine  │
└────────┬────────┘
         │ ai_score
         ▼
┌─────────────────────────────────────┐
│  Database: execution_log table      │  모든 결정 기록
└──────┬──────────────────────────────┘
       │
       ├──► analyze_signals.py        → 기본 통계
       │
       ├──► evaluate_prompt.py        → 프롬프트 품질 진단
       │
       └──► SQL 쿼리                 → 심화 분석
       
┌──────────────────────┐
│  APP32               │  거래 실행 (필터 규칙)
│  main.py             │
└──────────────────────┘
```

---

## 📁 핵심 파일

### 1. 실행 엔진

| 파일 | 역할 | 기술 |
|------|------|------|
| `app64/signal_engine.py` | AI 신호 생성 | Python, 프롬프트 기반 |
| `app32/main.py` | 거래 실행 + 필터 | Python, 규칙 기반 |
| `shared/data/trading.db` | 로그 저장소 | SQLite |

### 2. 분석 도구

| 파일 | 목적 | 사용 시점 |
|------|------|----------|
| `scripts/analyze_signals.py` | 기본 신호 통계 | 실행 직후 |
| `scripts/evaluate_prompt.py` | 프롬프트 품질 진단 | 최소 500 신호 후 |

### 3. 설정 & 가이드

| 파일 | 내용 |
|------|------|
| `shared/config/strategy_params.json` | 거래 규칙 및 필터 |
| `LOGGING_SCHEMA.md` | 로그 데이터 구조 |
| `SIGNAL_ANALYSIS_GUIDE.md` | 기본 신호 분석 |
| `PROMPT_EVALUATION_FRAMEWORK.md` | 프롬프트 평가 방법론 |
| `PROMPT_TUNING_WORKFLOW.md` | 프롬프트 개선 프로세스 |

---

## 🎯 빠른 시작

### 1단계: 데이터 수집 (1-2일)

```bash
# Terminal 1: APP64 (신호 생성)
cd c:\project\QUANT-EVO
python app64/signal_engine.py

# Terminal 2: APP32 (거래 실행)
cd c:\project\QUANT-EVO
python app32/main.py
```

**목표:** 최소 500개 신호 생성

### 2단계: 기본 분석

```bash
python scripts/analyze_signals.py
```

**산출:**
- 총 신호 개수
- 승인/거절 비율
- 거절 이유 분포
- AI 점수 비교
- 종목별/버전별 통계

### 3단계: 프롬프트 진단

```bash
python scripts/evaluate_prompt.py
```

**산출:**
- 신호 분포 분석 (mean, std, range)
- 판별력 지수 (AI 신호 유효성)
- 거절 이유별 신호 품질
- 종목/시간 편향 감지
- **자동 진단**: 프롬프트 문제 식별

### 4단계: 개선 (필요시)

```json
// strategy_params.json
{
  "version": "2026-01-28_02",  // ← 버전 증가
  "signal": {
    "signal_ttl_ms": 10000     // ← 조정 (예)
  },
  "execution": {
    "cooldown_sec": 15         // ← 조정 (예)
  }
}
```

### 5단계: 검증

다시 `evaluate_prompt.py` 실행 → 이전 버전과 비교

---

## 📊 분석 지표 설명

### Signal Distribution (신호 분포)
```
Mean score: 0.72        ← 평균 점수 (이상적: 0.65-0.75)
Std dev:    0.10        ← 표준편차 (이상적: 0.08-0.12)
Score range: 0.50~0.95  ← 점수 범위
```

**해석:**
- Mean 높음 (>0.80) → 프롬프트 공격적 ⚠️
- Std 낮음 (<0.05) → 신호 단조, 평가 기준 불명확 ⚠️

### Discrimination Index (판별력 지수)
```
DI = (SENT_mean - REJECTED_mean) / (SENT_std + REJECTED_std)

DI > 1.0:  ✅ 좋은 판별력 (AI 신호 유효)
DI 0.5-1.0: ⚠️ 중간 판별력
DI < 0.5:  ❌ 나쁜 판별력 (프롬프트 개선 필요)
```

### Rejection Reason Distribution (거절 이유)
```
TTL_EXPIRED:  87 (20%) avg=0.758
DAILY_LIMIT:  186 (43%) avg=0.742
COOLDOWN:     147 (34%) avg=0.751
ONE_POSITION: 14 (3%)  avg=0.763
```

**해석:**
- 특정 이유의 avg > 0.75 → 좋은 신호를 차단 ⚠️
  - 필터 문제, 프롬프트 아님

### Symbol Bias (종목 편향)
```
Bias Index = MAX(symbol_avg) - MIN(symbol_avg)

< 0.03:  ✅ 중립적 (종목 선호 없음)
0.03-0.05: ⚠️ 약한 편향
> 0.05:  ❌ 심한 편향 (프롬프트 개선 필요)
```

---

## 🔍 프롬프트 vs 필터 문제 구분

### 프롬프트 문제 신호
```
✗ Mean score > 0.80 (공격적) 또는 < 0.60 (보수적)
✗ Std < 0.05 (단조, 평가 기준 불명확)
✗ Discrimination Index < 0.5 (판별 안 됨)
✗ 특정 시간/종목 편향 큼
```

**개선:** `app64/signal_engine.py` 프롬프트 수정

### 필터 문제 신호
```
✓ Mean score 정상 (0.65-0.75)
✓ DI > 1.0 (판별력 좋음)
✗ 특정 거절 이유의 avg > 0.75
  → 좋은 신호가 필터에 차단됨
```

**개선:** `strategy_params.json` 필터 설정 조정

---

## 📈 개선 사례

### Case 1: 공격적 프롬프트 개선

**문제:**
```
Mean score: 0.82
Std dev: 0.03
DI: 0.4 ← 판별력 없음
```

**원인:** 프롬프트가 거의 모든 신호를 높게 평가

**개선:**
```python
# 이전 프롬프트
"Score range: 0.70-0.90"

# 개선된 프롬프트
"Score range: 0.50-1.00
- 0.50-0.60: Weak signals
- 0.60-0.75: Moderate signals
- 0.75-0.85: Strong signals
- 0.85-1.00: Exceptional signals"
```

**결과:**
```
Mean score: 0.71 ✅ (개선)
Std dev: 0.11 ✅ (개선)
DI: 1.05 ✅ (대폭 개선)
```

### Case 2: 필터 과도 개선

**문제:**
```
TTL_EXPIRED: 30%, avg=0.81 ← 좋은 신호 손실
COOLDOWN: 40%, avg=0.78
```

**원인:** signal_ttl_ms 짧음, cooldown_sec 김

**개선:**
```json
// strategy_params.json
{
  "signal": {
    "signal_ttl_ms": 5000 → 10000
  },
  "execution": {
    "cooldown_sec": 30 → 15
  }
}
```

**결과:**
```
TTL_EXPIRED: 8% ✅
COOLDOWN: 25% ✅
Execution rate: 60% → 75% ✅
```

---

## 🗂️ 데이터 영구 보관 정책

**중요:** 모든 로그 데이터는 **완전히 보관**됩니다.

```sql
-- 데이터 절대 삭제 안 함
-- 버전별로 분리되어 저장됨

SELECT params_version_id, COUNT(*) 
FROM execution_log 
GROUP BY params_version_id
ORDER BY params_version_id DESC;

-- 결과:
-- 2026-01-28_02: 650 records
-- 2026-01-28_01: 1200 records
-- ← 언제든 비교 분석 가능
```

**장점:**
- 이전 버전으로 돌아갈 수 있음
- 장기 성능 트렌드 분석 가능
- 완전한 감시 추적 (audit trail)

---

## 📚 상세 가이드

| 문서 | 목적 |
|------|------|
| `LOGGING_SCHEMA.md` | 📋 로그 데이터 구조 이해 |
| `SIGNAL_ANALYSIS_GUIDE.md` | 📊 기본 신호 분석 해석 |
| `PROMPT_EVALUATION_FRAMEWORK.md` | 🎯 프롬프트 평가 방법론 (상세) |
| `PROMPT_TUNING_WORKFLOW.md` | 🚀 프롬프트 개선 프로세스 (단계별) |

---

## 🛠️ Advanced Usage

### SQL 직접 쿼리 (심화 분석)

```sql
-- 판별력 지수 계산
SELECT 
    (SELECT AVG(ai_score) FROM execution_log WHERE module='APP32' AND decision='SENT') -
    (SELECT AVG(ai_score) FROM execution_log WHERE module='APP32' AND decision='REJECTED') 
    as score_gap;

-- 버전별 거절 이유 변화 추적
SELECT params_version_id, rejection_reason, COUNT(*) 
FROM execution_log 
WHERE decision='REJECTED'
GROUP BY params_version_id, rejection_reason
ORDER BY params_version_id DESC;

-- 시간대별 신호 패턴
SELECT strftime('%H', ts) as hour, COUNT(*), AVG(ai_score)
FROM execution_log WHERE module='APP32'
GROUP BY hour ORDER BY hour;
```

---

## ✅ 체크리스트

### 초기 설정
```
[ ] APP64, APP32 실행 확인
[ ] 신호 생성 대기 (500+ signals)
[ ] evaluate_prompt.py 실행 가능 확인
```

### 분석
```
[ ] analyze_signals.py 로 기본 통계 확인
[ ] evaluate_prompt.py 로 프롬프트 진단
[ ] 프롬프트 vs 필터 문제 구분
```

### 개선
```
[ ] strategy_params.json의 version 증가
[ ] 변경 사항 주석 기록
[ ] 새 버전에서 500+ 신호 수집
[ ] 이전 버전과 비교
```

---

## 📞 FAQ

### Q: 실제 거래는 되나요?
**A:** 아니요. Dry-run 전용입니다. 실제 자금 사용 안 함.

### Q: 강화학습이 필요한가요?
**A:** 아니요. 간단한 통계 분석으로 충분합니다.

### Q: 데이터 손실이 있을까요?
**A:** 아니요. 모든 데이터는 영구 보관됩니다.

### Q: 얼마나 자주 분석해야 하나요?
**A:** 버전별로 최소 500 신호 후 분석 권장 (1-2일).

### Q: 과거 버전과 비교할 수 있나요?
**A:** 네, SQL로 언제든 버전별 비교 분석 가능합니다.

---

## 🎓 학습 순서

1. **기본 개념** → `LOGGING_SCHEMA.md`
2. **기본 분석** → `SIGNAL_ANALYSIS_GUIDE.md`
3. **프롬프트 이해** → `PROMPT_EVALUATION_FRAMEWORK.md`
4. **실습 프로세스** → `PROMPT_TUNING_WORKFLOW.md`
5. **심화 분석** → SQL 직접 쿼리

---

## 🚀 핵심 원칙

1. **데이터 기반**: 로그 데이터로만 판단
2. **과학적**: 정량적 지표로 평가
3. **안전함**: Dry-run이므로 위험 없음
4. **추적 가능**: 모든 결정과 데이터 기록
5. **반복적**: 지속적인 개선 루프

---

## 💾 저장된 모든 정보

```
project/
├── app64/
│   ├── signal_engine.py      (AI 신호 생성)
│   └── db.py                 (DB 연결)
├── app32/
│   ├── main.py               (거래 실행)
│   └── db.py                 (DB 연결)
├── scripts/
│   ├── analyze_signals.py    (기본 분석)
│   └── evaluate_prompt.py    (프롬프트 진단) ← ★ 가장 중요
├── shared/
│   ├── config/
│   │   └── strategy_params.json  (필터 설정)
│   └── data/
│       └── trading.db        (로그 저장소)
└── docs/
    ├── LOGGING_SCHEMA.md     (로그 구조)
    ├── SIGNAL_ANALYSIS_GUIDE.md
    ├── PROMPT_EVALUATION_FRAMEWORK.md
    └── PROMPT_TUNING_WORKFLOW.md
```

---

**시작하기:** `python scripts/evaluate_prompt.py`를 실행하세요!
