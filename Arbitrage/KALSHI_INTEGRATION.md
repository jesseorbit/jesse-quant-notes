# Kalshi Integration Guide

## ✅ Kalshi 추가 완료!

Polymarket-Kalshi 차익거래 스캐너가 준비되었습니다.

---

## 🎯 Kalshi란?

[Kalshi](https://kalshi.com)는 미국 CFTC 규제를 받는 예측 시장 플랫폼입니다.
- 정치, 경제, 날씨, 스포츠 등 다양한 이벤트
- 규제된 거래소로 높은 신뢰도
- 공개 API로 인증 없이 마켓 데이터 접근 가능

---

## 📊 API 정보

### Endpoint
```
https://api.elections.kalshi.com/trade-api/v2/markets
```

### 특징
- ✅ **인증 불필요**: 마켓 데이터는 공개 API
- ✅ **높은 한도**: 한 번에 최대 1000개 마켓 조회
- ✅ **실시간 데이터**: 현재 가격, 거래량 등

### 가격 형식
- Kalshi는 **센트 단위** (0-100)
- 자동으로 0.0-1.0 범위로 변환
- 예: `yes_price: 65` → `0.65`

---

## 🚀 사용법

### 기본 실행 (Polymarket vs Kalshi)
```bash
cd /Users/jessesung/Arbitrage
/Users/jessesung/.venv/bin/python main.py
```

**출력 예시**:
```
INFO - No Opinion Labs API key - scanning Polymarket vs Kalshi only
INFO - Fetching Polymarket markets (limit=100)...
INFO - Fetching Kalshi markets (limit=100)...
INFO - Fetched 311 Polymarket markets
INFO - Fetched 100 Kalshi markets
INFO - === Scanning Polymarket vs Kalshi ===
```

### 3개 플랫폼 모두 스캔
```bash
# Opinion Labs API key 설정
export OPINION_API_KEY="your_key"

# 실행
/Users/jessesung/.venv/bin/python main.py
```

**스캔 조합**:
1. Polymarket vs Kalshi
2. Polymarket vs Opinion Labs
3. Kalshi vs Opinion Labs

---

## 📝 코드 예시

### Kalshi 마켓 가져오기
```python
from services import KalshiCollector

# 수집기 생성 (인증 불필요)
collector = KalshiCollector()

# 마켓 가져오기
markets = collector.fetch_active_markets(limit=50)

print(f"Fetched {len(markets)} Kalshi markets")
for market in markets:
    print(f"- {market.title}")
    print(f"  YES: ${market.price_yes:.2f} | NO: ${market.price_no:.2f}")
    print(f"  Volume: ${market.volume:,.0f}")
```

### 직접 API 호출
```python
import requests

url = "https://api.elections.kalshi.com/trade-api/v2/markets"
params = {"status": "open", "limit": 10}

response = requests.get(url, params=params)
data = response.json()

for market in data["markets"]:
    print(f"{market['ticker']}: {market['title']}")
    print(f"  YES: {market['yes_price']}¢")
```

---

## 🔍 실제 테스트 결과

```bash
$ /Users/jessesung/.venv/bin/python main.py

2025-12-22 15:13:09 - INFO - No Opinion Labs API key - scanning Polymarket vs Kalshi only
2025-12-22 15:13:09 - INFO - Fetching Polymarket markets (limit=100)...
2025-12-22 15:13:09 - INFO - Fetching Kalshi markets (limit=100)...
2025-12-22 15:13:10 - INFO - Fetched 100 Kalshi markets ✅
2025-12-22 15:13:10 - INFO - Fetched 311 Polymarket markets ✅
2025-12-22 15:13:10 - INFO - === Scanning Polymarket vs Kalshi ===
2025-12-22 15:13:10 - INFO - Matching 311 Polymarket vs 100 Kalshi markets...
```

**결과**: 정상 작동! 🎉

---

## 💡 팁

### 매칭률 향상
두 플랫폼이 다른 이벤트를 다룰 수 있으므로:
- `similarity_threshold`를 낮춰보세요 (예: 80.0)
- `min_common_keywords`를 낮춰보세요 (예: 1)

```python
matcher = MarketMatcher(
    similarity_threshold=80.0,  # 기본: 85.0
    min_common_keywords=1       # 기본: 2
)
```

### 더 많은 마켓 가져오기
```python
poly_markets, kalshi_markets, _ = await gather_all_data(
    limit=500,  # 더 많은 마켓
    enable_opinion=False
)
```

---

## 📂 관련 파일

- [`services/kalshi.py`](file:///Users/jessesung/Arbitrage/services/kalshi.py) - Kalshi 수집기
- [`main.py`](file:///Users/jessesung/Arbitrage/main.py) - 멀티 플랫폼 스캐너
- [`README.md`](file:///Users/jessesung/Arbitrage/README.md) - 전체 문서

---

## 🎯 다음 단계

1. ✅ Polymarket 연동 완료
2. ✅ Kalshi 연동 완료
3. ⏳ Opinion Labs API key 대기 중
4. 🔜 실제 차익거래 기회 발견 시 알림 시스템
