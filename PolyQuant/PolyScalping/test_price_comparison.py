"""
가격 비교 테스트: WebSocket vs Polymarket API
"""
import asyncio
import aiohttp
from loguru import logger

# 테스트할 마켓 정보
TEST_MARKET_ID = "0xaf9d0e448129a9f657f851d49495ba4742055d80e0ef1166ba0ee81d4d594214"
TEST_TOKEN_YES = "101676997363687199724245607342877036148401850938023978421879460310389391082353"
TEST_TOKEN_NO = "4153292802911610701832309484716814274802943278345248636922528170020319407796"

async def get_orderbook_from_api(token_id: str):
    """Polymarket API에서 orderbook 가져오기"""
    url = f"https://clob.polymarket.com/book?token_id={token_id}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    # 최고 매수/매도 가격
                    bids = data.get("bids", [])
                    asks = data.get("asks", [])

                    best_bid = float(bids[0]["price"]) if bids else 0.0
                    best_ask = float(asks[0]["price"]) if asks else 0.0

                    return best_bid, best_ask, data
                else:
                    logger.error(f"API error: {resp.status}")
                    return 0.0, 0.0, None
    except Exception as e:
        logger.error(f"Failed to fetch orderbook: {e}")
        return 0.0, 0.0, None

async def main():
    logger.info(f"Testing market: {TEST_MARKET_ID[:16]}...")
    logger.info(f"YES token: {TEST_TOKEN_YES}")
    logger.info(f"NO token: {TEST_TOKEN_NO}")
    logger.info("")

    # YES 토큰 가격
    logger.info("📊 Fetching YES token orderbook from API...")
    yes_bid, yes_ask, yes_data = await get_orderbook_from_api(TEST_TOKEN_YES)
    logger.info(f"   YES: bid={yes_bid:.4f}, ask={yes_ask:.4f}")

    if yes_data:
        bids = yes_data.get("bids", [])[:3]
        asks = yes_data.get("asks", [])[:3]
        logger.info(f"   Top 3 bids: {bids}")
        logger.info(f"   Top 3 asks: {asks}")

    logger.info("")

    # NO 토큰 가격
    logger.info("📊 Fetching NO token orderbook from API...")
    no_bid, no_ask, no_data = await get_orderbook_from_api(TEST_TOKEN_NO)
    logger.info(f"   NO: bid={no_bid:.4f}, ask={no_ask:.4f}")

    if no_data:
        bids = no_data.get("bids", [])[:3]
        asks = no_data.get("asks", [])[:3]
        logger.info(f"   Top 3 bids: {bids}")
        logger.info(f"   Top 3 asks: {asks}")

    logger.info("")
    logger.info("💡 Expected properties:")
    logger.info(f"   1. YES ask + NO ask should be close to 1.0")
    logger.info(f"      Actual: {yes_ask:.4f} + {no_ask:.4f} = {yes_ask + no_ask:.4f}")
    logger.info(f"   2. Bid should be < Ask for each token")
    logger.info(f"      YES: {yes_bid:.4f} < {yes_ask:.4f} = {yes_bid < yes_ask}")
    logger.info(f"      NO: {no_bid:.4f} < {no_ask:.4f} = {no_bid < no_ask}")

if __name__ == "__main__":
    asyncio.run(main())
