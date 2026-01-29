"""
WebSocket 연결 테스트 스크립트
실제로 메시지를 받는지 확인
"""
import asyncio
import aiohttp
import json
from loguru import logger

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

# 실제 토큰 ID (Trump deportation market - active YES token)
TEST_TOKEN_ID = "101676997363687199724245607342877036148401850938023978421879460310389391082353"

async def test_websocket():
    """WebSocket 연결 테스트"""
    logger.info(f"Connecting to: {WS_URL}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                WS_URL,
                heartbeat=10.0,
                timeout=aiohttp.ClientTimeout(total=None, sock_read=30)
            ) as ws:
                logger.success("✅ WebSocket CONNECTED!")

                # STEP 1: Send initial handshake (required by Polymarket protocol)
                logger.info("\n📤 Step 1: Sending initial handshake")
                init_payload = {
                    "assets_ids": [],
                    "type": "market"
                }
                logger.info(f"   Payload: {json.dumps(init_payload, indent=2)}")
                await ws.send_json(init_payload)
                logger.success("   ✓ Handshake sent!")
                await asyncio.sleep(0.5)

                # STEP 2: Subscribe to token
                logger.info("\n📤 Step 2: Subscribing to token")
                subscribe_payload = {
                    "operation": "subscribe",
                    "assets_ids": [TEST_TOKEN_ID]
                }
                logger.info(f"   Payload: {json.dumps(subscribe_payload, indent=2)}")
                await ws.send_json(subscribe_payload)
                logger.success("   ✓ Subscription sent!")
                await asyncio.sleep(0.5)

                # 메시지 대기
                logger.info("\n⏳ Waiting for messages (30 seconds)...")
                msg_count = 0
                start_time = asyncio.get_event_loop().time()

                async for msg in ws:
                    # Timeout check
                    if asyncio.get_event_loop().time() - start_time > 30:
                        logger.warning(f"\n⏰ Timeout after 30 seconds. Received {msg_count} messages.")
                        break

                    try:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                msg_count += 1
                                logger.success(f"\n📨 MESSAGE #{msg_count} RECEIVED!")
                                try:
                                    data = json.loads(msg.data)
                                    logger.info(f"   Data: {json.dumps(data, indent=2)[:500]}...")
                                except:
                                    logger.info(f"   Raw: {msg.data[:500]}...")
                            elif msg.type == aiohttp.WSMsgType.PONG:
                                logger.debug("⬅️  PONG received")
                            elif msg.type == aiohttp.WSMsgType.PING:
                                logger.debug("⬅️  PING received")
                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                logger.warning("❌ WebSocket closed by server")
                                break
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.error(f"❌ WebSocket error: {ws.exception()}")
                                break
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")

                if msg_count == 0:
                    logger.error("\n❌ NO MESSAGES RECEIVED!")
                    logger.error("   Possible issues:")
                    logger.error("   1. Wrong subscription format")
                    logger.error("   2. Invalid token ID")
                    logger.error("   3. Authentication required")
                    logger.error("   4. WebSocket endpoint changed")
                else:
                    logger.success(f"\n✅ SUCCESS! Received {msg_count} messages")

    except Exception as e:
        logger.error(f"❌ Connection failed: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(test_websocket())
