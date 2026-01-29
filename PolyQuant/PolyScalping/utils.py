import sys
import time
import math
from datetime import datetime
from loguru import logger
from config import config

def setup_logging():
    """Configure loguru logging."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=config.log_level
    )
    logger.add(
        "polyscalping.log",
        rotation="10 MB",
        retention="1 week",
        level="DEBUG"
    )

def current_timestamp() -> float:
    """Return current timestamp in seconds."""
    return time.time()

def format_price(price: float) -> str:
    """Format price to 2 decimal places."""
    return f"{price:.2f}"

def format_pct(val: float) -> str:
    """Format float as percentage string."""
    return f"{val * 100:.2f}%"

def truncate(number: float, decimals: int = 2) -> float:
    """
    Returns a value truncated to a specific number of decimal places.
    """
    if not isinstance(decimals, int):
        raise TypeError("decimal places must be an integer.")
    elif decimals < 0:
        raise ValueError("decimal places has to be 0 or more.")
    elif decimals == 0:
        return math.trunc(number)

    factor = 10.0 ** decimals
    return math.trunc(number * factor) / factor
