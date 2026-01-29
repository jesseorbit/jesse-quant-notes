"""
BTC 스캘핑 봇 웹 서버
실시간 대시보드와 거래 모니터링
"""
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import List, Dict, Optional
import json
import time
from loguru import logger

from btc_scalping_bot import BTCScalpingBot
from config import config
from simple_dca_strategy import SimpleDCAStrategy
from multi_level_scalping_strategy import MultiLevelScalpingStrategy
from models import OrderSide


# WebSocket 연결 관리
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New WebSocket connection. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """모든 연결된 클라이언트에게 메시지 전송"""
        if not self.active_connections:
            return

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                disconnected.append(connection)

        # 끊긴 연결 제거
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


manager = ConnectionManager()
bot_instance: BTCScalpingBot = None
bot_task = None

# 거래 히스토리 저장
trade_history: List[Dict] = []
event_log: List[Dict] = []


# 봇 이벤트 콜백
async def on_trade_executed(trade_info: dict):
    """거래 체결 시 호출"""
    global trade_history, event_log

    # 히스토리에 추가
    trade_history.append(trade_info)
    if len(trade_history) > 100:
        trade_history = trade_history[-100:]  # 최근 100개만 유지

    # 이벤트 로그
    event = {
        "type": "trade",
        "timestamp": time.time(),
        "data": trade_info
    }
    event_log.append(event)
    if len(event_log) > 200:
        event_log = event_log[-200:]

    # 실시간 브로드캐스트
    await manager.broadcast({
        "type": "trade_executed",
        "data": trade_info
    })

    logger.info(f"Trade executed: {trade_info}")


async def on_signal_generated(signal_info: dict):
    """신호 생성 시 호출"""
    global event_log

    event = {
        "type": "signal",
        "timestamp": time.time(),
        "data": signal_info
    }
    event_log.append(event)

    await manager.broadcast({
        "type": "signal_generated",
        "data": signal_info
    })


async def on_market_update(market_info: dict):
    """마켓 업데이트 시 호출"""
    # 마켓 정보를 더 완전하게 포함
    if bot_instance and market_info.get("market_id"):
        market_id = market_info["market_id"]
        market = bot_instance.active_markets.get(market_id, {})

        full_info = {
            "id": market_id,
            "question": market_info.get("question", market.get("question", "Unknown")),
            "yes_price": market_info.get("yes_price", 0),
            "no_price": market_info.get("no_price", 0),
            "time_remaining": market_info.get("time_remaining", 0),
            "position": market_info.get("position", {}),
            "liquidity": market.get("liquidity", 0),
            "volume": market.get("volume", 0),
            "btc_price": market_info.get("btc_price"),
            "timestamp": market_info.get("timestamp", time.time())
        }

        await manager.broadcast({
            "type": "market_update",
            "data": full_info
        })
    else:
        await manager.broadcast({
            "type": "market_update",
            "data": market_info
        })


async def on_bot_status_change(status: dict):
    """봇 상태 변경 시 호출"""
    await manager.broadcast({
        "type": "bot_status",
        "data": status
    })


# Bot 수정 버전 (이벤트 콜백 추가)
class WebBTCScalpingBot(BTCScalpingBot):
    """웹 UI용 봇 (이벤트 콜백 추가)"""

    def __init__(self, use_dca_strategy: bool = False, use_multilevel_strategy: bool = False):
        """봇 초기화 - 전략 선택 가능"""
        # ⚠️ 먼저 전략 타입을 저장
        _use_multilevel = use_multilevel_strategy
        _use_dca = use_dca_strategy

        # 부모 클래스 초기화 (use_multi_level_strategy 파라미터 사용)
        super().__init__(use_multi_level_strategy=use_multilevel_strategy)

        # ⚠️ 멀티레벨 전략이 요청되었으면 덮어쓰기
        if _use_multilevel:
            self.strategy = MultiLevelScalpingStrategy(self.price_tracker)
            # Limit order 콜백 주입
            self.strategy.place_limit_order_callback = self._place_limit_order_sync
            logger.critical("🎯 Using Multi-Level Scalping Strategy (0.34/0.24/0.14 + 5% TP + HIGH PRICE SCALPING)")
        # DCA 전략
        elif _use_dca:
            self.strategy = SimpleDCAStrategy(self.price_tracker)
            logger.info("Using Simple DCA Strategy (34c entry + DCA)")

    async def execute_signal(self, market_id: str, ctx, signal):
        """신호 실행 (오버라이드)"""
        # 신호 생성 이벤트
        await on_signal_generated({
            "market_id": market_id,
            "market_question": self.active_markets.get(market_id, {}).get("question", "Unknown"),
            "action": signal.action,
            "price": signal.price,
            "size": signal.size,
            "confidence": signal.confidence,
            "edge": signal.edge,
            "reason": signal.reason,
            "urgency": signal.urgency,
            "timestamp": time.time()
        })

        # DRY RUN 모드에서는 거래 실행 및 로깅 스킵
        if not config.trading_enabled:
            logger.error(f"❌ [DRY RUN MODE] {signal.action} signal BLOCKED - TRADING_ENABLED=False ❌")
            logger.error(f"   Would execute: {signal.action} {signal.token_id[:8]} @ {signal.price} x{signal.size}")
            return

        # 원래 로직 실행
        if signal.action == "ENTER_YES":
            success = await self.place_order(
                token_id=signal.token_id,
                price=signal.price,
                size=signal.size,
                side=OrderSide.BUY
            )

            # 거래 체결 이벤트 (성공/실패 모두 기록)
            if success:
                # 포지션 업데이트 (성공했을 때만)
                total_cost = ctx.position_yes * ctx.avg_price_yes + signal.size * signal.price
                ctx.position_yes += signal.size
                ctx.avg_price_yes = total_cost / ctx.position_yes

                # 전략 콜백 (MultiLevelStrategy 전용)
                if hasattr(self.strategy, 'on_order_filled') and signal.metadata:
                    self.strategy.on_order_filled(
                        market_id=market_id,
                        side=signal.metadata.get("side", "YES"),
                        price=signal.price,
                        size=signal.size,
                        level=signal.metadata.get("level", 0),
                        metadata=signal.metadata
                    )

                await on_trade_executed({
                    "market_id": market_id,
                    "market_question": self.active_markets.get(market_id, {}).get("question", "Unknown"),
                    "action": "ENTER_YES",
                    "side": "YES",
                    "price": signal.price,
                    "size": signal.size,
                    "position_after": ctx.position_yes,
                    "avg_price": ctx.avg_price_yes,
                    "status": "success",
                    "timestamp": time.time()
                })
            else:
                # 주문 실패 콜백
                if hasattr(self.strategy, 'on_order_failed') and signal.metadata:
                    self.strategy.on_order_failed(
                        market_id=market_id,
                        side=signal.metadata.get("side", "YES"),
                        level=signal.metadata.get("level", 0)
                    )

                # 실패한 거래도 기록 (포지션은 업데이트 안 함)
                await on_trade_executed({
                    "market_id": market_id,
                    "market_question": self.active_markets.get(market_id, {}).get("question", "Unknown"),
                    "action": "ENTER_YES",
                    "side": "YES",
                    "price": signal.price,
                    "size": signal.size,
                    "position_after": ctx.position_yes,  # 변경 없음
                    "avg_price": ctx.avg_price_yes,  # 변경 없음
                    "status": "failed",
                    "timestamp": time.time()
                })

        elif signal.action == "ENTER_NO":
            success = await self.place_order(
                token_id=signal.token_id,
                price=signal.price,
                size=signal.size,
                side=OrderSide.BUY
            )

            # 거래 체결 이벤트 (성공/실패 모두 기록)
            if success:
                # 포지션 업데이트 (성공했을 때만)
                total_cost = ctx.position_no * ctx.avg_price_no + signal.size * signal.price
                ctx.position_no += signal.size
                ctx.avg_price_no = total_cost / ctx.position_no

                # 전략 콜백 (MultiLevelStrategy 전용)
                if hasattr(self.strategy, 'on_order_filled') and signal.metadata:
                    self.strategy.on_order_filled(
                        market_id=market_id,
                        side=signal.metadata.get("side", "NO"),
                        price=signal.price,
                        size=signal.size,
                        level=signal.metadata.get("level", 0),
                        metadata=signal.metadata
                    )

                await on_trade_executed({
                    "market_id": market_id,
                    "market_question": self.active_markets.get(market_id, {}).get("question", "Unknown"),
                    "action": "ENTER_NO",
                    "side": "NO",
                    "price": signal.price,
                    "size": signal.size,
                    "position_after": ctx.position_no,
                    "avg_price": ctx.avg_price_no,
                    "status": "success",
                    "timestamp": time.time()
                })
            else:
                # 주문 실패 콜백
                if hasattr(self.strategy, 'on_order_failed') and signal.metadata:
                    self.strategy.on_order_failed(
                        market_id=market_id,
                        side=signal.metadata.get("side", "NO"),
                        level=signal.metadata.get("level", 0)
                    )

                # 실패한 거래도 기록 (포지션은 업데이트 안 함)
                await on_trade_executed({
                    "market_id": market_id,
                    "market_question": self.active_markets.get(market_id, {}).get("question", "Unknown"),
                    "action": "ENTER_NO",
                    "side": "NO",
                    "price": signal.price,
                    "size": signal.size,
                    "position_after": ctx.position_no,  # 변경 없음
                    "avg_price": ctx.avg_price_no,  # 변경 없음
                    "status": "failed",
                    "timestamp": time.time()
                })

        elif signal.action == "PLACE_TP_LIMIT":
            # TP 조건 만족 - limit order 발행 (기존 주문이 있으면 먼저 취소)
            order_type = signal.metadata.get("order_type", "BUY")
            order_side = OrderSide.SELL if order_type == "SELL" else OrderSide.BUY

            # **중요: 이미 TP limit order가 있으면 발행하지 않음**
            # CLOB이 알아서 최선의 가격으로 체결해주므로 가격 개선 불필요
            if market_id in self.strategy.active_exit_orders and len(self.strategy.active_exit_orders[market_id]) > 0:
                logger.debug(f"⏭️  TP limit order already exists, skipping")
                return

            # TP Limit은 BUY 주문이므로 잔액 체크
            if order_side == OrderSide.BUY:
                required_cash = signal.size * signal.price
                current_balance = await self.poly_client.get_usdc_balance()

                if current_balance < required_cash:
                    logger.error(f"❌ Insufficient balance for TP limit: ${current_balance:.2f} < ${required_cash:.2f}")
                    logger.warning(f"⚠️ Marking as failed to prevent retry")
                    # active_exit_orders에 추가하여 재시도 방지
                    if market_id not in self.strategy.active_exit_orders:
                        self.strategy.active_exit_orders[market_id] = []
                    self.strategy.active_exit_orders[market_id].append("insufficient-balance")
                    return  # 주문 발행 중단

            logger.info(f"📋 Placing TP limit order: {order_type} {signal.size} @ {signal.price:.3f}")

            try:
                resp = await self.poly_client.place_order(
                    token_id=signal.token_id,
                    price=signal.price,
                    size=signal.size,
                    side=order_side,
                    post_only=True  # Limit order
                )

                if resp:
                    order_id = resp.get('orderID', f"tp-{signal.token_id[:8]}")
                    # active_exit_orders에 추가
                    if market_id not in self.strategy.active_exit_orders:
                        self.strategy.active_exit_orders[market_id] = []
                    self.strategy.active_exit_orders[market_id].append(order_id)
                    logger.success(f"✅ TP Limit Order placed: {order_id}")
                else:
                    logger.error("❌ TP Limit Order failed")
                    # 실패해도 active_exit_orders에 추가하여 재시도 방지
                    # (다음 평가 cycle에서 동일 주문 반복 방지)
                    if market_id not in self.strategy.active_exit_orders:
                        self.strategy.active_exit_orders[market_id] = []
                    self.strategy.active_exit_orders[market_id].append("failed-order")
                    logger.warning("⚠️ Added failed order marker to prevent retry")
            except Exception as e:
                logger.error(f"TP Limit Order error: {e}")

        elif signal.action == "EXIT" or signal.action == "EXIT_SELL":
            # EXIT: 반대 토큰 BUY (unwinding) - 더 효율적이지만 잔액 필요
            # EXIT_SELL: 보유 토큰 SELL (폴백) - 잔액 불필요

            # ⚠️ 먼저 활성 TP limit order들을 취소
            market_id = ctx.market_id
            if market_id in self.strategy.active_exit_orders:
                order_ids = self.strategy.active_exit_orders[market_id]
                logger.warning(f"🚫 Cancelling {len(order_ids)} active TP limit orders before EXIT...")
                for order_id in order_ids:
                    try:
                        success = await self.poly_client.cancel_order(order_id)
                        if success:
                            logger.info(f"✓ Cancelled TP limit order: {order_id}")
                        else:
                            logger.warning(f"⚠️ Failed to cancel TP limit order: {order_id}")
                    except Exception as e:
                        logger.error(f"Error cancelling order {order_id}: {e}")
                # 취소 완료 후 리스트 클리어
                self.strategy.active_exit_orders[market_id] = []

            order_side = OrderSide.BUY

            # EXIT 액션이면 잔액 체크 → 부족하면 SELL 폴백
            if signal.action == "EXIT":
                required_cash = signal.size * signal.price
                current_balance = await self.poly_client.get_usdc_balance()

                if current_balance < required_cash:
                    # 잔액 부족 → SELL 폴백 사용
                    logger.warning(f"Insufficient balance ${current_balance:.2f} < ${required_cash:.2f}, using SELL fallback")
                    signal.action = "EXIT_SELL"
                    signal.token_id = signal.metadata.get("fallback_token", signal.token_id)
                    signal.price = signal.metadata.get("fallback_sell_price", signal.price)
                    order_side = OrderSide.SELL
                else:
                    logger.info(f"Unwinding with ${current_balance:.2f} balance (need ${required_cash:.2f})")
            else:
                # EXIT_SELL은 바로 SELL
                order_side = OrderSide.SELL

            logger.warning(f"🔔 EXIT SIGNAL: action={signal.action}, token={signal.token_id[:8]}, price={signal.price:.3f}, size={signal.size}, side={order_side}")
            logger.warning(f"📞 Calling place_order() for EXIT...")

            success = await self.place_order(
                token_id=signal.token_id,
                price=signal.price,
                size=signal.size,
                side=order_side
            )

            logger.warning(f"📞 place_order() returned: {success}")

            if not success:
                logger.error(f"❌ EXIT ORDER FAILED: {signal.reason}")

                # 주문 실패 시 SELL fallback 시도 (BUY 주문이 최소 금액 미달일 경우)
                if signal.action == "EXIT" and order_side == OrderSide.BUY:
                    fallback_token = signal.metadata.get("fallback_token")
                    fallback_price = signal.metadata.get("fallback_sell_price")

                    if fallback_token and fallback_price:
                        logger.warning(f"🔄 Trying SELL fallback: SELL {fallback_token[:8]}... @ {fallback_price:.3f} x{signal.size}")

                        success = await self.place_order(
                            token_id=fallback_token,
                            price=fallback_price,
                            size=signal.size,
                            side=OrderSide.SELL
                        )

                        if success:
                            logger.success(f"✅ SELL FALLBACK SUCCESS!")
                            signal.action = "EXIT_SELL"
                            signal.token_id = fallback_token
                            signal.price = fallback_price
                        else:
                            logger.error(f"❌ SELL FALLBACK ALSO FAILED")
            else:
                logger.success(f"✅ EXIT ORDER SUCCESS")

            # PnL 계산
            pnl = 0
            pnl_pct = 0
            entry_price = 0

            if ctx.position_yes > 0:
                entry_price = ctx.avg_price_yes
                if signal.action == "EXIT_SELL":
                    # SELL: 간단한 계산 (팔 가격 - 산 가격)
                    pnl = signal.size * (signal.price - entry_price)
                else:
                    # BUY: 기존 계산
                    pnl = signal.size * (1.0 - entry_price - signal.price)
                pnl_pct = (pnl / (signal.size * entry_price)) if entry_price > 0 else 0
                side = "YES"
            else:
                entry_price = ctx.avg_price_no
                if signal.action == "EXIT_SELL":
                    # SELL: 간단한 계산 (팔 가격 - 산 가격)
                    pnl = signal.size * (signal.price - entry_price)
                else:
                    # BUY: 기존 계산
                    pnl = signal.size * (1.0 - entry_price - signal.price)
                pnl_pct = (pnl / (signal.size * entry_price)) if entry_price > 0 else 0
                side = "NO"

            if success:
                # 포지션 업데이트 (성공했을 때만)
                if ctx.position_yes > 0:
                    ctx.position_yes = max(0, ctx.position_yes - signal.size)
                    if ctx.position_yes == 0:
                        ctx.avg_price_yes = 0
                else:
                    ctx.position_no = max(0, ctx.position_no - signal.size)
                    if ctx.position_no == 0:
                        ctx.avg_price_no = 0

                # 전략 콜백 (MultiLevelStrategy 전용)
                if hasattr(self.strategy, 'on_exit_filled'):
                    self.strategy.on_exit_filled(market_id=market_id, side=side)

                self.total_trades += 1
                self.total_pnl += pnl

                if pnl > 0:
                    self.winning_trades += 1

                await on_trade_executed({
                    "market_id": market_id,
                    "market_question": self.active_markets.get(market_id, {}).get("question", "Unknown"),
                    "action": "EXIT",
                    "side": side,
                    "entry_price": entry_price,
                    "exit_price": signal.price,
                    "size": signal.size,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "status": "success",
                    "timestamp": time.time()
                })
            else:
                # 실패한 EXIT도 기록 (포지션/통계는 업데이트 안 함)
                await on_trade_executed({
                    "market_id": market_id,
                    "market_question": self.active_markets.get(market_id, {}).get("question", "Unknown"),
                    "action": "EXIT",
                    "side": side,
                    "entry_price": entry_price,
                    "exit_price": signal.price,
                    "size": signal.size,
                    "pnl": pnl,  # 계산만 하고 적용 안 함
                    "pnl_pct": pnl_pct,
                    "status": "failed",
                    "timestamp": time.time()
                })

    def _place_limit_order_sync(self, market_id: str, token_id: str, price: float, size: float, action: str, metadata: dict = None) -> Optional[str]:
        """
        진입 후 자동으로 익절 limit order를 거는 동기 메서드

        Returns:
            order_id if successful, None otherwise
        """
        try:
            logger.info(f"📋 [TP Limit Order] Placing {action} limit order: Token={token_id[:8]}, Price={price:.3f}, Size={size}")

            # Limit order는 비동기 컨텍스트가 필요하므로 asyncio.create_task로 실행
            # 동기 메서드이므로 Task 생성만 하고 반환
            loop = asyncio.get_event_loop()
            task = loop.create_task(self._place_limit_order_async(token_id, price, size, action))

            # Task ID를 order ID로 사용 (실제 order ID는 나중에 받음)
            return f"limit-{token_id[:8]}-{price:.3f}"
        except Exception as e:
            logger.error(f"Failed to place limit order: {e}")
            return None

    async def _place_limit_order_async(self, token_id: str, price: float, size: float, action: str):
        """실제 limit order 비동기 실행"""
        try:
            # action에 따라 OrderSide 결정
            if action == "SELL":
                order_side = OrderSide.SELL
                # SELL order는 토큰 잔액이 필요하므로 약간 지연
                logger.info(f"Waiting 3s for token settlement before placing SELL limit order...")
                await asyncio.sleep(3)
            else:  # UNWIND = BUY
                order_side = OrderSide.BUY

            # Limit order 배치 (post_only=True)
            resp = await self.poly_client.place_order(
                token_id=token_id,
                price=price,
                size=size,
                side=order_side,
                post_only=True  # Limit order는 post_only
            )

            if resp:
                logger.success(f"✅ TP Limit Order placed: {action} {size} @ {price:.3f} → {resp}")
            else:
                logger.error(f"❌ TP Limit Order failed: {action} {size} @ {price:.3f}")

        except Exception as e:
            logger.error(f"TP Limit Order error: {e}")
            # SELL order 실패 시 (잔액 부족일 가능성), 5초 후 재시도
            if action == "SELL" and "balance" in str(e).lower():
                logger.warning(f"Retrying SELL limit order in 5s...")
                await asyncio.sleep(5)
                try:
                    resp = await self.poly_client.place_order(
                        token_id=token_id,
                        price=price,
                        size=size,
                        side=OrderSide.SELL,
                        post_only=True
                    )
                    if resp:
                        logger.success(f"✅ TP Limit Order placed (retry): {action} {size} @ {price:.3f} → {resp}")
                except Exception as e2:
                    logger.error(f"TP Limit Order retry failed: {e2}")

    async def evaluate_market(self, market_id: str, ctx):
        """마켓 평가 (오버라이드 - 실시간 업데이트 추가)"""
        # 가격 변경 추적을 위해 이전 가격 저장
        if not hasattr(self, '_last_prices'):
            self._last_prices = {}

        old_yes = self._last_prices.get(market_id, {}).get('yes', 0)
        old_no = self._last_prices.get(market_id, {}).get('no', 0)

        # 오더북에서 가격 먼저 가져오기
        bid_yes, ask_yes = self.orderbook_tracker.get_price(ctx.token_yes)
        bid_no, ask_no = self.orderbook_tracker.get_price(ctx.token_no)

        if not ask_yes and not ask_no:
            logger.warning(f"No prices for {market_id}: ask_yes={ask_yes}, ask_no={ask_no}")

        # 가격 상세 로깅 (디버깅용)
        if ask_yes and ask_no:
            logger.debug(f"[{market_id[:8]}] Prices - YES: bid={bid_yes:.3f} ask={ask_yes:.3f} | NO: bid={bid_no:.3f} ask={ask_no:.3f}")

        # Mid Price 계산 (UI 표시용)
        mid_yes = (bid_yes + ask_yes) / 2 if bid_yes and ask_yes else ask_yes
        mid_no = (bid_no + ask_no) / 2 if bid_no and ask_no else ask_no

        # 원래 로직 (가격 업데이트 포함 - Ask 가격 사용)
        await super().evaluate_market(market_id, ctx)

        # 가격이 변경되었는지 확인
        price_changed = (old_yes != ctx.yes_price or old_no != ctx.no_price)

        # 가격 저장
        self._last_prices[market_id] = {
            'yes': ctx.yes_price,
            'no': ctx.no_price
        }

        # 가격이 변경되었으면 즉시 브로드캐스트, 아니면 0.1초마다
        if not hasattr(self, '_last_broadcast_time'):
            self._last_broadcast_time = {}

        now = time.time()
        should_broadcast = (
            price_changed or  # 가격 변화 시 즉시
            market_id not in self._last_broadcast_time or
            now - self._last_broadcast_time[market_id] > 0.1  # 또는 0.1초마다
        )

        if should_broadcast:
            self._last_broadcast_time[market_id] = now

            summary = self.strategy.get_position_summary(ctx)
            await on_market_update({
                "market_id": market_id,
                "question": self.active_markets.get(market_id, {}).get("question", "Unknown"),
                "yes_price": mid_yes,  # Mid price for display
                "no_price": mid_no,    # Mid price for display
                "yes_ask": ctx.yes_price,  # Ask price for reference
                "no_ask": ctx.no_price,    # Ask price for reference
                "position": summary,
                "time_remaining": ctx.end_time - time.time(),
                "btc_price": self.price_tracker.get_current_price(),
                "timestamp": time.time()
            })


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 라이프사이클"""
    global bot_instance, bot_task

    logger.info("Starting BTC Scalping Web Server...")
    logger.critical(f"🚨 TRADING_ENABLED = {config.trading_enabled} 🚨")
    if not config.trading_enabled:
        logger.error("⚠️  BOT IS IN DRY RUN MODE - NO REAL ORDERS WILL BE PLACED ⚠️")
    else:
        logger.success("✅ LIVE TRADING MODE ACTIVE ✅")

    bot_instance = WebBTCScalpingBot(use_multilevel_strategy=True)

    # 오더북 업데이트 시 즉시 브로드캐스트하는 콜백 추가
    async def on_orderbook_update(token_id: str, _orderbook):
        """오더북 업데이트 시 즉시 호출"""
        # 토큰이 어느 마켓에 속하는지 찾기
        if not bot_instance:
            return

        for market_id, ctx in bot_instance.market_contexts.items():
            if token_id in [ctx.token_yes, ctx.token_no]:
                # 가격 가져오기
                bid_yes, ask_yes = bot_instance.orderbook_tracker.get_price(ctx.token_yes)
                bid_no, ask_no = bot_instance.orderbook_tracker.get_price(ctx.token_no)

                # 🔍 DEBUG: Log retrieved prices
                logger.debug(f"🎯 Callback prices for {market_id[:16]}...")
                logger.debug(f"   YES token {ctx.token_yes[:16]}... -> bid={bid_yes:.4f}, ask={ask_yes:.4f}")
                logger.debug(f"   NO token {ctx.token_no[:16]}... -> bid={bid_no:.4f}, ask={ask_no:.4f}")

                if ask_yes and ask_no:
                    # 가격 변경 확인 (업데이트 전에 체크)
                    old_yes = getattr(ctx, 'yes_price', 0)
                    old_no = getattr(ctx, 'no_price', 0)

                    # CRITICAL: Update context prices (used by strategy)
                    ctx.yes_price = ask_yes
                    ctx.no_price = ask_no

                    # Mid Price 계산 (UI 표시용)
                    mid_yes = (bid_yes + ask_yes) / 2 if bid_yes and ask_yes else ask_yes
                    mid_no = (bid_no + ask_no) / 2 if bid_no and ask_no else ask_no

                    # 🔍 DEBUG: Log calculated mid prices
                    logger.debug(f"   Mid prices: YES={mid_yes:.4f}, NO={mid_no:.4f}")

                    if old_yes != ask_yes or old_no != ask_no:
                        # 🔍 DEBUG: Log price change
                        logger.debug(f"   Price changed: YES {old_yes:.4f}→{ask_yes:.4f}, NO {old_no:.4f}→{ask_no:.4f}")

                        # 즉시 브로드캐스트
                        summary = bot_instance.strategy.get_position_summary(ctx)
                        await on_market_update({
                            "market_id": market_id,
                            "question": bot_instance.active_markets.get(market_id, {}).get("question", "Unknown"),
                            "yes_price": mid_yes,  # Mid price for display
                            "no_price": mid_no,    # Mid price for display
                            "yes_ask": ask_yes,    # Ask price for reference
                            "no_ask": ask_no,      # Ask price for reference
                            "position": summary,
                            "time_remaining": ctx.end_time - time.time(),
                            "btc_price": bot_instance.price_tracker.get_current_price(),
                            "timestamp": time.time()
                        })
                break

    # 콜백 등록
    bot_instance.orderbook_tracker.add_callback(on_orderbook_update)

    async def run_bot():
        await bot_instance.start()
        while bot_instance.is_running:
            try:
                # 마켓 스캔
                if time.time() - bot_instance.last_market_scan > 30:
                    await bot_instance.scan_and_add_markets()
                    bot_instance.last_market_scan = time.time()

                # 만료된 마켓 정리
                await bot_instance.cleanup_expired_markets()

                # 활성 마켓 평가
                await bot_instance.evaluate_all_markets()

                # 상태 브로드캐스트
                await on_bot_status_change({
                    "running": bot_instance.is_running,
                    "active_markets": len(bot_instance.active_markets),
                    "total_trades": bot_instance.total_trades,
                    "winning_trades": bot_instance.winning_trades,
                    "total_pnl": bot_instance.total_pnl,
                    "win_rate": bot_instance.winning_trades / bot_instance.total_trades if bot_instance.total_trades > 0 else 0,
                    "btc_price": bot_instance.price_tracker.get_current_price() if bot_instance.price_tracker else None,
                    "timestamp": time.time()
                })

                # 0.05초 대기 - 초고속 응답성 (초당 20회 업데이트)
                await asyncio.sleep(0.05)

            except Exception as e:
                logger.error(f"Bot loop error: {e}")
                await asyncio.sleep(5)

    bot_task = asyncio.create_task(run_bot())

    yield

    # Shutdown
    logger.info("Shutting down...")
    bot_instance.is_running = False
    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
    await bot_instance.stop()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# API Models
class ControlAction(BaseModel):
    action: str  # "start", "stop", "pause"


# REST API Endpoints
@app.get("/api/status")
async def get_status():
    """봇 현재 상태"""
    if not bot_instance:
        return {"status": "initializing"}

    active_markets_info = []
    for market_id, ctx in bot_instance.market_contexts.items():
        market = bot_instance.active_markets.get(market_id, {})
        summary = bot_instance.strategy.get_position_summary(ctx)

        active_markets_info.append({
            "id": market_id,
            "question": market.get("question", "Unknown"),
            "time_remaining": ctx.end_time - time.time(),
            "yes_price": ctx.yes_price,
            "no_price": ctx.no_price,
            "position": summary,
            "liquidity": market.get("liquidity", 0),
            "volume": market.get("volume", 0)
        })

    # 거래 히스토리에서 통계 계산 (더 정확함)
    exit_trades = [t for t in trade_history if t.get("action") == "EXIT" and t.get("status") == "success"]
    total_exits = len(exit_trades)
    winning_exits = len([t for t in exit_trades if t.get("pnl", 0) > 0])
    total_pnl_from_history = sum(t.get("pnl", 0) for t in exit_trades)

    # 진입 거래 통계
    entry_trades = [t for t in trade_history if t.get("action") in ["ENTER_YES", "ENTER_NO"]]
    successful_entries = len([t for t in entry_trades if t.get("status") == "success"])
    failed_entries = len([t for t in entry_trades if t.get("status") == "failed"])

    return {
        "running": bot_instance.is_running,
        "btc_price": bot_instance.price_tracker.get_current_price() if bot_instance.price_tracker else None,
        "active_markets": active_markets_info,
        "stats": {
            "total_trades": total_exits,
            "winning_trades": winning_exits,
            "total_pnl": total_pnl_from_history,
            "win_rate": winning_exits / total_exits if total_exits > 0 else 0,
            "total_entries": len(entry_trades),
            "successful_entries": successful_entries,
            "failed_entries": failed_entries,
            "entry_success_rate": successful_entries / len(entry_trades) if len(entry_trades) > 0 else 0
        },
        "config": {
            "trading_enabled": config.trading_enabled,
            "max_concurrent_markets": config.max_concurrent_markets,
            "daily_loss_limit": config.daily_loss_limit_usdc
        }
    }


@app.get("/api/trades")
async def get_trades(limit: int = 50):
    """거래 히스토리"""
    return {
        "trades": trade_history[-limit:],
        "total": len(trade_history)
    }


@app.get("/api/events")
async def get_events(limit: int = 100):
    """이벤트 로그"""
    return {
        "events": event_log[-limit:],
        "total": len(event_log)
    }


class AddMarketRequest(BaseModel):
    market_url: str  # Polymarket URL


@app.get("/api/websocket_status")
async def get_websocket_status():
    """WebSocket 연결 상태 확인"""
    if not bot_instance:
        return {"error": "Bot not initialized"}

    status = bot_instance.orderbook_tracker.get_status()
    return status


@app.post("/api/websocket_reconnect")
async def reconnect_websocket():
    """WebSocket 재연결"""
    if not bot_instance:
        return {"error": "Bot not initialized"}

    try:
        # 기존 연결 중지
        await bot_instance.orderbook_tracker.stop()
        await asyncio.sleep(1)

        # 재연결
        await bot_instance.orderbook_tracker.start()

        # 활성 마켓 재구독
        for market_id, market_info in bot_instance.active_markets.items():
            tokens = market_info.get('tokens', [])
            if tokens and len(tokens) >= 2:
                token_ids = [tokens[0]['token_id'], tokens[1]['token_id']]
                await bot_instance.orderbook_tracker.subscribe(market_id, token_ids)
                logger.info(f"Re-subscribed to market {market_id}")

        return {"status": "success", "message": "WebSocket reconnected"}
    except Exception as e:
        logger.error(f"Failed to reconnect WebSocket: {e}")
        return {"status": "error", "message": str(e)}


class ConfigUpdate(BaseModel):
    max_trades_per_market: Optional[int] = None
    # 레벨 진입 설정
    level_1_price: Optional[float] = None
    level_1_size: Optional[float] = None
    level_2_price: Optional[float] = None
    level_2_size: Optional[float] = None
    level_3_price: Optional[float] = None
    level_3_size: Optional[float] = None
    # 기대 수익률
    profit_target_pct: Optional[float] = None
    # High price scalping 설정
    enable_high_price_scalping: Optional[bool] = None
    high_price_threshold: Optional[float] = None  # 80c+ 쪽 threshold
    high_price_scalp_size: Optional[float] = None
    high_price_profit_pct: Optional[float] = None

@app.get("/api/config")
async def get_config():
    """현재 설정 조회"""
    if not bot_instance or not hasattr(bot_instance.strategy, 'entry_levels'):
        return {"error": "Bot not initialized"}

    strategy = bot_instance.strategy
    return {
        "max_trades_per_market": strategy.max_trades_per_market,
        "entry_levels": [
            {"price": strategy.entry_levels[0], "size": strategy.level_sizes[0]},
            {"price": strategy.entry_levels[1], "size": strategy.level_sizes[1]},
            {"price": strategy.entry_levels[2], "size": strategy.level_sizes[2]},
        ],
        "profit_target_pct": strategy.take_profit_pct * 100,  # % 단위로 반환
        "enable_high_price_scalping": strategy.enable_high_price_scalping,
        "high_price_threshold": strategy.high_price_threshold,
        "high_price_scalp_size": strategy.high_price_scalp_size,
        "high_price_profit_pct": strategy.high_price_profit_pct * 100,
    }

@app.post("/api/config")
async def update_config(config_update: ConfigUpdate):
    """설정 업데이트"""
    if not bot_instance:
        return {"error": "Bot not initialized"}

    strategy = bot_instance.strategy

    # 마켓별 거래 횟수
    if config_update.max_trades_per_market is not None:
        strategy.max_trades_per_market = config_update.max_trades_per_market
        logger.info(f"Updated max_trades_per_market to {config_update.max_trades_per_market}")

    # 레벨 가격 업데이트
    if config_update.level_1_price is not None:
        strategy.entry_levels[0] = config_update.level_1_price
        logger.info(f"Updated level 1 price to {config_update.level_1_price}")

    if config_update.level_2_price is not None:
        strategy.entry_levels[1] = config_update.level_2_price
        logger.info(f"Updated level 2 price to {config_update.level_2_price}")

    if config_update.level_3_price is not None:
        strategy.entry_levels[2] = config_update.level_3_price
        logger.info(f"Updated level 3 price to {config_update.level_3_price}")

    # 레벨 사이즈 업데이트
    if config_update.level_1_size is not None:
        strategy.level_sizes[0] = config_update.level_1_size
        logger.info(f"Updated level 1 size to {config_update.level_1_size}")

    if config_update.level_2_size is not None:
        strategy.level_sizes[1] = config_update.level_2_size
        logger.info(f"Updated level 2 size to {config_update.level_2_size}")

    if config_update.level_3_size is not None:
        strategy.level_sizes[2] = config_update.level_3_size
        logger.info(f"Updated level 3 size to {config_update.level_3_size}")

    # 수익률 목표
    if config_update.profit_target_pct is not None:
        strategy.take_profit_pct = config_update.profit_target_pct / 100.0  # % -> 소수
        logger.info(f"Updated profit target to {config_update.profit_target_pct}%")

    # High price scalping 설정
    if config_update.enable_high_price_scalping is not None:
        strategy.enable_high_price_scalping = config_update.enable_high_price_scalping
        logger.info(f"Updated enable_high_price_scalping to {config_update.enable_high_price_scalping}")

    if config_update.high_price_threshold is not None:
        strategy.high_price_threshold = config_update.high_price_threshold
        logger.info(f"Updated high_price_threshold to {config_update.high_price_threshold}")

    if config_update.high_price_scalp_size is not None:
        strategy.high_price_scalp_size = config_update.high_price_scalp_size
        logger.info(f"Updated high_price_scalp_size to {config_update.high_price_scalp_size}")

    if config_update.high_price_profit_pct is not None:
        strategy.high_price_profit_pct = config_update.high_price_profit_pct / 100.0
        logger.info(f"Updated high_price_profit_pct to {config_update.high_price_profit_pct}%")

    return {
        "status": "success",
        "config": {
            "max_trades_per_market": strategy.max_trades_per_market,
            "entry_levels": strategy.entry_levels,
            "level_sizes": strategy.level_sizes,
            "profit_target_pct": strategy.take_profit_pct * 100,
            "enable_high_price_scalping": strategy.enable_high_price_scalping,
            "high_price_threshold": strategy.high_price_threshold,
            "high_price_scalp_size": strategy.high_price_scalp_size,
            "high_price_profit_pct": strategy.high_price_profit_pct * 100,
        }
    }

@app.post("/api/emergency_unwind/{market_id}")
async def emergency_unwind(market_id: str):
    """
    긴급 청산 - 특정 마켓의 모든 포지션을 즉시 청산

    1. 모든 포지션 확인
    2. Unwinding 시도 (반대 토큰 매수)
    3. 잔액 부족 시 SELL로 전환
    4. 해당 마켓 자동 거래 중지
    """
    if not bot_instance:
        return {"error": "Bot not initialized"}

    try:
        # 마켓 확인
        if market_id not in bot_instance.market_contexts:
            return {"error": f"Market {market_id} not found"}

        ctx = bot_instance.market_contexts[market_id]

        # 전략에서 포지션 확인
        if not hasattr(bot_instance.strategy, 'positions'):
            return {"error": "Strategy does not support positions"}

        positions = bot_instance.strategy.positions.get(market_id, [])

        if not positions:
            return {"message": "No positions to unwind", "positions_closed": 0}

        logger.warning(f"🚨 EMERGENCY UNWIND requested for market {market_id}")
        logger.warning(f"   Positions to close: {len(positions)}")

        closed_count = 0
        results = []

        # 같은 side끼리 묶어서 처리
        from collections import defaultdict
        positions_by_side = defaultdict(list)
        for pos in positions:
            positions_by_side[pos.side].append(pos)

        # 각 side별로 청산
        for side, side_positions in positions_by_side.items():
            total_size = sum(p.size for p in side_positions)
            total_cost = sum(p.size * p.entry_price for p in side_positions)
            avg_entry = total_cost / total_size if total_size > 0 else 0

            logger.warning(f"   Closing {side} position: {total_size} shares @ avg {avg_entry:.3f}")

            # Unwinding 시도 (반대 토큰 매수)
            if side == "YES":
                # YES 포지션 → NO 토큰 매수
                exit_token = ctx.token_no
                exit_price = ctx.no_price
                opposite = "NO"
            else:
                # NO 포지션 → YES 토큰 매수
                exit_token = ctx.token_yes
                exit_price = ctx.yes_price
                opposite = "YES"

            # 잔액 확인
            balance = await bot_instance.poly_client.get_usdc_balance()
            required = total_size * exit_price

            logger.warning(f"   Required: ${required:.2f}, Balance: ${balance:.2f}")

            if balance >= required:
                # Unwinding 가능
                logger.warning(f"   → Unwinding: BUY {opposite} {total_size} @ {exit_price:.3f}")
                success = await bot_instance.place_order(
                    token_id=exit_token,
                    price=exit_price,
                    size=total_size,
                    side=OrderSide.BUY
                )

                if success:
                    closed_count += 1
                    results.append({
                        "side": side,
                        "method": "UNWIND",
                        "size": total_size,
                        "price": exit_price,
                        "status": "success"
                    })
                else:
                    results.append({
                        "side": side,
                        "method": "UNWIND",
                        "size": total_size,
                        "price": exit_price,
                        "status": "failed"
                    })
            else:
                # SELL로 전환
                sell_token = ctx.token_yes if side == "YES" else ctx.token_no
                sell_price = ctx.yes_price if side == "YES" else ctx.no_price

                logger.warning(f"   → Insufficient balance, SELL instead: SELL {side} {total_size} @ {sell_price:.3f}")
                success = await bot_instance.place_order(
                    token_id=sell_token,
                    price=sell_price,
                    size=total_size,
                    side=OrderSide.SELL
                )

                if success:
                    closed_count += 1
                    results.append({
                        "side": side,
                        "method": "SELL",
                        "size": total_size,
                        "price": sell_price,
                        "status": "success"
                    })
                else:
                    results.append({
                        "side": side,
                        "method": "SELL",
                        "size": total_size,
                        "price": sell_price,
                        "status": "failed"
                    })

        # 포지션 클리어
        bot_instance.strategy.positions[market_id] = []

        # 해당 마켓 자동 거래 중지 (거래 횟수 최대치로 설정)
        bot_instance.strategy.trade_count[market_id] = bot_instance.strategy.max_trades_per_market

        logger.success(f"✓ Emergency unwind complete: {closed_count} positions closed")

        return {
            "status": "success",
            "market_id": market_id,
            "positions_closed": closed_count,
            "results": results,
            "message": f"Closed {closed_count} positions, auto-trading disabled for this market"
        }

    except Exception as e:
        logger.error(f"Emergency unwind failed: {e}")
        return {"error": str(e)}

@app.get("/api/config")
async def get_config():
    """현재 설정 가져오기"""
    if not bot_instance:
        return {"error": "Bot not initialized"}

    if hasattr(bot_instance.strategy, 'max_trades_per_market'):
        return {
            "max_trades_per_market": bot_instance.strategy.max_trades_per_market
        }

    return {"max_trades_per_market": 1}

@app.post("/api/control")
async def control_bot(ctrl: ControlAction):
    """봇 제어"""
    if not bot_instance:
        return {"error": "Bot not initialized"}

    if ctrl.action == "start":
        bot_instance.is_running = True
        return {"status": "started"}
    elif ctrl.action == "stop":
        bot_instance.is_running = False
        return {"status": "stopped"}
    elif ctrl.action == "pause":
        bot_instance.is_running = False
        return {"status": "paused"}

    return {"error": "Invalid action"}


@app.post("/api/add_market")
async def add_market_manually(req: AddMarketRequest):
    """수동으로 마켓 추가"""
    if not bot_instance:
        return {"error": "Bot not initialized"}

    try:
        # URL에서 slug 추출
        # 예: https://polymarket.com/event/btc-updown-15m-1768889700
        slug = req.market_url.split("/")[-1]

        # Gamma API로 마켓 정보 가져오기 (events endpoint 사용)
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url = f"https://gamma-api.polymarket.com/events?slug={slug}"
            async with session.get(url) as resp:
                if resp.status != 200:
                    return {"error": f"Market not found: {slug}"}

                events = await resp.json()
                if not events or len(events) == 0:
                    return {"error": f"No events found for slug: {slug}"}

                # 첫 번째 이벤트 가져오기
                event_data = events[0]

                # 이벤트 내부의 첫 번째 마켓 가져오기
                if "markets" not in event_data or len(event_data["markets"]) == 0:
                    return {"error": f"No markets found in event: {slug}"}

                market_data = event_data["markets"][0]

        # 마켓 정보 추출
        import json
        from datetime import datetime

        market_details = {
            "id": market_data.get("id"),
            "question": market_data.get("question"),
            "slug": market_data.get("slug"),
            "condition_id": market_data.get("conditionId"),
            "end_date": market_data.get("endDate"),
            "liquidity": float(market_data.get("liquidity", 0)),
            "volume": float(market_data.get("volume", 0)),
            "volume24hr": float(market_data.get("volume24hr", 0))
        }

        # 토큰 ID 추출 (clobTokenIds가 없으면 tokens에서 추출)
        clob_ids = json.loads(market_data.get("clobTokenIds", "[]")) if market_data.get("clobTokenIds") else []
        if not clob_ids and "tokens" in market_data:
            clob_ids = [t.get("token_id") or t.get("id") for t in market_data.get("tokens", [])]

        if len(clob_ids) >= 2:
            market_details["token_yes"] = clob_ids[0]
            market_details["token_no"] = clob_ids[1]
        else:
            return {"error": "Invalid market: missing tokens"}

        # 남은 시간 계산
        end_dt = datetime.fromisoformat(market_details["end_date"].replace("Z", "+00:00"))
        now_dt = datetime.now(end_dt.tzinfo)
        remaining = (end_dt - now_dt).total_seconds()
        market_details["minutes_remaining"] = remaining / 60

        # 봇에 마켓 추가
        await bot_instance.add_market(market_details)

        return {
            "status": "success",
            "market": market_details
        }

    except Exception as e:
        logger.error(f"Error adding market: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


@app.delete("/api/remove_market/{market_id}")
async def remove_market(market_id: str):
    """마켓 수동 삭제"""
    if not bot_instance:
        return {"error": "Bot not initialized"}

    try:
        # 마켓이 존재하는지 확인
        if market_id not in bot_instance.active_markets:
            return {"error": f"Market not found: {market_id}"}

        # 마켓 정보 저장 (응답용)
        market_info = bot_instance.active_markets[market_id]

        # 봇에서 마켓 제거
        if market_id in bot_instance.active_markets:
            del bot_instance.active_markets[market_id]
        if market_id in bot_instance.market_contexts:
            del bot_instance.market_contexts[market_id]
        if market_id in bot_instance.market_start_prices:
            del bot_instance.market_start_prices[market_id]

        logger.info(f"Market removed manually: {market_id}")

        return {
            "status": "success",
            "message": f"Market {market_id} removed",
            "market": market_info
        }

    except Exception as e:
        logger.error(f"Error removing market: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


@app.get("/api/search_markets")
async def search_markets(query: str = ""):
    """마켓 검색"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            if query:
                url = f"https://gamma-api.polymarket.com/markets?q={query}&limit=20&active=true&closed=false"
            else:
                url = "https://gamma-api.polymarket.com/markets?limit=20&active=true&closed=false&order=volume24hr&ascending=false"

            async with session.get(url) as resp:
                if resp.status == 200:
                    markets = await resp.json()

                    # 간단한 정보만 반환
                    results = []
                    for m in markets[:10]:
                        results.append({
                            "id": m.get("id"),
                            "question": m.get("question"),
                            "slug": m.get("slug"),
                            "liquidity": float(m.get("liquidity", 0)),
                            "volume24hr": float(m.get("volume24hr", 0)),
                            "url": f"https://polymarket.com/event/{m.get('slug')}"
                        })

                    return {"markets": results}

        return {"markets": []}
    except Exception as e:
        logger.error(f"Search error: {e}")
        return {"error": str(e)}


# WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """실시간 데이터 스트림"""
    await manager.connect(websocket)

    try:
        # 초기 상태 전송
        await websocket.send_json({
            "type": "connected",
            "data": {
                "message": "Connected to BTC Scalping Bot",
                "timestamp": time.time()
            }
        })

        # 연결 유지
        while True:
            # 클라이언트로부터 메시지 수신 (ping/pong)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Echo back (keep-alive)
                await websocket.send_json({"type": "pong", "timestamp": time.time()})
            except asyncio.TimeoutError:
                # 타임아웃이면 ping 전송
                await websocket.send_json({"type": "ping", "timestamp": time.time()})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# HTML 페이지
@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """메인 대시보드"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>BTC Scalping Bot Dashboard</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body class="bg-gray-900 text-gray-100">
        <div id="app" class="container mx-auto px-4 py-6">
            <!-- Header -->
            <div class="mb-8">
                <h1 class="text-4xl font-bold mb-2">🚀 BTC Scalping Bot</h1>
                <p class="text-gray-400">Real-time 15-minute market trading dashboard</p>
            </div>

            <!-- Status Bar -->
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                <div class="bg-gray-800 rounded-lg p-4">
                    <div class="text-sm text-gray-400">Bot Status</div>
                    <div class="text-2xl font-bold" :class="status.running ? 'text-green-400' : 'text-red-400'">
                        {{ status.running ? 'RUNNING' : 'STOPPED' }}
                    </div>
                </div>
                <div class="bg-gray-800 rounded-lg p-4">
                    <div class="text-sm text-gray-400">BTC Price</div>
                    <div class="text-2xl font-bold text-blue-400">
                        ${{ formatNumber(status.btc_price) }}
                    </div>
                </div>
                <div class="bg-gray-800 rounded-lg p-4">
                    <div class="text-sm text-gray-400">Total PnL</div>
                    <div class="text-2xl font-bold" :class="status.stats?.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'">
                        ${{ formatNumber(status.stats?.total_pnl, 2, true) }}
                    </div>
                    <div class="text-xs text-gray-500 mt-1">
                        {{ status.stats?.total_trades || 0 }} completed trades
                    </div>
                </div>
                <div class="bg-gray-800 rounded-lg p-4">
                    <div class="text-sm text-gray-400">Win Rate</div>
                    <div class="text-2xl font-bold text-purple-400">
                        {{ formatPercent(status.stats?.win_rate) }}
                    </div>
                    <div class="text-xs text-gray-500 mt-1">
                        {{ status.stats?.winning_trades || 0 }} / {{ status.stats?.total_trades || 0 }} wins
                    </div>
                </div>
            </div>

            <!-- Additional Stats -->
            <div class="bg-gray-800 rounded-lg p-4 mb-6">
                <h3 class="text-lg font-semibold mb-3">📊 Trading Statistics</h3>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <div class="text-gray-400">Total Entries</div>
                        <div class="text-xl font-bold text-blue-400">{{ status.stats?.total_entries || 0 }}</div>
                    </div>
                    <div>
                        <div class="text-gray-400">Successful Entries</div>
                        <div class="text-xl font-bold text-green-400">{{ status.stats?.successful_entries || 0 }}</div>
                    </div>
                    <div>
                        <div class="text-gray-400">Failed Entries</div>
                        <div class="text-xl font-bold text-red-400">{{ status.stats?.failed_entries || 0 }}</div>
                    </div>
                    <div>
                        <div class="text-gray-400">Entry Success Rate</div>
                        <div class="text-xl font-bold text-purple-400">{{ formatPercent(status.stats?.entry_success_rate) }}</div>
                    </div>
                </div>
            </div>

            <!-- Controls -->
            <div class="bg-gray-800 rounded-lg p-4 mb-6">
                <div class="flex gap-4 mb-4">
                    <button @click="controlBot('start')"
                            class="px-6 py-2 bg-green-600 hover:bg-green-700 rounded-lg font-semibold">
                        ▶ Start
                    </button>
                    <button @click="controlBot('stop')"
                            class="px-6 py-2 bg-red-600 hover:bg-red-700 rounded-lg font-semibold">
                        ⏹ Stop
                    </button>
                    <button @click="loadData"
                            class="px-6 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold">
                        🔄 Refresh
                    </button>
                    <div class="flex-1"></div>
                    <div class="flex items-center gap-2">
                        <span class="w-3 h-3 rounded-full" :class="wsConnected ? 'bg-green-500' : 'bg-red-500'"></span>
                        <span class="text-sm">{{ wsConnected ? 'Connected' : 'Disconnected' }}</span>
                    </div>
                </div>

                <!-- WebSocket Status -->
                <div class="border-t border-gray-700 pt-4">
                    <div class="flex items-center justify-between mb-2">
                        <h3 class="text-lg font-semibold">WebSocket Status</h3>
                        <button @click="reconnectWebSocket"
                                class="px-4 py-1 text-sm bg-yellow-600 hover:bg-yellow-700 rounded font-semibold"
                                :disabled="wsReconnecting">
                            {{ wsReconnecting ? '⏳ Reconnecting...' : '🔌 Reconnect WS' }}
                        </button>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                        <div class="bg-gray-700 rounded p-2">
                            <div class="text-gray-400 text-xs">Status</div>
                            <div class="font-bold" :class="wsStatus.connected ? 'text-green-400' : 'text-red-400'">
                                {{ wsStatus.connected ? '✓ Connected' : '✗ Disconnected' }}
                            </div>
                        </div>
                        <div class="bg-gray-700 rounded p-2">
                            <div class="text-gray-400 text-xs">Subscriptions</div>
                            <div class="font-bold text-blue-400">
                                {{ wsStatus.subscribed_tokens || 0 }} tokens
                            </div>
                        </div>
                        <div class="bg-gray-700 rounded p-2">
                            <div class="text-gray-400 text-xs">Total Messages</div>
                            <div class="font-bold text-purple-400">
                                {{ formatNumber(wsStatus.total_messages) || 0 }}
                            </div>
                        </div>
                        <div class="bg-gray-700 rounded p-2">
                            <div class="text-gray-400 text-xs">Last Message</div>
                            <div class="font-bold" :class="wsStatus.is_healthy ? 'text-green-400' : 'text-red-400'">
                                {{ formatLastMessageTime(wsStatus.last_message_ago) }}
                            </div>
                        </div>
                    </div>
                    <div v-if="!wsStatus.is_healthy && wsStatus.last_message_ago >= 0"
                         class="mt-2 p-2 bg-red-900/30 border border-red-600 rounded text-sm text-red-300">
                        ⚠️ Warning: No messages received for {{ Math.floor(wsStatus.last_message_ago) }}s. Prices may not be updating.
                    </div>
                </div>
            </div>

            <!-- Add Market Section -->
            <div class="bg-gray-800 rounded-lg p-6 mb-6">
                <h2 class="text-2xl font-bold mb-4">➕ Add Market</h2>
                <div class="bg-gray-700 rounded-lg p-4">
                    <div class="flex gap-2">
                        <input v-model="marketUrl"
                               type="text"
                               placeholder="https://polymarket.com/event/btc-updown-15m-..."
                               class="flex-1 px-3 py-2 bg-gray-600 rounded border border-gray-500 text-white">
                        <button @click="addMarket"
                                class="px-4 py-2 bg-green-600 hover:bg-green-700 rounded font-semibold">
                            Add
                        </button>
                    </div>
                    <div class="mt-2 text-sm text-gray-400">
                        Paste a Polymarket market URL (e.g., https://polymarket.com/event/btc-updown-15m-1768889700)
                    </div>

                    <!-- Search Markets -->
                    <div class="mt-4">
                        <div class="flex gap-2 mb-2">
                            <input v-model="searchQuery"
                                   @keyup.enter="searchMarkets"
                                   type="text"
                                   placeholder="Search markets... (e.g., 'BTC', 'Bitcoin')"
                                   class="flex-1 px-3 py-2 bg-gray-600 rounded border border-gray-500 text-white">
                            <button @click="searchMarkets"
                                    class="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded font-semibold">
                                Search
                            </button>
                        </div>
                        <div v-if="searchResults.length > 0" class="space-y-2 max-h-64 overflow-y-auto">
                            <div v-for="market in searchResults" :key="market.id"
                                 class="bg-gray-600 rounded p-2 flex justify-between items-center">
                                <div class="flex-1">
                                    <div class="text-sm font-semibold">{{ market.question }}</div>
                                    <div class="text-xs text-gray-400">
                                        Liquidity: ${{ formatNumber(market.liquidity) }} |
                                        24h Vol: ${{ formatNumber(market.volume24hr) }}
                                    </div>
                                </div>
                                <button @click="marketUrl = market.url; addMarket()"
                                        class="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm">
                                    Add
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Active Markets -->
            <div class="bg-gray-800 rounded-lg p-6 mb-6">
                <h2 class="text-2xl font-bold mb-4">📊 Active Markets ({{ activeMarkets.length }})</h2>
                <div v-if="activeMarkets.length > 0" class="space-y-4">
                    <div v-for="market in activeMarkets" :key="'market-' + market.id"
                         class="bg-gray-700 rounded-lg p-4 transition-opacity duration-200">
                        <div class="flex justify-between items-start mb-2">
                            <div class="flex-1">
                                <div class="font-semibold text-lg">{{ market.question }}</div>
                                <div class="text-sm text-gray-400">ID: {{ market.id }}</div>
                            </div>
                            <div class="flex items-center gap-3">
                                <div class="text-right">
                                    <div class="text-sm text-gray-400">Time Left</div>
                                    <div class="font-semibold text-yellow-400">{{ formatTime(market.time_remaining) }}</div>
                                </div>
                                <button @click="removeMarket(market.id)"
                                        class="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-sm font-semibold"
                                        title="Remove this market">
                                    🗑️
                                </button>
                            </div>
                        </div>
                        <div class="grid grid-cols-2 gap-4 mt-3">
                            <div class="bg-gray-800 rounded p-2">
                                <div class="text-xs text-gray-400 mb-1">YES Price</div>
                                <div class="text-xl font-bold text-green-400">{{ market.yes_price?.toFixed(3) || '-' }}</div>
                            </div>
                            <div class="bg-gray-800 rounded p-2">
                                <div class="text-xs text-gray-400 mb-1">NO Price</div>
                                <div class="text-xl font-bold text-red-400">{{ market.no_price?.toFixed(3) || '-' }}</div>
                            </div>
                        </div>
                        <div class="grid grid-cols-2 gap-4 mt-2 text-xs text-gray-400">
                            <div>Liquidity: ${{ formatNumber(market.liquidity) }}</div>
                            <div>Volume: ${{ formatNumber(market.volume) }}</div>
                        </div>
                        <div v-if="market.position && market.position.has_position" class="mt-3 pt-3 border-t border-gray-600">
                            <div class="text-sm font-semibold text-blue-400">
                                Position: {{ market.position.side }} x{{ market.position.size }}
                            </div>
                            <div class="text-sm mt-1" :class="market.position.unrealized_pnl_pct >= 0 ? 'text-green-400' : 'text-red-400'">
                                PnL: {{ formatPercent(market.position.unrealized_pnl_pct) }}
                                (${{ market.position.unrealized_pnl_usdc?.toFixed(2) || '0.00' }})
                            </div>
                        </div>
                    </div>
                </div>
                <div v-else class="text-center text-gray-500 py-8">
                    <div class="text-lg mb-2">No active markets</div>
                    <div class="text-sm">Click ➕ Add Market above to add a BTC 15m market</div>
                </div>
            </div>

            <!-- Trade History -->
            <div class="bg-gray-800 rounded-lg p-6 mb-6">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-2xl font-bold">💰 Recent Trades</h2>
                    <div class="text-sm text-gray-400">
                        Total: {{ trades.length }} |
                        Success: {{ trades.filter(t => t.status === 'success').length }} |
                        Failed: {{ trades.filter(t => t.status === 'failed').length }}
                    </div>
                </div>
                <div v-if="trades.length > 0" class="space-y-2 max-h-96 overflow-y-auto">
                    <div v-for="trade in trades.slice().reverse()" :key="trade.timestamp"
                         class="rounded p-3"
                         :class="trade.status === 'failed' ? 'bg-red-900/20 border border-red-700' : 'bg-gray-700'">
                        <div class="flex justify-between items-center">
                            <div class="flex items-center gap-2">
                                <!-- Status Badge -->
                                <span v-if="trade.status === 'failed'"
                                      class="px-2 py-0.5 text-xs bg-red-700 text-white rounded">
                                    FAILED
                                </span>

                                <!-- Action -->
                                <span class="font-semibold"
                                      :class="trade.action === 'EXIT' ? 'text-yellow-400' : 'text-blue-400'">
                                    {{ trade.action }}
                                </span>

                                <!-- Side -->
                                <span :class="trade.side === 'YES' ? 'text-green-400' : 'text-red-400'"
                                      class="font-bold">
                                    {{ trade.side }}
                                </span>

                                <!-- Size and Price -->
                                <span class="text-gray-300">
                                    {{ trade.size }}x @ {{ trade.price?.toFixed(3) }}c
                                </span>

                                <!-- Entry/Exit Info for EXIT trades -->
                                <span v-if="trade.action === 'EXIT' && trade.entry_price"
                                      class="text-xs text-gray-400">
                                    ({{ trade.entry_price?.toFixed(3) }}c → {{ trade.exit_price?.toFixed(3) }}c)
                                </span>
                            </div>

                            <!-- PnL and Time -->
                            <div class="text-right">
                                <div v-if="trade.pnl !== undefined" class="flex items-center gap-2">
                                    <span :class="trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'"
                                          class="font-semibold text-lg">
                                        {{ trade.pnl >= 0 ? '+' : '' }}${{ trade.pnl?.toFixed(2) }}
                                    </span>
                                    <span v-if="trade.pnl_pct !== undefined"
                                          :class="trade.pnl_pct >= 0 ? 'text-green-300' : 'text-red-300'"
                                          class="text-sm">
                                        ({{ trade.pnl_pct >= 0 ? '+' : '' }}{{ (trade.pnl_pct * 100).toFixed(1) }}%)
                                    </span>
                                </div>
                                <div v-else-if="trade.action.startsWith('ENTER')" class="text-gray-400 text-sm">
                                    Position: {{ trade.position_after }} @ {{ trade.avg_price?.toFixed(3) }}c
                                </div>
                                <div class="text-xs text-gray-500 mt-1">{{ formatTimestamp(trade.timestamp) }}</div>
                            </div>
                        </div>

                        <!-- Market Question -->
                        <div class="text-sm text-gray-400 mt-2 truncate">{{ trade.market_question }}</div>
                    </div>
                </div>
                <div v-else class="text-center text-gray-500 py-8">
                    No trades yet. Waiting for entry signals...
                </div>
            </div>

            <!-- Events Log -->
            <div class="bg-gray-800 rounded-lg p-6">
                <h2 class="text-2xl font-bold mb-4">📋 Event Log</h2>
                <div class="space-y-1 max-h-64 overflow-y-auto text-sm font-mono">
                    <div v-for="event in events.slice().reverse().slice(0, 50)" :key="event.timestamp"
                         class="flex gap-2 text-gray-400">
                        <span class="text-gray-600">{{ formatTimestamp(event.timestamp) }}</span>
                        <span :class="getEventColor(event.type)">{{ event.type }}</span>
                        <span>{{ formatEventData(event) }}</span>
                    </div>
                </div>
            </div>
        </div>

        <script>
        const { createApp } = Vue;

        createApp({
            data() {
                return {
                    status: {},
                    trades: [],
                    events: [],
                    wsConnected: false,
                    ws: null,
                    showAddMarket: false,
                    marketUrl: '',
                    searchQuery: '',
                    searchResults: [],
                    wsStatus: {
                        connected: false,
                        subscribed_tokens: 0,
                        total_messages: 0,
                        last_message_ago: -1,
                        is_healthy: false
                    },
                    wsReconnecting: false
                }
            },
            computed: {
                activeMarkets() {
                    // 안정적인 키를 위해 active_markets를 복사하고 정렬
                    const markets = this.status.active_markets || [];
                    return markets.slice().sort((a, b) => {
                        // ID로 정렬하여 순서 안정화
                        return (a.id || '').localeCompare(b.id || '');
                    });
                }
            },
            mounted() {
                this.loadData();
                this.connectWebSocket();
                // 주기적 업데이트 - 1초마다 (WebSocket과 함께 사용)
                setInterval(() => this.loadData(), 1000);
            },
            methods: {
                async loadData() {
                    try {
                        const [statusRes, tradesRes, eventsRes, wsStatusRes] = await Promise.all([
                            fetch('/api/status'),
                            fetch('/api/trades'),
                            fetch('/api/events'),
                            fetch('/api/websocket_status')
                        ]);
                        this.status = await statusRes.json();
                        const tradesData = await tradesRes.json();
                        const eventsData = await eventsRes.json();
                        this.trades = tradesData.trades || [];
                        this.events = eventsData.events || [];

                        // WebSocket 상태 업데이트
                        const wsStatusData = await wsStatusRes.json();
                        if (!wsStatusData.error) {
                            this.wsStatus = wsStatusData;
                        }
                    } catch (e) {
                        console.error('Error loading data:', e);
                    }
                },
                connectWebSocket() {
                    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                    this.ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

                    this.ws.onopen = () => {
                        this.wsConnected = true;
                        console.log('WebSocket connected');
                    };

                    this.ws.onclose = () => {
                        this.wsConnected = false;
                        console.log('WebSocket disconnected');
                        // 재연결
                        setTimeout(() => this.connectWebSocket(), 3000);
                    };

                    this.ws.onmessage = (event) => {
                        const msg = JSON.parse(event.data);
                        this.handleWebSocketMessage(msg);
                    };
                },
                handleWebSocketMessage(msg) {
                    if (msg.type === 'trade_executed') {
                        this.trades.push(msg.data);
                        this.events.push({type: 'trade', timestamp: msg.data.timestamp, data: msg.data});
                    } else if (msg.type === 'signal_generated') {
                        this.events.push({type: 'signal', timestamp: msg.data.timestamp, data: msg.data});
                    } else if (msg.type === 'market_update') {
                        // 마켓 상태 업데이트 - 더 빠른 반영
                        if (!this.status.active_markets) {
                            this.status.active_markets = [];
                        }
                        const idx = this.status.active_markets.findIndex(m => m.id === msg.data.id);
                        if (idx >= 0) {
                            // 기존 마켓 업데이트 - 직접 교체 (더 빠름)
                            this.status.active_markets.splice(idx, 1, msg.data);
                        } else {
                            // 새 마켓 추가
                            this.status.active_markets.push(msg.data);
                        }

                        // BTC 가격도 업데이트
                        if (msg.data.btc_price) {
                            this.status.btc_price = msg.data.btc_price;
                        }
                    } else if (msg.type === 'bot_status') {
                        // 전체 상태 업데이트
                        Object.assign(this.status, msg.data);
                    }
                },
                async controlBot(action) {
                    try {
                        await fetch('/api/control', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({action})
                        });
                        await this.loadData();
                    } catch (e) {
                        console.error('Error controlling bot:', e);
                    }
                },
                async reconnectWebSocket() {
                    if (this.wsReconnecting) return;

                    this.wsReconnecting = true;
                    try {
                        const response = await fetch('/api/websocket_reconnect', {
                            method: 'POST'
                        });
                        const result = await response.json();

                        if (result.status === 'success') {
                            console.log('WebSocket reconnected successfully');
                            // 2초 후에 상태 업데이트
                            setTimeout(async () => {
                                await this.loadData();
                                this.wsReconnecting = false;
                            }, 2000);
                        } else {
                            console.error('WebSocket reconnection failed:', result.message);
                            alert('Failed to reconnect WebSocket: ' + result.message);
                            this.wsReconnecting = false;
                        }
                    } catch (e) {
                        console.error('Error reconnecting WebSocket:', e);
                        alert('Error reconnecting WebSocket');
                        this.wsReconnecting = false;
                    }
                },
                async addMarket() {
                    if (!this.marketUrl) {
                        alert('Please enter a market URL');
                        return;
                    }
                    try {
                        const res = await fetch('/api/add_market', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({market_url: this.marketUrl})
                        });
                        const data = await res.json();
                        if (data.error) {
                            alert('Error: ' + data.error);
                        } else {
                            alert('Market added successfully!');
                            this.marketUrl = '';
                            this.showAddMarket = false;
                            await this.loadData();
                        }
                    } catch (e) {
                        console.error('Error adding market:', e);
                        alert('Error adding market');
                    }
                },
                async removeMarket(marketId) {
                    if (!confirm('Are you sure you want to remove this market?')) {
                        return;
                    }
                    try {
                        const res = await fetch(`/api/remove_market/${marketId}`, {
                            method: 'DELETE'
                        });
                        const data = await res.json();
                        if (data.error) {
                            alert('Error: ' + data.error);
                        } else {
                            // 성공 - UI에서 즉시 제거
                            if (this.status.active_markets) {
                                const idx = this.status.active_markets.findIndex(m => m.id === marketId);
                                if (idx >= 0) {
                                    this.status.active_markets.splice(idx, 1);
                                }
                            }
                            await this.loadData();
                        }
                    } catch (e) {
                        console.error('Error removing market:', e);
                        alert('Error removing market');
                    }
                },
                async searchMarkets() {
                    try {
                        const query = encodeURIComponent(this.searchQuery);
                        const res = await fetch(`/api/search_markets?query=${query}`);
                        const data = await res.json();
                        this.searchResults = data.markets || [];
                    } catch (e) {
                        console.error('Error searching markets:', e);
                    }
                },
                formatNumber(num, decimals = 0, sign = false) {
                    if (num === null || num === undefined) return '-';
                    const formatted = num.toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
                    return sign && num > 0 ? '+' + formatted : formatted;
                },
                formatPercent(val) {
                    if (val === null || val === undefined) return '-';
                    return (val * 100).toFixed(1) + '%';
                },
                formatLastMessageTime(seconds) {
                    if (seconds === null || seconds === undefined || seconds < 0) return 'Never';
                    if (seconds < 1) return 'Just now';
                    if (seconds < 60) return Math.floor(seconds) + 's ago';
                    const mins = Math.floor(seconds / 60);
                    if (mins < 60) return mins + 'm ago';
                    const hours = Math.floor(mins / 60);
                    return hours + 'h ago';
                },
                formatTime(seconds) {
                    if (!seconds || seconds < 0) return '0s';
                    const mins = Math.floor(seconds / 60);
                    const secs = Math.floor(seconds % 60);
                    return `${mins}m ${secs}s`;
                },
                formatTimestamp(ts) {
                    return new Date(ts * 1000).toLocaleTimeString();
                },
                getEventColor(type) {
                    const colors = {
                        'trade': 'text-green-400',
                        'signal': 'text-yellow-400',
                        'error': 'text-red-400'
                    };
                    return colors[type] || 'text-gray-400';
                },
                formatEventData(event) {
                    if (event.type === 'trade') {
                        const d = event.data;
                        return `${d.action} ${d.side} x${d.size} @ ${d.price?.toFixed(3)}`;
                    } else if (event.type === 'signal') {
                        const d = event.data;
                        return `${d.action} - ${d.reason}`;
                    }
                    return JSON.stringify(event.data).substring(0, 50);
                }
            }
        }).mount('#app');
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
