#!/usr/bin/env python3
"""
Diagnostic script to find actual Bitcoin/ETH/SOL/XRP Up/Down markets.

Based on user example: "bitcoin up and down December 17,12-12:15AM ET"

This searches for markets with:
- Asset names (bitcoin, ethereum, solana, xrp)
- "up" or "down" keywords
- Time range patterns (e.g., "12-12:15", "12:00-12:15")
"""

import requests
import time
import re
from typing import List, Dict, Any


GAMMA_API_BASE = "https://gamma-api.polymarket.com"
MAX_MARKETS = 2000
PAGINATION_LIMIT = 100
REQUEST_DELAY = 0.5

# Asset keywords (case-insensitive)
ASSETS = {
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "eth"],
    "SOL": ["solana", "sol"],
    "XRP": ["xrp", "ripple"],
}

# Direction keywords
DIRECTIONS = ["up", "down"]


def fetch_markets_batch(offset: int, limit: int) -> List[Dict[str, Any]]:
    """Fetch a batch of markets from Gamma API."""
    url = f"{GAMMA_API_BASE}/markets"
    params = {"limit": limit, "offset": offset}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "data" in data:
            return data["data"]
        return []
    except Exception as e:
        print(f"Error at offset {offset}: {e}")
        return []


def fetch_all_markets(max_markets: int) -> List[Dict[str, Any]]:
    """Fetch all markets with pagination."""
    all_markets = []
    offset = 0
    
    print(f"Fetching up to {max_markets} markets...")
    
    while len(all_markets) < max_markets:
        batch = fetch_markets_batch(offset, PAGINATION_LIMIT)
        if not batch:
            break
        
        all_markets.extend(batch)
        print(f"  Fetched {len(all_markets)} markets...", end="\r")
        
        offset += len(batch)
        if len(batch) < PAGINATION_LIMIT:
            break
        
        time.sleep(REQUEST_DELAY)
    
    print(f"\nTotal fetched: {len(all_markets)}")
    return all_markets[:max_markets]


def matches_time_range_pattern(text: str) -> bool:
    """
    Check if text contains a time range pattern like:
    - "12-12:15"
    - "12:00-12:15"
    - "12:00 AM - 12:15 AM"
    """
    patterns = [
        r'\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}',  # 12:00-12:15
        r'\d{1,2}-\d{1,2}:\d{2}',               # 12-12:15
        r'\d{1,2}:\d{2}\s*[AP]M\s*-\s*\d{1,2}:\d{2}\s*[AP]M',  # 12:00 AM - 12:15 AM
    ]
    
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def scan_for_crypto_updown_markets(markets: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Scan for crypto Up/Down markets.
    
    Returns dict mapping asset_direction to list of markets:
    {
        "BTC_UP": [...],
        "BTC_DOWN": [...],
        ...
    }
    """
    results = {f"{asset}_{direction.upper()}": [] 
               for asset in ASSETS.keys() 
               for direction in DIRECTIONS}
    
    for market in markets:
        question = market.get("question", "").lower()
        description = market.get("description", "").lower()
        combined = f"{question} {description}"
        
        # Check for each asset
        for asset_code, keywords in ASSETS.items():
            if not any(kw in combined for kw in keywords):
                continue
            
            # Check for direction
            for direction in DIRECTIONS:
                if direction in combined:
                    # Check if it has a time range pattern (optional but helpful)
                    results[f"{asset_code}_{direction.upper()}"].append(market)
    
    return results


def print_market_summary(asset_direction: str, markets: List[Dict[str, Any]], max_show: int = 5):
    """Print summary of markets for an asset/direction."""
    print(f"\n{'='*60}")
    print(f"{asset_direction}: {len(markets)} markets found")
    print('='*60)
    
    if not markets:
        print("  (none)")
        return
    
    # Count by status
    enabled = sum(1 for m in markets if m.get('enableOrderBook', False))
    closed = sum(1 for m in markets if m.get('closed', True))
    
    print(f"  enableOrderBook=True: {enabled}/{len(markets)}")
    print(f"  closed=True: {closed}/{len(markets)}")
    print(f"  open: {len(markets) - closed}/{len(markets)}")
    
    print(f"\n  Showing up to {max_show} examples:")
    
    for i, market in enumerate(markets[:max_show], 1):
        print(f"\n  [{i}] {market.get('question', 'N/A')}")
        print(f"      ID: {market.get('id', 'N/A')}")
        print(f"      Slug: {market.get('slug', 'N/A')}")
        print(f"      OrderBook: {market.get('enableOrderBook', 'N/A')}")
        print(f"      Closed: {market.get('closed', 'N/A')}")
        
        # Show token IDs if available
        tokens = market.get('tokens') or market.get('clobTokenIds')
        if tokens:
            print(f"      Tokens: {tokens}")


def main():
    print("\n" + "="*60)
    print("CRYPTO UP/DOWN MARKETS DIAGNOSTIC")
    print("="*60)
    print("\nSearching for markets like:")
    print('  "bitcoin up and down December 17,12-12:15AM ET"')
    print("\n" + "="*60 + "\n")
    
    # Fetch markets
    all_markets = fetch_all_markets(MAX_MARKETS)
    
    if not all_markets:
        print("ERROR: Failed to fetch markets")
        return
    
    # Scan for crypto up/down markets
    print("\nScanning for crypto Up/Down markets...")
    results = scan_for_crypto_updown_markets(all_markets)
    
    # Print results
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    
    total_found = sum(len(markets) for markets in results.values())
    print(f"\nTotal crypto Up/Down markets found: {total_found}")
    
    # Print by asset and direction
    for asset in ["BTC", "ETH", "SOL", "XRP"]:
        for direction in ["UP", "DOWN"]:
            key = f"{asset}_{direction}"
            print_market_summary(key, results[key])
    
    # Overall summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for asset in ["BTC", "ETH", "SOL", "XRP"]:
        up_count = len(results[f"{asset}_UP"])
        down_count = len(results[f"{asset}_DOWN"])
        print(f"{asset}: {up_count} UP, {down_count} DOWN")
    
    print("\n" + "="*60)
    print("DIAGNOSTIC COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
