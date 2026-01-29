
import time
import sys
import os
import random
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from matcher import MarketMatcher
from models import StandardMarket

# Optimize logging for benchmark
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_market(platform, i, title_base):
    return StandardMarket(
        platform=platform,
        market_id=f"{platform}_{i}",
        title=f"{title_base} {i}",
        price_yes=random.random(),
        price_no=random.random(),
        volume=1000,
        url="http://example.com"
    )

def main():
    print("Generating synthetic data...")
    # Generate 1000 Poly markets and 5000 Kalshi markets (scaled down for quick test)
    # Scaled up this would be 20k vs 80k
    
    poly_topics = ["Bitcoin", "Ethereum", "Trump", "Biden", "Fed Rate", "GDP", "Inflation", "Nvidia"]
    kalshi_topics = poly_topics + ["Rain", "Temperature", "Case-Shiller", "Box Office", "Senate"]
    
    poly_markets = []
    for i in range(100):
        topic = random.choice(poly_topics)
        poly_markets.append(generate_market("POLY", i, f"Will {topic} go up by December"))

    kalshi_markets = []
    for i in range(5000):
        topic = random.choice(kalshi_topics)
        kalshi_markets.append(generate_market("KALSHI", i, f"Will {topic} be higher than previous month"))
        
    print(f"Dataset: {len(poly_markets)} Poly vs {len(kalshi_markets)} Kalshi")
    
    matcher = MarketMatcher()
    
    print("\nStarting matching...")
    start_time = time.time()
    matches = matcher.find_matches(poly_markets, kalshi_markets)
    end_time = time.time()
    
    duration = end_time - start_time
    print(f"\nTime taken: {duration:.4f} seconds")
    print(f"Matches found: {len(matches)}")
    print(f"Speed: {len(poly_markets) * len(kalshi_markets) / duration:.0f} comparisons/sec (effective)")

if __name__ == "__main__":
    main()
