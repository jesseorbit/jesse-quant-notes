#!/usr/bin/env python3
import os
import logging
from dotenv import load_dotenv
from services.opinion import OpinionCollector

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_fetch():
    # Load env
    load_dotenv()
    
    print("Initializing OpinionCollector (curl-based)...")
    collector = OpinionCollector()
    
    print("Fetching markets...")
    markets = collector.fetch_active_markets(limit=200)
    
    print(f"\nFetched {len(markets)} active markets.")
    
    if markets:
        print("\nSample Markets:")
        for m in markets[:5]:
            print(f"- [{m.market_id}] {m.title} (Price: {m.price_yes:.2f}/{m.price_no:.2f})")
            
        # Count non-default prices
        # Default is 0.5. If we fetched successfully, many should be different.
        priced_markets = sum(1 for m in markets if abs(m.price_yes - 0.5) > 0.0001)
        print(f"\nMarkets with real prices (!= 0.5): {priced_markets}/{len(markets)}")
    else:
        print("No markets fetched.")

if __name__ == "__main__":
    test_fetch()
