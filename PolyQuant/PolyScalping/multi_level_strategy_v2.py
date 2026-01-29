"""
Multi-Level Scalping Strategy V2 - Refactored
==============================================

핵심 개선사항:
1. 포지션이 상태의 단일 진실 원천 (Single Source of Truth)
2. 모든 카운터는 포지션에서 실시간 계산 (별도 추적 불필요)
3. TP limit order 로직 제거 (5분 미만에는 MARKET만, 5분 이상에는 전략이 아닌 봇에서 관리)
4. 상태 동기화 문제 완전 제거
5. 단순하고 명확한 로직
"""
import time
from typing import Optional, List
from dataclasses import dataclass
from loguru import logger

from models import OrderSide
from tracker import BTCPriceTracker


@dataclass
class LevelPosition:
    """단일 포지션 (레벨별로 구분)"""
    side: str  # "YES" or "NO"
    entry_price: float
    size: float
    entry_time: float
    is_high_scalp: bool  # True면 high price scalping, False면 일반 LEVEL
    profit_target: float  # 익절 목표 (0.05 = 5%, 0.02 = 2%)


@dataclass
class MarketContext:
    """마켓 평가에 필요한 모든 정보"""
    market_id: str
    end_time: float  # Unix timestamp
    yes_price: float  # 현재 YES ASK 가격
    no_price: float  # 현재 NO ASK 가격
    token_yes: str
    token_no: str


@dataclass
class ScalpSignal:
    """전략 시그널"""
    action: str  # "ENTER_YES", "ENTER_NO", "EXIT"
    token_id: str
    price: float
    size: float
    reason: str
    urgency: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    metadata: dict


class MultiLevelScalpingStrategyV2:
    """
    리팩토링된 멀티레벨 스캘핑 전략

    **핵심 원칙:**
    1. 포지션만 추적, 모든 통계는 포지션에서 계산
    2. 5분 미만: LEVEL 포지션 강제 청산 → HIGH SCALP만
    3. 5분 이상: LEVEL 진입 허용, TP는 봇에서 LIMIT order 관리
    """

    def __init__(self, price_tracker: BTCPriceTracker):
        self.tracker = price_tracker

        # === 전략 설정 ===
        # LEVEL 진입 (일반 스캘핑)
        self.entry_levels = [0.34, 0.24, 0.14]
        self.level_size = 10.0
        self.level_profit_target = 0.05  # 5%

        # HIGH SCALP 진입 (5분 미만, 고확률)
        self.high_scalp_threshold = 0.85  # 85¢ 이상
        self.high_scalp_size = 5.0
        self.high_scalp_profit_target = 0.02  # 2%
        self.max_high_scalp_per_market = 4

        # 시간 제한
        self.min_time_for_level_entry = 420  # 7분 (420초) - 이보다 적으면 LEVEL 진입 금지
        self.force_unwind_time = 300  # 5분 (300초) - 이보다 적으면 LEVEL 강제청산

        # 마켓당 최대 완료된 사이클 (LEVEL)
        self.max_completed_cycles = 3

        # === 상태 (포지션만) ===
        self.positions: dict[str, List[LevelPosition]] = {}

        # 완료된 사이클 추적 (LEVEL만, HIGH SCALP 제외)
        # 한 사이클 = 진입 → 익절 완료
        self.completed_cycles: dict[str, int] = {}

    def on_order_filled(self, market_id: str, side: str, price: float, size: float,
                       level: float, metadata: dict):
        """
        주문 체결 콜백 - 포지션 추가

        **중요**: 이 함수만이 포지션을 추가할 수 있음
        """
        if market_id not in self.positions:
            self.positions[market_id] = []

        is_high_scalp = metadata.get('is_high_price_scalp', False)
        profit_target = metadata.get('profit_target', self.level_profit_target)

        position = LevelPosition(
            side=side,
            entry_price=price,
            size=size,
            entry_time=time.time(),
            is_high_scalp=is_high_scalp,
            profit_target=profit_target
        )

        self.positions[market_id].append(position)

        # 로그
        pos_type = "HIGH_SCALP" if is_high_scalp else "LEVEL"
        total_positions = len(self.positions[market_id])

        if is_high_scalp:
            high_scalp_count = self._count_high_scalp_positions(market_id)
            logger.info(
                f"✓ Position added [{pos_type}]: {side} {size} @ {price:.3f} "
                f"(target {profit_target*100:.0f}%) | "
                f"High scalp #{high_scalp_count}/{self.max_high_scalp_per_market} | "
                f"Total positions: {total_positions}"
            )
        else:
            logger.info(
                f"✓ Position added [{pos_type}]: {side} {size} @ {price:.3f} "
                f"(target {profit_target*100:.0f}%) | "
                f"Total positions: {total_positions}"
            )

    def on_exit_filled(self, market_id: str, side: str, is_high_scalp: bool = False):
        """
        청산 체결 콜백 - 포지션 제거

        **중요**: 이 함수만이 포지션을 제거할 수 있음
        """
        if market_id not in self.positions:
            return

        # 해당 side의 모든 포지션 제거
        removed_positions = [p for p in self.positions[market_id] if p.side == side]
        self.positions[market_id] = [p for p in self.positions[market_id] if p.side != side]

        # LEVEL 포지션 청산이면 completed_cycles 증가
        if not is_high_scalp and removed_positions:
            if market_id not in self.completed_cycles:
                self.completed_cycles[market_id] = 0
            self.completed_cycles[market_id] += 1

            logger.info(
                f"✓ Exit confirmed (LEVEL): {side} - "
                f"Cycle #{self.completed_cycles[market_id]}/{self.max_completed_cycles} completed - "
                f"{len(self.positions[market_id])} positions remaining"
            )
        else:
            logger.info(
                f"✓ Exit confirmed (HIGH_SCALP): {side} - "
                f"{len(self.positions[market_id])} positions remaining"
            )

    # === 유틸리티: 포지션에서 통계 계산 ===

    def _count_high_scalp_positions(self, market_id: str) -> int:
        """현재 HIGH SCALP 포지션 개수"""
        if market_id not in self.positions:
            return 0
        return sum(1 for p in self.positions[market_id] if p.is_high_scalp)

    def _get_level_positions(self, market_id: str) -> List[LevelPosition]:
        """LEVEL 포지션만 필터링"""
        if market_id not in self.positions:
            return []
        return [p for p in self.positions[market_id] if not p.is_high_scalp]

    def _get_high_scalp_positions(self, market_id: str) -> List[LevelPosition]:
        """HIGH SCALP 포지션만 필터링"""
        if market_id not in self.positions:
            return []
        return [p for p in self.positions[market_id] if p.is_high_scalp]

    def _has_position_at_level(self, market_id: str, level: float, tolerance: float = 0.01) -> bool:
        """특정 레벨에 이미 포지션이 있는지 확인 (LEVEL만)"""
        level_positions = self._get_level_positions(market_id)
        for p in level_positions:
            if abs(p.entry_price - level) < tolerance:
                return True
        return False

    # === 메인 평가 함수 ===

    def evaluate_market(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """
        마켓 평가 및 신호 생성

        우선순위:
        1. <5분: LEVEL 강제 청산 (MARKET order)
        2. <5분: HIGH SCALP 진입/청산
        3. >=5분: LEVEL 진입
        4. >=5분: LEVEL 청산 (봇에서 LIMIT order 처리)
        """
        market_id = ctx.market_id
        time_remaining = ctx.end_time - time.time()

        # 초기화
        if market_id not in self.positions:
            self.positions[market_id] = []
        if market_id not in self.completed_cycles:
            self.completed_cycles[market_id] = 0

        # === 1. <5분: 긴급 상황 ===
        if time_remaining < self.force_unwind_time:
            logger.debug(f"⏰ <5min mode: {time_remaining:.0f}s remaining")

            # 1-1. LEVEL 포지션 강제 청산
            force_unwind_signal = self._check_force_unwind(ctx)
            if force_unwind_signal:
                return force_unwind_signal

            # 1-2. HIGH SCALP 청산 체크
            high_scalp_exit = self._check_high_scalp_exit(ctx)
            if high_scalp_exit:
                return high_scalp_exit

            # 1-3. HIGH SCALP 진입 체크
            high_scalp_entry = self._check_high_scalp_entry(ctx)
            if high_scalp_entry:
                return high_scalp_entry

            # <5분에는 LEVEL 진입/청산 하지 않음
            return None

        # === 2. >=5분: 일반 모드 ===

        # 2-1. LEVEL 청산 체크 (TP 조건 만족 시)
        # 실제 청산은 봇에서 LIMIT order로 처리
        level_exit = self._check_level_exit(ctx)
        if level_exit:
            return level_exit

        # 2-2. LEVEL 진입 체크
        level_entry = self._check_level_entry(ctx)
        if level_entry:
            return level_entry

        return None

    # === 청산 체크 ===

    def _check_force_unwind(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """
        5분 미만: LEVEL 포지션 강제 청산 (MARKET order)
        HIGH SCALP 포지션은 제외 (자체 익절 로직 사용)
        """
        market_id = ctx.market_id
        level_positions = self._get_level_positions(market_id)

        if not level_positions:
            return None

        time_remaining = ctx.end_time - time.time()

        # Side별로 분류
        yes_positions = [p for p in level_positions if p.side == "YES"]
        no_positions = [p for p in level_positions if p.side == "NO"]

        total_yes_size = sum(p.size for p in yes_positions)
        total_no_size = sum(p.size for p in no_positions)

        # 둘 다 있으면 경고 (헷징 상태)
        if yes_positions and no_positions:
            logger.warning(
                f"⚠️  FORCE UNWIND: Both YES ({total_yes_size}) and NO ({total_no_size}) "
                f"LEVEL positions exist! Unwinding larger first."
            )

        # YES 포지션이 더 크면 YES 청산
        if yes_positions and (not no_positions or total_yes_size >= total_no_size):
            avg_entry = sum(p.size * p.entry_price for p in yes_positions) / total_yes_size
            exit_price = ctx.no_price
            pnl = total_yes_size * (1.0 - avg_entry - exit_price)
            pnl_pct = pnl / (total_yes_size * avg_entry) if avg_entry > 0 else 0

            logger.warning(
                f"🚨 FORCE UNWIND: BUY NO x{total_yes_size} @ {exit_price:.3f} "
                f"(unwinding {len(yes_positions)} YES @ avg {avg_entry:.3f}) | "
                f"PnL: ${pnl:+.2f} ({pnl_pct:+.1%}) | {time_remaining:.0f}s left"
            )

            return ScalpSignal(
                action="EXIT",
                token_id=ctx.token_no,
                price=exit_price,
                size=total_yes_size,
                reason=f"FORCE UNWIND ({time_remaining:.0f}s): BUY NO @ {exit_price:.3f}",
                urgency="CRITICAL",
                metadata={
                    "side": "YES",
                    "is_high_price_scalp": False,
                    "fallback_sell_price": ctx.yes_price,
                    "fallback_token": ctx.token_yes
                }
            )

        # NO 포지션 청산
        if no_positions:
            avg_entry = sum(p.size * p.entry_price for p in no_positions) / total_no_size
            exit_price = ctx.yes_price
            pnl = total_no_size * (1.0 - avg_entry - exit_price)
            pnl_pct = pnl / (total_no_size * avg_entry) if avg_entry > 0 else 0

            logger.warning(
                f"🚨 FORCE UNWIND: BUY YES x{total_no_size} @ {exit_price:.3f} "
                f"(unwinding {len(no_positions)} NO @ avg {avg_entry:.3f}) | "
                f"PnL: ${pnl:+.2f} ({pnl_pct:+.1%}) | {time_remaining:.0f}s left"
            )

            return ScalpSignal(
                action="EXIT",
                token_id=ctx.token_yes,
                price=exit_price,
                size=total_no_size,
                reason=f"FORCE UNWIND ({time_remaining:.0f}s): BUY YES @ {exit_price:.3f}",
                urgency="CRITICAL",
                metadata={
                    "side": "NO",
                    "is_high_price_scalp": False,
                    "fallback_sell_price": ctx.no_price,
                    "fallback_token": ctx.token_no
                }
            )

        return None

    def _check_level_exit(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """
        LEVEL 포지션 익절 체크 (5분 이상)

        TP 조건 만족 시 신호 반환 (실제 LIMIT order는 봇에서 처리)
        """
        market_id = ctx.market_id
        level_positions = self._get_level_positions(market_id)

        if not level_positions:
            return None

        # Side별로 분류
        yes_positions = [p for p in level_positions if p.side == "YES"]
        no_positions = [p for p in level_positions if p.side == "NO"]

        # YES 포지션 청산 체크
        if yes_positions:
            total_size = sum(p.size for p in yes_positions)
            avg_entry = sum(p.size * p.entry_price for p in yes_positions) / total_size
            profit_target = self.level_profit_target

            # Target exit = 1 - (1 + profit_target) * avg_entry
            target_exit = 1.0 - (1.0 + profit_target) * avg_entry
            current_exit = ctx.no_price

            if current_exit <= target_exit:
                pnl = total_size * (1.0 - avg_entry - current_exit)
                pnl_pct = pnl / (total_size * avg_entry)

                logger.info(
                    f"✓ TP met (LEVEL YES): BUY NO x{total_size} @ {current_exit:.3f} "
                    f"(unwinding YES @ avg {avg_entry:.3f}) | "
                    f"PnL: ${pnl:+.2f} ({pnl_pct:+.1%})"
                )

                return ScalpSignal(
                    action="PLACE_TP_LIMIT",
                    token_id=ctx.token_no,
                    price=current_exit,
                    size=total_size,
                    reason=f"TP LIMIT: BUY NO @ {current_exit:.3f} ({pnl_pct:+.1%})",
                    urgency="MEDIUM",
                    metadata={
                        "side": "YES",
                        "is_high_price_scalp": False,
                        "order_type": "BUY",
                        "token_yes": ctx.token_yes,
                        "token_no": ctx.token_no
                    }
                )

        # NO 포지션 청산 체크
        if no_positions:
            total_size = sum(p.size for p in no_positions)
            avg_entry = sum(p.size * p.entry_price for p in no_positions) / total_size
            profit_target = self.level_profit_target

            target_exit = 1.0 - (1.0 + profit_target) * avg_entry
            current_exit = ctx.yes_price

            if current_exit <= target_exit:
                pnl = total_size * (1.0 - avg_entry - current_exit)
                pnl_pct = pnl / (total_size * avg_entry)

                logger.info(
                    f"✓ TP met (LEVEL NO): BUY YES x{total_size} @ {current_exit:.3f} "
                    f"(unwinding NO @ avg {avg_entry:.3f}) | "
                    f"PnL: ${pnl:+.2f} ({pnl_pct:+.1%})"
                )

                return ScalpSignal(
                    action="PLACE_TP_LIMIT",
                    token_id=ctx.token_yes,
                    price=current_exit,
                    size=total_size,
                    reason=f"TP LIMIT: BUY YES @ {current_exit:.3f} ({pnl_pct:+.1%})",
                    urgency="MEDIUM",
                    metadata={
                        "side": "NO",
                        "is_high_price_scalp": False,
                        "order_type": "BUY",
                        "token_yes": ctx.token_yes,
                        "token_no": ctx.token_no
                    }
                )

        return None

    def _check_high_scalp_exit(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """HIGH SCALP 포지션 익절 체크 (MARKET order)"""
        market_id = ctx.market_id
        high_scalp_positions = self._get_high_scalp_positions(market_id)

        if not high_scalp_positions:
            return None

        # Side별로 분류
        yes_positions = [p for p in high_scalp_positions if p.side == "YES"]
        no_positions = [p for p in high_scalp_positions if p.side == "NO"]

        # YES 포지션 청산 체크
        if yes_positions:
            total_size = sum(p.size for p in yes_positions)
            avg_entry = sum(p.size * p.entry_price for p in yes_positions) / total_size
            profit_target = self.high_scalp_profit_target

            target_exit = 1.0 - (1.0 + profit_target) * avg_entry
            current_exit = ctx.no_price

            if current_exit <= target_exit:
                pnl = total_size * (1.0 - avg_entry - current_exit)
                pnl_pct = pnl / (total_size * avg_entry)

                logger.info(
                    f"✓ TP met (HIGH_SCALP YES): BUY NO x{total_size} @ {current_exit:.3f} | "
                    f"PnL: ${pnl:+.2f} ({pnl_pct:+.1%})"
                )

                return ScalpSignal(
                    action="EXIT",
                    token_id=ctx.token_no,
                    price=current_exit,
                    size=total_size,
                    reason=f"HIGH_SCALP TP: BUY NO @ {current_exit:.3f} ({pnl_pct:+.1%})",
                    urgency="HIGH",
                    metadata={
                        "side": "YES",
                        "is_high_price_scalp": True,
                        "fallback_sell_price": ctx.yes_price,
                        "fallback_token": ctx.token_yes
                    }
                )

        # NO 포지션 청산 체크
        if no_positions:
            total_size = sum(p.size for p in no_positions)
            avg_entry = sum(p.size * p.entry_price for p in no_positions) / total_size
            profit_target = self.high_scalp_profit_target

            target_exit = 1.0 - (1.0 + profit_target) * avg_entry
            current_exit = ctx.yes_price

            if current_exit <= target_exit:
                pnl = total_size * (1.0 - avg_entry - current_exit)
                pnl_pct = pnl / (total_size * avg_entry)

                logger.info(
                    f"✓ TP met (HIGH_SCALP NO): BUY YES x{total_size} @ {current_exit:.3f} | "
                    f"PnL: ${pnl:+.2f} ({pnl_pct:+.1%})"
                )

                return ScalpSignal(
                    action="EXIT",
                    token_id=ctx.token_yes,
                    price=current_exit,
                    size=total_size,
                    reason=f"HIGH_SCALP TP: BUY YES @ {current_exit:.3f} ({pnl_pct:+.1%})",
                    urgency="HIGH",
                    metadata={
                        "side": "NO",
                        "is_high_price_scalp": True,
                        "fallback_sell_price": ctx.no_price,
                        "fallback_token": ctx.token_no
                    }
                )

        return None

    # === 진입 체크 ===

    def _check_level_entry(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """
        LEVEL 진입 체크 (5분 이상만)

        조건:
        - 7분 이상 남음
        - 완료된 사이클이 max 미만
        - 레벨 진입 조건 만족
        - 포지션이 없거나 반대편만 있을 때
        """
        market_id = ctx.market_id
        time_remaining = ctx.end_time - time.time()

        # 7분 미만이면 LEVEL 진입 금지
        if time_remaining < self.min_time_for_level_entry:
            return None

        # 완료된 사이클 체크
        cycles = self.completed_cycles.get(market_id, 0)
        if cycles >= self.max_completed_cycles:
            return None

        # 현재 LEVEL 포지션 확인
        level_positions = self._get_level_positions(market_id)
        yes_positions = [p for p in level_positions if p.side == "YES"]
        no_positions = [p for p in level_positions if p.side == "NO"]

        # YES와 NO 둘 다 있으면 진입 금지 (헷징 방지)
        if yes_positions and no_positions:
            return None

        # YES 진입 체크 (레벨 하향 돌파)
        for level in self.entry_levels:
            if ctx.yes_price < level:
                # 이미 이 레벨에 진입했는지 체크
                if self._has_position_at_level(market_id, level):
                    continue

                # NO 포지션이 있으면 진입 금지 (헷징 방지)
                if no_positions:
                    continue

                logger.info(
                    f"💰 LEVEL entry: YES @ {ctx.yes_price:.3f} < {level:.2f} | "
                    f"Cycle {cycles+1}/{self.max_completed_cycles} | "
                    f"{time_remaining:.0f}s remaining"
                )

                return ScalpSignal(
                    action="ENTER_YES",
                    token_id=ctx.token_yes,
                    price=ctx.yes_price,
                    size=self.level_size,
                    reason=f"LEVEL entry: YES @ {ctx.yes_price:.3f} (level {level:.2f})",
                    urgency="MEDIUM",
                    metadata={
                        "side": "YES",
                        "level": level,
                        "is_high_price_scalp": False,
                        "profit_target": self.level_profit_target
                    }
                )

        # NO 진입 체크 (레벨 하향 돌파)
        for level in self.entry_levels:
            if ctx.no_price < level:
                # 이미 이 레벨에 진입했는지 체크
                if self._has_position_at_level(market_id, level):
                    continue

                # YES 포지션이 있으면 진입 금지 (헷징 방지)
                if yes_positions:
                    continue

                logger.info(
                    f"💰 LEVEL entry: NO @ {ctx.no_price:.3f} < {level:.2f} | "
                    f"Cycle {cycles+1}/{self.max_completed_cycles} | "
                    f"{time_remaining:.0f}s remaining"
                )

                return ScalpSignal(
                    action="ENTER_NO",
                    token_id=ctx.token_no,
                    price=ctx.no_price,
                    size=self.level_size,
                    reason=f"LEVEL entry: NO @ {ctx.no_price:.3f} (level {level:.2f})",
                    urgency="MEDIUM",
                    metadata={
                        "side": "NO",
                        "level": level,
                        "is_high_price_scalp": False,
                        "profit_target": self.level_profit_target
                    }
                )

        return None

    def _check_high_scalp_entry(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """
        HIGH SCALP 진입 체크 (5분 미만만)

        조건:
        - 5분 미만
        - 가격이 threshold (85¢) 이상
        - HIGH SCALP 포지션이 max 미만
        """
        market_id = ctx.market_id
        time_remaining = ctx.end_time - time.time()

        # 5분 이상이면 스킵
        if time_remaining >= self.force_unwind_time:
            return None

        # HIGH SCALP 포지션 개수 체크
        high_scalp_count = self._count_high_scalp_positions(market_id)
        if high_scalp_count >= self.max_high_scalp_per_market:
            return None

        # 현재 HIGH SCALP 포지션 확인
        high_scalp_positions = self._get_high_scalp_positions(market_id)

        # 이미 포지션이 있으면 진입 금지 (한 번에 하나만)
        if high_scalp_positions:
            return None

        # YES가 threshold 이상이면 YES 매수
        if ctx.yes_price >= self.high_scalp_threshold:
            logger.info(
                f"🎯 HIGH_SCALP entry: YES @ {ctx.yes_price:.3f} (≥{self.high_scalp_threshold:.2f}) | "
                f"#{high_scalp_count+1}/{self.max_high_scalp_per_market} | "
                f"{time_remaining:.0f}s remaining"
            )

            return ScalpSignal(
                action="ENTER_YES",
                token_id=ctx.token_yes,
                price=ctx.yes_price,
                size=self.high_scalp_size,
                reason=f"HIGH_SCALP: YES @ {ctx.yes_price:.3f} ({time_remaining:.0f}s)",
                urgency="HIGH",
                metadata={
                    "side": "YES",
                    "level": ctx.yes_price,
                    "is_high_price_scalp": True,
                    "profit_target": self.high_scalp_profit_target
                }
            )

        # NO가 threshold 이상이면 NO 매수
        if ctx.no_price >= self.high_scalp_threshold:
            logger.info(
                f"🎯 HIGH_SCALP entry: NO @ {ctx.no_price:.3f} (≥{self.high_scalp_threshold:.2f}) | "
                f"#{high_scalp_count+1}/{self.max_high_scalp_per_market} | "
                f"{time_remaining:.0f}s remaining"
            )

            return ScalpSignal(
                action="ENTER_NO",
                token_id=ctx.token_no,
                price=ctx.no_price,
                size=self.high_scalp_size,
                reason=f"HIGH_SCALP: NO @ {ctx.no_price:.3f} ({time_remaining:.0f}s)",
                urgency="HIGH",
                metadata={
                    "side": "NO",
                    "level": ctx.no_price,
                    "is_high_price_scalp": True,
                    "profit_target": self.high_scalp_profit_target
                }
            )

        return None

    def get_position_summary(self, ctx: MarketContext) -> dict:
        """포지션 요약 정보"""
        positions = self.positions.get(ctx.market_id, [])

        if not positions:
            return {"has_position": False}

        # Side별 합산
        yes_positions = [p for p in positions if p.side == "YES"]
        no_positions = [p for p in positions if p.side == "NO"]

        total_yes_size = sum(p.size for p in yes_positions)
        total_no_size = sum(p.size for p in no_positions)

        # 메인 side 결정
        if total_yes_size > total_no_size:
            main_side = "YES"
            total_size = total_yes_size
            avg_entry = sum(p.size * p.entry_price for p in yes_positions) / total_yes_size
            current_exit_price = ctx.no_price
        elif total_no_size > 0:
            main_side = "NO"
            total_size = total_no_size
            avg_entry = sum(p.size * p.entry_price for p in no_positions) / total_no_size
            current_exit_price = ctx.yes_price
        else:
            return {"has_position": False}

        # PnL 계산
        pnl = total_size * (1.0 - avg_entry - current_exit_price)
        pnl_pct = pnl / (total_size * avg_entry) if avg_entry > 0 else 0

        return {
            "has_position": True,
            "side": main_side,
            "size": total_size,
            "avg_entry_price": avg_entry,
            "current_exit_price": current_exit_price,
            "unrealized_pnl_usdc": pnl,
            "unrealized_pnl_pct": pnl_pct,
            "num_positions": len(positions),
            "positions": [
                {
                    "side": p.side,
                    "entry": p.entry_price,
                    "size": p.size,
                    "type": "HIGH_SCALP" if p.is_high_scalp else "LEVEL"
                }
                for p in positions
            ]
        }
