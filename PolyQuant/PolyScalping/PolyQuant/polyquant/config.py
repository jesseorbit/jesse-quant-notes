"""
Configuration module for PolyQuant.

Contains API endpoints, asset mappings, search patterns, and default parameters.
"""

from pathlib import Path
from typing import Dict, List

# API Base URLs
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"

# Asset keyword mappings for market discovery
ASSET_KEYWORDS: Dict[str, List[str]] = {
    "BTC": ["BTC", "Bitcoin"],
    "ETH": ["ETH", "Ethereum"],
    "SOL": ["SOL", "Solana"],
    "XRP": ["XRP", "Ripple"],
}

# Market search patterns
TIME_KEYWORDS = ["15"]  # Looking for "15" in question/description
TIME_UNIT_KEYWORDS = ["minute", "min"]  # Time unit indicators
DIRECTION_KEYWORDS = {
    "UP": ["Up", "up", "UP", "higher", "above"],
    "DOWN": ["Down", "down", "DOWN", "lower", "below"],
}

# Default parameters
DEFAULT_FIDELITY = 1  # 1-minute resolution
DEFAULT_PAGINATION_LIMIT = 100  # Number of markets to fetch per request
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "XRP"]
DEFAULT_MARKET_MINUTES = 15  # 15-minute markets

# Rate limiting
REQUEST_DELAY_SECONDS = 0.5  # Delay between API requests
RETRY_ATTEMPTS = 3  # Number of retry attempts for failed requests
RETRY_BACKOFF_BASE = 1.0  # Base delay for exponential backoff (seconds)

# Data directories (relative to project root)
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
METADATA_DIR = DATA_DIR / "metadata"

# Logging configuration
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
