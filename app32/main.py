import json, time, os
from datetime import datetime, timezone
from pathlib import Path
import sys
from db import connect, init_schema, get_kst_date
from brokers import MockBroker

CONFIG_PATH = Path(__file__).resolve().parents[1] / "shared" / "config" / "strategy_params.json"
LOGS_PATH = Path(__file__).resolve().parents[1] / "shared" / "logs"
LOGS_PATH.mkdir(parents=True, exist_ok=True)

# ===== REJECTION REASON CONSTANTS =====
# 거절 이유 표준화 (분석용 상수)
class RejectionReason:
    """모든 거절 이유의 표준 정의"""
    TTL_EXPIRED = "TTL_EXPIRED"              # 신호 유효시간 초과
    DAILY_LIMIT = "DAILY_LIMIT"              # 일일 매수 한도 도달
    COOLDOWN = "COOLDOWN"                    # 마지막 거래 후 쿨다운 기간 미경과
    ONE_POSITION = "ONE_POSITION"            # 포지션 중복 진입 제한
    BROKER_ERROR = "BROKER_ERROR"            # 브로커 주문 실행 오류

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def now_ms():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def now_iso():
    """ISO 8601 with milliseconds"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def today_prefix():
    return datetime.now().strftime("%Y-%m-%d")  # "2026-01-28"

def load_params():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

def log_jsonl(event_type, symbol, action, ai_score, params_version_id, 
              rejection_reason=None, cooldown_sec=0, max_orders_per_day=0, 
              one_position_only=False, latency_ms=None, **kwargs):
    """
    Log execution events to JSON Lines format.
    [TUNING v2] Added latency_ms field for performance tracking
    
    Example entries:
    EXEC_SENT:     {"ts":"2026-01-28T14:35:42.123Z","module":"APP32","event_type":"EXEC_SENT",
                    "symbol":"005930","action":"BUY","ai_score":0.75,"params_version_id":"2026-01-28_01",
                    "latency_ms":125.5,"params_snapshot":{"cooldown_sec":30,"max_orders_per_day":5,"one_position_only":true}}
    
    EXEC_REJECTED: {"ts":"2026-01-28T14:35:42.123Z","module":"APP32","event_type":"EXEC_REJECTED",
                    "symbol":"005930","action":"BUY","ai_score":0.75,"params_version_id":"2026-01-28_01",
                    "rejection_reason":"TTL_EXPIRED","latency_ms":1250.0,"context":{...}}
    """
    try:
        log_entry = {
            'ts': now_iso(),
            'module': 'APP32',
            'event_type': event_type,
            'symbol': symbol,
            'action': action,
            'ai_score': round(ai_score, 4),
            'params_version_id': params_version_id,
        }
        
        if latency_ms is not None:
            log_entry['latency_ms'] = round(latency_ms, 2)
        
        if event_type == 'EXEC_SENT':
            log_entry['params_snapshot'] = {
                'cooldown_sec': cooldown_sec,
                'max_orders_per_day': max_orders_per_day,
                'one_position_only': one_position_only
            }
        elif event_type == 'EXEC_REJECTED':
            log_entry['rejection_reason'] = rejection_reason
            if kwargs:
                log_entry['context'] = kwargs
        
        log_file = LOGS_PATH / f"app32_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    except Exception as e:
        print(f"[LOG_ERROR] {e}")

def log_execution(conn, ts, symbol, action, decision, rejection_reason, ai_score, params_version_id, context="", 
                 latency_ms=None, received_at=None, executed_at=None):
    """
    Structured execution log entry with latency tracking.
    
    Parameters:
    - ts: timestamp (YYYY-MM-DD HH:MM:SS.mmm)
    - module: "APP32" (execution engine)
    - symbol: ticker code
    - action: "BUY" / "SELL"
    - decision: "SENT" (approved) / "REJECTED" (filtered)
    - rejection_reason: ttl_expired, daily_limit, cooldown, one_position, etc. (NULL if SENT)
    - ai_score: signal confidence from APP64
    - params_version_id: strategy version for traceability
    - context: additional JSON context (timing info, counts, etc.)
    - latency_ms: time from signal creation to execution (milliseconds)
    - received_at: timestamp when APP32 received the signal (ISO 8601)
    - executed_at: timestamp after broker.place_order call (ISO 8601)
    """
    conn.execute(
        "INSERT INTO execution_log "
        "(ts, module, symbol, action, decision, rejection_reason, ai_score, params_version_id, context, latency_ms, received_at, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, "APP32", symbol, action, decision, rejection_reason, ai_score, params_version_id, context, latency_ms, received_at, executed_at)
    )
    
    # Console output (legacy, kept for monitoring)
    if decision == "SENT":
        print(f"[{ts}] [APP32] [SENT] {action} {symbol} score={ai_score:.2f} ver={params_version_id}")
    else:
        print(f"[{ts}] [APP32] [REJECTED] {symbol} {action} reason={rejection_reason} score={ai_score:.2f} ver={params_version_id}")

def log_execution_with_jsonl(conn, ts, symbol, action, decision, rejection_reason, ai_score, params_version_id, 
                             context="", cooldown_sec=0, max_orders_per_day=0, one_position_only=False,
                             latency_ms=None, received_at=None, executed_at=None):
    """
    Combined DB and JSON Lines logging for execution events.
    [TUNING v2] Added latency_ms, received_at, executed_at tracking
    """
    log_execution(conn, ts, symbol, action, decision, rejection_reason, ai_score, params_version_id, context,
                 latency_ms=latency_ms, received_at=received_at, executed_at=executed_at)
    
    if decision == "SENT":
        log_jsonl('EXEC_SENT', symbol, action, ai_score, params_version_id,
                 cooldown_sec=cooldown_sec, max_orders_per_day=max_orders_per_day, 
                 one_position_only=one_position_only, latency_ms=latency_ms)
    else:  # REJECTED
        # Parse context JSON if available
        context_dict = {}
        if context:
            try:
                context_dict = json.loads(context)
            except:
                pass
        log_jsonl('EXEC_REJECTED', symbol, action, ai_score, params_version_id,
                 rejection_reason=rejection_reason, latency_ms=latency_ms, **context_dict)

def count_sent_buy_today(conn, trade_day=None):
    """
    오늘(SENT) 처리된 주문 중 BUY만 카운트.
    trade_day column 기반 쿼리 (KST 타임존).
    """
    if trade_day is None:
        trade_day = get_kst_date()
    row = conn.execute(
        "SELECT COUNT(*) FROM orders_intent "
        "WHERE status='SENT' AND action='BUY' AND trade_day=?",
        (trade_day,)
    ).fetchone()
    return int(row[0]) if row else 0

def reset_daily_counters(conn):
    """
    테스트/디버깅용: 오늘 날짜의 SENT BUY 주문을 모두 'PROCESSED'로 변경하여
    카운터를 0으로 리셋.
    trade_day 컬럼 기반 업데이트 (KST 타임존).
    """
    trade_day = get_kst_date()
    result = conn.execute(
        "UPDATE orders_intent SET status='PROCESSED' "
        "WHERE status='SENT' AND action='BUY' AND trade_day=?",
        (trade_day,)
    )
    count = result.rowcount
    conn.commit()
    
    # 리셋 이벤트를 JSONL에 기록 (감사자용)
    log_jsonl('RESET_DAILY_COUNTERS', 'N/A', 'N/A', 0.0, 'SYSTEM',
             rejection_reason=None, 
             records_affected=count,
             event_note=f"Reset {count} BUY orders from SENT to PROCESSED on {trade_day}")
    
    print(f"[RESET] {count} BUY orders marked as PROCESSED (trade_day={trade_day})")
    return count

def create_broker_execution_callback(conn):
    """
    브로커의 주문 실행 결과를 DB에 기록하는 콜백 생성.
    
    MockBroker.place_order()가 성공하면 이 함수가 호출되어
    execution_log에 기록함.
    """
    def callback(symbol: str, action: str, order_id: str, status: str, 
                quantity: int, price: float, order_type: str):
        current_ts = now()
        ai_score = 0.0  # 브로커에서는 AI score 모름
        params_version_id = load_params().get("metadata", {}).get("version_id", "1")
        
        # execution_log에 INSERT (decision이 실제 컬럼명)
        conn.execute(
            "INSERT INTO execution_log(ts, module, symbol, action, order_id, decision, ai_score, params_version_id) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (current_ts, 'BROKER', symbol, action, order_id, status, ai_score, params_version_id)
        )
        conn.commit()
        
        print(f"[BROKER] {action} {symbol} @{order_id} logged to execution_log")
    
    return callback

def main():
    conn = connect()
    init_schema(conn)
    print("[APP32] started", now())

    # ✅ 브로커 초기화 (MOCK 모드)
    broker = MockBroker(execution_log_callback=create_broker_execution_callback(conn))
    print("[APP32] Broker initialized (MOCK mode)")

    has_position = False
    last_trade_ts = 0.0

    # ✅ 하루 BUY 주문 카운터(프로그램 재시작해도 유지되게 DB에서 로드)
    current_day = today_prefix()
    buys_today = count_sent_buy_today(conn)
    print(f"[LIMIT] loaded sent BUY orders today = {buys_today} (day={current_day})")

    while True:
        params = load_params()
        poll = params["execution"]["poll_interval_ms"] / 1000.0
        
        # Get execution parameters once for each iteration
        cooldown_sec = params["execution"].get("cooldown_sec", 0)
        max_orders_per_day = params["execution"].get("max_orders_per_day", 0)
        one_position_only = params["execution"].get("one_position_only", True)

        # ✅ 날짜가 바뀌면 카운터 리셋(정확히는 DB 기준 재로드)
        new_day = today_prefix()
        if new_day != current_day:
            current_day = new_day
            buys_today = count_sent_buy_today(conn)
            print(f"[LIMIT] day changed -> reload sent BUY orders today = {buys_today} (day={current_day})")

        rows = conn.execute(
            "SELECT id, ts, created_at, symbol, action, ai_score, params_version_id "
            "FROM orders_intent WHERE status='NEW' ORDER BY id ASC LIMIT 10"
        ).fetchall()

        for intent_id, ts, created_at, symbol, action, score, ver in rows:
            current_ts = now_ms()
            received_at = now_iso()  # [TUNING v2] Record when APP32 received this signal
            
            # ✅ [TUNING v2] Calculate latency_ms: time from signal creation to now
            latency_ms = None
            if created_at:
                try:
                    # Parse created_at: "2026-01-28 HH:MM:SS.mmm" format
                    created_dt = datetime.strptime(created_at.split('.')[0], "%Y-%m-%d %H:%M:%S")
                    # Add milliseconds if present
                    if '.' in created_at:
                        ms = int(created_at.split('.')[1][:3])
                        created_dt = created_dt.replace(microsecond=ms * 1000)
                    latency_ms = (datetime.now() - created_dt).total_seconds() * 1000.0
                except Exception as e:
                    print(f"[LATENCY_ERROR] {e} (created_at={created_at})")
                    latency_ms = None
            elif ts:
                # Fallback to ts column if created_at is NULL
                try:
                    intent_dt = datetime.strptime(ts.split('.')[0], "%Y-%m-%d %H:%M:%S")
                    if '.' in ts:
                        ms = int(ts.split('.')[1][:3])
                        intent_dt = intent_dt.replace(microsecond=ms * 1000)
                    latency_ms = (datetime.now() - intent_dt).total_seconds() * 1000.0
                except Exception as e:
                    print(f"[LATENCY_ERROR_TS] {e} (ts={ts})")
                    latency_ms = None

            # ✅ TTL 체크: 너무 오래된 신호는 폐기
            ttl_ms = params["signal"].get("signal_ttl_ms", 0)
            if ttl_ms > 0:
                # Handle milliseconds in timestamp (format: "2026-01-28 16:33:28.536")
                intent_dt = datetime.strptime(ts.split('.')[0], "%Y-%m-%d %H:%M:%S")
                age_ms = (datetime.now() - intent_dt).total_seconds() * 1000.0
                if age_ms > ttl_ms:
                    context = f'{{"age_ms": {age_ms:.0f}, "ttl_ms": {ttl_ms}}}'
                    log_execution_with_jsonl(
                        conn, current_ts, symbol, action, "REJECTED", RejectionReason.TTL_EXPIRED, score, ver, 
                        context=context, cooldown_sec=cooldown_sec, max_orders_per_day=max_orders_per_day, 
                        one_position_only=one_position_only, latency_ms=latency_ms, received_at=received_at
                    )
                    conn.execute(
                        "UPDATE orders_intent SET status='REJECTED' WHERE id=?",
                        (intent_id,)
                    )
                    continue

            # ✅ 하루 진입 제한: BUY만 제한 (SELL은 제한하면 위험)
            max_orders = params["execution"].get("max_orders_per_day", 0)
            if action == "BUY" and max_orders and max_orders > 0:
                if buys_today >= max_orders:
                    context = f'{{"buys_today": {buys_today}, "max_orders_per_day": {max_orders}}}'
                    log_execution_with_jsonl(
                        conn, current_ts, symbol, action, "REJECTED", RejectionReason.DAILY_LIMIT, score, ver, 
                        context=context, cooldown_sec=cooldown_sec, max_orders_per_day=max_orders_per_day, 
                        one_position_only=one_position_only, latency_ms=latency_ms, received_at=received_at
                    )
                    conn.execute(
                        "UPDATE orders_intent SET status='REJECTED' WHERE id=?",
                        (intent_id,)
                    )
                    continue

            # ✅ 쿨다운 체크: 마지막 BUY 후 cooldown_sec 동안 BUY 금지
            now_ts = time.time()
            if action == "BUY" and cooldown_sec > 0:
                if (now_ts - last_trade_ts) < cooldown_sec:
                    elapsed = now_ts - last_trade_ts
                    remain = cooldown_sec - elapsed
                    context = f'{{"elapsed_sec": {elapsed:.1f}, "remaining_sec": {remain:.1f}, "cooldown_sec": {cooldown_sec}}}'
                    log_execution_with_jsonl(
                        conn, current_ts, symbol, action, "REJECTED", RejectionReason.COOLDOWN, score, ver, 
                        context=context, cooldown_sec=cooldown_sec, max_orders_per_day=max_orders_per_day, 
                        one_position_only=one_position_only, latency_ms=latency_ms, received_at=received_at
                    )
                    conn.execute(
                        "UPDATE orders_intent SET status='REJECTED' WHERE id=?",
                        (intent_id,)
                    )
                    continue

            # ✅ 1포지션 제한: 이미 포지션 있으면 BUY 거절
            if params["execution"].get("one_position_only", True):
                if has_position and action == "BUY":
                    context = f'{{"has_position": true}}'
                    log_execution_with_jsonl(
                        conn, current_ts, symbol, action, "REJECTED", RejectionReason.ONE_POSITION, score, ver, 
                        context=context, cooldown_sec=cooldown_sec, max_orders_per_day=max_orders_per_day, 
                        one_position_only=one_position_only, latency_ms=latency_ms, received_at=received_at
                    )
                    conn.execute(
                        "UPDATE orders_intent SET status='REJECTED' WHERE id=?",
                        (intent_id,)
                    )
                    continue

            # ✅ 드라이런 주문 실행 - 승인됨 (브로커를 통한 실행)
            # 1. 브로커에 주문 전송
            broker_result = broker.place_order(
                symbol=symbol,
                action=action,
                order_type='market',
                quantity=1
            )
            executed_at = now_iso()  # [TUNING v2] Record execution timestamp
            
            # 2. 주문 결과 로깅 및 DB 업데이트
            if broker_result.success:
                order_id = broker_result.order_id
                print(f"[ORDER] {action} {symbol} executed -> {order_id}")
                
                # JSONL 로깅
                log_execution_with_jsonl(
                    conn, current_ts, symbol, action, "SENT", None, score, ver, 
                    context=json.dumps(broker_result.context or {}), 
                    cooldown_sec=cooldown_sec, max_orders_per_day=max_orders_per_day, 
                    one_position_only=one_position_only, latency_ms=latency_ms, 
                    received_at=received_at, executed_at=executed_at
                )
                
                # orders_intent 상태 업데이트
                conn.execute(
                    "UPDATE orders_intent SET status='SENT' WHERE id=?",
                    (intent_id,)
                )
            else:
                # 브로커 실행 실패
                print(f"[ERROR] Broker order failed: {broker_result.reason}")
                log_execution_with_jsonl(
                    conn, current_ts, symbol, action, "REJECTED", 
                    RejectionReason.BROKER_ERROR, score, ver, 
                    context=f'{{"broker_error": "{broker_result.reason}"}}', 
                    cooldown_sec=cooldown_sec, max_orders_per_day=max_orders_per_day, 
                    one_position_only=one_position_only, latency_ms=latency_ms, 
                    received_at=received_at, executed_at=executed_at
                )
                conn.execute(
                    "UPDATE orders_intent SET status='REJECTED' WHERE id=?",
                    (intent_id,)
                )
                continue

            # ✅ BUY가 실행되면: 포지션 보유 + 마지막 거래 시간 갱신 + 오늘 BUY 카운트 증가
            if action == "BUY":
                has_position = True
                last_trade_ts = time.time()
                buys_today += 1

        time.sleep(poll)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='APP32 - QUANT-EVO Execution Engine')
    parser.add_argument('--reset-daily-counters', action='store_true',
                       help='Reset daily BUY order counters (marks existing SENT as PROCESSED)')
    args = parser.parse_args()
    
    if args.reset_daily_counters:
        # Safety guard: ALLOW_RESET 환경변수 검증
        allow_reset = os.getenv('ALLOW_RESET', '0')
        if allow_reset != '1':
            print("[ERROR] --reset-daily-counters 실행 전에 ALLOW_RESET=1 환경변수 설정 필수")
            print("[ERROR] Usage: $env:ALLOW_RESET = '1'; python app32/main.py --reset-daily-counters")
            print("[ERROR] Safety guard: 의도하지 않은 리셋 방지")
            sys.exit(1)
        
        print("[APP32] --reset-daily-counters 플래그로 실행 중 (ALLOW_RESET=1 확인됨)")
        conn = connect()
        init_schema(conn)
        reset_daily_counters(conn)
        conn.close()
        print("[APP32] Daily counters reset 완료. 메인 루프를 다시 시작합니다...")
        print()
    
    main()
