"""
BTC 15분 마켓 스캘핑 봇 V2 - Refactored
==========================================

V2 개선사항:
- 단순하고 명확한 상태 관리
- TP limit order는 봇에서 관리 (전략은 신호만)
- 5분 미만에는 LIMIT order 절대 금지
- 완료된 사이클 기반 거래 제한
"""
import asyncio
import time
from typing import Dict, Optional
from loguru import logger
from datetime import datetime, timezone

from btc_market_scanner import BTCMarketScanner
from btc_price_tracker import BTCPriceTracker
from multi_level_strategy_v2 import MultiLevelScalpingStrategyV2, MarketContext
from clients import PolymarketClient
from tracker import MarketDataStreamer
from config import config
from models import OrderSide


class BTCScalpingBotV2:
    """
    BTC 15분 마켓 전용 스캘핑 봇 V2

    주요 개선사항:
    - 포지션만 추적, 모든 통계는 포지션에서 계산
    - TP limit order 관리를 봇으로 이동
    - 5분 미만에는 MARKET order만 사용
    """

    def __init__(self):
        self.scanner = BTCMarketScanner()
        self.price_tracker = BTCPriceTracker()
        self.poly_client = PolymarketClient()
        self.orderbook_tracker = MarketDataStreamer()

        # V2 전략 사용
        self.strategy = MultiLevelScalpingStrategyV2(self.price_tracker)

        # 활성 마켓 관리
        self.active_markets: Dict[str, dict] = {}
        self.market_contexts: Dict[str, MarketContext] = {}
        self.market_start_prices: Dict[str, float] = {}

        # TP limit order 추적 (봇에서 관리)
        self.active_tp_orders: Dict[str, list] = {}  # market_id -> [order_ids]

        # 통계
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0

    async def run(self):
        """봇 메인 루프"""
        logger.info("="*100)
        logger.info("BTC Scalping Bot V2 Starting...")
        logger.info(f"Trading: {'ENABLED' if config.trading_enabled else 'DISABLED (SIMULATION)'}")
        logger.info("="*100)

        # WebSocket 시작
        await self.orderbook_tracker.start()

        # 메인 루프
        try:
            while True:
                # 1. 새로운 마켓 스캔
                await self.scan_for_new_markets()

                # 2. 만료된 마켓 정리
                await self.cleanup_expired_markets()

                # 3. 모든 활성 마켓 평가
                await self.evaluate_all_markets()

                # 2초 대기
                await asyncio.sleep(2)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            await self.orderbook_tracker.stop()

    async def scan_for_new_markets(self):
        """새로운 BTC 15분 마켓 스캔"""
        markets = await self.scanner.find_active_btc_15m_markets(limit=10)

        for market in markets:
            market_id = market.get("id")

            if market_id in self.active_markets:
                continue

            # 마켓 상세 정보
            market_details = await self.scanner.get_market_details(market)

            # 시작 가격 기록
            try:
                current_btc_price = self.price_tracker.get_current_price()
            except:
                current_btc_price = 0

            self.market_start_prices[market_id] = current_btc_price

            # 활성 마켓 추가
            self.active_markets[market_id] = market_details

            # Orderbook 구독
            token_ids = [market_details["token_yes"], market_details["token_no"]]
            await self.orderbook_tracker.subscribe(market_id, token_ids)

            logger.success(f"\n{'='*100}")
            logger.success(f"NEW MARKET FOUND!")
            logger.success(f"  Question: {market_details['question']}")
            logger.success(f"  Expires: {market_details['minutes_remaining']:.1f} min")
            logger.success(f"  Liquidity: ${market_details['liquidity']:,.0f}")
            logger.success(f"  Start BTC: ${current_btc_price:,.2f}")
            logger.success(f"{'='*100}\n")

            # MarketContext 생성
            end_date_str = market_details["end_date"]
            end_ts = datetime.fromisoformat(end_date_str.replace("Z", "+00:00")).timestamp()

            self.market_contexts[market_id] = MarketContext(
                market_id=market_id,
                end_time=end_ts,
                yes_price=0.5,  # 초기값, 곧 업데이트됨
                no_price=0.5,
                token_yes=market_details["token_yes"],
                token_no=market_details["token_no"],
            )

    async def cleanup_expired_markets(self):
        """만료된 마켓 정리"""
        now = time.time()
        expired = []

        for market_id, ctx in self.market_contexts.items():
            # 만료 10분 후까지 유지 (결과 확인용)
            if now > ctx.end_time + 600:
                expired.append(market_id)

        for market_id in expired:
            logger.info(f"Removing expired market: {market_id[:8]}")
            del self.active_markets[market_id]
            del self.market_contexts[market_id]
            if market_id in self.market_start_prices:
                del self.market_start_prices[market_id]
            if market_id in self.active_tp_orders:
                del self.active_tp_orders[market_id]

    async def evaluate_all_markets(self):
        """모든 활성 마켓 평가"""
        for market_id, ctx in list(self.market_contexts.items()):
            try:
                await self.evaluate_market(market_id, ctx)
            except Exception as e:
                logger.error(f"Error evaluating market {market_id}: {e}")

    async def evaluate_market(self, market_id: str, ctx: MarketContext):
        """특정 마켓 평가 및 거래"""
        time_remaining = ctx.end_time - time.time()

        # 오더북에서 최신 가격 가져오기
        bid_yes, ask_yes = self.orderbook_tracker.get_price(ctx.token_yes)
        bid_no, ask_no = self.orderbook_tracker.get_price(ctx.token_no)

        # 가격이 없으면 스킵
        if not ask_yes or not ask_no:
            return

        # Context 업데이트 (ASK 가격 사용)
        ctx.yes_price = ask_yes
        ctx.no_price = ask_no

        # === TP limit order 관리 (봇 레벨) ===
        # 5분 미만이면 모든 TP limit order 취소
        if time_remaining < 300:
            if market_id in self.active_tp_orders and self.active_tp_orders[market_id]:
                logger.warning(f"⚠️  <5min: Cancelling {len(self.active_tp_orders[market_id])} TP limit orders")
                await self.cancel_tp_orders(market_id)

        # 전략 실행
        signal = self.strategy.evaluate_market(ctx)

        if signal:
            logger.info(f"\n{'='*100}")
            logger.info(f"SIGNAL: {signal.reason}")
            logger.info(f"  Market: {self.active_markets[market_id]['question']}")
            logger.info(f"  Action: {signal.action}")
            logger.info(f"  Size: {signal.size}")
            logger.info(f"  Price: {signal.price:.3f}")
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
            success = await self.place_order(
                token_id=signal.token_id,
                price=signal.price,
                size=signal.size,
                side=OrderSide.BUY
            )

            if success:
                logger.success(f"✅ Entered YES position: {signal.size} @ {signal.price:.3f}")

                # 전략 콜백
                if signal.metadata:
                    self.strategy.on_order_filled(
                        market_id=market_id,
                        side=signal.metadata.get("side", "YES"),
                        price=signal.price,
                        size=signal.size,
                        level=signal.metadata.get("level", 0),
                        metadata=signal.metadata
                    )

        elif signal.action == "ENTER_NO":
            success = await self.place_order(
                token_id=signal.token_id,
                price=signal.price,
                size=signal.size,
                side=OrderSide.BUY
            )

            if success:
                logger.success(f"✅ Entered NO position: {signal.size} @ {signal.price:.3f}")

                # 전략 콜백
                if signal.metadata:
                    self.strategy.on_order_filled(
                        market_id=market_id,
                        side=signal.metadata.get("side", "NO"),
                        price=signal.price,
                        size=signal.size,
                        level=signal.metadata.get("level", 0),
                        metadata=signal.metadata
                    )

        elif signal.action == "PLACE_TP_LIMIT":
            # TP limit order 발행 (봇에서 관리)
            # 먼저 기존 TP limit order 취소
            if market_id in self.active_tp_orders and self.active_tp_orders[market_id]:
                logger.info(f"🔄 Cancelling {len(self.active_tp_orders[market_id])} existing TP orders to update price")
                await self.cancel_tp_orders(market_id)

            # 새로운 TP limit order 발행
            success = await self.place_order(
                token_id=signal.token_id,
                price=signal.price,
                size=signal.size,
                side=OrderSide.BUY,
                post_only=True  # LIMIT order
            )

            if success:
                # active_tp_orders에 추가 (실제로는 order_id 받아서 저장해야 함)
                if market_id not in self.active_tp_orders:
                    self.active_tp_orders[market_id] = []
                # TODO: 실제 order_id 받아서 저장
                # self.active_tp_orders[market_id].append(order_id)

                logger.success(f"✅ TP Limit order placed: {signal.size} @ {signal.price:.3f}")

                # **주의**: 실제로는 limit order 체결 확인 필요
                # 지금은 간단하게 주문 성공 = 체결로 가정
                # TODO: WebSocket으로 체결 확인 후 콜백 호출

                # 임시로 즉시 처리
                if signal.metadata:
                    exit_side = signal.metadata.get("side", "YES")
                    is_high_scalp = signal.metadata.get("is_high_price_scalp", False)

                    # PnL 계산 (간단하게)
                    pnl = signal.size * 0.05  # 임시

                    self.total_trades += 1
                    self.total_pnl += pnl
                    if pnl > 0:
                        self.winning_trades += 1

                    logger.success(f"  TP Limit filled (assumed): PnL ~${pnl:+.2f}")

                    # 전략 콜백
                    self.strategy.on_exit_filled(
                        market_id=market_id,
                        side=exit_side,
                        is_high_scalp=is_high_scalp
                    )

        elif signal.action == "EXIT":
            # MARKET order로 즉시 청산
            # 먼저 활성 TP limit order 취소
            if market_id in self.active_tp_orders and self.active_tp_orders[market_id]:
                logger.warning(f"🚫 Cancelling {len(self.active_tp_orders[market_id])} TP orders before EXIT")
                await self.cancel_tp_orders(market_id)

            success = await self.place_order(
                token_id=signal.token_id,
                price=signal.price,
                size=signal.size,
                side=OrderSide.BUY
            )

            if success:
                if signal.metadata:
                    exit_side = signal.metadata.get("side", "YES")
                    is_high_scalp = signal.metadata.get("is_high_price_scalp", False)

                    # PnL 계산 (간단하게)
                    pnl = signal.size * 0.02  # 임시

                    self.total_trades += 1
                    self.total_pnl += pnl
                    if pnl > 0:
                        self.winning_trades += 1

                    logger.success(f"  Exited position: PnL ~${pnl:+.2f}")
                    logger.info(f"  Total: {self.winning_trades}/{self.total_trades} wins, ${self.total_pnl:+.2f} PnL")

                    # 전략 콜백
                    self.strategy.on_exit_filled(
                        market_id=market_id,
                        side=exit_side,
                        is_high_scalp=is_high_scalp
                    )

    async def cancel_tp_orders(self, market_id: str):
        """TP limit order 취소"""
        if market_id not in self.active_tp_orders:
            return

        order_ids = self.active_tp_orders[market_id]
        for order_id in order_ids:
            try:
                await self.poly_client.cancel_order(order_id)
                logger.info(f"  ✓ Cancelled TP order: {order_id}")
            except Exception as e:
                logger.warning(f"  ⚠️  Failed to cancel TP order {order_id}: {e}")

        # 리스트 클리어
        self.active_tp_orders[market_id] = []

    async def place_order(self, token_id: str, price: float, size: float,
                         side: OrderSide, post_only: bool = False) -> bool:
        """주문 실행"""
        try:
            resp = await self.poly_client.place_order(
                token_id=token_id,
                price=price,
                size=size,
                side=side,
                post_only=post_only
            )

            if resp:
                order_id = resp.get("orderID", "unknown")
                logger.info(f"  Order placed: {order_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return False

    def print_stats(self):
        """통계 출력"""
        logger.info("\n" + "="*100)
        logger.info("SESSION STATISTICS")
        logger.info("="*100)
        logger.info(f"Total Trades: {self.total_trades}")
        logger.info(f"Winning Trades: {self.winning_trades}")
        logger.info(f"Win Rate: {self.winning_trades/self.total_trades*100:.1f}%" if self.total_trades > 0 else "Win Rate: N/A")
        logger.info(f"Total PnL: ${self.total_pnl:+.2f}")
        logger.info("="*100)


async def main():
    bot = BTCScalpingBotV2()
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        bot.print_stats()


if __name__ == "__main__":
    asyncio.run(main())
