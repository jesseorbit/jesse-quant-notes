"""
BUY와 SELL 주문 테스트
"""
import asyncio
from loguru import logger
from clients import PolymarketClient
from models import OrderSide

async def test_sides():
    """BUY와 SELL 테스트"""
    async with PolymarketClient() as client:
        if not client.clob_client:
            logger.error("No CLOB client available")
            return

        # 활성 마켓 가져오기
        markets = await client.get_active_markets("BTC", limit=1)
        if not markets:
            logger.error("No markets found")
            return

        market = markets[0]
        logger.info(f"Testing with market: {market.get('question', 'Unknown')}")

        # Token IDs 추출
        import json
        yes_token = None
        no_token = None

        if "clobTokenIds" in market:
            tokens = json.loads(market["clobTokenIds"])
            if len(tokens) >= 2:
                yes_token = tokens[0]
                no_token = tokens[1]

        if not yes_token:
            logger.error("Could not find token IDs")
            return

        logger.info(f"YES token: {yes_token}")
        logger.info(f"NO token: {no_token}")

        # TEST 1: OrderSide.BUY로 YES 토큰 구매 (ENTER_YES 시나리오)
        logger.info("\n=== TEST 1: OrderSide.BUY with YES token ===")
        try:
            resp = await client.place_order(
                token_id=yes_token,
                price=0.50,
                size=5.0,  # Minimum size
                side=OrderSide.BUY,
                post_only=False
            )
            logger.info(f"Result: {resp}")
        except Exception as e:
            logger.error(f"Failed: {e}")

        await asyncio.sleep(1)

        # TEST 2: OrderSide.BUY로 NO 토큰 구매 (EXIT YES 시나리오)
        logger.info("\n=== TEST 2: OrderSide.BUY with NO token (EXIT YES) ===")
        try:
            resp = await client.place_order(
                token_id=no_token,
                price=0.50,
                size=5.0,
                side=OrderSide.BUY,
                post_only=False
            )
            logger.info(f"Result: {resp}")
        except Exception as e:
            logger.error(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_sides())
