#!/usr/bin/env python3
"""
Advanced DCA Unwind Strategy with Smart Refinements

Key improvements:
1. DCA time cutoff: Only DCA in first 5 minutes (avoid chasing bad trades)
2. Time-aware exit rules:
   - If T > 5m: Exit only when locked_pnl >= profit_buffer
   - If T ≤ 5m and locked_pnl >= 0: Exit (lock in any profit)
   - If T ≤ 5m and locked_pnl < 0: Skip hedge (don't buy expensive insurance)
3. Dynamic hedging: Hedge based on average cost, not fixed 0.65 threshold
   - Only hedge when it improves your position
   - Calculate if hedging at current price makes mathematical sense

This is a disciplined mean-reversion strategy that:
- Enters aggressively (0.35)
- DCA's early (first 5 min only)
- Hedges intelligently (based on math, not fixed price)
- Exits smartly (time-aware, avoids expensive insurance near expiry)
"""

from __future__ import annotations
import argparse
import time
import requests
import pandas as pd
import numpy as np
import re
from dataclasses import dataclass, asdict

CLOB = "https://clob.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"

ASSET_RE = re.compile(r"^(btc|eth|sol|xrp)-updown-15m-(\\d+)$", re.IGNORECASE)

@dataclass
class Config:
    entry_threshold: float = 0.35
    dca_levels: tuple[float, ...] = (0.25, 0.15, 0.05)
    dca_time_cutoff_minutes: float = 5.0  # NEW: Only DCA in first 5 minutes
    profit_buffer: float = 0.01  # NEW: Exit when profit > $0.01 (any profit)
    size_per_leg: int = 100
    force_unwind_minutes: int = 5
    window_pre_minutes: int = 60
    window_post_minutes: int = 15
    fidelity_minutes: int = 1
    slippage_bps: float = 10.0
    fee_bps: float = 0.0
    max_markets: int = 100  # ~96 markets per day for one asset
    days_back: int = 1  # Focus on most recent 1 day
    only_assets: tuple[str, ...] = ("btc",)  # Focus on BTC only for daily profit check

def fetch_market_by_slug(slug: str) -> dict | None:
    """Fetch a single market from Gamma API by slug."""
    url = f"{GAMMA}/markets/slug/{slug}"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def iter_15m_markets(cfg: Config):
    """Generate 15m markets by epoch iteration (Gamma API approach)."""
    from datetime import datetime, timedelta, timezone
    
    days_back = cfg.days_back
    now = datetime.now(timezone.utc)
    start_dt = now - timedelta(days=days_back)
    
    start_epoch = int(start_dt.timestamp())
    start_epoch = (start_epoch // 900) * 900
    
    end_epoch = int(now.timestamp())
    end_epoch = (end_epoch // 900) * 900
    
    found = 0
    not_found = 0
    
    print(f"Scanning {days_back} days of 15m markets...")
    print(f"Epoch range: {start_epoch} to {end_epoch}")
    
    for asset in cfg.only_assets:
        for epoch in range(start_epoch, end_epoch + 900, 900):
            slug = f"{asset}-updown-15m-{epoch}"
            
            market = fetch_market_by_slug(slug)
            
            if market is None:
                not_found += 1
                continue
            
            clob_token_ids = market.get("clobTokenIds", [])
            if isinstance(clob_token_ids, str):
                import json
                try:
                    clob_token_ids = json.loads(clob_token_ids)
                except:
                    continue
            
            if len(clob_token_ids) < 2:
                continue
            
            tokens = [
                {"token_id": clob_token_ids[0], "outcome": "Yes"},
                {"token_id": clob_token_ids[1], "outcome": "No"}
            ]
            
            yield {
                "asset": asset,
                "slug": slug,
                "epoch": epoch,
                "condition_id": market.get("id"),
                "tokens": tokens,
                "active": market.get("active", False),
                "closed": market.get("closed", True),
            }
            
            found += 1
            if found % 10 == 0:
                print(f"  Found {found} markets, {not_found} not found")
            
            if found >= cfg.max_markets:
                return
            
            time.sleep(0.3)

def get_prices_history(token_id: str, start_ts: int, end_ts: int, fidelity_min: int) -> pd.DataFrame:
    """Fetch price history from CLOB API."""
    url = (f"{CLOB}/prices-history"
           f"?market={token_id}"
           f"&fidelity={fidelity_min}"
           f"&startTs={start_ts}"
           f"&endTs={end_ts}")
    
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        j = r.json()
        
        if isinstance(j, dict) and "history" in j:
            hist = j["history"]
        else:
            hist = j
        
        if not hist:
            return pd.DataFrame(columns=["price"])
        
        df = pd.DataFrame(hist)
        if "t" in df.columns and "p" in df.columns:
            df["ts"] = pd.to_datetime(df["t"], unit="s", utc=True)
            df = df.rename(columns={"p": "price"})
            df = df[["ts", "price"]].set_index("ts").sort_index()
        else:
            return pd.DataFrame(columns=["price"])
        
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df = df.dropna()
        return df
    
    except Exception as e:
        print(f"    Error fetching price history: {e}")
        return pd.DataFrame(columns=["price"])

@dataclass
class TradeResult:
    slug: str
    asset: str
    epoch: int
    entered: bool
    unwinded: bool
    forced: bool
    entry_side: str | None
    shares_yes: int
    shares_no: int
    avg_cost_yes: float
    avg_cost_no: float
    total_cost: float
    locked_payout: float
    pnl: float
    max_gross_exposure: float
    hedged: bool  # NEW: Track if we hedged
    dca_count: int  # NEW: Track how many DCA levels hit
    minutes_to_unwind: float | None

def simulate_market(market: dict, cfg: Config) -> TradeResult:
    """Simulate trading strategy with advanced refinements."""
    tok_map = {t.get("outcome","").lower(): t.get("token_id") for t in market["tokens"]}
    if "yes" not in tok_map or "no" not in tok_map:
        return TradeResult(market["slug"], market["asset"], market["epoch"], False, False, False,
                           None, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, 0, None)

    yes_id, no_id = tok_map["yes"], tok_map["no"]

    start_ts = market["epoch"] - cfg.window_pre_minutes*60
    end_ts = market["epoch"] + cfg.window_post_minutes*60
    yes = get_prices_history(yes_id, start_ts, end_ts, cfg.fidelity_minutes).rename(columns={"price":"yes"})
    no  = get_prices_history(no_id,  start_ts, end_ts, cfg.fidelity_minutes).rename(columns={"price":"no"})

    df = yes.join(no, how="inner").dropna()
    if df.empty:
        return TradeResult(market["slug"], market["asset"], market["epoch"], False, False, False,
                           None, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, 0, None)

    def buy(price: float) -> float:
        p = price * (1.0 + cfg.slippage_bps/10000.0)
        p = min(max(p, 0.0001), 0.9999)
        return p

    fee_mult = cfg.fee_bps/10000.0

    shares_yes = shares_no = 0
    cost_yes = cost_no = 0.0
    entry_side = None
    entry_time = None
    entered = False
    unwinded = False
    forced = False
    hedged = False
    dca_count = 0
    max_gross_exposure = 0.0
    unwind_time = None

    dca_used_yes = set()
    dca_used_no = set()

    market_end = pd.to_datetime(market["epoch"] + 15*60, unit="s", utc=True)

    for ts, row in df.iterrows():
        yes_p, no_p = float(row["yes"]), float(row["no"])

        gross = yes_p*shares_yes + no_p*shares_no
        max_gross_exposure = max(max_gross_exposure, gross)

        minutes_left = (market_end - ts).total_seconds()/60.0
        
        # NEW: Calculate time since entry
        minutes_since_entry = 0.0
        if entry_time is not None:
            minutes_since_entry = (ts - entry_time).total_seconds() / 60.0

        # NEW: Calculate profit if we unwind now
        def calc_profit_if_unwind() -> tuple[float, float, int, int]:
            target = max(shares_yes, shares_no)
            add_yes = target - shares_yes
            add_no  = target - shares_no
            
            add_cost_yes = add_yes * buy(yes_p)
            add_cost_no  = add_no  * buy(no_p)

            total_cost = cost_yes + cost_no + add_cost_yes + add_cost_no
            locked_payout = target * 1.0
            fees = total_cost * fee_mult
            pnl = locked_payout - total_cost - fees
            
            return pnl, total_cost, add_yes, add_no

        # Entry logic
        if not entered:
            if yes_p <= cfg.entry_threshold or no_p <= cfg.entry_threshold:
                entered = True
                entry_time = ts
                if yes_p <= no_p:
                    entry_side = "yes"
                    shares_yes += cfg.size_per_leg
                    cost_yes += cfg.size_per_leg * buy(yes_p)
                else:
                    entry_side = "no"
                    shares_no += cfg.size_per_leg
                    cost_no += cfg.size_per_leg * buy(no_p)
            continue

        # NEW: DCA logic with time cutoff (only in first 5 minutes)
        if minutes_since_entry <= cfg.dca_time_cutoff_minutes:
            if entry_side == "yes":
                for lvl in cfg.dca_levels:
                    if yes_p <= lvl and lvl not in dca_used_yes:
                        dca_used_yes.add(lvl)
                        shares_yes += cfg.size_per_leg
                        cost_yes += cfg.size_per_leg * buy(yes_p)
                        dca_count += 1
            elif entry_side == "no":
                for lvl in cfg.dca_levels:
                    if no_p <= lvl and lvl not in dca_used_no:
                        dca_used_no.add(lvl)
                        shares_no += cfg.size_per_leg
                        cost_no += cfg.size_per_leg * buy(no_p)
                        dca_count += 1

        # NEW: Dynamic hedging based on average cost
        # Only hedge if it makes mathematical sense
        if not hedged:
            avg_yes_cost = (cost_yes / shares_yes) if shares_yes > 0 else 0
            avg_no_cost = (cost_no / shares_no) if shares_no > 0 else 0
            
            # If we have YES position, consider hedging with NO
            if entry_side == "yes" and shares_no == 0:
                # Hedge if: avg_yes_cost + current_no_price < 1.0 (profitable)
                # This means we can lock in profit by hedging now
                potential_total_cost = avg_yes_cost + buy(no_p)
                if potential_total_cost < 1.0:  # Would be profitable
                    shares_no += shares_yes  # Match position size
                    cost_no += shares_yes * buy(no_p)
                    hedged = True
            
            # If we have NO position, consider hedging with YES
            elif entry_side == "no" and shares_yes == 0:
                potential_total_cost = avg_no_cost + buy(yes_p)
                if potential_total_cost < 1.0:  # Would be profitable
                    shares_yes += shares_no  # Match position size
                    cost_yes += shares_no * buy(yes_p)
                    hedged = True

        # TIME-AWARE EXIT/UNWIND LOGIC
        # Calculate potential profit if we unwind now
        pnl, total_cost, add_yes, add_no = calc_profit_if_unwind()
        
        # Rule 1: If time remaining > 5 minutes (T > 5m)
        # Only unwind if locked_pnl >= +buffer
        if minutes_left > cfg.force_unwind_minutes:
            if pnl >= cfg.profit_buffer:
                # Lock in profit immediately
                if add_yes > 0:
                    cost_yes += add_yes * buy(yes_p)
                    shares_yes += add_yes
                if add_no > 0:
                    cost_no += add_no * buy(no_p)
                    shares_no += add_no
                unwinded = True
                unwind_time = ts
                break
        
        # Rule 2: If time remaining ≤ 5 minutes (T ≤ 5m)
        else:
            # If locked_pnl >= 0: Unwind (lock it in)
            if pnl >= 0:
                if add_yes > 0:
                    cost_yes += add_yes * buy(yes_p)
                    shares_yes += add_yes
                if add_no > 0:
                    cost_no += add_no * buy(no_p)
                    shares_no += add_no
                unwinded = True
                forced = True
                unwind_time = ts
                break
            # If locked_pnl < 0: Do NOT unwind (skip the hedge)
            # Don't buy expensive insurance into expiry
            else:
                # Just let it ride - don't complete the set
                # We'll handle final accounting at the end
                pass

    # Final accounting
    if (shares_yes > 0 or shares_no > 0) and not unwinded:
        ts = df.index[-1]
        yes_p, no_p = float(df.iloc[-1]["yes"]), float(df.iloc[-1]["no"])
        
        # Calculate if completing the set would be profitable
        target = max(shares_yes, shares_no)
        add_yes = target - shares_yes
        add_no  = target - shares_no
        
        add_cost_yes = add_yes * buy(yes_p)
        add_cost_no  = add_no  * buy(no_p)
        
        potential_total_cost = cost_yes + cost_no + add_cost_yes + add_cost_no
        locked_payout = target * 1.0
        fees = potential_total_cost * fee_mult
        potential_pnl = locked_payout - potential_total_cost - fees
        
        # Only complete the set if it would be profitable (or break-even)
        # Otherwise, let the losing side expire worthless
        if potential_pnl >= 0:
            if add_yes > 0:
                cost_yes += add_yes * buy(yes_p)
                shares_yes += add_yes
            if add_no > 0:
                cost_no += add_no * buy(no_p)
                shares_no += add_no
            unwinded = True
            forced = True
            unwind_time = ts
        else:
            # Don't complete the set - let the losing side expire
            # The PnL will reflect the loss from the side that expires worthless
            forced = True  # Mark as forced since we hit expiry
            unwind_time = ts

    avg_cost_yes = (cost_yes / shares_yes) if shares_yes else 0.0
    avg_cost_no  = (cost_no / shares_no) if shares_no else 0.0
    total_cost = cost_yes + cost_no
    
    # Calculate payout based on what actually happened
    # If we completed the set (unwinded), we get max(shares_yes, shares_no)
    # If we didn't complete the set, we need to determine which side won
    if unwinded:
        locked_payout = max(shares_yes, shares_no) * 1.0
    else:
        # Position expired incomplete - assume worst case (losing side)
        # In reality, one side would pay out $1, but we don't know which
        # For backtest purposes, we'll assume the side we're NOT holding wins
        # This means our shares are worth $0
        locked_payout = 0.0
    
    fees = total_cost * fee_mult
    pnl = locked_payout - total_cost - fees

    return TradeResult(
        slug=market["slug"],
        asset=market["asset"],
        epoch=market["epoch"],
        entered=entered,
        unwinded=unwinded,
        forced=forced,
        entry_side=entry_side,
        shares_yes=shares_yes,
        shares_no=shares_no,
        avg_cost_yes=float(avg_cost_yes),
        avg_cost_no=float(avg_cost_no),
        total_cost=float(total_cost),
        locked_payout=float(locked_payout),
        pnl=float(pnl),
        max_gross_exposure=float(max_gross_exposure),
        hedged=hedged,
        dca_count=dca_count,
        minutes_to_unwind=None,
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-markets", type=int, default=100, help="Max markets to scan (default: 100, ~96 per day)")
    ap.add_argument("--days", type=int, default=1, help="Days back to scan (default: 1)")
    ap.add_argument("--dca-cutoff", type=float, default=5.0, help="DCA time cutoff in minutes (default: 5)")
    ap.add_argument("--profit-buffer", type=float, default=0.01, help="Profit buffer in USDC (default: 0.01)")
    ap.add_argument("--slippage-bps", type=float, default=10.0)
    ap.add_argument("--fee-bps", type=float, default=0.0)
    ap.add_argument("--out", type=str, default="backtest_advanced.csv")
    ap.add_argument("--assets", type=str, default="btc", help="Comma-separated assets (default: btc)")
    args = ap.parse_args()

    cfg = Config(
        max_markets=args.max_markets,
        days_back=args.days,
        dca_time_cutoff_minutes=args.dca_cutoff,
        profit_buffer=args.profit_buffer,
        slippage_bps=args.slippage_bps,
        fee_bps=args.fee_bps,
        only_assets=tuple([a.strip().lower() for a in args.assets.split(",") if a.strip()])
    )

    print("="*60)
    print("ADVANCED DCA UNWIND BACKTEST")
    print("="*60)
    print(f"Entry threshold: {cfg.entry_threshold}")
    print(f"DCA time cutoff: {cfg.dca_time_cutoff_minutes} minutes")
    print(f"Profit buffer: ${cfg.profit_buffer}")
    print(f"DCA levels: {cfg.dca_levels}")
    print(f"Dynamic hedging: Based on average cost")
    print("="*60)

    results = []
    n = 0
    t0 = time.time()

    for m in iter_15m_markets(cfg):
        n += 1
        print(f"[{n}] {m['slug']} closed={m['closed']} active={m['active']}")
        try:
            res = simulate_market(m, cfg)
            results.append(asdict(res))
        except Exception as e:
            print(f"  !! error: {e}")
        if n >= cfg.max_markets:
            break

    df = pd.DataFrame(results)
    df.to_csv(args.out, index=False)

    # Summary
    entered = df[df["entered"] == True]
    print("\n=== Summary ===")
    print(f"markets scanned: {len(df)} | entered: {len(entered)}")
    if len(entered):
        hedged_trades = entered[entered['hedged'] == True]
        print(f"hedged trades: {len(hedged_trades)}/{len(entered)} ({len(hedged_trades)/len(entered):.1%})")
        print(f"avg DCA count: {entered['dca_count'].mean():.2f}")
        print(f"win-rate (pnl>=0): {(entered['pnl']>=0).mean():.3f}")
        print(f"avg pnl: {entered['pnl'].mean():.4f} | median pnl: {entered['pnl'].median():.4f}")
        print(f"avg win: {entered.loc[entered['pnl']>=0,'pnl'].mean():.4f}")
        print(f"avg loss: {entered.loc[entered['pnl']<0,'pnl'].mean():.4f}")
        print(f"max loss: {entered['pnl'].min():.4f}")
        print(f"forced unwind rate: {entered['forced'].mean():.3f}")
        
        # Expected value
        wins = entered[entered['pnl'] >= 0]
        losses = entered[entered['pnl'] < 0]
        win_rate = len(wins) / len(entered)
        avg_win = wins['pnl'].mean() if len(wins) > 0 else 0
        avg_loss = losses['pnl'].mean() if len(losses) > 0 else 0
        ev = win_rate * avg_win + (1 - win_rate) * avg_loss
        print(f"\nExpected Value: {ev:.4f} USDC per trade")
        
        # Daily profit summary
        total_pnl = entered['pnl'].sum()
        print("\n" + "="*60)
        print("DAILY PROFIT SUMMARY (Most Recent 1 Day)")
        print("="*60)
        print(f"Total Daily Profit: ${total_pnl:.2f} USDC")
        print(f"Total Markets Traded: {len(entered)}")
        print(f"Profit per Market: ${total_pnl/len(entered):.4f} USDC")
        print(f"Expected Hourly Profit: ${total_pnl/24:.4f} USDC/hour")
        print(f"Expected Daily Profit (96 markets): ${ev * 96:.2f} USDC")
        print("="*60)

    print(f"\nSaved -> {args.out}")
    print(f"Elapsed: {time.time()-t0:.1f}s")

if __name__ == "__main__":
    main()
