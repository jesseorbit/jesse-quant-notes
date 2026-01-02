"""
Fuzzy matching engine for identifying similar markets across platforms.
"""

import logging
import re
from typing import List, Tuple, Dict, Set
from collections import defaultdict
from rapidfuzz import fuzz
from models import StandardMarket, ArbitrageOpportunity
from services.llm_verifier import LLMVerifier

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "will", "the", "be", "in", "on", "at", "to", "for", "of", "a", "an", "is", "by",
    "does", "do", "did", "market", "bet", "prediction", "forecast", "outcome", "would", "should", "could",
    "market", "price", "prediction", "forecast", "bet", "outcome", "result", "b", "c"
}


class MarketMatcher:
    """Fuzzy matching engine for cross-platform market identification."""
    
    def __init__(self, similarity_threshold: float = 90.0, min_common_keywords: int = 2):
        """
        Initialize market matcher.
        
        Args:
            similarity_threshold: Minimum similarity score (0-100) to consider a match
            min_common_keywords: Minimum number of common keywords required
        """
        self.similarity_threshold = similarity_threshold
        self.min_common_keywords = min_common_keywords
        self.llm = LLMVerifier()
    
    def find_matches(
        self, 
        poly_markets: List[StandardMarket], 
        opinion_markets: List[StandardMarket]
    ) -> List[Tuple[StandardMarket, StandardMarket, float]]:
        """
        Find matching markets between Polymarket and Opinion Labs.
        
        Args:
            poly_markets: List of Polymarket markets
            opinion_markets: List of Opinion Labs markets
            
        Returns:
            List of tuples (poly_market, opinion_market, similarity_score)
        """
    def _tokenize(self, text: str) -> Set[str]:
        """Extract significant tokens from text."""
        # Lowercase and remove special chars
        clean_text = re.sub(r'[^a-z0-9\s]', '', text.lower())
        tokens = clean_text.split()
        # Filter stop words and short tokens
        return {t for t in tokens if t not in STOP_WORDS and len(t) > 2}

    def _extract_years(self, text: str) -> Set[str]:
        """Extract 4-digit years from text."""
        # Find years from 2020 to 2030
        return set(re.findall(r'202[0-9]', text))
        
    def _check_nuance(self, text1: str, text2: str) -> bool:
        """
        Check for semantic nuances that distinguish markets.
        Returns False if a conflict is found (e.g., 'before' vs 'after').
        """
        t1, t2 = text1.lower(), text2.lower()
        
        # 0. Month Check (User request)
        # Distinguish "June 2026" vs "March 2026"
        months = [
            "january", "february", "march", "april", "may", "june", 
            "july", "august", "september", "october", "november", "december",
            "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec"
        ]
        
        found_months_1 = {m for m in months if f" {m} " in f" {t1} "}
        found_months_2 = {m for m in months if f" {m} " in f" {t2} "}
        
        # Normalize (january -> jan)
        def normalize_month(m):
            mapping = {
                "january": "jan", "february": "feb", "march": "mar", "april": "apr",
                "june": "jun", "july": "jul", "august": "aug", "september": "sep",
                "october": "oct", "november": "nov", "december": "dec"
            }
            return mapping.get(m, m)
            
        norm_1 = {normalize_month(m) for m in found_months_1}
        norm_2 = {normalize_month(m) for m in found_months_2}
        
        # Check intersection logic:
        # If both have months, they MUST overlap
        if norm_1 and norm_2:
            if not norm_1.intersection(norm_2):
                return False
        
        # 1. Prepositions regarding dates/time
        
        # 1. Prepositions regarding dates/time
        prepositions = ["before", "after", "in", "by", "since", "until"]
        for prep in prepositions:
            # If one has the preposition and the other doesn't, it's suspicious
            # But more importantly, if they have DIFFERENT prepositions
            # "Before 2026" vs "In 2026"
            # Logic: If both have a preposition near a year, they must match?
            # Simple heuristic: If one has 'before 2026' and other has 'in 2026', distinct.
            
            # Check for direct conflicts
            if "before" in t1 and "after" in t2: return False
            if "before" in t2 and "after" in t1: return False
            
            # "In" vs "Before"
            # "Will X happen in 2025?" vs "Will X happen before 2025?" -> Different
            if " in " in t1 and " before " in t2: return False
            if " in " in t2 and " before " in t1: return False
            
        # 2. Ordinals / Rankings
        # "Second largest" vs "Largest"
        ordinals = ["first", "second", "third", "fourth", "fifth", "largest", "highest", "lowest", "smallest"]
        
        t1_tokens = set(t1.split())
        t2_tokens = set(t2.split())
        
        for ord_word in ordinals:
            # If one has an ordinal and the other doesn't, allow it? No, usually distinct.
            # "Largest crypto" vs "Second largest crypto"
            if ord_word in t1_tokens and ord_word not in t2_tokens:
                # Be careful: "Largest" might match "The Largest" (both have it)
                # But if t2 is just "Crypto market cap" it might be generic.
                # Stricter: if t1 has "second" and t2 has "largest", conflict?
                # "Second largest" contains "largest".
                pass
            
            # Specific conflict: "Second" vs not "Second"
            if "second" in t1_tokens and "second" not in t2_tokens: return False
            if "second" in t2_tokens and "second" not in t1_tokens: return False
            
            if "third" in t1_tokens and "third" not in t2_tokens: return False
            if "third" in t2_tokens and "third" not in t1_tokens: return False

        return True

    def _check_proper_nouns(self, text1: str, text2: str) -> bool:
        """
        Check for proper noun mismatches (Capitalized words).
        Returns False if there is a conflict.
        """
        def get_proper_nouns(text):
            words = text.split()
            # simple heuristic: words starting with diff case than lowercase version
            # AND not first word of sentence (unless it's always proper)
            # Actually, standard title case makes this hard.
            # But usually entities like "Inter", "Como", "Turkey", "Ukraine" are distinct.
            # Let's try to extract all words > 3 chars that are Title cased.
            proper = set()
            for i, w in enumerate(words):
                clean_w = w.strip("?,.:!\"'()")
                # Allow 2-letter proper nouns (US, UK, EU, AI)
                # Ensure it's not a stop word (In, Of, To are handled by STOP_WORDS)
                if len(clean_w) < 2: continue
                
                # Check capitalization
                if clean_w[0].isupper() and clean_w.lower() not in STOP_WORDS:
                    # Extra check for 2-letter words: both must be upper? 
                    # "Us" (we) vs "US" (USA). 
                    # If it's a title, "Us" might be capitalized. 
                    # But usually "US" is distinct.
                    # Let's keep it simple: if not in stop words, count it.
                    proper.add(clean_w.lower())
            return proper

        pn1 = get_proper_nouns(text1)
        pn2 = get_proper_nouns(text2)
        
        if not pn1 or not pn2:
            return True
            
        # Symmetric difference: words in one but not the other
        diff = pn1.symmetric_difference(pn2)
        
        # If there are proper nouns in the difference, it's risky
        # But we must be careful not to kill "Poly" vs "Kalshi" wording diffs
        # e.g. "Will Trump win?" vs "Trump to win?" -> "Will" is in diff? No, stop words handles that.
        # "Inter" vs "Como" -> Both are proper nouns. Diff = {inter, como}. Reject.
        if len(diff) > 0:
            # If the difference is just 1 or 2 words, and they are significant names
            # we should reject.
            # However, sometimes titles add extra info "Trump 2024" vs "Trump"
            # Diff = {2024}.
            # We already check years.
            
            # Allow subset relationship? 
            # If pn1 is subset of pn2, maybe OK? (e.g. "Trump" vs "Trump Election")
            if pn1.issubset(pn2) or pn2.issubset(pn1):
                return True
                
            return False
            
        return True

    def _build_index(self, markets: List[StandardMarket]) -> Dict[str, List[StandardMarket]]:
        """Build an inverted index mapping tokens to markets."""
        index = defaultdict(list)
        for market in markets:
            tokens = self._tokenize(market.title)
            for token in tokens:
                index[token].append(market)
        return index

    def find_matches(
        self, 
        poly_markets: List[StandardMarket], 
        opinion_markets: List[StandardMarket]
    ) -> List[Tuple[StandardMarket, StandardMarket, float]]:
        """
        Find matching markets between Polymarket and Kalshi/Opinion using Inverted Index optimization.
        
        Args:
            poly_markets: List of Polymarket markets
            opinion_markets: List of Opinion Labs markets
            
        Returns:
            List of tuples (poly_market, opinion_market, similarity_score)
        """
        matches = []
        
        if len(opinion_markets) > len(poly_markets):
            index = self._build_index(opinion_markets)
            source_markets = poly_markets
            target_is_second = True
            platform2 = opinion_markets[0].platform if opinion_markets else "Second"
            platform1 = "POLY"
        else:
            index = self._build_index(poly_markets)
            source_markets = opinion_markets
            target_is_second = False
            platform2 = "POLY"
            platform1 = opinion_markets[0].platform if opinion_markets else "First"
            
        logger.info(f"Matching {len(poly_markets)} Polymarket vs {len(opinion_markets)} {platform1 if target_is_second else platform1} markets...")
            
        logger.info("Index built. Starting optimized matching...")
        
        for source_market in source_markets:
            source_tokens = self._tokenize(source_market.title)
            if not source_tokens:
                continue
                
            # Get candidates that share at least one keyword
            candidates = set()
            for token in source_tokens:
                if token in index:
                    candidates.update(index[token])
            
            # If too many candidates, it might be a generic match (e.g. "Trump"), skip if overwhelmed
            # But for now let's just process them
            
            best_match = None
            best_score = 0.0
            
            # Minimum Volume Filter (User request 2)
            # Skip source market if volume too low (e.g. < $1000)
            if source_market.volume < 1000:
                continue

            for candidate in candidates:
                # Volume Filter for candidate
                if candidate.volume < 1000:
                    continue

                # Year Check
                source_years = self._extract_years(source_market.title)
                candidate_years = self._extract_years(candidate.title)
                
                # If both have years, they MUST overlap
                # e.g., "GOP 2024" should NOT match "GOP 2028"
                # But "GOP Nominee" (no year) can match "GOP 2024" if score is high
                if source_years and candidate_years:
                     if not source_years.intersection(candidate_years):
                         continue

                # Calculate similarity score
                score = fuzz.token_sort_ratio(
                    source_market.title, 
                    candidate.title
                )
                
                if score >= self.similarity_threshold:
                    # Semantic Nuance Check (User request 3 & 4)
                    if not self._check_nuance(source_market.title, candidate.title):
                        continue

                    # Proper Noun Check (User request 4 - Entities)
                    # MUST use raw_title because title is lowercase
                    if not self._check_proper_nouns(source_market.raw_title, candidate.raw_title):
                         continue
                         
                    # LLM Verification (Ultimate Tie-Breaker)
                    # Use LLM only if score is high enough to be worth the cost
                    # Use raw_title for better LLM context
                    if not self.llm.verify_match(source_market.raw_title, candidate.raw_title):
                         continue
                        
                    if score > best_score:
                        best_score = score
                        best_match = candidate
            
            if best_match:
                if target_is_second:
                    poly = source_market
                    other = best_match
                else:
                    poly = best_match
                    other = source_market
                    
                # Double check to avoid duplicates if multiple source markets match same target
                # (Simple linear append for now, can be improved)
                matches.append((poly, other, best_score))
                # logger.debug(f"Match: {poly.title[:30]}... <-> {opinion.title[:30]}... ({best_score})")
        
        logger.info(f"Found {len(matches)} matching pairs")
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
        
        for poly_market, opinion_market, similarity_score in matches:
            # Strategy 1: Buy Poly Yes + Opinion No
            cost_1 = poly_market.price_yes + opinion_market.price_no
            
            # Strategy 2: Buy Poly No + Opinion Yes
            cost_2 = poly_market.price_no + opinion_market.price_yes
            
            # Choose the cheaper strategy
            if cost_1 < cost_2:
                total_cost = cost_1
                profit = 1.0 - total_cost
                poly_side = "YES"
                opinion_side = "NO"
                strategy_desc = (
                    f"Yes {poly_market.platform} (${poly_market.price_yes:.2f}) + "
                    f"No {opinion_market.platform} (${opinion_market.price_no:.2f}) "
                    f"-> Profit ${profit:.2f}"
                )
            else:
                total_cost = cost_2
                profit = 1.0 - total_cost
                poly_side = "NO"
                opinion_side = "YES"
                strategy_desc = (
                    f"No {poly_market.platform} (${poly_market.price_no:.2f}) + "
                    f"Yes {opinion_market.platform} (${opinion_market.price_yes:.2f}) "
                    f"-> Profit ${profit:.2f}"
                )
            
            # Check if arbitrage exists
            if total_cost <= max_cost:
                profit_margin = 1.0 - total_cost
                
                if profit_margin >= min_margin:
                    # ROI per user request: (1 - Yes - No) as percentage
                    # This represents raw profit from $1 payout
                    roi_percent = profit_margin * 100
                    
                    opportunity = ArbitrageOpportunity(
                        poly_market=poly_market,
                        opinion_market=opinion_market,
                        similarity_score=similarity_score,
                        total_cost=total_cost,
                        profit_margin=profit_margin,
                        roi_percent=roi_percent,
                        poly_side=poly_side,
                        opinion_side=opinion_side,
                        strategy=strategy_desc
                    )
                    
                    opportunities.append(opportunity)
                    logger.info(
                        f"Arbitrage found! ROI={roi_percent:.2f}%, "
                        f"Cost=${total_cost:.4f}, Platform1={poly_market.platform}, Platform2={opinion_market.platform}"
                    )
        
        # Sort by ROI descending
        opportunities.sort(key=lambda x: x.roi_percent, reverse=True)
        
        logger.info(f"Found {len(opportunities)} arbitrage opportunities")
        return opportunities
