# PolyQuant Quick Reference

## Installation

```bash
cd /Users/jessesung/PolyQuant

# Install dependencies
python3 -m pip install requests pandas pyarrow python-dateutil

# Or use a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate
pip install requests pandas pyarrow python-dateutil
```

## Quick Start

### 1. Discover Markets

```bash
python scripts/discover_markets.py
```

### 2. Download Last 7 Days of Data

```bash
python scripts/download_history.py \
  --start 2025-12-10 \
  --end 2025-12-17 \
  --fidelity 1
```

### 3. Download with Custom Parameters

```bash
# Specific assets only
python scripts/download_history.py \
  --start 2025-12-01 \
  --end 2025-12-17 \
  --assets BTC,ETH \
  --fidelity 5

# Force rediscovery
python scripts/download_history.py \
  --start 2025-12-01 \
  --end 2025-12-17 \
  --rediscover
```

## Data Analysis

```python
import pandas as pd

# Load processed data
df = pd.read_parquet("data/processed/BTC_15m_UP.parquet")

# Basic info
print(df.info())
print(df.describe())

# Check for arbitrage
arbitrage = df[df['mispricing'].abs() > 0.01]
print(f"Arbitrage opportunities: {len(arbitrage)}")

# Plot prices
import matplotlib.pyplot as plt
df.plot(x='ts', y=['yes_price', 'no_price'])
plt.title('BTC 15m UP Market Prices')
plt.show()
```

## File Locations

- **Raw data**: `data/raw/{market_name}_{YES|NO}.{csv|parquet}`
- **Processed data**: `data/processed/{market_name}.{csv|parquet}`
- **Metadata**: `data/metadata/markets.json`

## Troubleshooting

### No markets found

The specific 15-minute Up/Down markets may not exist or use different naming. To fix:

1. Check actual market names on Polymarket
2. Update keywords in `polyquant/config.py`:
   ```python
   TIME_KEYWORDS = ["15"]
   DIRECTION_KEYWORDS = {
       "UP": ["Up", "up", "higher"],
       "DOWN": ["Down", "down", "lower"],
   }
   ```
3. Run discovery again

### Extend to other assets

Add to `polyquant/config.py`:
```python
ASSET_KEYWORDS = {
    "BTC": ["BTC", "Bitcoin"],
    "DOGE": ["DOGE", "Dogecoin"],  # Add new
    ...
}
```

Then run:
```bash
python scripts/download_history.py --assets DOGE --start ... --end ...
```

## Testing

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test file
python3 -m pytest tests/test_token_parsing.py -v
```

## Project Structure

```
PolyQuant/
├── README.md              # Full documentation
├── pyproject.toml        # Dependencies
├── polyquant/            # Core package
│   ├── config.py         # Configuration
│   ├── utils.py          # Utilities
│   ├── clients/          # API clients
│   ├── market_discovery.py
│   ├── fetch_history.py
│   └── storage.py
├── scripts/              # CLI tools
│   ├── discover_markets.py
│   └── download_history.py
├── data/                 # Output data
└── tests/                # Unit tests
```
