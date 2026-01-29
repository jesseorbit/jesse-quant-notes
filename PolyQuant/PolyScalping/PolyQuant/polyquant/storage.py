"""
Data storage module.

Handles saving raw and processed time series data in CSV and Parquet formats,
plus metadata in JSON.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from . import config
from .utils import safe_filename

logger = logging.getLogger(__name__)


def save_raw_history(
    market_name: str,
    token_id: str,
    direction: str,
    df: pd.DataFrame,
    base_path: Path = config.RAW_DATA_DIR
) -> None:
    """
    Save individual YES/NO token history to raw data directory.
    
    Args:
        market_name: Market identifier (e.g., "BTC_15m_UP")
        token_id: Token ID for reference
        direction: "YES" or "NO"
        df: DataFrame with columns: ts, price
        base_path: Base directory for raw data
    """
    if df.empty:
        logger.warning(f"Skipping empty DataFrame for {market_name}_{direction}")
        return
    
    safe_name = safe_filename(market_name)
    filename_base = f"{safe_name}_{direction}"
    
    # Save CSV
    csv_path = base_path / f"{filename_base}.csv"
    df.to_csv(csv_path, index=False)
    logger.info(f"Saved raw CSV: {csv_path}")
    
    # Save Parquet
    parquet_path = base_path / f"{filename_base}.parquet"
    df.to_parquet(parquet_path, index=False)
    logger.info(f"Saved raw Parquet: {parquet_path}")


def save_processed_history(
    market_name: str,
    df: pd.DataFrame,
    base_path: Path = config.PROCESSED_DATA_DIR
) -> None:
    """
    Save merged time series to processed data directory.
    
    Args:
        market_name: Market identifier (e.g., "BTC_15m_UP")
        df: DataFrame with columns: ts, yes_price, no_price, sum_price, mispricing
        base_path: Base directory for processed data
    """
    if df.empty:
        logger.warning(f"Skipping empty DataFrame for {market_name}")
        return
    
    safe_name = safe_filename(market_name)
    
    # Save CSV
    csv_path = base_path / f"{safe_name}.csv"
    df.to_csv(csv_path, index=False)
    logger.info(f"Saved processed CSV: {csv_path}")
    
    # Save Parquet
    parquet_path = base_path / f"{safe_name}.parquet"
    df.to_parquet(parquet_path, index=False)
    logger.info(f"Saved processed Parquet: {parquet_path}")


def save_metadata(
    markets_dict: Dict[str, Dict[str, Any]],
    query_params: Dict[str, Any],
    base_path: Path = config.METADATA_DIR
) -> None:
    """
    Save market metadata and query parameters to JSON.
    
    Args:
        markets_dict: Dictionary of market metadata
        query_params: Query parameters used (start, end, fidelity, etc.)
        base_path: Base directory for metadata
    """
    metadata = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "query_params": query_params,
        "markets": markets_dict,
    }
    
    metadata_path = base_path / "markets.json"
    
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    
    logger.info(f"Saved metadata: {metadata_path}")


def load_metadata(base_path: Path = config.METADATA_DIR) -> Dict[str, Any]:
    """
    Load market metadata from JSON.
    
    Args:
        base_path: Base directory for metadata
    
    Returns:
        Metadata dictionary or empty dict if not found
    """
    metadata_path = base_path / "markets.json"
    
    if not metadata_path.exists():
        logger.warning(f"Metadata file not found: {metadata_path}")
        return {}
    
    with open(metadata_path, "r") as f:
        metadata = json.load(f)
    
    logger.info(f"Loaded metadata from: {metadata_path}")
    return metadata


def save_all_histories(
    histories: Dict[str, pd.DataFrame],
    markets_dict: Dict[str, Dict[str, Any]],
    query_params: Dict[str, Any]
) -> None:
    """
    Save all histories (raw and processed) plus metadata.
    
    Args:
        histories: Dictionary mapping market names to DataFrames
        markets_dict: Dictionary of market metadata
        query_params: Query parameters used
    """
    logger.info(f"Saving {len(histories)} market histories...")
    
    for market_name, df in histories.items():
        # Save processed (merged) data
        save_processed_history(market_name, df)
        
        # Save raw YES and NO data separately
        if "yes_price" in df.columns:
            yes_df = df[["ts", "yes_price"]].rename(columns={"yes_price": "price"})
            yes_token_id = markets_dict[market_name]["yes_token_id"]
            save_raw_history(market_name, yes_token_id, "YES", yes_df)
        
        if "no_price" in df.columns:
            no_df = df[["ts", "no_price"]].rename(columns={"no_price": "price"})
            no_token_id = markets_dict[market_name]["no_token_id"]
            save_raw_history(market_name, no_token_id, "NO", no_df)
    
    # Save metadata
    save_metadata(markets_dict, query_params)
    
    logger.info("All data saved successfully")
