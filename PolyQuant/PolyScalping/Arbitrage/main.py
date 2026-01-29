#!/usr/bin/env python3
"""
Prediction Market Arbitrage Scanner

Main execution script that:
1. Collects data from Polymarket, Kalshi, and Opinion Labs
2. Matches similar markets using fuzzy matching
3. Identifies arbitrage opportunities
4. Outputs results

Supported platforms:
- Polymarket (always enabled)
- Kalshi (always enabled, no API key needed)
- Opinion Labs (requires API key)
"""

import asyncio
import logging
import json
import sys
from typing import List
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from models import ArbitrageOpportunity
from services import PolymarketCollector, OpinionCollector, KalshiCollector
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


async def collect_opinion_data(limit: int = None):
    """Collect data from Opinion Labs asynchronously."""
    loop = asyncio.get_event_loop()
    collector = OpinionCollector()
    
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


async def gather_all_data(limit: int = None, enable_opinion: bool = False):
    """
    Gather data from available platforms concurrently.
    
    Args:
        limit: Maximum markets per platform (None = all markets)
        enable_opinion: Whether to fetch from Opinion Labs (requires API key)
    """
    logger.info("Starting data collection from available platforms...")
    
    # Always collect from Polymarket and Kalshi
    tasks = [
        collect_polymarket_data(limit),
        collect_kalshi_data(limit),
    ]
    
    # Optionally add Opinion Labs
    if enable_opinion:
        tasks.append(collect_opinion_data(limit))
    
    # Run all collectors concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    poly_markets = results[0] if not isinstance(results[0], Exception) else []
    kalshi_markets = results[1] if not isinstance(results[1], Exception) else []
    opinion_markets = results[2] if len(results) > 2 and not isinstance(results[2], Exception) else []
    
    # Handle exceptions
    if isinstance(poly_markets, Exception):
        logger.error(f"Polymarket collection failed: {poly_markets}")
        poly_markets = []
    
    if isinstance(kalshi_markets, Exception):
        logger.error(f"Kalshi collection failed: {kalshi_markets}")
        kalshi_markets = []
    
    if enable_opinion and isinstance(opinion_markets, Exception):
        logger.error(f"Opinion Labs collection failed: {opinion_markets}")
        opinion_markets = []
    
    return poly_markets, kalshi_markets, opinion_markets


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
            "market1": {
                "platform": opp.poly_market.platform,
                "market_id": opp.poly_market.market_id,
                "title": opp.poly_market.title,
                "price_yes": opp.poly_market.price_yes,
                "price_no": opp.poly_market.price_no,
                "volume": opp.poly_market.volume,
                "url": opp.poly_market.url,
            },
            "market2": {
                "platform": opp.opinion_market.platform,
                "market_id": opp.opinion_market.market_id,
                "title": opp.opinion_market.title,
                "price_yes": opp.opinion_market.price_yes,
                "price_no": opp.opinion_market.price_no,
                "volume": opp.opinion_market.volume,
                "url": opp.opinion_market.url,
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
        print(f"\n{opp.poly_market.platform}:")
        print(f"  Title: {opp.poly_market.title[:60]}...")
        print(f"  YES: ${opp.poly_market.price_yes:.4f} | NO: ${opp.poly_market.price_no:.4f}")
        print(f"  URL: {opp.poly_market.url}")
        print(f"\n{opp.opinion_market.platform}:")
        print(f"  Title: {opp.opinion_market.title[:60]}...")
        print(f"  YES: ${opp.opinion_market.price_yes:.4f} | NO: ${opp.opinion_market.price_no:.4f}")
        print(f"  URL: {opp.opinion_market.url}")
    
    if len(opportunities) > 10:
        print(f"\n... and {len(opportunities) - 10} more opportunities")
    
    print("\n" + "="*80)


async def main():
    """
    Main execution function.
    
    Scans for arbitrage opportunities between:
    1. Polymarket vs Kalshi (always enabled)
    2. Polymarket vs Opinion Labs (if API key available)
    3. Kalshi vs Opinion Labs (if API key available)
    """
    try:
        import os
        enable_opinion = bool(os.getenv("OPINION_API_KEY"))
        
        if enable_opinion:
            logger.info("Opinion Labs API key found - scanning all 3 platforms")
        else:
            logger.info("No Opinion Labs API key - scanning Polymarket vs Kalshi only")
        
        # Step 1: Gather data from available platforms (fetch ALL markets)
        poly_markets, kalshi_markets, opinion_markets = await gather_all_data(
            limit=None,  # Fetch ALL markets
            enable_opinion=enable_opinion
        )
        
        if not poly_markets:
            logger.warning("No Polymarket data collected")
        
        if not kalshi_markets:
            logger.warning("No Kalshi data collected")
        
        if enable_opinion and not opinion_markets:
            logger.warning("No Opinion Labs data collected")
        
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
        
        # Polymarket vs Opinion Labs (if available)
        if poly_markets and opinion_markets:
            logger.info("\n=== Scanning Polymarket vs Opinion Labs ===")
            matches = matcher.find_matches(poly_markets, opinion_markets)
            if matches:
                opportunities = matcher.calculate_arbitrage(
                    matches,
                    min_margin=0.02,
                    max_cost=0.98
                )
                all_opportunities.extend(opportunities)
                logger.info(f"Found {len(opportunities)} Poly-Opinion arbitrage opportunities")
        
        # Kalshi vs Opinion Labs (if available)
        if kalshi_markets and opinion_markets:
            logger.info("\n=== Scanning Kalshi vs Opinion Labs ===")
            matches = matcher.find_matches(kalshi_markets, opinion_markets)
            if matches:
                opportunities = matcher.calculate_arbitrage(
                    matches,
                    min_margin=0.02,
                    max_cost=0.98
                )
                all_opportunities.extend(opportunities)
                logger.info(f"Found {len(opportunities)} Kalshi-Opinion arbitrage opportunities")
        
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
