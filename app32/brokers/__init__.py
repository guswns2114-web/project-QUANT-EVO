"""
Broker adapters package.

모든 거래소 로직을 여기에 수집:
- BrokerInterface: 추상 인터페이스
- MockBroker: 시뮬레이션용 (개발/테스트)
- LiveBroker: 실제 거래용 (프로덕션)
"""

from .base import BrokerInterface, OrderResult, Position
from .mock import MockBroker
from .live import LiveBroker

__all__ = [
    'BrokerInterface',
    'OrderResult',
    'Position',
    'MockBroker',
    'LiveBroker',
]
