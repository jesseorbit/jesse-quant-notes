#!/usr/bin/env python3
"""
Quick script to find a specific market by partial name match.
"""

import requests

GAMMA_API_BASE = "https://gamma-api.polymarket.com"

# Search for markets containing "bitcoin up and down"
search_terms = ["bitcoin up and down", "ethereum up and down", "solana up and down", "xrp up and down"]

print("Searching for specific market patterns...")
print("="*60)

for term in search_terms:
    print(f"\nSearching for: '{term}'")
    
    # Fetch first batch of markets
    response = requests.get(f"{GAMMA_API_BASE}/markets", params={"limit": 100, "offset": 0})
    markets = response.json()
    
    if isinstance(markets, dict) and "data" in markets:
        markets = markets["data"]
    
    found = []
    for market in markets:
        question = market.get("question", "").lower()
        if term.lower() in question:
            found.append(market)
    
    if found:
        print(f"  Found {len(found)} matches!")
        for m in found[:3]:
            print(f"    - {m.get('question')}")
            print(f"      ID: {m.get('id')}, Closed: {m.get('closed')}")
    else:
        print(f"  No matches in first 100 markets")

print("\n" + "="*60)
