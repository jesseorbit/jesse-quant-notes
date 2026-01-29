"""
Test script to fetch top 10 markets by liquidity from Polymarket.
"""
import asyncio
from clients import PolymarketClient
from loguru import logger

async def main():
    """Fetch and display top 10 markets by liquidity."""
    client = PolymarketClient()

    # Fetch markets ordered by volume (proxy for liquidity)
    logger.info("Fetching top 10 markets by 24h volume...")
    markets = await client.get_active_markets(
        asset="",  # All assets
        limit=10,
        order="volume24hr",
        ascending=False
    )

    if not markets:
        logger.error("No markets found")
        return

    logger.info(f"\nTop 10 markets by liquidity:\n")
    logger.info("=" * 100)

    for idx, market in enumerate(markets[:10], 1):
        volume_24h = float(market.get('volume24hr', 0))
        liquidity = float(market.get('liquidity', 0))
        question = market.get('question', 'N/A')
        market_slug = market.get('market_slug', 'N/A')

        logger.info(f"\n{idx}. {question}")
        logger.info(f"   Slug: {market_slug}")
        logger.info(f"   24h Volume: ${volume_24h:,.2f}")
        logger.info(f"   Liquidity: ${liquidity:,.2f}")
        logger.info("-" * 100)

if __name__ == "__main__":
    asyncio.run(main())
