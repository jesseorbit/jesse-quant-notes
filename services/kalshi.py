"""
Kalshi data collector using their public API.

Documentation: https://docs.kalshi.com/
API Endpoint: https://api.elections.kalshi.com/trade-api/v2
Authentication: Optional API key for higher rate limits
"""

import logging
import os
import re
import time
import base64
import requests
from datetime import datetime
from typing import List, Dict, Any
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from models import StandardMarket
from utils.text_processing import normalize_title

logger = logging.getLogger(__name__)

KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"


class KalshiCollector:
    """Collector for Kalshi data."""
    
    def __init__(self, api_key: str = None, timeout: int = 30):
        """
        Initialize Kalshi collector.
        
        Args:
            api_key: Kalshi API key (optional, for authenticated requests)
            timeout: Request timeout in seconds
        """
        self.base_url = KALSHI_API_BASE
        self.timeout = timeout
        self.api_key = api_key or os.getenv("KALSHI_API_KEY")
        self.key_id = os.getenv("KALSHI_KEY_ID")
        self.private_key_content = os.getenv("KALSHI_PRIVATE_KEY")
        self.private_key = None
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ArbitrageScanner/1.0",
            "Accept": "application/json",
        })
        
        # Load Private Key if available
        if self.key_id and self.private_key_content:
            try:
                # Handle file path vs content
                if os.path.exists(self.private_key_content):
                    with open(self.private_key_content, "rb") as f:
                        key_data = f.read()
                else:
                    key_data = self.private_key_content.encode()
                
                self.private_key = serialization.load_pem_private_key(
                    key_data,
                    password=None
                )
                logger.info("Kalshi RSA authentication configured")
            except Exception as e:
                logger.error(f"Failed to load Kalshi private key: {e}")
                self.private_key = None
        
        # Fallback to simple API key if provided (legacy)
        if not self.private_key and self.api_key:
            self.session.headers.update({
                "Authorization": f"Bearer {self.api_key}"
            })
            logger.info("Kalshi API key configured (Legacy)")
        elif not self.private_key:
            logger.info("Kalshi running without authentication (public data only)")

    def _get_auth_headers(self, method: str, path: str) -> Dict[str, str]:
        """
        Generate RSA authentication headers.
        
        Args:
            method: HTTP method (e.g., "GET")
            path: Request path (e.g., "/trade-api/v2/markets")
            
        Returns:
            Dictionary of auth headers
        """
        if not self.private_key or not self.key_id:
            return {}
            
        timestamp = str(int(time.time() * 1000))
        msg_string = f"{timestamp}{method}{path}"
        
        signature = self.private_key.sign(
            msg_string.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": signature_b64
        }
    
    def fetch_active_markets(self, limit: int = None) -> List[StandardMarket]:
        """
        Fetch active markets from Kalshi.
        
        Args:
            limit: Maximum number of markets to fetch (None = all markets)
            
        Returns:
            List of StandardMarket objects
        """
        # Strip base URL to get path for signing
        path = "/trade-api/v2/markets"
        url = f"{self.base_url}/markets"
        
        all_markets = []
        cursor = None
        
        try:
            logger.info(f"Fetching Kalshi markets...")
            
            while True:
                params = {
                    "status": "open",
                    "limit": 1000,  # Kalshi max per request
                }
                
                if cursor:
                    params["cursor"] = cursor
                
                # Basic Rate Limiting
                # Public: 1s, Authenticated: 0.1s (10 requests/s)
                sleep_time = 0.1 if self.private_key else 1.0
                time.sleep(sleep_time)

                # Add auth headers if configured
                headers = self._get_auth_headers("GET", path)
                
                # Retry loop
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = self.session.get(
                            url, 
                            params=params, 
                            headers=headers, 
                            timeout=self.timeout
                        )
                        response.raise_for_status()
                        break
                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code == 429:
                            wait_time = (2 ** attempt) * 2  # Exponential backoff: 2, 4, 8...
                            logger.warning(f"Rate limited (429). Retrying in {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                        raise
                else:
                    logger.error("Max retries exceeded for Kalshi API")
                    break
                
                data = response.json()
                markets_data = data.get("markets", [])
                
                for market_data in markets_data:
                    try:
                        # Optimization: Skip markets with very low volume immediately
                        # This significantly reduces memory and downstream processing
                        volume = float(market_data.get("volume", 0) or 0)
                        if volume < 500: # Slightly lower than matcher threshold for safety
                            continue

                        # Optimization: Filter out past markets
                        close_time = market_data.get("close_time")
                        if close_time:
                            try:
                                end_dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                                now = datetime.now(end_dt.tzinfo)
                                if end_dt < now:
                                    continue
                            except:
                                pass

                        standard_market = self._parse_market(market_data)
                        if standard_market:
                            all_markets.append(standard_market)
                            
                            # Stop if we hit the limit
                            if limit and len(all_markets) >= limit:
                                break
                    except Exception as e:
                        logger.warning(f"Failed to parse market: {e}")
                        continue
                
                # Check if we should stop
                if limit and len(all_markets) >= limit:
                    break
                
                # Get next cursor for pagination
                cursor = data.get("cursor")
                
                # Stop if no more pages
                if not cursor:
                    break
                
                logger.debug(f"Fetched {len(all_markets)} markets so far, continuing...")
                
                # Safety break: Kalshi has 200k+ markets, if we still haven't finished 
                # after a reasonable amount of active markets, we might be in a loop
                if len(all_markets) > 50000:
                    logger.warning("Safety limit reached (50k markets). Stopping fetch.")
                    break
            
            logger.info(f"Fetched {len(all_markets)} Kalshi markets")
            return all_markets[:limit] if limit else all_markets
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch Kalshi markets: {e}")
            return []
    
    def _parse_market(self, market: Dict[str, Any]) -> StandardMarket:
        """
        Parse a single market from Kalshi API response.
        
        Args:
            market: Market data from API
            
        Returns:
            StandardMarket object or None if parsing fails
        """
        # Extract market ticker (ID)
        ticker = market.get("ticker")
        if not ticker:
            return None
        
        # Extract title
        title = market.get("title")
        if not title:
            return None
            
        # Append subtitle/candidate name if present to distinguish options
        # e.g., "Who will be Pope?" -> "Who will be Pope? - Pizzaballa"
        subtitle = market.get("yes_sub_title") or market.get("subtitle")
        if subtitle and subtitle.lower() not in title.lower():
            title = f"{title} - {subtitle}"
        
        # Extract prices - Kalshi uses cents (1-99)
        # Convert to 0.0-1.0 range
        
        # Priority: yes_ask (Best Ask for buyer) > last_price > yes_bid
        # User explicitly requested "lowest sell price" (Ask)
        yes_price_cents = market.get("yes_ask")
        
        if yes_price_cents is None:
            # Fallback to last price if no ask
            yes_price_cents = market.get("last_price")
            
            if yes_price_cents is None:
                 # Fallback to bid if no last price
                yes_price_cents = market.get("yes_bid")
            
            if yes_price_cents is None:
                # Ultimate fallback
                yes_price_cents = market.get("yes_price")

        if yes_price_cents is not None:
            price_yes = float(yes_price_cents) / 100.0
        else:
            # Fallback if absolutely no price info
            # logger.debug(f"No price info for {ticker}")
            price_yes = 0.5
        
        # Normalize range to avoid API data issues (e.g. 100 cents)
        price_yes = max(0.01, min(0.99, price_yes))
        
        # Calculate derived NO price
        price_no = 1.0 - price_yes
        
        # Extract volume
        volume = float(market.get("volume", 0) or 0)
        
        # Construct market URL
        # Kalshi uses format: /markets/{event_ticker}/{event_slug}/{market_ticker}
        # We can get event_ticker from the market response
        event_ticker = market.get("event_ticker", "")
        
        if event_ticker:
            # Simple URL: https://kalshi.com/markets/{event_ticker}
            # User request V6: https://kalshi.com/markets/{event_ticker}/{slug}/{ticker}
            # Slug generation
            slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
            url = f"https://kalshi.com/markets/{event_ticker}/{slug}/{ticker}"
        else:
            # Fallback to ticker
            url = f"https://kalshi.com/markets/{ticker}"
        
        # Normalize title
        normalized_title = normalize_title(title)
        
        # Extract End Date
        close_time = market.get("close_time")
        end_date = None
        if close_time:
            try:
                end_date = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
            except:
                pass

        return StandardMarket(
            platform="KALSHI",
            market_id=ticker,
            title=normalized_title,
            raw_title=title,
            price_yes=price_yes,
            price_no=price_no,
            volume=volume,
            url=url,
            end_date=end_date,
        )
