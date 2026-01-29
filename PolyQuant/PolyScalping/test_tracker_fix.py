"""
수정된 tracker 테스트
"""
import asyncio
from tracker import MarketDataStreamer
from loguru import logger

async def test():
    tracker = MarketDataStreamer()

    # 콜백
    def on_message(asset_id, orderbook):
        bid = orderbook.get_best_bid()
        ask = orderbook.get_best_ask()
        logger.info(f"📨 {asset_id[:16]}... | bid={bid:.4f} ask={ask:.4f}")

    tracker.add_callback(on_message)

    # 시작
    await tracker.start()
    await asyncio.sleep(2)

    # 구독
    TEST_TOKEN_YES = "101676997363687199724245607342877036148401850938023978421879460310389391082353"
    TEST_TOKEN_NO = "4153292802911610701832309484716814274802943278345248636922528170020319407796"
    TEST_MARKET = "0xaf9d0e448129a9f657f851d49495ba4742055d80e0ef1166ba0ee81d4d594214"

    await tracker.subscribe(TEST_MARKET, [TEST_TOKEN_YES, TEST_TOKEN_NO])

    logger.info("Waiting for messages...")
    await asyncio.sleep(10)

    await tracker.stop()
    logger.success("Test complete")

if __name__ == "__main__":
    asyncio.run(test())
