#!/usr/bin/env python3
"""
QUANT-EVO Prompt Quality Auditor

역할: 프롬프트 구조적 문제를 찾는 감사자
목표: 수익 예측이 아니라, 신호 생성 프롬프트의 문제 식별

입력: JSONL 로그 + strategy_params.json
출력: 문제 분석 + 조정 제안 시나리오

제약:
- 실계좌/손익 예측 금지 ✅
- 프롬프트 자동 수정 금지 ✅
- 조정 제안만 시나리오로 제시 ✅
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from statistics import mean

def load_params():
    """현재 strategy_params.json 로드"""
    config_path = Path(__file__).resolve().parents[1] / "shared" / "config" / "strategy_params.json"
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_jsonl_events(logs_dir):
    """JSON Lines 로그 로드"""
    logs_path = Path(logs_dir)
    events = []
    
    for jsonl_file in sorted(logs_path.glob("*.jsonl")):
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except:
                        pass
    
    return events

def analyze_prompt_structure(params, events):
    """프롬프트 구조 분석 - 신호 생성이 언제/왜 실패하는지"""
    
    # === Step 1: 신호 생성 빈도 분석 ===
    signal_created = [e for e in events if e.get('event_type') == 'SIGNAL_CREATED']
    exec_sent = [e for e in events if e.get('event_type') == 'EXEC_SENT']
    exec_rejected = [e for e in events if e.get('event_type') == 'EXEC_REJECTED']
    
    if not signal_created:
        return None
    
    # 시간 계산
    try:
        from datetime import datetime
        start = datetime.fromisoformat(signal_created[0]['ts'].replace('Z', '+00:00'))
        end = datetime.fromisoformat(signal_created[-1]['ts'].replace('Z', '+00:00'))
        elapsed_minutes = (end - start).total_seconds() / 60
    except:
        elapsed_minutes = 1
    
    intents_per_minute = len(signal_created) / elapsed_minutes if elapsed_minutes > 0 else 0
    
    # === Step 2: 신호 특성 분석 ===
    ai_scores = [e.get('ai_score', 0) for e in signal_created]
    buy_signals = sum(1 for e in signal_created if e.get('action') == 'BUY')
    
    # === Step 3: 거절 이유 분석 ===
    rejection_reasons = defaultdict(int)
    for e in exec_rejected:
        reason = e.get('rejection_reason', 'UNKNOWN')
        rejection_reasons[reason] += 1
    
    # TTL 거절 비율
    ttl_rejects = rejection_reasons.get('TTL_EXPIRED', 0)
    ttl_reject_ratio = ttl_rejects / len(exec_rejected) * 100 if exec_rejected else 0
    
    # COOLDOWN 거절 비율
    cooldown_rejects = rejection_reasons.get('COOLDOWN', 0)
    cooldown_reject_ratio = cooldown_rejects / len(exec_rejected) * 100 if exec_rejected else 0
    
    return {
        'signal_created_count': len(signal_created),
        'exec_sent_count': len(exec_sent),
        'exec_rejected_count': len(exec_rejected),
        'intents_per_minute': intents_per_minute,
        'elapsed_minutes': elapsed_minutes,
        'ai_scores': ai_scores,
        'ai_score_mean': mean(ai_scores) if ai_scores else 0,
        'buy_ratio': buy_signals / len(signal_created) if signal_created else 0,
        'sent_rate': len(exec_sent) / len(signal_created) * 100 if signal_created else 0,
        'rejection_reasons': dict(rejection_reasons),
        'ttl_reject_ratio': ttl_reject_ratio,
        'cooldown_reject_ratio': cooldown_reject_ratio,
    }

def diagnose_low_intents_per_minute(params, analysis):
    """intents/min이 낮은 원인 진단 - 프롬프트 구조 관점"""
    
    intents_pm = analysis['intents_per_minute']
    
    # 진단: 어디서 신호 생성이 제한되는가?
    
    diagnostics = {
        'problem_severity': 'CRITICAL' if intents_pm < 2 else 'HIGH' if intents_pm < 5 else 'MEDIUM',
        'current_rate': intents_pm,
        'target_rate': 10,  # 이상적인 범위의 중간값
        'gap': 10 - intents_pm,
    }
    
    # === Hypothesis 1: ai_score_cut이 너무 높은가? ===
    ai_score_cut = params['signal']['ai_score_cut']
    mean_score = analysis['ai_score_mean']
    
    hypothesis_1 = {
        'name': '신호 신뢰도 기준 (ai_score_cut) 과도히 높음',
        'current_value': ai_score_cut,
        'analysis': {
            'ai_score_cut': ai_score_cut,
            'actual_mean_score': mean_score,
            'score_variance': max(analysis['ai_scores']) - min(analysis['ai_scores']) if analysis['ai_scores'] else 0,
        },
        'impact': 'HIGH' if ai_score_cut > mean_score + 0.05 else 'MEDIUM' if ai_score_cut > mean_score else 'LOW',
        'reasoning': f"현재 생성되는 신호의 평균 점수({mean_score:.3f})가 기준({ai_score_cut})보다 낮음. "
                    f"기준이 높으면 신호 생성 자체가 제한됨.",
    }
    
    # === Hypothesis 2: vol_spike_min 또는 book_ratio_min 조건이 과도히 엄격한가? ===
    vol_spike_min = params['signal'].get('vol_spike_min', 2.0)
    book_ratio_min = params['signal'].get('book_ratio_min', 1.30)
    
    hypothesis_2 = {
        'name': '시장 조건 필터 (volatility/book ratio) 과도히 엄격함',
        'current_values': {
            'vol_spike_min': vol_spike_min,
            'book_ratio_min': book_ratio_min,
        },
        'impact': 'MEDIUM' if vol_spike_min > 2.5 or book_ratio_min > 1.5 else 'LOW',
        'reasoning': f"volatility spike {vol_spike_min}배, book ratio {book_ratio_min}배 조건. "
                    f"이 조건들은 특정 시장 상황에서만 만족되므로, 신호 기회를 크게 제한할 수 있음.",
    }
    
    # === Hypothesis 3: 필터는 충분하지만 프롬프트 자체가 보수적인가? ===
    hypothesis_3 = {
        'name': '프롬프트 로직 자체가 신호 생성을 제한함',
        'analysis': {
            'price_above_vwap_required': params['signal'].get('require_price_above_vwap', True),
            'max_symbols': params['universe']['max_symbols'],
            'window_sec': params['signal'].get('window_sec', 30),
            'buy_ratio_min': params['signal'].get('buy_ratio_min', 0.65),
        },
        'impact': 'MEDIUM',
        'reasoning': f"VWAP 이상 가격 요구, 최대 {params['universe']['max_symbols']}개 심볼 등의 조건. "
                    f"이들이 복합적으로 신호 기회를 줄임.",
    }
    
    return hypothesis_1, hypothesis_2, hypothesis_3

def propose_adjustment_scenarios(params, analysis, h1, h2, h3):
    """조정 제안 시나리오 (실제 수정 아님, 제안만)"""
    
    scenarios = []
    
    # === Scenario A: 신호 신뢰도 기준(ai_score_cut) 완화 ===
    scenario_a = {
        'name': 'Scenario A: ai_score_cut 완화',
        'rationale': '신호 신뢰도 기준을 낮춰서 신호 생성 빈도 증가',
        'current_setting': {
            'ai_score_cut': params['signal']['ai_score_cut'],
        },
        'proposed_adjustments': [
            {
                'parameter': 'ai_score_cut',
                'current_value': params['signal']['ai_score_cut'],
                'proposed_value': params['signal']['ai_score_cut'] - 0.05,
                'rationale': f"기준을 {params['signal']['ai_score_cut']}에서 {params['signal']['ai_score_cut'] - 0.05}로 완화",
            }
        ],
        'expected_effects': {
            'intents_per_minute': f"예상 증가: {analysis['intents_per_minute']:.2f} → {analysis['intents_per_minute'] * 1.5:.2f}",
            'risk': '낮은 신뢰도 신호도 생성 가능 (거절 필터 의존)',
            'ai_score_impact': '평균 신호 신뢰도 약간 감소',
        },
        'warning': '신호는 많아지지만, 필터링이 더 중요해짐',
    }
    
    # === Scenario B: 시장 조건 필터 완화 ===
    scenario_b = {
        'name': 'Scenario B: 시장 조건 필터(vol_spike, book_ratio) 완화',
        'rationale': '시장 변동성/호가 조건을 완화하여 신호 기회 확대',
        'current_settings': {
            'vol_spike_min': params['signal'].get('vol_spike_min', 2.0),
            'book_ratio_min': params['signal'].get('book_ratio_min', 1.30),
        },
        'proposed_adjustments': [
            {
                'parameter': 'vol_spike_min',
                'current_value': params['signal'].get('vol_spike_min', 2.0),
                'proposed_value': params['signal'].get('vol_spike_min', 2.0) - 0.3,
                'rationale': f"변동성 스파이크 기준 {params['signal'].get('vol_spike_min', 2.0)}배에서 {params['signal'].get('vol_spike_min', 2.0) - 0.3}배로 완화",
            },
            {
                'parameter': 'book_ratio_min',
                'current_value': params['signal'].get('book_ratio_min', 1.30),
                'proposed_value': params['signal'].get('book_ratio_min', 1.30) - 0.1,
                'rationale': f"호가 레시오 기준 {params['signal'].get('book_ratio_min', 1.30)}배에서 {params['signal'].get('book_ratio_min', 1.30) - 0.1}배로 완화",
            }
        ],
        'expected_effects': {
            'intents_per_minute': f"예상 증가: {analysis['intents_per_minute']:.2f} → {analysis['intents_per_minute'] * 2.0:.2f}",
            'risk': '더 많은 신호가 생성되지만, 시장 조건이 좋지 않을 때도 신호 발생',
            'filter_impact': 'COOLDOWN/TTL 거절 비율 증가 가능',
        },
        'warning': '완화 폭이 크면 노이즈 신호 증가 가능',
    }
    
    # === Scenario C: 보수적 접근 - 1단계 완화 ===
    scenario_c = {
        'name': 'Scenario C: 1단계 점진적 완화 (Hybrid)',
        'rationale': '과도한 변화 피하고, ai_score_cut만 조금 완화',
        'current_settings': {
            'ai_score_cut': params['signal']['ai_score_cut'],
        },
        'proposed_adjustments': [
            {
                'parameter': 'ai_score_cut',
                'current_value': params['signal']['ai_score_cut'],
                'proposed_value': params['signal']['ai_score_cut'] - 0.03,
                'rationale': f"기준을 {params['signal']['ai_score_cut']}에서 {params['signal']['ai_score_cut'] - 0.03}로 보수적으로 완화",
            }
        ],
        'expected_effects': {
            'intents_per_minute': f"예상 증가: {analysis['intents_per_minute']:.2f} → {analysis['intents_per_minute'] * 1.2:.2f}",
            'risk': '적절한 수준의 신호 증가, 거절 비율은 현재 유지',
            'benefit': '안정적인 점진적 개선',
        },
        'warning': '제한적 개선이지만, 데이터 수집 후 추가 평가 가능',
    }
    
    return scenario_a, scenario_b, scenario_c

def generate_audit_report(params, events):
    """감사 리포트 생성"""
    
    print("\n" + "="*80)
    print("🔍 QUANT-EVO PROMPT QUALITY AUDITOR")
    print("   (구조적 문제 식별 및 조정 제안)")
    print("="*80)
    
    analysis = analyze_prompt_structure(params, events)
    
    if not analysis:
        print("❌ 신호 데이터 부족")
        return
    
    print(f"\n📊 CURRENT PROMPT STATE")
    print("-"*80)
    print(f"버전: {params['version']}")
    print(f"수집 기간: {analysis['elapsed_minutes']:.1f}분")
    print(f"신호 생성: {analysis['signal_created_count']}개")
    print(f"신호율: {analysis['intents_per_minute']:.2f} signals/min (목표: 10-15)")
    print(f"평균 AI 점수: {analysis['ai_score_mean']:.4f}")
    print(f"BUY 비율: {analysis['buy_ratio']*100:.0f}%")
    print(f"실행률: {analysis['sent_rate']:.0f}%")
    
    print(f"\n📋 REJECTION BREAKDOWN")
    print("-"*80)
    for reason, count in sorted(analysis['rejection_reasons'].items(), key=lambda x: x[1], reverse=True):
        pct = count / analysis['exec_rejected_count'] * 100 if analysis['exec_rejected_count'] > 0 else 0
        print(f"  {reason:20s}: {count:3d}개 ({pct:5.1f}%)")
    
    # === DIAGNOSTICS ===
    print(f"\n🔧 PROBLEM ANALYSIS: 'intents/min이 낮은 이유'")
    print("-"*80)
    
    h1, h2, h3 = diagnose_low_intents_per_minute(params, analysis)
    
    print(f"\n[원인 가설 1] {h1['name']}")
    print(f"  영향도: {h1['impact']}")
    print(f"  현재값: ai_score_cut = {h1['analysis']['ai_score_cut']}")
    print(f"  실제값: 평균 신호 점수 = {h1['analysis']['actual_mean_score']:.4f}")
    print(f"  설명: {h1['reasoning']}")
    
    print(f"\n[원인 가설 2] {h2['name']}")
    print(f"  영향도: {h2['impact']}")
    print(f"  현재값: vol_spike_min = {h2['current_values']['vol_spike_min']}, book_ratio_min = {h2['current_values']['book_ratio_min']}")
    print(f"  설명: {h2['reasoning']}")
    
    print(f"\n[원인 가설 3] {h3['name']}")
    print(f"  영향도: {h3['impact']}")
    print(f"  조건:")
    for key, val in h3['analysis'].items():
        print(f"    • {key}: {val}")
    print(f"  설명: {h3['reasoning']}")
    
    # === SCENARIOS ===
    print(f"\n" + "="*80)
    print("💡 ADJUSTMENT PROPOSAL SCENARIOS")
    print("   (실제 수정 금지. 논의/검토용만)")
    print("="*80)
    
    s_a, s_b, s_c = propose_adjustment_scenarios(params, analysis, h1, h2, h3)
    
    for scenario in [s_a, s_b, s_c]:
        print(f"\n🔹 {scenario['name']}")
        print(f"   근거: {scenario['rationale']}")
        print(f"\n   제안 조정:")
        for adj in scenario['proposed_adjustments']:
            print(f"     • {adj['parameter']}")
            print(f"       현재: {adj['current_value']}")
            print(f"       제안: {adj['proposed_value']}")
            print(f"       이유: {adj['rationale']}")
        
        print(f"\n   예상 효과:")
        for key, val in scenario['expected_effects'].items():
            print(f"     • {key}: {val}")
        
        if 'warning' in scenario:
            print(f"\n   ⚠️  주의: {scenario['warning']}")
    
    # === RECOMMENDATIONS ===
    print(f"\n" + "="*80)
    print("📌 AUDITOR RECOMMENDATIONS")
    print("="*80)
    
    print(f"\n1️⃣  우선순위 진단 (가장 제한적인 요소):")
    if h1['impact'] == 'HIGH':
        print(f"   🔴 [1순위] {h1['name']} - {h1['reasoning'][:80]}...")
    if h2['impact'] == 'MEDIUM':
        print(f"   🟡 [2순위] {h2['name']} - {h2['reasoning'][:80]}...")
    if h3['impact'] == 'MEDIUM':
        print(f"   🟡 [3순위] {h3['name']} - {h3['reasoning'][:80]}...")
    
    print(f"\n2️⃣  권장 검토 순서:")
    print(f"   1단계: 신호율을 저해하는 주 요인 파악")
    print(f"          → ai_score_cut vs 시장 조건 필터 중 어느 것이 더 제한적인가?")
    print(f"   2단계: 로그에서 거절된 신호 상세 분석")
    print(f"          → 거절 신호의 AI 점수는? TTL 만료는 신호 발생 자체 문제인가?")
    print(f"   3단계: 시나리오별 시뮬레이션 (데이터 수집 후)")
    print(f"          → 각 파라미터 변화에 따른 intents/min 추정 가능")
    
    print(f"\n3️⃣  조정 권장 단계:")
    print(f"   ✅ Scenario C (1단계 완화)부터 시작")
    print(f"      이유: 낮은 위험, 데이터 수집 관찰 가능")
    print(f"   ✅ 100-200개 신호 수집 후 재평가")
    print(f"   ✅ 필요시 Scenario A/B 고려")
    
    print(f"\n4️⃣  금지 사항:")
    print(f"   ❌ 손익을 기반으로 파라미터 변경")
    print(f"   ❌ 한 번에 여러 파라미터 동시 변경")
    print(f"   ❌ 데이터 부족 상태에서 최종 결정")
    print(f"   ❌ 프롬프트 자동 수정 적용 (반드시 수동 검토)")
    
    print(f"\n5️⃣  다음 단계:")
    print(f"   → 추가 신호 200개 수집")
    print(f"   → 거절된 신호들의 상세 로그 분석")
    print(f"   → 시나리오별 예상 효과 재계산")
    print(f"   → 최종 파라미터 선택 (경영진 협의)")
    
    print(f"\n" + "="*80)
    print(f"📌 NOTE: 이 감사는 로그 통계만 기반입니다.")
    print(f"   손익, 거래 결과, 실제 수익률은 포함되지 않습니다.")
    print(f"   파라미터 변경은 신중한 검토 후 수동으로 진행하세요.")
    print("="*80 + "\n")

def main():
    project_root = Path(__file__).resolve().parents[1]
    logs_dir = project_root / "shared" / "logs"
    
    # 파라미터 로드
    params = load_params()
    
    # 로그 로드
    events = load_jsonl_events(str(logs_dir))
    
    if not events:
        print("❌ 로그 파일을 찾을 수 없습니다.")
        print("   APP64/APP32를 실행하여 신호를 생성한 후 다시 시도하세요.")
        return
    
    # 감사 리포트 생성
    generate_audit_report(params, events)

if __name__ == "__main__":
    main()
