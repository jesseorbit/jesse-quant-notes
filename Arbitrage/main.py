#!/usr/bin/env python3
"""
Prediction Market Arbitrage Scanner

Main execution script that:
1. Collects data from Polymarket and Kalshi
2. Matches similar markets using fuzzy matching
3. Identifies arbitrage opportunities
4. Outputs results

Supported platforms:
- Polymarket (always enabled)
- Kalshi (always enabled, no API key needed)
"""

import asyncio
import logging
import json
import sys
from typing import List
from datetime import datetime

from models import ArbitrageOpportunity
from services import KalshiCollector, PolymarketCollector
from matcher import MarketMatcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('arbitrage_scanner.log')
    ]
)

logger = logging.getLogger(__name__)


async def collect_polymarket_data(limit: int = None):
    """Collect data from Polymarket asynchronously."""
    loop = asyncio.get_event_loop()
    collector = PolymarketCollector()
    
    # Run in executor to avoid blocking
    markets = await loop.run_in_executor(
        None, 
        collector.fetch_active_markets, 
        limit
    )
    
    return markets


async def collect_kalshi_data(limit: int = None):
    """Collect data from Kalshi asynchronously."""
    loop = asyncio.get_event_loop()
    collector = KalshiCollector()
    
    # Run in executor to avoid blocking
    markets = await loop.run_in_executor(
        None, 
        collector.fetch_active_markets, 
        limit
    )
    
    return markets


async def gather_all_data(limit: int = None):
    """
    Gather data from available platforms concurrently.

    Args:
        limit: Maximum markets per platform (None = all markets)
    """
    logger.info("Starting data collection from Polymarket and Kalshi...")

    tasks = [
        collect_polymarket_data(limit),
        collect_kalshi_data(limit),
    ]

    # Run all collectors concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    poly_markets = results[0] if not isinstance(results[0], Exception) else []
    kalshi_markets = results[1] if not isinstance(results[1], Exception) else []

    # Handle exceptions
    if isinstance(poly_markets, Exception):
        logger.error(f"Polymarket collection failed: {poly_markets}")
        poly_markets = []
    
    if isinstance(kalshi_markets, Exception):
        logger.error(f"Kalshi collection failed: {kalshi_markets}")
        kalshi_markets = []

    return poly_markets, kalshi_markets


def save_results(opportunities: List[ArbitrageOpportunity], filename: str = "arbitrage_results.json"):
    """Save arbitrage opportunities to JSON file."""
    results = []
    
    for opp in opportunities:
        results.append({
            "timestamp": datetime.now().isoformat(),
            "roi_percent": opp.roi_percent,
            "profit_margin": opp.profit_margin,
            "total_cost": opp.total_cost,
            "similarity_score": opp.similarity_score,
            "polymarket": {
                "market_id": opp.poly_market.market_id,
                "title": opp.poly_market.title,
                "price_yes": opp.poly_market.price_yes,
                "price_no": opp.poly_market.price_no,
                "volume": opp.poly_market.volume,
                "url": opp.poly_market.url,
            },
            "counter_market": {
                "market_id": opp.counter_market.market_id,
                "platform": opp.counter_market.platform,
                "title": opp.counter_market.title,
                "price_yes": opp.counter_market.price_yes,
                "price_no": opp.counter_market.price_no,
                "volume": opp.counter_market.volume,
                "url": opp.counter_market.url,
            }
        })
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Results saved to {filename}")


def print_summary(opportunities: List[ArbitrageOpportunity]):
    """Print summary of arbitrage opportunities."""
    print("\n" + "="*80)
    print("ARBITRAGE SCANNER RESULTS")
    print("="*80)
    
    if not opportunities:
        print("\nNo arbitrage opportunities found.")
        return
    
    print(f"\nFound {len(opportunities)} arbitrage opportunities!\n")
    
    for i, opp in enumerate(opportunities[:10], 1):  # Show top 10
        print(f"\n--- Opportunity #{i} ---")
        print(f"ROI: {opp.roi_percent:.2f}%")
        print(f"Profit Margin: ${opp.profit_margin:.4f}")
        print(f"Total Cost: ${opp.total_cost:.4f}")
        print(f"Match Score: {opp.similarity_score:.1f}/100")
        print(f"\nPolymarket:")
        print(f"  Title: {opp.poly_market.title[:60]}...")
        print(f"  YES: ${opp.poly_market.price_yes:.4f} | NO: ${opp.poly_market.price_no:.4f}")
        print(f"  URL: {opp.poly_market.url}")
        print(f"\n{opp.counter_market.platform}:")
        print(f"  Title: {opp.counter_market.title[:60]}...")
        print(f"  YES: ${opp.counter_market.price_yes:.4f} | NO: ${opp.counter_market.price_no:.4f}")
        print(f"  URL: {opp.counter_market.url}")
    
    if len(opportunities) > 10:
        print(f"\n... and {len(opportunities) - 10} more opportunities")
    
    print("\n" + "="*80)


async def main():
    """
    Main execution function.
    
    Scans for arbitrage opportunities between Polymarket and Kalshi only.
    """
    try:
        logger.info("Scanning Polymarket vs Kalshi (Opinion Labs disabled)")

        # Step 1: Gather data from available platforms (fetch ALL markets)
        poly_markets, kalshi_markets = await gather_all_data(
            limit=None,  # Fetch ALL markets
        )
        
        if not poly_markets:
            logger.warning("No Polymarket data collected")
        
        if not kalshi_markets:
            logger.warning("No Kalshi data collected")
        
        # Step 2: Match markets and find arbitrage
        matcher = MarketMatcher(
            similarity_threshold=85.0,
            min_common_keywords=2
        )
        
        all_opportunities = []
        
        # Polymarket vs Kalshi (primary)
        if poly_markets and kalshi_markets:
            logger.info("\n=== Scanning Polymarket vs Kalshi ===")
            matches = matcher.find_matches(poly_markets, kalshi_markets)
            if matches:
                opportunities = matcher.calculate_arbitrage(
                    matches,
                    min_margin=0.02,
                    max_cost=0.98
                )
                all_opportunities.extend(opportunities)
                logger.info(f"Found {len(opportunities)} Poly-Kalshi arbitrage opportunities")
        
        # Sort all opportunities by ROI
        all_opportunities.sort(key=lambda x: x.roi_percent, reverse=True)
        
        # Step 3: Output results
        print_summary(all_opportunities)
        
        if all_opportunities:
            save_results(all_opportunities)
        
        logger.info("Arbitrage scan completed successfully")
        
    except Exception as e:
        logger.error(f"Fatal error in main execution: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
