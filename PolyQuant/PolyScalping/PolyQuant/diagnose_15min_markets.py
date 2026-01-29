#!/usr/bin/env python3
"""
Diagnostic script to verify whether 15-minute markets exist in Polymarket's Gamma API.

This script scans up to 2,000 markets and searches for any that reference a 15-minute
time window using broad keyword matching.

Usage:
    python3 diagnose_15min_markets.py
"""

import requests
import time
from typing import List, Dict, Any


# Configuration
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
MAX_MARKETS = 2000
PAGINATION_LIMIT = 100
REQUEST_DELAY = 0.5  # seconds between requests

# Broad 15-minute keyword patterns
FIFTEEN_MIN_KEYWORDS = [
    "15 minute",
    "15 minutes",
    "15 min",
    "15m",
    "15-minute",
    "15-min",
    "within 15",
    "next 15",
    "in 15",
    "quarter hour",
    "900 seconds",
    "900 second",
    "fifteen minute",
    "fifteen min",
]


def fetch_markets_batch(offset: int, limit: int) -> List[Dict[str, Any]]:
    """
    Fetch a batch of markets from Gamma API.
    
    Args:
        offset: Pagination offset
        limit: Number of markets to fetch
    
    Returns:
        List of market dictionaries
    """
    url = f"{GAMMA_API_BASE}/markets"
    params = {"limit": limit, "offset": offset}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Handle different response formats
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "data" in data:
            return data["data"]
        else:
            print(f"Warning: Unexpected response format: {type(data)}")
            return []
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching markets at offset {offset}: {e}")
        return []


def fetch_all_markets(max_markets: int) -> List[Dict[str, Any]]:
    """
    Fetch all markets up to max_markets using pagination.
    
    Args:
        max_markets: Maximum number of markets to fetch
    
    Returns:
        List of all fetched markets
    """
    all_markets = []
    offset = 0
    
    print(f"Fetching up to {max_markets} markets from Gamma API...")
    print("=" * 60)
    
    while len(all_markets) < max_markets:
        print(f"Fetching batch at offset {offset}...", end=" ")
        
        batch = fetch_markets_batch(offset, PAGINATION_LIMIT)
        
        if not batch:
            print("(no more data)")
            break
        
        all_markets.extend(batch)
        print(f"(got {len(batch)} markets, total: {len(all_markets)})")
        
        offset += len(batch)
        
        # Stop if we got fewer results than requested (end of data)
        if len(batch) < PAGINATION_LIMIT:
            break
        
        # Rate limiting
        time.sleep(REQUEST_DELAY)
    
    print("=" * 60)
    print(f"Total markets fetched: {len(all_markets)}\n")
    
    return all_markets[:max_markets]


def matches_15min_keywords(text: str) -> bool:
    """
    Check if text contains any 15-minute keywords.
    
    Args:
        text: Text to search (lowercase)
    
    Returns:
        True if any keyword is found
    """
    return any(keyword in text for keyword in FIFTEEN_MIN_KEYWORDS)


def scan_for_15min_markets(markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Scan markets for 15-minute references.
    
    Args:
        markets: List of market dictionaries
    
    Returns:
        List of markets that match 15-minute keywords
    """
    matches = []
    
    for market in markets:
        question = market.get("question", "")
        description = market.get("description", "")
        
        # Concatenate and lowercase
        combined_text = f"{question} {description}".lower()
        
        # Check for 15-minute keywords
        if matches_15min_keywords(combined_text):
            matches.append(market)
    
    return matches


def print_market_details(market: Dict[str, Any], index: int) -> None:
    """
    Print details of a single market.
    
    Args:
        market: Market dictionary
        index: Index number for display
    """
    print(f"\n[{index}] Market Details:")
    print(f"  ID: {market.get('id', 'N/A')}")
    print(f"  Slug: {market.get('slug', 'N/A')}")
    print(f"  Enable Order Book: {market.get('enableOrderBook', 'N/A')}")
    print(f"  Closed: {market.get('closed', 'N/A')}")
    print(f"  Question: {market.get('question', 'N/A')}")
    
    description = market.get('description', '')
    if description:
        # Truncate long descriptions
        if len(description) > 200:
            description = description[:200] + "..."
        print(f"  Description: {description}")
    else:
        print(f"  Description: (none)")


def main():
    """Main diagnostic function."""
    print("\n" + "=" * 60)
    print("POLYMARKET 15-MINUTE MARKETS DIAGNOSTIC")
    print("=" * 60)
    print()
    
    # Fetch all markets
    all_markets = fetch_all_markets(MAX_MARKETS)
    
    if not all_markets:
        print("ERROR: Failed to fetch any markets from Gamma API.")
        return
    
    # Scan for 15-minute markets
    print("Scanning for 15-minute market references...")
    print(f"Using keywords: {', '.join(FIFTEEN_MIN_KEYWORDS)}")
    print("=" * 60)
    
    matches = scan_for_15min_markets(all_markets)
    
    # Print results
    print("\n" + "=" * 60)
    print("DIAGNOSTIC RESULTS")
    print("=" * 60)
    print(f"Total markets scanned: {len(all_markets)}")
    print(f"15-minute market matches: {len(matches)}")
    print("=" * 60)
    
    if matches:
        print(f"\nFound {len(matches)} markets with 15-minute references!")
        print("\nShowing up to 30 examples:\n")
        
        # Show up to 30 matches
        for i, market in enumerate(matches[:30], 1):
            print_market_details(market, i)
        
        if len(matches) > 30:
            print(f"\n... and {len(matches) - 30} more matches (not shown)")
        
        # Summary statistics
        print("\n" + "=" * 60)
        print("SUMMARY STATISTICS")
        print("=" * 60)
        
        enabled_count = sum(1 for m in matches if m.get('enableOrderBook', False))
        closed_count = sum(1 for m in matches if m.get('closed', True))
        open_count = sum(1 for m in matches if not m.get('closed', True))
        
        print(f"Markets with enableOrderBook=True: {enabled_count}/{len(matches)}")
        print(f"Markets closed: {closed_count}/{len(matches)}")
        print(f"Markets open: {open_count}/{len(matches)}")
        
        # Check for Up/Down keywords
        up_count = sum(1 for m in matches 
                      if any(kw in f"{m.get('question', '')} {m.get('description', '')}".lower() 
                            for kw in ["up", "higher", "above"]))
        down_count = sum(1 for m in matches 
                        if any(kw in f"{m.get('question', '')} {m.get('description', '')}".lower() 
                              for kw in ["down", "lower", "below"]))
        
        print(f"Markets with 'Up/Higher/Above' keywords: {up_count}/{len(matches)}")
        print(f"Markets with 'Down/Lower/Below' keywords: {down_count}/{len(matches)}")
        
        # Asset mentions
        btc_count = sum(1 for m in matches 
                       if any(kw in f"{m.get('question', '')} {m.get('description', '')}".lower() 
                             for kw in ["btc", "bitcoin"]))
        eth_count = sum(1 for m in matches 
                       if any(kw in f"{m.get('question', '')} {m.get('description', '')}".lower() 
                             for kw in ["eth", "ethereum"]))
        sol_count = sum(1 for m in matches 
                       if any(kw in f"{m.get('question', '')} {m.get('description', '')}".lower() 
                             for kw in ["sol", "solana"]))
        xrp_count = sum(1 for m in matches 
                       if any(kw in f"{m.get('question', '')} {m.get('description', '')}".lower() 
                             for kw in ["xrp", "ripple"]))
        
        print(f"\nAsset mentions:")
        print(f"  BTC/Bitcoin: {btc_count}")
        print(f"  ETH/Ethereum: {eth_count}")
        print(f"  SOL/Solana: {sol_count}")
        print(f"  XRP/Ripple: {xrp_count}")
    
    else:
        print("\n" + "!" * 60)
        print("No 15-minute markets found in the scanned Gamma dataset.")
        print("!" * 60)
        print("\nPossible reasons:")
        print("  1. These markets don't currently exist on Polymarket")
        print("  2. They use different time window terminology")
        print("  3. They exist but are beyond the first 2,000 markets")
        print("\nRecommendation:")
        print("  - Check Polymarket's website directly for available market types")
        print("  - Try searching for other time windows (e.g., 5-min, 30-min, 1-hour)")
        print("  - Inspect a sample of markets to understand naming patterns")
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
