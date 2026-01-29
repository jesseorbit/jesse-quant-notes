#!/usr/bin/env python3
"""
Market discovery script.

Discovers 15-minute Up/Down markets for BTC, ETH, SOL, and XRP,
and saves metadata to data/metadata/markets.json.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from polyquant import config
from polyquant.clients.gamma import GammaClient
from polyquant.market_discovery import discover_15min_markets
from polyquant.storage import save_metadata
from polyquant.utils import ensure_directories, setup_logging


def main():
    """Main entry point for market discovery."""
    # Setup
    logger = setup_logging()
    ensure_directories()
    
    logger.info("=" * 60)
    logger.info("PolyQuant Market Discovery")
    logger.info("=" * 60)
    
    # Initialize Gamma client
    gamma_client = GammaClient()
    
    # Discover markets
    try:
        markets = discover_15min_markets(
            assets=config.DEFAULT_ASSETS,
            gamma_client=gamma_client
        )
        
        # Print results
        print("\n" + "=" * 60)
        print(f"DISCOVERED MARKETS ({len(markets)}/{len(config.DEFAULT_ASSETS) * 2})")
        print("=" * 60)
        
        for market_name, meta in sorted(markets.items()):
            print(f"\n{market_name}:")
            print(f"  Question: {meta['question']}")
            print(f"  Market ID: {meta['market_id']}")
            print(f"  YES Token: {meta['yes_token_id'][:10]}...")
            print(f"  NO Token:  {meta['no_token_id'][:10]}...")
        
        # Save metadata
        query_params = {
            "assets": config.DEFAULT_ASSETS,
            "market_minutes": config.DEFAULT_MARKET_MINUTES,
        }
        save_metadata(markets, query_params)
        
        print("\n" + "=" * 60)
        print(f"✓ Metadata saved to: {config.METADATA_DIR / 'markets.json'}")
        print("=" * 60)
        
        return 0
    
    except Exception as e:
        logger.error(f"Market discovery failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
