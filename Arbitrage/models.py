"""
Data models for the Arbitrage Scanner.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class StandardMarket:
    """Normalized market data structure."""
    platform: str        # 'POLY', 'KALSHI', etc.
    market_id: str       # Platform specific ID
    title: str           # Cleaned title (lowercase, special chars removed)
    price_yes: float     # 0.00 ~ 1.00
    price_no: float      # 0.00 ~ 1.00
    volume: float        # USD Volume
    url: str             # Market Link
    
    def __post_init__(self):
        """Validate data after initialization."""
        assert 0.0 <= self.price_yes <= 1.0, f"Invalid price_yes: {self.price_yes}"
        assert 0.0 <= self.price_no <= 1.0, f"Invalid price_no: {self.price_no}"
        assert self.volume >= 0, f"Invalid volume: {self.volume}"


@dataclass
class ArbitrageOpportunity:
    """Arbitrage opportunity between two markets."""

    poly_market: StandardMarket
    counter_market: StandardMarket
    similarity_score: float
    total_cost: float
    profit_margin: float
    roi_percent: float

    def __str__(self):
        return (
            f"Arbitrage Opportunity (ROI: {self.roi_percent:.2f}%)\n"
            f"  Primary: {self.poly_market.title[:50]}...\n"
            f"  Counter: {self.counter_market.title[:50]}...\n"
            f"  Match Score: {self.similarity_score:.1f}\n"
            f"  Total Cost: ${self.total_cost:.4f}\n"
            f"  Profit: ${self.profit_margin:.4f}\n"
        )
