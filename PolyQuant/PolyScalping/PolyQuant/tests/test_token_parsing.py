"""Tests for token ID extraction."""

import json

import pytest

from polyquant.market_discovery import extract_token_ids


def test_extract_token_ids_list():
    """Test extraction from JSON array."""
    market = {
        "question": "Test market",
        "tokens": ["0xabc123", "0xdef456"],
        "outcomes": ["Yes", "No"]
    }
    
    yes_token, no_token = extract_token_ids(market)
    
    assert yes_token == "0xabc123"
    assert no_token == "0xdef456"


def test_extract_token_ids_json_string():
    """Test extraction from JSON-encoded string."""
    market = {
        "question": "Test market",
        "clobTokenIds": '["0xabc123", "0xdef456"]',
        "outcomes": ["Yes", "No"]
    }
    
    yes_token, no_token = extract_token_ids(market)
    
    assert yes_token == "0xabc123"
    assert no_token == "0xdef456"


def test_extract_token_ids_comma_separated():
    """Test extraction from comma-separated string."""
    market = {
        "question": "Test market",
        "tokens": "0xabc123,0xdef456",
        "outcomes": ["Yes", "No"]
    }
    
    yes_token, no_token = extract_token_ids(market)
    
    assert yes_token == "0xabc123"
    assert no_token == "0xdef456"


def test_extract_token_ids_outcomes_mapping():
    """Test YES/NO mapping using outcomes."""
    market = {
        "question": "Test market",
        "tokens": ["0xdef456", "0xabc123"],  # NO first, YES second
        "outcomes": ["No", "Yes"]
    }
    
    yes_token, no_token = extract_token_ids(market)
    
    # Should map correctly based on outcomes
    assert yes_token == "0xabc123"
    assert no_token == "0xdef456"


def test_extract_token_ids_no_outcomes():
    """Test default mapping when outcomes are missing."""
    market = {
        "question": "Test market",
        "tokens": ["0xabc123", "0xdef456"]
    }
    
    yes_token, no_token = extract_token_ids(market)
    
    # Default: first = YES, second = NO
    assert yes_token == "0xabc123"
    assert no_token == "0xdef456"


def test_extract_token_ids_missing_tokens():
    """Test handling of missing token IDs."""
    market = {
        "question": "Test market"
    }
    
    yes_token, no_token = extract_token_ids(market)
    
    assert yes_token is None
    assert no_token is None


def test_extract_token_ids_insufficient_tokens():
    """Test handling of insufficient token IDs."""
    market = {
        "question": "Test market",
        "tokens": ["0xabc123"]  # Only one token
    }
    
    yes_token, no_token = extract_token_ids(market)
    
    assert yes_token is None
    assert no_token is None
