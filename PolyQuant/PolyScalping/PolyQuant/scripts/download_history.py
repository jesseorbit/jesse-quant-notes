#!/usr/bin/env python3
"""
Historical data download script.

Downloads price histories for discovered markets and saves to CSV/Parquet.
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from polyquant import config
from polyquant.clients.clob import ClobClient
from polyquant.clients.gamma import GammaClient
from polyquant.fetch_history import download_all_histories
from polyquant.market_discovery import discover_15min_markets
from polyquant.storage import load_metadata, save_all_histories, save_metadata
from polyquant.utils import ensure_directories, parse_timestamp, setup_logging


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download historical price data for Polymarket 15-minute markets"
    )
    
    parser.add_argument(
        "--start",
        required=True,
        help="Start date (ISO format like '2025-12-01' or unix timestamp)"
    )
    
    parser.add_argument(
        "--end",
        required=True,
        help="End date (ISO format like '2025-12-17' or unix timestamp)"
    )
    
    parser.add_argument(
        "--fidelity",
        type=int,
        default=config.DEFAULT_FIDELITY,
        help=f"Resolution in minutes (default: {config.DEFAULT_FIDELITY})"
    )
    
    parser.add_argument(
        "--assets",
        default=",".join(config.DEFAULT_ASSETS),
        help=f"Comma-separated asset list (default: {','.join(config.DEFAULT_ASSETS)})"
    )
    
    parser.add_argument(
        "--minutes",
        type=int,
        default=config.DEFAULT_MARKET_MINUTES,
        help=f"Market duration in minutes (default: {config.DEFAULT_MARKET_MINUTES})"
    )
    
    parser.add_argument(
        "--rediscover",
        action="store_true",
        help="Force rediscovery of markets (ignore cached metadata)"
    )
    
    return parser.parse_args()


def main():
    """Main entry point for history download."""
    args = parse_args()
    
    # Setup
    logger = setup_logging()
    ensure_directories()
    
    logger.info("=" * 60)
    logger.info("PolyQuant Historical Data Download")
    logger.info("=" * 60)
    
    # Parse timestamps
    try:
        start_dt = parse_timestamp(args.start)
        end_dt = parse_timestamp(args.end)
    except ValueError as e:
        logger.error(f"Invalid timestamp: {e}")
        return 1
    
    logger.info(f"Date range: {start_dt.isoformat()} to {end_dt.isoformat()}")
    logger.info(f"Fidelity: {args.fidelity} minutes")
    
    # Parse assets
    assets = [a.strip().upper() for a in args.assets.split(",")]
    logger.info(f"Assets: {assets}")
    
    # Load or discover markets
    markets = None
    
    if not args.rediscover:
        metadata = load_metadata()
        if metadata and "markets" in metadata:
            markets = metadata["markets"]
            logger.info(f"Loaded {len(markets)} markets from cached metadata")
            
            # Filter by requested assets
            filtered_markets = {
                name: meta for name, meta in markets.items()
                if any(asset in name for asset in assets)
            }
            markets = filtered_markets
            logger.info(f"Filtered to {len(markets)} markets for requested assets")
    
    if not markets or args.rediscover:
        logger.info("Discovering markets...")
        gamma_client = GammaClient()
        markets = discover_15min_markets(assets=assets, gamma_client=gamma_client)
        
        if not markets:
            logger.error("No markets discovered. Exiting.")
            return 1
    
    # Download histories
    logger.info(f"Downloading histories for {len(markets)} markets...")
    
    clob_client = ClobClient()
    
    try:
        histories = download_all_histories(
            markets_dict=markets,
            clob_client=clob_client,
            start=start_dt,
            end=end_dt,
            fidelity=args.fidelity
        )
        
        if not histories:
            logger.warning("No histories downloaded")
            return 1
        
        # Save all data
        query_params = {
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "fidelity": args.fidelity,
            "assets": assets,
            "market_minutes": args.minutes,
        }
        
        save_all_histories(histories, markets, query_params)
        
        # Print summary
        print("\n" + "=" * 60)
        print("DOWNLOAD SUMMARY")
        print("=" * 60)
        
        for market_name, df in sorted(histories.items()):
            print(f"{market_name}: {len(df)} data points")
        
        print("\n" + "=" * 60)
        print(f"✓ Raw data saved to: {config.RAW_DATA_DIR}")
        print(f"✓ Processed data saved to: {config.PROCESSED_DATA_DIR}")
        print(f"✓ Metadata saved to: {config.METADATA_DIR / 'markets.json'}")
        print("=" * 60)
        
        return 0
    
    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
