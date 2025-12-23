# jesse-quant-notes

Personal quant research notes and scratchpad code.

This repository is experiment-first: small scripts, prototypes, and notes used to test trading ideas and prediction-market analytics. Expect rough edges and frequent iteration.

## Contents

- **Arbitrage/**  
  Experiments for cross-venue market matching and simple arbitrage scanning (e.g., Polymarket ↔ Kalshi).

- **PolyQuant/**  
  Prediction-market quant utilities, datasets, and research scripts.

- **config.py**  
  Central configuration (endpoints, constants, local settings).

## Quick start

### 1) Create a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate
2) Install dependencies
If you have a requirements.txt:

bash
Copy code
pip install -r requirements.txt
Otherwise, install what the scripts require (commonly: requests, pandas, numpy).

3) Configure
Prefer environment variables for any secrets. Do not commit API keys.

Example:

bash
Copy code
export POLYMARKET_API_KEY="..."
export OPINION_API_KEY="..."
How to run
This repo contains multiple small experiments, so entry points vary by folder.

A typical workflow:

Pull markets / prices / orderbooks

Normalize and match markets

Compute spreads / signals

Log or export results

To discover options for a script:

bash
Copy code
python path/to/script.py --help
Notes
Research sandbox, not production trading code.

No financial advice.

Never commit secrets.

License
Private / All rights reserved (unless a LICENSE file is added later).
