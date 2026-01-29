#!/usr/bin/env python3
"""
Fetch historical YES/NO prices for a single Polymarket market.

Usage:
    python scripts/fetch_single_market_history.py --slug btc-updown-15m-1765988100 --days 90 --fidelity 1
    python scripts/fetch_single_market_history.py --slug btc-updown-15m-1765988100 --start 2025-09-17 --end 2025-12-17
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
    Fetch market metadata from CLOB API by slug.
    
    The slug format is typically: "asset-updown-15m-{condition_id}"
    We extract the condition_id and search for it.
    
    Args:
        slug: Market slug (e.g., "btc-updown-15m-1765988100")
    
    Returns:
        Market metadata dictionary
    """
    # Extract condition_id from slug (last part after final dash)
    parts = slug.split("-")
    potential_condition_id = parts[-1] if parts else None
    
    logger.info(f"Searching for market with slug: {slug}")
    if potential_condition_id and potential_condition_id.isdigit():
        logger.info(f"Extracted potential condition_id: {potential_condition_id}")
    
    url = f"{CLOB_API_BASE}/markets"
    response = request_with_retry("GET", url)
    data = response.json()
    
    # Handle response format
    markets = data.get("data", []) if isinstance(data, dict) else data
    logger.info(f"Fetched {len(markets)} markets from CLOB API")
    
    # Search for market by slug or condition_id
    for market in markets:
        market_slug = market.get("slug", "")
        market_cond_id = str(market.get("condition_id", ""))
        
        # Match by slug or condition_id
        if (market_slug == slug or 
            market_cond_id == potential_condition_id or
            market_cond_id == slug):
            logger.info(f"Found market: {market.get('question', 'N/A')}")
            logger.info(f"  Condition ID: {market_cond_id}")
            logger.info(f"  Slug: {market_slug}")
            return market
    
    raise ValueError(
        f"Market not found. Searched for slug='{slug}' "
        f"and condition_id='{potential_condition_id}' in {len(markets)} markets"
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
    # CLOB API uses "tokens" field
    tokens_raw = market.get("tokens")
    
    # Fallback to other possible field names
    if not tokens_raw:
        tokens_raw = market.get("clobTokenIds") or market.get("tokenIds")
    
    if not tokens_raw:
        raise ValueError("No token IDs found in market metadata")
    
    # Parse token IDs
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
    
    # Map to YES/NO using outcomes
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
    
    # Default: first = YES, second = NO
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
    
    # Try both parameter names
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


def parse_timestamp(ts: str) -> datetime:
    """
    Parse ISO date or unix timestamp to datetime.
    
    Args:
        ts: Timestamp as ISO string or unix seconds
    
    Returns:
        Datetime object (UTC)
    """
    try:
        # Try parsing as unix timestamp
        return datetime.utcfromtimestamp(float(ts))
    except (ValueError, TypeError):
        # Try parsing as ISO date
        return date_parser.parse(ts)


def save_raw_csv(token_id: str, direction: str, df: pd.DataFrame, slug: str, base_dir: Path):
    """Save raw token history to CSV."""
    filename = f"{slug}_{direction}.csv"
    path = base_dir / "raw" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logger.info(f"Saved raw {direction} data: {path}")


def save_merged_csv(df: pd.DataFrame, slug: str, base_dir: Path):
    """Save merged YES/NO history to CSV."""
    filename = f"{slug}_merged.csv"
    path = base_dir / "processed" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logger.info(f"Saved merged data: {path}")


def save_metadata(metadata: Dict[str, Any], slug: str, base_dir: Path):
    """Save market metadata to JSON."""
    filename = f"{slug}.json"
    path = base_dir / "metadata" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, "w") as f:
        json.dump(metadata, f, indent=2)
    
    logger.info(f"Saved metadata: {path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch historical YES/NO prices for a Polymarket market"
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
        "--days",
        type=int,
        default=90,
        help="Number of days of history to fetch (default: 90)"
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
        help="Resolution in minutes (default: 1)"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.slug and not args.condition_id and not (args.yes_token and args.no_token):
        parser.error("Must provide either --slug, --condition-id, or both --yes-token and --no-token")
    
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
    logger.info("POLYMARKET SINGLE MARKET HISTORY FETCHER")
    logger.info("="*60)
    logger.info(f"Identifier: {identifier}")
    logger.info(f"Date range: {start_dt.isoformat()} to {end_dt.isoformat()}")
    logger.info(f"Fidelity: {args.fidelity} minutes")
    logger.info("="*60)
    
    try:
        # Determine token IDs
        if args.yes_token and args.no_token:
            # Direct token IDs provided
            logger.info("Using directly provided token IDs")
            yes_token_id = args.yes_token
            no_token_id = args.no_token
            market_id = args.condition_id or "unknown"
            question = f"Market {identifier}"
        else:
            # Fetch market metadata
            search_term = args.slug or args.condition_id
            market = fetch_market_by_slug(search_term)
            market_id = market.get("id") or market.get("condition_id")
            question = market.get("question", "N/A")
            
            # Extract token IDs
            yes_token_id, no_token_id = extract_token_ids(market)
        
        # Step 3: Fetch price histories
        logger.info("\nFetching YES token history...")
        yes_history = fetch_price_history(yes_token_id, start_ts, end_ts, args.fidelity)
        
        logger.info("Fetching NO token history...")
        no_history = fetch_price_history(no_token_id, start_ts, end_ts, args.fidelity)
        
        # Step 4: Convert to DataFrames
        yes_df = pd.DataFrame(yes_history)
        no_df = pd.DataFrame(no_history)
        
        if not yes_df.empty:
            yes_df = yes_df.rename(columns={"t": "ts", "p": "yes_price"})
            yes_df["ts"] = pd.to_datetime(yes_df["ts"], unit="s", utc=True)
        
        if not no_df.empty:
            no_df = no_df.rename(columns={"t": "ts", "p": "no_price"})
            no_df["ts"] = pd.to_datetime(no_df["ts"], unit="s", utc=True)
        
        # Step 5: Merge and calculate derived columns
        if not yes_df.empty and not no_df.empty:
            merged = pd.merge(yes_df, no_df, on="ts", how="outer")
        elif not yes_df.empty:
            merged = yes_df
            merged["no_price"] = None
        elif not no_df.empty:
            merged = no_df
            merged["yes_price"] = None
        else:
            logger.error("No price history available")
            return 1
        
        merged = merged.sort_values("ts").reset_index(drop=True)
        merged["sum_price"] = merged["yes_price"] + merged["no_price"]
        merged["mispricing"] = 1.0 - merged["sum_price"]
        
        logger.info(f"\nMerged {len(merged)} data points")
        
        # Step 6: Save data
        data_dir = Path(__file__).parent.parent / "data"
        
        # Save raw data
        if not yes_df.empty:
            save_raw_csv(yes_token_id, "YES", yes_df, identifier, data_dir)
        if not no_df.empty:
            save_raw_csv(no_token_id, "NO", no_df, identifier, data_dir)
        
        # Save merged data
        save_merged_csv(merged, identifier, data_dir)
        
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
            "fidelity": args.fidelity,
            "yes_rows": len(yes_df),
            "no_rows": len(no_df),
            "merged_rows": len(merged),
            "fetched_at": datetime.utcnow().isoformat() + "Z"
        }
        save_metadata(metadata, identifier, data_dir)
        
        # Summary
        logger.info("\n" + "="*60)
        logger.info("SUMMARY")
        logger.info("="*60)
        logger.info(f"Market: {question}")
        logger.info(f"YES token rows: {len(yes_df)}")
        logger.info(f"NO token rows: {len(no_df)}")
        logger.info(f"Merged rows: {len(merged)}")
        logger.info(f"\nFiles saved to: {data_dir}")
        logger.info("="*60)
        
        return 0
    
    except Exception as e:
        logger.error(f"Failed to fetch market history: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
