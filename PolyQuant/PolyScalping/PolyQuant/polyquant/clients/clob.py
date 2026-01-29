"""
CLOB API client.

Provides access to Polymarket's CLOB API for price history and order book data.
"""

import logging
import time
from typing import Any, Dict, List, Optional

import requests

from .. import config

logger = logging.getLogger(__name__)


class ClobClient:
    """
    Client for Polymarket CLOB API.
    
    Handles price history retrieval, order book queries, and automatic retry logic.
    """
    
    def __init__(self, base_url: str = config.CLOB_API_BASE):
        """
        Initialize CLOB API client.
        
        Args:
            base_url: Base URL for CLOB API
        """
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PolyQuant/0.1.0",
            "Accept": "application/json",
        })
    
    def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Any:
        """
        Make HTTP request with exponential backoff retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            **kwargs: Additional requests arguments
        
        Returns:
            JSON response (dict or list)
        
        Raises:
            requests.HTTPError: If all retries fail
        """
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(config.RETRY_ATTEMPTS):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    timeout=30,
                    **kwargs
                )
                response.raise_for_status()
                
                # Rate limiting delay
                time.sleep(config.REQUEST_DELAY_SECONDS)
                
                return response.json()
            
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code
                
                # Retry on rate limit or server errors
                if status_code in [429, 500, 502, 503, 504]:
                    if attempt < config.RETRY_ATTEMPTS - 1:
                        delay = config.RETRY_BACKOFF_BASE * (2 ** attempt)
                        logger.warning(
                            f"HTTP {status_code} error, retrying in {delay}s "
                            f"(attempt {attempt + 1}/{config.RETRY_ATTEMPTS})"
                        )
                        time.sleep(delay)
                        continue
                
                # Don't retry on client errors (4xx except 429)
                logger.error(f"HTTP error {status_code}: {e}")
                raise
            
            except requests.exceptions.RequestException as e:
                if attempt < config.RETRY_ATTEMPTS - 1:
                    delay = config.RETRY_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        f"Request failed: {e}, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{config.RETRY_ATTEMPTS})"
                    )
                    time.sleep(delay)
                    continue
                
                logger.error(f"Request failed after {config.RETRY_ATTEMPTS} attempts: {e}")
                raise
        
        raise requests.HTTPError("All retry attempts exhausted")
    
    def get_price_history(
        self,
        token_id: str,
        start_ts: int,
        end_ts: int,
        fidelity: int = config.DEFAULT_FIDELITY
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical price data for a token.
        
        Args:
            token_id: CLOB token ID
            start_ts: Start timestamp (unix seconds)
            end_ts: End timestamp (unix seconds)
            fidelity: Resolution in minutes (default: 1)
        
        Returns:
            List of price points: [{"t": timestamp, "p": price}, ...]
        """
        # Try both parameter names (market and token_id)
        params_variants = [
            {
                "market": token_id,
                "startTs": start_ts,
                "endTs": end_ts,
                "fidelity": fidelity,
            },
            {
                "token_id": token_id,
                "startTs": start_ts,
                "endTs": end_ts,
                "fidelity": fidelity,
            },
        ]
        
        logger.debug(
            f"Fetching price history for token {token_id[:8]}... "
            f"from {start_ts} to {end_ts} (fidelity: {fidelity}m)"
        )
        
        # Try first variant
        try:
            response = self._request_with_retry(
                "GET",
                "/prices-history",
                params=params_variants[0]
            )
            
            if isinstance(response, list):
                logger.info(f"Fetched {len(response)} price points for token {token_id[:8]}...")
                return response
            elif isinstance(response, dict) and "history" in response:
                history = response["history"]
                logger.info(f"Fetched {len(history)} price points for token {token_id[:8]}...")
                return history
            else:
                logger.warning(f"Unexpected response format: {type(response)}")
                return []
        
        except requests.HTTPError as e:
            # If first variant fails, try second
            logger.debug(f"First parameter variant failed, trying alternative: {e}")
            
            try:
                response = self._request_with_retry(
                    "GET",
                    "/prices-history",
                    params=params_variants[1]
                )
                
                if isinstance(response, list):
                    logger.info(f"Fetched {len(response)} price points for token {token_id[:8]}...")
                    return response
                elif isinstance(response, dict) and "history" in response:
                    history = response["history"]
                    logger.info(f"Fetched {len(history)} price points for token {token_id[:8]}...")
                    return history
                else:
                    logger.warning(f"Unexpected response format: {type(response)}")
                    return []
            
            except requests.HTTPError:
                logger.error(f"Failed to fetch price history for token {token_id}")
                raise
    
    def get_order_book(self, token_id: str) -> Dict[str, Any]:
        """
        Fetch current order book for a token (optional, for debugging).
        
        Args:
            token_id: CLOB token ID
        
        Returns:
            Order book data with bids and asks
        """
        params = {"token_id": token_id}
        
        logger.debug(f"Fetching order book for token {token_id[:8]}...")
        
        try:
            response = self._request_with_retry("GET", "/book", params=params)
            return response
        except requests.HTTPError as e:
            logger.warning(f"Failed to fetch order book: {e}")
            return {}
