#!/usr/bin/env python3
"""
QUANT-EVO Research Engine: Prompt Quality Evaluation via Log Statistics

요구사항:
1. 손익 기반 튜닝 절대 금지 ✅
2. 로그 통계만으로 평가 ✅
3. BUY 비율, intents/min, REJECT 사유를 핵심 지표로 ✅
4. 단타 기준 승률 가능성 정의 ✅
5. 과최적화 위험 경고 ✅

출력:
- 현재 프롬프트 상태 평가
- 위험 신호
- 다음 단계 조건 체크리스트
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from statistics import mean, stdev, median

def load_jsonl_files(logs_dir):
    """JSON Lines 파일 로드"""
    logs_path = Path(logs_dir)
    all_events = []
    
    for jsonl_file in sorted(logs_path.glob("*.jsonl")):
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        all_events.append(json.loads(line))
                    except:
                        pass
    
    return all_events

def categorize_events(events):
    """이벤트를 버전별로 분류"""
    by_version = defaultdict(list)
    for event in events:
        version_id = event.get('params_version_id', 'UNKNOWN')
        by_version[version_id].append(event)
    return by_version

def analyze_version(events, version_id):
    """특정 버전의 프롬프트 분석"""
    
    signal_created = [e for e in events if e.get('event_type') == 'SIGNAL_CREATED']
    exec_sent = [e for e in events if e.get('event_type') == 'EXEC_SENT']
    exec_rejected = [e for e in events if e.get('event_type') == 'EXEC_REJECTED']
    
    # === 1. 신호 생성 패턴 분석 ===
    if signal_created:
        start_ts = signal_created[0].get('ts')
        end_ts = signal_created[-1].get('ts')
        
        try:
            start = datetime.fromisoformat(start_ts.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_ts.replace('Z', '+00:00'))
            elapsed_seconds = (end - start).total_seconds()
            elapsed_minutes = elapsed_seconds / 60.0 if elapsed_seconds > 0 else 1.0
        except:
            elapsed_minutes = 1.0
    else:
        elapsed_minutes = 1.0
    
    intents_per_minute = len(signal_created) / elapsed_minutes if elapsed_minutes > 0 else 0
    
    # === 2. BUY 비율 분석 ===
    buy_signals = sum(1 for e in signal_created if e.get('action') == 'BUY')
    buy_ratio = buy_signals / len(signal_created) if signal_created else 0
    
    # === 3. AI 점수 분포 ===
    ai_scores_created = [e.get('ai_score', 0) for e in signal_created]
    ai_scores_sent = [e.get('ai_score', 0) for e in exec_sent]
    ai_scores_rejected = [e.get('ai_score', 0) for e in exec_rejected]
    
    # === 4. 실행률 ===
    sent_rate = len(exec_sent) / len(signal_created) * 100 if signal_created else 0
    rejected_rate = len(exec_rejected) / len(signal_created) * 100 if signal_created else 0
    
    # === 5. 거절 이유 분석 ===
    rejection_reasons = defaultdict(int)
    for e in exec_rejected:
        reason = e.get('rejection_reason', 'UNKNOWN')
        rejection_reasons[reason] += 1
    
    # === 6. 심볼별 분석 ===
    symbol_sent = defaultdict(int)
    symbol_rejected = defaultdict(int)
    for e in exec_sent:
        symbol_sent[e.get('symbol')] += 1
    for e in exec_rejected:
        symbol_rejected[e.get('symbol')] += 1
    
    # === 7. 단타 승률 가능성 분석 ===
    # 정의: AI 점수 높고 거절 적으면 승률 가능성 높음
    quality_score = (
        (1.0 if ai_scores_sent and mean(ai_scores_sent) > 0.70 else 0.5) * 0.3 +
        (1.0 if sent_rate > 80 else (sent_rate / 80) if sent_rate > 0 else 0) * 0.4 +
        (1.0 if buy_ratio >= 0.6 and buy_ratio <= 0.8 else 0.5) * 0.3
    )
    
    return {
        'version_id': version_id,
        'signal_created': len(signal_created),
        'exec_sent': len(exec_sent),
        'exec_rejected': len(exec_rejected),
        'elapsed_minutes': elapsed_minutes,
        'intents_per_minute': intents_per_minute,
        'buy_ratio': buy_ratio,
        'sent_rate': sent_rate,
        'rejected_rate': rejected_rate,
        'rejection_reasons': dict(rejection_reasons),
        'ai_score_stats': {
            'created': {
                'mean': mean(ai_scores_created) if ai_scores_created else 0,
                'std': stdev(ai_scores_created) if len(ai_scores_created) > 1 else 0,
                'median': median(ai_scores_created) if ai_scores_created else 0,
            },
            'sent': {
                'mean': mean(ai_scores_sent) if ai_scores_sent else 0,
                'std': stdev(ai_scores_sent) if len(ai_scores_sent) > 1 else 0,
                'median': median(ai_scores_sent) if ai_scores_sent else 0,
            },
            'rejected': {
                'mean': mean(ai_scores_rejected) if ai_scores_rejected else 0,
                'std': stdev(ai_scores_rejected) if len(ai_scores_rejected) > 1 else 0,
                'median': median(ai_scores_rejected) if ai_scores_rejected else 0,
            }
        },
        'symbol_performance': {
            'sent': dict(symbol_sent),
            'rejected': dict(symbol_rejected),
        },
        'quality_score': quality_score,  # 0.0 ~ 1.0
    }

def evaluate_prompt_state(analysis):
    """프롬프트 상태 평가"""
    
    metrics = analysis
    
    # === 공격성 평가 ===
    if metrics['intents_per_minute'] < 5:
        aggressiveness = "매우 보수적"
        agg_level = "LOW"
    elif metrics['intents_per_minute'] < 10:
        aggressiveness = "보수적"
        agg_level = "MEDIUM-LOW"
    elif metrics['intents_per_minute'] < 15:
        aggressiveness = "중간"
        agg_level = "MEDIUM"
    elif metrics['intents_per_minute'] < 20:
        aggressiveness = "공격적"
        agg_level = "MEDIUM-HIGH"
    else:
        aggressiveness = "매우 공격적"
        agg_level = "HIGH"
    
    # === 실행 품질 평가 ===
    if metrics['sent_rate'] > 90:
        quality = "필터가 매우 관대함 (과도한 신호 실행)"
        quality_level = "LOOSE"
    elif metrics['sent_rate'] > 75:
        quality = "합리적 필터링"
        quality_level = "GOOD"
    elif metrics['sent_rate'] > 50:
        quality = "필터가 엄격함 (신호 많이 거절)"
        quality_level = "STRICT"
    else:
        quality = "필터가 매우 엄격함 (대부분 거절)"
        quality_level = "VERY_STRICT"
    
    # === BUY 비율 평가 ===
    if metrics['buy_ratio'] < 0.4:
        buy_evaluation = "매도/관망 편향 (매수 신호 부족)"
        buy_bias = "SELL_BIAS"
    elif metrics['buy_ratio'] < 0.5:
        buy_evaluation = "균형잡힌 신호 분포 (약간의 매도 편향)"
        buy_bias = "BALANCED_SELL"
    elif metrics['buy_ratio'] < 0.6:
        buy_evaluation = "균형잡힌 신호 분포"
        buy_bias = "BALANCED"
    elif metrics['buy_ratio'] < 0.7:
        buy_evaluation = "균형잡힌 신호 분포 (약간의 매수 편향)"
        buy_bias = "BALANCED_BUY"
    elif metrics['buy_ratio'] < 0.8:
        buy_evaluation = "매수 편향 신호 (공격적 매수)"
        buy_bias = "BUY_BIAS"
    else:
        buy_evaluation = "매우 강한 매수 편향 (과도한 매수)"
        buy_bias = "STRONG_BUY_BIAS"
    
    return {
        'aggressiveness': aggressiveness,
        'aggressiveness_level': agg_level,
        'quality': quality,
        'quality_level': quality_level,
        'buy_evaluation': buy_evaluation,
        'buy_bias': buy_bias,
    }

def identify_risk_signals(analysis):
    """위험 신호 식별"""
    
    risks = []
    warnings = []
    
    # === Risk 1: 실행률이 너무 높음 (필터 무시) ===
    if analysis['sent_rate'] > 95:
        risks.append({
            'level': 'HIGH',
            'signal': '실행률 과도히 높음 (>95%)',
            'reason': '거의 모든 신호가 실행됨 = 필터가 작동 안 함',
            'impact': '위험한 신호도 실행될 가능성',
        })
    elif analysis['sent_rate'] > 85:
        warnings.append({
            'level': 'MEDIUM',
            'signal': '실행률이 높음 (>85%)',
            'reason': '필터링이 충분하지 않을 수 있음',
            'impact': '거절 이유 분석 필요',
        })
    
    # === Risk 2: 실행률이 너무 낮음 (과도한 필터) ===
    if analysis['sent_rate'] < 20:
        warnings.append({
            'level': 'MEDIUM',
            'signal': '실행률 과도히 낮음 (<20%)',
            'reason': '필터가 너무 엄격하거나 신호 품질 문제',
            'impact': '거래 기회 상실',
        })
    
    # === Risk 3: BUY 비율 극단적 ===
    if analysis['buy_ratio'] > 0.85:
        warnings.append({
            'level': 'MEDIUM',
            'signal': 'BUY 비율 과도히 높음 (>85%)',
            'reason': '프롬프트가 매수만 권장 = 단방향 베팅',
            'impact': '하락장 손실 위험, 다양성 부족',
        })
    elif analysis['buy_ratio'] < 0.3:
        warnings.append({
            'level': 'MEDIUM',
            'signal': 'BUY 비율 과도히 낮음 (<30%)',
            'reason': '프롬프트가 매도/관망만 권장',
            'impact': '상승장 수익 기회 상실',
        })
    
    # === Risk 4: 거절 이유 분포 불균형 ===
    rejection_reasons = analysis['rejection_reasons']
    if rejection_reasons:
        total_rejections = sum(rejection_reasons.values())
        top_reason = max(rejection_reasons.items(), key=lambda x: x[1])
        top_ratio = top_reason[1] / total_rejections if total_rejections > 0 else 0
        
        if top_ratio > 0.7:
            warnings.append({
                'level': 'MEDIUM',
                'signal': f'거절 이유 편중: {top_reason[0]} ({top_ratio*100:.0f}%)',
                'reason': '한 가지 이유로만 거절됨 = 필터 불균형',
                'impact': '다른 위험 신호를 놓칠 가능성',
            })
    
    # === Risk 5: AI 점수 역전 (SENT < REJECTED) ===
    ai_sent = analysis['ai_score_stats']['sent']['mean']
    ai_rejected = analysis['ai_score_stats']['rejected']['mean']
    
    if ai_sent > 0 and ai_rejected > 0 and ai_sent < ai_rejected:
        warnings.append({
            'level': 'HIGH',
            'signal': 'AI 점수 역전: REJECTED > SENT',
            'reason': f'거절된 신호({ai_rejected:.3f}) > 실행 신호({ai_sent:.3f})',
            'impact': '필터가 좋은 신호를 거절하고 나쁜 신호만 실행 중',
        })
    
    # === Risk 6: AI 점수 너무 낮음 ===
    if ai_sent < 0.6:
        warnings.append({
            'level': 'MEDIUM',
            'signal': '실행 신호의 AI 점수 낮음 (<0.60)',
            'reason': '신뢰도 낮은 신호가 실행 중',
            'impact': '잘못된 거래 가능성 증가',
        })
    
    # === Risk 7: 신호 생성 부족 ===
    if analysis['intents_per_minute'] < 2:
        warnings.append({
            'level': 'MEDIUM',
            'signal': '신호 생성율 매우 낮음 (<2/min)',
            'reason': '분당 2개 미만의 신호 = 프롬프트가 너무 보수적',
            'impact': '거래 기회 심각하게 부족',
        })
    
    # === Risk 8: 과최적화 가능성 (정보 부족) ===
    if analysis['signal_created'] < 50:
        warnings.append({
            'level': 'INFO',
            'signal': '수집된 데이터 부족 (<50개 신호)',
            'reason': '통계적 유의성 확보 필요',
            'impact': '현재 지표의 신뢰도 낮음, 추가 데이터 수집 필요',
        })
    
    return risks, warnings

def define_win_rate_potential(analysis):
    """단타 기준 승률 가능성 정의"""
    
    metrics = analysis
    
    # === 승률 가능성 판단 기준 ===
    # 1. AI 점수 (SENT): 높을수록 좋음 (0.65 이상 이상적)
    # 2. AI 점수 분포: std가 작을수록 일관됨 (0.05 이하 이상적)
    # 3. 거절률: 낮을수록 좋음 (20% 이하 이상적)
    # 4. BUY 비율: 0.5~0.7 범위가 이상적 (균형잡힌 거래)
    
    score_components = {}
    
    # Component 1: AI 점수
    ai_sent = metrics['ai_score_stats']['sent']['mean']
    if ai_sent >= 0.75:
        score_components['ai_score'] = (1.0, "매우 높음 (>=0.75)")
    elif ai_sent >= 0.70:
        score_components['ai_score'] = (0.85, "높음 (0.70-0.75)")
    elif ai_sent >= 0.65:
        score_components['ai_score'] = (0.7, "양호 (0.65-0.70)")
    elif ai_sent >= 0.60:
        score_components['ai_score'] = (0.5, "낮음 (0.60-0.65)")
    else:
        score_components['ai_score'] = (0.2, "매우 낮음 (<0.60)")
    
    # Component 2: AI 점수 일관성
    ai_std = metrics['ai_score_stats']['sent']['std']
    if ai_std <= 0.05:
        score_components['consistency'] = (1.0, "매우 일관됨 (std<=0.05)")
    elif ai_std <= 0.08:
        score_components['consistency'] = (0.8, "일관됨 (0.05<std<=0.08)")
    elif ai_std <= 0.12:
        score_components['consistency'] = (0.6, "보통 (0.08<std<=0.12)")
    else:
        score_components['consistency'] = (0.3, "불일관 (std>0.12)")
    
    # Component 3: 거절 이유의 다양성 (낮은 거절률 + 명확한 이유)
    rejection_reasons = metrics['rejection_reasons']
    if metrics['rejected_rate'] < 15:
        score_components['rejection_control'] = (1.0, "우수한 필터링 (<15%)")
    elif metrics['rejected_rate'] < 30:
        score_components['rejection_control'] = (0.8, "합리적 필터링 (15-30%)")
    elif metrics['rejected_rate'] < 50:
        score_components['rejection_control'] = (0.5, "낮은 필터링 (30-50%)")
    else:
        score_components['rejection_control'] = (0.2, "과도한 필터링 (>50%)")
    
    # Component 4: BUY 비율 균형
    buy_ratio = metrics['buy_ratio']
    if 0.50 <= buy_ratio <= 0.70:
        score_components['buy_balance'] = (1.0, "균형잡힘 (0.50-0.70)")
    elif 0.40 <= buy_ratio <= 0.80:
        score_components['buy_balance'] = (0.8, "대체로 균형 (0.40-0.80)")
    elif 0.30 <= buy_ratio <= 0.90:
        score_components['buy_balance'] = (0.5, "불균형 (0.30-0.90)")
    else:
        score_components['buy_balance'] = (0.2, "극단적 불균형 (<0.30 or >0.90)")
    
    # === 종합 승률 가능성 ===
    weights = {
        'ai_score': 0.35,
        'consistency': 0.25,
        'rejection_control': 0.25,
        'buy_balance': 0.15,
    }
    
    potential_win_rate = sum(
        score_components[key][0] * weights[key]
        for key in weights.keys()
    )
    
    # 단타 기준 해석
    if potential_win_rate >= 0.85:
        win_rate_category = "EXCELLENT (85-100%)"
        win_rate_desc = "단타 성공 가능성 매우 높음 (거래 시작 OK)"
        action = "수집된 신호로 실전 테스트 고려"
    elif potential_win_rate >= 0.70:
        win_rate_category = "GOOD (70-85%)"
        win_rate_desc = "단타 성공 가능성 높음 (상한선 OK)"
        action = "추가 데이터 수집하며 지표 모니터링"
    elif potential_win_rate >= 0.55:
        win_rate_category = "FAIR (55-70%)"
        win_rate_desc = "단타 성공 가능성 중간 (개선 필요)"
        action = "프롬프트 미세 조정 또는 추가 평가"
    elif potential_win_rate >= 0.40:
        win_rate_category = "POOR (40-55%)"
        win_rate_desc = "단타 성공 가능성 낮음 (신호 품질 우려)"
        action = "프롬프트 주요 수정 고려"
    else:
        win_rate_category = "VERY_POOR (<40%)"
        win_rate_desc = "단타 성공 가능성 매우 낮음 (재설계 필요)"
        action = "전략 전반적 재검토 필수"
    
    return {
        'potential_win_rate': potential_win_rate,
        'category': win_rate_category,
        'description': win_rate_desc,
        'action': action,
        'components': score_components,
    }

def generate_checklist(analysis, win_rate, risks, warnings):
    """다음 단계 조건 체크리스트"""
    
    checklist = []
    
    # === Data Sufficiency ===
    if analysis['signal_created'] < 50:
        checklist.append({
            'stage': '1. 데이터 수집',
            'status': '❌ PENDING',
            'condition': f"최소 50개 신호 필요 (현재: {analysis['signal_created']}개)",
            'target': '100개 신호 수집',
            'estimated_time': f"{(100-analysis['signal_created'])/analysis['intents_per_minute']:.0f}분",
        })
    else:
        checklist.append({
            'stage': '1. 데이터 수집',
            'status': '✅ PASS',
            'condition': f"충분한 데이터 확보 ({analysis['signal_created']}개 신호)",
            'target': '통계 신뢰도 확보',
            'estimated_time': '완료',
        })
    
    # === Risk Assessment ===
    if risks:
        checklist.append({
            'stage': '2. 위험 평가',
            'status': '❌ PENDING',
            'condition': f"HIGH 레벨 위험 {len(risks)}개 발견",
            'target': '모든 HIGH 위험 해결',
            'action': f"위험: {', '.join(r['signal'] for r in risks)}",
        })
    else:
        checklist.append({
            'stage': '2. 위험 평가',
            'status': '✅ PASS',
            'condition': f"HIGH 레벨 위험 없음 (경고 {len(warnings)}개)",
            'target': '안정적 프롬프트 상태',
            'estimated_time': '완료',
        })
    
    # === Win Rate Potential ===
    if win_rate['potential_win_rate'] >= 0.70:
        checklist.append({
            'stage': '3. 승률 가능성',
            'status': '✅ PASS',
            'condition': f"승률 가능성 {win_rate['category']}",
            'target': '실전 거래 준비 완료',
            'estimated_time': '완료',
        })
    else:
        checklist.append({
            'stage': '3. 승률 가능성',
            'status': '⚠️  NEEDS_WORK',
            'condition': f"승률 가능성 {win_rate['category']} (목표: 70% 이상)",
            'target': '승률 가능성 70% 이상으로 개선',
            'action': win_rate['action'],
        })
    
    # === Signal Quality ===
    if analysis['sent_rate'] >= 50 and analysis['sent_rate'] <= 90:
        checklist.append({
            'stage': '4. 신호 품질',
            'status': '✅ PASS',
            'condition': f"합리적 실행률 ({analysis['sent_rate']:.0f}%)",
            'target': '필터 효율 확보',
            'estimated_time': '완료',
        })
    else:
        checklist.append({
            'stage': '4. 신호 품질',
            'status': '⚠️  REVIEW',
            'condition': f"실행률 {analysis['sent_rate']:.0f}% ({'과도' if analysis['sent_rate'] > 90 else '부족'})",
            'target': '실행률 50-90% 범위로 조정',
            'action': '필터 파라미터 재검토',
        })
    
    # === Version Stability ===
    checklist.append({
        'stage': '5. 버전 안정성',
        'status': '✅ BASELINE',
        'condition': f"버전: {analysis['version_id']}",
        'target': '현재 버전을 기준선으로 설정',
        'action': '다음 버전과의 비교 기준점',
    })
    
    # === Next Action ===
    if win_rate['potential_win_rate'] >= 0.85:
        next_stage = '실전 거래 테스트 (Paper Trading)'
    elif win_rate['potential_win_rate'] >= 0.70:
        next_stage = '추가 데이터 수집 및 안정성 모니터링'
    elif win_rate['potential_win_rate'] >= 0.55:
        next_stage = '프롬프트 미세 조정'
    else:
        next_stage = '프롬프트 주요 수정 또는 완전 재설계'
    
    checklist.append({
        'stage': '6. 다음 단계',
        'status': '→ RECOMMENDED',
        'action': next_stage,
        'rationale': win_rate['description'],
    })
    
    return checklist

def print_research_report(version_analysis, all_versions=None):
    """최종 리서치 리포트 출력"""
    
    analysis = version_analysis
    
    print("\n" + "="*80)
    print("🔬 QUANT-EVO RESEARCH ENGINE: PROMPT QUALITY EVALUATION")
    print("="*80)
    
    print(f"\n📊 ANALYZED VERSION: {analysis['version_id']}")
    print(f"   Time Window: {analysis['elapsed_minutes']:.1f} minutes")
    print(f"   Sample Size: {analysis['signal_created']} signals")
    
    # === 현재 프롬프트 상태 평가 ===
    print("\n" + "-"*80)
    print("📋 CURRENT PROMPT STATE EVALUATION")
    print("-"*80)
    
    state = evaluate_prompt_state(analysis)
    
    print(f"\n1️⃣  공격성 (Aggressiveness):")
    print(f"   수준: {state['aggressiveness']} ({state['aggressiveness_level']})")
    print(f"   신호율: {analysis['intents_per_minute']:.2f} signals/min")
    print(f"   평가: {'✅ 적절' if state['aggressiveness_level'] in ['MEDIUM', 'MEDIUM-HIGH'] else '⚠️ 검토 필요'}")
    
    print(f"\n2️⃣  필터 품질 (Filter Quality):")
    print(f"   실행률: {analysis['sent_rate']:.0f}%")
    print(f"   거절률: {analysis['rejected_rate']:.0f}%")
    print(f"   평가: {state['quality']}")
    
    print(f"\n3️⃣  매수/매도 분포 (Buy/Sell Distribution):")
    print(f"   BUY 비율: {analysis['buy_ratio']*100:.0f}%")
    print(f"   평가: {state['buy_evaluation']}")
    
    print(f"\n4️⃣  신호 신뢰도 (AI Score Statistics):")
    print(f"   생성 신호: μ={analysis['ai_score_stats']['created']['mean']:.4f}, σ={analysis['ai_score_stats']['created']['std']:.4f}")
    print(f"   실행 신호: μ={analysis['ai_score_stats']['sent']['mean']:.4f}, σ={analysis['ai_score_stats']['sent']['std']:.4f}")
    print(f"   거절 신호: μ={analysis['ai_score_stats']['rejected']['mean']:.4f}, σ={analysis['ai_score_stats']['rejected']['std']:.4f}")
    
    # AI 점수 비교
    if analysis['ai_score_stats']['sent']['mean'] > analysis['ai_score_stats']['rejected']['mean']:
        print(f"   ✅ 필터 효율: 높은 신호만 선택 중 (좋음)")
    else:
        print(f"   ⚠️  필터 효율: REVERSED! 낮은 신호가 실행 중 (위험)")
    
    print(f"\n5️⃣  거절 이유 분석 (Rejection Breakdown):")
    if analysis['rejection_reasons']:
        for reason, count in sorted(analysis['rejection_reasons'].items(), 
                                   key=lambda x: x[1], reverse=True):
            pct = count / sum(analysis['rejection_reasons'].values()) * 100
            print(f"   • {reason}: {count}개 ({pct:.0f}%)")
    else:
        print(f"   • 거절 없음")
    
    # === 위험 신호 ===
    risks, warnings = identify_risk_signals(analysis)
    
    print("\n" + "-"*80)
    print("⚠️  RISK SIGNALS & WARNINGS")
    print("-"*80)
    
    if risks:
        print(f"\n🚨 HIGH PRIORITY RISKS ({len(risks)}개):")
        for i, risk in enumerate(risks, 1):
            print(f"\n   {i}. {risk['signal']}")
            print(f"      원인: {risk['reason']}")
            print(f"      영향: {risk['impact']}")
    else:
        print(f"\n✅ HIGH 레벨 위험 없음")
    
    if warnings:
        print(f"\n⚠️  MEDIUM PRIORITY WARNINGS ({len(warnings)}개):")
        for i, warning in enumerate(warnings, 1):
            print(f"\n   {i}. {warning['signal']}")
            print(f"      원인: {warning['reason']}")
            print(f"      영향: {warning['impact']}")
    else:
        print(f"\n✅ MEDIUM 레벨 경고 없음")
    
    # === 단타 승률 가능성 ===
    win_rate = define_win_rate_potential(analysis)
    
    print("\n" + "-"*80)
    print("📈 DAY TRADING WIN RATE POTENTIAL")
    print("-"*80)
    
    print(f"\n전체 점수: {win_rate['potential_win_rate']:.1%} ({win_rate['category']})")
    print(f"평가: {win_rate['description']}")
    print(f"\n구성 요소:")
    for component, (score, desc) in win_rate['components'].items():
        bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        print(f"  • {component:20s}: {bar} {score:.1%} - {desc}")
    
    # === 다음 단계 체크리스트 ===
    checklist = generate_checklist(analysis, win_rate, risks, warnings)
    
    print("\n" + "-"*80)
    print("✅ NEXT STEPS CHECKLIST")
    print("-"*80)
    
    for item in checklist:
        print(f"\n{item['stage']} {item['status']}")
        if 'condition' in item:
            print(f"  조건: {item['condition']}")
        if 'target' in item:
            print(f"  목표: {item['target']}")
        if 'action' in item:
            print(f"  조치: {item['action']}")
        if 'rationale' in item:
            print(f"  근거: {item['rationale']}")
        if 'estimated_time' in item:
            print(f"  예상시간: {item['estimated_time']}")
    
    # === 최종 권장사항 ===
    print("\n" + "="*80)
    print("🎯 FINAL RECOMMENDATION")
    print("="*80)
    
    if win_rate['potential_win_rate'] >= 0.85:
        print("\n✅ READY FOR LIVE TESTING")
        print("\n이 프롬프트는 실전 거래 테스트를 시작할 준비가 되었습니다.")
        print("• 작은 규모부터 시작하세요")
        print("• 실행된 거래의 결과를 추적하세요")
        print("• 수익/손실보다는 기계적 거래 실행에 집중하세요")
    elif win_rate['potential_win_rate'] >= 0.70:
        print("\n⚠️  GOOD BUT NEEDS MONITORING")
        print("\n이 프롬프트는 유망하지만 추가 검증이 필요합니다.")
        print("• 추가 100-200개 신호를 수집하세요")
        print("• 안정성을 모니터링하세요")
        print("• 경고 항목들을 지켜보세요")
    elif win_rate['potential_win_rate'] >= 0.55:
        print("\n🔄 NEEDS REFINEMENT")
        print("\n이 프롬프트는 개선이 필요합니다.")
        print("• 주요 위험 신호들을 해결하세요")
        print("• 필터 파라미터를 재검토하세요")
        print("• 프롬프트 미세 조정을 고려하세요")
    else:
        print("\n❌ MAJOR REVISION REQUIRED")
        print("\n이 프롬프트는 전반적인 재검토가 필요합니다.")
        print("• 현재 설정으로는 위험합니다")
        print("• 프롬프트의 핵심 로직을 다시 검토하세요")
        print("• 필터 파라미터를 완전히 재설정하세요")
    
    print("\n" + "="*80)
    print("📌 NOTE: 이 평가는 로그 통계만을 기반으로 합니다.")
    print("   손익이나 실제 거래 결과는 포함되지 않습니다.")
    print("="*80 + "\n")

def main():
    project_root = Path(__file__).resolve().parents[1]
    logs_dir = project_root / "shared" / "logs"
    
    print(f"\n🔍 로그 디렉토리: {logs_dir}")
    
    # 로그 로드
    events = load_jsonl_files(str(logs_dir))
    
    if not events:
        print("❌ 로그 파일을 찾을 수 없습니다.")
        print("   최소 1분 이상 앱을 실행한 후 다시 시도하세요.")
        return
    
    print(f"✅ {len(events)}개 이벤트 로드됨\n")
    
    # 버전별 분석
    by_version = categorize_events(events)
    
    print(f"📋 {len(by_version)}개 버전 발견됨:")
    for version_id in by_version.keys():
        print(f"   • {version_id}")
    
    # 각 버전 분석
    print("\n" + "="*80)
    
    for version_id in sorted(by_version.keys()):
        version_events = by_version[version_id]
        analysis = analyze_version(version_events, version_id)
        print_research_report(analysis, by_version)

if __name__ == "__main__":
    main()
