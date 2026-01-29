#!/usr/bin/env python3
"""
Parameter optimization for DCA unwind backtest.

Tests different combinations of:
- entry_threshold: When to enter (0.25, 0.30, 0.35, 0.40)
- hedge_threshold: When to hedge opposite side (0.60, 0.65, 0.70)
- dca_levels: DCA entry points
- force_unwind_minutes: When to force exit (3, 5, 7, 10)

Objective: Maximize expected value = win_rate × avg_win - (1 - win_rate) × avg_loss
"""

import sys
import time
from itertools import product
from dataclasses import dataclass, asdict
import pandas as pd

# Import from the main backtest script
sys.path.insert(0, '/Users/jessesung/PolyQuant')
from polymarket_15m_dca_unwind_backtest import (
    Config, iter_15m_markets, simulate_market
)

@dataclass
class OptimizationResult:
    entry_threshold: float
    hedge_threshold: float
    dca_levels: tuple
    force_unwind_minutes: int
    markets_entered: int
    win_rate: float
    avg_pnl: float
    median_pnl: float
    avg_win: float
    avg_loss: float
    max_loss: float
    expected_value: float
    forced_rate: float

def run_backtest_with_params(
    entry_threshold: float,
    hedge_threshold: float,
    dca_levels: tuple,
    force_unwind_minutes: int,
    max_markets: int = 200,
    days: int = 7,
    assets: tuple = ("btc",)
) -> OptimizationResult:
    """Run backtest with specific parameters."""
    
    cfg = Config(
        entry_threshold=entry_threshold,
        hedge_threshold=hedge_threshold,
        dca_levels=dca_levels,
        force_unwind_minutes=force_unwind_minutes,
        max_markets=max_markets,
        days_back=days,
        only_assets=assets
    )
    
    results = []
    n = 0
    
    for m in iter_15m_markets(cfg):
        n += 1
        try:
            res = simulate_market(m, cfg)
            results.append(asdict(res))
        except Exception:
            pass
        if n >= cfg.max_markets:
            break
    
    df = pd.DataFrame(results)
    entered = df[df["entered"] == True]
    
    if len(entered) == 0:
        return OptimizationResult(
            entry_threshold=entry_threshold,
            hedge_threshold=hedge_threshold,
            dca_levels=dca_levels,
            force_unwind_minutes=force_unwind_minutes,
            markets_entered=0,
            win_rate=0.0,
            avg_pnl=0.0,
            median_pnl=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            max_loss=0.0,
            expected_value=0.0,
            forced_rate=0.0
        )
    
    wins = entered[entered['pnl'] >= 0]
    losses = entered[entered['pnl'] < 0]
    
    win_rate = len(wins) / len(entered)
    avg_pnl = entered['pnl'].mean()
    median_pnl = entered['pnl'].median()
    avg_win = wins['pnl'].mean() if len(wins) > 0 else 0.0
    avg_loss = losses['pnl'].mean() if len(losses) > 0 else 0.0
    max_loss = entered['pnl'].min()
    forced_rate = entered['forced'].mean()
    
    # Expected value = win_rate × avg_win + (1 - win_rate) × avg_loss
    expected_value = win_rate * avg_win + (1 - win_rate) * avg_loss
    
    return OptimizationResult(
        entry_threshold=entry_threshold,
        hedge_threshold=hedge_threshold,
        dca_levels=dca_levels,
        force_unwind_minutes=force_unwind_minutes,
        markets_entered=len(entered),
        win_rate=win_rate,
        avg_pnl=avg_pnl,
        median_pnl=median_pnl,
        avg_win=avg_win,
        avg_loss=avg_loss,
        max_loss=max_loss,
        expected_value=expected_value,
        forced_rate=forced_rate
    )

def main():
    print("="*60)
    print("PARAMETER OPTIMIZATION FOR DCA UNWIND STRATEGY")
    print("="*60)
    print("\nTesting parameter combinations...")
    print("This will take several minutes...\n")
    
    # Parameter grid
    entry_thresholds = [0.25, 0.30, 0.35, 0.40]
    hedge_thresholds = [0.60, 0.65, 0.70]
    dca_level_sets = [
        (0.25, 0.15, 0.05),  # Original
        (0.20, 0.10),        # Fewer levels, more aggressive
        (0.30, 0.20, 0.10),  # More conservative
        (0.25, 0.15),        # Medium
    ]
    force_unwind_times = [3, 5, 7, 10]
    
    total_combinations = (
        len(entry_thresholds) * 
        len(hedge_thresholds) * 
        len(dca_level_sets) * 
        len(force_unwind_times)
    )
    
    print(f"Total combinations to test: {total_combinations}\n")
    
    results = []
    count = 0
    start_time = time.time()
    
    for entry, hedge, dca, force_time in product(
        entry_thresholds,
        hedge_thresholds,
        dca_level_sets,
        force_unwind_times
    ):
        count += 1
        print(f"[{count}/{total_combinations}] Testing: entry={entry}, hedge={hedge}, "
              f"dca={dca}, force={force_time}min", end="")
        
        result = run_backtest_with_params(
            entry_threshold=entry,
            hedge_threshold=hedge,
            dca_levels=dca,
            force_unwind_minutes=force_time,
            max_markets=200,
            days=7,
            assets=("btc",)
        )
        
        results.append(asdict(result))
        print(f" -> EV={result.expected_value:.4f}, WR={result.win_rate:.3f}, "
              f"Entered={result.markets_entered}")
    
    # Save all results
    df = pd.DataFrame(results)
    df.to_csv("optimization_results.csv", index=False)
    
    # Sort by expected value
    df_sorted = df.sort_values('expected_value', ascending=False)
    
    # Display top 10
    print("\n" + "="*60)
    print("TOP 10 PARAMETER COMBINATIONS (by Expected Value)")
    print("="*60)
    
    for i, row in df_sorted.head(10).iterrows():
        print(f"\n#{df_sorted.index.get_loc(i) + 1}")
        print(f"  Entry: {row['entry_threshold']:.2f} | Hedge: {row['hedge_threshold']:.2f} | "
              f"DCA: {row['dca_levels']} | Force: {row['force_unwind_minutes']}min")
        print(f"  Expected Value: {row['expected_value']:.4f}")
        print(f"  Win Rate: {row['win_rate']:.1%} | Avg PnL: {row['avg_pnl']:.4f}")
        print(f"  Avg Win: {row['avg_win']:.4f} | Avg Loss: {row['avg_loss']:.4f}")
        print(f"  Markets Entered: {row['markets_entered']} | Forced: {row['forced_rate']:.1%}")
    
    # Best result
    best = df_sorted.iloc[0]
    print("\n" + "="*60)
    print("BEST PARAMETERS")
    print("="*60)
    print(f"Entry Threshold: {best['entry_threshold']}")
    print(f"Hedge Threshold: {best['hedge_threshold']}")
    print(f"DCA Levels: {best['dca_levels']}")
    print(f"Force Unwind: {best['force_unwind_minutes']} minutes")
    print(f"\nExpected Value: {best['expected_value']:.4f} USDC per trade")
    print(f"Win Rate: {best['win_rate']:.1%}")
    print(f"Avg Win: {best['avg_win']:.4f} USDC")
    print(f"Avg Loss: {best['avg_loss']:.4f} USDC")
    print(f"Markets Entered: {best['markets_entered']}/200")
    
    elapsed = time.time() - start_time
    print(f"\nTotal time: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
    print(f"Saved all results to: optimization_results.csv")

if __name__ == "__main__":
    main()
