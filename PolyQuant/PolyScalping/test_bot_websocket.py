"""
봇의 WebSocket이 정상 작동하는지 테스트
"""
import asyncio
from tracker import MarketDataStreamer
from loguru import logger

async def test_bot_websocket():
    """봇의 WebSocket 테스트"""
    tracker = MarketDataStreamer()

    # 메시지 수신 콜백
    message_count = 0
    def on_message(asset_id, orderbook):
        nonlocal message_count
        message_count += 1
        logger.success(f"📨 Message #{message_count} | Asset: {asset_id[:16]}... | Bid: {orderbook.get_best_bid():.4f} | Ask: {orderbook.get_best_ask():.4f}")

    tracker.add_callback(on_message)

    # 트래커 시작
    await tracker.start()
    logger.info("Tracker started, waiting for connection...")
    await asyncio.sleep(2)

    # 마켓 구독
    market_id = "0xaf9d0e448129a9f657f851d49495ba4742055d80e0ef1166ba0ee81d4d594214"
    token_ids = [
        "101676997363687199724245607342877036148401850938023978421879460310389391082353",
        "4153292802911610701832309484716814274802943278345248636922528170020319407796"
    ]

    logger.info(f"Subscribing to market: {market_id[:16]}...")
    await tracker.subscribe(market_id, token_ids)

    # 메시지 대기
    logger.info("Waiting for messages (15 seconds)...")
    await asyncio.sleep(15)

    # 결과
    logger.info(f"\n{'='*60}")
    if message_count > 0:
        logger.success(f"✅ SUCCESS! Received {message_count} messages")
        logger.success("✅ Bot's WebSocket is working perfectly!")
    else:
        logger.error(f"❌ FAILED! No messages received")
        logger.error("❌ Bot's WebSocket is NOT working")
    logger.info(f"{'='*60}\n")

    await tracker.stop()

if __name__ == "__main__":
    asyncio.run(test_bot_websocket())
