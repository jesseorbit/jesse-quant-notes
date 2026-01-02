
import json
import sys

try:
    with open('opinion_response_auth.json', 'r') as f:
        data = json.load(f)
    
    # print(f"Top level type: {type(data)}")
    
    if isinstance(data, dict):
        # print(f"Keys: {list(data.keys())}")
        result = data.get("result")
        if result:
            # print(f"Result type: {type(result)}")
            if isinstance(result, dict):
                # print(f"Result keys: {list(result.keys())}")
                if "list" in result:
                     print(f"Count in result['list']: {len(result['list'])}")
                     # Sample one
                     if len(result['list']) > 0:
                         print(f"Sample item status: {result['list'][0].get('status')}")
                         # Count by status
                         statuses = {}
                         for m in result['list']:
                             s = m.get('status')
                             statuses[s] = statuses.get(s, 0) + 1
                         print(f"Status distribution: {statuses}")
            elif isinstance(result, list):
                print(f"Count in result (list): {len(result)}")
        else:
            # print("No 'result' key.")
            markets = data.get("markets", data.get("data"))
            if markets:
                print(f"Count in data/markets: {len(markets)}")
    elif isinstance(data, list):
        print(f"Count top level list: {len(data)}")

except Exception as e:
    print(f"Error: {e}")
