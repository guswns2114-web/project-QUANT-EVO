import json, random, time
from datetime import datetime, timezone
from pathlib import Path
import os, sys, stat, subprocess, atexit
from db import connect, init_schema, get_kst_date

CONFIG_PATH = Path(__file__).resolve().parents[1] / "shared" / "config" / "strategy_params.json"
LOGS_PATH = Path(__file__).resolve().parents[1] / "shared" / "logs"
LOGS_PATH.mkdir(parents=True, exist_ok=True)

# ========== SINGLE-INSTANCE LOCK MECHANISM ==========
LOCK_FILE = Path(__file__).resolve().parents[1] / "shared" / ".signal_engine.lock"

def pid_exists(pid):
    """
    Check if process with given PID exists (Windows-compatible).
    Priority: psutil > tasklist > assume dead
    """
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    
    # Fallback: tasklist parsing (Windows)
    try:
        result = subprocess.run(
            f'tasklist /FI "PID eq {pid}" /NH',
            capture_output=True,
            text=True,
            timeout=2
        )
        # If PID exists, output will contain process name + PID
        return str(pid) in result.stdout
    except Exception:
        # If tasklist fails, assume process is dead
        return False

def log_duplicate_instance(current_pid, existing_pid):
    """Log duplicate instance block event to JSONL."""
    try:
        log_entry = {
            'ts': datetime.now(timezone.utc).isoformat() + "Z",
            'module': 'APP64',
            'event_type': 'DUPLICATE_INSTANCE_BLOCKED',
            'current_pid': current_pid,
            'existing_pid': existing_pid,
            'lock_path': str(LOCK_FILE),
        }
        
        log_file = LOGS_PATH / f"app64_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception as e:
        print(f"[LOG_ERROR] Failed to log duplicate instance: {e}")

def acquire_lock_atomic():
    """
    Acquire exclusive lock using atomic file creation.
    Returns: (acquired: bool, existing_pid: int or None)
    
    Algorithm:
    1. Try atomic open (O_CREAT|O_EXCL) - only one process succeeds
    2. If fails: existing lock found -> check if stale
    3. If stale: delete and retry once
    4. Return status + existing PID if blocked
    """
    current_pid = os.getpid()
    created_at = datetime.now(timezone.utc).isoformat()
    lock_content = f"{current_pid}|{created_at}"
    
    # Attempt 1: atomic create
    for attempt in range(2):
        try:
            # O_CREAT|O_EXCL: fail if exists
            fd = os.open(
                str(LOCK_FILE),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644
            )
            with os.fdopen(fd, 'w') as f:
                f.write(lock_content)
            return (True, None)
        except FileExistsError:
            # Lock exists - check if stale
            if attempt == 0:
                try:
                    with open(LOCK_FILE, 'r') as f:
                        lock_data = f.read().strip()
                    
                    if '|' in lock_data:
                        existing_pid = int(lock_data.split('|')[0])
                    else:
                        # Old format (no timestamp) - assume stale
                        existing_pid = int(lock_data)
                    
                    # Check if process alive
                    if not pid_exists(existing_pid):
                        # Stale lock detected - clean up and retry
                        try:
                            LOCK_FILE.unlink()
                        except:
                            pass
                        continue  # Retry atomic create
                    else:
                        # Live process - we are blocked
                        return (False, existing_pid)
                except (ValueError, IOError):
                    # Corrupted lock - try cleanup and retry
                    try:
                        LOCK_FILE.unlink()
                    except:
                        pass
                    continue
            else:
                # Second attempt failed - give up
                return (False, None)
    
    return (False, None)

def release_lock():
    """
    Release lock on exit.
    Only delete if lock file contains current process PID (safety check).
    """
    current_pid = os.getpid()
    try:
        if LOCK_FILE.exists():
            with open(LOCK_FILE, 'r') as f:
                lock_data = f.read().strip()
            
            # Extract PID from lock file (format: "pid|created_at")
            if '|' in lock_data:
                lock_pid = int(lock_data.split('|')[0])
            else:
                lock_pid = int(lock_data)
            
            # Only delete if it matches current process
            if lock_pid == current_pid:
                LOCK_FILE.unlink()
    except Exception:
        # Corrupted or unreadable lock - play it safe, don't delete
        pass

def ensure_single_instance():
    """
    Guard: ensure only one instance runs.
    If duplicate detected: log event + exit immediately.
    """
    acquired, existing_pid = acquire_lock_atomic()
    
    if not acquired:
        current_pid = os.getpid()
        print(f"[APP64] FATAL: signal_engine already running (PID {existing_pid})")
        log_duplicate_instance(current_pid, existing_pid)
        sys.exit(1)
    
    # Register cleanup on exit
    atexit.register(release_lock)

# ========== END LOCK MECHANISM ==========

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def now_iso():
    """ISO 8601 with milliseconds"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def now_ms():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def load_params():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

def clamp(value, low, high):
    return max(low, min(high, value))

def select_symbol(symbols, last_seen, dedupe_window_sec):
    now_ts = time.time()
    eligible = [s for s in symbols if (now_ts - last_seen.get(s, 0)) >= dedupe_window_sec]
    if not eligible:
        return random.choice(symbols)
    return random.choice(eligible)

def log_jsonl(event_type, symbol, action, ai_score, params_version_id, ttl_ms, **kwargs):
    """
    Log signal events to JSON Lines format.
    
    Example entry:
    {"ts":"2026-01-28T14:35:42.123Z","module":"APP64","event_type":"SIGNAL_CREATED",
     "symbol":"005930","action":"BUY","ai_score":0.75,"params_version_id":"2026-01-28_01",
     "ttl_ms":5000,"metadata":{...}}
    """
    try:
        log_entry = {
            'ts': now_iso(),
            'module': 'APP64',
            'event_type': event_type,
            'symbol': symbol,
            'action': action,
            'ai_score': round(ai_score, 4),
            'params_version_id': params_version_id,
            'ttl_ms': ttl_ms,
        }
        # Add any additional metadata
        log_entry.update(kwargs)
        
        log_file = LOGS_PATH / f"app64_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception as e:
        print(f"[LOG_ERROR] {e}")

def log_signal(conn, ts, symbol, action, ai_score, params_version_id, context=""):
    """
    Structured signal generation log entry (DB).
    """
    conn.execute(
        "INSERT INTO execution_log "
        "(ts, module, symbol, action, decision, rejection_reason, ai_score, params_version_id, context) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, "APP64", symbol, action, "CREATED", None, ai_score, params_version_id, context)
    )
    
    # Console output (legacy, kept for monitoring)
    print(f"[{ts}] [APP64] [CREATED] {action} {symbol} score={ai_score:.2f} ver={params_version_id}")

def main():
    # CRITICAL: Single-instance guard BEFORE any DB operations
    ensure_single_instance()
    
    conn = connect()
    init_schema(conn)
    print("[APP64] MOCK-ONLY MODE STARTED", now())

    mock_last_seen = {}

    while True:
        # ====== LOAD CONFIGURATION ONCE PER LOOP ======
        params = load_params()
        ver = params["version"]
        
        # MOCK mode parameters (all required)
        ttl = params["signal"]["signal_ttl_ms"]
        mock_intents_per_min = params.get("mock_intents_per_min", 6)
        mock_symbols = params.get("mock_symbols", ["005930"])
        mock_action_ratio_buy = params.get("mock_action_ratio_buy", 0.5)
        mock_ai_score_mean = params.get("mock_ai_score_mean", 0.685)
        mock_ai_score_std = params.get("mock_ai_score_std", 0.05)
        dedupe_window_sec = params.get("dedupe_window_sec", 5)
        
        current_ts = now_ms()
        created_at = now_iso()

        # ====== MOCK MODE: Generate synthetic signals ======
        # Select symbol from MOCK symbols list with deduplication
        sym = select_symbol(mock_symbols, mock_last_seen, dedupe_window_sec)
        
        # Generate AI score from Gaussian distribution
        score = clamp(random.gauss(mock_ai_score_mean, mock_ai_score_std), 0.0, 1.0)
        
        # Generate action (BUY or SELL) based on ratio
        action = "BUY" if random.random() < mock_action_ratio_buy else "SELL"
        
        # Get KST trade_day for DAILY_LIMIT tracking
        trade_day = get_kst_date()
        
        # Insert into database
        conn.execute(
            "INSERT INTO orders_intent(ts, created_at, trade_day, symbol, action, ai_score, ttl_ms, params_version_id, status) VALUES (?,?,?,?,?,?,?,?, 'NEW')",
            (now(), created_at, trade_day, sym, action, score, ttl, ver)
        )
        
        # Log to database execution_log
        context = (
            f'{{"data_mode":"MOCK", "mock_intents_per_min": {mock_intents_per_min}, '
            f'"mock_symbols": {json.dumps(mock_symbols)}, '
            f'"mock_action_ratio_buy": {mock_action_ratio_buy}, "mock_ai_score_mean": {mock_ai_score_mean}, '
            f'"mock_ai_score_std": {mock_ai_score_std}, "dedupe_window_sec": {dedupe_window_sec}}}'
        )
        log_signal(conn, current_ts, sym, action, score, ver, context)
        
        # Log to JSON Lines
        log_jsonl(
            'SIGNAL_CREATED',
            sym,
            action,
            score,
            ver,
            ttl,
            data_mode="MOCK",
            created_at=created_at
        )
        
        # Track deduplication window
        mock_last_seen[sym] = time.time()
        
        # Sleep based on target intents per minute
        interval_sec = 60.0 / max(mock_intents_per_min, 0.1)
        time.sleep(interval_sec)

if __name__ == "__main__":
    main()
