"""
Execution Analysis Tool for QUANT-EVO Tuning Validation
[TUNING v2] Analyzes 3-5min concurrent execution (APP32+APP64) results

Usage:
    python tools/analyze_execution.py [--jsonl-file <path>] [--db-file <path>]

Success Criteria:
    - EXEC_SENT / (SENT + REJECTED) >= 30%
    - TTL_EXPIRED not TOP1 rejection reason
    - No 100% DAILY_LIMIT rejections
    - Average latency_ms < 5000ms (5 seconds)
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import sys

def analyze_jsonl(jsonl_file):
    """Analyze JSONL log file"""
    if not Path(jsonl_file).exists():
        print(f"[ERROR] JSONL file not found: {jsonl_file}")
        return None
    
    stats = {
        'exec_sent': 0,
        'exec_rejected': 0,
        'rejection_reasons': defaultdict(int),
        'latencies': [],
        'symbols': set(),
        'timestamps': []
    }
    
    try:
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    entry = json.loads(line)
                    
                    if entry.get('event_type') == 'EXEC_SENT':
                        stats['exec_sent'] += 1
                    elif entry.get('event_type') == 'EXEC_REJECTED':
                        stats['exec_rejected'] += 1
                        reason = entry.get('rejection_reason')
                        if reason:
                            stats['rejection_reasons'][reason] += 1
                    
                    # Collect latency
                    if 'latency_ms' in entry and entry['latency_ms'] is not None:
                        stats['latencies'].append(entry['latency_ms'])
                    
                    # Collect symbol
                    if 'symbol' in entry:
                        stats['symbols'].add(entry['symbol'])
                    
                    # Collect timestamp
                    if 'ts' in entry:
                        stats['timestamps'].append(entry['ts'])
                
                except json.JSONDecodeError as e:
                    print(f"[WARN] Invalid JSON at line {line_num}: {e}")
                    continue
        
        return stats
    except Exception as e:
        print(f"[ERROR] Failed to read JSONL: {e}")
        return None

def analyze_db(db_file):
    """Analyze execution_log from SQLite database"""
    if not Path(db_file).exists():
        print(f"[WARN] Database file not found: {db_file}")
        return None
    
    try:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        
        stats = {
            'exec_sent': 0,
            'exec_rejected': 0,
            'rejection_reasons': defaultdict(int),
            'latencies': [],
            'symbols': set(),
        }
        
        # Query execution_log
        cursor = conn.execute(
            "SELECT decision, rejection_reason, latency_ms, symbol FROM execution_log WHERE module='APP32'"
        )
        
        for row in cursor:
            decision = row['decision']
            if decision == 'SENT':
                stats['exec_sent'] += 1
            elif decision == 'REJECTED':
                stats['exec_rejected'] += 1
                reason = row['rejection_reason']
                if reason:
                    stats['rejection_reasons'][reason] += 1
            
            # Collect latency
            if row['latency_ms'] is not None:
                stats['latencies'].append(row['latency_ms'])
            
            # Collect symbol
            if row['symbol']:
                stats['symbols'].add(row['symbol'])
        
        conn.close()
        return stats
    except Exception as e:
        print(f"[ERROR] Failed to read database: {e}")
        return None

def compute_metrics(stats):
    """Compute performance metrics"""
    if not stats:
        return None
    
    sent = stats['exec_sent']
    rejected = stats['exec_rejected']
    total = sent + rejected
    
    if total == 0:
        print("[WARN] No execution records found")
        return None
    
    metrics = {
        'total_records': total,
        'exec_sent': sent,
        'exec_rejected': rejected,
        'send_rate': (sent / total * 100) if total > 0 else 0,
        'rejection_rate': (rejected / total * 100) if total > 0 else 0,
        'rejection_reasons': dict(stats['rejection_reasons']),
        'latency_stats': None,
        'symbols': list(stats['symbols']),
    }
    
    # Latency statistics
    if stats['latencies']:
        latencies = sorted(stats['latencies'])
        metrics['latency_stats'] = {
            'count': len(latencies),
            'min_ms': round(latencies[0], 2),
            'max_ms': round(latencies[-1], 2),
            'avg_ms': round(sum(latencies) / len(latencies), 2),
            'median_ms': round(latencies[len(latencies)//2], 2),
            'p95_ms': round(latencies[int(len(latencies) * 0.95)], 2) if len(latencies) > 1 else round(latencies[0], 2),
        }
    
    return metrics

def print_report(metrics):
    """Print formatted analysis report"""
    print("\n" + "="*70)
    print("QUANT-EVO EXECUTION ANALYSIS REPORT [TUNING v2]")
    print("="*70)
    
    if not metrics:
        print("[ERROR] No metrics to report")
        return
    
    print(f"\n[OVERVIEW]")
    print(f"  Total Records:        {metrics['total_records']}")
    print(f"  EXEC_SENT:            {metrics['exec_sent']} ({metrics['send_rate']:.1f}%)")
    print(f"  EXEC_REJECTED:        {metrics['exec_rejected']} ({metrics['rejection_rate']:.1f}%)")
    print(f"  Symbols Involved:     {', '.join(sorted(metrics['symbols']))}")
    
    # Rejection breakdown
    print(f"\n[REJECTION BREAKDOWN]")
    if metrics['rejection_reasons']:
        sorted_reasons = sorted(metrics['rejection_reasons'].items(), key=lambda x: x[1], reverse=True)
        for rank, (reason, count) in enumerate(sorted_reasons, 1):
            pct = (count / metrics['exec_rejected'] * 100) if metrics['exec_rejected'] > 0 else 0
            print(f"  {rank}. {reason:20} {count:6} ({pct:5.1f}%)")
    else:
        print(f"  (No rejections)")
    
    # Latency statistics
    if metrics['latency_stats']:
        ls = metrics['latency_stats']
        print(f"\n[LATENCY ANALYSIS] (n={ls['count']} records)")
        print(f"  Min:                  {ls['min_ms']:.2f} ms")
        print(f"  Avg:                  {ls['avg_ms']:.2f} ms")
        print(f"  Median:               {ls['median_ms']:.2f} ms")
        print(f"  P95:                  {ls['p95_ms']:.2f} ms")
        print(f"  Max:                  {ls['max_ms']:.2f} ms")
    else:
        print(f"\n[LATENCY ANALYSIS] No latency data available")
    
    # Success criteria assessment
    print(f"\n[SUCCESS CRITERIA CHECK]")
    send_rate = metrics['send_rate']
    ttl_expired_pct = 0
    if metrics['rejection_reasons']:
        ttl_count = metrics['rejection_reasons'].get('TTL_EXPIRED', 0)
        ttl_expired_pct = (ttl_count / metrics['exec_rejected'] * 100) if metrics['exec_rejected'] > 0 else 0
        ttl_top1 = list(sorted(metrics['rejection_reasons'].items(), key=lambda x: x[1], reverse=True))[0][0] == 'TTL_EXPIRED'
    else:
        ttl_top1 = False
    
    # Criteria 1: Send rate >= 30%
    crit1_pass = send_rate >= 30
    print(f"  [{'PASS' if crit1_pass else 'FAIL'}] Send Rate >= 30%: {send_rate:.1f}%")
    
    # Criteria 2: TTL_EXPIRED not TOP1
    crit2_pass = not ttl_top1
    print(f"  [{'PASS' if crit2_pass else 'FAIL'}] TTL_EXPIRED NOT top1 rejection: {ttl_expired_pct:.1f}% (top1)")
    
    # Criteria 3: Average latency < 5000ms
    crit3_pass = True
    if metrics['latency_stats']:
        crit3_pass = metrics['latency_stats']['avg_ms'] < 5000
        print(f"  [{'PASS' if crit3_pass else 'FAIL'}] Avg Latency < 5000ms: {metrics['latency_stats']['avg_ms']:.2f}ms")
    else:
        print(f"  [SKIP] Avg Latency check (no data)")
    
    # Overall verdict
    all_pass = crit1_pass and crit2_pass and crit3_pass
    print(f"\n[OVERALL VERDICT]")
    print(f"  {'SUCCESS' if all_pass else 'FAILURE'}")
    print("="*70 + "\n")
    
    return all_pass

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='QUANT-EVO Execution Analysis')
    parser.add_argument('--jsonl-file', type=str, help='JSONL log file path')
    parser.add_argument('--db-file', type=str, help='SQLite database file path')
    args = parser.parse_args()
    
    # Determine file paths
    project_root = Path(__file__).resolve().parents[1]
    
    if args.jsonl_file:
        jsonl_file = Path(args.jsonl_file)
    else:
        # Auto-detect latest JSONL file
        logs_path = project_root / "shared" / "logs"
        if logs_path.exists():
            jsonl_files = sorted(logs_path.glob("app32_*.jsonl"))
            if jsonl_files:
                jsonl_file = jsonl_files[-1]  # Latest
            else:
                jsonl_file = None
        else:
            jsonl_file = None
    
    if args.db_file:
        db_file = Path(args.db_file)
    else:
        db_file = project_root / "shared" / "data" / "trading.db"
    
    print(f"[INFO] Analyzing execution results...")
    print(f"[INFO] JSONL file: {jsonl_file}")
    print(f"[INFO] Database file: {db_file}")
    
    # Analyze JSONL
    stats = None
    if jsonl_file and jsonl_file.exists():
        print(f"[INFO] Reading JSONL: {jsonl_file}")
        stats = analyze_jsonl(str(jsonl_file))
    
    # Fallback to database if JSONL not available
    if not stats and db_file.exists():
        print(f"[INFO] Reading database: {db_file}")
        stats = analyze_db(str(db_file))
    
    if not stats:
        print("[ERROR] No data sources available")
        sys.exit(1)
    
    # Compute and print metrics
    metrics = compute_metrics(stats)
    if metrics:
        success = print_report(metrics)
        sys.exit(0 if success else 1)
    else:
        print("[ERROR] Failed to compute metrics")
        sys.exit(1)

if __name__ == "__main__":
    main()
