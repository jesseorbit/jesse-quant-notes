"""
WebSocket 가격 vs Polymarket API 가격 비교
"""
import asyncio
import aiohttp
from tracker import MarketDataStreamer
from loguru import logger

# Test market - replace with current active market
TEST_MARKET = "0x1252c84fbc82fa1f317ee9fdaf18b0af43ebb319764b2140b4faf24ecff1648d"
TEST_TOKEN_UP = "46990995984311730403299224081165359062221905541960360160305692934134623049547"
TEST_TOKEN_DOWN = "89604707140280930321701518310339812713707018175031709435245166486787360677658"

async def get_api_price(token_id: str):
    """Get price from Polymarket API"""
    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                bids = data.get("bids", [])
                asks = data.get("asks", [])

                best_bid = float(bids[0]["price"]) if bids else 0.0
                best_ask = float(asks[0]["price"]) if asks else 0.0

                return best_bid, best_ask
    return 0.0, 0.0

async def test():
    logger.info("Starting price accuracy test...")

    # Start tracker
    tracker = MarketDataStreamer()
    await tracker.start()
    await asyncio.sleep(2)

    # Subscribe to market
    await tracker.subscribe(TEST_MARKET, [TEST_TOKEN_UP, TEST_TOKEN_DOWN])
    logger.info("Subscribed to market, waiting for prices...")
    await asyncio.sleep(5)

    # Get prices from WebSocket
    ws_up_bid, ws_up_ask = tracker.get_price(TEST_TOKEN_UP)
    ws_down_bid, ws_down_ask = tracker.get_price(TEST_TOKEN_DOWN)

    # Get prices from API
    api_up_bid, api_up_ask = await get_api_price(TEST_TOKEN_UP)
    api_down_bid, api_down_ask = await get_api_price(TEST_TOKEN_DOWN)

    # Compare
    logger.info("\n" + "="*80)
    logger.info("PRICE COMPARISON")
    logger.info("="*80)

    logger.info(f"\nUP Token ({TEST_TOKEN_UP[:16]}...):")
    logger.info(f"  WebSocket:  bid={ws_up_bid:.4f}, ask={ws_up_ask:.4f}")
    logger.info(f"  API:        bid={api_up_bid:.4f}, ask={api_up_ask:.4f}")
    bid_diff = abs(ws_up_bid - api_up_bid)
    ask_diff = abs(ws_up_ask - api_up_ask)
    if bid_diff > 0.01 or ask_diff > 0.01:
        logger.error(f"  ❌ MISMATCH! bid diff={bid_diff:.4f}, ask diff={ask_diff:.4f}")
    else:
        logger.success(f"  ✅ Match!")

    logger.info(f"\nDOWN Token ({TEST_TOKEN_DOWN[:16]}...):")
    logger.info(f"  WebSocket:  bid={ws_down_bid:.4f}, ask={ws_down_ask:.4f}")
    logger.info(f"  API:        bid={api_down_bid:.4f}, ask={api_down_ask:.4f}")
    bid_diff = abs(ws_down_bid - api_down_bid)
    ask_diff = abs(ws_down_ask - api_down_ask)
    if bid_diff > 0.01 or ask_diff > 0.01:
        logger.error(f"  ❌ MISMATCH! bid diff={bid_diff:.4f}, ask diff={ask_diff:.4f}")
    else:
        logger.success(f"  ✅ Match!")

    logger.info(f"\nPrice sum check:")
    logger.info(f"  UP ask + DOWN ask = {ws_up_ask + ws_down_ask:.4f} (should be ≈ 1.0)")

    logger.info("\n" + "="*80)

    await tracker.stop()

if __name__ == "__main__":
    asyncio.run(test())
