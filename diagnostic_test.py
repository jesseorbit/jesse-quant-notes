
import sys
import os
import logging
from dotenv import load_dotenv

# Add current directory to path
sys.path.append(os.getcwd())

from services.kalshi import KalshiCollector
from services.polymarket import PolymarketCollector

logging.basicConfig(level=logging.INFO)

def test_kalshi():
    print("Testing Kalshi...")
    collector = KalshiCollector()
    markets = collector.fetch_active_markets(limit=10)
    print(f"Fetched {len(markets)} Kalshi markets")
    for m in markets:
        print(f"  - {m.title} (${m.price_yes})")

def test_poly():
    print("\nTesting Polymarket...")
    collector = PolymarketCollector()
    markets = collector.fetch_active_markets(limit=10)
    print(f"Fetched {len(markets)} Polymarket markets")
    for m in markets:
        print(f"  - {m.title} (${m.price_yes})")

if __name__ == "__main__":
    load_dotenv()
    test_kalshi()
    test_poly()
