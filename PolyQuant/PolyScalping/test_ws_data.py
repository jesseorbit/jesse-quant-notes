"""
WebSocket 데이터 수신 테스트 - 실제로 무엇을 받는지 확인
"""
import asyncio
import aiohttp
import json
from loguru import logger

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

# Trump deportation market
TEST_TOKEN_YES = "101676997363687199724245607342877036148401850938023978421879460310389391082353"
TEST_TOKEN_NO = "4153292802911610701832309484716814274802943278345248636922528170020319407796"

async def test():
    logger.info("Connecting to WebSocket...")

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(
            WS_URL,
            heartbeat=15.0,
            timeout=aiohttp.ClientTimeout(total=None, sock_read=120)
        ) as ws:
            logger.success("✅ Connected!")

            # Handshake
            await ws.send_json({"assets_ids": [], "type": "market"})
            logger.info("📤 Sent handshake")
            await asyncio.sleep(0.5)

            # Subscribe
            await ws.send_json({
                "operation": "subscribe",
                "assets_ids": [TEST_TOKEN_YES, TEST_TOKEN_NO]
            })
            logger.info("📤 Subscribed to YES and NO tokens")
            logger.info(f"   YES: {TEST_TOKEN_YES}")
            logger.info(f"   NO: {TEST_TOKEN_NO}")

            # Wait for messages
            logger.info("\n⏳ Waiting for messages (60 seconds)...\n")
            msg_count = 0
            start = asyncio.get_event_loop().time()

            async for msg in ws:
                if asyncio.get_event_loop().time() - start > 60:
                    break

                if msg.type == aiohttp.WSMsgType.TEXT:
                    msg_count += 1
                    data = json.loads(msg.data)

                    logger.info(f"\n{'='*80}")
                    logger.info(f"📨 MESSAGE #{msg_count}")
                    logger.info(f"{'='*80}")

                    # Pretty print the data
                    logger.info(f"Type: {type(data)}")

                    if isinstance(data, list):
                        logger.info(f"Array length: {len(data)}")
                        for i, item in enumerate(data[:3]):  # First 3 items
                            logger.info(f"\n  Item {i}:")
                            logger.info(f"    Keys: {list(item.keys())}")

                            # Check for asset_id
                            if "asset_id" in item:
                                asset_id = item["asset_id"]
                                logger.info(f"    asset_id: {asset_id[:20]}...")
                                logger.info(f"    Is YES token: {asset_id == TEST_TOKEN_YES}")
                                logger.info(f"    Is NO token: {asset_id == TEST_TOKEN_NO}")

                            # Check for bids/asks
                            if "bids" in item:
                                bids = item["bids"]
                                logger.info(f"    bids: {len(bids)} levels")
                                if bids:
                                    logger.info(f"      Best bid: {bids[0]}")

                            if "asks" in item:
                                asks = item["asks"]
                                logger.info(f"    asks: {len(asks)} levels")
                                if asks:
                                    logger.info(f"      Best ask: {asks[0]}")

                            # Check for price_changes
                            if "price_changes" in item:
                                changes = item["price_changes"]
                                logger.info(f"    price_changes: {len(changes)} changes")
                                for change in changes[:2]:  # First 2 changes
                                    logger.info(f"      {change}")

                    elif isinstance(data, dict):
                        logger.info(f"Dict keys: {list(data.keys())}")
                        logger.info(f"Data: {json.dumps(data, indent=2)[:500]}")

                    # Stop after 5 messages
                    if msg_count >= 5:
                        logger.success(f"\n✅ Received {msg_count} messages - stopping")
                        break

            if msg_count == 0:
                logger.error("\n❌ NO MESSAGES RECEIVED!")
            else:
                logger.success(f"\n✅ Test complete - received {msg_count} messages")

if __name__ == "__main__":
    asyncio.run(test())
