#!/usr/bin/env python3
"""
Quick diagnostic to check why the backtest isn't entering trades.
"""
import requests
import pandas as pd

CLOB = "https://clob.polymarket.com"

# Get one BTC 15m market
url = f"{CLOB}/markets"
r = requests.get(url, timeout=30)
data = r.json()

markets = data.get("data", []) if isinstance(data, dict) else data

# Find a BTC 15m market
btc_market = None
for m in markets[:100]:
    slug = m.get("market_slug") or m.get("slug", "")
    if "btc-updown-15m" in slug.lower():
        btc_market = m
        break

if not btc_market:
    print("No BTC 15m market found in first 100 markets")
    print(f"Sample slugs: {[m.get('slug', m.get('market_slug', 'N/A'))[:50] for m in markets[:5]]}")
    exit(1)

print(f"Found market: {btc_market.get('slug', btc_market.get('market_slug'))}")
print(f"Keys: {list(btc_market.keys())}")
print(f"Tokens: {btc_market.get('tokens', 'N/A')}")

# Try to get price history for first token
tokens = btc_market.get("tokens", [])
if not tokens:
    print("No tokens found")
    exit(1)

token_id = tokens[0].get("token_id") if isinstance(tokens[0], dict) else tokens[0]
print(f"\nFetching price history for token: {token_id[:20]}...")

# Extract epoch from slug
slug = btc_market.get("slug") or btc_market.get("market_slug")
epoch = int(slug.split("-")[-1])
start_ts = epoch - 3600  # 1 hour before
end_ts = epoch + 900     # 15 min after

url = f"{CLOB}/prices-history?market={token_id}&interval=min&fidelity=1&startTs={start_ts}&endTs={end_ts}"
print(f"URL: {url[:100]}...")

r = requests.get(url, timeout=30)
print(f"Status: {r.status_code}")

if r.status_code == 200:
    j = r.json()
    print(f"Response type: {type(j)}")
    if isinstance(j, list):
        print(f"List length: {len(j)}")
        if j:
            print(f"First item: {j[0]}")
            print(f"First item type: {type(j[0])}")
    elif isinstance(j, dict):
        print(f"Dict keys: {list(j.keys())}")
        if "history" in j:
            hist = j["history"]
            print(f"History length: {len(hist)}")
            if hist:
                print(f"First history item: {hist[0]}")
else:
    print(f"Error: {r.text[:200]}")
