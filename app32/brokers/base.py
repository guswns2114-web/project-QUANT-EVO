"""
BrokerInterface: Abstract base class for broker adapters.

목표:
- MOCK과 LIVE 브로커를 동일한 인터페이스로 취급
- 실행 로직 (place_order, cancel_order 등)을 구체적인 브로커 구현으로 분리
- 테스트 시 MOCK, 실운영 시 LIVE로 쉽게 전환
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List


@dataclass
class OrderResult:
    """주문 실행 결과"""
    success: bool                    # True: 성공, False: 실패
    order_id: Optional[str]         # 주문 ID (성공 시)
    reason: Optional[str]           # 실패 이유 또는 참고사항
    context: Optional[Dict[str, Any]] = None  # 추가 컨텍스트


@dataclass
class Position:
    """포지션 정보"""
    symbol: str
    action: str  # BUY or SELL
    quantity: int
    avg_price: float
    current_price: float
    unrealized_pnl: float


class BrokerInterface(ABC):
    """
    추상 브로커 인터페이스.
    
    모든 브로커 어댑터는 이 클래스를 상속하고 추상 메서드를 구현해야 함.
    """
    
    @abstractmethod
    def place_order(self, 
                   symbol: str, 
                   action: str,  # 'BUY' or 'SELL'
                   order_type: str = 'market',  # 'market' or 'limit'
                   quantity: int = 1,
                   price: Optional[float] = None,
                   **kwargs) -> OrderResult:
        """
        주문 생성.
        
        Args:
            symbol: 거래 대상 (e.g., 'AAPL')
            action: 'BUY' 또는 'SELL'
            order_type: 'market' (즉시 체결) 또는 'limit' (지정가)
            quantity: 주문 수량
            price: 지정가 (order_type='limit'일 때 필수)
            **kwargs: 브로커별 추가 파라미터
        
        Returns:
            OrderResult: 주문 결과 (성공/실패 및 주문 ID)
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResult:
        """
        주문 취소.
        
        Args:
            order_id: 취소할 주문 ID
        
        Returns:
            OrderResult: 취소 결과
        """
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Position]:
        """
        현재 보유 포지션 조회.
        
        Returns:
            Position 리스트
        """
        pass
    
    @abstractmethod
    def get_cash(self) -> float:
        """
        현금 잔액 조회.
        
        Returns:
            현금 금액
        """
        pass
    
    def validate_order(self, 
                      symbol: str,
                      action: str,
                      quantity: int,
                      price: Optional[float] = None) -> Optional[str]:
        """
        주문 유효성 검증 (모든 브로커 공통).
        
        Returns:
            None (유효함) 또는 에러 메시지
        """
        if action not in ['BUY', 'SELL']:
            return f"Invalid action: {action}. Must be 'BUY' or 'SELL'"
        
        if quantity <= 0:
            return f"Invalid quantity: {quantity}. Must be > 0"
        
        if not symbol or len(symbol) == 0:
            return "Invalid symbol: empty"
        
        return None
