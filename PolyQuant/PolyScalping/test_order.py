"""
Test placing a simple order to diagnose the issue
"""
import asyncio
from loguru import logger
from clients import PolymarketClient
from models import OrderSide

async def test_order():
    """Test placing a small order"""
    async with PolymarketClient() as client:
        if not client.clob_client:
            logger.error("No CLOB client available")
            return

        # Get an active market
        markets = await client.get_active_markets("BTC", limit=1)
        if not markets:
            logger.error("No markets found")
            return

        market = markets[0]
        logger.info(f"Testing with market: {market.get('question', 'Unknown')}")
        logger.info(f"Market data keys: {market.keys()}")

        # Get the YES token ID - check different possible structures
        yes_token = None
        no_token = None

        if "tokens" in market:
            tokens = market["tokens"]
            if len(tokens) >= 2:
                yes_token = tokens[0].get("token_id")
                no_token = tokens[1].get("token_id")

        # Try clobTokenIds as alternative (it's a JSON string)
        if not yes_token and "clobTokenIds" in market:
            import json
            tokens_str = market["clobTokenIds"]
            try:
                tokens = json.loads(tokens_str)
                if isinstance(tokens, list) and len(tokens) >= 2:
                    yes_token = tokens[0]
                    no_token = tokens[1]
            except:
                pass

        if not yes_token:
            logger.error(f"Could not find token IDs in market: {market}")
            return

        logger.info(f"YES token ID: {yes_token}")
        logger.info(f"NO token ID: {no_token}")

        # Try to place a very small order (1 USDC worth at 0.50 = 2 shares)
        logger.info("Attempting to place order: BUY 2.0 shares @ $0.50")

        try:
            resp = await client.place_order(
                token_id=yes_token,
                price=0.50,
                size=2.0,
                side=OrderSide.BUY,
                post_only=False
            )

            if resp:
                logger.success(f"Order SUCCESS: {resp}")
            else:
                logger.error("Order returned None")

        except Exception as e:
            logger.exception(f"Order failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_order())
