#!/usr/bin/env python3
"""
Polymarket 15m Up/Down DCA + Unwind Backtest (BTC/ETH/SOL/XRP)

What this does
- Pulls CLOB markets via GET https://clob.polymarket.com/markets?next_cursor=...
- Filters market_slug that matches: {asset}-updown-15m-{epoch}
- For each market, pulls BOTH outcome token price histories via:
    GET https://clob.polymarket.com/prices-history?market=<token_id>&interval=<fidelity>&fidelity=<minutes>&startTs=<unix>&endTs=<unix>

- Simulates your strategy:
  1) Buy 100 shares when either side <= 0.35
  2) If you bought YES, then when NO <= 0.65 buy 100 shares (or unwind logic generalized)
  3) If price continues against you, DCA additional 100 shares at 0.25, 0.15, 0.05 (configurable)
  4) When opportunity arises to loc
  k >= 0 profit (after fees/slippage), buy the opposite side with equal shares to unwind
  5) If no opportunity and remaining time <= 5 min, force unwind at current prices

Important realism notes
- This backtester uses *price history* (mid) and approximates execution using slippage_bps (default 10 bps).
  If you want full realism, replace the execution model with order book snapshots (harder).
- 15m markets are short-dated; behavior is often *not* mean-reverting near expiry.
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

ASSET_RE = re.compile(r"^(btc|eth|sol|xrp)-updown-15m-(\d+)$", re.IGNORECASE)

@dataclass
class Config:
    entry_threshold: float = 0.35
    hedge_threshold: float = 0.65
    dca_levels: tuple[float, ...] = (0.25, 0.15, 0.05)
    size_per_leg: int = 100
    force_unwind_minutes: int = 5
    window_pre_minutes: int = 60
    window_post_minutes: int = 15
    fidelity_minutes: int = 1
    slippage_bps: float = 10.0          # execution price = mid*(1+slippage_bps/10000) for buys
    fee_bps: float = 0.0                # set if CLOB fees apply
    max_markets: int = 300              # safety cap
    days_back: int = 7                  # days to scan backwards
    only_assets: tuple[str, ...] = ("btc","eth","sol","xrp")

def fetch_market_by_slug(slug: str) -> dict | None:
    """
    Fetch a single market from Gamma API by slug.
    Returns None if market doesn't exist (404).
    """
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
    """
    Generate 15m markets by epoch iteration (Gamma API approach).
    BTC/ETH/SOL/XRP 15m markets are NOT in CLOB /markets endpoint,
    so we generate epochs and fetch directly from Gamma API.
    """
    from datetime import datetime, timedelta, timezone
    
    # Generate epochs for last N days
    # Use days from config (default 7 to avoid too many API calls)
    days_back = cfg.days_back
    now = datetime.now(timezone.utc)
    start_dt = now - timedelta(days=days_back)
    
    start_epoch = int(start_dt.timestamp())
    start_epoch = (start_epoch // 900) * 900  # Round to 15-min boundary
    
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
            
            # Extract token IDs from clobTokenIds
            clob_token_ids = market.get("clobTokenIds", [])
            if isinstance(clob_token_ids, str):
                import json
                try:
                    clob_token_ids = json.loads(clob_token_ids)
                except:
                    continue
            
            if len(clob_token_ids) < 2:
                continue
            
            # Map to tokens format expected by simulate_market
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
            
            time.sleep(0.3)  # Rate limiting

def get_prices_history(token_id: str, start_ts: int, end_ts: int, fidelity_min: int) -> pd.DataFrame:
    """
    Fetch price history from CLOB API.
    API returns list of {t: timestamp_sec, p: price} objects.
    """
    url = (f"{CLOB}/prices-history"
           f"?market={token_id}"
           f"&fidelity={fidelity_min}"
           f"&startTs={start_ts}"
           f"&endTs={end_ts}")
    
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        j = r.json()
        
        # Handle response format: list of {t, p} or dict with "history"
        if isinstance(j, dict) and "history" in j:
            hist = j["history"]
        else:
            hist = j
        
        if not hist:
            return pd.DataFrame(columns=["price"])
        
        # Parse {t: timestamp_sec, p: price} format
        df = pd.DataFrame(hist)
        if "t" in df.columns and "p" in df.columns:
            df["ts"] = pd.to_datetime(df["t"], unit="s", utc=True)
            df = df.rename(columns={"p": "price"})
            df = df[["ts", "price"]].set_index("ts").sort_index()
        else:
            # Fallback for unexpected format
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
    minutes_to_unwind: float | None

def simulate_market(market: dict, cfg: Config) -> TradeResult:
    # Identify YES/NO tokens
    tok_map = {t.get("outcome","").lower(): t.get("token_id") for t in market["tokens"]}
    if "yes" not in tok_map or "no" not in tok_map:
        # Some up/down markets might use "Up"/"Down" etc; normalize:
        # We'll assume outcomes are "Yes"/"No" for these markets; otherwise bail.
        return TradeResult(market["slug"], market["asset"], market["epoch"], False, False, False,
                           None, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None)

    yes_id, no_id = tok_map["yes"], tok_map["no"]

    start_ts = market["epoch"] - cfg.window_pre_minutes*60
    end_ts = market["epoch"] + cfg.window_post_minutes*60
    yes = get_prices_history(yes_id, start_ts, end_ts, cfg.fidelity_minutes).rename(columns={"price":"yes"})
    no  = get_prices_history(no_id,  start_ts, end_ts, cfg.fidelity_minutes).rename(columns={"price":"no"})

    df = yes.join(no, how="inner").dropna()
    if df.empty:
        return TradeResult(market["slug"], market["asset"], market["epoch"], False, False, False,
                           None, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None)

    # Execution helper
    def buy(price: float) -> float:
        # Buy at worse than mid
        p = price * (1.0 + cfg.slippage_bps/10000.0)
        p = min(max(p, 0.0001), 0.9999)
        return p

    fee_mult = cfg.fee_bps/10000.0

    # Position state
    shares_yes = shares_no = 0
    cost_yes = cost_no = 0.0
    entry_side = None
    entered = False
    unwinded = False
    forced = False
    max_gross_exposure = 0.0
    unwind_time = None

    # Track which DCA levels already used (per-side)
    dca_used_yes = set()
    dca_used_no = set()

    # Determine market end time approximation: epoch+15m
    market_end = pd.to_datetime(market["epoch"] + 15*60, unit="s", utc=True)

    for ts, row in df.iterrows():
        yes_p, no_p = float(row["yes"]), float(row["no"])

        # Gross exposure (cash at risk in open single-sided position) approx = current mid * shares
        gross = yes_p*shares_yes + no_p*shares_no
        max_gross_exposure = max(max_gross_exposure, gross)

        # Time remaining to end
        minutes_left = (market_end - ts).total_seconds()/60.0

        # Helper: compute locked PnL if we unwind now (equalize shares by buying opposite)
        def locked_pnl_if_unwind_now() -> tuple[float,float,float,int,int,float,float]:
            # Determine target equal shares = max(shares_yes, shares_no)
            target = max(shares_yes, shares_no)
            add_yes = target - shares_yes
            add_no  = target - shares_no
            # execute buys at current price for needed side(s)
            add_cost_yes = add_yes * buy(yes_p)
            add_cost_no  = add_no  * buy(no_p)

            total_cost = cost_yes + cost_no + add_cost_yes + add_cost_no
            locked_payout = target * 1.0  # 1 USDC per pair at resolution
            # apply fees on traded notional (approx): total_cost * fee_mult
            fees = total_cost * fee_mult
            pnl = locked_payout - total_cost - fees
            return pnl, total_cost, locked_payout, target, add_yes, add_no, fees

        # Force unwind if near end and we have any open exposure
        if minutes_left <= cfg.force_unwind_minutes and (shares_yes > 0 or shares_no > 0):
            pnl, total_cost, locked_payout, target, add_yes, add_no, fees = locked_pnl_if_unwind_now()
            # execute
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

        # If not entered, check entry
        if not entered:
            if yes_p <= cfg.entry_threshold or no_p <= cfg.entry_threshold:
                entered = True
                if yes_p <= no_p:
                    entry_side = "yes"
                    shares_yes += cfg.size_per_leg
                    cost_yes += cfg.size_per_leg * buy(yes_p)
                else:
                    entry_side = "no"
                    shares_no += cfg.size_per_leg
                    cost_no += cfg.size_per_leg * buy(no_p)
            continue

        # After entered, DCA logic on the entry_side (your described version)
        if entry_side == "yes":
            for lvl in cfg.dca_levels:
                if yes_p <= lvl and lvl not in dca_used_yes:
                    dca_used_yes.add(lvl)
                    shares_yes += cfg.size_per_leg
                    cost_yes += cfg.size_per_leg * buy(yes_p)
        elif entry_side == "no":
            for lvl in cfg.dca_levels:
                if no_p <= lvl and lvl not in dca_used_no:
                    dca_used_no.add(lvl)
                    shares_no += cfg.size_per_leg
                    cost_no += cfg.size_per_leg * buy(no_p)

        # Optional: small "hedge at 0.65" rule (your step 2) for the opposite side, only once
        # We'll implement: if we have exactly one leg and opposite <= hedge_threshold, buy one leg opposite.
        if entry_side == "yes" and shares_no == 0 and no_p <= cfg.hedge_threshold:
            shares_no += cfg.size_per_leg
            cost_no += cfg.size_per_leg * buy(no_p)
        if entry_side == "no" and shares_yes == 0 and yes_p <= cfg.hedge_threshold:
            shares_yes += cfg.size_per_leg
            cost_yes += cfg.size_per_leg * buy(yes_p)

        # Check if we can unwind for >=0 profit (rule 4)
        pnl, total_cost, locked_payout, target, add_yes, add_no, fees = locked_pnl_if_unwind_now()
        if pnl >= 0:
            # execute unwind now
            if add_yes > 0:
                cost_yes += add_yes * buy(yes_p)
                shares_yes += add_yes
            if add_no > 0:
                cost_no += add_no * buy(no_p)
                shares_no += add_no
            unwinded = True
            unwind_time = ts
            break

    # Final accounting (if never unwinded, assume forced at last available timestamp)
    if (shares_yes > 0 or shares_no > 0) and not unwinded:
        ts = df.index[-1]
        yes_p, no_p = float(df.iloc[-1]["yes"]), float(df.iloc[-1]["no"])
        # force unwind
        def buy(price: float) -> float:
            p = price * (1.0 + cfg.slippage_bps/10000.0)
            p = min(max(p, 0.0001), 0.9999)
            return p
        target = max(shares_yes, shares_no)
        add_yes = target - shares_yes
        add_no  = target - shares_no
        if add_yes > 0:
            cost_yes += add_yes * buy(yes_p)
            shares_yes += add_yes
        if add_no > 0:
            cost_no += add_no * buy(no_p)
            shares_no += add_no
        unwinded = True
        forced = True
        unwind_time = ts

    avg_cost_yes = (cost_yes / shares_yes) if shares_yes else 0.0
    avg_cost_no  = (cost_no / shares_no) if shares_no else 0.0
    total_cost = cost_yes + cost_no
    locked_payout = max(shares_yes, shares_no) * 1.0
    fees = total_cost * fee_mult
    pnl = locked_payout - total_cost - fees

    minutes_to_unwind = None
    if unwind_time is not None:
        start_time = df.index[df.index.get_loc(unwind_time)]  # itself
        # entry time unknown in this minimal stat; leave None

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
        minutes_to_unwind=None,
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-markets", type=int, default=200)
    ap.add_argument("--days", type=int, default=7, help="Days to scan backwards (default: 7)")
    ap.add_argument("--slippage-bps", type=float, default=10.0)
    ap.add_argument("--fee-bps", type=float, default=0.0)
    ap.add_argument("--out", type=str, default="backtest_results.csv")
    ap.add_argument("--assets", type=str, default="btc,eth,sol,xrp")
    args = ap.parse_args()

    cfg = Config(max_markets=args.max_markets,
                 days_back=args.days,
                 slippage_bps=args.slippage_bps,
                 fee_bps=args.fee_bps,
                 only_assets=tuple([a.strip().lower() for a in args.assets.split(",") if a.strip()]))

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
        print(f"win-rate (pnl>=0): {(entered['pnl']>=0).mean():.3f}")
        print(f"avg pnl: {entered['pnl'].mean():.4f} | median pnl: {entered['pnl'].median():.4f}")
        print(f"avg win: {entered.loc[entered['pnl']>=0,'pnl'].mean():.4f}")
        print(f"avg loss: {entered.loc[entered['pnl']<0,'pnl'].mean():.4f}")
        print(f"max loss: {entered['pnl'].min():.4f}")
        print(f"forced unwind rate: {entered['forced'].mean():.3f}")

    print(f"\nSaved -> {args.out}")
    print(f"Elapsed: {time.time()-t0:.1f}s")

if __name__ == "__main__":
    main()
