#!/usr/bin/env python3
"""
JSON Lines Log Analyzer for QUANT-EVO Trading System

Analyzes SIGNAL_CREATED, INTENT_INSERTED, EXEC_SENT, EXEC_REJECTED events
from JSON Lines logs in shared/logs/ directory.

Calculates metrics:
- Signal generation rate
- Execution rates
- Rejection reasons distribution
- AI score histograms
- Per-symbol and per-version analysis
- Prompt aggressiveness index (2 variants):
  1. intents_inserted / elapsed_minutes
  2. buy_intents / total_signals

Output:
- Console summary report
- CSV files: metrics.csv, rejection_analysis.csv, aggressiveness_index.csv
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from statistics import mean, stdev

def load_jsonl_files(logs_dir):
    """Load all .jsonl files from logs directory"""
    logs_path = Path(logs_dir)
    logs_path.mkdir(parents=True, exist_ok=True)
    
    all_events = []
    jsonl_files = list(logs_path.glob("*.jsonl"))
    
    if not jsonl_files:
        print(f"[INFO] No .jsonl files found in {logs_path}")
        return all_events
    
    for jsonl_file in sorted(jsonl_files):
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        event = json.loads(line)
                        all_events.append(event)
                    except json.JSONDecodeError as e:
                        print(f"[WARN] Failed to parse line in {jsonl_file.name}: {e}")
    
    return all_events

def analyze_events(events):
    """Analyze all events and return metrics"""
    
    metrics = {
        'total_events': len(events),
        'signal_created_count': 0,
        'intent_inserted_count': 0,
        'exec_sent_count': 0,
        'exec_rejected_count': 0,
        'rejection_reasons': defaultdict(int),
        'ai_scores_sent': [],
        'ai_scores_rejected': [],
        'per_symbol': defaultdict(lambda: {'created': 0, 'sent': 0, 'rejected': 0}),
        'per_version': defaultdict(lambda: {'created': 0, 'sent': 0, 'rejected': 0}),
        'per_rejection_reason': defaultdict(int),
        'buy_actions': 0,
        'sell_actions': 0,
        'events_by_type': defaultdict(list),
        'start_ts': None,
        'end_ts': None,
    }
    
    for event in events:
        event_type = event.get('event_type', '')
        symbol = event.get('symbol', 'UNKNOWN')
        action = event.get('action', '')
        ai_score = event.get('ai_score', 0)
        params_version_id = event.get('params_version_id', 'UNKNOWN')
        ts = event.get('ts', '')
        
        # Track time range
        if ts:
            if metrics['start_ts'] is None or ts < metrics['start_ts']:
                metrics['start_ts'] = ts
            if metrics['end_ts'] is None or ts > metrics['end_ts']:
                metrics['end_ts'] = ts
        
        # Count events by type
        metrics['events_by_type'][event_type].append(event)
        
        if event_type == 'SIGNAL_CREATED':
            metrics['signal_created_count'] += 1
            metrics['per_symbol'][symbol]['created'] += 1
            metrics['per_version'][params_version_id]['created'] += 1
            
        elif event_type == 'INTENT_INSERTED':
            metrics['intent_inserted_count'] += 1
            
        elif event_type == 'EXEC_SENT':
            metrics['exec_sent_count'] += 1
            metrics['per_symbol'][symbol]['sent'] += 1
            metrics['per_version'][params_version_id]['sent'] += 1
            metrics['ai_scores_sent'].append(ai_score)
            
            if action == 'BUY':
                metrics['buy_actions'] += 1
            elif action == 'SELL':
                metrics['sell_actions'] += 1
            
        elif event_type == 'EXEC_REJECTED':
            metrics['exec_rejected_count'] += 1
            metrics['per_symbol'][symbol]['rejected'] += 1
            metrics['per_version'][params_version_id]['rejected'] += 1
            metrics['ai_scores_rejected'].append(ai_score)
            
            rejection_reason = event.get('rejection_reason', 'UNKNOWN')
            metrics['rejection_reasons'][rejection_reason] += 1
            metrics['per_rejection_reason'][rejection_reason] += 1
    
    return metrics

def calculate_aggressiveness_index(metrics):
    """
    Calculate prompt aggressiveness index:
    1. Intents per minute (insertion rate)
    2. Buy ratio (buy_intents / total_signals)
    """
    agg_metrics = {}
    
    # Variant 1: Intents inserted per minute
    if metrics['start_ts'] and metrics['end_ts']:
        try:
            start = datetime.fromisoformat(metrics['start_ts'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(metrics['end_ts'].replace('Z', '+00:00'))
            elapsed_seconds = (end - start).total_seconds()
            elapsed_minutes = elapsed_seconds / 60.0 if elapsed_seconds > 0 else 1.0
            
            intents_per_minute = metrics['intent_inserted_count'] / elapsed_minutes
            agg_metrics['intents_per_minute'] = round(intents_per_minute, 4)
            agg_metrics['elapsed_minutes'] = round(elapsed_minutes, 2)
        except:
            agg_metrics['intents_per_minute'] = 0
            agg_metrics['elapsed_minutes'] = 0
    else:
        agg_metrics['intents_per_minute'] = 0
        agg_metrics['elapsed_minutes'] = 0
    
    # Variant 2: Buy intent ratio
    total_intents = metrics['intent_inserted_count']
    if total_intents > 0:
        # Count BUY intents from sent events
        buy_count = metrics['buy_actions']
        buy_ratio = buy_count / total_intents
        agg_metrics['buy_ratio'] = round(buy_ratio, 4)
    else:
        agg_metrics['buy_ratio'] = 0
    
    # Overall aggressiveness score (normalized)
    agg_metrics['aggressiveness_score'] = round(
        agg_metrics['intents_per_minute'] * 0.5 + agg_metrics['buy_ratio'] * 100 * 0.5,
        2
    )
    
    return agg_metrics

def print_summary(metrics, agg_metrics):
    """Print console summary report"""
    print("\n" + "="*70)
    print("QUANT-EVO TRADING SYSTEM - JSON LINES LOG ANALYSIS")
    print("="*70)
    
    # Basic Event Counts
    print("\n[EVENT COUNTS]")
    print(f"  Total Events:           {metrics['total_events']}")
    print(f"  SIGNAL_CREATED:         {metrics['signal_created_count']}")
    print(f"  INTENT_INSERTED:        {metrics['intent_inserted_count']}")
    print(f"  EXEC_SENT:              {metrics['exec_sent_count']}")
    print(f"  EXEC_REJECTED:          {metrics['exec_rejected_count']}")
    
    # Execution Rates
    if metrics['signal_created_count'] > 0:
        sent_rate = metrics['exec_sent_count'] / metrics['signal_created_count'] * 100
        rejected_rate = metrics['exec_rejected_count'] / metrics['signal_created_count'] * 100
    else:
        sent_rate = rejected_rate = 0
    
    print(f"\n[EXECUTION RATES]")
    print(f"  Sent Rate:              {sent_rate:.1f}%")
    print(f"  Rejected Rate:          {rejected_rate:.1f}%")
    
    # Rejection Reasons
    if metrics['rejection_reasons']:
        print(f"\n[REJECTION REASONS]")
        for reason, count in sorted(metrics['rejection_reasons'].items(), 
                                   key=lambda x: x[1], reverse=True):
            pct = count / metrics['exec_rejected_count'] * 100 if metrics['exec_rejected_count'] > 0 else 0
            print(f"  {reason:20s}: {count:4d} ({pct:5.1f}%)")
    
    # AI Score Analysis
    print(f"\n[AI SCORE STATISTICS]")
    if metrics['ai_scores_sent']:
        print(f"  SENT:")
        print(f"    Count:    {len(metrics['ai_scores_sent'])}")
        print(f"    Mean:     {mean(metrics['ai_scores_sent']):.4f}")
        if len(metrics['ai_scores_sent']) > 1:
            print(f"    StdDev:   {stdev(metrics['ai_scores_sent']):.4f}")
        print(f"    Min/Max:  {min(metrics['ai_scores_sent']):.4f} / {max(metrics['ai_scores_sent']):.4f}")
    
    if metrics['ai_scores_rejected']:
        print(f"  REJECTED:")
        print(f"    Count:    {len(metrics['ai_scores_rejected'])}")
        print(f"    Mean:     {mean(metrics['ai_scores_rejected']):.4f}")
        if len(metrics['ai_scores_rejected']) > 1:
            print(f"    StdDev:   {stdev(metrics['ai_scores_rejected']):.4f}")
        print(f"    Min/Max:  {min(metrics['ai_scores_rejected']):.4f} / {max(metrics['ai_scores_rejected']):.4f}")
    
    # Action Distribution
    total_actions = metrics['buy_actions'] + metrics['sell_actions']
    if total_actions > 0:
        buy_pct = metrics['buy_actions'] / total_actions * 100
        sell_pct = metrics['sell_actions'] / total_actions * 100
    else:
        buy_pct = sell_pct = 0
    
    print(f"\n[ACTION DISTRIBUTION (SENT)]")
    print(f"  BUY:                    {metrics['buy_actions']} ({buy_pct:.1f}%)")
    print(f"  SELL:                   {metrics['sell_actions']} ({sell_pct:.1f}%)")
    
    # Aggressiveness Index
    print(f"\n[PROMPT AGGRESSIVENESS INDEX]")
    print(f"  Time Window:            {agg_metrics['elapsed_minutes']:.1f} minutes")
    print(f"  Intents per Minute:     {agg_metrics['intents_per_minute']:.4f}")
    print(f"  Buy Ratio:              {agg_metrics['buy_ratio']:.4f} ({agg_metrics['buy_ratio']*100:.1f}%)")
    print(f"  Aggressiveness Score:   {agg_metrics['aggressiveness_score']:.2f}")
    
    # Per-Symbol Summary
    if metrics['per_symbol']:
        print(f"\n[PER-SYMBOL SUMMARY]")
        for symbol in sorted(metrics['per_symbol'].keys()):
            stats = metrics['per_symbol'][symbol]
            print(f"  {symbol:6s}: Created={stats['created']:3d}, Sent={stats['sent']:3d}, Rejected={stats['rejected']:3d}")
    
    # Per-Version Summary
    if metrics['per_version']:
        print(f"\n[PER-VERSION SUMMARY]")
        for version in sorted(metrics['per_version'].keys()):
            stats = metrics['per_version'][version]
            print(f"  {version}: Created={stats['created']:3d}, Sent={stats['sent']:3d}, Rejected={stats['rejected']:3d}")
    
    print("\n" + "="*70)

def export_csv_metrics(metrics, agg_metrics, output_dir):
    """Export metrics to CSV files"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Main metrics CSV
    metrics_file = output_path / "metrics.csv"
    with open(metrics_file, 'w', encoding='utf-8') as f:
        f.write("metric_name,value\n")
        f.write(f"total_events,{metrics['total_events']}\n")
        f.write(f"signal_created,{metrics['signal_created_count']}\n")
        f.write(f"intent_inserted,{metrics['intent_inserted_count']}\n")
        f.write(f"exec_sent,{metrics['exec_sent_count']}\n")
        f.write(f"exec_rejected,{metrics['exec_rejected_count']}\n")
        
        if metrics['signal_created_count'] > 0:
            sent_rate = metrics['exec_sent_count'] / metrics['signal_created_count'] * 100
            rejected_rate = metrics['exec_rejected_count'] / metrics['signal_created_count'] * 100
        else:
            sent_rate = rejected_rate = 0
        
        f.write(f"sent_rate_percent,{sent_rate:.2f}\n")
        f.write(f"rejected_rate_percent,{rejected_rate:.2f}\n")
        f.write(f"buy_actions,{metrics['buy_actions']}\n")
        f.write(f"sell_actions,{metrics['sell_actions']}\n")
        
        if metrics['ai_scores_sent']:
            f.write(f"ai_score_sent_mean,{mean(metrics['ai_scores_sent']):.4f}\n")
        if metrics['ai_scores_rejected']:
            f.write(f"ai_score_rejected_mean,{mean(metrics['ai_scores_rejected']):.4f}\n")
    
    print(f"[EXPORT] {metrics_file}")
    
    # Rejection Analysis CSV
    rejection_file = output_path / "rejection_analysis.csv"
    with open(rejection_file, 'w', encoding='utf-8') as f:
        f.write("rejection_reason,count,percentage\n")
        total_rejected = metrics['exec_rejected_count']
        for reason in sorted(metrics['rejection_reasons'].keys()):
            count = metrics['rejection_reasons'][reason]
            pct = count / total_rejected * 100 if total_rejected > 0 else 0
            f.write(f"{reason},{count},{pct:.2f}\n")
    
    print(f"[EXPORT] {rejection_file}")
    
    # Aggressiveness Index CSV
    agg_file = output_path / "aggressiveness_index.csv"
    with open(agg_file, 'w', encoding='utf-8') as f:
        f.write("metric,value\n")
        f.write(f"time_window_minutes,{agg_metrics['elapsed_minutes']:.2f}\n")
        f.write(f"intents_per_minute,{agg_metrics['intents_per_minute']:.4f}\n")
        f.write(f"buy_ratio,{agg_metrics['buy_ratio']:.4f}\n")
        f.write(f"aggressiveness_score,{agg_metrics['aggressiveness_score']:.2f}\n")
    
    print(f"[EXPORT] {agg_file}")
    
    # Per-Symbol CSV
    symbol_file = output_path / "per_symbol.csv"
    with open(symbol_file, 'w', encoding='utf-8') as f:
        f.write("symbol,created,sent,rejected\n")
        for symbol in sorted(metrics['per_symbol'].keys()):
            stats = metrics['per_symbol'][symbol]
            f.write(f"{symbol},{stats['created']},{stats['sent']},{stats['rejected']}\n")
    
    print(f"[EXPORT] {symbol_file}")
    
    # Per-Version CSV
    version_file = output_path / "per_version.csv"
    with open(version_file, 'w', encoding='utf-8') as f:
        f.write("version,created,sent,rejected\n")
        for version in sorted(metrics['per_version'].keys()):
            stats = metrics['per_version'][version]
            f.write(f"{version},{stats['created']},{stats['sent']},{stats['rejected']}\n")
    
    print(f"[EXPORT] {version_file}")

def main():
    # Paths
    project_root = Path(__file__).resolve().parents[1]
    logs_dir = project_root / "shared" / "logs"
    reports_dir = project_root / "shared" / "reports"
    
    print(f"[PATHS]")
    print(f"  Logs:    {logs_dir}")
    print(f"  Reports: {reports_dir}")
    
    # Load events
    print(f"\n[LOADING]")
    events = load_jsonl_files(str(logs_dir))
    print(f"  Loaded {len(events)} events")
    
    if len(events) == 0:
        print("\n[INFO] No events to analyze. Exiting.")
        return
    
    # Analyze
    print(f"\n[ANALYZING]")
    metrics = analyze_events(events)
    agg_metrics = calculate_aggressiveness_index(metrics)
    
    # Print summary
    print_summary(metrics, agg_metrics)
    
    # Export CSV
    print(f"\n[EXPORTING]")
    export_csv_metrics(metrics, agg_metrics, str(reports_dir))
    
    print(f"\n[DONE]")

if __name__ == "__main__":
    main()
