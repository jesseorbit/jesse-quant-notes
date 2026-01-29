"""Tests for market filtering logic."""

import pytest

from polyquant.market_discovery import (
    matches_asset_keywords,
    matches_direction_keywords,
    matches_time_keywords,
    select_best_market,
)


def test_matches_asset_keywords_btc():
    """Test BTC keyword matching."""
    assert matches_asset_keywords("Will BTC go up?", "BTC") is True
    assert matches_asset_keywords("Bitcoin price prediction", "BTC") is True
    assert matches_asset_keywords("ETH price", "BTC") is False


def test_matches_asset_keywords_eth():
    """Test ETH keyword matching."""
    assert matches_asset_keywords("Will ETH go up?", "ETH") is True
    assert matches_asset_keywords("Ethereum price prediction", "ETH") is True
    assert matches_asset_keywords("BTC price", "ETH") is False


def test_matches_time_keywords():
    """Test 15-minute keyword matching."""
    assert matches_time_keywords("15 minute market") is True
    assert matches_time_keywords("15min prediction") is True
    assert matches_time_keywords("15-minute window") is True
    assert matches_time_keywords("5 minute market") is False
    assert matches_time_keywords("1 hour market") is False


def test_matches_direction_keywords_up():
    """Test UP direction keyword matching."""
    assert matches_direction_keywords("Will price go Up?", "UP") is True
    assert matches_direction_keywords("Price higher than X", "UP") is True
    assert matches_direction_keywords("Above threshold", "UP") is True
    assert matches_direction_keywords("Will price go Down?", "UP") is False


def test_matches_direction_keywords_down():
    """Test DOWN direction keyword matching."""
    assert matches_direction_keywords("Will price go Down?", "DOWN") is True
    assert matches_direction_keywords("Price lower than X", "DOWN") is True
    assert matches_direction_keywords("Below threshold", "DOWN") is True
    assert matches_direction_keywords("Will price go Up?", "DOWN") is False


def test_select_best_market_by_liquidity():
    """Test market selection by liquidity."""
    candidates = [
        {"question": "Market 1", "liquidity": 1000},
        {"question": "Market 2", "liquidity": 5000},
        {"question": "Market 3", "liquidity": 2000},
    ]
    
    best = select_best_market(candidates)
    
    assert best["question"] == "Market 2"
    assert best["liquidity"] == 5000


def test_select_best_market_by_volume():
    """Test market selection by volume when liquidity is missing."""
    candidates = [
        {"question": "Market 1", "volume": 1000},
        {"question": "Market 2", "volume": 5000},
        {"question": "Market 3", "volume": 2000},
    ]
    
    best = select_best_market(candidates)
    
    assert best["question"] == "Market 2"
    assert best["volume"] == 5000


def test_select_best_market_by_recency():
    """Test market selection by end date when liquidity/volume missing."""
    candidates = [
        {"question": "Market 1", "endDate": "2025-12-01"},
        {"question": "Market 2", "endDate": "2025-12-15"},
        {"question": "Market 3", "endDate": "2025-12-10"},
    ]
    
    best = select_best_market(candidates)
    
    assert best["question"] == "Market 2"
    assert best["endDate"] == "2025-12-15"


def test_select_best_market_first_candidate():
    """Test market selection defaults to first candidate."""
    candidates = [
        {"question": "Market 1"},
        {"question": "Market 2"},
        {"question": "Market 3"},
    ]
    
    best = select_best_market(candidates)
    
    assert best["question"] == "Market 1"


def test_select_best_market_empty():
    """Test market selection with empty list."""
    candidates = []
    
    best = select_best_market(candidates)
    
    assert best is None
