"""
Gamma Markets API client.

Provides access to Polymarket's Gamma API for market discovery and metadata.
"""

import logging
import time
from typing import Any, Dict, List, Optional

import requests

from .. import config

logger = logging.getLogger(__name__)


class GammaClient:
    """
    Client for Polymarket Gamma Markets API.
    
    Handles market retrieval, search, pagination, and automatic retry logic.
    """
    
    def __init__(self, base_url: str = config.GAMMA_API_BASE):
        """
        Initialize Gamma API client.
        
        Args:
            base_url: Base URL for Gamma API
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
    ) -> Dict[str, Any]:
        """
        Make HTTP request with exponential backoff retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            **kwargs: Additional requests arguments
        
        Returns:
            JSON response as dictionary
        
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
    
    def get_markets(
        self,
        limit: int = config.DEFAULT_PAGINATION_LIMIT,
        offset: int = 0,
        **filters
    ) -> List[Dict[str, Any]]:
        """
        Retrieve markets with pagination.
        
        Args:
            limit: Number of markets to fetch
            offset: Pagination offset
            **filters: Additional query filters
        
        Returns:
            List of market dictionaries
        """
        params = {
            "limit": limit,
            "offset": offset,
            **filters
        }
        
        logger.debug(f"Fetching markets with params: {params}")
        response = self._request_with_retry("GET", "/markets", params=params)
        
        # Response can be a list or a dict with a 'data' key
        if isinstance(response, list):
            return response
        elif isinstance(response, dict) and "data" in response:
            return response["data"]
        else:
            logger.warning(f"Unexpected response format: {type(response)}")
            return []
    
    def search_markets(
        self,
        query_text: str,
        limit: int = config.DEFAULT_PAGINATION_LIMIT
    ) -> List[Dict[str, Any]]:
        """
        Search markets by question/description text.
        
        Args:
            query_text: Search query
            limit: Maximum number of results
        
        Returns:
            List of matching market dictionaries
        """
        logger.info(f"Searching markets for: {query_text}")
        
        # Fetch markets and filter by text matching
        # Note: Gamma API may not support full-text search, so we fetch and filter
        all_markets = []
        offset = 0
        
        while len(all_markets) < limit:
            batch = self.get_markets(limit=config.DEFAULT_PAGINATION_LIMIT, offset=offset)
            
            if not batch:
                break
            
            # Filter by query text in question or description
            for market in batch:
                question = market.get("question", "").lower()
                description = market.get("description", "").lower()
                query_lower = query_text.lower()
                
                if query_lower in question or query_lower in description:
                    all_markets.append(market)
                    
                    if len(all_markets) >= limit:
                        break
            
            offset += len(batch)
            
            # Stop if we got fewer results than requested (end of data)
            if len(batch) < config.DEFAULT_PAGINATION_LIMIT:
                break
        
        logger.info(f"Found {len(all_markets)} markets matching '{query_text}'")
        return all_markets[:limit]
    
    def get_all_markets(self, max_markets: int = 1000, **filters) -> List[Dict[str, Any]]:
        """
        Fetch all available markets with pagination.
        
        Args:
            max_markets: Maximum number of markets to fetch
            **filters: Additional query filters (e.g., closed=False)
        
        Returns:
            List of all market dictionaries
        """
        logger.info(f"Fetching all markets (max: {max_markets}, filters: {filters})")
        
        all_markets = []
        offset = 0
        
        while len(all_markets) < max_markets:
            batch = self.get_markets(
                limit=config.DEFAULT_PAGINATION_LIMIT,
                offset=offset,
                **filters
            )
            
            if not batch:
                break
            
            all_markets.extend(batch)
            offset += len(batch)
            
            logger.debug(f"Fetched {len(all_markets)} markets so far...")
            
            # Stop if we got fewer results than requested
            if len(batch) < config.DEFAULT_PAGINATION_LIMIT:
                break
        
        logger.info(f"Fetched total of {len(all_markets)} markets")
        return all_markets[:max_markets]
