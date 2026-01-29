"""
Market discovery module.

Implements robust algorithm to find 15-minute Up/Down markets for specified assets.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import config
from .clients.gamma import GammaClient

logger = logging.getLogger(__name__)


def extract_token_ids(market: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """
    Extract YES and NO token IDs from a Gamma market object.
    
    Handles multiple formats:
    - JSON array: ["0xabc...", "0xdef..."]
    - JSON-encoded string: '["0xabc...", "0xdef..."]'
    - Comma-separated string: "0xabc...,0xdef..."
    
    Args:
        market: Gamma market dictionary
    
    Returns:
        Tuple of (yes_token_id, no_token_id)
    """
    tokens_raw = market.get("tokens") or market.get("clobTokenIds")
    
    if not tokens_raw:
        logger.warning(f"No token IDs found in market: {market.get('question', 'Unknown')}")
        return None, None
    
    # Parse token IDs
    token_ids = []
    
    if isinstance(tokens_raw, list):
        # Already a list
        token_ids = tokens_raw
    elif isinstance(tokens_raw, str):
        # Try parsing as JSON
        try:
            parsed = json.loads(tokens_raw)
            if isinstance(parsed, list):
                token_ids = parsed
            else:
                logger.warning(f"Unexpected JSON format: {type(parsed)}")
        except json.JSONDecodeError:
            # Try comma-separated
            token_ids = [t.strip() for t in tokens_raw.split(",") if t.strip()]
    
    if len(token_ids) < 2:
        logger.warning(
            f"Expected 2 token IDs, got {len(token_ids)} for market: "
            f"{market.get('question', 'Unknown')}"
        )
        return None, None
    
    # Map to YES/NO using outcomes if available
    outcomes = market.get("outcomes")
    
    if outcomes and len(outcomes) >= 2:
        # Try to match "Yes" and "No" in outcomes
        yes_idx = None
        no_idx = None
        
        for i, outcome in enumerate(outcomes):
            outcome_lower = str(outcome).lower()
            if "yes" in outcome_lower:
                yes_idx = i
            elif "no" in outcome_lower:
                no_idx = i
        
        if yes_idx is not None and no_idx is not None:
            return token_ids[yes_idx], token_ids[no_idx]
        else:
            logger.warning(
                f"Could not map outcomes to YES/NO: {outcomes}. "
                f"Using default mapping (first=YES, second=NO)"
            )
    
    # Default: first token = YES, second token = NO
    return token_ids[0], token_ids[1]


def matches_asset_keywords(text: str, asset: str) -> bool:
    """
    Check if text contains keywords for the specified asset.
    
    Args:
        text: Text to search (question or description)
        asset: Asset code (BTC, ETH, SOL, XRP)
    
    Returns:
        True if any asset keyword is found
    """
    text_lower = text.lower()
    keywords = config.ASSET_KEYWORDS.get(asset, [])
    
    return any(keyword.lower() in text_lower for keyword in keywords)


def matches_time_keywords(text: str) -> bool:
    """
    Check if text contains 15-minute time keywords.
    
    Args:
        text: Text to search
    
    Returns:
        True if "15" and ("minute" or "min") are found
    """
    text_lower = text.lower()
    
    # Check for "15"
    has_fifteen = any(time_kw in text_lower for time_kw in config.TIME_KEYWORDS)
    
    # Check for time unit
    has_time_unit = any(unit_kw in text_lower for unit_kw in config.TIME_UNIT_KEYWORDS)
    
    return has_fifteen and has_time_unit


def matches_direction_keywords(text: str, direction: str) -> bool:
    """
    Check if text contains direction keywords (Up or Down).
    
    Args:
        text: Text to search
        direction: "UP" or "DOWN"
    
    Returns:
        True if any direction keyword is found
    """
    text_lower = text.lower()
    keywords = config.DIRECTION_KEYWORDS.get(direction, [])
    
    return any(keyword.lower() in text_lower for keyword in keywords)


def select_best_market(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Select the best market from candidates.
    
    Preference order:
    1. Highest liquidity/volume if available
    2. Most recently active market
    3. First valid candidate
    
    Args:
        candidates: List of candidate markets
    
    Returns:
        Best market or None if no candidates
    """
    if not candidates:
        return None
    
    # Try to select by liquidity
    markets_with_liquidity = [
        m for m in candidates
        if m.get("liquidity") is not None or m.get("volume") is not None
    ]
    
    if markets_with_liquidity:
        # Sort by liquidity (descending)
        sorted_markets = sorted(
            markets_with_liquidity,
            key=lambda m: float(m.get("liquidity") or m.get("volume") or 0),
            reverse=True
        )
        logger.debug(f"Selected market by liquidity: {sorted_markets[0].get('question')}")
        return sorted_markets[0]
    
    # Try to select by most recent activity
    markets_with_end_date = [
        m for m in candidates
        if m.get("endDate") is not None or m.get("end_date_iso") is not None
    ]
    
    if markets_with_end_date:
        # Sort by end date (descending)
        sorted_markets = sorted(
            markets_with_end_date,
            key=lambda m: m.get("endDate") or m.get("end_date_iso") or "",
            reverse=True
        )
        logger.debug(f"Selected market by recency: {sorted_markets[0].get('question')}")
        return sorted_markets[0]
    
    # Default: first candidate
    logger.debug(f"Selected first candidate: {candidates[0].get('question')}")
    return candidates[0]


def discover_15min_markets(
    assets: List[str],
    gamma_client: GammaClient,
    max_markets: int = 2000,
    active_only: bool = True
) -> Dict[str, Dict[str, Any]]:
    """
    Discover Up/Down markets for specified assets.
    
    Note: These markets don't explicitly mention "15 minutes" in their questions.
    They use patterns like "bitcoin up and down December 17,12-12:15AM ET".
    We search for markets containing asset keywords + "up" or "down".
    
    Args:
        assets: List of asset codes (e.g., ["BTC", "ETH", "SOL", "XRP"])
        gamma_client: Initialized GammaClient instance
        max_markets: Maximum number of markets to fetch from API
    
    Returns:
        Dictionary mapping market names to metadata:
        {
            "BTC_UP": {
                "market_id": "...",
                "slug": "...",
                "question": "...",
                "yes_token_id": "0x...",
                "no_token_id": "0x...",
                "discovered_at": "2025-12-17T13:20:30Z"
            },
            ...
        }
    """
    logger.info(f"Discovering Up/Down markets for assets: {assets}")
    
    # Fetch all markets
    filters = {}
    if active_only:
        filters["closed"] = False
        
    all_markets = gamma_client.get_all_markets(max_markets=max_markets, **filters)
    logger.info(f"Fetched {len(all_markets)} total markets")
    
    discovered = {}
    
    for asset in assets:
        logger.info(f"Searching for {asset} markets...")
        
        # Find candidates for UP and DOWN
        up_candidates = []
        down_candidates = []
        
        for market in all_markets:
            question = market.get("question", "")
            description = market.get("description", "")
            combined_text = f"{question} {description}"

            # Filter by active status if requested
            if active_only:
                # check if market is closed/resolved
                if market.get("closed"):
                    continue
                    
                # check end date
                end_date_str = market.get("endDate") or market.get("end_date_iso")
                if end_date_str:
                    try:
                        # Handle ISO format variations (sometimes with Z, sometimes without)
                        if end_date_str.endswith("Z"):
                            end_date_str = end_date_str[:-1]
                        
                        # Handle potential fractional seconds
                        if "." in end_date_str:
                             end_date_str = end_date_str.split(".")[0]
                             
                        end_date = datetime.fromisoformat(end_date_str)
                        if end_date < datetime.utcnow():
                            continue
                    except (ValueError, TypeError):
                        logger.warning(f"Could not parse end date: {end_date_str}")
                        pass
            
            
            # Note: We removed enableOrderBook and closed filters because:
            # 1. enableOrderBook is not reliably set in API responses (often N/A)
            # 2. Most crypto Up/Down markets are short-duration and close quickly
            # Users can filter by these fields later if needed.
            
            # Check for asset keywords
            if not matches_asset_keywords(combined_text, asset):
                continue
            
            # Check for direction
            if matches_direction_keywords(combined_text, "UP"):
                up_candidates.append(market)
            if matches_direction_keywords(combined_text, "DOWN"):
                down_candidates.append(market)
        
        logger.info(f"Found {len(up_candidates)} UP candidates and {len(down_candidates)} DOWN candidates for {asset}")
        
        # Select best UP market
        best_up = select_best_market(up_candidates)
        if best_up:
            yes_token, no_token = extract_token_ids(best_up)
            
            if yes_token and no_token:
                discovered[f"{asset}_UP"] = {
                    "market_id": best_up.get("id") or best_up.get("condition_id"),
                    "slug": best_up.get("slug"),
                    "question": best_up.get("question"),
                    "description": best_up.get("description"),
                    "yes_token_id": yes_token,
                    "no_token_id": no_token,
                    "discovered_at": datetime.utcnow().isoformat() + "Z",
                }
                logger.info(f"✓ Discovered {asset}_UP: {best_up.get('question')}")
            else:
                logger.warning(f"✗ Failed to extract token IDs for {asset}_UP")
        else:
            logger.warning(f"✗ No UP market found for {asset}")
        
        # Select best DOWN market
        best_down = select_best_market(down_candidates)
        if best_down:
            yes_token, no_token = extract_token_ids(best_down)
            
            if yes_token and no_token:
                discovered[f"{asset}_DOWN"] = {
                    "market_id": best_down.get("id") or best_down.get("condition_id"),
                    "slug": best_down.get("slug"),
                    "question": best_down.get("question"),
                    "description": best_down.get("description"),
                    "yes_token_id": yes_token,
                    "no_token_id": no_token,
                    "discovered_at": datetime.utcnow().isoformat() + "Z",
                }
                logger.info(f"✓ Discovered {asset}_DOWN: {best_down.get('question')}")
            else:
                logger.warning(f"✗ Failed to extract token IDs for {asset}_DOWN")
        else:
            logger.warning(f"✗ No DOWN market found for {asset}")
    
    logger.info(f"Discovery complete: {len(discovered)}/{len(assets) * 2} markets found")
    return discovered
