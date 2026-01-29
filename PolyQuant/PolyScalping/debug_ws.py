import asyncio
import aiohttp
import json
from config import config
from clients import PolymarketClient

async def main():
    # 1. Get a valid token ID
    print("Fetching active BTC market...")
    async with PolymarketClient() as client:
        markets = await client.get_active_markets("BTC")
        if not markets:
            print("No markets found.")
            return
        
        m = markets[0]
        if 'clobTokenIds' in m:
            tids = json.loads(m['clobTokenIds'])
            token_id = tids[0]
        elif 'tokens' in m:
            token_id = m['tokens'][0]['id']
        else:
            print("No tokens found")
            return
            
        print(f"Testing with Token ID: {token_id} (Market: {m.get('question')})")

    # 2. Connect to WS
    url = config.polymarket_ws_url
    print(f"Connecting to {url}...")
    
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url) as ws:
            print("Connected.")
            
            # Try assets_ids
            payload = {
                "assets_ids": [token_id],
                "type": "market"
            }
            print(f"Sending: {json.dumps(payload)}")
            await ws.send_json(payload)
            
            # Read a few messages
            for _ in range(5):
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=5.0)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        print(f"Received: {msg.data[:500]}...") # Truncate
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        print("Closed")
                        break
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print("Error")
                        break
                except asyncio.TimeoutError:
                    print("Timeout waiting for msg")
                    break

if __name__ == "__main__":
    asyncio.run(main())
