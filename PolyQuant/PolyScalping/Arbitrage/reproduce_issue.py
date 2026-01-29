import logging
import os
from dotenv import load_dotenv
from services.opinion import OpinionCollector

# Configure logging
logging.basicConfig(level=logging.DEBUG)
load_dotenv()

def test_collector():
    collector = OpinionCollector()
    print("Fetching markets...")
    markets = collector.fetch_active_markets(limit=1000)
    print(f"Total Markets Fetched: {len(markets)}")
    for m in markets[:5]:
        print(f" - {m.title} (${m.price_yes})")

if __name__ == "__main__":
    test_collector()
