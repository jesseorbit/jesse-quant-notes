
import logging
import sys
import os
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.kalshi import KalshiCollector

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Loading environment variables...")
    load_dotenv()
    
    api_key = os.getenv("KALSHI_API_KEY")
    if api_key:
        logger.info(f"API Key found: {api_key[:4]}***")
    else:
        logger.warning("No API Key found in .env")
        
    logger.info("Initializing Kalshi Collector...")
    collector = KalshiCollector()
    
    logger.info("Fetching markets (limit=2500 to force pagination)...")
    markets = collector.fetch_active_markets(limit=2500)
    
    if markets:
        logger.info(f"Successfully fetched {len(markets)} markets.")
        logger.info(f"Sample market: {markets[0].title} (Price: {markets[0].price_yes})")
    else:
        logger.error("Failed to fetch markets.")

if __name__ == "__main__":
    main()
