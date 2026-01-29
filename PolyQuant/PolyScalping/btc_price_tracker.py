"""
실시간 비트코인 가격 추적 모듈
외부 거래소(Binance, Coinbase)에서 BTC 가격을 가져와서
15분 마켓의 예상 결과를 추정하는데 사용
"""
import asyncio
import aiohttp
import time
from typing import Optional, Callable, List
from loguru import logger
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class PriceSnapshot:
    """가격 스냅샷"""
    timestamp: float
    price: float
    source: str


class BTCPriceTracker:
    """
    실시간 BTC 가격 추적기
    여러 소스에서 가격을 가져와서 평균값 사용
    """

    def __init__(self):
        self.current_price: Optional[float] = None
        self.price_history: List[PriceSnapshot] = []
        self.callbacks: List[Callable] = []
        self.running = False
        self.last_update = 0
        self.update_interval = 1  # 1초마다 업데이트

    def add_callback(self, callback: Callable):
        """가격 업데이트 콜백 등록"""
        self.callbacks.append(callback)

    async def start(self):
        """추적 시작"""
        self.running = True
        logger.info("Starting BTC price tracker...")
        asyncio.create_task(self._update_loop())

    async def stop(self):
        """추적 중지"""
        self.running = False
        logger.info("BTC price tracker stopped")

    async def _update_loop(self):
        """가격 업데이트 루프"""
        while self.running:
            try:
                await self._fetch_and_update()
                await asyncio.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in price update loop: {e}")
                await asyncio.sleep(5)

    async def _fetch_and_update(self):
        """여러 소스에서 가격 가져오기"""
        prices = []

        # Binance
        binance_price = await self._fetch_binance()
        if binance_price:
            prices.append(binance_price)

        # Coinbase
        coinbase_price = await self._fetch_coinbase()
        if coinbase_price:
            prices.append(coinbase_price)

        # 평균 계산
        if prices:
            avg_price = sum(prices) / len(prices)
            old_price = self.current_price
            self.current_price = avg_price
            self.last_update = time.time()

            # 히스토리 저장 (최대 1000개)
            self.price_history.append(
                PriceSnapshot(
                    timestamp=time.time(),
                    price=avg_price,
                    source="average"
                )
            )
            if len(self.price_history) > 1000:
                self.price_history = self.price_history[-1000:]

            # 콜백 실행 (가격이 변경된 경우)
            if old_price != avg_price:
                for callback in self.callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(avg_price, old_price)
                        else:
                            callback(avg_price, old_price)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")

    async def _fetch_binance(self) -> Optional[float]:
        """Binance에서 BTC 가격 가져오기"""
        try:
            url = "https://api.binance.com/api/v3/ticker/price"
            params = {"symbol": "BTCUSDT"}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = float(data.get("price", 0))
                        if price > 0:
                            return price
        except Exception as e:
            logger.debug(f"Failed to fetch from Binance: {e}")
        return None

    async def _fetch_coinbase(self) -> Optional[float]:
        """Coinbase에서 BTC 가격 가져오기"""
        try:
            url = "https://api.coinbase.com/v2/prices/BTC-USD/spot"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = float(data.get("data", {}).get("amount", 0))
                        if price > 0:
                            return price
        except Exception as e:
            logger.debug(f"Failed to fetch from Coinbase: {e}")
        return None

    def get_current_price(self) -> Optional[float]:
        """현재 가격 조회"""
        return self.current_price

    def get_price_change_since(self, seconds_ago: int) -> Optional[float]:
        """
        N초 전 대비 가격 변화율

        Returns:
            변화율 (예: 0.005 = 0.5% 상승)
        """
        if not self.price_history or not self.current_price:
            return None

        cutoff_time = time.time() - seconds_ago

        # 가장 가까운 과거 가격 찾기
        for snapshot in reversed(self.price_history):
            if snapshot.timestamp <= cutoff_time:
                old_price = snapshot.price
                return (self.current_price - old_price) / old_price

        return None

    def predict_15m_outcome(self, start_price: float, current_price: Optional[float] = None) -> str:
        """
        15분 마켓 결과 예측

        Args:
            start_price: 마켓 시작 시점의 BTC 가격
            current_price: 현재 가격 (None이면 추적 중인 가격 사용)

        Returns:
            "UP" or "DOWN"
        """
        if current_price is None:
            current_price = self.current_price

        if current_price is None or start_price is None:
            return "UNKNOWN"

        if current_price > start_price:
            return "UP"
        elif current_price < start_price:
            return "DOWN"
        else:
            return "FLAT"

    def get_price_direction_confidence(self, start_price: float, lookback_seconds: int = 60) -> float:
        """
        가격 방향성 신뢰도 계산

        Args:
            start_price: 기준 가격
            lookback_seconds: 과거 몇 초를 볼지

        Returns:
            0.0 ~ 1.0 (1.0 = 매우 확실한 방향성)
        """
        if not self.current_price:
            return 0.0

        # 최근 가격 변화 추세 분석
        recent_changes = []
        cutoff = time.time() - lookback_seconds

        for i in range(1, len(self.price_history)):
            snapshot = self.price_history[-i]
            if snapshot.timestamp < cutoff:
                break

            prev_snapshot = self.price_history[-i - 1]
            change = snapshot.price - prev_snapshot.price
            recent_changes.append(1 if change > 0 else -1 if change < 0 else 0)

        if not recent_changes:
            return 0.0

        # 일관성 계산
        positive_count = sum(1 for c in recent_changes if c > 0)
        negative_count = sum(1 for c in recent_changes if c < 0)
        total = len(recent_changes)

        consistency = max(positive_count, negative_count) / total

        # 변화 크기 고려
        price_change_pct = abs((self.current_price - start_price) / start_price)

        # 변화가 클수록, 일관성이 높을수록 신뢰도 상승
        confidence = min(consistency * (1 + price_change_pct * 10), 1.0)

        return confidence


class MarketPriceAnalyzer:
    """
    15분 마켓의 가격을 분석하고 거래 신호 생성
    """

    def __init__(self, price_tracker: BTCPriceTracker):
        self.tracker = price_tracker

    def analyze_market_opportunity(
        self,
        market_start_time: float,
        market_end_time: float,
        start_price: float,
        yes_price: float,
        no_price: float
    ) -> dict:
        """
        마켓 기회 분석

        Returns:
            dict with:
            - predicted_outcome: "UP" or "DOWN"
            - confidence: 0.0 ~ 1.0
            - edge: 예상 수익률
            - should_trade: 거래 권장 여부
        """
        current_price = self.tracker.get_current_price()
        if not current_price:
            return {
                "predicted_outcome": "UNKNOWN",
                "confidence": 0.0,
                "edge": 0.0,
                "should_trade": False,
                "reason": "No price data"
            }

        # 현재까지의 방향 예측
        predicted = self.tracker.predict_15m_outcome(start_price, current_price)

        # 신뢰도 계산
        elapsed = time.time() - market_start_time
        remaining = market_end_time - time.time()

        # 시간이 많이 지나갈수록 예측 신뢰도 상승
        time_confidence = elapsed / (elapsed + remaining)

        # 가격 변화 일관성 기반 신뢰도
        direction_confidence = self.tracker.get_price_direction_confidence(start_price, lookback_seconds=int(elapsed))

        # 종합 신뢰도
        overall_confidence = (time_confidence * 0.3 + direction_confidence * 0.7)

        # Edge 계산
        if predicted == "UP":
            # UP이 예상되면 YES 토큰의 가치는 1.0
            # 현재 YES 가격이 0.6이고 예상 가치가 1.0이면
            # edge = (1.0 - 0.6) / 0.6 = 0.667 (66.7% 수익)
            expected_value = 1.0
            cost = yes_price
            edge = (expected_value - cost) / cost if cost > 0 else 0
            best_side = "YES"
        elif predicted == "DOWN":
            expected_value = 1.0
            cost = no_price
            edge = (expected_value - cost) / cost if cost > 0 else 0
            best_side = "NO"
        else:
            edge = 0
            best_side = None

        # 가격 합이 1에 가까운지 확인 (시장 효율성)
        price_sum = yes_price + no_price
        market_efficiency = abs(1.0 - price_sum)

        # 거래 조건
        should_trade = (
            overall_confidence > 0.6 and  # 신뢰도 60% 이상
            edge > 0.15 and  # 15% 이상 edge
            remaining > 120 and  # 2분 이상 남음
            market_efficiency < 0.05  # 시장 효율성 양호
        )

        return {
            "predicted_outcome": predicted,
            "confidence": overall_confidence,
            "edge": edge,
            "should_trade": should_trade,
            "best_side": best_side,
            "time_confidence": time_confidence,
            "direction_confidence": direction_confidence,
            "remaining_seconds": remaining,
            "current_btc_price": current_price,
            "start_btc_price": start_price,
            "price_change_pct": (current_price - start_price) / start_price,
            "reason": self._get_reason(should_trade, overall_confidence, edge, remaining)
        }

    def _get_reason(self, should_trade: bool, confidence: float, edge: float, remaining: float) -> str:
        """거래 여부에 대한 이유"""
        if not should_trade:
            if confidence < 0.6:
                return f"Low confidence ({confidence:.1%})"
            elif edge < 0.15:
                return f"Insufficient edge ({edge:.1%})"
            elif remaining < 120:
                return f"Too close to expiry ({remaining:.0f}s)"
            else:
                return "Market inefficiency detected"
        else:
            return f"Good opportunity: {confidence:.1%} confidence, {edge:.1%} edge"


async def main():
    """테스트"""
    tracker = BTCPriceTracker()

    def on_price_update(new_price, old_price):
        if old_price:
            change = new_price - old_price
            change_pct = (change / old_price) * 100
            logger.info(f"BTC Price: ${new_price:,.2f} ({change_pct:+.4f}%)")
        else:
            logger.info(f"BTC Price: ${new_price:,.2f}")

    tracker.add_callback(on_price_update)
    await tracker.start()

    # 30초 동안 추적
    logger.info("Tracking BTC price for 30 seconds...")
    await asyncio.sleep(30)

    # 15분 마켓 시뮬레이션
    logger.info("\n=== 15분 마켓 시뮬레이션 ===")
    start_price = tracker.get_current_price()
    logger.info(f"Market start price: ${start_price:,.2f}")

    analyzer = MarketPriceAnalyzer(tracker)

    # 10초 후 분석
    await asyncio.sleep(10)

    analysis = analyzer.analyze_market_opportunity(
        market_start_time=time.time() - 10,
        market_end_time=time.time() + 890,  # 15분 - 10초
        start_price=start_price,
        yes_price=0.55,
        no_price=0.47
    )

    logger.info(f"\n분석 결과:")
    logger.info(f"  예측: {analysis['predicted_outcome']}")
    logger.info(f"  신뢰도: {analysis['confidence']:.1%}")
    logger.info(f"  Edge: {analysis['edge']:.1%}")
    logger.info(f"  거래 권장: {analysis['should_trade']}")
    logger.info(f"  이유: {analysis['reason']}")

    await tracker.stop()


if __name__ == "__main__":
    asyncio.run(main())
