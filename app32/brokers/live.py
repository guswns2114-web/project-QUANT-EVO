"""
LiveBroker: LIVE 브로커 구현 (실제 거래용).

주의:
- 현재는 스텁 (구현되지 않음)
- 실제 API 키 설정 필요
- 환경: 라이브 거래 시에만 사용
"""

from typing import Optional, List
from .base import BrokerInterface, OrderResult, Position


class LiveBroker(BrokerInterface):
    """
    LIVE 브로커: 실제 거래소 API와 연동.
    
    TODO:
    - Interactive Brokers API 연동
    - Alpaca API 연동
    - E*TRADE API 연동
    """
    
    def __init__(self, api_key: str, api_secret: str):
        """
        Args:
            api_key: 브로커 API 키
            api_secret: 브로커 API 시크릿
        """
        raise NotImplementedError("LiveBroker is not yet implemented")
        self.api_key = api_key
        self.api_secret = api_secret
        # TODO: Initialize broker connection
    
    def place_order(self, 
                   symbol: str, 
                   action: str,
                   order_type: str = 'market',
                   quantity: int = 1,
                   price: Optional[float] = None,
                   **kwargs) -> OrderResult:
        """주문 생성 (실제 거래소에 전송)."""
        raise NotImplementedError("LiveBroker.place_order() not implemented")
    
    def cancel_order(self, order_id: str) -> OrderResult:
        """주문 취소 (실제 거래소에서 취소)."""
        raise NotImplementedError("LiveBroker.cancel_order() not implemented")
    
    def get_positions(self) -> List[Position]:
        """현재 포지션 조회 (실제 거래소에서)."""
        raise NotImplementedError("LiveBroker.get_positions() not implemented")
    
    def get_cash(self) -> float:
        """현금 잔액 조회 (실제 거래소에서)."""
        raise NotImplementedError("LiveBroker.get_cash() not implemented")
