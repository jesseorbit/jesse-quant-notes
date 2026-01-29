"""
BTC 15분 Up/Down 마켓 스캐너
실시간으로 비트코인 15분 마켓을 찾아서 거래 가능한 마켓을 식별합니다.
"""
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Optional
from loguru import logger
from clients import PolymarketClient
import json


class BTCMarketScanner:
    """비트코인 15분 마켓 전용 스캐너"""

    def __init__(self):
        self.client = PolymarketClient()

    async def find_active_btc_15m_markets(self, limit: int = 50) -> List[Dict]:
        """
        활성화된 BTC 15분 up/down 마켓 찾기

        Returns:
            List of market dicts with additional metadata
        """
        logger.info("Searching for BTC 15m markets...")

        # 여러 검색어로 시도
        search_queries = [
            "BTC 15m up down",
            "Bitcoin 15m",
            "BTC 15 minute",
            "bitcoin 15 minutes"
        ]

        all_markets = []
        seen_ids = set()

        for query in search_queries:
            markets = await self.client.search_markets(query, limit=limit)

            for market in markets:
                market_id = market.get("id")
                if market_id in seen_ids:
                    continue

                # BTC 15분 마켓인지 확인
                if self._is_btc_15m_market(market):
                    seen_ids.add(market_id)
                    all_markets.append(market)

        # 만료 시간으로 정렬 (가장 가까운 것부터)
        all_markets.sort(key=lambda m: m.get("endDate", ""))

        logger.info(f"Found {len(all_markets)} active BTC 15m markets")
        return all_markets

    def _is_btc_15m_market(self, market: Dict) -> bool:
        """마켓이 BTC 15분 마켓인지 확인"""
        question = market.get("question", "").lower()
        slug = market.get("slug", "").lower()
        description = market.get("description", "").lower()

        # BTC/Bitcoin 키워드 확인
        has_btc = any(keyword in question or keyword in slug
                     for keyword in ["btc", "bitcoin"])

        if not has_btc:
            return False

        # 15분 키워드 확인
        has_15m = any(keyword in question or keyword in slug or keyword in description
                     for keyword in ["15m", "15 m", "15 min", "15min", "fifteen"])

        if not has_15m:
            return False

        # up/down 확인 (바이너리 마켓)
        has_updown = ("up" in question or "down" in question or
                     "higher" in question or "lower" in question)

        # 토큰 개수 확인 (바이너리는 2개)
        clob_ids = json.loads(market.get("clobTokenIds", "[]"))
        if not clob_ids and "tokens" in market:
            clob_ids = [t.get("id") for t in market.get("tokens", [])]

        is_binary = len(clob_ids) == 2

        # 활성 상태 확인
        is_active = market.get("active", False) and not market.get("closed", True)

        # 만료 시간 확인
        end_date = market.get("endDate")
        if end_date:
            try:
                end_ts = datetime.fromisoformat(end_date.replace("Z", "+00:00")).timestamp()
                now_ts = datetime.now(timezone.utc).timestamp()

                # 아직 만료되지 않았고, 5분 이상 남은 경우
                time_remaining = end_ts - now_ts
                has_time = 0 < time_remaining < 3600  # 1시간 이내
            except:
                has_time = False
        else:
            has_time = False

        return is_binary and is_active and has_time

    async def get_market_details(self, market: Dict) -> Dict:
        """마켓의 상세 정보 추출"""
        market_id = market.get("id")
        question = market.get("question")
        end_date = market.get("endDate")

        # 토큰 ID 추출
        clob_ids = json.loads(market.get("clobTokenIds", "[]"))
        if not clob_ids and "tokens" in market:
            clob_ids = [t.get("id") for t in market.get("tokens", [])]

        # 결과 라벨 추출
        outcomes = json.loads(market.get("outcomes", "[]"))

        # 만료까지 남은 시간 계산
        if end_date:
            try:
                end_ts = datetime.fromisoformat(end_date.replace("Z", "+00:00")).timestamp()
                now_ts = datetime.now(timezone.utc).timestamp()
                minutes_remaining = (end_ts - now_ts) / 60
            except:
                minutes_remaining = 0
        else:
            minutes_remaining = 0

        # 유동성 정보
        liquidity = float(market.get("liquidity", 0))
        volume = float(market.get("volume", 0))
        volume24hr = float(market.get("volume24hr", 0))

        return {
            "id": market_id,
            "question": question,
            "slug": market.get("slug"),
            "condition_id": market.get("conditionId"),
            "end_date": end_date,
            "minutes_remaining": round(minutes_remaining, 2),
            "token_yes": clob_ids[0] if len(clob_ids) > 0 else None,
            "token_no": clob_ids[1] if len(clob_ids) > 1 else None,
            "outcome_yes": outcomes[0] if len(outcomes) > 0 else "YES",
            "outcome_no": outcomes[1] if len(outcomes) > 1 else "NO",
            "liquidity": liquidity,
            "volume": volume,
            "volume24hr": volume24hr,
            "spread_pct": self._estimate_spread(market),
        }

    def _estimate_spread(self, market: Dict) -> float:
        """스프레드 추정 (데이터가 있으면)"""
        # 실제로는 orderbook에서 가져와야 하지만,
        # 여기서는 유동성 기반으로 대략적인 추정
        liquidity = float(market.get("liquidity", 0))

        if liquidity > 10000:
            return 0.01  # 1% (높은 유동성)
        elif liquidity > 5000:
            return 0.02  # 2%
        elif liquidity > 1000:
            return 0.03  # 3%
        else:
            return 0.05  # 5% (낮은 유동성)

    async def monitor_markets(self, callback=None, interval: int = 10):
        """
        지속적으로 마켓 모니터링

        Args:
            callback: 새 마켓 발견 시 호출될 함수
            interval: 스캔 간격 (초)
        """
        seen_markets = set()

        logger.info(f"Starting continuous market monitoring (interval: {interval}s)")

        while True:
            try:
                markets = await self.find_active_btc_15m_markets()

                for market in markets:
                    market_id = market.get("id")

                    # 새로운 마켓 발견
                    if market_id not in seen_markets:
                        seen_markets.add(market_id)
                        details = await self.get_market_details(market)

                        logger.info(
                            f"New market found: {details['question']} "
                            f"| {details['minutes_remaining']}m remaining "
                            f"| Liquidity: ${details['liquidity']:,.0f}"
                        )

                        if callback:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(details)
                            else:
                                callback(details)

                # 만료된 마켓 정리
                seen_markets = {mid for mid in seen_markets
                              if any(m.get("id") == mid for m in markets)}

                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Error in market monitoring: {e}")
                await asyncio.sleep(interval)


async def main():
    """테스트용 메인 함수"""
    scanner = BTCMarketScanner()

    # 현재 활성 마켓 찾기
    markets = await scanner.find_active_btc_15m_markets()

    if not markets:
        logger.warning("No active BTC 15m markets found")
        return

    logger.info(f"\n{'='*100}")
    logger.info(f"Found {len(markets)} active BTC 15m markets:")
    logger.info(f"{'='*100}\n")

    for idx, market in enumerate(markets[:5], 1):  # 상위 5개만 표시
        details = await scanner.get_market_details(market)

        logger.info(f"{idx}. {details['question']}")
        logger.info(f"   ID: {details['id']}")
        logger.info(f"   Time Remaining: {details['minutes_remaining']:.1f} minutes")
        logger.info(f"   Liquidity: ${details['liquidity']:,.2f}")
        logger.info(f"   24h Volume: ${details['volume24hr']:,.2f}")
        logger.info(f"   Estimated Spread: {details['spread_pct']:.1%}")
        logger.info(f"   Token YES: {details['token_yes']}")
        logger.info(f"   Token NO: {details['token_no']}")
        logger.info(f"   Outcomes: {details['outcome_yes']} / {details['outcome_no']}")
        logger.info(f"{'-'*100}\n")


if __name__ == "__main__":
    asyncio.run(main())
