"""
BTC 15분 마켓 스캘핑 전략
빠른 진입/청산에 최적화된 전략
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from loguru import logger
from config import config
from btc_price_tracker import BTCPriceTracker, MarketPriceAnalyzer
import time


@dataclass
class ScalpSignal:
    """스캘핑 신호"""
    action: str  # "ENTER_YES", "ENTER_NO", "EXIT", "HOLD"
    token_id: str
    price: float
    size: float
    confidence: float
    edge: float
    reason: str
    urgency: str  # "LOW", "MEDIUM", "HIGH"
    metadata: Optional[Dict[str, Any]] = None  # 추가 메타데이터 (레벨, 사이드 등)


@dataclass
class MarketContext:
    """마켓 컨텍스트 정보"""
    market_id: str
    start_time: float
    end_time: float
    start_price: float  # BTC 시작 가격
    token_yes: str
    token_no: str
    yes_price: float  # YES 토큰 현재 가격
    no_price: float  # NO 토큰 현재 가격
    position_yes: float = 0.0  # 현재 YES 포지션
    position_no: float = 0.0  # 현재 NO 포지션
    avg_price_yes: float = 0.0
    avg_price_no: float = 0.0


class BTCScalpingStrategy:
    """
    BTC 15분 마켓 스캘핑 전략

    특징:
    1. 빠른 진입/청산 (1-3분 홀딩)
    2. 작은 edge로도 거래 (5%+)
    3. 손절 빠름 (-5%)
    4. 포지션 크기 작게 유지
    """

    def __init__(self, price_tracker: BTCPriceTracker):
        self.tracker = price_tracker
        self.analyzer = MarketPriceAnalyzer(price_tracker)

        # 스캘핑 파라미터
        self.min_edge = 0.05  # 5% 최소 edge
        self.take_profit_pct = 0.03  # 3% 익절
        self.stop_loss_pct = 0.05  # 5% 손절
        self.min_confidence = 0.5  # 50% 최소 신뢰도

        # 포지션 관리
        self.max_position_size = config.shares_per_clip * 2  # 20 shares
        self.scale_in_size = config.shares_per_clip  # 10 shares씩

        # 타이밍
        self.min_time_to_enter = 180  # 진입은 만료 3분 전까지
        self.force_exit_time = 60  # 만료 1분 전 강제 청산

        # High price scalping 설정
        self.enable_high_price_scalping = True
        self.high_price_threshold = 0.85  # 85c 이상 (기본 전략용으로 좀 낮게)
        self.high_price_scalp_size = 5.0  # 5 shares
        self.high_price_profit_pct = 0.02  # 2% 익절

    def check_entry(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """
        진입 신호 확인

        조건:
        1. 포지션이 없어야 함
        2. 충분한 시간 남아있어야 함
        3. Edge와 신뢰도가 충분해야 함
        """
        # 이미 포지션이 있으면 진입 안함
        if ctx.position_yes > 0.1 or ctx.position_no > 0.1:
            return None

        # 시간 체크 - 5분 미만이면 진입 금지 (high price scalping은 evaluate_market에서 처리)
        remaining = ctx.end_time - time.time()
        if remaining < 300:  # 5분 = 300초
            return None

        if remaining < self.min_time_to_enter:
            return None

        # 마켓 분석
        analysis = self.analyzer.analyze_market_opportunity(
            market_start_time=ctx.start_time,
            market_end_time=ctx.end_time,
            start_price=ctx.start_price,
            yes_price=ctx.yes_price,
            no_price=ctx.no_price
        )

        # 신뢰도와 edge 확인
        if analysis["confidence"] < self.min_confidence:
            return None

        if analysis["edge"] < self.min_edge:
            return None

        # 진입 신호 생성
        predicted = analysis["predicted_outcome"]

        if predicted == "UP":
            # YES 매수
            return ScalpSignal(
                action="ENTER_YES",
                token_id=ctx.token_yes,
                price=ctx.yes_price,
                size=self.scale_in_size,
                confidence=analysis["confidence"],
                edge=analysis["edge"],
                reason=f"UP predicted | Conf: {analysis['confidence']:.1%} | Edge: {analysis['edge']:.1%}",
                urgency=self._calculate_urgency(analysis["confidence"], analysis["edge"])
            )
        elif predicted == "DOWN":
            # NO 매수
            return ScalpSignal(
                action="ENTER_NO",
                token_id=ctx.token_no,
                price=ctx.no_price,
                size=self.scale_in_size,
                confidence=analysis["confidence"],
                edge=analysis["edge"],
                reason=f"DOWN predicted | Conf: {analysis['confidence']:.1%} | Edge: {analysis['edge']:.1%}",
                urgency=self._calculate_urgency(analysis["confidence"], analysis["edge"])
            )

        return None

    def check_exit(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """
        청산 신호 확인

        조건:
        1. 익절: 3% 이상 수익
        2. 손절: 5% 이상 손실
        3. 강제 청산: 만료 1분 전
        4. 방향 전환: 예측과 반대 방향으로 강하게 움직임
        """
        # 포지션 없으면 청산 불필요
        if ctx.position_yes < 0.1 and ctx.position_no < 0.1:
            return None

        # 시간 기반 강제 청산
        remaining = ctx.end_time - time.time()
        if remaining < self.force_exit_time:
            return self._create_force_exit_signal(ctx, "Time-based force exit")

        # YES 포지션 청산 체크
        if ctx.position_yes > 0.1:
            return self._check_yes_position_exit(ctx, remaining)

        # NO 포지션 청산 체크
        if ctx.position_no > 0.1:
            return self._check_no_position_exit(ctx, remaining)

        return None

    def _check_yes_position_exit(self, ctx: MarketContext, remaining: float) -> Optional[ScalpSignal]:
        """YES 포지션 청산 체크"""
        # 현재 청산 시 손익 계산
        exit_cost = ctx.no_price  # NO 토큰 사서 청산
        entry_cost = ctx.avg_price_yes
        total_cost = entry_cost + exit_cost
        pnl = 1.0 - total_cost  # 스프레드 캡처
        pnl_pct = pnl / entry_cost if entry_cost > 0 else 0

        # 익절 조건
        if pnl_pct >= self.take_profit_pct:
            return ScalpSignal(
                action="EXIT",
                token_id=ctx.token_no,
                price=ctx.no_price,
                size=ctx.position_yes,
                confidence=1.0,
                edge=pnl_pct,
                reason=f"Take Profit ({pnl_pct:.1%})",
                urgency="HIGH"
            )

        # 손절 조건
        if pnl_pct <= -self.stop_loss_pct:
            return ScalpSignal(
                action="EXIT",
                token_id=ctx.token_no,
                price=ctx.no_price,
                size=ctx.position_yes,
                confidence=1.0,
                edge=pnl_pct,
                reason=f"Stop Loss ({pnl_pct:.1%})",
                urgency="HIGH"
            )

        # 방향 전환 체크
        current_price = self.tracker.get_current_price()
        if current_price and ctx.start_price:
            # YES 포지션인데 가격이 하락 중이면 위험
            if current_price < ctx.start_price:
                price_change = (current_price - ctx.start_price) / ctx.start_price

                # -0.5% 이상 하락하고 손실이면 청산
                if price_change < -0.005 and pnl_pct < 0:
                    return ScalpSignal(
                        action="EXIT",
                        token_id=ctx.token_no,
                        price=ctx.no_price,
                        size=ctx.position_yes,
                        confidence=0.8,
                        edge=pnl_pct,
                        reason=f"Direction reversal ({price_change:.2%})",
                        urgency="MEDIUM"
                    )

        return None

    def _check_no_position_exit(self, ctx: MarketContext, remaining: float) -> Optional[ScalpSignal]:
        """NO 포지션 청산 체크"""
        # 현재 청산 시 손익 계산
        exit_cost = ctx.yes_price  # YES 토큰 사서 청산
        entry_cost = ctx.avg_price_no
        total_cost = entry_cost + exit_cost
        pnl = 1.0 - total_cost
        pnl_pct = pnl / entry_cost if entry_cost > 0 else 0

        # 익절 조건
        if pnl_pct >= self.take_profit_pct:
            return ScalpSignal(
                action="EXIT",
                token_id=ctx.token_yes,
                price=ctx.yes_price,
                size=ctx.position_no,
                confidence=1.0,
                edge=pnl_pct,
                reason=f"Take Profit ({pnl_pct:.1%})",
                urgency="HIGH"
            )

        # 손절 조건
        if pnl_pct <= -self.stop_loss_pct:
            return ScalpSignal(
                action="EXIT",
                token_id=ctx.token_yes,
                price=ctx.yes_price,
                size=ctx.position_no,
                confidence=1.0,
                edge=pnl_pct,
                reason=f"Stop Loss ({pnl_pct:.1%})",
                urgency="HIGH"
            )

        # 방향 전환 체크
        current_price = self.tracker.get_current_price()
        if current_price and ctx.start_price:
            # NO 포지션인데 가격이 상승 중이면 위험
            if current_price > ctx.start_price:
                price_change = (current_price - ctx.start_price) / ctx.start_price

                # +0.5% 이상 상승하고 손실이면 청산
                if price_change > 0.005 and pnl_pct < 0:
                    return ScalpSignal(
                        action="EXIT",
                        token_id=ctx.token_yes,
                        price=ctx.yes_price,
                        size=ctx.position_no,
                        confidence=0.8,
                        edge=pnl_pct,
                        reason=f"Direction reversal ({price_change:.2%})",
                        urgency="MEDIUM"
                    )

        return None

    def _create_force_exit_signal(self, ctx: MarketContext, reason: str) -> ScalpSignal:
        """강제 청산 신호 생성"""
        if ctx.position_yes > 0.1:
            return ScalpSignal(
                action="EXIT",
                token_id=ctx.token_no,
                price=ctx.no_price,
                size=ctx.position_yes,
                confidence=1.0,
                edge=0.0,
                reason=reason,
                urgency="HIGH"
            )
        else:
            return ScalpSignal(
                action="EXIT",
                token_id=ctx.token_yes,
                price=ctx.yes_price,
                size=ctx.position_no,
                confidence=1.0,
                edge=0.0,
                reason=reason,
                urgency="HIGH"
            )

    def _calculate_urgency(self, confidence: float, edge: float) -> str:
        """신호의 긴급도 계산"""
        score = confidence + edge

        if score > 1.0:  # 매우 좋은 기회
            return "HIGH"
        elif score > 0.7:
            return "MEDIUM"
        else:
            return "LOW"

    def evaluate_market(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """
        마켓 전체 평가 (진입 + 청산 통합)

        Returns:
            ScalpSignal or None
        """
        # 0. 긴급 청산 확인
        time_remaining = ctx.end_time - time.time()

        # 5분 미만: 모든 포지션 강제 청산 후, high price scalping 체크
        if time_remaining < 300:  # 5분 = 300초
            # YES 포지션이 있으면 NO로 unwinding (market order - 즉시 청산)
            if ctx.position_yes > 0.1:
                pnl = ctx.position_yes * (1.0 - ctx.avg_price_yes - ctx.no_price)
                pnl_pct = pnl / (ctx.position_yes * ctx.avg_price_yes) if ctx.avg_price_yes > 0 else 0

                logger.warning(f"⚠️ FORCE UNWIND ({time_remaining:.0f}s left): BUY NO x{ctx.position_yes:.2f} @ {ctx.no_price:.3f} (unwinding YES @ avg {ctx.avg_price_yes:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")

                return ScalpSignal(
                    action="EXIT",
                    token_id=ctx.token_no,
                    price=ctx.no_price,
                    size=ctx.position_yes,
                    confidence=1.0,
                    edge=0.0,
                    reason=f"⚠️ FORCE UNWIND ({time_remaining:.0f}s left) {pnl_pct:+.1%}: BUY NO @ {ctx.no_price:.3f}",
                    urgency="CRITICAL"
                )

            # NO 포지션이 있으면 YES로 unwinding (market order - 즉시 청산)
            elif ctx.position_no > 0.1:
                pnl = ctx.position_no * (1.0 - ctx.avg_price_no - ctx.yes_price)
                pnl_pct = pnl / (ctx.position_no * ctx.avg_price_no) if ctx.avg_price_no > 0 else 0

                logger.warning(f"⚠️ FORCE UNWIND ({time_remaining:.0f}s left): BUY YES x{ctx.position_no:.2f} @ {ctx.yes_price:.3f} (unwinding NO @ avg {ctx.avg_price_no:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")

                return ScalpSignal(
                    action="EXIT",
                    token_id=ctx.token_yes,
                    price=ctx.yes_price,
                    size=ctx.position_no,
                    confidence=1.0,
                    edge=0.0,
                    reason=f"⚠️ FORCE UNWIND ({time_remaining:.0f}s left) {pnl_pct:+.1%}: BUY YES @ {ctx.yes_price:.3f}",
                    urgency="CRITICAL"
                )

            # **포지션이 모두 정리되었으면 (market order로 즉시 청산 완료), high price scalping 체크**
            # BTCScalpingStrategy는 ctx.position으로 관리하므로 위에서 EXIT 반환하면 봇이 포지션 제거함
            # 다음 cycle에 여기 도달 = 포지션 정리 완료
            high_price_signal = self._check_high_price_scalping(ctx)
            if high_price_signal:
                return high_price_signal

            # 5분 미만이면 일반 진입/청산은 하지 않음
            return None

        # 7분 미만: 신규 진입 금지, unwinding만 허용
        if time_remaining < 420:  # 7분 = 420초
            # 청산만 체크
            exit_signal = self.check_exit(ctx)
            if exit_signal:
                return exit_signal
            # 진입은 하지 않음
            return None

        # 1. 청산 체크 (우선순위 높음)
        exit_signal = self.check_exit(ctx)
        if exit_signal:
            return exit_signal

        # 2. 진입 체크
        entry_signal = self.check_entry(ctx)
        if entry_signal:
            return entry_signal

        return None

    def _check_high_price_scalping(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """
        하이 프라이스 스캘핑 전략 (BTCScalpingStrategy용)
        5분 미만 남았을 때, 한쪽이 threshold(85¢) 이상이면 그 쪽을 매수

        YES ≥85¢ → YES 매수
        NO ≥85¢ → NO 매수
        """
        if not self.enable_high_price_scalping:
            return None

        time_remaining = ctx.end_time - time.time()

        # 5분 미만만 허용
        if time_remaining >= 300:
            return None

        # 이미 포지션이 있으면 진입 금지
        if ctx.position_yes > 0.1 or ctx.position_no > 0.1:
            return None

        # YES가 threshold(85¢) 이상일 때 → YES를 매수
        if ctx.yes_price >= self.high_price_threshold:
            order_size = self.high_price_scalp_size
            order_value = order_size * ctx.yes_price

            logger.info(f"HIGH PRICE SCALP: YES @ {ctx.yes_price:.3f} (마감 {time_remaining:.0f}s, NO={ctx.no_price:.3f}) - Size: {order_size} shares (${order_value:.2f})")

            return ScalpSignal(
                action="ENTER_YES",
                token_id=ctx.token_yes,
                price=ctx.yes_price,
                size=order_size,
                confidence=0.95,
                edge=self.high_price_profit_pct,
                reason=f"High price scalp: YES @ {ctx.yes_price:.3f} (마감 {time_remaining:.0f}s, target +{self.high_price_profit_pct*100:.0f}%)",
                urgency="HIGH",
                metadata={"is_high_price_scalp": True, "profit_target": self.high_price_profit_pct}
            )

        # NO가 threshold(85¢) 이상일 때 → NO를 매수
        elif ctx.no_price >= self.high_price_threshold:
            order_size = self.high_price_scalp_size
            order_value = order_size * ctx.no_price

            logger.info(f"HIGH PRICE SCALP: NO @ {ctx.no_price:.3f} (마감 {time_remaining:.0f}s, YES={ctx.yes_price:.3f}) - Size: {order_size} shares (${order_value:.2f})")

            return ScalpSignal(
                action="ENTER_NO",
                token_id=ctx.token_no,
                price=ctx.no_price,
                size=order_size,
                confidence=0.95,
                edge=self.high_price_profit_pct,
                reason=f"High price scalp: NO @ {ctx.no_price:.3f} (마감 {time_remaining:.0f}s, target +{self.high_price_profit_pct*100:.0f}%)",
                urgency="HIGH",
                metadata={"is_high_price_scalp": True, "profit_target": self.high_price_profit_pct}
            )

        return None

    def get_position_summary(self, ctx: MarketContext) -> dict:
        """포지션 요약 정보"""
        if ctx.position_yes > 0.1:
            unrealized_pnl_pct = (1.0 - ctx.avg_price_yes - ctx.no_price) / ctx.avg_price_yes
            side = "YES"
            size = ctx.position_yes
            avg_price = ctx.avg_price_yes
            current_exit_price = ctx.no_price
        elif ctx.position_no > 0.1:
            unrealized_pnl_pct = (1.0 - ctx.avg_price_no - ctx.yes_price) / ctx.avg_price_no
            side = "NO"
            size = ctx.position_no
            avg_price = ctx.avg_price_no
            current_exit_price = ctx.yes_price
        else:
            return {
                "has_position": False
            }

        return {
            "has_position": True,
            "side": side,
            "size": size,
            "avg_entry_price": avg_price,
            "current_exit_price": current_exit_price,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "unrealized_pnl_usdc": size * (1.0 - avg_price - current_exit_price),
            "time_remaining": ctx.end_time - time.time()
        }


class AdvancedScalpingStrategy(BTCScalpingStrategy):
    """
    고급 스캘핑 전략

    추가 기능:
    1. 스케일 인/아웃
    2. 트레일링 스톱
    3. 볼륨 분석
    """

    def __init__(self, price_tracker: BTCPriceTracker):
        super().__init__(price_tracker)

        # 고급 파라미터
        self.enable_scale_in = True
        self.max_scale_levels = 2  # 최대 2번까지 추가 진입
        self.scale_in_edge_threshold = 0.10  # 10% 이상 edge면 추가 진입

        self.enable_trailing_stop = True
        self.trailing_stop_distance = 0.02  # 2% 트레일링

        # 트레일링 스톱 추적
        self.best_pnl_seen: dict = {}  # market_id -> best_pnl_pct

    def check_scale_in(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """추가 진입 체크"""
        if not self.enable_scale_in:
            return None

        # 포지션이 없으면 불가능
        if ctx.position_yes < 0.1 and ctx.position_no < 0.1:
            return None

        # 이미 최대 포지션이면 불가능
        total_position = ctx.position_yes + ctx.position_no
        if total_position >= self.max_position_size:
            return None

        # 시간 확인
        remaining = ctx.end_time - time.time()
        if remaining < self.min_time_to_enter:
            return None

        # 마켓 분석
        analysis = self.analyzer.analyze_market_opportunity(
            market_start_time=ctx.start_time,
            market_end_time=ctx.end_time,
            start_price=ctx.start_price,
            yes_price=ctx.yes_price,
            no_price=ctx.no_price
        )

        # Edge가 충분히 높으면 추가 진입
        if analysis["edge"] < self.scale_in_edge_threshold:
            return None

        # 현재 포지션과 같은 방향인지 확인
        predicted = analysis["predicted_outcome"]

        if ctx.position_yes > 0.1 and predicted == "UP":
            return ScalpSignal(
                action="ENTER_YES",
                token_id=ctx.token_yes,
                price=ctx.yes_price,
                size=self.scale_in_size,
                confidence=analysis["confidence"],
                edge=analysis["edge"],
                reason=f"Scale in YES | Edge: {analysis['edge']:.1%}",
                urgency="MEDIUM"
            )
        elif ctx.position_no > 0.1 and predicted == "DOWN":
            return ScalpSignal(
                action="ENTER_NO",
                token_id=ctx.token_no,
                price=ctx.no_price,
                size=self.scale_in_size,
                confidence=analysis["confidence"],
                edge=analysis["edge"],
                reason=f"Scale in NO | Edge: {analysis['edge']:.1%}",
                urgency="MEDIUM"
            )

        return None

    def check_trailing_stop(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """트레일링 스톱 체크"""
        if not self.enable_trailing_stop:
            return None

        # 포지션 없으면 불필요
        if ctx.position_yes < 0.1 and ctx.position_no < 0.1:
            return None

        # 현재 PnL 계산
        if ctx.position_yes > 0.1:
            current_pnl = (1.0 - ctx.avg_price_yes - ctx.no_price) / ctx.avg_price_yes
        else:
            current_pnl = (1.0 - ctx.avg_price_no - ctx.yes_price) / ctx.avg_price_no

        # Best PnL 추적
        if ctx.market_id not in self.best_pnl_seen:
            self.best_pnl_seen[ctx.market_id] = current_pnl
        else:
            if current_pnl > self.best_pnl_seen[ctx.market_id]:
                self.best_pnl_seen[ctx.market_id] = current_pnl

        best_pnl = self.best_pnl_seen[ctx.market_id]

        # Best에서 trailing_stop_distance 이상 하락하면 청산
        if best_pnl > 0 and (best_pnl - current_pnl) > self.trailing_stop_distance:
            if ctx.position_yes > 0.1:
                return ScalpSignal(
                    action="EXIT",
                    token_id=ctx.token_no,
                    price=ctx.no_price,
                    size=ctx.position_yes,
                    confidence=1.0,
                    edge=current_pnl,
                    reason=f"Trailing stop (Best: {best_pnl:.1%}, Now: {current_pnl:.1%})",
                    urgency="HIGH"
                )
            else:
                return ScalpSignal(
                    action="EXIT",
                    token_id=ctx.token_yes,
                    price=ctx.yes_price,
                    size=ctx.position_no,
                    confidence=1.0,
                    edge=current_pnl,
                    reason=f"Trailing stop (Best: {best_pnl:.1%}, Now: {current_pnl:.1%})",
                    urgency="HIGH"
                )

        return None

    def evaluate_market(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """고급 전략 평가"""
        # 0. 긴급 청산 확인 (5분 미만 남으면 모든 포지션 강제 청산)
        time_remaining = ctx.end_time - time.time()

        # 5분 미만: 모든 포지션 강제 청산 후, high price scalping 체크
        if time_remaining < 300:  # 5분 = 300초
            # YES 포지션이 있으면 NO로 unwinding (market order - 즉시 청산)
            if ctx.position_yes > 0.1:
                pnl = ctx.position_yes * (1.0 - ctx.avg_price_yes - ctx.no_price)
                pnl_pct = pnl / (ctx.position_yes * ctx.avg_price_yes) if ctx.avg_price_yes > 0 else 0

                logger.warning(f"⚠️ FORCE UNWIND ({time_remaining:.0f}s left): BUY NO x{ctx.position_yes:.2f} @ {ctx.no_price:.3f} (unwinding YES @ avg {ctx.avg_price_yes:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")

                return ScalpSignal(
                    action="EXIT",
                    token_id=ctx.token_no,
                    price=ctx.no_price,
                    size=ctx.position_yes,
                    confidence=1.0,
                    edge=0.0,
                    reason=f"⚠️ FORCE UNWIND ({time_remaining:.0f}s left) {pnl_pct:+.1%}: BUY NO @ {ctx.no_price:.3f}",
                    urgency="CRITICAL"
                )

            # NO 포지션이 있으면 YES로 unwinding (market order - 즉시 청산)
            elif ctx.position_no > 0.1:
                pnl = ctx.position_no * (1.0 - ctx.avg_price_no - ctx.yes_price)
                pnl_pct = pnl / (ctx.position_no * ctx.avg_price_no) if ctx.avg_price_no > 0 else 0

                logger.warning(f"⚠️ FORCE UNWIND ({time_remaining:.0f}s left): BUY YES x{ctx.position_no:.2f} @ {ctx.yes_price:.3f} (unwinding NO @ avg {ctx.avg_price_no:.3f}) = ${pnl:+.2f} ({pnl_pct:+.1%})")

                return ScalpSignal(
                    action="EXIT",
                    token_id=ctx.token_yes,
                    price=ctx.yes_price,
                    size=ctx.position_no,
                    confidence=1.0,
                    edge=0.0,
                    reason=f"⚠️ FORCE UNWIND ({time_remaining:.0f}s left) {pnl_pct:+.1%}: BUY YES @ {ctx.yes_price:.3f}",
                    urgency="CRITICAL"
                )

            # **포지션이 모두 정리되었으면 (market order로 즉시 청산 완료), high price scalping 체크**
            # AdvancedScalpingStrategy도 ctx.position으로 관리하므로 위에서 EXIT 반환하면 봇이 포지션 제거함
            # 다음 cycle에 여기 도달 = 포지션 정리 완료
            high_price_signal = self._check_high_price_scalping(ctx)
            if high_price_signal:
                return high_price_signal

            # 5분 미만이면 일반 진입/청산은 하지 않음
            return None

        # 1. 트레일링 스톱 체크
        trailing = self.check_trailing_stop(ctx)
        if trailing:
            return trailing

        # 2. 기본 청산 체크
        exit_signal = self.check_exit(ctx)
        if exit_signal:
            return exit_signal

        # 3. 추가 진입 체크
        scale = self.check_scale_in(ctx)
        if scale:
            return scale

        # 4. 신규 진입 체크
        entry = self.check_entry(ctx)
        if entry:
            return entry

        return None

    def _check_high_price_scalping(self, ctx: MarketContext) -> Optional[ScalpSignal]:
        """
        하이 프라이스 스캘핑 전략
        5분 미만 남았을 때, 한쪽이 threshold(85¢) 이상이면 그 쪽을 매수 (승리 확률 높은 쪽)

        YES ≥85¢ → YES 매수
        NO ≥85¢ → NO 매수
        """
        if not self.enable_high_price_scalping:
            return None

        time_remaining = ctx.end_time - time.time()

        # 5분 미만만 허용
        if time_remaining >= 300:
            return None

        # 이미 포지션이 있으면 진입 금지
        if ctx.position_yes > 0.1 or ctx.position_no > 0.1:
            return None

        # YES가 threshold(85¢) 이상일 때 → YES를 매수 (승리 확률 높은 쪽)
        if ctx.yes_price >= self.high_price_threshold:
            order_size = self.high_price_scalp_size
            order_value = order_size * ctx.yes_price

            logger.info(f"HIGH PRICE SCALP: YES @ {ctx.yes_price:.3f} (마감 {time_remaining:.0f}s, NO={ctx.no_price:.3f}) - Size: {order_size} shares (${order_value:.2f})")

            return ScalpSignal(
                action="ENTER_YES",
                token_id=ctx.token_yes,
                price=ctx.yes_price,
                size=order_size,
                confidence=0.95,  # 85¢+ 이면 승리 확률 매우 높음
                edge=self.high_price_profit_pct,
                reason=f"High price scalp: YES @ {ctx.yes_price:.3f} (마감 {time_remaining:.0f}s, target +{self.high_price_profit_pct*100:.0f}%)",
                urgency="HIGH",
                metadata={"is_high_price_scalp": True, "profit_target": self.high_price_profit_pct}
            )

        # NO가 threshold(85¢) 이상일 때 → NO를 매수 (승리 확률 높은 쪽)
        elif ctx.no_price >= self.high_price_threshold:
            order_size = self.high_price_scalp_size
            order_value = order_size * ctx.no_price

            logger.info(f"HIGH PRICE SCALP: NO @ {ctx.no_price:.3f} (마감 {time_remaining:.0f}s, YES={ctx.yes_price:.3f}) - Size: {order_size} shares (${order_value:.2f})")

            return ScalpSignal(
                action="ENTER_NO",
                token_id=ctx.token_no,
                price=ctx.no_price,
                size=order_size,
                confidence=0.95,  # 85¢+ 이면 승리 확률 매우 높음
                edge=self.high_price_profit_pct,
                reason=f"High price scalp: NO @ {ctx.no_price:.3f} (마감 {time_remaining:.0f}s, target +{self.high_price_profit_pct*100:.0f}%)",
                urgency="HIGH",
                metadata={"is_high_price_scalp": True, "profit_target": self.high_price_profit_pct}
            )

        return None
