#!/usr/bin/env python3
"""
Build a 90-day dataset for Polymarket BTC 15-minute Up/Down markets.

This script efficiently fetches all BTC 15m markets from Gamma API, builds an
epoch-to-market mapping, retrieves price history from CLOB API, and merges
everything into a comprehensive dataset with caching support.

Usage:
    # Full 90-day scan
    python3 scripts/fetch_btc_updown_15m_90d.py --days 90 --fidelity 1 --lookback-hours 1 --lookforward-hours 0.5
    
    # Quick test (2 days, max 20 markets)
    python3 scripts/fetch_btc_updown_15m_90d.py --days 2 --max-found 20
    
    # Force refresh (bypass cache)
    python3 scripts/fetch_btc_updown_15m_90d.py --days 90 --force-refresh
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

# API Configuration
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"

# Rate limiting
REQUEST_DELAY = 0.3
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 1.0

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def request_with_retry(
    method: str,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Optional[requests.Response]:
    """
    Make HTTP request with exponential backoff retry logic.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: Full URL
        params: Query parameters
        **kwargs: Additional requests arguments
    
    Returns:
        Response object or None if 404
    
    Raises:
        requests.HTTPError: If all retries fail (except 404)
    """
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                timeout=30,
                **kwargs
            )
            
            # Return None for 404
            if response.status_code == 404:
                return None
            
            response.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return response
        
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            
            if status_code == 404:
                return None
            
            if status_code in [429, 500, 502, 503, 504]:
                if attempt < RETRY_ATTEMPTS - 1:
                    delay = RETRY_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        f"HTTP {status_code} error, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{RETRY_ATTEMPTS})"
                    )
                    time.sleep(delay)
                    continue
            
            logger.error(f"HTTP error {status_code}: {e}")
            raise
        
        except requests.exceptions.RequestException as e:
            if attempt < RETRY_ATTEMPTS - 1:
                delay = RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    f"Request failed: {e}, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{RETRY_ATTEMPTS})"
                )
                time.sleep(delay)
                continue
            
            logger.error(f"Request failed after {RETRY_ATTEMPTS} attempts: {e}")
            raise
    
    raise requests.HTTPError("All retry attempts exhausted")


def load_cache(cache_dir: Path) -> Dict[str, Any]:
    """
    Load cached data from disk.
    
    Args:
        cache_dir: Cache directory path
    
    Returns:
        Cache dictionary with markets and price histories
    """
    cache_file = cache_dir / "cache.json"
    
    if not cache_file.exists():
        return {"markets": {}, "price_histories": {}, "last_updated": None}
    
    try:
        with open(cache_file, "r") as f:
            cache = json.load(f)
        logger.info(f"Loaded cache from {cache_file}")
        logger.info(f"  Cached markets: {len(cache.get('markets', {}))}")
        logger.info(f"  Cached price histories: {len(cache.get('price_histories', {}))}")
        logger.info(f"  Last updated: {cache.get('last_updated', 'N/A')}")
        return cache
    except Exception as e:
        logger.warning(f"Failed to load cache: {e}")
        return {"markets": {}, "price_histories": {}, "last_updated": None}


def save_cache(cache_dir: Path, cache: Dict[str, Any]):
    """
    Save cache data to disk.
    
    Args:
        cache_dir: Cache directory path
        cache: Cache dictionary to save
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "cache.json"
    
    cache["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    try:
        with open(cache_file, "w") as f:
            json.dump(cache, f, indent=2)
        logger.info(f"Saved cache to {cache_file}")
    except Exception as e:
        logger.warning(f"Failed to save cache: {e}")


def fetch_all_btc_15m_markets(days: int) -> List[Dict[str, Any]]:
    """
    Fetch all BTC 15-minute markets using direct epoch generation.
    
    Recent BTC 15m markets are NOT returned by the /markets endpoint,
    so we must generate epochs and fetch each market directly by slug.
    
    Args:
        days: Number of days to look back
    
    Returns:
        List of market dictionaries
    """
    logger.info("Fetching BTC 15-minute markets via direct epoch generation...")
    
    all_markets = []
    
    # Calculate date range (UTC-aware)
    now = datetime.now(timezone.utc)
    start_dt = now - timedelta(days=days)
    
    logger.info(f"Looking for markets between {start_dt.isoformat()} and {now.isoformat()}")
    
    # Generate all 15-minute epochs in the range
    # Round to nearest 15-minute boundary
    start_epoch = int(start_dt.timestamp())
    start_epoch = (start_epoch // 900) * 900  # Round down to 15-min boundary
    
    end_epoch = int(now.timestamp())
    end_epoch = (end_epoch // 900) * 900  # Round down to 15-min boundary
    
    total_epochs = (end_epoch - start_epoch) // 900
    logger.info(f"Generating {total_epochs} epochs from {start_epoch} to {end_epoch}")
    
    found_count = 0
    not_found_count = 0
    
    # Generate epochs and fetch each market
    for epoch in range(start_epoch, end_epoch + 900, 900):
        slug = f"btc-updown-15m-{epoch}"
        
        # Fetch market by slug
        url = f"{GAMMA_API_BASE}/markets/slug/{slug}"
        response = request_with_retry("GET", url)
        
        if response is not None:
            try:
                market = response.json()
                all_markets.append(market)
                found_count += 1
                
                if found_count % 10 == 0:
                    logger.info(f"Progress: {found_count} markets found, {not_found_count} not found (epoch {epoch})")
            except Exception as e:
                logger.warning(f"Failed to parse market {slug}: {e}")
                not_found_count += 1
        else:
            not_found_count += 1
    
    logger.info(f"Total BTC 15-minute markets found: {len(all_markets)}")
    logger.info(f"Markets not found (404): {not_found_count}")
    return all_markets




def build_epoch_mapping(markets: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """
    Build epoch-to-market mapping using market end times.
    
    Args:
        markets: List of market dictionaries
    
    Returns:
        Dictionary mapping epoch to market data
    """
    logger.info("Building epoch-to-market mapping...")
    
    epoch_map = {}
    
    for market in markets:
        slug = market.get("slug", "")
        
        # Extract epoch from slug
        try:
            epoch_str = slug.split("-")[-1]
            epoch = int(epoch_str)
            
            # Extract token IDs
            clob_token_ids_raw = market.get("clobTokenIds", [])
            
            # Handle both list and JSON string formats
            if isinstance(clob_token_ids_raw, str):
                try:
                    clob_token_ids = json.loads(clob_token_ids_raw)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse clobTokenIds JSON for {slug}")
                    continue
            elif isinstance(clob_token_ids_raw, list):
                clob_token_ids = clob_token_ids_raw
            else:
                logger.warning(f"Unexpected clobTokenIds type for {slug}: {type(clob_token_ids_raw)}")
                continue
            
            if len(clob_token_ids) >= 2:
                epoch_map[epoch] = {
                    "slug": slug,
                    "epoch": epoch,
                    "gamma_market_id": market.get("id"),
                    "question": market.get("question"),
                    "yes_token_id": clob_token_ids[0],
                    "no_token_id": clob_token_ids[1],
                    "end_date": market.get("endDate")
                }
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse epoch from slug {slug}: {e}")
            continue
    
    logger.info(f"Built epoch mapping for {len(epoch_map)} markets")
    return epoch_map


def fetch_price_history(
    token_id: str,
    start_ts: int,
    end_ts: int,
    fidelity: int,
    cache: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Fetch historical price data for a token from CLOB API or cache.
    
    Args:
        token_id: CLOB token ID
        start_ts: Start timestamp (unix seconds)
        end_ts: End timestamp (unix seconds)
        fidelity: Resolution in minutes
        cache: Cache dictionary
    
    Returns:
        List of price points: [{"t": timestamp, "p": price}, ...]
    """
    # Create cache key
    cache_key = f"{token_id}_{start_ts}_{end_ts}_{fidelity}"
    
    # Check cache first
    if cache_key in cache.get("price_histories", {}):
        return cache["price_histories"][cache_key]
    
    # Fetch from API
    url = f"{CLOB_API_BASE}/prices-history"
    params = {
        "market": token_id,
        "startTs": start_ts,
        "endTs": end_ts,
        "fidelity": fidelity
    }
    
    response = request_with_retry("GET", url, params=params)
    
    if response is None:
        logger.warning(f"No price history for token {token_id[:10]}...")
        return []
    
    try:
        data = response.json()
        
        # Handle both response formats
        if isinstance(data, list):
            history = data
        elif isinstance(data, dict) and "history" in data:
            history = data["history"]
        else:
            logger.warning(f"Unexpected response format for token {token_id[:10]}...")
            history = []
        
        # Cache the result
        if "price_histories" not in cache:
            cache["price_histories"] = {}
        cache["price_histories"][cache_key] = history
        
        return history
    
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse price history for token {token_id[:10]}...")
        return []


def fetch_markets_data(
    epoch_map: Dict[int, Dict[str, Any]],
    fidelity: int,
    lookback_hours: int,
    lookforward_hours: int,
    max_found: Optional[int],
    cache: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Fetch price histories for all markets.
    
    Args:
        epoch_map: Epoch-to-market mapping
        fidelity: Price history resolution in minutes
        lookback_hours: Hours to look back from epoch
        lookforward_hours: Hours to look forward from epoch
        max_found: Maximum number of markets to process
        cache: Cache dictionary
    
    Returns:
        List of market data dictionaries with price histories
    """
    logger.info(f"Fetching price histories for {len(epoch_map)} markets...")
    
    markets_data = []
    count = 0
    
    for epoch, market_info in sorted(epoch_map.items()):
        count += 1
        
        if count % 20 == 0:
            logger.info(f"Processing market {count}/{len(epoch_map)}: {market_info['slug']}")
        
        # Calculate price history window
        price_start_ts = epoch - (lookback_hours * 3600)
        price_end_ts = epoch + (lookforward_hours * 3600)
        
        # Fetch price histories
        yes_history = fetch_price_history(
            market_info["yes_token_id"],
            price_start_ts,
            price_end_ts,
            fidelity,
            cache
        )
        
        no_history = fetch_price_history(
            market_info["no_token_id"],
            price_start_ts,
            price_end_ts,
            fidelity,
            cache
        )
        
        # Store market data
        market_data = {
            "slug": market_info["slug"],
            "epoch": epoch,
            "gamma_market_id": market_info["gamma_market_id"],
            "question": market_info["question"],
            "yes_token_id": market_info["yes_token_id"],
            "no_token_id": market_info["no_token_id"],
            "price_start_ts": price_start_ts,
            "price_end_ts": price_end_ts,
            "yes_history": yes_history,
            "no_history": no_history
        }
        
        markets_data.append(market_data)
        
        # Check max_found limit
        if max_found and count >= max_found:
            logger.info(f"Reached max_found limit of {max_found} markets")
            break
    
    logger.info(f"Fetched price histories for {len(markets_data)} markets")
    return markets_data


def save_per_slug_data(market_data: Dict[str, Any], base_dir: Path):
    """
    Save per-slug raw price data and metadata.
    
    Args:
        market_data: Market data dictionary
        base_dir: Base data directory
    """
    slug = market_data["slug"]
    
    # Create directories
    raw_dir = base_dir / "raw" / "btc_15m"
    metadata_dir = base_dir / "metadata" / "btc_15m"
    raw_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    
    # Save YES history
    if market_data["yes_history"]:
        yes_df = pd.DataFrame(market_data["yes_history"])
        yes_df = yes_df.rename(columns={"t": "ts", "p": "price"})
        yes_df["ts_utc"] = pd.to_datetime(yes_df["ts"], unit="s", utc=True)
        yes_df = yes_df[["ts_utc", "price"]]
        
        yes_path = raw_dir / f"{slug}_YES.parquet"
        yes_df.to_parquet(yes_path, index=False)
    
    # Save NO history
    if market_data["no_history"]:
        no_df = pd.DataFrame(market_data["no_history"])
        no_df = no_df.rename(columns={"t": "ts", "p": "price"})
        no_df["ts_utc"] = pd.to_datetime(no_df["ts"], unit="s", utc=True)
        no_df = no_df[["ts_utc", "price"]]
        
        no_path = raw_dir / f"{slug}_NO.parquet"
        no_df.to_parquet(no_path, index=False)
    
    # Save metadata
    metadata = {
        "slug": slug,
        "epoch": market_data["epoch"],
        "gamma_market_id": market_data["gamma_market_id"],
        "question": market_data["question"],
        "yes_token_id": market_data["yes_token_id"],
        "no_token_id": market_data["no_token_id"],
        "price_start_ts": market_data["price_start_ts"],
        "price_end_ts": market_data["price_end_ts"],
        "yes_rows": len(market_data["yes_history"]),
        "no_rows": len(market_data["no_history"])
    }
    
    metadata_path = metadata_dir / f"{slug}.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)


def merge_all_markets(markets_data: List[Dict[str, Any]], base_dir: Path):
    """
    Merge all market price histories into a single dataset.
    
    Args:
        markets_data: List of market data dictionaries
        base_dir: Base data directory
    """
    logger.info(f"Merging {len(markets_data)} markets into final dataset...")
    
    all_records = []
    
    for market_data in markets_data:
        slug = market_data["slug"]
        epoch = market_data["epoch"]
        
        # Convert histories to DataFrames
        yes_df = None
        no_df = None
        
        if market_data["yes_history"]:
            yes_df = pd.DataFrame(market_data["yes_history"])
            yes_df = yes_df.rename(columns={"t": "ts", "p": "yes_price"})
            yes_df["ts_utc"] = pd.to_datetime(yes_df["ts"], unit="s", utc=True)
            yes_df = yes_df[["ts_utc", "yes_price"]]
        
        if market_data["no_history"]:
            no_df = pd.DataFrame(market_data["no_history"])
            no_df = no_df.rename(columns={"t": "ts", "p": "no_price"})
            no_df["ts_utc"] = pd.to_datetime(no_df["ts"], unit="s", utc=True)
            no_df = no_df[["ts_utc", "no_price"]]
        
        # Merge YES and NO
        if yes_df is not None and no_df is not None:
            merged = pd.merge(yes_df, no_df, on="ts_utc", how="outer")
        elif yes_df is not None:
            merged = yes_df
            merged["no_price"] = None
        elif no_df is not None:
            merged = no_df
            merged["yes_price"] = None
        else:
            continue
        
        # Add slug and epoch
        merged["slug"] = slug
        merged["epoch"] = epoch
        
        all_records.append(merged)
    
    if not all_records:
        logger.warning("No data to merge")
        return
    
    # Concatenate all markets
    final_df = pd.concat(all_records, ignore_index=True)
    
    # Reorder columns
    final_df = final_df[["slug", "epoch", "ts_utc", "yes_price", "no_price"]]
    
    # Calculate derived columns
    final_df["sum_price"] = final_df["yes_price"] + final_df["no_price"]
    final_df["mispricing"] = 1.0 - final_df["sum_price"]
    
    # Sort by epoch and timestamp
    final_df = final_df.sort_values(["epoch", "ts_utc"]).reset_index(drop=True)
    
    logger.info(f"Final merged dataset: {len(final_df)} rows")
    
    # Save to processed directory
    processed_dir = base_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    # Save as Parquet
    parquet_path = processed_dir / "btc_updown_15m_90d_merged.parquet"
    final_df.to_parquet(parquet_path, index=False)
    logger.info(f"Saved merged Parquet: {parquet_path}")
    
    # Save as CSV
    csv_path = processed_dir / "btc_updown_15m_90d_merged.csv"
    final_df.to_csv(csv_path, index=False)
    logger.info(f"Saved merged CSV: {csv_path}")
    
    # Print summary statistics
    logger.info("\n" + "="*60)
    logger.info("DATASET SUMMARY")
    logger.info("="*60)
    logger.info(f"Total markets: {final_df['slug'].nunique()}")
    logger.info(f"Total rows: {len(final_df)}")
    logger.info(f"Date range: {final_df['ts_utc'].min()} to {final_df['ts_utc'].max()}")
    logger.info(f"Average rows per market: {len(final_df) / final_df['slug'].nunique():.1f}")
    logger.info("="*60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build 90-day dataset for Polymarket BTC 15-minute Up/Down markets"
    )
    
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Number of days to scan backwards (default: 90)"
    )
    
    parser.add_argument(
        "--fidelity",
        type=int,
        default=1,
        help="Price history resolution in minutes (default: 1)"
    )
    
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=1,
        help="Hours to look back from epoch for price history (default: 1, focuses on active trading)"
    )
    
    parser.add_argument(
        "--lookforward-hours",
        type=float,
        default=0.5,
        help="Hours to look forward from epoch for price history (default: 0.5, captures resolution period)"
    )
    
    parser.add_argument(
        "--max-found",
        type=int,
        help="Maximum number of markets to fetch (for testing)"
    )
    
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force refresh, bypass cache"
    )
    
    args = parser.parse_args()
    
    logger.info("="*60)
    logger.info("POLYMARKET BTC 15-MINUTE UP/DOWN 90-DAY DATASET BUILDER")
    logger.info("="*60)
    logger.info(f"Days to scan: {args.days}")
    logger.info(f"Price fidelity: {args.fidelity} minutes")
    logger.info(f"Price window: -{args.lookback_hours}h to +{args.lookforward_hours}h around epoch")
    if args.max_found:
        logger.info(f"Max markets to fetch: {args.max_found}")
    if args.force_refresh:
        logger.info("Force refresh: ENABLED (bypassing cache)")
    logger.info("="*60)
    
    try:
        data_dir = Path(__file__).parent.parent / "data"
        cache_dir = data_dir / "cache" / "btc_15m"
        
        # Step 1: Load cache
        cache = {} if args.force_refresh else load_cache(cache_dir)
        
        # Step 2: Fetch markets from Gamma API
        if "markets" not in cache or not cache["markets"] or args.force_refresh:
            logger.info("\nFetching markets from Gamma API...")
            markets = fetch_all_btc_15m_markets(args.days)
            cache["markets"] = {m["slug"]: m for m in markets}
        else:
            logger.info("\nUsing cached markets")
            markets = list(cache["markets"].values())
        
        if not markets:
            logger.warning("No markets found")
            return 1
        
        # Step 3: Build epoch mapping
        epoch_map = build_epoch_mapping(markets)
        
        if not epoch_map:
            logger.warning("No valid markets in epoch mapping")
            return 1
        
        # Step 4: Fetch price histories
        markets_data = fetch_markets_data(
            epoch_map,
            args.fidelity,
            args.lookback_hours,
            args.lookforward_hours,
            args.max_found,
            cache
        )
        
        if not markets_data:
            logger.warning("No market data fetched")
            return 1
        
        # Step 5: Save cache
        save_cache(cache_dir, cache)
        
        # Step 6: Save per-slug data
        logger.info(f"\nSaving per-slug data to {data_dir}...")
        for i, market_data in enumerate(markets_data, 1):
            save_per_slug_data(market_data, data_dir)
            if i % 50 == 0:
                logger.info(f"Saved {i}/{len(markets_data)} markets")
        
        logger.info(f"Saved all {len(markets_data)} markets")
        
        # Step 7: Merge all markets
        merge_all_markets(markets_data, data_dir)
        
        logger.info("\n" + "="*60)
        logger.info("SUCCESS - Dataset build complete!")
        logger.info("="*60)
        
        return 0
    
    except Exception as e:
        logger.error(f"Failed to build dataset: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
