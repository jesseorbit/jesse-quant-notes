"""
BTC 15분 마켓 스캘핑 봇
모든 모듈을 통합한 메인 봇
"""
import asyncio
import time
from typing import Dict, Optional
from loguru import logger
from datetime import datetime, timezone

from btc_market_scanner import BTCMarketScanner
from btc_price_tracker import BTCPriceTracker
from scalping_strategy import BTCScalpingStrategy, AdvancedScalpingStrategy, MarketContext
from multi_level_scalping_strategy import MultiLevelScalpingStrategy
from clients import PolymarketClient
from tracker import MarketDataStreamer
from config import config
from models import OrderSide


class BTCScalpingBot:
    """
    BTC 15분 마켓 전용 스캘핑 봇

    워크플로우:
    1. 마켓 스캐너로 BTC 15분 마켓 발견
    2. 가격 추적기로 실시간 BTC 가격 모니터링
    3. 전략으로 진입/청산 신호 생성
    4. 자동 주문 실행
    """

    def __init__(self, use_multi_level_strategy: bool = True):
        # 클라이언트
        self.poly_client = PolymarketClient()
        self.market_scanner = BTCMarketScanner()
        self.price_tracker = BTCPriceTracker()
        self.orderbook_tracker = MarketDataStreamer()

        # 전략
        if use_multi_level_strategy:
            self.strategy = MultiLevelScalpingStrategy(self.price_tracker)
            logger.info("Using Multi-Level Scalping Strategy V1 (with fixes)")
        else:
            self.strategy = AdvancedScalpingStrategy(self.price_tracker)
            logger.info("Using Advanced Scalping Strategy")

        # 상태 관리
        self.active_markets: Dict[str, dict] = {}  # market_id -> market_info
        self.market_contexts: Dict[str, MarketContext] = {}  # market_id -> context
        self.market_start_prices: Dict[str, float] = {}  # market_id -> BTC start price

        # 통계
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0

        # 런타임
        self.is_running = False
        self.last_market_scan = 0

    async def start(self):
        """봇 시작"""
        logger.info("="*100)
        logger.info("Starting BTC Scalping Bot")
        logger.info("="*100)

        self.is_running = True

        # 가격 추적기 시작
        await self.price_tracker.start()
        logger.info("BTC price tracker started")

        # 오더북 추적기 시작
        await self.orderbook_tracker.start()
        logger.info("Orderbook tracker started")

        # 초기 BTC 가격 대기
        for _ in range(10):
            if self.price_tracker.get_current_price():
                break
            await asyncio.sleep(1)

        logger.info(f"Initial BTC Price: ${self.price_tracker.get_current_price():,.2f}")

        if not config.trading_enabled:
            logger.warning("⚠️  TRADING DISABLED - Running in DRY RUN mode")

        logger.info("Bot ready!")

    async def stop(self):
        """봇 중지"""
        logger.info("Stopping bot...")
        self.is_running = False
        await self.price_tracker.stop()
        await self.orderbook_tracker.stop()
        logger.info("Bot stopped")

    async def run(self):
        """메인 루프"""
        await self.start()

        try:
            while self.is_running:
                # 1. 마켓 스캔 (30초마다)
                if time.time() - self.last_market_scan > 30:
                    await self.scan_and_add_markets()
                    self.last_market_scan = time.time()

                # 2. 만료된 마켓 정리
                await self.cleanup_expired_markets()

                # 3. 활성 마켓 평가 및 거래
                await self.evaluate_all_markets()

                # 4. 짧은 대기
                await asyncio.sleep(2)

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            await self.stop()

    async def scan_and_add_markets(self):
        """새로운 마켓 스캔 및 추가"""
        logger.info("Scanning for new BTC 15m markets...")

        markets = await self.market_scanner.find_active_btc_15m_markets(limit=20)

        for market in markets:
            market_id = market.get("id")

            # 이미 추적 중이면 스킵
            if market_id in self.active_markets:
                continue

            # 마켓 상세 정보
            details = await self.market_scanner.get_market_details(market)

            # 충분한 시간이 남아있는지 확인 (최소 5분)
            if details["minutes_remaining"] < 5:
                continue

            # 마켓 추가
            await self.add_market(details)

        logger.info(f"Currently tracking {len(self.active_markets)} markets")

    async def add_market(self, market_details: dict):
        """마켓 추가"""
        market_id = market_details["id"]

        logger.info(f"Adding market: {market_details['question']}")
        logger.info(f"  Time remaining: {market_details['minutes_remaining']:.1f}m")
        logger.info(f"  Liquidity: ${market_details['liquidity']:,.0f}")

        # BTC 시작 가격 기록
        current_btc_price = self.price_tracker.get_current_price()
        if not current_btc_price:
            logger.warning("  No BTC price available, skipping")
            return

        self.market_start_prices[market_id] = current_btc_price
        self.active_markets[market_id] = market_details

        # 오더북 구독
        tokens = [market_details["token_yes"], market_details["token_no"]]
        await self.orderbook_tracker.subscribe(market_id, tokens)

        # MarketContext 초기화
        end_ts = datetime.fromisoformat(
            market_details["end_date"].replace("Z", "+00:00")
        ).timestamp()

        self.market_contexts[market_id] = MarketContext(
            market_id=market_id,
            start_time=time.time(),
            end_time=end_ts,
            start_price=current_btc_price,
            token_yes=market_details["token_yes"],
            token_no=market_details["token_no"],
            yes_price=0.5,  # 초기값, 곧 업데이트됨
            no_price=0.5,
        )

        logger.success(f"  Market added! Start BTC: ${current_btc_price:,.2f}")

    async def cleanup_expired_markets(self):
        """만료된 마켓 정리"""
        now = time.time()
        expired = []

        for market_id, ctx in self.market_contexts.items():
            # 만료 10분 후까지 유지 (결과 확인용)
            if now > ctx.end_time + 600:
                expired.append(market_id)

        for market_id in expired:
            logger.info(f"Removing expired market: {market_id}")
            del self.active_markets[market_id]
            del self.market_contexts[market_id]
            if market_id in self.market_start_prices:
                del self.market_start_prices[market_id]

    async def evaluate_all_markets(self):
        """모든 활성 마켓 평가"""
        for market_id, ctx in list(self.market_contexts.items()):
            try:
                await self.evaluate_market(market_id, ctx)
            except Exception as e:
                logger.error(f"Error evaluating market {market_id}: {e}")

    async def evaluate_market(self, market_id: str, ctx: MarketContext):
        """특정 마켓 평가 및 거래"""
        # 시간 체크 (5분 미만일 때 로그)
        time_remaining = ctx.end_time - time.time()
        if time_remaining < 300:
            # 포지션 카운트 확인
            position_count = len(self.strategy.positions.get(market_id, []))
            logger.warning(f"📊📊📊 EVALUATING <5MIN MARKET: {market_id[:8]} with {time_remaining:.0f}s remaining | Positions: {position_count}")

        # 오더북에서 최신 가격 가져오기
        bid_yes, ask_yes = self.orderbook_tracker.get_price(ctx.token_yes)
        bid_no, ask_no = self.orderbook_tracker.get_price(ctx.token_no)

        # 가격이 없으면 스킵
        if not ask_yes or not ask_no:
            if time_remaining < 300:
                logger.error(f"❌❌❌ NO PRICE DATA for {market_id[:8]} (ask_yes={ask_yes}, ask_no={ask_no}) - SKIPPING EVALUATION")
            return

        if time_remaining < 300:
            logger.info(f"✅ Price data OK for {market_id[:8]}: YES bid={bid_yes:.3f}/ask={ask_yes:.3f}, NO bid={bid_no:.3f}/ask={ask_no:.3f}")

        # Context 업데이트 (ASK 가격 사용 = 매수 시 실제 지불 가격)
        ctx.yes_price = ask_yes
        ctx.no_price = ask_no

        # 가격 로깅 (ask 가격 = 우리가 매수할 때 지불하는 가격)
        logger.debug(f"[{market_id[:8]}] Using ASK prices for strategy: YES={ask_yes:.3f}, NO={ask_no:.3f}")

        # 전략 실행
        signal = self.strategy.evaluate_market(ctx)

        if signal:
            logger.info(f"\n{'='*100}")
            logger.info(f"SIGNAL: {signal.reason}")
            logger.info(f"  Market: {self.active_markets[market_id]['question']}")
            logger.info(f"  Action: {signal.action}")
            logger.info(f"  Size: {signal.size}")
            logger.info(f"  Price: {signal.price:.3f}")
            logger.info(f"  Confidence: {signal.confidence:.1%}")
            logger.info(f"  Edge: {signal.edge:.1%}")
            logger.info(f"  Urgency: {signal.urgency}")

            # 주문 실행
            await self.execute_signal(market_id, ctx, signal)

        # 포지션 정보 로깅 (포지션이 있을 때만)
        summary = self.strategy.get_position_summary(ctx)
        if summary.get("has_position"):
            remaining = ctx.end_time - time.time()
            logger.info(
                f"[{market_id[:8]}] {summary['side']} {summary['size']:.1f} @ {summary['avg_entry_price']:.3f} | "
                f"PnL: {summary['unrealized_pnl_pct']:+.2%} (${summary['unrealized_pnl_usdc']:+.2f}) | "
                f"Exit: {summary['current_exit_price']:.3f} | {remaining:.0f}s left"
            )

    async def execute_signal(self, market_id: str, ctx: MarketContext, signal):
        """신호 실행"""
        if signal.action == "ENTER_YES":
            # **중요: LEVEL 진입(10 shares)은 5분 미만일 때 절대 금지**
            # HIGH SCALP은 5 shares, LEVEL은 10 shares
            time_remaining = ctx.end_time - time.time()
            is_high_scalp = signal.metadata.get("is_high_price_scalp", False) if signal.metadata else False

            if signal.size >= 10 and not is_high_scalp and time_remaining < 300:
                logger.error(f"❌ BLOCKED LEVEL entry: {signal.size} YES @ {signal.price:.3f} - Only {time_remaining:.0f}s remaining (need 300s+)")
                logger.error(f"   This is a bug! LEVEL entries should not be signaled when <5min remaining")
                return  # 주문 거부

            success = await self.place_order(
                token_id=signal.token_id,
                price=signal.price,
                size=signal.size,
                side=OrderSide.BUY
            )

            if success:
                # 포지션 업데이트
                total_cost = ctx.position_yes * ctx.avg_price_yes + signal.size * signal.price
                ctx.position_yes += signal.size
                ctx.avg_price_yes = total_cost / ctx.position_yes
                logger.success(f"  Entered YES position: {ctx.position_yes} @ {ctx.avg_price_yes:.3f}")

                # 전략 콜백 (MultiLevelStrategy만 해당)
                if hasattr(self.strategy, 'on_order_filled') and signal.metadata:
                    self.strategy.on_order_filled(
                        market_id=market_id,
                        side=signal.metadata.get("side", "YES"),
                        price=signal.price,
                        size=signal.size,
                        level=signal.metadata.get("level", 0),
                        metadata=signal.metadata
                    )
            else:
                # 주문 실패 콜백
                if hasattr(self.strategy, 'on_order_failed') and signal.metadata:
                    self.strategy.on_order_failed(
                        market_id=market_id,
                        side=signal.metadata.get("side", "YES"),
                        level=signal.metadata.get("level", 0)
                    )

        elif signal.action == "ENTER_NO":
            # **중요: LEVEL 진입(10 shares)은 5분 미만일 때 절대 금지**
            # HIGH SCALP은 5 shares, LEVEL은 10 shares
            time_remaining = ctx.end_time - time.time()
            is_high_scalp = signal.metadata.get("is_high_price_scalp", False) if signal.metadata else False

            if signal.size >= 10 and not is_high_scalp and time_remaining < 300:
                logger.error(f"❌ BLOCKED LEVEL entry: {signal.size} NO @ {signal.price:.3f} - Only {time_remaining:.0f}s remaining (need 300s+)")
                logger.error(f"   This is a bug! LEVEL entries should not be signaled when <5min remaining")
                return  # 주문 거부

            success = await self.place_order(
                token_id=signal.token_id,
                price=signal.price,
                size=signal.size,
                side=OrderSide.BUY
            )

            if success:
                # 포지션 업데이트
                total_cost = ctx.position_no * ctx.avg_price_no + signal.size * signal.price
                ctx.position_no += signal.size
                ctx.avg_price_no = total_cost / ctx.position_no
                logger.success(f"  Entered NO position: {ctx.position_no} @ {ctx.avg_price_no:.3f}")

                # 전략 콜백
                if hasattr(self.strategy, 'on_order_filled') and signal.metadata:
                    self.strategy.on_order_filled(
                        market_id=market_id,
                        side=signal.metadata.get("side", "NO"),
                        price=signal.price,
                        size=signal.size,
                        level=signal.metadata.get("level", 0),
                        metadata=signal.metadata
                    )
            else:
                # 주문 실패 콜백
                if hasattr(self.strategy, 'on_order_failed') and signal.metadata:
                    self.strategy.on_order_failed(
                        market_id=market_id,
                        side=signal.metadata.get("side", "NO"),
                        level=signal.metadata.get("level", 0)
                    )

        elif signal.action == "PLACE_TP_LIMIT":
            # TP limit order 발행 (MultiLevelStrategy의 청산 로직)
            success = await self.place_order(
                token_id=signal.token_id,
                price=signal.price,
                size=signal.size,
                side=OrderSide.BUY
            )

            if success:
                metadata = signal.metadata or {}
                exit_side = metadata.get("side", "YES")

                logger.success(f"  TP Limit order placed: {exit_side} @ {signal.price:.3f} x{signal.size}")

                # **주의: 실제 Polymarket에서는 limit order가 체결되면 별도 이벤트를 받아야 함**
                # 지금은 간단하게 주문 성공 = 체결로 가정 (실제로는 체결 확인 필요)
                # TODO: 실제 체결 확인 로직 추가 필요

                # 임시로 즉시 처리 (실제로는 체결 확인 후 처리해야 함)
                if exit_side == "YES" or ctx.position_yes > 0:
                    pnl = signal.size * (1.0 - ctx.avg_price_yes - signal.price)
                    ctx.position_yes = 0
                    ctx.avg_price_yes = 0
                else:
                    pnl = signal.size * (1.0 - ctx.avg_price_no - signal.price)
                    ctx.position_no = 0
                    ctx.avg_price_no = 0

                self.total_trades += 1
                self.total_pnl += pnl

                if pnl > 0:
                    self.winning_trades += 1

                logger.success(f"  TP Limit filled: PnL ${pnl:+.2f}")
                logger.info(f"  Total: {self.winning_trades}/{self.total_trades} wins, ${self.total_pnl:+.2f} PnL")

                # 전략 콜백
                if hasattr(self.strategy, 'on_exit_filled'):
                    is_high_scalp = signal.metadata.get("is_high_price_scalp", False) if signal.metadata else False
                    self.strategy.on_exit_filled(market_id=market_id, side=exit_side, is_high_price_scalp=is_high_scalp)

        elif signal.action == "EXIT":
            success = await self.place_order(
                token_id=signal.token_id,
                price=signal.price,
                size=signal.size,
                side=OrderSide.BUY
            )

            if success:
                # PnL 계산 및 통계 업데이트
                if ctx.position_yes > 0:
                    pnl = signal.size * (1.0 - ctx.avg_price_yes - signal.price)
                    exit_side = "YES"
                    ctx.position_yes = 0
                    ctx.avg_price_yes = 0
                else:
                    pnl = signal.size * (1.0 - ctx.avg_price_no - signal.price)
                    exit_side = "NO"
                    ctx.position_no = 0
                    ctx.avg_price_no = 0

                self.total_trades += 1
                self.total_pnl += pnl

                if pnl > 0:
                    self.winning_trades += 1

                logger.success(f"  Exited position: PnL ${pnl:+.2f}")
                logger.info(f"  Total: {self.winning_trades}/{self.total_trades} wins, ${self.total_pnl:+.2f} PnL")

                # 전략 콜백
                if hasattr(self.strategy, 'on_exit_filled'):
                    # High price scalping 여부 전달
                    is_high_scalp = signal.metadata.get("is_high_price_scalp", False) if signal.metadata else False
                    self.strategy.on_exit_filled(market_id=market_id, side=exit_side, is_high_price_scalp=is_high_scalp)

    async def place_order(self, token_id: str, price: float, size: float, side: OrderSide) -> bool:
        """주문 실행"""
        try:
            resp = await self.poly_client.place_order(
                token_id=token_id,
                price=price,
                size=size,
                side=side,
                post_only=False
            )

            if resp:
                logger.info(f"  Order placed: {resp}")
                return True
            else:
                logger.error(f"  Order failed")
                return False

        except Exception as e:
            logger.error(f"  Order error: {e}")
            return False

    def print_stats(self):
        """통계 출력"""
        logger.info("\n" + "="*100)
        logger.info("TRADING STATISTICS")
        logger.info("="*100)
        logger.info(f"Total Trades: {self.total_trades}")
        logger.info(f"Winning Trades: {self.winning_trades}")
        if self.total_trades > 0:
            win_rate = self.winning_trades / self.total_trades
            logger.info(f"Win Rate: {win_rate:.1%}")
        logger.info(f"Total PnL: ${self.total_pnl:+.2f}")
        logger.info("="*100)


async def main():
    """메인 실행"""
    bot = BTCScalpingBot(use_multi_level_strategy=True)

    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        bot.print_stats()


if __name__ == "__main__":
    asyncio.run(main())
