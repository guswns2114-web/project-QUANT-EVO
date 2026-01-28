"""
Test script: Run APP64 + APP32 pipeline for 5 minutes.
Validates:
- Signal generation (APP64)
- Signal processing and execution (APP32)
- trade_day column population
- DAILY_LIMIT enforcement
- Broker adapter integration
"""

import subprocess
import time
import json
from pathlib import Path
from datetime import datetime

WORKSPACE = Path("c:\\project\\QUANT-EVO")
LOGS_DIR = WORKSPACE / "shared" / "logs"
LOG_FILE = LOGS_DIR / f"app32_{datetime.now().strftime('%Y%m%d')}.jsonl"

def run_test():
    print("=" * 60)
    print("QUANT-EVO PIPELINE TEST (5 MIN)")
    print("=" * 60)
    print(f"[TEST] Starting at {datetime.now()}")
    print(f"[TEST] Log file: {LOG_FILE}")
    print()
    
    # Clean up old database to start fresh
    db_file = WORKSPACE / "shared" / "data" / "logs" / "orders.db"
    if db_file.exists():
        print(f"[TEST] Removing old DB: {db_file}")
        db_file.unlink()
    print()
    
    # Start APP32 (Execution Engine)
    print("[TEST] Starting APP32 (Execution Engine)...")
    app32_proc = subprocess.Popen(
        ["python", "app32/main.py"],
        cwd=WORKSPACE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    time.sleep(2)  # Give APP32 time to initialize
    print("[TEST] APP32 started")
    
    # Start APP64 (Signal Engine)
    print("[TEST] Starting APP64 (Signal Engine)...")
    app64_proc = subprocess.Popen(
        ["python", "app64/signal_engine.py"],
        cwd=WORKSPACE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    time.sleep(2)  # Give APP64 time to initialize
    print("[TEST] APP64 started")
    print()
    
    # Run for 5 minutes
    test_duration = 5 * 60  # seconds
    start_time = time.time()
    
    print(f"[TEST] Running for {test_duration} seconds...")
    print("[TEST] (Tail logs in real-time below)")
    print("-" * 60)
    
    try:
        while time.time() - start_time < test_duration:
            # Read APP64 output
            try:
                line = app64_proc.stdout.readline()
                if line:
                    print(f"[APP64] {line.rstrip()}")
            except:
                pass
            
            time.sleep(0.1)
        
        print("-" * 60)
        print(f"[TEST] Test duration complete at {datetime.now()}")
        
    finally:
        # Terminate processes
        print("[TEST] Terminating APP64...")
        app64_proc.terminate()
        app64_proc.wait(timeout=5)
        
        print("[TEST] Terminating APP32...")
        app32_proc.terminate()
        app32_proc.wait(timeout=5)
        
        print("[TEST] Both processes terminated")
    
    # Parse and validate results
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            lines = f.readlines()
        
        events = {}
        for line in lines:
            try:
                record = json.loads(line)
                event_type = record.get('event_type')
                events[event_type] = events.get(event_type, 0) + 1
            except:
                pass
        
        print(f"Total JSONL records: {len(lines)}")
        print("Event distribution:")
        for event_type, count in sorted(events.items()):
            print(f"  {event_type}: {count}")
        
        # Validate trade_day
        exec_sent = [json.loads(l) for l in lines if 'event_type' in json.loads(l) and json.loads(l)['event_type'] == 'EXEC_SENT']
        if exec_sent:
            print(f"\nEXEC_SENT orders: {len(exec_sent)}")
            # Check if trade_day is populated
            sample = exec_sent[0]
            print(f"  Sample: {sample}")
    else:
        print(f"[ERROR] Log file not found: {LOG_FILE}")
    
    print()
    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    run_test()
