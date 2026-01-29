#!/usr/bin/env python3
"""
Fetch historical price data for Polymarket markets and convert to OHLC format.

This script fetches continuous price data and aggregates it into OHLC (Open, High, Low, Close)
candles at specified intervals. Useful for technical analysis and trading strategies.

Usage:
    # Fetch 15-minute OHLC candles for a BTC market
    python scripts/fetch_ohlc_data.py --slug btc-updown-15m-1765988100 --timeframe 15m --days 7
    
    # Fetch 1-hour OHLC candles with custom date range
    python scripts/fetch_ohlc_data.py --slug btc-updown-15m-1765988100 --timeframe 1h --start 2025-12-01 --end 2025-12-19
    
    # Use direct token IDs
    python scripts/fetch_ohlc_data.py --yes-token TOKEN1 --no-token TOKEN2 --timeframe 5m --days 30
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from dateutil import parser as date_parser

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
) -> requests.Response:
    """
    Make HTTP request with exponential backoff retry logic.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: Full URL
        params: Query parameters
        **kwargs: Additional requests arguments
    
    Returns:
        Response object
    
    Raises:
        requests.HTTPError: If all retries fail
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
            response.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return response
        
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            
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


def fetch_market_by_slug(slug: str) -> Dict[str, Any]:
    """
    Fetch market metadata from CLOB or Gamma API by slug.
    
    BTC 15m markets are not available in CLOB /markets endpoint,
    so we try Gamma API direct slug lookup as fallback.
    
    Args:
        slug: Market slug (e.g., "btc-updown-15m-1765988100")
    
    Returns:
        Market metadata dictionary
    """
    parts = slug.split("-")
    potential_condition_id = parts[-1] if parts else None
    
    logger.info(f"Searching for market with slug: {slug}")
    if potential_condition_id and potential_condition_id.isdigit():
        logger.info(f"Extracted potential condition_id: {potential_condition_id}")
    
    # Try CLOB API first
    url = f"{CLOB_API_BASE}/markets"
    response = request_with_retry("GET", url)
    data = response.json()
    
    markets = data.get("data", []) if isinstance(data, dict) else data
    logger.info(f"Fetched {len(markets)} markets from CLOB API")
    
    for market in markets:
        market_slug = market.get("slug", "")
        market_cond_id = str(market.get("condition_id", ""))
        
        if (market_slug == slug or 
            market_cond_id == potential_condition_id or
            market_cond_id == slug):
            logger.info(f"Found market in CLOB API: {market.get('question', 'N/A')}")
            logger.info(f"  Condition ID: {market_cond_id}")
            logger.info(f"  Slug: {market_slug}")
            return market
    
    # Fallback: Try Gamma API direct slug lookup (for BTC 15m markets)
    logger.info(f"Market not found in CLOB API, trying Gamma API direct lookup...")
    gamma_url = f"{GAMMA_API_BASE}/markets/slug/{slug}"
    
    try:
        gamma_response = request_with_retry("GET", gamma_url)
        if gamma_response and gamma_response.status_code == 200:
            market = gamma_response.json()
            logger.info(f"Found market in Gamma API: {market.get('question', 'N/A')}")
            logger.info(f"  Slug: {market.get('slug', 'N/A')}")
            return market
    except Exception as e:
        logger.warning(f"Gamma API lookup failed: {e}")
    
    raise ValueError(
        f"Market not found. Searched for slug='{slug}' "
        f"in CLOB API ({len(markets)} markets) and Gamma API direct lookup"
    )


def extract_token_ids(market: Dict[str, Any]) -> Tuple[str, str]:
    """
    Extract YES and NO token IDs from market metadata.
    
    Args:
        market: Market metadata dictionary from CLOB API
    
    Returns:
        Tuple of (yes_token_id, no_token_id)
    
    Raises:
        ValueError: If token IDs cannot be extracted
    """
    tokens_raw = market.get("tokens")
    
    if not tokens_raw:
        tokens_raw = market.get("clobTokenIds") or market.get("tokenIds")
    
    if not tokens_raw:
        raise ValueError("No token IDs found in market metadata")
    
    token_ids = []
    
    if isinstance(tokens_raw, list):
        token_ids = tokens_raw
    elif isinstance(tokens_raw, str):
        try:
            parsed = json.loads(tokens_raw)
            if isinstance(parsed, list):
                token_ids = parsed
            else:
                token_ids = [t.strip() for t in tokens_raw.split(",") if t.strip()]
        except json.JSONDecodeError:
            token_ids = [t.strip() for t in tokens_raw.split(",") if t.strip()]
    
    if len(token_ids) < 2:
        raise ValueError(f"Expected 2 token IDs, got {len(token_ids)}: {token_ids}")
    
    outcomes = market.get("outcomes")
    
    if outcomes and len(outcomes) >= 2:
        yes_idx = None
        no_idx = None
        
        for i, outcome in enumerate(outcomes):
            outcome_lower = str(outcome).lower()
            if "yes" in outcome_lower:
                yes_idx = i
            elif "no" in outcome_lower:
                no_idx = i
        
        if yes_idx is not None and no_idx is not None:
            logger.info(f"Mapped tokens using outcomes: YES={token_ids[yes_idx][:10]}..., NO={token_ids[no_idx][:10]}...")
            return token_ids[yes_idx], token_ids[no_idx]
    
    logger.info(f"Using default mapping: YES={token_ids[0][:10]}..., NO={token_ids[1][:10]}...")
    return token_ids[0], token_ids[1]


def fetch_price_history(
    token_id: str,
    start_ts: int,
    end_ts: int,
    fidelity: int = 1
) -> List[Dict[str, Any]]:
    """
    Fetch historical price data for a token from CLOB API.
    
    Args:
        token_id: CLOB token ID
        start_ts: Start timestamp (unix seconds)
        end_ts: End timestamp (unix seconds)
        fidelity: Resolution in minutes
    
    Returns:
        List of price points: [{"t": timestamp, "p": price}, ...]
    """
    url = f"{CLOB_API_BASE}/prices-history"
    
    params_variants = [
        {"market": token_id, "startTs": start_ts, "endTs": end_ts, "fidelity": fidelity},
        {"token_id": token_id, "startTs": start_ts, "endTs": end_ts, "fidelity": fidelity},
    ]
    
    logger.info(f"Fetching price history for token {token_id[:10]}... (fidelity: {fidelity}m)")
    
    for params in params_variants:
        try:
            response = request_with_retry("GET", url, params=params)
            data = response.json()
            
            if isinstance(data, list):
                logger.info(f"Fetched {len(data)} price points")
                return data
            elif isinstance(data, dict) and "history" in data:
                history = data["history"]
                logger.info(f"Fetched {len(history)} price points")
                return history
            else:
                logger.warning(f"Unexpected response format: {type(data)}")
                return []
        
        except requests.HTTPError:
            continue
    
    raise requests.HTTPError(f"Failed to fetch price history for token {token_id}")


def parse_timeframe(timeframe: str) -> int:
    """
    Parse timeframe string to minutes.
    
    Args:
        timeframe: Timeframe string (e.g., "1m", "5m", "15m", "1h", "4h", "1d")
    
    Returns:
        Number of minutes
    
    Raises:
        ValueError: If timeframe format is invalid
    """
    timeframe = timeframe.lower().strip()
    
    if timeframe.endswith('m'):
        return int(timeframe[:-1])
    elif timeframe.endswith('h'):
        return int(timeframe[:-1]) * 60
    elif timeframe.endswith('d'):
        return int(timeframe[:-1]) * 60 * 24
    else:
        raise ValueError(f"Invalid timeframe format: {timeframe}. Use format like '1m', '5m', '15m', '1h', '4h', '1d'")


def convert_to_ohlc(df: pd.DataFrame, timeframe_minutes: int, price_col: str = 'price') -> pd.DataFrame:
    """
    Convert price data to OHLC format.
    
    Args:
        df: DataFrame with 'timestamp' and price column
        timeframe_minutes: Timeframe in minutes for OHLC aggregation
        price_col: Name of the price column
    
    Returns:
        DataFrame with OHLC data
    """
    if df.empty:
        return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'count'])
    
    # Ensure timestamp is datetime
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
    
    # Set timestamp as index for resampling
    df = df.set_index('timestamp')
    
    # Resample to specified timeframe
    timeframe_str = f'{timeframe_minutes}T'  # T = minutes in pandas
    
    ohlc = df[price_col].resample(timeframe_str).agg([
        ('open', 'first'),
        ('high', 'max'),
        ('low', 'min'),
        ('close', 'last'),
        ('count', 'count')
    ])
    
    # Reset index to make timestamp a column again
    ohlc = ohlc.reset_index()
    
    # Drop rows with no data
    ohlc = ohlc[ohlc['count'] > 0]
    
    return ohlc


def parse_timestamp(ts: str) -> datetime:
    """
    Parse ISO date or unix timestamp to datetime.
    
    Args:
        ts: Timestamp as ISO string or unix seconds
    
    Returns:
        Datetime object (UTC)
    """
    try:
        return datetime.utcfromtimestamp(float(ts))
    except (ValueError, TypeError):
        return date_parser.parse(ts)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch Polymarket price data and convert to OHLC format"
    )
    
    parser.add_argument(
        "--slug",
        help="Market slug (e.g., btc-updown-15m-1765988100)"
    )
    
    parser.add_argument(
        "--condition-id",
        help="Market condition ID (alternative to slug)"
    )
    
    parser.add_argument(
        "--yes-token",
        help="YES token ID (if provided with --no-token, skips market lookup)"
    )
    
    parser.add_argument(
        "--no-token",
        help="NO token ID (if provided with --yes-token, skips market lookup)"
    )
    
    parser.add_argument(
        "--timeframe",
        default="15m",
        help="OHLC timeframe (e.g., 1m, 5m, 15m, 1h, 4h, 1d). Default: 15m"
    )
    
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days of history to fetch (default: 7)"
    )
    
    parser.add_argument(
        "--start",
        help="Start date (ISO format like '2025-09-17' or unix timestamp)"
    )
    
    parser.add_argument(
        "--end",
        help="End date (ISO format like '2025-12-17' or unix timestamp)"
    )
    
    parser.add_argument(
        "--fidelity",
        type=int,
        default=1,
        help="API fetch resolution in minutes (default: 1). Lower values give more granular data."
    )
    
    parser.add_argument(
        "--output-dir",
        help="Output directory for CSV files (default: data/ohlc)"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.slug and not args.condition_id and not (args.yes_token and args.no_token):
        parser.error("Must provide either --slug, --condition-id, or both --yes-token and --no-token")
    
    # Parse timeframe
    try:
        timeframe_minutes = parse_timeframe(args.timeframe)
    except ValueError as e:
        logger.error(str(e))
        return 1
    
    # Determine identifier for output files
    identifier = args.slug or args.condition_id or f"tokens_{args.yes_token[:8]}"
    
    # Determine time range
    if args.start and args.end:
        start_dt = parse_timestamp(args.start)
        end_dt = parse_timestamp(args.end)
    else:
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=args.days)
    
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    
    logger.info("="*60)
    logger.info("POLYMARKET OHLC DATA FETCHER")
    logger.info("="*60)
    logger.info(f"Identifier: {identifier}")
    logger.info(f"Date range: {start_dt.isoformat()} to {end_dt.isoformat()}")
    logger.info(f"API fidelity: {args.fidelity} minutes")
    logger.info(f"OHLC timeframe: {args.timeframe} ({timeframe_minutes} minutes)")
    logger.info("="*60)
    
    try:
        # Determine token IDs
        if args.yes_token and args.no_token:
            logger.info("Using directly provided token IDs")
            yes_token_id = args.yes_token
            no_token_id = args.no_token
            market_id = args.condition_id or "unknown"
            question = f"Market {identifier}"
        else:
            search_term = args.slug or args.condition_id
            market = fetch_market_by_slug(search_term)
            market_id = market.get("id") or market.get("condition_id")
            question = market.get("question", "N/A")
            yes_token_id, no_token_id = extract_token_ids(market)
        
        # Fetch price histories
        logger.info("\nFetching YES token history...")
        yes_history = fetch_price_history(yes_token_id, start_ts, end_ts, args.fidelity)
        
        logger.info("Fetching NO token history...")
        no_history = fetch_price_history(no_token_id, start_ts, end_ts, args.fidelity)
        
        # Convert to DataFrames
        yes_df = pd.DataFrame(yes_history)
        no_df = pd.DataFrame(no_history)
        
        if yes_df.empty and no_df.empty:
            logger.error("No price history available")
            return 1
        
        # Prepare data for OHLC conversion
        if not yes_df.empty:
            yes_df = yes_df.rename(columns={"t": "timestamp", "p": "price"})
        
        if not no_df.empty:
            no_df = no_df.rename(columns={"t": "timestamp", "p": "price"})
        
        # Convert to OHLC
        logger.info(f"\nConverting to {args.timeframe} OHLC candles...")
        
        yes_ohlc = convert_to_ohlc(yes_df, timeframe_minutes, 'price') if not yes_df.empty else pd.DataFrame()
        no_ohlc = convert_to_ohlc(no_df, timeframe_minutes, 'price') if not no_df.empty else pd.DataFrame()
        
        # Rename columns to indicate YES/NO
        if not yes_ohlc.empty:
            yes_ohlc = yes_ohlc.rename(columns={
                'open': 'yes_open',
                'high': 'yes_high',
                'low': 'yes_low',
                'close': 'yes_close',
                'count': 'yes_count'
            })
        
        if not no_ohlc.empty:
            no_ohlc = no_ohlc.rename(columns={
                'open': 'no_open',
                'high': 'no_high',
                'low': 'no_low',
                'close': 'no_close',
                'count': 'no_count'
            })
        
        # Merge YES and NO OHLC data
        if not yes_ohlc.empty and not no_ohlc.empty:
            merged_ohlc = pd.merge(yes_ohlc, no_ohlc, on='timestamp', how='outer')
        elif not yes_ohlc.empty:
            merged_ohlc = yes_ohlc
        else:
            merged_ohlc = no_ohlc
        
        merged_ohlc = merged_ohlc.sort_values('timestamp').reset_index(drop=True)
        
        logger.info(f"Generated {len(merged_ohlc)} OHLC candles")
        
        # Determine output directory
        if args.output_dir:
            output_dir = Path(args.output_dir)
        else:
            output_dir = Path(__file__).parent.parent / "data" / "ohlc"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save OHLC data to CSV
        output_filename = f"{identifier}_{args.timeframe}_ohlc.csv"
        output_path = output_dir / output_filename
        merged_ohlc.to_csv(output_path, index=False)
        logger.info(f"\nSaved OHLC data to: {output_path}")
        
        # Save metadata
        metadata = {
            "slug": identifier,
            "market_id": market_id,
            "question": question,
            "yes_token_id": yes_token_id,
            "no_token_id": no_token_id,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_iso": start_dt.isoformat(),
            "end_iso": end_dt.isoformat(),
            "api_fidelity": args.fidelity,
            "ohlc_timeframe": args.timeframe,
            "ohlc_timeframe_minutes": timeframe_minutes,
            "candles_count": len(merged_ohlc),
            "fetched_at": datetime.utcnow().isoformat() + "Z"
        }
        
        metadata_path = output_dir / f"{identifier}_{args.timeframe}_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        logger.info(f"Saved metadata to: {metadata_path}")
        
        # Display summary
        logger.info("\n" + "="*60)
        logger.info("SUMMARY")
        logger.info("="*60)
        logger.info(f"Market: {question}")
        logger.info(f"Timeframe: {args.timeframe}")
        logger.info(f"Candles generated: {len(merged_ohlc)}")
        logger.info(f"Date range: {merged_ohlc['timestamp'].min()} to {merged_ohlc['timestamp'].max()}")
        logger.info(f"\nOutput directory: {output_dir}")
        logger.info("="*60)
        
        # Show sample data
        if not merged_ohlc.empty:
            logger.info("\nSample OHLC data (first 5 rows):")
            print(merged_ohlc.head().to_string())
        
        return 0
    
    except Exception as e:
        logger.error(f"Failed to fetch OHLC data: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
