"""
Utility functions for PolyQuant.

Provides logging setup, timestamp parsing, directory management, and filename sanitization.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Union

from dateutil import parser as date_parser

from . import config


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Configure structured logging with timestamps.
    
    Args:
        level: Logging level (default: INFO)
    
    Returns:
        Configured logger instance
    """
    logging.basicConfig(
        level=level,
        format=config.LOG_FORMAT,
        datefmt=config.LOG_DATE_FORMAT,
    )
    logger = logging.getLogger("polyquant")
    return logger


def parse_timestamp(ts: Union[str, int, float]) -> datetime:
    """
    Convert ISO dates or unix timestamps to datetime.
    
    Args:
        ts: Timestamp as ISO string (e.g., "2025-12-01") or unix seconds
    
    Returns:
        Datetime object (UTC)
    
    Raises:
        ValueError: If timestamp format is invalid
    """
    if isinstance(ts, (int, float)):
        return datetime.utcfromtimestamp(ts)
    
    if isinstance(ts, str):
        # Try parsing as ISO date first
        try:
            return date_parser.parse(ts)
        except Exception as e:
            # Try parsing as unix timestamp string
            try:
                return datetime.utcfromtimestamp(float(ts))
            except Exception:
                raise ValueError(f"Invalid timestamp format: {ts}") from e
    
    raise ValueError(f"Unsupported timestamp type: {type(ts)}")


def ensure_directories() -> None:
    """
    Create data directories if they don't exist.
    
    Creates:
        - data/raw
        - data/processed
        - data/metadata
    """
    config.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.METADATA_DIR.mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    """
    Sanitize market names for filesystem.
    
    Args:
        name: Market name or identifier
    
    Returns:
        Filesystem-safe filename
    """
    # Replace spaces and special characters with underscores
    safe = re.sub(r'[^\w\-_]', '_', name)
    # Remove consecutive underscores
    safe = re.sub(r'_+', '_', safe)
    # Remove leading/trailing underscores
    safe = safe.strip('_')
    return safe


def timestamp_to_unix(dt: datetime) -> int:
    """
    Convert datetime to unix timestamp (seconds).
    
    Args:
        dt: Datetime object
    
    Returns:
        Unix timestamp in seconds
    """
    return int(dt.timestamp())
