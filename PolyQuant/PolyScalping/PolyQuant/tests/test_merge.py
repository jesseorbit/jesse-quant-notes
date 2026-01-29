"""Tests for time series merging."""

import pandas as pd
import pytest

from polyquant.fetch_history import fetch_market_history


def test_merge_aligned_timestamps():
    """Test merging when timestamps are perfectly aligned."""
    # Create mock data
    yes_history = [
        {"t": 1000, "p": 0.6},
        {"t": 1060, "p": 0.65},
        {"t": 1120, "p": 0.7},
    ]
    
    no_history = [
        {"t": 1000, "p": 0.4},
        {"t": 1060, "p": 0.35},
        {"t": 1120, "p": 0.3},
    ]
    
    # Convert to DataFrames
    yes_df = pd.DataFrame(yes_history).rename(columns={"t": "ts", "p": "yes_price"})
    yes_df["ts"] = pd.to_datetime(yes_df["ts"], unit="s", utc=True)
    
    no_df = pd.DataFrame(no_history).rename(columns={"t": "ts", "p": "no_price"})
    no_df["ts"] = pd.to_datetime(no_df["ts"], unit="s", utc=True)
    
    # Merge
    merged = pd.merge(yes_df, no_df, on="ts", how="outer")
    merged = merged.sort_values("ts").reset_index(drop=True)
    
    # Calculate derived columns
    merged["sum_price"] = merged["yes_price"] + merged["no_price"]
    merged["mispricing"] = 1.0 - merged["sum_price"]
    
    # Assertions
    assert len(merged) == 3
    assert merged["yes_price"].tolist() == [0.6, 0.65, 0.7]
    assert merged["no_price"].tolist() == [0.4, 0.35, 0.3]
    assert merged["sum_price"].tolist() == [1.0, 1.0, 1.0]
    assert merged["mispricing"].tolist() == [0.0, 0.0, 0.0]


def test_merge_misaligned_timestamps():
    """Test merging when timestamps are not aligned."""
    yes_history = [
        {"t": 1000, "p": 0.6},
        {"t": 1120, "p": 0.7},
    ]
    
    no_history = [
        {"t": 1060, "p": 0.35},
        {"t": 1120, "p": 0.3},
    ]
    
    # Convert to DataFrames
    yes_df = pd.DataFrame(yes_history).rename(columns={"t": "ts", "p": "yes_price"})
    yes_df["ts"] = pd.to_datetime(yes_df["ts"], unit="s", utc=True)
    
    no_df = pd.DataFrame(no_history).rename(columns={"t": "ts", "p": "no_price"})
    no_df["ts"] = pd.to_datetime(no_df["ts"], unit="s", utc=True)
    
    # Merge (outer join to keep all timestamps)
    merged = pd.merge(yes_df, no_df, on="ts", how="outer")
    merged = merged.sort_values("ts").reset_index(drop=True)
    
    # Assertions
    assert len(merged) == 3  # 1000, 1060, 1120
    assert pd.isna(merged.loc[merged["ts"] == pd.Timestamp(1000, unit="s", tz="UTC"), "no_price"].values[0])
    assert pd.isna(merged.loc[merged["ts"] == pd.Timestamp(1060, unit="s", tz="UTC"), "yes_price"].values[0])


def test_derived_columns_calculation():
    """Test calculation of sum_price and mispricing."""
    data = {
        "ts": pd.to_datetime([1000, 1060, 1120], unit="s", utc=True),
        "yes_price": [0.6, 0.65, 0.7],
        "no_price": [0.4, 0.35, 0.25],
    }
    
    df = pd.DataFrame(data)
    df["sum_price"] = df["yes_price"] + df["no_price"]
    df["mispricing"] = 1.0 - df["sum_price"]
    
    # Assertions
    assert df["sum_price"].tolist() == [1.0, 1.0, 0.95]
    assert df["mispricing"].tolist() == pytest.approx([0.0, 0.0, 0.05])
