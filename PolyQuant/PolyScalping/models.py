from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

@dataclass
class Market:
    """Represents a Polymarket market (binary)."""
    id: str
    question: str
    condition_id: str
    slug: str
    end_date_iso: str
    tokens: List[str]  # [TokenID_YES, TokenID_NO] usually
    outcomes: List[str] # ["YES", "NO"]
    
    # Live data
    best_bid_yes: float = 0.0
    best_ask_yes: float = 0.0
    best_bid_no: float = 0.0
    best_ask_no: float = 0.0
    
    last_updated: float = 0.0

@dataclass
class Position:
    """Tracks current holdings for a specific market."""
    market_id: str
    shares_yes: float = 0.0
    shares_no: float = 0.0
    avg_price_yes: float = 0.0
    avg_price_no: float = 0.0
    
    entry_timestamp: float = 0.0
    first_fill_timestamp: Optional[float] = None
    
    @property
    def total_exposure(self) -> float:
        return (self.shares_yes * self.avg_price_yes) + (self.shares_no * self.avg_price_no)

@dataclass
class ActiveOrder:
    """Tracks an open order placed by the bot."""
    order_id: str
    market_id: str
    token_id: str
    side: OrderSide
    price: float
    size: float
    timestamp: float
    is_dca: bool = False  # True if part of the grid/DCA logic
