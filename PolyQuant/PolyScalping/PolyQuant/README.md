# PolyQuant

**Production-ready data ingestion pipeline for Polymarket 15-minute Up/Down markets**

PolyQuant fetches and stores historical YES/NO price time series for Polymarket's 15-minute "Up/Down" prediction markets across major crypto assets (BTC, ETH, SOL, XRP). The pipeline discovers relevant markets, extracts CLOB token IDs, downloads historical price data, and stores cleaned time series in CSV and Parquet formats for backtesting and analysis.

## Features

- 🔍 **Automated Market Discovery**: Finds 15-minute Up/Down markets using intelligent keyword matching
- 🔄 **Robust Token Parsing**: Handles multiple token ID formats (JSON array, JSON string, comma-separated)
- 📊 **Dual Format Storage**: Saves data in both CSV (human-readable) and Parquet (efficient)
- 🛡️ **Production-Grade Reliability**: Exponential backoff retry logic, rate limiting, comprehensive error handling
- 📈 **Derived Metrics**: Automatically calculates sum_price and mispricing for arbitrage analysis
- 🧪 **Well-Tested**: Unit tests for critical parsing and merging logic
- 📝 **Type Hints & Docstrings**: Clean, maintainable code with full documentation

## Project Structure

```
PolyQuant/
├── README.md                    # This file
├── pyproject.toml              # Python project configuration
├── polyquant/                  # Main package
│   ├── __init__.py
│   ├── config.py               # Configuration and constants
│   ├── utils.py                # Utility functions
│   ├── clients/                # API clients
│   │   ├── gamma.py           # Gamma Markets API client
│   │   └── clob.py            # CLOB API client
│   ├── market_discovery.py    # Market discovery logic
│   ├── fetch_history.py       # Historical data fetching
│   └── storage.py             # Data persistence
├── scripts/                    # CLI scripts
│   ├── discover_markets.py    # Discover and save markets
│   └── download_history.py    # Download price histories
├── data/                       # Data storage (created on first run)
│   ├── raw/                   # Individual YES/NO token histories
│   ├── processed/             # Merged time series with derived metrics
│   └── metadata/              # Market metadata (JSON)
└── tests/                      # Unit tests
    ├── test_token_parsing.py
    ├── test_merge.py
    └── test_market_filter.py
```

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Setup

1. **Clone or navigate to the project directory**:
   ```bash
   cd /Users/jessesung/PolyQuant
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On macOS/Linux
   # OR
   venv\Scripts\activate  # On Windows
   ```

3. **Install dependencies**:
   ```bash
   pip install -e .
   ```

4. **Install development dependencies** (optional, for testing):
   ```bash
   pip install -e ".[dev]"
   ```

## Quick Start

### 1. Discover Markets

Find 15-minute Up/Down markets for BTC, ETH, SOL, and XRP:

```bash
python scripts/discover_markets.py
```

**Output**:
- Prints discovered markets to console
- Saves metadata to `data/metadata/markets.json`

**Example output**:
```
============================================================
DISCOVERED MARKETS (8/8)
============================================================

BTC_15m_DOWN:
  Question: Will BTC be down in 15 minutes?
  Market ID: 0x123abc...
  YES Token: 0xabc123...
  NO Token:  0xdef456...

BTC_15m_UP:
  Question: Will BTC be up in 15 minutes?
  ...
```

### 2. Download Historical Data

Download price histories for a specific date range:

```bash
python scripts/download_history.py --start 2025-12-10 --end 2025-12-17 --fidelity 1
```

**Arguments**:
- `--start`: Start date (ISO format like `2025-12-01` or unix timestamp)
- `--end`: End date (ISO format or unix timestamp)
- `--fidelity`: Resolution in minutes (default: 1)
- `--assets`: Comma-separated asset list (default: `BTC,ETH,SOL,XRP`)
- `--minutes`: Market duration filter (default: 15)
- `--rediscover`: Force rediscovery of markets (ignore cached metadata)

**Output**:
- Raw YES/NO histories: `data/raw/{market_name}_{YES|NO}.{csv|parquet}`
- Processed merged data: `data/processed/{market_name}.{csv|parquet}`
- Updated metadata: `data/metadata/markets.json`

**Example output**:
```
============================================================
DOWNLOAD SUMMARY
============================================================
BTC_15m_DOWN: 10080 data points
BTC_15m_UP: 10080 data points
ETH_15m_DOWN: 10080 data points
...

✓ Raw data saved to: /Users/jessesung/PolyQuant/data/raw
✓ Processed data saved to: /Users/jessesung/PolyQuant/data/processed
✓ Metadata saved to: /Users/jessesung/PolyQuant/data/metadata/markets.json
```

### 3. Load and Analyze Data

```python
import pandas as pd

# Load processed data
df = pd.read_parquet("data/processed/BTC_15m_UP.parquet")

# Inspect columns
print(df.columns)
# Index(['ts', 'yes_price', 'no_price', 'sum_price', 'mispricing'], dtype='object')

# Check for arbitrage opportunities
arbitrage = df[df['mispricing'].abs() > 0.01]
print(f"Found {len(arbitrage)} potential arbitrage opportunities")

# Plot prices
import matplotlib.pyplot as plt
df.plot(x='ts', y=['yes_price', 'no_price'])
plt.show()
```

## Data Format

### Processed Time Series

Each processed file contains a merged DataFrame with the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `ts` | datetime | UTC timestamp |
| `yes_price` | float | YES token price (0.0 to 1.0) |
| `no_price` | float | NO token price (0.0 to 1.0) |
| `sum_price` | float | yes_price + no_price (should ≈ 1.0) |
| `mispricing` | float | 1.0 - sum_price (arbitrage indicator) |

### Metadata JSON

`data/metadata/markets.json` contains:

```json
{
  "generated_at": "2025-12-17T13:20:30Z",
  "query_params": {
    "start": "2025-12-10T00:00:00",
    "end": "2025-12-17T00:00:00",
    "fidelity": 1,
    "assets": ["BTC", "ETH", "SOL", "XRP"]
  },
  "markets": {
    "BTC_15m_UP": {
      "market_id": "0x123...",
      "slug": "btc-up-15min",
      "question": "Will BTC be up in 15 minutes?",
      "yes_token_id": "0xabc...",
      "no_token_id": "0xdef...",
      "discovered_at": "2025-12-17T13:20:30Z"
    },
    ...
  }
}
```

## API Usage

### Polymarket APIs

PolyQuant uses two public Polymarket APIs:

1. **Gamma Markets API** (`https://gamma-api.polymarket.com`)
   - Endpoint: `GET /markets`
   - Purpose: Market discovery and metadata
   - Pagination: `limit` and `offset` parameters

2. **CLOB API** (`https://clob.polymarket.com`)
   - Endpoint: `GET /prices-history`
   - Purpose: Historical price data
   - Parameters: `market`/`token_id`, `startTs`, `endTs`, `fidelity`

**No authentication required** - all endpoints are public.

### Rate Limiting

- Default delay: 0.5 seconds between requests
- Automatic retry: 3 attempts with exponential backoff (1s, 2s, 4s)
- Handles HTTP 429 (rate limit) and 5xx (server errors)

## Extending to Other Markets

To discover markets for different assets or time windows:

1. **Add asset keywords** in `polyquant/config.py`:
   ```python
   ASSET_KEYWORDS = {
       "BTC": ["BTC", "Bitcoin"],
       "DOGE": ["DOGE", "Dogecoin"],  # Add new asset
       ...
   }
   ```

2. **Modify time keywords** for different durations:
   ```python
   TIME_KEYWORDS = ["5"]  # For 5-minute markets
   ```

3. **Run discovery** with custom parameters:
   ```bash
   python scripts/download_history.py --assets DOGE --minutes 5 --start 2025-12-01 --end 2025-12-17
   ```

## Testing

Run unit tests:

```bash
pytest tests/
```

Run with coverage:

```bash
pytest tests/ --cov=polyquant --cov-report=html
```

## Troubleshooting

### No markets discovered

**Symptom**: `discover_markets.py` finds 0 markets

**Solutions**:
- Check that markets exist on Polymarket for the specified assets
- Verify keyword matching in `config.py` matches actual market questions
- Increase `max_markets` parameter in `discover_15min_markets()`
- Check logs for filtering details

### Empty price histories

**Symptom**: `download_history.py` returns empty DataFrames

**Solutions**:
- Verify date range is valid (not in the future)
- Check that markets were active during the specified period
- Inspect token IDs in metadata to ensure they're correct
- Try a different fidelity (e.g., `--fidelity 5` for 5-minute resolution)

### HTTP errors

**Symptom**: Requests fail with 429 or 5xx errors

**Solutions**:
- Increase `REQUEST_DELAY_SECONDS` in `config.py`
- Reduce `DEFAULT_PAGINATION_LIMIT` to fetch fewer markets per request
- Wait a few minutes and retry (may be temporary rate limiting)

### Token ID parsing errors

**Symptom**: Warnings about failed token ID extraction

**Solutions**:
- Inspect market data structure using Gamma API directly
- Update `extract_token_ids()` in `market_discovery.py` to handle new formats
- Check logs for the exact format received

## Configuration

Key settings in `polyquant/config.py`:

```python
# API endpoints
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"

# Rate limiting
REQUEST_DELAY_SECONDS = 0.5
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 1.0

# Default parameters
DEFAULT_FIDELITY = 1  # 1-minute resolution
DEFAULT_PAGINATION_LIMIT = 100
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "XRP"]
```

## License

This project is provided as-is for educational and research purposes.

## Disclaimer

This tool is for data collection and analysis only. It does not place trades or interact with Polymarket's trading infrastructure. Always verify data accuracy before using it for financial decisions.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass (`pytest tests/`)
5. Submit a pull request

## Support

For issues or questions:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review logs for detailed error messages
3. Open an issue with:
   - Error message and stack trace
   - Command that failed
   - Python version and OS
   - Relevant log output

---

**Built with ❤️ for the Polymarket community**
