
import logging
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from polyquant.clients.gamma import GammaClient
from polyquant.market_discovery import discover_15min_markets

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("Initializing Gamma Client...")
    gamma_client = GammaClient()
    
    active_only = True
    assets = ["BTC", "ETH"]
    
    logger.info(f"Discovering markets with active_only={active_only}...")
    discovered = discover_15min_markets(assets, gamma_client, max_markets=500, active_only=active_only)
    
    logger.info("\n=== Discovery Results ===")
    
    if not discovered:
        logger.warning("No markets discovered.")
        return

    has_past_markets = False
    
    for key, market in discovered.items():
        market_id = market.get("market_id")
        question = market.get("question")
        
        # We need to fetch the full market object again to check endDate properly if not stored in discovered dict
        # but for now let's just inspect what we have found.
        # Ideally we should trust the discovery logic, but let's do a sanity check by fetching details if needed.
        # Actually, discover_15min_markets filters them out, so if they are here, they survived the filter.
        
        # Let's verify manually by checking the market details from API
        # (simulated or by printing what we can find)
        
        logger.info(f"Market: {key}")
        logger.info(f"  Question: {question}")
        logger.info(f"  ID: {market_id}")
        
    logger.info(f"\nTotal markets found: {len(discovered)}")

if __name__ == "__main__":
    main()
