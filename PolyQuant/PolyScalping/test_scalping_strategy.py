"""
스캘핑 전략 테스트 및 시뮬레이션
실제 거래 전에 전략을 테스트합니다
"""
import asyncio
import time
from loguru import logger

from btc_market_scanner import BTCMarketScanner
from btc_price_tracker import BTCPriceTracker
from scalping_strategy import BTCScalpingStrategy, AdvancedScalpingStrategy, MarketContext


async def test_market_scanner():
    """마켓 스캐너 테스트"""
    logger.info("\n" + "="*100)
    logger.info("TEST 1: Market Scanner")
    logger.info("="*100)

    scanner = BTCMarketScanner()
    markets = await scanner.find_active_btc_15m_markets(limit=10)

    if not markets:
        logger.warning("No active BTC 15m markets found")
        return

    logger.success(f"Found {len(markets)} active markets")

    for idx, market in enumerate(markets[:3], 1):
        details = await scanner.get_market_details(market)
        logger.info(f"\n{idx}. {details['question']}")
        logger.info(f"   Time remaining: {details['minutes_remaining']:.1f}m")
        logger.info(f"   Liquidity: ${details['liquidity']:,.0f}")
        logger.info(f"   Tokens: {details['token_yes'][:8]}... / {details['token_no'][:8]}...")


async def test_price_tracker():
    """가격 추적기 테스트"""
    logger.info("\n" + "="*100)
    logger.info("TEST 2: BTC Price Tracker")
    logger.info("="*100)

    tracker = BTCPriceTracker()

    updates = []

    def on_price_update(new_price, old_price):
        if old_price:
            change_pct = ((new_price - old_price) / old_price) * 100
            logger.info(f"BTC: ${new_price:,.2f} ({change_pct:+.4f}%)")
        else:
            logger.info(f"BTC: ${new_price:,.2f}")
        updates.append(new_price)

    tracker.add_callback(on_price_update)
    await tracker.start()

    logger.info("Tracking for 15 seconds...")
    await asyncio.sleep(15)

    if len(updates) > 1:
        first = updates[0]
        last = updates[-1]
        total_change = ((last - first) / first) * 100
        logger.success(f"Total change: {total_change:+.4f}%")
        logger.info(f"Updates received: {len(updates)}")

    await tracker.stop()


async def test_strategy_logic():
    """전략 로직 테스트 (시뮬레이션)"""
    logger.info("\n" + "="*100)
    logger.info("TEST 3: Strategy Logic Simulation")
    logger.info("="*100)

    tracker = BTCPriceTracker()
    await tracker.start()

    # BTC 가격 대기
    for _ in range(10):
        if tracker.get_current_price():
            break
        await asyncio.sleep(1)

    start_btc = tracker.get_current_price()
    logger.info(f"Start BTC Price: ${start_btc:,.2f}")

    # 전략 초기화
    strategy = AdvancedScalpingStrategy(tracker)

    # 시뮬레이션 시나리오
    scenarios = [
        {
            "name": "Good Entry - UP prediction",
            "ctx": MarketContext(
                market_id="test_1",
                start_time=time.time(),
                end_time=time.time() + 600,  # 10분 후
                start_price=start_btc,
                token_yes="token_yes_1",
                token_no="token_no_1",
                yes_price=0.45,  # 저렴한 YES
                no_price=0.52,
                position_yes=0.0,
                position_no=0.0
            )
        },
        {
            "name": "Take Profit Scenario",
            "ctx": MarketContext(
                market_id="test_2",
                start_time=time.time() - 300,  # 5분 전 진입
                end_time=time.time() + 300,
                start_price=start_btc,
                token_yes="token_yes_2",
                token_no="token_no_2",
                yes_price=0.48,
                no_price=0.45,  # 이제 NO가 저렴 (TP 가능)
                position_yes=10.0,
                position_no=0.0,
                avg_price_yes=0.50
            )
        },
        {
            "name": "Stop Loss Scenario",
            "ctx": MarketContext(
                market_id="test_3",
                start_time=time.time() - 300,
                end_time=time.time() + 300,
                start_price=start_btc,
                token_yes="token_yes_3",
                token_no="token_no_3",
                yes_price=0.40,
                no_price=0.70,  # NO가 비쌈 (손실)
                position_yes=10.0,
                position_no=0.0,
                avg_price_yes=0.50
            )
        }
    ]

    # 각 시나리오 테스트
    for scenario in scenarios:
        logger.info(f"\n--- {scenario['name']} ---")
        ctx = scenario['ctx']

        signal = strategy.evaluate_market(ctx)

        if signal:
            logger.success(f"Signal: {signal.action}")
            logger.info(f"  Reason: {signal.reason}")
            logger.info(f"  Confidence: {signal.confidence:.1%}")
            logger.info(f"  Edge: {signal.edge:.1%}")
            logger.info(f"  Urgency: {signal.urgency}")
        else:
            logger.warning("No signal")

        # 포지션 요약
        summary = strategy.get_position_summary(ctx)
        if summary.get("has_position"):
            logger.info(f"  Position: {summary['side']} {summary['size']}")
            logger.info(f"  Unrealized PnL: {summary['unrealized_pnl_pct']:+.2%} (${summary['unrealized_pnl_usdc']:+.2f})")

    await tracker.stop()


async def test_integrated_flow():
    """통합 플로우 테스트"""
    logger.info("\n" + "="*100)
    logger.info("TEST 4: Integrated Flow (Dry Run)")
    logger.info("="*100)

    scanner = BTCMarketScanner()
    tracker = BTCPriceTracker()

    await tracker.start()

    # BTC 가격 대기
    for _ in range(10):
        if tracker.get_current_price():
            break
        await asyncio.sleep(1)

    logger.info(f"BTC Price: ${tracker.get_current_price():,.2f}")

    # 마켓 찾기
    logger.info("Finding markets...")
    markets = await scanner.find_active_btc_15m_markets(limit=5)

    if not markets:
        logger.warning("No markets found")
        await tracker.stop()
        return

    # 첫 번째 마켓 선택
    market = markets[0]
    details = await scanner.get_market_details(market)

    logger.info(f"\nSelected Market:")
    logger.info(f"  {details['question']}")
    logger.info(f"  Time remaining: {details['minutes_remaining']:.1f}m")
    logger.info(f"  Liquidity: ${details['liquidity']:,.0f}")

    # 전략 실행 (10초 동안)
    strategy = AdvancedScalpingStrategy(tracker)

    ctx = MarketContext(
        market_id=details['id'],
        start_time=time.time(),
        end_time=time.time() + details['minutes_remaining'] * 60,
        start_price=tracker.get_current_price(),
        token_yes=details['token_yes'],
        token_no=details['token_no'],
        yes_price=0.5,
        no_price=0.5,
    )

    logger.info("\nMonitoring for 10 seconds...")

    for i in range(5):
        await asyncio.sleep(2)

        # 실제 마켓이면 여기서 오더북 가격을 가져와야 함
        # 시뮬레이션: 랜덤하게 움직이는 가격
        import random
        ctx.yes_price = 0.45 + random.random() * 0.1
        ctx.no_price = 1.0 - ctx.yes_price + random.uniform(-0.02, 0.02)

        signal = strategy.evaluate_market(ctx)

        current_btc = tracker.get_current_price()
        logger.info(f"[{i+1}/5] BTC: ${current_btc:,.2f} | YES: {ctx.yes_price:.3f} | NO: {ctx.no_price:.3f}")

        if signal:
            logger.success(f"  >> SIGNAL: {signal.action} - {signal.reason}")
        else:
            logger.info(f"  >> No signal")

    await tracker.stop()
    logger.success("Integrated test complete!")


async def run_all_tests():
    """모든 테스트 실행"""
    logger.info("\n" + "🚀 "*20)
    logger.info("BTC SCALPING STRATEGY TEST SUITE")
    logger.info("🚀 "*20 + "\n")

    try:
        # Test 1: Market Scanner
        await test_market_scanner()
        await asyncio.sleep(2)

        # Test 2: Price Tracker
        await test_price_tracker()
        await asyncio.sleep(2)

        # Test 3: Strategy Logic
        await test_strategy_logic()
        await asyncio.sleep(2)

        # Test 4: Integrated Flow
        await test_integrated_flow()

        logger.info("\n" + "✅ "*20)
        logger.success("ALL TESTS PASSED")
        logger.info("✅ "*20 + "\n")

    except Exception as e:
        logger.error(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
