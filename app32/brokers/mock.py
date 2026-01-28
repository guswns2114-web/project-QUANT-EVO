"""
MockBroker: MOCK 브로커 구현 (드라이런/시뮬레이션용).

기능:
- 주문 생성 시 즉시 성공 응답 (네트워크 지연 없음)
- execution_log에 주문 기록
- 실제 자금이 소요되지 않음
- 테스트/개발 환경에서 사용
"""

import json, time
from datetime import datetime, timezone
from typing import Optional, List
from .base import BrokerInterface, OrderResult, Position

# Import from parent package (app32.db)
try:
    from app32.db import connect, init_schema
except ImportError:
    # Fallback for local imports
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from db import connect, init_schema


class MockBroker(BrokerInterface):
    """MOCK 브로커: 주문을 즉시 성공시킴 (드라이런용)."""
    
    def __init__(self, execution_log_callback=None):
        """
        Args:
            execution_log_callback: 주문 기록 시 호출할 콜백 함수
                                   (timestamp, symbol, action, order_id, status, ...) 형태
        """
        self.conn = connect()
        init_schema(self.conn)
        self.execution_log_callback = execution_log_callback
        self.order_counter = 0  # 테스트용 주문 ID 생성
        self.mock_positions = {}  # 시뮬레이션용 포지션
    
    def place_order(self, 
                   symbol: str, 
                   action: str,
                   order_type: str = 'market',
                   quantity: int = 1,
                   price: Optional[float] = None,
                   **kwargs) -> OrderResult:
        """
        주문 생성 (즉시 성공).
        
        Returns:
            OrderResult: 항상 성공 (success=True)
        """
        # 유효성 검증
        error = self.validate_order(symbol, action, quantity, price)
        if error:
            return OrderResult(success=False, order_id=None, reason=error)
        
        # Mock 주문 ID 생성
        self.order_counter += 1
        order_id = f"MOCK_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{self.order_counter:04d}"
        
        # 실행 로그에 기록 (콜백이 있으면 호출)
        if self.execution_log_callback:
            self.execution_log_callback(
                symbol=symbol,
                action=action,
                order_id=order_id,
                status='SENT',
                quantity=quantity,
                price=price or 0.0,
                order_type=order_type
            )
        
        # Mock: 포지션 업데이트
        if symbol not in self.mock_positions:
            self.mock_positions[symbol] = {'quantity': 0, 'avg_price': 0.0}
        
        pos = self.mock_positions[symbol]
        if action == 'BUY':
            pos['quantity'] += quantity
            pos['avg_price'] = price or pos['avg_price']  # 간단한 평균가
        elif action == 'SELL':
            pos['quantity'] = max(0, pos['quantity'] - quantity)
        
        return OrderResult(
            success=True,
            order_id=order_id,
            reason="Order placed successfully (MOCK)",
            context={
                'broker': 'MOCK',
                'order_type': order_type,
                'quantity': quantity,
                'price': price
            }
        )
    
    def cancel_order(self, order_id: str) -> OrderResult:
        """
        주문 취소 (MOCK: 항상 성공).
        
        Returns:
            OrderResult: 항상 성공
        """
        return OrderResult(
            success=True,
            order_id=order_id,
            reason="Order cancelled successfully (MOCK)"
        )
    
    def get_positions(self) -> List[Position]:
        """
        현재 포지션 (MOCK: 시뮬레이션된 포지션).
        
        Returns:
            Position 리스트
        """
        positions = []
        for symbol, data in self.mock_positions.items():
            if data['quantity'] > 0:
                positions.append(Position(
                    symbol=symbol,
                    action='BUY',
                    quantity=data['quantity'],
                    avg_price=data['avg_price'],
                    current_price=data['avg_price'],  # Mock: 변화 없음
                    unrealized_pnl=0.0
                ))
        return positions
    
    def get_cash(self) -> float:
        """
        현금 잔액 (MOCK: 무한대).
        
        Returns:
            현금 금액 (1,000,000으로 고정)
        """
        return 1_000_000.0  # Mock: 항상 충분한 현금
    
    def __del__(self):
        """정리: DB 연결 종료."""
        try:
            if hasattr(self, 'conn'):
                self.conn.close()
        except:
            pass
