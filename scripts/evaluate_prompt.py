#!/usr/bin/env python3
"""
AI Prompt Quality Evaluator

프롬프트 품질을 정량적으로 평가하고 개선 방향을 제시하는 도구.
실행 로그 기반, dry-run 전용.
"""

import sqlite3
from pathlib import Path
from collections import defaultdict
import statistics
import json

DB_PATH = Path(__file__).resolve().parents[1] / "shared" / "data" / "trading.db"

def connect_db():
    if not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
        return conn
    except:
        return None

class PromptEvaluator:
    """AI 프롬프트 품질 평가기"""
    
    def __init__(self, conn):
        self.conn = conn
    
    def get_signal_distribution(self):
        """
        신호 점수 분포 분석
        
        반환:
            dict: mean, std, min, max, count
        """
        try:
            cursor = self.conn.execute(
                "SELECT ai_score FROM execution_log WHERE module='APP64'"
            )
            scores = [row[0] for row in cursor.fetchall()]
            
            if not scores:
                return None
            
            return {
                'count': len(scores),
                'mean': round(statistics.mean(scores), 4),
                'stdev': round(statistics.stdev(scores), 4) if len(scores) > 1 else 0.0,
                'min': round(min(scores), 4),
                'max': round(max(scores), 4),
                'median': round(statistics.median(scores), 4),
            }
        except:
            return None
    
    def get_discrimination_index(self):
        """
        판별력 지수 계산 (DI)
        
        DI > 1.0: 좋은 판별력
        DI 0.5-1.0: 중간 판별력
        DI < 0.5: 나쁜 판별력
        """
        try:
            # SENT 신호
            cursor = self.conn.execute(
                "SELECT ai_score FROM execution_log WHERE module='APP32' AND decision='SENT'"
            )
            sent_scores = [row[0] for row in cursor.fetchall()]
            
            # REJECTED 신호
            cursor = self.conn.execute(
                "SELECT ai_score FROM execution_log WHERE module='APP32' AND decision='REJECTED'"
            )
            rejected_scores = [row[0] for row in cursor.fetchall()]
            
            if not sent_scores or not rejected_scores:
                return None
            
            sent_mean = statistics.mean(sent_scores)
            rejected_mean = statistics.mean(rejected_scores)
            sent_std = statistics.stdev(sent_scores) if len(sent_scores) > 1 else 0.001
            rejected_std = statistics.stdev(rejected_scores) if len(rejected_scores) > 1 else 0.001
            
            di = (sent_mean - rejected_mean) / (sent_std + rejected_std)
            
            return {
                'DI': round(di, 4),
                'SENT_mean': round(sent_mean, 4),
                'SENT_std': round(sent_std, 4),
                'SENT_count': len(sent_scores),
                'REJECTED_mean': round(rejected_mean, 4),
                'REJECTED_std': round(rejected_std, 4),
                'REJECTED_count': len(rejected_scores),
                'score_gap': round(sent_mean - rejected_mean, 4),
            }
        except:
            return None
    
    def get_rejection_analysis(self):
        """
        거절 이유별 점수 분석
        """
        try:
            cursor = self.conn.execute(
                "SELECT rejection_reason, ai_score FROM execution_log WHERE decision='REJECTED'"
            )
            
            reason_scores = defaultdict(list)
            total = 0
            
            for reason, score in cursor.fetchall():
                reason_scores[reason].append(score)
                total += 1
            
            result = {}
            for reason in reason_scores:
                scores = reason_scores[reason]
                result[reason] = {
                    'count': len(scores),
                    'pct': round(100.0 * len(scores) / total, 2),
                    'mean_score': round(statistics.mean(scores), 4),
                    'min_score': round(min(scores), 4),
                    'max_score': round(max(scores), 4),
                }
            
            return dict(sorted(result.items(), key=lambda x: x[1]['count'], reverse=True))
        except:
            return None
    
    def get_symbol_bias(self):
        """
        종목별 편향 분석
        """
        try:
            cursor = self.conn.execute(
                "SELECT symbol, ai_score FROM execution_log WHERE module='APP32'"
            )
            
            symbol_scores = defaultdict(list)
            
            for symbol, score in cursor.fetchall():
                symbol_scores[symbol].append(score)
            
            result = {}
            for symbol in symbol_scores:
                scores = symbol_scores[symbol]
                result[symbol] = {
                    'count': len(scores),
                    'mean_score': round(statistics.mean(scores), 4),
                    'std_score': round(statistics.stdev(scores), 4) if len(scores) > 1 else 0.0,
                }
            
            # 편향 지수
            if result:
                means = [v['mean_score'] for v in result.values()]
                bias_index = max(means) - min(means)
                result['_bias_index'] = round(bias_index, 4)
            
            return dict(sorted(result.items(), key=lambda x: x[1]['mean_score'] if isinstance(x[1], dict) else 0, reverse=True))
        except:
            return None
    
    def get_time_bias(self):
        """
        시간대별 편향 분석
        """
        try:
            cursor = self.conn.execute(
                "SELECT strftime('%H', ts) as hour, ai_score FROM execution_log WHERE module='APP32'"
            )
            
            hour_scores = defaultdict(list)
            
            for hour, score in cursor.fetchall():
                hour_scores[hour].append(score)
            
            result = {}
            all_means = []
            
            for hour in sorted(hour_scores.keys()):
                scores = hour_scores[hour]
                mean = statistics.mean(scores)
                all_means.append(mean)
                result[hour] = {
                    'count': len(scores),
                    'mean_score': round(mean, 4),
                    'std_score': round(statistics.stdev(scores), 4) if len(scores) > 1 else 0.0,
                }
            
            # 시간 편향 지수
            if all_means:
                time_bias = max(all_means) - min(all_means)
                result['_time_bias'] = round(time_bias, 4)
            
            return result
        except:
            return None
    
    def diagnose_problems(self):
        """
        프롬프트 문제 자동 진단
        """
        diagnostics = []
        
        # 신호 분포 검사
        sig_dist = self.get_signal_distribution()
        if sig_dist:
            if sig_dist['mean'] > 0.80:
                diagnostics.append({
                    'type': 'OVER_AGGRESSIVE',
                    'severity': 'HIGH',
                    'description': f"평균 점수가 {sig_dist['mean']}로 과도하게 높음",
                    'action': '프롬프트: 낮은 점수 신호 생성 장려'
                })
            elif sig_dist['mean'] < 0.60:
                diagnostics.append({
                    'type': 'OVER_CONSERVATIVE',
                    'severity': 'HIGH',
                    'description': f"평균 점수가 {sig_dist['mean']}로 과도하게 낮음",
                    'action': '프롬프트: 높은 점수 신호 생성 장려'
                })
            
            if sig_dist['stdev'] < 0.05:
                diagnostics.append({
                    'type': 'LOW_VARIANCE',
                    'severity': 'MEDIUM',
                    'description': f"표준편차 {sig_dist['stdev']}로 신호 단조로움",
                    'action': '프롬프트: 명확한 평가 기준별 구분 추가'
                })
            elif sig_dist['stdev'] > 0.15:
                diagnostics.append({
                    'type': 'HIGH_VARIANCE',
                    'severity': 'MEDIUM',
                    'description': f"표준편차 {sig_dist['stdev']}로 신호 불일관",
                    'action': '프롬프트: 평가 기준 명확화'
                })
        
        # 판별력 검사
        di_data = self.get_discrimination_index()
        if di_data:
            if di_data['DI'] < 0.5:
                diagnostics.append({
                    'type': 'POOR_DISCRIMINATION',
                    'severity': 'HIGH',
                    'description': f"판별력 지수 {di_data['DI']} (SENT와 REJECTED 점수 유사)",
                    'action': '필터가 정상이면 프롬프트 신호 품질 개선 필요'
                })
        
        # 거절 이유 검사
        rejection = self.get_rejection_analysis()
        if rejection:
            for reason, data in rejection.items():
                if data['mean_score'] > 0.76:
                    diagnostics.append({
                        'type': 'GOOD_SIGNALS_REJECTED',
                        'severity': 'MEDIUM',
                        'description': f"{reason}로 거절된 신호의 평균 점수 {data['mean_score']}",
                        'action': f'필터 설정 검토 필요 ({reason} 임계값 완화?)'
                    })
        
        # 편향 검사
        symbol_bias = self.get_symbol_bias()
        if symbol_bias and '_bias_index' in symbol_bias:
            if symbol_bias['_bias_index'] > 0.05:
                diagnostics.append({
                    'type': 'SYMBOL_BIAS',
                    'severity': 'MEDIUM',
                    'description': f"종목 편향 지수 {symbol_bias['_bias_index']}",
                    'action': '프롬프트: 종목별 동등 평가 기준 추가'
                })
        
        time_bias = self.get_time_bias()
        if time_bias and '_time_bias' in time_bias:
            if time_bias['_time_bias'] > 0.03:
                diagnostics.append({
                    'type': 'TIME_BIAS',
                    'severity': 'LOW',
                    'description': f"시간대 편향 지수 {time_bias['_time_bias']}",
                    'action': '프롬프트: 시간 독립성 강화'
                })
        
        return diagnostics

def print_header(text):
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}\n")

def print_section(text):
    print(f"\n{text}")
    print(f"{'-'*70}")

def main():
    print("\n" + "="*70)
    print("  AI TRADING PROMPT QUALITY EVALUATOR")
    print("  Data-driven evaluation of signal generation quality")
    print("="*70)
    
    conn = connect_db()
    if not conn:
        print("\n❌ 데이터베이스를 찾을 수 없습니다.")
        print("   APP64와 APP32를 먼저 실행하여 데이터를 생성하세요.")
        return
    
    evaluator = PromptEvaluator(conn)
    
    try:
        # 1. 신호 분포
        print_section("📊 1. Signal Distribution Analysis")
        sig_dist = evaluator.get_signal_distribution()
        
        if sig_dist:
            print(f"Total signals generated:  {sig_dist['count']:>6}")
            print(f"Mean score:               {sig_dist['mean']:>6.4f}")
            print(f"Std deviation:            {sig_dist['stdev']:>6.4f}")
            print(f"Score range:              {sig_dist['min']:.4f} ~ {sig_dist['max']:.4f}")
            print(f"Median score:             {sig_dist['median']:>6.4f}")
            
            print("\n💡 Interpretation:")
            if 0.65 < sig_dist['mean'] < 0.75 and 0.08 < sig_dist['stdev'] < 0.13:
                print("   ✅ 양호: 적절한 신호 분포")
            elif sig_dist['mean'] > 0.80:
                print("   ⚠️  과도하게 공격적: 대부분의 신호 점수가 높음")
                print("       → 프롬프트에서 낮은 점수 신호 생성 장려")
            elif sig_dist['mean'] < 0.60:
                print("   ⚠️  과도하게 보수적: 신호 개수가 적을 가능성")
                print("       → 프롬프트에서 신호 생성 임계값 낮춤")
            
            if sig_dist['stdev'] < 0.05:
                print("   ⚠️  신호 단조로움: 평가 기준이 불명확한 것으로 보임")
            elif sig_dist['stdev'] > 0.15:
                print("   ⚠️  신호 불일관: 평가 기준이 일정하지 않음")
        else:
            print("No signal data available yet.")
        
        # 2. 판별력 지수
        print_section("🎯 2. Discrimination Index (SENT vs REJECTED)")
        di_data = evaluator.get_discrimination_index()
        
        if di_data:
            print(f"Discrimination Index:     {di_data['DI']:>6.4f}")
            print(f"\nSENT signals:")
            print(f"  Count:                  {di_data['SENT_count']:>6}")
            print(f"  Mean score:             {di_data['SENT_mean']:>6.4f}")
            print(f"  Std deviation:          {di_data['SENT_std']:>6.4f}")
            print(f"\nREJECTED signals:")
            print(f"  Count:                  {di_data['REJECTED_count']:>6}")
            print(f"  Mean score:             {di_data['REJECTED_mean']:>6.4f}")
            print(f"  Std deviation:          {di_data['REJECTED_std']:>6.4f}")
            print(f"\nScore gap (SENT - REJECTED): {di_data['score_gap']:>6.4f}")
            
            print("\n💡 Interpretation:")
            if di_data['DI'] > 1.0:
                print("   ✅ 우수: AI 신호가 유효한 판별력 있음")
            elif di_data['DI'] > 0.5:
                print("   ⚠️  중간: 판별력은 있지만 개선 여지 있음")
            else:
                print("   ❌ 부족: SENT와 REJECTED 점수 구분 안 됨")
                print("       → 프롬프트의 평가 기준 명확화 필요")
        else:
            print("No execution data available yet.")
        
        # 3. 거절 이유 분석
        print_section("🚫 3. Rejection Reason Analysis")
        rejection = evaluator.get_rejection_analysis()
        
        if rejection:
            print(f"{'Reason':<20} {'Count':>6} {'%':>6} {'Avg Score':>10}")
            print("-" * 50)
            for reason, data in rejection.items():
                score_quality = "HIGH" if data['mean_score'] > 0.76 else "OK" if data['mean_score'] > 0.70 else "LOW"
                print(f"{reason:<20} {data['count']:>6} {data['pct']:>5.1f}% {data['mean_score']:>10.4f} ({score_quality})")
            
            print("\n💡 Interpretation:")
            high_score_rejections = [r for r, d in rejection.items() if d['mean_score'] > 0.76]
            if high_score_rejections:
                print(f"   ⚠️  High-score signals rejected by: {', '.join(high_score_rejections)}")
                print("       → 이 필터들이 좋은 신호를 차단하고 있음")
                print("       → 필터 설정 검토 필요 (TTL 증가? 쿨다운 감소?)")
        else:
            print("No rejection data available yet.")
        
        # 4. 종목 편향
        print_section("📈 4. Symbol Bias Analysis")
        symbol_bias = evaluator.get_symbol_bias()
        
        if symbol_bias and len(symbol_bias) > 1:
            bias_index = symbol_bias.pop('_bias_index', 0)
            
            print(f"{'Symbol':<10} {'Count':>6} {'Avg Score':>10}")
            print("-" * 30)
            for symbol, data in symbol_bias.items():
                print(f"{symbol:<10} {data['count']:>6} {data['mean_score']:>10.4f}")
            
            print(f"\nBias Index: {bias_index:.4f}")
            
            print("\n💡 Interpretation:")
            if bias_index < 0.03:
                print("   ✅ 양호: 종목 간 균형 잡힘")
            elif bias_index < 0.05:
                print("   ⚠️  약한 편향: 약간의 종목 선호 있음")
            else:
                print("   ❌ 심한 편향: 특정 종목을 선호하는 것으로 보임")
                print("       → 프롬프트: 종목별 동등 평가 기준 추가")
        else:
            print("Insufficient symbol data.")
        
        # 5. 시간 편향
        print_section("⏰ 5. Time-of-Day Bias Analysis")
        time_bias = time_bias = evaluator.get_time_bias()
        
        if time_bias and len(time_bias) > 1:
            time_bias_index = time_bias.pop('_time_bias', 0)
            
            print(f"{'Hour':<6} {'Count':>6} {'Avg Score':>10}")
            print("-" * 30)
            for hour in sorted(time_bias.keys()):
                data = time_bias[hour]
                print(f"{hour:<6} {data['count']:>6} {data['mean_score']:>10.4f}")
            
            print(f"\nTime Bias Index: {time_bias_index:.4f}")
            
            print("\n💡 Interpretation:")
            if time_bias_index < 0.03:
                print("   ✅ 양호: 시간별 신호 균형")
            else:
                print("   ⚠️  시간 편향: 특정 시간대 신호 품질 편차")
                print("       → 프롬프트: 시간 독립성 강화")
        else:
            print("Insufficient time-series data.")
        
        # 6. 자동 진단
        print_section("🔍 6. Automatic Diagnosis")
        diagnostics = evaluator.diagnose_problems()
        
        if diagnostics:
            print(f"발견된 문제: {len(diagnostics)}개\n")
            
            for i, diag in enumerate(diagnostics, 1):
                severity_emoji = "❌" if diag['severity'] == 'HIGH' else "⚠️ " if diag['severity'] == 'MEDIUM' else "ℹ️ "
                print(f"{severity_emoji} [{diag['type']}] {diag['description']}")
                print(f"   → {diag['action']}\n")
        else:
            print("✅ 프롬프트 품질 양호: 주요 문제 없음")
        
        # 최종 권장사항
        print_section("📋 Final Recommendations")
        print("""
1. 위의 진단 결과를 검토하세요.
2. 가장 심각한 문제부터 해결하세요.
3. 각 변경 후 새로운 버전으로 테스트하세요:
   - strategy_params.json의 "version" 증가
   - 최소 충분한 데이터 수집 (500+ 신호)
4. 이전 버전과 비교하여 개선 여부 확인하세요.
5. 모든 데이터는 영구 보관되므로 언제든 비교 가능합니다.
        """)
        
    except Exception as e:
        print(f"\n❌ 분석 중 오류: {e}")
    
    finally:
        conn.close()

if __name__ == "__main__":
    main()
