"""
멀티 레벨 스캘핑 전략
특정 가격 레벨에서 진입하고 5% 익절 반복
"""
from dataclasses import dataclass
from typing import Optional, List
from loguru import logger
from scalping_strategy import ScalpSignal, MarketContext
from btc_price_tracker import BTCPriceTracker
import time


@dataclass
class LevelPosition:
    """레벨별 포지션"""
    level_price: float  # 진입 레벨 (0.34, 0.24, 0.12)
    side: str  # "YES" or "NO"
    entry_price: float  # 실제 진입 가격
    size: float  # 포지션 크기
    entry_time: float  # 진입 시간
    is_high_price_scalp: bool = False  # 하이 프라이스 스캘핑 여부
    profit_target: float = 0.05  # 수익 목표 (기본 5%, 하이 프라이스는 2%)

    def get_target_exit_price(self) -> float:
        """목표 청산 가격 계산 (진입가 대비 profit_target% 이익)"""
        # Polymarket: PnL = size * (1 - entry_price - exit_price)
        # profit_target% 이익: profit_target * cost = profit_target * (size * entry_price)
        # size * (1 - entry_price - exit_price) = profit_target * size * entry_price
        # 1 - entry_price - exit_price = profit_target * entry_price
        # exit_price = 1 - entry_price - profit_target * entry_price
        # exit_price = 1 - (1 + profit_target) * entry_price
        target_exit = 1.0 - (1.0 + self.profit_target) * self.entry_price
        return max(0.01, target_exit)  # 최소 0.01


class MultiLevelScalpingStrategy:
    """
    멀티 레벨 스캘핑 전략

    레벨:
    - Level 1: 0.34c 터치 → 매수 → +5% 익절
    - Level 2: 0.24c 터치 → 매수 → +5% 익절
    - Level 3: 0.12c 터치 → 매수 → +5% 익절

    각 레벨은 독립적으로 진입/청산 반복 가능
    """

    def __init__(self, price_tracker: BTCPriceTracker, max_trades_per_market: int = 1):
        self.tracker = price_tracker

        # 진입 레벨 (높은 순서대로)
        self.entry_levels = [0.34, 0.24, 0.14]
        self.level_sizes = [10.0, 10.0, 10.0]  # 각 레벨당 shares (모두 10으로 통일)

        self.min_order_value = 5.0  # Polymarket 최소 주문 금액 ($5)
        self.take_profit_pct = 0.05  # 5% 익절

        # High price scalping 설정
        self.enable_high_price_scalping = True
        self.high_price_threshold = 0.85  # 85c 이상
        self.high_price_scalp_size = 5.0  # 5 shares
        self.high_price_profit_pct = 0.02  # 2% 익절

        # 한 마켓당 최대 거래 횟수 (기본 3회)
        self.max_trades_per_market = 3 if max_trades_per_market == 1 else max_trades_per_market

        # High price scalping 최대 횟수
        self.max_high_scalp_count = 4

        # 각 마켓의 활성 포지션들 (레벨별로 여러 개 가능)
        self.positions: dict[str, List[LevelPosition]] = {}

        # 각 레벨에서 마지막 진입 시간 (재진입 방지용)
        self.last_entry_time: dict[str, dict[float, float]] = {}

        # 마켓별 거래 횟수 추적
        self.trade_count: dict[str, int] = {}

        # 마켓별 high price scalping 횟수 추적
        self.high_scalp_count: dict[str, int] = {}

        # TP limit order 추적용 (봇이 limit order 체결 확인하기 전까지 필요)
        self.active_exit_orders: dict[str, List[str]] = {}
        self.last_tp_limit_price: dict[str, tuple[str, float]] = {}

        # EXIT 시그널 중복 방지용 (마지막 EXIT 시그널 시간)
        self.last_exit_signal_time: dict[str, float] = {}

    def calculate_order_size(self, level_index: int) -> float:
        """레벨별 주문 크기 반환"""
        if 0 <= level_index < len(self.level_sizes):
            return self.level_sizes[level_index]
        return 10.0  # 기본값

    def on_order_filled(self, market_id: str, side: str, price: float, size: float, level: float, metadata: dict = None):
        """주문 체결 콜백 - 실제로 체결된 후에만 포지션 추가"""
        if market_id not in self.positions:
            self.positions[market_id] = []

        # 메타데이터에서 하이 프라이스 스캘핑 정보 추출
        is_high_price = metadata.get('is_high_price_scalp', False) if metadata else False
        profit_target = metadata.get('profit_target', self.take_profit_pct) if metadata else self.take_profit_pct

        # **중요: LEVEL 진입(10 shares)이 잘못 체결되는 것을 감지**
        # HIGH SCALP은 5 shares, LEVEL은 10 shares
        if not is_high_price and size >= 10:
            logger.warning(f"⚠️  LEVEL entry filled: {side} {size} @ {price:.3f} - This should not happen if <5min remaining!")

        position = LevelPosition(
            level_price=level,
            side=side,
            entry_price=price,
            size=size,
            entry_time=time.time(),
            is_high_price_scalp=is_high_price,
            profit_target=profit_target
        )
        self.positions[market_id].append(position)

        scalp_type = "HIGH PRICE SCALP" if is_high_price else "LEVEL"
        total_positions = len(self.positions[market_id])

        # **중요: High scalp 체결 시 카운터 증가** (주문 발행이 아닌 체결 시점)
        if is_high_price:
            if market_id not in self.high_scalp_count:
                self.high_scalp_count[market_id] = 0
            self.high_scalp_count[market_id] += 1
            logger.info(f"Position confirmed [{scalp_type}]: {side} {size} @ {price:.3f} (target {profit_target*100:.0f}%) | High scalp #{self.high_scalp_count[market_id]}/{self.max_high_scalp_count} | Total positions: {total_positions}")
        else:
            logger.info(f"Position confirmed [{scalp_type}]: {side} {size} @ {price:.3f} (target {profit_target*100:.0f}%) | Total positions: {total_positions}")

        # TP limit order는 _check_exit()에서 조건 만족 시에만 발행


    def on_order_failed(self, market_id: str, side: str, level: float):  # noqa: ARG002
        """주문 실패 콜백 - 재시도 방지"""
        # 주문 실패해도 쿨다운 유지 (과도한 재시도 방지)
        logger.warning(f"Order failed: {side} @ level {level:.2f} - waiting for cooldown")

    def on_exit_filled(self, market_id: str, side: str, is_high_price_scalp: bool = False):
        """청산 체결 콜백 - 포지션 제거 및 거래 횟수 증가"""
        # 해당 side의 모든 포지션 제거
        if market_id in self.positions:
            positions = self.positions[market_id]
            removed_positions = [p for p in positions if p.side == side]
            self.positions[market_id] = [p for p in positions if p.side != side]
            logger.info(f"✓ Removed {len(removed_positions)} {side} positions from {market_id}")

        # active_exit_orders 클리어
        if market_id in self.active_exit_orders:
            self.active_exit_orders[market_id] = []

        # last_tp_limit_price 클리어 (새로운 진입을 위해)
        if market_id in self.last_tp_limit_price:
            del self.last_tp_limit_price[market_id]

        # EXIT 시그널 타이머 초기화 (새로운 진입을 위해)
        if market_id in self.last_exit_signal_time:
            del self.last_exit_signal_time[market_id]

        # **중요 수정: LEVEL 포지션이 모두 청산되었을 때만 사이클 증가**
        # (부분 청산이 아니라 완전 청산일 때만)
        if not is_high_price_scalp:
            # 남은 LEVEL 포지션 확인
            remaining_positions = self.positions.get(market_id, [])
            level_positions = [p for p in remaining_positions if not p.is_high_price_scalp]

            # LEVEL 포지션이 하나도 없으면 사이클 완료
            if len(level_positions) == 0:
                if market_id not in self.trade_count:
                    self.trade_count[market_id] = 0
                self.trade_count[market_id] += 1
                logger.info(f"✓✓✓ CYCLE COMPLETED: Trade #{self.trade_count[market_id]}/{self.max_trades_per_market}")
            else:
                logger.info(f"Partial exit: {len(level_positions)} LEVEL positions still remaining (cycle not complete)")

        positions = self.positions.get(market_id, [])

        if is_high_price_scalp:
            logger.info(f"Exit confirmed (HIGH SCALP): {side} - {len(positions)} positions remaining")
        else:
            logger.info(f"Exit confirmed (LEVEL): {side} - {len(positions)} positions remaining")

    def evaluate_market(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """마켓 평가 및 신호 생성"""
        market_id = ctx.market_id

        # 초기화
        if market_id not in self.positions:
            self.positions[market_id] = []
        if market_id not in self.last_entry_time:
            self.last_entry_time[market_id] = {}

        # 0. 긴급 청산 확인
        time_remaining = ctx.end_time - time.time()

        # 5분 이하: 즉시 강제 청산 (MARKET order), 그 다음 high scalping
        if time_remaining <= 300:  # 5분
            positions = self.positions.get(market_id, [])
            logger.warning(f"⏰⏰⏰ <5MIN TRIGGER: {time_remaining:.0f}s remaining - Total positions: {len(positions)}")

            # 포지션 상세 로그
            for i, p in enumerate(positions):
                logger.info(f"  Position #{i+1}: {p.side} x{p.size} @ {p.entry_price:.3f} (high_scalp={p.is_high_price_scalp})")

            # **중요: 5분 이하이면 무조건 MARKET order로 즉시 청산**
            # TP 조건 체크 없이 모든 포지션을 강제 청산
            if positions:
                logger.warning(f"🚨 <5MIN: Force unwinding ALL positions (no TP check, MARKET order only)")
                force_exit = self._force_unwind(ctx)  # 모든 포지션 MARKET order로 즉시 청산
                if force_exit:
                    logger.warning(f"✅ _force_unwind returned EXIT signal: {force_exit.reason}")
                    return force_exit

            # 포지션이 없으면 high price scalping 진입 체크 (일반 진입은 안 함)
            logger.warning(f"✓ No positions - checking high price scalping entry (<5min)")
            high_price_signal = self._check_high_price_scalping(ctx)
            if high_price_signal:
                logger.warning(f"🎯 HIGH PRICE SCALP ENTRY (<5min): {high_price_signal.reason}")
                return high_price_signal

            return None

        # 1. 청산 신호 확인 (진입보다 우선)
        exit_signal = self._check_exit(ctx)
        if exit_signal:
            return exit_signal

        # 2. 진입 신호 확인
        entry_signal = self._check_entry(ctx)
        if entry_signal:
            return entry_signal

        return None

    def _check_entry(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """진입 신호 확인 - 레벨별로 한 번씩만 진입 (10 shares)"""
        market_id = ctx.market_id
        now = time.time()

        logger.info(f"🔍 _check_entry called for {market_id[:8]}... YES={ctx.yes_price:.3f} NO={ctx.no_price:.3f}")

        # **변경: 포지션이 있어도 다른 레벨은 진입 가능**
        # 단, 거래 횟수 제한은 유지

        # **중요: 마켓별 거래 횟수 제한 체크**
        if market_id not in self.trade_count:
            self.trade_count[market_id] = 0

        if self.trade_count[market_id] >= self.max_trades_per_market:
            logger.info(f"   ❌ Blocked: trade_count={self.trade_count[market_id]} >= max={self.max_trades_per_market}")
            return None

        # 리스크 관리: 진입 금지 조건
        time_remaining = ctx.end_time - now

        # **중요: 5분 미만 남으면 LEVEL 진입 절대 금지**
        # (5분 미만에는 high price scalping만 허용)
        if time_remaining < 300:  # 5분 = 300초
            logger.info(f"   ❌ Blocked: <5min remaining ({time_remaining:.0f}s)")
            return None

        # 1. 7분 미만 남으면 신규 진입 금지 (unwinding만 허용)
        if time_remaining < 420:  # 7분 = 420초
            logger.info(f"   ❌ Blocked: <7min remaining ({time_remaining:.0f}s)")
            return None

        # **중요: TP limit order가 활성화되어 있으면 진입 금지 (체결 대기 중)**
        has_active_exit_orders = market_id in self.active_exit_orders and len(self.active_exit_orders[market_id]) > 0
        if has_active_exit_orders:
            logger.info(f"   ❌ Blocked: has_active_exit_orders (count={len(self.active_exit_orders.get(market_id, []))})")
            # TP limit order 체결 대기 중이면 새로운 진입 하지 않음
            return None

        # **포지션이 있어도 다른 레벨에서는 진입 가능** (주석과 일치하도록 수정)

        # YES 체크 - 레벨을 하향 돌파할 때마다 진입 (34¢ 미만, 24¢ 미만, 14¢ 미만)
        # **수정: 현재 가격이 여러 레벨 미만일 때, 가장 낮은 레벨에서만 진입**
        # 1단계: 현재 가격보다 높은 레벨들 중 아직 진입하지 않은 가장 낮은 레벨 찾기
        lowest_unentered_level = None
        lowest_unentered_index = None

        for i in reversed(range(len(self.entry_levels))):  # 낮은 레벨부터 체크
            level = self.entry_levels[i]

            # 현재 가격이 레벨 미만일 때 (하향 돌파)
            if ctx.yes_price < level:
                # 이 레벨에서 이미 진입했는지 확인
                last_time = self.last_entry_time[market_id].get(('YES', level), 0)
                if last_time == 0:
                    # 아직 진입하지 않은 레벨 발견
                    lowest_unentered_level = level
                    lowest_unentered_index = i
                    break  # 가장 낮은 레벨을 찾았으므로 중단

        # 2단계: 찾은 레벨에서 진입
        if lowest_unentered_level is not None:
            # 진입 신호 생성 (포지션은 주문 체결 후 추가)
            self.last_entry_time[market_id][('YES', lowest_unentered_level)] = now
            i = lowest_unentered_index
            level = lowest_unentered_level

            # 레벨별 shares
            order_size = self.calculate_order_size(i)
            order_value = order_size * ctx.yes_price

            logger.info(f"Entry signal: YES @ {ctx.yes_price:.3f} (below {level:.2f} level) - Size: {order_size} shares (${order_value:.2f})")

            return ScalpSignal(
                action="ENTER_YES",
                token_id=ctx.token_yes,
                price=ctx.yes_price,
                size=order_size,
                confidence=1.0,
                edge=0.0,
                reason=f"YES @ {ctx.yes_price:.3f} (below {level:.2f}) - Target +{self.take_profit_pct*100:.0f}%",
                urgency="MEDIUM",
                # 메타데이터로 레벨 정보 및 토큰 ID 전달
                metadata={"side": "YES", "level": level, "token_id": ctx.token_yes, "token_yes": ctx.token_yes, "token_no": ctx.token_no}
            )

        # NO 체크 - 레벨을 하향 돌파할 때마다 진입 (34¢ 미만, 24¢ 미만, 14¢ 미만)
        # **수정: 현재 가격이 여러 레벨 미만일 때, 가장 낮은 레벨에서만 진입**
        # 1단계: 현재 가격보다 높은 레벨들 중 아직 진입하지 않은 가장 낮은 레벨 찾기
        lowest_unentered_level = None
        lowest_unentered_index = None

        for i in reversed(range(len(self.entry_levels))):  # 낮은 레벨부터 체크
            level = self.entry_levels[i]

            # 현재 가격이 레벨 미만일 때 (하향 돌파)
            if ctx.no_price < level:
                # 이 레벨에서 이미 진입했는지 확인
                last_time = self.last_entry_time[market_id].get(('NO', level), 0)
                if last_time == 0:
                    # 아직 진입하지 않은 레벨 발견
                    lowest_unentered_level = level
                    lowest_unentered_index = i
                    break  # 가장 낮은 레벨을 찾았으므로 중단

        # 2단계: 찾은 레벨에서 진입
        if lowest_unentered_level is not None:
            # 진입 신호 생성 (포지션은 주문 체결 후 추가)
            self.last_entry_time[market_id][('NO', lowest_unentered_level)] = now
            i = lowest_unentered_index
            level = lowest_unentered_level

            # 레벨별 shares
            order_size = self.calculate_order_size(i)
            order_value = order_size * ctx.no_price

            logger.info(f"Entry signal: NO @ {ctx.no_price:.3f} (below {level:.2f} level) - Size: {order_size} shares (${order_value:.2f})")

            return ScalpSignal(
                action="ENTER_NO",
                token_id=ctx.token_no,
                price=ctx.no_price,
                size=order_size,
                confidence=1.0,
                edge=0.0,
                reason=f"NO @ {ctx.no_price:.3f} (below {level:.2f}) - Target +{self.take_profit_pct*100:.0f}%",
                urgency="MEDIUM",
                # 메타데이터로 레벨 정보 및 토큰 ID 전달
                metadata={"side": "NO", "level": level, "token_id": ctx.token_no, "token_yes": ctx.token_yes, "token_no": ctx.token_no}
            )

        return None

    def _check_high_price_scalping(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """
        하이 프라이스 스캘핑 전략
        5분 미만 남았을 때, 한쪽이 90¢ 이상이면 그 쪽을 매수 (승리 확률 높은 쪽)

        YES ≥90¢ → YES 매수
        NO ≥90¢ → NO 매수

        최대 4번까지 반복 가능
        """
        # High price scalping 비활성화면 스킵
        if not self.enable_high_price_scalping:
            return None

        market_id = ctx.market_id
        now = time.time()
        time_remaining = ctx.end_time - now

        # 5분 미만만 허용
        if time_remaining >= 300:
            return None

        # **중요: HIGH SCALP 포지션이 이미 있으면 진입 금지**
        # (LEVEL 포지션은 상관없음 - 강제 청산 대상)
        existing_positions = self.positions.get(market_id, [])
        high_scalp_positions = [p for p in existing_positions if p.is_high_price_scalp]
        has_active_exit_orders = market_id in self.active_exit_orders and len(self.active_exit_orders[market_id]) > 0

        if len(high_scalp_positions) > 0 or has_active_exit_orders:
            logger.debug(f"_check_high_price_scalping: Blocked (high_scalp_positions={len(high_scalp_positions)}, active_exit_orders={has_active_exit_orders})")
            return None

        # High price scalping 횟수 체크 (최대 4번)
        if market_id not in self.high_scalp_count:
            self.high_scalp_count[market_id] = 0

        if self.high_scalp_count[market_id] >= self.max_high_scalp_count:
            return None

        # YES가 threshold(90¢) 이상일 때 → YES를 매수 (승리 확률 높은 쪽)
        if ctx.yes_price >= self.high_price_threshold:
            # 설정된 shares
            order_size = self.high_price_scalp_size
            order_value = order_size * ctx.yes_price

            # **중요: 횟수는 체결 시점(on_order_filled)에서 증가**
            # 여기서는 증가하지 않음 (주문 실패 시 카운터만 증가하는 문제 방지)
            current_count = self.high_scalp_count[market_id] + 1  # 예상 카운트 (로그용)

            logger.info(f"HIGH PRICE SCALP #{current_count}/{self.max_high_scalp_count}: YES @ {ctx.yes_price:.3f} (마감 {time_remaining:.0f}s, NO={ctx.no_price:.3f}) - Size: {order_size} shares (${order_value:.2f})")

            return ScalpSignal(
                action="ENTER_YES",
                token_id=ctx.token_yes,
                price=ctx.yes_price,
                size=order_size,
                confidence=0.95,  # 90¢+ 이면 승리 확률 매우 높음
                edge=self.high_price_profit_pct,
                reason=f"High price scalp #{current_count}/{self.max_high_scalp_count}: YES @ {ctx.yes_price:.3f} (마감 {time_remaining:.0f}s, target +{self.high_price_profit_pct*100:.0f}%)",
                urgency="HIGH",
                metadata={"side": "YES", "level": ctx.yes_price, "is_high_price_scalp": True, "profit_target": self.high_price_profit_pct, "token_id": ctx.token_yes, "token_yes": ctx.token_yes, "token_no": ctx.token_no}
            )

        # NO가 threshold(90¢) 이상일 때 → NO를 매수 (승리 확률 높은 쪽)
        elif ctx.no_price >= self.high_price_threshold:
            # 설정된 shares
            order_size = self.high_price_scalp_size
            order_value = order_size * ctx.no_price

            # **중요: 횟수는 체결 시점(on_order_filled)에서 증가**
            # 여기서는 증가하지 않음 (주문 실패 시 카운터만 증가하는 문제 방지)
            current_count = self.high_scalp_count[market_id] + 1  # 예상 카운트 (로그용)

            logger.info(f"HIGH PRICE SCALP #{current_count}/{self.max_high_scalp_count}: NO @ {ctx.no_price:.3f} (마감 {time_remaining:.0f}s, YES={ctx.yes_price:.3f}) - Size: {order_size} shares (${order_value:.2f})")

            return ScalpSignal(
                action="ENTER_NO",
                token_id=ctx.token_no,
                price=ctx.no_price,
                size=order_size,
                confidence=0.95,  # 90¢+ 이면 승리 확률 매우 높음
                edge=self.high_price_profit_pct,
                reason=f"High price scalp #{current_count}/{self.max_high_scalp_count}: NO @ {ctx.no_price:.3f} (마감 {time_remaining:.0f}s, target +{self.high_price_profit_pct*100:.0f}%)",
                urgency="HIGH",
                metadata={"side": "NO", "level": ctx.no_price, "is_high_price_scalp": True, "profit_target": self.high_price_profit_pct, "token_id": ctx.token_no, "token_yes": ctx.token_yes, "token_no": ctx.token_no}
            )

        return None

    def _record_exit_signal(self, market_id: str, signal: ScalpSignal) -> ScalpSignal:
        """EXIT 시그널 시간 기록 (중복 방지용)"""
        self.last_exit_signal_time[market_id] = time.time()
        return signal

    def _check_exit(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """청산 신호 확인 - TP 조건 만족 시 limit order 발행 (가격 개선 시 업데이트)"""
        market_id = ctx.market_id
        positions = self.positions.get(market_id, [])
        time_remaining = ctx.end_time - time.time()

        if not positions:
            return None

        # **중복 EXIT 시그널 방지**: 1초 이내에 같은 마켓의 EXIT 시그널은 한 번만
        now = time.time()
        last_exit_time = self.last_exit_signal_time.get(market_id, 0)
        if now - last_exit_time < 1.0:
            logger.debug(f"_check_exit: Skipping duplicate EXIT signal (last signal {now - last_exit_time:.2f}s ago)")
            return None

        logger.debug(f"_check_exit: {len(positions)} positions, time_remaining={time_remaining:.0f}s")

        # **변경: TP limit order가 이미 있어도 가격이 더 좋아지면 새로운 주문 발행**
        # (봇에서 기존 주문을 취소하고 새 주문을 넣을 것으로 예상)

        # 모든 포지션을 합산 (같은 side끼리)
        yes_positions = [p for p in positions if p.side == "YES"]
        no_positions = [p for p in positions if p.side == "NO"]

        # YES 포지션 청산 체크
        if yes_positions:
            # 평균가 계산
            total_yes_size = sum(p.size for p in yes_positions)
            total_yes_cost = sum(p.size * p.entry_price for p in yes_positions)
            avg_yes_entry = total_yes_cost / total_yes_size if total_yes_size > 0 else 0

            # High price scalp인지 확인 (하나라도 있으면)
            is_high_price_scalp = any(p.is_high_price_scalp for p in yes_positions)

            # **디버그: 포지션 상세 출력**
            for i, p in enumerate(yes_positions):
                logger.debug(f"  YES pos #{i+1}: {p.size} @ {p.entry_price:.3f} (high_scalp={p.is_high_price_scalp})")

            logger.debug(f"YES positions: {len(yes_positions)}, total_size={total_yes_size}, avg_entry={avg_yes_entry:.3f}, is_high_scalp={is_high_price_scalp}")

            # 청산 가격
            if is_high_price_scalp:
                # High price scalp은 Market order로 즉시 청산 (NO 매수)
                current_exit_price = ctx.no_price
                profit_target = self.high_price_profit_pct

                # Target exit price: 진입가 대비 profit_target% 이익
                # PnL = size * (1 - entry - exit) = profit_target * size * entry
                # exit = 1 - entry - profit_target * entry = 1 - (1 + profit_target) * entry
                target_exit = 1.0 - (1.0 + profit_target) * avg_yes_entry

                if current_exit_price <= target_exit:
                    pnl = total_yes_size * (1.0 - avg_yes_entry - current_exit_price)
                    pnl_pct = (pnl / total_yes_cost) if total_yes_cost > 0 else 0

                    logger.info(f"TP condition met (HIGH PRICE SCALP): BUY NO x{total_yes_size} @ {current_exit_price:.3f} (unwinding YES @ {avg_yes_entry:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")

                    # **중요: 포지션은 봇의 on_exit_filled()에서 제거** (주문 체결 후)
                    # (즉시 제거하면 주문 실패 시 데이터 불일치 발생)
                    return self._record_exit_signal(market_id, ScalpSignal(
                        action="EXIT",  # Market order - 즉시 청산
                        token_id=ctx.token_no,
                        price=current_exit_price,
                        size=total_yes_size,
                        confidence=1.0,
                        edge=0.0,
                        reason=f"HIGH SCALP EXIT: BUY NO @ {current_exit_price:.3f} (target {pnl_pct:+.1%})",
                        urgency="HIGH",
                        metadata={"side": "YES", "is_high_price_scalp": True, "fallback_sell_price": ctx.yes_price, "fallback_token": ctx.token_yes}
                    ))
            else:
                # 일반 포지션 → Unwinding으로 청산
                current_exit_price = ctx.no_price
                profit_target = self.take_profit_pct

                # 5분 이하 남았으면 2%로 낮춤
                if time_remaining <= 300:
                    profit_target = 0.02

                # Target exit price 계산
                target_exit = 1.0 - (1.0 + profit_target) * avg_yes_entry

                # **상세 로그: TP 조건 체크**
                logger.info(f"💰 YES TP check: current_exit={current_exit_price:.3f}, target_exit={target_exit:.3f}, profit_target={profit_target*100:.1f}%")
                logger.info(f"   Avg entry: {avg_yes_entry:.3f}, Total size: {total_yes_size}, Positions: {len(yes_positions)}")
                if current_exit_price <= target_exit:
                    logger.info(f"   ✅ TP CONDITION MET! (current {current_exit_price:.3f} <= target {target_exit:.3f})")
                else:
                    logger.info(f"   ❌ TP not met yet (current {current_exit_price:.3f} > target {target_exit:.3f}, need NO to drop more)")

                if current_exit_price <= target_exit:
                    pnl = total_yes_size * (1.0 - avg_yes_entry - current_exit_price)
                    pnl_pct = (pnl / total_yes_cost) if total_yes_cost > 0 else 0

                    logger.info(f"TP condition met: BUY NO x{total_yes_size} @ {current_exit_price:.3f} (unwinding YES avg @ {avg_yes_entry:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")

                    # 5분 이하면 MARKET order, 5분 초과면 LIMIT order
                    if time_remaining <= 300:
                        # **중요: 포지션은 봇의 on_exit_filled()에서 제거** (주문 체결 후)
                        # (즉시 제거하면 주문 실패 시 데이터 불일치 발생)
                        return self._record_exit_signal(market_id, ScalpSignal(
                            action="EXIT",
                            token_id=ctx.token_no,
                            price=current_exit_price,
                            size=total_yes_size,
                            confidence=1.0,
                            edge=0.0,
                            reason=f"TP EXIT (<5min): BUY NO @ {current_exit_price:.3f} (target {pnl_pct:+.1%})",
                            urgency="HIGH",
                            metadata={"side": "YES", "fallback_sell_price": ctx.yes_price, "fallback_token": ctx.token_yes}
                        ))
                    else:
                        # LIMIT order 발행 (5분 이상)
                        return self._record_exit_signal(market_id, ScalpSignal(
                            action="PLACE_TP_LIMIT",
                            token_id=ctx.token_no,
                            price=current_exit_price,
                            size=total_yes_size,
                            confidence=1.0,
                            edge=0.0,
                            reason=f"Place TP limit: BUY NO @ {current_exit_price:.3f} (target {pnl_pct:+.1%})",
                            urgency="HIGH",
                            metadata={
                                "side": "YES",
                                "order_type": "BUY",
                                "token_yes": ctx.token_yes,
                                "token_no": ctx.token_no
                            }
                        ))

        # NO 포지션 청산 체크
        if no_positions:
            # 평균가 계산
            total_no_size = sum(p.size for p in no_positions)
            total_no_cost = sum(p.size * p.entry_price for p in no_positions)
            avg_no_entry = total_no_cost / total_no_size if total_no_size > 0 else 0

            # High price scalp인지 확인
            is_high_price_scalp = any(p.is_high_price_scalp for p in no_positions)

            # **디버그: 포지션 상세 출력**
            for i, p in enumerate(no_positions):
                logger.debug(f"  NO pos #{i+1}: {p.size} @ {p.entry_price:.3f} (high_scalp={p.is_high_price_scalp})")

            logger.debug(f"NO positions: {len(no_positions)}, total_size={total_no_size}, avg_entry={avg_no_entry:.3f}, is_high_scalp={is_high_price_scalp}")

            # 청산 가격
            if is_high_price_scalp:
                # High price scalp은 Market order로 즉시 청산 (YES 매수)
                current_exit_price = ctx.yes_price
                profit_target = self.high_price_profit_pct

                # Target exit price: 진입가 대비 profit_target% 이익
                # PnL = size * (1 - entry - exit) = profit_target * size * entry
                # exit = 1 - entry - profit_target * entry = 1 - (1 + profit_target) * entry
                target_exit = 1.0 - (1.0 + profit_target) * avg_no_entry

                if current_exit_price <= target_exit:
                    pnl = total_no_size * (1.0 - avg_no_entry - current_exit_price)
                    pnl_pct = (pnl / total_no_cost) if total_no_cost > 0 else 0

                    logger.info(f"TP condition met (HIGH PRICE SCALP): BUY YES x{total_no_size} @ {current_exit_price:.3f} (unwinding NO @ {avg_no_entry:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")

                    # **중요: 포지션은 봇의 on_exit_filled()에서 제거** (주문 체결 후)
                    # (즉시 제거하면 주문 실패 시 데이터 불일치 발생)
                    return self._record_exit_signal(market_id, ScalpSignal(
                        action="EXIT",  # Market order - 즉시 청산
                        token_id=ctx.token_yes,
                        price=current_exit_price,
                        size=total_no_size,
                        confidence=1.0,
                        edge=0.0,
                        reason=f"HIGH SCALP EXIT: BUY YES @ {current_exit_price:.3f} (target {pnl_pct:+.1%})",
                        urgency="HIGH",
                        metadata={"side": "NO", "is_high_price_scalp": True, "fallback_sell_price": ctx.no_price, "fallback_token": ctx.token_no}
                    ))
            else:
                # 일반 포지션 → Unwinding으로 청산
                current_exit_price = ctx.yes_price
                profit_target = self.take_profit_pct

                # 5분 이하 남았으면 2%로 낮춤
                if time_remaining <= 300:
                    profit_target = 0.02

                # Target exit price 계산
                target_exit = 1.0 - (1.0 + profit_target) * avg_no_entry

                # **상세 로그: TP 조건 체크**
                logger.info(f"💰 NO TP check: current_exit={current_exit_price:.3f}, target_exit={target_exit:.3f}, profit_target={profit_target*100:.1f}%")
                logger.info(f"   Avg entry: {avg_no_entry:.3f}, Total size: {total_no_size}, Positions: {len(no_positions)}")
                if current_exit_price <= target_exit:
                    logger.info(f"   ✅ TP CONDITION MET! (current {current_exit_price:.3f} <= target {target_exit:.3f})")
                else:
                    logger.info(f"   ❌ TP not met yet (current {current_exit_price:.3f} > target {target_exit:.3f}, need YES to drop more)")

                if current_exit_price <= target_exit:
                    pnl = total_no_size * (1.0 - avg_no_entry - current_exit_price)
                    pnl_pct = (pnl / total_no_cost) if total_no_cost > 0 else 0

                    logger.info(f"TP condition met: BUY YES x{total_no_size} @ {current_exit_price:.3f} (unwinding NO avg @ {avg_no_entry:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")

                    # 5분 이하면 MARKET order, 5분 초과면 LIMIT order
                    if time_remaining <= 300:
                        # **중요: 포지션은 봇의 on_exit_filled()에서 제거** (주문 체결 후)
                        # (즉시 제거하면 주문 실패 시 데이터 불일치 발생)
                        return self._record_exit_signal(market_id, ScalpSignal(
                            action="EXIT",
                            token_id=ctx.token_yes,
                            price=current_exit_price,
                            size=total_no_size,
                            confidence=1.0,
                            edge=0.0,
                            reason=f"TP EXIT (<5min): BUY YES @ {current_exit_price:.3f} (target {pnl_pct:+.1%})",
                            urgency="HIGH",
                            metadata={"side": "NO", "fallback_sell_price": ctx.no_price, "fallback_token": ctx.token_no}
                        ))
                    else:
                        # LIMIT order 발행 (5분 이상)
                        return self._record_exit_signal(market_id, ScalpSignal(
                            action="PLACE_TP_LIMIT",
                            token_id=ctx.token_yes,
                            price=current_exit_price,
                            size=total_no_size,
                            confidence=1.0,
                            edge=0.0,
                            reason=f"Place TP limit: BUY YES @ {current_exit_price:.3f} (target {pnl_pct:+.1%})",
                            urgency="HIGH",
                            metadata={
                                "side": "NO",
                                "order_type": "BUY",
                                "token_yes": ctx.token_yes,
                                "token_no": ctx.token_no
                            }
                        ))

        return None

    def _force_unwind(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """
        긴급 청산 - 5분 미만 남았을 때 **LEVEL 포지션만** 강제 청산
        항상 MARKET order 사용 (체결 보장)

        **중요: HIGH SCALP 포지션은 청산하지 않음** (자체 TP 로직 사용)

        모든 LEVEL 포지션을 합산해서 평균가 계산 후, 반대 토큰으로 한 번에 unwinding
        """
        market_id = ctx.market_id
        positions = self.positions.get(market_id, [])

        logger.warning(f"🔍 _force_unwind called: market_id={market_id[:8]}, positions in dict={len(positions)}")
        logger.warning(f"   ctx.position_yes={ctx.position_yes}, ctx.position_no={ctx.position_no}")

        time_remaining = ctx.end_time - time.time()

        # **중요: self.positions가 비어있어도 ctx에 포지션이 있으면 청산**
        # (수동 진입하거나 봇이 추적하지 못한 포지션 대응)
        if not positions:
            logger.warning(f"⚠️ _force_unwind: No positions in self.positions[{market_id[:8]}], but checking ctx...")

            # ctx에서 포지션 확인 (수동 진입 대응)
            if ctx.position_yes > 0 and ctx.position_no > 0:
                logger.warning(f"⚠️ Both YES ({ctx.position_yes}) and NO ({ctx.position_no}) in ctx - unwinding larger position")
                if ctx.position_yes >= ctx.position_no:
                    # YES 포지션 청산
                    exit_price = ctx.no_price
                    pnl = ctx.position_yes * (1.0 - ctx.avg_price_yes - exit_price)
                    pnl_pct = (pnl / (ctx.position_yes * ctx.avg_price_yes)) if ctx.avg_price_yes > 0 else 0
                    logger.warning(f"FORCE UNWIND (from ctx): BUY NO x{ctx.position_yes} @ {exit_price:.3f} (unwinding YES @ {ctx.avg_price_yes:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")
                    return ScalpSignal(
                        action="EXIT",
                        token_id=ctx.token_no,
                        price=exit_price,
                        size=ctx.position_yes,
                        confidence=1.0,
                        edge=0.0,
                        reason=f"⚠️ FORCE UNWIND (ctx, {time_remaining:.0f}s): BUY NO @ {exit_price:.3f}",
                        urgency="CRITICAL",
                        metadata={"side": "YES", "fallback_sell_price": ctx.yes_price, "fallback_token": ctx.token_yes}
                    )
                else:
                    # NO 포지션 청산
                    exit_price = ctx.yes_price
                    pnl = ctx.position_no * (1.0 - ctx.avg_price_no - exit_price)
                    pnl_pct = (pnl / (ctx.position_no * ctx.avg_price_no)) if ctx.avg_price_no > 0 else 0
                    logger.warning(f"FORCE UNWIND (from ctx): BUY YES x{ctx.position_no} @ {exit_price:.3f} (unwinding NO @ {ctx.avg_price_no:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")
                    return ScalpSignal(
                        action="EXIT",
                        token_id=ctx.token_yes,
                        price=exit_price,
                        size=ctx.position_no,
                        confidence=1.0,
                        edge=0.0,
                        reason=f"⚠️ FORCE UNWIND (ctx, {time_remaining:.0f}s): BUY YES @ {exit_price:.3f}",
                        urgency="CRITICAL",
                        metadata={"side": "NO", "fallback_sell_price": ctx.no_price, "fallback_token": ctx.token_no}
                    )
            elif ctx.position_yes > 0:
                # YES만 있음
                exit_price = ctx.no_price
                pnl = ctx.position_yes * (1.0 - ctx.avg_price_yes - exit_price)
                pnl_pct = (pnl / (ctx.position_yes * ctx.avg_price_yes)) if ctx.avg_price_yes > 0 else 0
                logger.warning(f"FORCE UNWIND (from ctx): BUY NO x{ctx.position_yes} @ {exit_price:.3f} (unwinding YES @ {ctx.avg_price_yes:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")
                return ScalpSignal(
                    action="EXIT",
                    token_id=ctx.token_no,
                    price=exit_price,
                    size=ctx.position_yes,
                    confidence=1.0,
                    edge=0.0,
                    reason=f"⚠️ FORCE UNWIND (ctx, {time_remaining:.0f}s): BUY NO @ {exit_price:.3f}",
                    urgency="CRITICAL",
                    metadata={"side": "YES", "fallback_sell_price": ctx.yes_price, "fallback_token": ctx.token_yes}
                )
            elif ctx.position_no > 0:
                # NO만 있음
                exit_price = ctx.yes_price
                pnl = ctx.position_no * (1.0 - ctx.avg_price_no - exit_price)
                pnl_pct = (pnl / (ctx.position_no * ctx.avg_price_no)) if ctx.avg_price_no > 0 else 0
                logger.warning(f"FORCE UNWIND (from ctx): BUY YES x{ctx.position_no} @ {exit_price:.3f} (unwinding NO @ {ctx.avg_price_no:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")
                return ScalpSignal(
                    action="EXIT",
                    token_id=ctx.token_yes,
                    price=exit_price,
                    size=ctx.position_no,
                    confidence=1.0,
                    edge=0.0,
                    reason=f"⚠️ FORCE UNWIND (ctx, {time_remaining:.0f}s): BUY YES @ {exit_price:.3f}",
                    urgency="CRITICAL",
                    metadata={"side": "NO", "fallback_sell_price": ctx.no_price, "fallback_token": ctx.token_no}
                )
            else:
                # 포지션 없음
                logger.warning(f"✓ No positions in ctx either - nothing to unwind")
                return None

        # **중요: LEVEL 포지션만 필터링** (HIGH SCALP 제외)
        level_positions = [p for p in positions if not p.is_high_price_scalp]
        high_scalp_positions = [p for p in positions if p.is_high_price_scalp]

        logger.warning(f"📊 _force_unwind breakdown: Total={len(positions)}, LEVEL={len(level_positions)}, HIGH_SCALP={len(high_scalp_positions)}")

        # 각 포지션 상세 로그
        for i, p in enumerate(level_positions):
            logger.info(f"  LEVEL #{i+1}: {p.side} x{p.size} @ {p.entry_price:.3f}")
        for i, p in enumerate(high_scalp_positions):
            logger.info(f"  HIGH_SCALP #{i+1}: {p.side} x{p.size} @ {p.entry_price:.3f}")

        if not level_positions:
            logger.warning(f"❌ _force_unwind: No LEVEL positions to unwind (only {len(high_scalp_positions)} HIGH SCALP exist)")
            return None

        # LEVEL 포지션을 side별로 분류
        yes_positions = [p for p in level_positions if p.side == "YES"]
        no_positions = [p for p in level_positions if p.side == "NO"]

        total_yes_size = sum(p.size for p in yes_positions) if yes_positions else 0
        total_no_size = sum(p.size for p in no_positions) if no_positions else 0

        # 둘 다 있으면 로그 출력
        if yes_positions and no_positions:
            logger.warning(f"⚠️  FORCE UNWIND (LEVEL only): Both YES ({total_yes_size}) and NO ({total_no_size}) positions exist! Unwinding larger position first.")

        # YES 포지션이 더 크거나 같으면 YES 먼저 청산
        if yes_positions and (not no_positions or total_yes_size >= total_no_size):
            # 평균가 계산
            total_yes_cost = sum(p.size * p.entry_price for p in yes_positions)
            avg_yes_entry = total_yes_cost / total_yes_size if total_yes_size > 0 else 0

            # YES 포지션 → NO 토큰 BUY (unwinding)
            exit_price = ctx.no_price
            pnl = total_yes_size * (1.0 - avg_yes_entry - exit_price)
            pnl_pct = (pnl / (total_yes_size * avg_yes_entry)) if avg_yes_entry > 0 else 0

            logger.warning(f"FORCE UNWIND MARKET ({time_remaining:.0f}s left): BUY NO x{total_yes_size:.2f} @ {exit_price:.3f} (unwinding {len(yes_positions)} YES positions @ avg {avg_yes_entry:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")
            # YES 포지션 제거는 봇의 on_exit_filled에서 처리 (주문 성공 후)
            # 여기서는 제거하지 않음 (주문 실패 시 재시도 가능하도록)
            return ScalpSignal(
                action="EXIT",  # market order
                token_id=ctx.token_no,
                price=exit_price,
                size=total_yes_size,
                confidence=1.0,
                edge=0.0,
                reason=f"⚠️ FORCE UNWIND MARKET ({time_remaining:.0f}s left) {pnl_pct:+.1%}: BUY NO @ {exit_price:.3f}",
                urgency="CRITICAL",
                metadata={
                    "side": "YES",
                    "fallback_sell_price": ctx.yes_price,
                    "fallback_token": ctx.token_yes,
                    "avg_entry_price": avg_yes_entry,
                    "num_positions": len(yes_positions)
                }
            )

        # NO 포지션 청산 (YES가 없거나 NO가 더 클 때)
        elif no_positions:
            # 평균가 계산
            total_no_size = sum(p.size for p in no_positions)
            total_no_cost = sum(p.size * p.entry_price for p in no_positions)
            avg_no_entry = total_no_cost / total_no_size if total_no_size > 0 else 0

            # NO 포지션 → YES 토큰 BUY (unwinding)
            exit_price = ctx.yes_price
            pnl = total_no_size * (1.0 - avg_no_entry - exit_price)
            pnl_pct = (pnl / (total_no_size * avg_no_entry)) if avg_no_entry > 0 else 0

            logger.warning(f"FORCE UNWIND MARKET ({time_remaining:.0f}s left): BUY YES x{total_no_size:.2f} @ {exit_price:.3f} (unwinding {len(no_positions)} NO positions @ avg {avg_no_entry:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")
            # NO 포지션 제거는 봇의 on_exit_filled에서 처리 (주문 성공 후)
            # 여기서는 제거하지 않음 (주문 실패 시 재시도 가능하도록)
            return ScalpSignal(
                action="EXIT",  # market order
                token_id=ctx.token_yes,
                price=exit_price,
                size=total_no_size,
                confidence=1.0,
                edge=0.0,
                reason=f"⚠️ FORCE UNWIND MARKET ({time_remaining:.0f}s left) {pnl_pct:+.1%}: BUY YES @ {exit_price:.3f}",
                urgency="CRITICAL",
                metadata={
                    "side": "NO",
                    "fallback_sell_price": ctx.no_price,
                    "fallback_token": ctx.token_no,
                    "avg_entry_price": avg_no_entry,
                    "num_positions": len(no_positions)
                }
            )

        return None

    def get_position_summary(self, ctx: MarketContext) -> dict:
        """포지션 요약"""
        positions = self.positions.get(ctx.market_id, [])

        if not positions:
            return {
                "has_position": False,
                "side": None,
                "size": 0,
                "avg_entry_price": 0,
                "current_exit_price": 0,
                "unrealized_pnl_usdc": 0,
                "unrealized_pnl_pct": 0
            }

        # 모든 포지션 합산
        total_size = sum(p.size for p in positions)
        total_cost = sum(p.size * p.entry_price for p in positions)
        avg_entry = total_cost / total_size if total_size > 0 else 0

        # PnL 계산 (모든 포지션)
        total_pnl = 0
        for pos in positions:
            if pos.side == "YES":
                exit_price = ctx.no_price
            else:
                exit_price = ctx.yes_price
            pnl = pos.size * (1.0 - pos.entry_price - exit_price)
            total_pnl += pnl

        pnl_pct = (total_pnl / total_cost) if total_cost > 0 else 0

        # 대표 side (가장 많은 쪽)
        yes_size = sum(p.size for p in positions if p.side == "YES")
        no_size = sum(p.size for p in positions if p.side == "NO")
        main_side = "YES" if yes_size > no_size else "NO"

        return {
            "has_position": True,
            "side": main_side,
            "size": total_size,
            "avg_entry_price": avg_entry,
            "current_exit_price": ctx.no_price if main_side == "YES" else ctx.yes_price,
            "unrealized_pnl_usdc": total_pnl,
            "unrealized_pnl_pct": pnl_pct,
            "num_positions": len(positions),
            "positions": [{"side": p.side, "level": p.level_price, "entry": p.entry_price, "size": p.size} for p in positions]
        }
