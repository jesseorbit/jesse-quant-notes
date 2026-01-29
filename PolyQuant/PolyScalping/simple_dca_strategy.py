"""
간단한 DCA (Dollar Cost Averaging) 전략
사용자 요구사항:
- YES or NO가 34c에 터치하면 10 shares 진입
- 반대 포지션이 60c 밑으로 떨어지면 unwinding (반대쪽 매수)
- 가격이 24c, 14c 떨어지면 각각 10 shares 물타기
- 3분 남았는데 손실 중이면 강제 청산
"""
from dataclasses import dataclass, field
from typing import Optional, List
from loguru import logger
from scalping_strategy import ScalpSignal, MarketContext
from btc_price_tracker import BTCPriceTracker
import time


@dataclass
class DCAPosition:
    """DCA 포지션 추적"""
    side: str  # "YES" or "NO"
    entries: List[float] = field(default_factory=list)  # 진입 가격들
    sizes: List[float] = field(default_factory=list)  # 각 진입 크기
    total_size: float = 0.0
    avg_price: float = 0.0
    entry_time: float = 0.0

    def add_entry(self, price: float, size: float):
        """진입 추가"""
        self.entries.append(price)
        self.sizes.append(size)
        total_cost = sum(p * s for p, s in zip(self.entries, self.sizes))
        self.total_size = sum(self.sizes)
        self.avg_price = total_cost / self.total_size if self.total_size > 0 else 0

        if self.entry_time == 0:
            self.entry_time = time.time()

    def get_pnl(self, current_exit_price: float) -> float:
        """현재 PnL 계산"""
        if self.total_size == 0:
            return 0.0
        # Polymarket: 청산은 반대쪽을 사는 것이므로
        # PnL = size * (1 - entry_price - exit_price)
        return self.total_size * (1.0 - self.avg_price - current_exit_price)

    def get_pnl_pct(self, current_exit_price: float) -> float:
        """PnL 퍼센트"""
        if self.total_size == 0 or self.avg_price == 0:
            return 0.0
        pnl = self.get_pnl(current_exit_price)
        cost = self.total_size * self.avg_price
        return pnl / cost if cost > 0 else 0.0


class SimpleDCAStrategy:
    """
    간단한 34c 진입 + DCA 전략

    규칙:
    1. YES or NO가 34c 터치 → 10 shares 진입
    2. 반대 포지션 60c 밑 → unwinding (반대쪽 매수로 청산)
    3. 24c 하락 → +10 shares DCA
    4. 14c 추가 하락 (총 38c 하락) → +10 shares DCA
    5. 3분 남았는데 손실 → 강제 청산
    """

    def __init__(self, price_tracker: BTCPriceTracker):
        self.tracker = price_tracker

        # 전략 파라미터
        self.entry_trigger = 0.34  # 34c 터치 시 진입
        self.unwind_trigger = 0.60  # 반대쪽 60c 밑이면 청산
        self.dca_level_1 = 0.24  # 24c 하락 시 첫 물타기
        self.dca_level_2 = 0.14  # 14c 추가 하락 시 두번째 물타기 (총 38c)
        self.clip_size = 10.0  # 기본 진입 크기
        self.force_exit_time = 180  # 3분 남았을 때

        # 포지션 추적
        self.positions: dict[str, Optional[DCAPosition]] = {}  # market_id -> DCAPosition
        self.entry_triggered: dict[str, bool] = {}  # market_id -> bool

    def evaluate_market(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """마켓 평가 및 신호 생성"""
        market_id = ctx.market_id

        # 포지션 초기화
        if market_id not in self.positions:
            self.positions[market_id] = None
            self.entry_triggered[market_id] = False

        current_position = self.positions[market_id]

        # 포지션 없으면 진입 신호 확인
        if current_position is None:
            return self._check_entry(ctx)

        # 포지션 있으면 청산 또는 DCA 확인
        exit_signal = self._check_exit(ctx, current_position)
        if exit_signal:
            return exit_signal

        dca_signal = self._check_dca(ctx, current_position)
        if dca_signal:
            return dca_signal

        return None

    def _check_entry(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """진입 신호 확인"""
        # 이미 진입했으면 스킵
        if self.entry_triggered.get(ctx.market_id, False):
            return None

        # YES가 34c 이하 터치?
        if ctx.yes_price <= self.entry_trigger:
            self.entry_triggered[ctx.market_id] = True

            # 포지션 생성
            position = DCAPosition(side="YES")
            position.add_entry(ctx.yes_price, self.clip_size)
            self.positions[ctx.market_id] = position

            logger.info(f"Entry triggered: YES @ {ctx.yes_price:.3f}")

            return ScalpSignal(
                action="ENTER_YES",
                token_id=ctx.token_yes,
                price=ctx.yes_price,
                size=self.clip_size,
                confidence=1.0,
                edge=0.0,
                reason=f"YES @ {ctx.yes_price:.2f}c (trigger: {self.entry_trigger:.2f}c)",
                urgency="MEDIUM"
            )

        # NO가 34c 이하 터치?
        if ctx.no_price <= self.entry_trigger:
            self.entry_triggered[ctx.market_id] = True

            # 포지션 생성
            position = DCAPosition(side="NO")
            position.add_entry(ctx.no_price, self.clip_size)
            self.positions[ctx.market_id] = position

            logger.info(f"Entry triggered: NO @ {ctx.no_price:.3f}")

            return ScalpSignal(
                action="ENTER_NO",
                token_id=ctx.token_no,
                price=ctx.no_price,
                size=self.clip_size,
                confidence=1.0,
                edge=0.0,
                reason=f"NO @ {ctx.no_price:.2f}c (trigger: {self.entry_trigger:.2f}c)",
                urgency="MEDIUM"
            )

        return None

    def _check_exit(self, ctx: MarketContext, position: DCAPosition) -> Optional[ScalpSignal]:
        """청산 신호 확인"""
        remaining = ctx.end_time - time.time()

        # 1. 반대쪽이 60c 밑으로 떨어졌나?
        if position.side == "YES":
            # YES 포지션 → NO가 60c 밑이면 청산
            if ctx.no_price < self.unwind_trigger:
                logger.info(f"Unwind triggered: NO @ {ctx.no_price:.3f} < {self.unwind_trigger:.2f}")

                # 포지션 초기화
                self.positions[ctx.market_id] = None
                self.entry_triggered[ctx.market_id] = False

                return ScalpSignal(
                    action="EXIT",
                    token_id=ctx.token_no,
                    price=ctx.no_price,
                    size=position.total_size,
                    confidence=1.0,
                    edge=0.0,
                    reason=f"Unwind: NO dropped to {ctx.no_price:.3f}c",
                    urgency="HIGH"
                )

        elif position.side == "NO":
            # NO 포지션 → YES가 60c 밑이면 청산
            if ctx.yes_price < self.unwind_trigger:
                logger.info(f"Unwind triggered: YES @ {ctx.yes_price:.3f} < {self.unwind_trigger:.2f}")

                # 포지션 초기화
                self.positions[ctx.market_id] = None
                self.entry_triggered[ctx.market_id] = False

                return ScalpSignal(
                    action="EXIT",
                    token_id=ctx.token_yes,
                    price=ctx.yes_price,
                    size=position.total_size,
                    confidence=1.0,
                    edge=0.0,
                    reason=f"Unwind: YES dropped to {ctx.yes_price:.3f}c",
                    urgency="HIGH"
                )

        # 2. 3분 남았는데 손실 중?
        if remaining <= self.force_exit_time:
            current_exit_price = ctx.no_price if position.side == "YES" else ctx.yes_price
            pnl = position.get_pnl(current_exit_price)

            if pnl < 0:
                logger.info(f"Force exit: {remaining:.0f}s left, PnL: ${pnl:.2f}")

                # 포지션 초기화
                self.positions[ctx.market_id] = None
                self.entry_triggered[ctx.market_id] = False

                return ScalpSignal(
                    action="EXIT",
                    token_id=ctx.token_no if position.side == "YES" else ctx.token_yes,
                    price=current_exit_price,
                    size=position.total_size,
                    confidence=1.0,
                    edge=0.0,
                    reason=f"Force exit: {remaining:.0f}s left, loss ${pnl:.2f}",
                    urgency="HIGH"
                )

        return None

    def _check_dca(self, ctx: MarketContext, position: DCAPosition) -> Optional[ScalpSignal]:
        """DCA (물타기) 신호 확인"""
        # 이미 3개 진입했으면 더 이상 DCA 안함
        if len(position.entries) >= 3:
            return None

        current_price = ctx.yes_price if position.side == "YES" else ctx.no_price
        first_entry_price = position.entries[0]

        # 가격 하락 폭
        drop = first_entry_price - current_price

        # 24c 하락 → 첫 DCA (2번째 진입)
        if len(position.entries) == 1 and drop >= self.dca_level_1:
            position.add_entry(current_price, self.clip_size)

            logger.info(f"DCA Level 1: {position.side} @ {current_price:.3f} (dropped {drop:.3f})")

            return ScalpSignal(
                action=f"ENTER_{position.side}",
                token_id=ctx.token_yes if position.side == "YES" else ctx.token_no,
                price=current_price,
                size=self.clip_size,
                confidence=1.0,
                edge=0.0,
                reason=f"DCA-1: Dropped {drop:.3f}c from entry",
                urgency="MEDIUM"
            )

        # 총 38c 하락 (24 + 14) → 두번째 DCA (3번째 진입)
        if len(position.entries) == 2 and drop >= (self.dca_level_1 + self.dca_level_2):
            position.add_entry(current_price, self.clip_size)

            logger.info(f"DCA Level 2: {position.side} @ {current_price:.3f} (dropped {drop:.3f})")

            return ScalpSignal(
                action=f"ENTER_{position.side}",
                token_id=ctx.token_yes if position.side == "YES" else ctx.token_no,
                price=current_price,
                size=self.clip_size,
                confidence=1.0,
                edge=0.0,
                reason=f"DCA-2: Dropped {drop:.3f}c from entry",
                urgency="HIGH"
            )

        return None

    def get_position_summary(self, ctx: MarketContext) -> dict:
        """포지션 요약"""
        position = self.positions.get(ctx.market_id)

        if position is None:
            return {
                "has_position": False,
                "side": None,
                "size": 0,
                "avg_entry_price": 0,
                "current_exit_price": 0,
                "unrealized_pnl_usdc": 0,
                "unrealized_pnl_pct": 0
            }

        current_exit_price = ctx.no_price if position.side == "YES" else ctx.yes_price
        pnl = position.get_pnl(current_exit_price)
        pnl_pct = position.get_pnl_pct(current_exit_price)

        return {
            "has_position": True,
            "side": position.side,
            "size": position.total_size,
            "avg_entry_price": position.avg_price,
            "current_exit_price": current_exit_price,
            "unrealized_pnl_usdc": pnl,
            "unrealized_pnl_pct": pnl_pct,
            "entries": len(position.entries),
            "entry_prices": position.entries
        }
