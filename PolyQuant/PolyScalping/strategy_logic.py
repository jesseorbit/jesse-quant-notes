from dataclasses import dataclass
from typing import Optional, Tuple
from loguru import logger
from config import config

@dataclass
class TradeSignal:
    action: str  # "BUY", "SELL" (but we only BUY to open or unwind)
    token_id: str
    price: float
    size: float
    reason: str

class PolyScalpingStrategy:
    def __init__(self):
        self.entry_prices = [
            config.entry_price_1,
            config.entry_price_2,
            config.entry_price_3
        ]
        self.shares_clip = config.shares_per_clip
        self.tp_spread = config.unwind_profit_spread
        self.sl_spread = config.stop_loss_spread
        
    def check_market(self, 
                    token_yes: str, 
                    token_no: str, 
                    ask_yes: float, 
                    ask_no: float, 
                    pos_yes: float, 
                    pos_no: float, 
                    avg_price_yes: float, 
                    avg_price_no: float) -> Optional[TradeSignal]:
                    
        """
        Determine if we should enter or unwind using Grid Logic.
        """
        
        # 1. Entry Logic - Grid
        # Level 1: Pos < Clip (0-10) -> Buy @ Entry 1
        # Level 2: Pos < 2*Clip (10-20) -> Buy @ Entry 2
        # Level 3: Pos < 3*Clip (20-30) -> Buy @ Entry 3
        # Max Exposure: 3 * Clip
        
        max_level = len(self.entry_prices)
        
        # Check YES Entry
        # Only enter YES if NO position is small (don't hedge lock for now, or assume separate buckets)
        if pos_no < 1.0:
            current_level_idx = int(pos_yes // self.shares_clip)
            # logger.debug(f"Strategy Check YES: Pos={pos_yes} Clip={self.shares_clip} Idx={current_level_idx}/{max_level}")
            
            if current_level_idx < max_level:
                target_price = self.entry_prices[current_level_idx]
                
                # Check if we are "full" for this level? 
                # Logic: If pos_yes is 0, idx=0. Buy.
                # If pos_yes is 10, idx=1. Buy @ Level 2 price.
                # We need to ensure we don't rebuy Level 1 if we are just slightly over?
                # The division handles it. 10 // 10 = 1.
                # But we might want margin? 
                # For safety: simpler check.
                
                if ask_yes > 0 and ask_yes <= target_price:
                    return TradeSignal("BUY", token_yes, ask_yes, self.shares_clip, f"Entry L{current_level_idx+1} YES @ {ask_yes}")

        # Check NO Entry
        if pos_yes < 1.0:
            current_level_idx = int(pos_no // self.shares_clip)
            if current_level_idx < max_level:
                target_price = self.entry_prices[current_level_idx]
                
                if ask_no > 0 and ask_no <= target_price:
                    return TradeSignal("BUY", token_no, ask_no, self.shares_clip, f"Entry L{current_level_idx+1} NO @ {ask_no}")
        
        # 2. Unwind Logic (Standard)
        # If we are Long YES
        if pos_yes >= 1.0:
            if ask_no > 0:
                cost_total = avg_price_yes + ask_no
                spread_pnl = 1.0 - cost_total
                
                if spread_pnl >= self.tp_spread:
                     return TradeSignal("BUY", token_no, ask_no, pos_yes, f"TP Unwind (+{spread_pnl:.2%})")
                
                if spread_pnl <= self.sl_spread:
                     return TradeSignal("BUY", token_no, ask_no, pos_yes, f"SL Unwind ({spread_pnl:.2%})")

        # If we are Long NO
        if pos_no >= 1.0:
            if ask_yes > 0:
                cost_total = avg_price_no + ask_yes
                spread_pnl = 1.0 - cost_total
                
                if spread_pnl >= self.tp_spread:
                     return TradeSignal("BUY", token_yes, ask_yes, pos_no, f"TP Unwind (+{spread_pnl:.2%})")
                
                if spread_pnl <= self.sl_spread:
                     return TradeSignal("BUY", token_yes, ask_yes, pos_no, f"SL Unwind ({spread_pnl:.2%})")
                     
        return None
