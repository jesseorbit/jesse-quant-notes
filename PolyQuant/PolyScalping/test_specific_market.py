"""
특정 BTC 15분 마켓 테스트
실제 활성 마켓으로 전략 테스트
"""
import asyncio
import time
from datetime import datetime
from loguru import logger

from btc_price_tracker import BTCPriceTracker
from scalping_strategy import AdvancedScalpingStrategy, MarketContext
from tracker import MarketDataStreamer
from clients import PolymarketClient


async def test_live_market():
    """
    실제 활성 마켓으로 테스트
    URL: https://polymarket.com/event/btc-updown-15m-1768889700
    """
    logger.info("="*100)
    logger.info("Testing with LIVE BTC 15m Market")
    logger.info("="*100)

    # 마켓 정보 (WebFetch에서 가져온 정보)
    market_info = {
        "id": "btc-updown-15m-1768889700",
        "question": "Bitcoin Up or Down - January 20, 1:15AM-1:30AM ET",
        "token_up": "102532121706924677833261070243482340983536028472869525932481339344853499718576",
        "token_down": "29574454140413362039745053514068295994534426287067850713460845525892853027494",
        "end_time": "2026-01-20T06:30:00Z",  # 6:30 AM ET
        "current_price_up": 0.565,
        "current_price_down": 0.435,
        "volume": 5488,
        "liquidity": 17950.24
    }

    logger.info(f"\nMarket: {market_info['question']}")
    logger.info(f"End Time: {market_info['end_time']}")
    logger.info(f"Current Prices - UP: {market_info['current_price_up']:.3f}, DOWN: {market_info['current_price_down']:.3f}")
    logger.info(f"Liquidity: ${market_info['liquidity']:,.2f}")

    # BTC 가격 추적기 시작
    price_tracker = BTCPriceTracker()
    await price_tracker.start()

    # 초기 가격 대기
    logger.info("\nWaiting for BTC price...")
    for _ in range(10):
        if price_tracker.get_current_price():
            break
        await asyncio.sleep(1)

    start_btc = price_tracker.get_current_price()
    logger.info(f"Current BTC Price: ${start_btc:,.2f}")

    # 오더북 추적기 시작
    orderbook_tracker = MarketDataStreamer()
    await orderbook_tracker.start()

    # 마켓 구독
    logger.info("\nSubscribing to market orderbook...")
    await orderbook_tracker.subscribe(
        market_info["id"],
        [market_info["token_up"], market_info["token_down"]]
    )

    # 전략 초기화
    strategy = AdvancedScalpingStrategy(price_tracker)

    # MarketContext 생성
    # 마켓 종료 시간 파싱
    end_dt = datetime.fromisoformat(market_info["end_time"].replace("Z", "+00:00"))
    end_ts = end_dt.timestamp()

    ctx = MarketContext(
        market_id=market_info["id"],
        start_time=time.time(),
        end_time=end_ts,
        start_price=start_btc,
        token_yes=market_info["token_up"],
        token_no=market_info["token_down"],
        yes_price=market_info["current_price_up"],
        no_price=market_info["current_price_down"],
    )

    # 남은 시간 계산
    remaining_seconds = end_ts - time.time()
    remaining_minutes = remaining_seconds / 60

    logger.info(f"Time remaining: {remaining_minutes:.2f} minutes ({remaining_seconds:.0f} seconds)")

    if remaining_seconds < 0:
        logger.warning("Market has already expired!")
        await price_tracker.stop()
        await orderbook_tracker.stop()
        return

    # 모니터링 시작
    logger.info("\n" + "="*100)
    logger.info("Starting Market Monitoring (30 seconds)")
    logger.info("="*100 + "\n")

    for i in range(15):  # 30초 동안 (2초마다)
        await asyncio.sleep(2)

        # 오더북에서 최신 가격 가져오기
        bid_up, ask_up = orderbook_tracker.get_price(ctx.token_yes)
        bid_down, ask_down = orderbook_tracker.get_price(ctx.token_no)

        if ask_up > 0:
            ctx.yes_price = ask_up
        if ask_down > 0:
            ctx.no_price = ask_down

        # 현재 BTC 가격
        current_btc = price_tracker.get_current_price()

        # 가격 변화
        if current_btc and start_btc:
            btc_change = current_btc - start_btc
            btc_change_pct = (btc_change / start_btc) * 100
        else:
            btc_change_pct = 0

        # 전략 평가
        signal = strategy.evaluate_market(ctx)

        # 로그 출력
        logger.info(f"[{i+1}/15] BTC: ${current_btc:,.2f} ({btc_change_pct:+.3f}%) | UP: {ctx.yes_price:.3f} | DOWN: {ctx.no_price:.3f}")

        if signal:
            logger.success(f"  🔥 SIGNAL: {signal.action}")
            logger.info(f"     Reason: {signal.reason}")
            logger.info(f"     Confidence: {signal.confidence:.1%}")
            logger.info(f"     Edge: {signal.edge:.1%}")
            logger.info(f"     Urgency: {signal.urgency}")
            logger.info(f"     Recommended Size: {signal.size}")

            # 실제 거래는 하지 않음 (테스트 모드)
            logger.warning("     [DRY RUN - No actual trade executed]")
        else:
            # 포지션 없으면 왜 진입 안하는지 설명
            if ctx.position_yes < 0.1 and ctx.position_no < 0.1:
                from btc_price_tracker import MarketPriceAnalyzer
                analyzer = MarketPriceAnalyzer(price_tracker)

                analysis = analyzer.analyze_market_opportunity(
                    market_start_time=ctx.start_time,
                    market_end_time=ctx.end_time,
                    start_price=ctx.start_price,
                    yes_price=ctx.yes_price,
                    no_price=ctx.no_price
                )

                logger.debug(f"     Analysis: {analysis['predicted_outcome']} | Conf: {analysis['confidence']:.1%} | Edge: {analysis['edge']:.1%}")
                logger.debug(f"     Reason: {analysis['reason']}")

        # 포지션 요약 (있으면)
        summary = strategy.get_position_summary(ctx)
        if summary.get("has_position"):
            logger.info(f"     Position: {summary['side']} {summary['size']:.1f} @ {summary['avg_entry_price']:.3f}")
            logger.info(f"     Unrealized PnL: {summary['unrealized_pnl_pct']:+.2%} (${summary['unrealized_pnl_usdc']:+.2f})")

    # 정리
    await price_tracker.stop()
    await orderbook_tracker.stop()

    logger.info("\n" + "="*100)
    logger.success("Test Complete!")
    logger.info("="*100)


async def get_market_from_api():
    """
    API를 통해 마켓 정보 직접 가져오기
    """
    logger.info("Fetching market from Polymarket API...")

    client = PolymarketClient()

    # 검색으로 마켓 찾기
    markets = await client.search_markets("BTC 15m", limit=10)

    logger.info(f"Found {len(markets)} markets")

    for market in markets[:3]:
        logger.info(f"\n{market.get('question')}")
        logger.info(f"  ID: {market.get('id')}")
        logger.info(f"  Slug: {market.get('slug')}")
        logger.info(f"  Active: {market.get('active')}")
        logger.info(f"  End: {market.get('endDate')}")

        # 토큰 확인
        import json
        tokens = json.loads(market.get('clobTokenIds', '[]'))
        if tokens:
            logger.info(f"  Tokens: {len(tokens)}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--api":
        asyncio.run(get_market_from_api())
    else:
        asyncio.run(test_live_market())
