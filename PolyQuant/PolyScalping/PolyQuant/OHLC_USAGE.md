# OHLC Data Fetcher Usage Guide

## Overview

The `fetch_ohlc_data.py` script fetches continuous price data from Polymarket and converts it to OHLC (Open, High, Low, Close) candlestick format. This is useful for technical analysis, backtesting trading strategies, and visualizing price movements.

## Features

- ✅ Fetches continuous price data for BTC 15m markets (and other Polymarket markets)
- ✅ Converts to OHLC format with configurable timeframes (1m, 5m, 15m, 1h, 4h, 1d)
- ✅ Exports to CSV format
- ✅ Supports both YES and NO token prices
- ✅ Includes metadata (timestamps, candle counts, etc.)
- ✅ Flexible date range selection
- ✅ Automatic retry logic for API failures

## Installation

Make sure you have the required dependencies:

```bash
pip install pandas requests python-dateutil
```

## Basic Usage

### 1. Fetch 15-minute OHLC candles for a BTC market

```bash
python scripts/fetch_ohlc_data.py --slug btc-updown-15m-1765988100 --timeframe 15m --days 7
```

This will:
- Fetch the last 7 days of price data
- Convert to 15-minute OHLC candles
- Save to `data/ohlc/btc-updown-15m-1765988100_15m_ohlc.csv`

### 2. Fetch 1-hour candles with custom date range

```bash
python scripts/fetch_ohlc_data.py \
  --slug btc-updown-15m-1765988100 \
  --timeframe 1h \
  --start 2025-12-01 \
  --end 2025-12-19
```

### 3. Fetch 5-minute candles for the last 30 days

```bash
python scripts/fetch_ohlc_data.py --slug btc-updown-15m-1765988100 --timeframe 5m --days 30
```

### 4. Use direct token IDs (skip market lookup)

```bash
python scripts/fetch_ohlc_data.py \
  --yes-token 0x1234... \
  --no-token 0x5678... \
  --timeframe 15m \
  --days 7
```

## Command-Line Arguments

| Argument | Description | Default | Example |
|----------|-------------|---------|---------|
| `--slug` | Market slug identifier | - | `btc-updown-15m-1765988100` |
| `--condition-id` | Market condition ID (alternative to slug) | - | `1765988100` |
| `--yes-token` | YES token ID (with `--no-token`) | - | `0x1234...` |
| `--no-token` | NO token ID (with `--yes-token`) | - | `0x5678...` |
| `--timeframe` | OHLC candle timeframe | `15m` | `1m`, `5m`, `15m`, `1h`, `4h`, `1d` |
| `--days` | Number of days of history | `7` | `30` |
| `--start` | Start date (ISO or unix timestamp) | - | `2025-12-01` |
| `--end` | End date (ISO or unix timestamp) | - | `2025-12-19` |
| `--fidelity` | API fetch resolution in minutes | `1` | `1`, `5`, `15` |
| `--output-dir` | Output directory for CSV files | `data/ohlc` | `/path/to/output` |

## Output Format

### CSV File Structure

The output CSV contains the following columns:

```csv
timestamp,yes_open,yes_high,yes_low,yes_close,yes_count,no_open,no_high,no_low,no_close,no_count
2025-12-19 00:00:00+00:00,0.52,0.54,0.51,0.53,15,0.48,0.49,0.46,0.47,15
2025-12-19 00:15:00+00:00,0.53,0.55,0.52,0.54,15,0.47,0.48,0.45,0.46,15
...
```

**Columns:**
- `timestamp`: Start time of the candle (UTC)
- `yes_open`: Opening price for YES token
- `yes_high`: Highest price for YES token
- `yes_low`: Lowest price for YES token
- `yes_close`: Closing price for YES token
- `yes_count`: Number of data points in this candle
- `no_open`: Opening price for NO token
- `no_high`: Highest price for NO token
- `no_low`: Lowest price for NO token
- `no_close`: Closing price for NO token
- `no_count`: Number of data points in this candle

### Metadata File

A JSON metadata file is also created with the same basename:

```json
{
  "slug": "btc-updown-15m-1765988100",
  "market_id": "1765988100",
  "question": "Will Bitcoin price be up or down in 15 minutes?",
  "yes_token_id": "0x1234...",
  "no_token_id": "0x5678...",
  "start_ts": 1733961600,
  "end_ts": 1734566400,
  "start_iso": "2025-12-12T00:00:00",
  "end_iso": "2025-12-19T00:00:00",
  "api_fidelity": 1,
  "ohlc_timeframe": "15m",
  "ohlc_timeframe_minutes": 15,
  "candles_count": 672,
  "fetched_at": "2025-12-19T09:38:00Z"
}
```

## Timeframe Options

The `--timeframe` parameter supports the following formats:

- **Minutes**: `1m`, `5m`, `15m`, `30m`
- **Hours**: `1h`, `2h`, `4h`, `6h`, `12h`
- **Days**: `1d`, `7d`

## Tips

### 1. Choosing the Right Fidelity

The `--fidelity` parameter controls how granular the raw data is before OHLC aggregation:

- **High granularity** (`--fidelity 1`): More accurate OHLC candles, but slower API calls
- **Low granularity** (`--fidelity 5` or `--fidelity 15`): Faster, but less precise

**Recommendation**: Use `--fidelity 1` for timeframes ≤ 15m, and `--fidelity 5` for larger timeframes.

### 2. Finding Market Slugs

To find BTC 15m market slugs, use the existing discovery script:

```bash
python diagnose_actual_markets.py
```

Or check recent markets at: https://polymarket.com

### 3. Continuous Data Collection

For continuous monitoring, you can set up a cron job or scheduled task:

```bash
# Fetch every hour
0 * * * * cd /Users/jessesung/PolyQuant && python scripts/fetch_ohlc_data.py --slug btc-updown-15m-CURRENT --timeframe 15m --days 1
```

## Examples

### Example 1: Quick 15m candles for last 24 hours

```bash
python scripts/fetch_ohlc_data.py --slug btc-updown-15m-1765988100 --timeframe 15m --days 1
```

### Example 2: High-resolution 1m candles for backtesting

```bash
python scripts/fetch_ohlc_data.py \
  --slug btc-updown-15m-1765988100 \
  --timeframe 1m \
  --fidelity 1 \
  --days 7
```

### Example 3: Daily candles for long-term analysis

```bash
python scripts/fetch_ohlc_data.py \
  --slug btc-updown-15m-1765988100 \
  --timeframe 1d \
  --days 90
```

## Troubleshooting

### Issue: "Market not found"

**Solution**: Verify the slug is correct. Use `diagnose_actual_markets.py` to find active markets.

### Issue: "No price history available"

**Solution**: The market might be too new or inactive. Try a different date range or market.

### Issue: API rate limiting

**Solution**: The script has built-in retry logic. If you still hit limits, increase `REQUEST_DELAY` in the script.

## Next Steps

After fetching OHLC data, you can:

1. **Visualize** with matplotlib or plotly
2. **Analyze** with pandas for statistical insights
3. **Backtest** trading strategies
4. **Train** machine learning models

## Related Scripts

- `fetch_single_market_history.py` - Fetch raw price data without OHLC conversion
- `diagnose_actual_markets.py` - Find active BTC/ETH/SOL/XRP markets
- `fetch_btc_updown_15m_90d.py` - Specialized BTC 15m fetcher
