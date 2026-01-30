# Prediction Market Arbitrage Scanner

A real-time scanner that monitors **Polymarket**, **Kalshi**, and **Opinion Labs** to surface **risk-free arbitrage** opportunities across prediction markets.

---

## 🎯 Features
- **Multi-venue support**: Polymarket, Kalshi, Opinion Labs
- **Real-time data ingestion**: via each venue’s official API
- **Smart market matching**: automatic event alignment using fuzzy matching
- **Arbitrage detection**: identifies risk-free combinations and computes ROI
- **Async-first architecture**: fast collection with `async/await`

---

## 🏢 Supported Platforms

| Platform      | API Auth Required | Status |
|--------------|-------------------|--------|
| Polymarket   | No                | ✅ Always on |
| Kalshi       | No                | ✅ Always on |
| Opinion Labs | Yes (API Key)     | ⚠️ Optional |

---

## 📁 Project Structure

```

Arbitrage/
├── main.py                  # Main entry point
├── models.py                # Data model definitions
├── matcher.py               # Fuzzy matching engine
├── services/
│   ├── **init**.py
│   ├── polymarket.py        # Polymarket data collector
│   └── opinion.py           # Opinion Labs data collector
├── utils/
│   ├── **init**.py
│   └── text_processing.py   # Text normalization utilities
├── requirements.txt         # Python dependencies
└── README.md                # This file

````

---

## 🚀 Quick Start

### 1) Install dependencies
```bash
cd Arbitrage
pip install -r requirements.txt
````

### 2) Set Opinion Labs API Key (optional)

To enable Opinion Labs scanning, you need an API key.

**Get an API key**

* Fill out the Opinion Labs API request form
* Receive your API key

**Configure**

```bash
# Option 1: Environment variable
export OPINION_API_KEY="your_api_key_here"

# Option 2: .env file
cp .env.example .env
# Open .env and paste your key
```

### 3) Run the scanner

```bash
python main.py
```

---

## 📊 How It Works

### 1) Data Collection

**Polymarket (Gamma API)**

* Endpoint: `GET https://gamma-api.polymarket.com/events`
* Params: `active=true`, `closed=false`, `limit=100`
* Parsing: `outcomePrices[0] = YES`, `outcomePrices[1] = NO`
* Auth: not required

**Kalshi**

* Endpoint: `GET https://api.elections.kalshi.com/trade-api/v2/markets`
* Params: `status=open`, `limit=100`
* Parsing: `yes_price` (cents → decimal), `no_price` (cents → decimal)
* Auth: not required

**Opinion Labs**

* Endpoint: `GET https://proxy.opinion.trade:8443/openapi/market`
* Params: `limit=100`
* Headers: `apikey: <your_api_key>`
* Parsing: uses `yes_price`, `no_price`, or `probability` fields depending on payload
* Auth: API key required

---

### 2) Data Normalization

All venue-specific markets are converted into a unified `StandardMarket` format:

```python
@dataclass
class StandardMarket:
    platform: str        # e.g. 'POLY', 'KALSHI', 'OPINION'
    market_id: str       # Venue-specific unique ID
    title: str           # Normalized title
    price_yes: float     # YES price (0.0 ~ 1.0)
    price_no: float      # NO price (0.0 ~ 1.0)
    volume: float        # Volume (USD)
    url: str             # Market URL
```

---

### 3) Fuzzy Matching

* Algorithm: `rapidfuzz.fuzz.token_sort_ratio`
* Threshold: similarity score ≥ **85**
* Validation: at least **2 shared keywords**

---

### 4) Arbitrage Calculation

**Strategies**

* Strategy 1: Buy **Polymarket YES** + Buy **Opinion NO**
* Strategy 2: Buy **Polymarket NO** + Buy **Opinion YES**

**Condition**

* `Total Cost < 0.98` (require at least **2%** margin)
* `Profit = 1.0 - Total Cost`

**ROI**

* `ROI% = (Profit / Total Cost) × 100`

---

## 📈 Output Example

```
================================================================================
ARBITRAGE SCANNER RESULTS
================================================================================

Found 5 arbitrage opportunities!

--- Opportunity #1 ---
ROI: 3.45%
Profit Margin: $0.0332
Total Cost: $0.9668
Match Score: 92.5/100

Polymarket:
  Title: will bitcoin reach 100000 by end of 2024
  YES: $0.6500 | NO: $0.3500
  URL: https://polymarket.com/event/bitcoin-100k-2024

Opinion Labs:
  Title: bitcoin price above 100k before 2025
  YES: $0.3168 | NO: $0.6832
  URL: https://opinion.trade/market/btc-100k-2024
```

---

## 🔧 Configuration

Adjust settings in `main.py`:

```python
# Matching configuration
matcher = MarketMatcher(
    similarity_threshold=85.0,  # Similarity threshold (0-100)
    min_common_keywords=2       # Minimum number of shared keywords
)

# Arbitrage configuration
opportunities = matcher.calculate_arbitrage(
    matches,
    min_margin=0.02,  # Minimum margin (2%)
    max_cost=0.98     # Maximum total cost (98%)
)
```

---

## 📝 Output Files

* `arbitrage_results.json`: detailed opportunity dump
* `arbitrage_scanner.log`: runtime logs

---

## ⚠️ Important Notes

* **API rate limits**: respect each venue’s API limits
* **Fees**: include platform fees in real trading decisions
* **Price movement**: quotes can move quickly in real time
* **Risk disclaimer**: for educational use; real trading can lose money

---

## 🔮 Future Enhancements

* FastAPI server
* Next.js dashboard UI
* Real-time updates via WebSockets
* Alerting (Telegram/Discord)
* Backtesting
* Optional auto-execution

---

## 📄 License

MIT License

```
