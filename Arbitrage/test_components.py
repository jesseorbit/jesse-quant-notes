#!/usr/bin/env python3
"""
Test script for the Arbitrage Scanner.

Tests individual components before running the full scanner.
"""

import sys
import logging
from models import StandardMarket
from utils.text_processing import normalize_title, has_common_keywords
from matcher import MarketMatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_text_processing():
    """Test text normalization."""
    print("\n=== Testing Text Processing ===")
    
    test_cases = [
        "Will Bitcoin reach $100,000 by 2024?",
        "BTC Price Above 100K Before 2025",
        "Trump wins 2024 election",
    ]
    
    for text in test_cases:
        normalized = normalize_title(text)
        print(f"Original: {text}")
        print(f"Normalized: {normalized}\n")


def test_keyword_matching():
    """Test keyword matching."""
    print("\n=== Testing Keyword Matching ===")
    
    title1 = "Will Bitcoin reach 100000 by end of 2024"
    title2 = "Bitcoin price above 100k before 2025"
    
    has_common = has_common_keywords(title1, title2, min_common=2)
    print(f"Title 1: {title1}")
    print(f"Title 2: {title2}")
    print(f"Has common keywords: {has_common}\n")


def test_fuzzy_matching():
    """Test fuzzy matching engine."""
    print("\n=== Testing Fuzzy Matching ===")

    # Create mock markets
    poly_markets = [
        StandardMarket(
            platform="POLY",
            market_id="poly-1",
            title=normalize_title("Will Bitcoin reach $100,000 by 2024?"),
            price_yes=0.65,
            price_no=0.35,
            volume=50000,
            url="https://polymarket.com/event/btc-100k"
        ),
        StandardMarket(
            platform="POLY",
            market_id="poly-2",
            title=normalize_title("Trump wins 2024 election"),
            price_yes=0.55,
            price_no=0.45,
            volume=100000,
            url="https://polymarket.com/event/trump-2024"
        ),
    ]

    kalshi_markets = [
        StandardMarket(
            platform="KALSHI",
            market_id="k-1",
            title=normalize_title("Bitcoin price above 100k before 2025"),
            price_yes=0.32,
            price_no=0.68,
            volume=30000,
            url="https://kalshi.com/market/btc-100k"
        ),
        StandardMarket(
            platform="KALSHI",
            market_id="k-2",
            title=normalize_title("Donald Trump elected president 2024"),
            price_yes=0.48,
            price_no=0.52,
            volume=75000,
            url="https://kalshi.com/market/trump-2024"
        ),
    ]

    # Test matching
    matcher = MarketMatcher(similarity_threshold=80.0)
    matches = matcher.find_matches(poly_markets, kalshi_markets)

    print(f"Found {len(matches)} matches:")
    for poly, kalshi, score in matches:
        print(f"\nMatch Score: {score:.1f}")
        print(f"  Poly: {poly.title}")
        print(f"  Kalshi: {kalshi.title}")


def test_arbitrage_calculation():
    """Test arbitrage calculation."""
    print("\n=== Testing Arbitrage Calculation ===")
    
    # Create a matched pair with arbitrage opportunity
    poly_market = StandardMarket(
        platform="POLY",
        market_id="poly-1",
        title="bitcoin reach 100000 by 2024",
        price_yes=0.65,
        price_no=0.35,
        volume=50000,
        url="https://polymarket.com/event/btc-100k"
    )
    
    kalshi_market = StandardMarket(
        platform="KALSHI",
        market_id="k-1",
        title="bitcoin price above 100k before 2025",
        price_yes=0.32,
        price_no=0.68,
        volume=30000,
        url="https://kalshi.com/market/btc-100k"
    )
    
    # Calculate costs
    cost_1 = poly_market.price_yes + kalshi_market.price_no  # 0.65 + 0.68 = 1.33 (no arb)
    cost_2 = poly_market.price_no + kalshi_market.price_yes  # 0.35 + 0.32 = 0.67 (arb!)
    
    print(f"Strategy 1 (Poly YES + Kalshi NO): ${cost_1:.4f}")
    print(f"Strategy 2 (Poly NO + Kalshi YES): ${cost_2:.4f}")
    
    if cost_2 < 0.98:
        profit = 1.0 - cost_2
        roi = (profit / cost_2) * 100
        print(f"\n✅ Arbitrage Opportunity Found!")
        print(f"   Profit: ${profit:.4f}")
        print(f"   ROI: {roi:.2f}%")
    else:
        print("\n❌ No arbitrage opportunity")
    
    # Test with matcher
    matcher = MarketMatcher()
    matches = [(poly_market, kalshi_market, 95.0)]
    opportunities = matcher.calculate_arbitrage(matches, min_margin=0.02)
    
    print(f"\nMatcher found {len(opportunities)} opportunities")
    if opportunities:
        print(opportunities[0])


def main():
    """Run all tests."""
    print("="*80)
    print("ARBITRAGE SCANNER - COMPONENT TESTS")
    print("="*80)
    
    try:
        test_text_processing()
        test_keyword_matching()
        test_fuzzy_matching()
        test_arbitrage_calculation()
        
        print("\n" + "="*80)
        print("✅ All tests completed successfully!")
        print("="*80)
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
