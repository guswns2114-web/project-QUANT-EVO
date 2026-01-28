#!/usr/bin/env python3
"""
JSON Lines 로깅 시스템 통합 테스트

이 스크립트는:
1. 샘플 JSON Lines 이벤트 생성
2. analyze_logs.py 실행
3. CSV 리포트 검증
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

def create_sample_logs():
    """테스트용 샘플 로그 생성"""
    logs_dir = Path(__file__).resolve().parents[1] / "shared" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    today = datetime.now().strftime('%Y%m%d')
    app64_log = logs_dir / f"app64_{today}.jsonl"
    app32_log = logs_dir / f"app32_{today}.jsonl"
    
    print(f"[CREATING] Sample logs in {logs_dir}")
    
    # APP64 events
    base_time = datetime.now(timezone.utc)
    app64_events = [
        # 10개의 SIGNAL_CREATED 이벤트 (시간 간격 1분)
        {
            "ts": (base_time + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "module": "APP64",
            "event_type": "SIGNAL_CREATED",
            "symbol": ["005930", "035420", "068270"][i % 3],
            "action": "BUY" if i % 2 == 0 else "SELL",
            "ai_score": 0.55 + (i * 0.03),
            "params_version_id": "test_v01",
            "ttl_ms": 5000,
            "context_desc": "Test signal"
        }
        for i in range(10)
    ]
    
    with open(app64_log, 'w', encoding='utf-8') as f:
        for event in app64_events:
            f.write(json.dumps(event) + '\n')
    
    print(f"  ✓ {app64_log.name}: {len(app64_events)} events")
    
    # APP32 events - 8개 SENT, 2개 REJECTED
    app32_events = [
        # SENT 이벤트 (8개)
        {
            "ts": (base_time + timedelta(minutes=i+1)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "module": "APP32",
            "event_type": "EXEC_SENT",
            "symbol": app64_events[i]["symbol"],
            "action": app64_events[i]["action"],
            "ai_score": app64_events[i]["ai_score"],
            "params_version_id": "test_v01",
            "params_snapshot": {
                "cooldown_sec": 30,
                "max_orders_per_day": 5,
                "one_position_only": True
            }
        }
        for i in range(8)
    ]
    
    # REJECTED 이벤트 (2개)
    rejected_events = [
        {
            "ts": (base_time + timedelta(minutes=8)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "module": "APP32",
            "event_type": "EXEC_REJECTED",
            "symbol": "005930",
            "action": "BUY",
            "ai_score": 0.72,
            "params_version_id": "test_v01",
            "rejection_reason": "COOLDOWN",
            "context": {
                "elapsed_sec": 5.2,
                "remaining_sec": 24.8,
                "cooldown_sec": 30
            }
        },
        {
            "ts": (base_time + timedelta(minutes=9)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "module": "APP32",
            "event_type": "EXEC_REJECTED",
            "symbol": "035420",
            "action": "BUY",
            "ai_score": 0.68,
            "params_version_id": "test_v01",
            "rejection_reason": "TTL_EXPIRED",
            "context": {
                "age_ms": 5500,
                "ttl_ms": 5000
            }
        }
    ]
    
    with open(app32_log, 'w', encoding='utf-8') as f:
        for event in app32_events + rejected_events:
            f.write(json.dumps(event) + '\n')
    
    print(f"  ✓ {app32_log.name}: {len(app32_events) + len(rejected_events)} events")
    print(f"    - EXEC_SENT: {len(app32_events)}")
    print(f"    - EXEC_REJECTED: {len(rejected_events)}")

def run_analysis():
    """분석 도구 실행"""
    print(f"\n[ANALYZING]")
    
    import subprocess
    project_root = Path(__file__).resolve().parents[1]
    analyze_script = project_root / "tools" / "analyze_logs.py"
    
    result = subprocess.run(
        [sys.executable, str(analyze_script)],
        cwd=str(project_root),
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.returncode == 0

def verify_reports():
    """생성된 리포트 검증"""
    print(f"\n[VERIFYING]")
    
    project_root = Path(__file__).resolve().parents[1]
    reports_dir = project_root / "shared" / "reports"
    
    csv_files = [
        "metrics.csv",
        "rejection_analysis.csv",
        "aggressiveness_index.csv",
        "per_symbol.csv",
        "per_version.csv"
    ]
    
    all_exist = True
    for csv_file in csv_files:
        csv_path = reports_dir / csv_file
        if csv_path.exists():
            size = csv_path.stat().st_size
            print(f"  ✓ {csv_file}: {size} bytes")
        else:
            print(f"  ✗ {csv_file}: NOT FOUND")
            all_exist = False
    
    return all_exist

def main():
    print("="*70)
    print("JSON LINES LOGGING SYSTEM - INTEGRATION TEST")
    print("="*70)
    
    try:
        # 1. 샘플 로그 생성
        create_sample_logs()
        
        # 2. 분석 실행
        if not run_analysis():
            print("[ERROR] Analysis failed")
            return 1
        
        # 3. 리포트 검증
        if not verify_reports():
            print("[ERROR] Some reports missing")
            return 1
        
        print("\n" + "="*70)
        print("[SUCCESS] All tests passed!")
        print("="*70)
        return 0
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
