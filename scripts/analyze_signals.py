#!/usr/bin/env python3
"""
Signal Quality Analysis Tool

목적:
  - 실행 로그(execution_log)를 읽어서 거래 신호 품질 평가
  - AI 프롬프트와 전략 파라미터 튜닝의 근거 제공
  - 신호 생성/거절 패턴 분석

특징:
  - 읽기 전용 분석 (데이터 변경 없음)
  - 데이터베이스 정리 없음 (완전한 감시 추적)
  - 독립형 스크립트 (별도 의존성 최소)
"""

import sqlite3
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import json

# 데이터베이스 경로
DB_PATH = Path(__file__).resolve().parents[1] / "shared" / "data" / "trading.db"

def connect_db():
    """데이터베이스 연결 (읽기 전용)"""
    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        return None
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    return conn

def get_total_signals(conn):
    """
    총 신호 개수 조회
    
    목적:
      - 일정 기간 동안 얼마나 많은 신호가 생성되었는지 파악
      - AI가 얼마나 자주 트리거되는지 평가
    """
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM execution_log WHERE module='APP64'"
        )
        return cursor.fetchone()[0]
    except sqlite3.OperationalError:
        # 테이블이 없으면 0 반환 (데이터 없음)
        return 0

def get_sent_vs_rejected(conn):
    """
    승인(SENT)과 거절(REJECTED) 비율
    
    목적:
      - 신호의 실행률(execution rate) 계산
      - 위험 필터의 효과성 평가
      - 높은 거절율 = 필터 과도 또는 신호 품질 저하
      - 낮은 거절율 = 필터 느슨함 또는 신호 우수
    """
    try:
        cursor = conn.execute(
            "SELECT decision, COUNT(*) as count FROM execution_log "
            "WHERE module='APP32' GROUP BY decision"
        )
        result = {"SENT": 0, "REJECTED": 0}
        for decision, count in cursor.fetchall():
            result[decision] = count
        
        total = result["SENT"] + result["REJECTED"]
        if total > 0:
            result["SENT_PCT"] = round(100.0 * result["SENT"] / total, 2)
            result["REJECTED_PCT"] = round(100.0 * result["REJECTED"] / total, 2)
        
        return result
    except sqlite3.OperationalError:
        return {"SENT": 0, "REJECTED": 0, "SENT_PCT": 0.0, "REJECTED_PCT": 0.0}

def get_rejection_distribution(conn):
    """
    거절 이유별 분포
    
    목적:
      - 어떤 위험 규칙이 가장 많이 작동하는지 파악
      - 과도한 필터 감지 (예: COOLDOWN이 50% 이상이면 쿨다운이 너무 길 수 있음)
      - 미충족 필터 감지 (예: TTL_EXPIRED가 0이면 신호가 너무 오래 대기 중)
    """
    try:
        cursor = conn.execute(
            "SELECT rejection_reason, COUNT(*) as count FROM execution_log "
            "WHERE decision='REJECTED' GROUP BY rejection_reason ORDER BY count DESC"
        )
        result = {}
        total_rejected = 0
        
        for reason, count in cursor.fetchall():
            result[reason] = count
            total_rejected += count
        
        # 퍼센트 계산
        for reason in result:
            result[reason] = {
                "count": result[reason],
                "pct": round(100.0 * result[reason] / total_rejected, 2) if total_rejected > 0 else 0.0
            }
        
        return result
    except sqlite3.OperationalError:
        return {}

def get_ai_score_distribution(conn):
    """
    AI 점수 분포 (승인 vs 거절)
    
    목적:
      - 승인된 신호가 거절된 신호보다 높은 점수를 가지는가?
      - AI 점수 커트(ai_score_cut)가 적절한가?
      - 명확한 분리 = 좋은 AI 모델 / 중첩 = 신호 품질 문제
    """
    try:
        # 승인된 신호
        cursor = conn.execute(
            "SELECT COUNT(*), AVG(ai_score), MIN(ai_score), MAX(ai_score) "
            "FROM execution_log WHERE module='APP32' AND decision='SENT'"
        )
        sent_row = cursor.fetchone()
        
        # 거절된 신호
        cursor = conn.execute(
            "SELECT COUNT(*), AVG(ai_score), MIN(ai_score), MAX(ai_score) "
            "FROM execution_log WHERE module='APP32' AND decision='REJECTED'"
        )
        rejected_row = cursor.fetchone()
        
        return {
            "SENT": {
                "count": sent_row[0],
                "avg_score": round(sent_row[1], 4) if sent_row[1] else 0.0,
                "min_score": round(sent_row[2], 4) if sent_row[2] else 0.0,
                "max_score": round(sent_row[3], 4) if sent_row[3] else 0.0,
            },
            "REJECTED": {
                "count": rejected_row[0],
                "avg_score": round(rejected_row[1], 4) if rejected_row[1] else 0.0,
                "min_score": round(rejected_row[2], 4) if rejected_row[2] else 0.0,
                "max_score": round(rejected_row[3], 4) if rejected_row[3] else 0.0,
            }
        }
    except sqlite3.OperationalError:
        return {
            "SENT": {"count": 0, "avg_score": 0.0, "min_score": 0.0, "max_score": 0.0},
            "REJECTED": {"count": 0, "avg_score": 0.0, "min_score": 0.0, "max_score": 0.0}
        }

def get_per_symbol_frequency(conn):
    """
    종목별 신호 빈도
    
    목적:
      - 종목 다양성 평가 (한 종목에 편중되지 않았는가?)
      - 특정 종목이 더 높은 신호를 생성하는가?
      - 우주 설정의 효과 검증 (max_symbols 적절한가?)
    """
    try:
        cursor = conn.execute(
            "SELECT symbol, decision, COUNT(*) as count FROM execution_log "
            "WHERE module='APP32' GROUP BY symbol, decision ORDER BY symbol"
        )
        
        result = defaultdict(lambda: {"SENT": 0, "REJECTED": 0, "total": 0})
        
        for symbol, decision, count in cursor.fetchall():
            result[symbol][decision] = count
            result[symbol]["total"] += count
        
        # 비율 계산
        for symbol in result:
            total = result[symbol]["total"]
            if total > 0:
                result[symbol]["SENT_PCT"] = round(100.0 * result[symbol]["SENT"] / total, 2)
                result[symbol]["REJECTED_PCT"] = round(100.0 * result[symbol]["REJECTED"] / total, 2)
        
        return dict(sorted(result.items()))
    except sqlite3.OperationalError:
        return {}

def get_per_version_stats(conn):
    """
    파라미터 버전별 통계
    
    목적:
      - 서로 다른 파라미터 세트의 성능 비교 (A/B 테스트)
      - 어떤 버전이 더 나은 신호를 생성하는가?
      - 파라미터 최적화 방향 결정
    """
    try:
        cursor = conn.execute(
            "SELECT params_version_id, module, decision, COUNT(*) as count "
            "FROM execution_log GROUP BY params_version_id, module, decision "
            "ORDER BY params_version_id DESC, module"
        )
        
        result = defaultdict(lambda: {"APP64_created": 0, "APP32_sent": 0, "APP32_rejected": 0})
        
        for version, module, decision, count in cursor.fetchall():
            if module == "APP64" and decision == "CREATED":
                result[version]["APP64_created"] = count
            elif module == "APP32" and decision == "SENT":
                result[version]["APP32_sent"] = count
            elif module == "APP32" and decision == "REJECTED":
                result[version]["APP32_rejected"] = count
        
        # 비율 계산
        for version in result:
            total_app32 = result[version]["APP32_sent"] + result[version]["APP32_rejected"]
            if total_app32 > 0:
                result[version]["execution_rate"] = round(
                    100.0 * result[version]["APP32_sent"] / total_app32, 2
                )
            else:
                result[version]["execution_rate"] = 0.0
        
        return dict(result)
    except sqlite3.OperationalError:
        return {}

def get_rejection_by_version(conn):
    """
    버전별 거절 이유 분포
    
    목적:
      - 버전마다 주요 거절 원인이 다른가?
      - 파라미터 변경 전후 거절 패턴 비교
      - 특정 버전에서 특정 필터가 과도하게 작동하는가?
    """
    try:
        cursor = conn.execute(
            "SELECT params_version_id, rejection_reason, COUNT(*) as count "
            "FROM execution_log WHERE decision='REJECTED' "
            "GROUP BY params_version_id, rejection_reason "
            "ORDER BY params_version_id DESC, count DESC"
        )
        
        result = defaultdict(dict)
        
        for version, reason, count in cursor.fetchall():
            result[version][reason] = count
        
        return dict(result)
    except sqlite3.OperationalError:
        return {}

def format_section(title):
    """섹션 제목 포맷팅"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def format_subsection(title):
    """서브섹션 제목 포맷팅"""
    print(f"\n{title}")
    print(f"{'-'*60}")

def main():
    """메인 분석 함수"""
    print("\n" + "="*60)
    print("  QUANT-EVO Signal Quality Analysis")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    conn = connect_db()
    if not conn:
        return
    
    try:
        # 1. 총 신호 개수
        format_section("1. Signal Generation Overview")
        total_signals = get_total_signals(conn)
        print(f"Total signals generated (APP64):  {total_signals:>6}")
        
        # 2. 승인 vs 거절
        format_section("2. Execution vs Rejection Rate")
        sent_rejected = get_sent_vs_rejected(conn)
        print(f"SENT (approved):                  {sent_rejected['SENT']:>6} ({sent_rejected.get('SENT_PCT', 0):>5.2f}%)")
        print(f"REJECTED (filtered):              {sent_rejected['REJECTED']:>6} ({sent_rejected.get('REJECTED_PCT', 0):>5.2f}%)")
        print(f"\n💡 Insight: Execution rate shows what % of signals pass risk filters.")
        print(f"   - High rate (>70%): Filters may be too loose")
        print(f"   - Low rate (<30%): Filters may be too strict")
        
        # 3. 거절 이유 분포
        format_section("3. Rejection Reason Distribution")
        rejection_dist = get_rejection_distribution(conn)
        if rejection_dist:
            for reason, data in sorted(rejection_dist.items(), key=lambda x: x[1]["count"], reverse=True):
                print(f"{reason:20} {data['count']:>6} ({data['pct']:>5.2f}%)")
            print(f"\n💡 Insight: Dominant rejection reasons reveal filter effectiveness.")
            print(f"   - TTL_EXPIRED high: Signals may be waiting too long")
            print(f"   - COOLDOWN high: Anti-overtrading rule blocks many signals")
            print(f"   - DAILY_LIMIT high: Day trade limit is restrictive")
            print(f"   - ONE_POSITION high: Single-position constraint is binding")
        else:
            print("No rejections recorded yet.")
        
        # 4. AI 점수 분포
        format_section("4. AI Score Distribution")
        score_dist = get_ai_score_distribution(conn)
        for decision, stats in score_dist.items():
            print(f"\n{decision} Signals:")
            print(f"  Count:     {stats['count']:>6}")
            print(f"  Avg Score: {stats['avg_score']:>6.4f}")
            print(f"  Min Score: {stats['min_score']:>6.4f}")
            print(f"  Max Score: {stats['max_score']:>6.4f}")
        
        print(f"\n💡 Insight: Compare score distributions to validate AI model.")
        print(f"   - SENT avg > REJECTED avg: AI filter is working correctly")
        print(f"   - Similar distributions: ai_score_cut threshold may need tuning")
        print(f"   - High variance: Inconsistent signal generation")
        
        # 5. 종목별 빈도
        format_section("5. Per-Symbol Signal Frequency")
        symbol_freq = get_per_symbol_frequency(conn)
        if symbol_freq:
            print(f"{'Symbol':>10} {'SENT':>6} {'REJECTED':>8} {'Total':>6} {'Exec %':>8}")
            print("-" * 45)
            for symbol, stats in symbol_freq.items():
                print(f"{symbol:>10} {stats['SENT']:>6} {stats['REJECTED']:>8} {stats['total']:>6} {stats.get('SENT_PCT', 0):>7.2f}%")
            print(f"\n💡 Insight: Symbol distribution reveals universe balance.")
            print(f"   - Equal distribution: Good (universe config OK)")
            print(f"   - Skewed distribution: AI may favor certain symbols")
        else:
            print("No per-symbol data available.")
        
        # 6. 버전별 통계
        format_section("6. Per-Version Statistics")
        version_stats = get_per_version_stats(conn)
        if version_stats:
            print(f"{'Version':>20} {'Created':>8} {'Sent':>6} {'Rejected':>8} {'Exec %':>8}")
            print("-" * 55)
            for version, stats in sorted(version_stats.items(), reverse=True):
                print(f"{version:>20} {stats['APP64_created']:>8} {stats['APP32_sent']:>6} {stats['APP32_rejected']:>8} {stats['execution_rate']:>7.2f}%")
            print(f"\n💡 Insight: Version comparison enables A/B testing.")
            print(f"   - Compare execution rates across versions")
            print(f"   - Identify which parameter set performs best")
        else:
            print("No version data available.")
        
        # 7. 버전별 거절 이유
        format_section("7. Rejection Reasons by Version")
        rejection_by_version = get_rejection_by_version(conn)
        if rejection_by_version:
            for version in sorted(rejection_by_version.keys(), reverse=True):
                print(f"\n{version}:")
                for reason, count in sorted(rejection_by_version[version].items(), key=lambda x: x[1], reverse=True):
                    print(f"  {reason:20} {count:>6}")
            print(f"\n💡 Insight: Track filter effectiveness across parameter updates.")
            print(f"   - Changing cooldown_sec should affect COOLDOWN count")
            print(f"   - Changing max_orders_per_day should affect DAILY_LIMIT count")
        else:
            print("No rejection data available.")
        
        # Summary
        format_section("Summary & Recommendations")
        print("\n📊 Next Steps for Prompt/Parameter Tuning:")
        print("  1. Review rejection reason distribution")
        print("  2. Compare AI score stats (SENT vs REJECTED)")
        print("  3. Analyze per-symbol bias")
        print("  4. Run A/B tests with different parameter versions")
        print("  5. Monitor execution rate over time")
        print("\n💾 All data retained for complete audit trail (no cleanup)")
        print("   Logs can be queried for deeper analysis as needed.")
        
    except sqlite3.OperationalError as e:
        print(f"\n⚠️  Database error: {e}")
        print("   This is expected if no trades have run yet.")
        print("   Run APP64 and APP32 first to generate execution logs.")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("   Please check the database or script configuration.")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()
