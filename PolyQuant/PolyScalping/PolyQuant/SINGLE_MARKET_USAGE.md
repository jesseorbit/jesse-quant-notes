# Single Market History Fetcher - Usage Guide

## Overview

`fetch_single_market_history.py` downloads 3 months of historical YES/NO prices for a specific Polymarket market.

## Usage Options

### Option 1: By Slug (if market is in CLOB /markets endpoint)

```bash
python scripts/fetch_single_market_history.py \
  --slug btc-updown-15m-1765988100 \
  --days 90 \
  --fidelity 1
```

### Option 2: By Condition ID

```bash
python scripts/fetch_single_market_history.py \
  --condition-id 1765988100 \
  --days 90 \
  --fidelity 1
```

### Option 3: By Token IDs Directly (Recommended if market not found)

If the market isn't in the CLOB /markets endpoint, provide token IDs directly:

```bash
python scripts/fetch_single_market_history.py \
  --yes-token <YES_TOKEN_ID> \
  --no-token <NO_TOKEN_ID> \
  --start 2025-09-17 \
  --end 2025-12-17 \
  --fidelity 1
```

## Arguments

- `--slug`: Market slug from URL (e.g., `btc-updown-15m-1765988100`)
- `--condition-id`: Market condition ID (alternative to slug)
- `--yes-token`: YES token ID (bypasses market lookup if used with `--no-token`)
- `--no-token`: NO token ID (bypasses market lookup if used with `--yes-token`)
- `--days`: Number of days of history (default: 90)
- `--start`: Start date (ISO format like `2025-09-17` or unix timestamp)
- `--end`: End date (ISO format like `2025-12-17` or unix timestamp)
- `--fidelity`: Resolution in minutes (default: 1)

## Output Files

All files saved to `PolyQuant/data/`:

### Raw Data
- `data/raw/{identifier}_YES.csv` - YES token price history
- `data/raw/{identifier}_NO.csv` - NO token price history

### Processed Data
- `data/processed/{identifier}_merged.csv` - Merged YES/NO with derived columns:
  - `ts` - UTC timestamp
  - `yes_price` - YES token price
  - `no_price` - NO token price
  - `sum_price` - yes_price + no_price
  - `mispricing` - 1.0 - sum_price

### Metadata
- `data/metadata/{identifier}.json` - Market metadata and fetch parameters

## Examples

### Fetch last 7 days with 1-minute resolution
```bash
python scripts/fetch_single_market_history.py \
  --slug btc-updown-15m-1765988100 \
  --days 7 \
  --fidelity 1
```

### Fetch specific date range with 5-minute resolution
```bash
python scripts/fetch_single_market_history.py \
  --slug btc-updown-15m-1765988100 \
  --start 2025-12-01 \
  --end 2025-12-17 \
  --fidelity 5
```

### Fetch using token IDs directly
```bash
python scripts/fetch_single_market_history.py \
  --yes-token 21742633143463906290569050155826241533067272736897614950488156847949938836455 \
  --no-token 52114319501935453034729844448153092149500604208256027341502715627424149766613 \
  --days 90
```

## Notes

- **API Endpoints**: Uses CLOB API (`https://clob.polymarket.com`)
- **Rate Limiting**: 0.3s delay between requests, 3 retry attempts with exponential backoff
- **Parameter Flexibility**: Tries both `market` and `token_id` parameters for price history endpoint
- **No Authentication**: All endpoints are public, no API keys required

## Troubleshooting

### Market not found
If you get "Market not found" error:
1. The market may not be in the first 1000 results from `/markets`
2. Use `--yes-token` and `--no-token` to bypass market lookup
3. Get token IDs from the market page on Polymarket website

### Empty price history
- Verify the date range is valid (not in the future)
- Check that the market was active during that period
- Try a different fidelity value

### HTTP errors
- 429: Rate limited - script will automatically retry
- 5xx: Server error - script will automatically retry
- Check your internet connection
