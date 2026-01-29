"""
Historical data fetching module.

Fetches and merges YES/NO price histories for Polymarket markets.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd

from .clients.clob import ClobClient

logger = logging.getLogger(__name__)


def fetch_market_history(
    market_meta: Dict[str, Any],
    clob_client: ClobClient,
    start_ts: int,
    end_ts: int,
    fidelity: int = 1
) -> pd.DataFrame:
    """
    Fetch historical price data for a market (YES and NO tokens).
    
    Args:
        market_meta: Market metadata with yes_token_id and no_token_id
        clob_client: Initialized ClobClient instance
        start_ts: Start timestamp (unix seconds)
        end_ts: End timestamp (unix seconds)
        fidelity: Resolution in minutes
    
    Returns:
        DataFrame with columns: ts, yes_price, no_price, sum_price, mispricing
    """
    yes_token_id = market_meta["yes_token_id"]
    no_token_id = market_meta["no_token_id"]
    market_name = market_meta.get("question", "Unknown")
    
    logger.info(f"Fetching history for: {market_name}")
    
    # Fetch YES token history
    try:
        yes_history = clob_client.get_price_history(
            token_id=yes_token_id,
            start_ts=start_ts,
            end_ts=end_ts,
            fidelity=fidelity
        )
    except Exception as e:
        logger.error(f"Failed to fetch YES token history: {e}")
        yes_history = []
    
    # Fetch NO token history
    try:
        no_history = clob_client.get_price_history(
            token_id=no_token_id,
            start_ts=start_ts,
            end_ts=end_ts,
            fidelity=fidelity
        )
    except Exception as e:
        logger.error(f"Failed to fetch NO token history: {e}")
        no_history = []
    
    if not yes_history and not no_history:
        logger.warning(f"No price history available for {market_name}")
        return pd.DataFrame()
    
    # Convert to DataFrames
    yes_df = pd.DataFrame(yes_history)
    no_df = pd.DataFrame(no_history)
    
    # Rename columns (API returns 't' for timestamp, 'p' for price)
    if not yes_df.empty:
        yes_df = yes_df.rename(columns={"t": "ts", "p": "yes_price"})
        yes_df["ts"] = pd.to_datetime(yes_df["ts"], unit="s", utc=True)
    
    if not no_df.empty:
        no_df = no_df.rename(columns={"t": "ts", "p": "no_price"})
        no_df["ts"] = pd.to_datetime(no_df["ts"], unit="s", utc=True)
    
    # Merge on timestamp (outer join to keep all data points)
    if not yes_df.empty and not no_df.empty:
        merged = pd.merge(yes_df, no_df, on="ts", how="outer")
    elif not yes_df.empty:
        merged = yes_df
        merged["no_price"] = None
    elif not no_df.empty:
        merged = no_df
        merged["yes_price"] = None
    else:
        return pd.DataFrame()
    
    # Sort by timestamp
    merged = merged.sort_values("ts").reset_index(drop=True)
    
    # Calculate derived columns
    merged["sum_price"] = merged["yes_price"] + merged["no_price"]
    merged["mispricing"] = 1.0 - merged["sum_price"]
    
    logger.info(f"Merged {len(merged)} data points for {market_name}")
    
    return merged


def download_all_histories(
    markets_dict: Dict[str, Dict[str, Any]],
    clob_client: ClobClient,
    start: datetime,
    end: datetime,
    fidelity: int = 1
) -> Dict[str, pd.DataFrame]:
    """
    Download price histories for all discovered markets.
    
    Args:
        markets_dict: Dictionary of market metadata (from discover_15min_markets)
        clob_client: Initialized ClobClient instance
        start: Start datetime (UTC)
        end: End datetime (UTC)
        fidelity: Resolution in minutes
    
    Returns:
        Dictionary mapping market names to DataFrames
    """
    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    
    logger.info(
        f"Downloading histories for {len(markets_dict)} markets "
        f"from {start.isoformat()} to {end.isoformat()}"
    )
    
    histories = {}
    
    for market_name, market_meta in markets_dict.items():
        logger.info(f"Processing {market_name}...")
        
        try:
            df = fetch_market_history(
                market_meta=market_meta,
                clob_client=clob_client,
                start_ts=start_ts,
                end_ts=end_ts,
                fidelity=fidelity
            )
            
            if not df.empty:
                histories[market_name] = df
                logger.info(f"✓ Downloaded {len(df)} data points for {market_name}")
            else:
                logger.warning(f"✗ Empty history for {market_name}")
        
        except Exception as e:
            logger.error(f"✗ Failed to download history for {market_name}: {e}")
    
    logger.info(f"Download complete: {len(histories)}/{len(markets_dict)} markets")
    return histories
