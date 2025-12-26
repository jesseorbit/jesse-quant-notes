"""
Opinion Labs data collector using their public API.

Documentation: https://docs.opinion.trade/api
API Endpoint: https://proxy.opinion.trade:8443/openapi/market
Authentication: Requires API key in 'apikey' header
"""

import logging
import os
import subprocess
import json
import concurrent.futures
from urllib.parse import urlencode
from datetime import datetime
from typing import List, Dict, Any, Optional
from models import StandardMarket
from utils.text_processing import normalize_title

logger = logging.getLogger(__name__)

OPINION_API_BASE = "https://proxy.opinion.trade:8443/openapi"


class OpinionCollector:
    """Collector for Opinion Labs data."""
    
    def __init__(self, api_key: Optional[str] = None, timeout: int = 30):
        """
        Initialize Opinion Labs collector.
        
        Args:
            api_key: Opinion Labs API key (or set OPINION_API_KEY env var)
            timeout: Request timeout in seconds
        """
        self.base_url = OPINION_API_BASE
        self.timeout = timeout
        
        # Get API key from parameter or environment variable
        self.api_key = api_key or os.getenv("OPINION_API_KEY")
        
        if self.api_key:
            logger.info("Opinion Labs API key configured")
        else:
            logger.warning(
                "No Opinion Labs API key provided. "
                "Set OPINION_API_KEY environment variable or pass api_key parameter. "
                "Get your API key at: https://docs.opinion.trade/"
            )

    def _curl_get(self, url: str, params: Dict = None) -> Dict:
        """
        Execute GET request using system curl to bypass Python/LibreSSL issues.
        """
        full_url = url
        if params:
            full_url = f"{url}?{urlencode(params)}"
            
        cmd = [
            "curl", "-s",  # Silent mode
            "-H", f"User-Agent: ArbitrageScanner/1.0",
            "-H", "Accept: application/json",
        ]
        
        if self.api_key:
            cmd.extend(["-H", f"apikey: {self.api_key}"])
            
        cmd.append(full_url)
        
        try:
            # logger.debug(f"Executing curl: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            if result.returncode != 0:
                logger.error(f"Curl failed: {result.stderr}")
                return {}
                
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning(f"Failed to decode JSON from curl response (len={len(result.stdout)})")
            return {}
        except Exception as e:
            logger.error(f"Curl execution error: {e}")
            return {}
    
    def fetch_active_markets(self, limit: int = 100) -> List[StandardMarket]:
        """
        Fetch active markets from Opinion Labs with pagination.
        
        Args:
            limit: Maximum number of markets to fetch (approximate)
            
        Returns:
            List of StandardMarket objects
        """
        # Opinion Labs endpoint: /openapi/market
        url = f"{self.base_url}/market"
        
        all_markets = []
        market_token_map = {} # Map market_id -> (yes_token_id, no_token_id, market_obj)
        
        page = 1
        page_size = 100
        empty_retries = 0
        
        logger.info(f"Fetching Opinion Labs markets via active curl...")
        
        if not self.api_key:
            logger.error("Cannot fetch markets: API key not configured")
            return []
            
        try:
            while True:
                params = {
                    "limit": page_size,
                    "page": page
                }
                
                # Fetch via curl
                data = self._curl_get(url, params)
                
                # Extract list
                if isinstance(data, dict):
                    result = data.get("result", {})
                    if isinstance(result, dict) and "list" in result:
                        markets_data = result["list"]
                    else:
                        markets_data = data.get("markets", data.get("data", []))
                else:
                    markets_data = data
                
                if not markets_data:
                    empty_retries += 1
                    if empty_retries >= 3:
                        break
                    page += 1
                    continue
                    
                # Parse current page
                page_active_count = 0
                for market_data in markets_data:
                    # Client-side status filter
                    # status: 2 = Activated
                    if market_data.get("status") != 2:
                        continue
                    
                    try:
                        standard_market = self._parse_market(market_data)
                        if standard_market:
                            all_markets.append(standard_market)
                            page_active_count += 1
                            
                            # Store token IDs for price fetching
                            yes_token_id = market_data.get("yesTokenId")
                            no_token_id = market_data.get("noTokenId")
                            if yes_token_id:
                                market_token_map[standard_market.market_id] = (yes_token_id, no_token_id, standard_market)
                    except Exception as e:
                        logger.warning(f"Failed to parse market: {e}")
                        continue
                
                logger.debug(f"Fetched page {page}: {len(markets_data)} raw, {page_active_count} active. Total: {len(all_markets)}")
                
                if limit and len(all_markets) >= limit:
                    break
                    
                page += 1
                if page > 50: # Safety break
                    break
                
            # 2. Fetch prices in parallel for ALL collected markets
            if all_markets:
                logger.info(f"Fetching prices for {len(market_token_map)} markets (via curl)...")
                self._fetch_prices_parallel(market_token_map)
            
            logger.info(f"Fetched {len(all_markets)} Opinion Labs markets total")
            return all_markets[:limit] if limit else all_markets
            
        except Exception as e:
            logger.error(f"Failed to fetch Opinion Labs markets: {e}")
            return []
            
    def _fetch_prices_parallel(self, market_token_map: Dict[str, tuple]):
        """Fetch prices for multiple markets in parallel threads."""
        
        def fetch_single_price(market_info):
            market_id, (yes_token_id, no_token_id, market_obj) = market_info
            price_url = f"{self.base_url}/token/latest-price"
            
            # Simple retry backoff
            retries = 3
            for attempt in range(retries):
                try:
                    # Random small sleep to jitter requests
                    import time
                    import random
                    if attempt > 0:
                        time.sleep(0.5 * attempt + random.random() * 0.5)
                    else:
                        time.sleep(random.random() * 0.2) # Initial jitter
                        
                    data = self._curl_get(price_url, params={"token_id": yes_token_id})
                    
                    # Check for rate limit message explicitly
                    if isinstance(data, dict) and 'message' in data:
                        msg = data['message'].lower()
                        if 'rate limit' in msg or 'too many' in msg:
                            # logger.warning(f"Rate limit hit for {market_id}, retrying ({attempt+1}/{retries})")
                            time.sleep(1 + attempt) # Exponentialish backoff
                            continue

                    # Response: {"result": {"price": "0.65", ...}}
                    result = data.get("result", {})
                    if result:
                        price_val = result.get("price")
                        if price_val:
                            price = float(price_val)
                            object.__setattr__(market_obj, 'price_yes', price)
                            object.__setattr__(market_obj, 'price_no', 1.0 - price)
                            # Success, break retry loop
                            break
                        else:
                            # Empty result but no error, maybe just no data
                            break
                    else:
                        # Empty result, could be transient
                        pass
                        
                except Exception as e:
                    logger.error(f"Error fetching price for {market_id}: {e}")
                    pass

        # Use ThreadPoolExecutor
        # Reduce concurrency to avoid rate limits
        logger.info("Starting threaded price fetch (workers=2)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(fetch_single_price, market_token_map.items()))
        logger.info("Price fetch completed.")

    
    def _parse_market(self, market: Dict[str, Any]) -> StandardMarket:
        """
        Parse a single market from Opinion API response.
        
        Args:
            market: Market data from API
            
        Returns:
            StandardMarket object or None if parsing fails
        """
        # Extract market ID
        market_id = str(market.get("marketId") or market.get("id"))
        if not market_id:
            return None
        
        # Extract title
        title = market.get("marketTitle") or market.get("question") or market.get("title", "")
        if not title:
            return None
        
        # Prices will be fetched separately, default to 0.5
        price_yes = 0.5
        price_no = 0.5
        
        # Extract volume
        volume = float(market.get("volume", 0) or market.get("totalVolume", 0) or 0)
        
        # Construct market URL
        # URL format: https://opinion.trade/market/{marketId}
        url = f"https://opinion.trade/market/{market_id}"
        
        # Normalize title
        normalized_title = normalize_title(title)
        
        # Extract End Date
        end_date_str = market.get("endDate") or market.get("closeDate")
        end_date = None
        if end_date_str:
            try:
                # Handle ISO format variants or Timestamp
                import re
                if isinstance(end_date_str, (int, float)) or (isinstance(end_date_str, str) and re.match(r'^\d+(\.\d+)?$', end_date_str)): 
                     # Check if ms or seconds
                     ts = float(end_date_str)
                     if ts > 1000000000000: # ms
                         ts = ts / 1000
                     end_date = datetime.fromtimestamp(ts)
                else:
                     end_date = datetime.fromisoformat(str(end_date_str).replace("Z", "+00:00"))
            except:
                pass

        return StandardMarket(
            platform="OPINION",
            market_id=market_id,
            title=normalized_title,
            raw_title=title,
            price_yes=price_yes,
            price_no=price_no,
            volume=volume,
            url=url,
            end_date=end_date,
        )
