"""
Data models for the Arbitrage Scanner.
"""

from dataclasses import dataclass
from typing import Optional
import datetime


@dataclass(frozen=True)
class StandardMarket:
    """Normalized market data structure."""
    platform: str        # 'POLY' or 'OPINION'
    market_id: str       # Platform specific ID
    title: str           # Cleaned title (lowercase, special chars removed)
    raw_title: str       # Original title (case preserved)
    price_yes: float     # 0.00 ~ 1.00
    price_no: float      # 0.00 ~ 1.00
    volume: float        # USD Volume
    volume: float        # USD Volume
    url: str             # Market Link
    end_date: Optional[datetime.datetime] = None  # Market expiration date
    
    def __post_init__(self):
        """Validate data after initialization."""
        assert 0.0 <= self.price_yes <= 1.0, f"Invalid price_yes: {self.price_yes}"
        assert 0.0 <= self.price_no <= 1.0, f"Invalid price_no: {self.price_no}"
        assert self.volume >= 0, f"Invalid volume: {self.volume}"


@dataclass
class ArbitrageOpportunity:
    """Arbitrage opportunity between two markets."""
    poly_market: StandardMarket
    opinion_market: StandardMarket
    similarity_score: float
    total_cost: float
    profit_margin: float
    roi_percent: float
    poly_side: str = "YES" # "YES" or "NO"
    opinion_side: str = "NO" # "YES" or "NO"
    strategy: str = "" # e.g. "Buy Poly YES ($0.4) + Buy Kalshi NO ($0.5)"
    
    def __str__(self):
        return (
            f"Arbitrage Opportunity (ROI: {self.roi_percent:.2f}%)\n"
            f"  Polymarket: {self.poly_market.title[:50]}...\n"
            f"  Opinion: {self.opinion_market.title[:50]}...\n"
            f"  Match Score: {self.similarity_score:.1f}\n"
            f"  Total Cost: ${self.total_cost:.4f}\n"
            f"  Profit: ${self.profit_margin:.4f}\n"
        )
