
import requests
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def inspect_kalshi_market():
    # Fetch a few markets from Kalshi to inspect structure
    url = "https://api.elections.kalshi.com/trade-api/v2/markets"
    params = {"limit": 5, "status": "open"}
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        markets = data.get("markets", [])
        if not markets:
            print("No markets found.")
            return

        print(f"\n--- Inspecting {len(markets)} Markets ---")
        
        for i, m in enumerate(markets):
            if i == 0:
                print("First Market Keys:", m.keys())
                print("First Market Dump:", json.dumps(m, indent=2))
            
            print(f"\nTitle: {m.get('title')}")
            print(f"Ticker: {m.get('ticker')}")
            print(f"Event Ticker: {m.get('event_ticker')}")
            
            # Print Price Fields
            print("Price Fields:")
            fields = ["yes_bid", "yes_ask", "yes_price", "last_price", "floor_price", "cap_price", "liquidity"]
            for f in fields:
                print(f"  {f}: {m.get(f)}")
                
            # Raw dump for URL analysis
            # print(json.dumps(m, indent=2))

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_kalshi_market()
