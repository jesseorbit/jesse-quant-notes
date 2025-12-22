"""
Fuzzy matching engine for identifying similar markets across platforms.
"""

import logging
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from rapidfuzz import fuzz

from models import ArbitrageOpportunity, StandardMarket
from utils.text_processing import extract_keywords

logger = logging.getLogger(__name__)


class MarketMatcher:
    """Fuzzy matching engine for cross-platform market identification."""
    
    def __init__(self, similarity_threshold: float = 85.0, min_common_keywords: int = 2):
        """
        Initialize market matcher.
        
        Args:
            similarity_threshold: Minimum similarity score (0-100) to consider a match
            min_common_keywords: Minimum number of common keywords required
        """
        self.similarity_threshold = similarity_threshold
        self.min_common_keywords = min_common_keywords
    
    def _build_keyword_index(
        self, markets: List[StandardMarket]
    ) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
        """Build keyword lookup tables for faster candidate selection."""

        keyword_cache: Dict[str, Set[str]] = {}
        keyword_index: Dict[str, Set[str]] = defaultdict(set)

        for market in markets:
            keywords = extract_keywords(market.title)
            keyword_cache[market.market_id] = keywords
            for keyword in keywords:
                keyword_index[keyword].add(market.market_id)

        return keyword_cache, keyword_index

    def find_matches(
        self,
        source_markets: List[StandardMarket],
        target_markets: List[StandardMarket]
    ) -> List[Tuple[StandardMarket, StandardMarket, float]]:
        """
        Find matching markets between two platforms using keyword pruning.

        Args:
            source_markets: List of markets from the primary platform
            target_markets: List of markets from the comparison platform

        Returns:
            List of tuples (source_market, target_market, similarity_score)
        """
        matches = []

        logger.info(
            "Matching %d markets (%s) vs %d markets (%s)...",
            len(source_markets),
            source_markets[0].platform if source_markets else "N/A",
            len(target_markets),
            target_markets[0].platform if target_markets else "N/A",
        )

        target_lookup: Dict[str, StandardMarket] = {
            market.market_id: market for market in target_markets
        }
        target_keywords, keyword_index = self._build_keyword_index(target_markets)

        for source_market in source_markets:
            source_keywords = extract_keywords(source_market.title)
            candidate_counts: Dict[str, int] = defaultdict(int)

            for keyword in source_keywords:
                for market_id in keyword_index.get(keyword, set()):
                    candidate_counts[market_id] += 1

            filtered_candidates = [
                market_id
                for market_id, count in candidate_counts.items()
                if count >= self.min_common_keywords
            ]

            best_match = None
            best_score = 0.0

            for market_id in filtered_candidates:
                target_market = target_lookup[market_id]
                common_keyword_count = len(
                    source_keywords & target_keywords[market_id]
                )

                if common_keyword_count < self.min_common_keywords:
                    continue

                score = fuzz.token_sort_ratio(
                    source_market.title,
                    target_market.title,
                )

                if score >= self.similarity_threshold and score > best_score:
                    best_score = score
                    best_match = target_market

            if best_match:
                matches.append((source_market, best_match, best_score))
                logger.debug(
                    "Match found (score=%.1f): %s <-> %s",
                    best_score,
                    source_market.title[:40],
                    best_match.title[:40],
                )

        logger.info("Found %d matching pairs", len(matches))
        return matches
    
    def calculate_arbitrage(
        self, 
        matches: List[Tuple[StandardMarket, StandardMarket, float]],
        min_margin: float = 0.02,
        max_cost: float = 0.98
    ) -> List[ArbitrageOpportunity]:
        """
        Calculate arbitrage opportunities from matched pairs.
        
        Strategy: Buy Yes on one platform, No on the other.
        Total cost should be < 1.0 to guarantee profit.
        
        Args:
            matches: List of matched market pairs
            min_margin: Minimum profit margin required (default 2%)
            max_cost: Maximum total cost allowed (default 0.98)
            
        Returns:
            List of ArbitrageOpportunity objects, sorted by ROI descending
        """
        opportunities = []
        
        logger.info(f"Calculating arbitrage for {len(matches)} matched pairs...")
        
        for poly_market, counter_market, similarity_score in matches:
            # Strategy 1: Buy Poly Yes + Counter No
            cost_1 = poly_market.price_yes + counter_market.price_no

            # Strategy 2: Buy Poly No + Counter Yes
            cost_2 = poly_market.price_no + counter_market.price_yes
            
            # Choose the cheaper strategy
            if cost_1 < cost_2:
                total_cost = cost_1
                strategy = "Poly YES + Counter NO"
            else:
                total_cost = cost_2
                strategy = "Poly NO + Counter YES"
            
            # Check if arbitrage exists
            if total_cost <= max_cost:
                profit_margin = 1.0 - total_cost
                
                if profit_margin >= min_margin:
                    roi_percent = (profit_margin / total_cost) * 100
                    
                    opportunity = ArbitrageOpportunity(
                        poly_market=poly_market,
                        counter_market=counter_market,
                        similarity_score=similarity_score,
                        total_cost=total_cost,
                        profit_margin=profit_margin,
                        roi_percent=roi_percent,
                    )
                    
                    opportunities.append(opportunity)
                    logger.info(
                        f"Arbitrage found! ROI={roi_percent:.2f}%, "
                        f"Cost=${total_cost:.4f}, Strategy={strategy}"
                    )
        
        # Sort by ROI descending
        opportunities.sort(key=lambda x: x.roi_percent, reverse=True)
        
        logger.info(f"Found {len(opportunities)} arbitrage opportunities")
        return opportunities
