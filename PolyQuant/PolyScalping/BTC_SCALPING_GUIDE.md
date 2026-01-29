# BTC 15분 마켓 스캘핑 가이드

## 개요

Polymarket의 BTC 15분 up/down 마켓에서 자동 스캘핑을 수행하는 봇입니다.

### 주요 기능

1. **자동 마켓 발견**: BTC 15분 마켓을 자동으로 찾아서 추적
2. **실시간 BTC 가격 추적**: Binance/Coinbase에서 실시간 가격 모니터링
3. **지능형 진입/청산**: 신뢰도와 Edge 기반 자동 거래
4. **리스크 관리**: 손절/익절 자동 실행

### 전략 특징

- **빠른 거래**: 1-3분 내 진입/청산
- **작은 Edge**: 5%+ edge만 있어도 진입
- **빠른 손절**: -5% 손실 시 즉시 청산
- **익절**: +3% 수익 시 자동 청산
- **고급 기능**: 스케일 인/아웃, 트레일링 스톱

---

## 설치 및 설정

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

필요한 패키지:
- `py-clob-client`: Polymarket CLOB API
- `aiohttp`: 비동기 HTTP 클라이언트
- `loguru`: 로깅
- `pydantic`: 설정 관리

### 2. 환경 변수 설정

`.env` 파일에 다음 내용 추가:

```bash
# Polymarket 인증
POLYMARKET_PRIVATE_KEY=your_private_key
POLYMARKET_WALLET_ADDRESS=your_wallet_address

# API 자격증명 (선택사항, 권장)
POLYMARKET_API_KEY=your_api_key
POLYMARKET_API_SECRET=your_api_secret
POLYMARKET_API_PASSPHRASE=your_passphrase

# 프록시 모드 사용 여부
USE_PROXY=true

# 거래 활성화 (테스트 시 false)
TRADING_ENABLED=false

# 리스크 관리
MAX_CONCURRENT_MARKETS=2
DAILY_LOSS_LIMIT_USDC=50.0
```

---

## 사용 방법

### 1. 마켓 스캐너 테스트

현재 활성화된 BTC 15분 마켓 확인:

```bash
python3 btc_market_scanner.py
```

출력 예시:
```
Found 5 active BTC 15m markets:
1. Will BTC be higher in 15m?
   Time Remaining: 12.5 minutes
   Liquidity: $15,234.56
   24h Volume: $45,678.90
```

### 2. BTC 가격 추적기 테스트

실시간 BTC 가격 모니터링:

```bash
python3 btc_price_tracker.py
```

출력 예시:
```
BTC Price: $104,523.45 (+0.0234%)
BTC Price: $104,525.12 (+0.0016%)
BTC Price: $104,520.00 (-0.0049%)
```

### 3. 전략 테스트 (시뮬레이션)

실제 거래 없이 전략 로직 테스트:

```bash
python3 test_scalping_strategy.py
```

4개의 테스트 수트 실행:
- 마켓 스캐너 테스트
- 가격 추적기 테스트
- 전략 로직 테스트
- 통합 플로우 테스트

### 4. 봇 실행 (Dry Run)

거래 없이 봇 실행 (로그만 출력):

`.env`에서 `TRADING_ENABLED=false` 확인 후:

```bash
python3 btc_scalping_bot.py
```

### 5. 실전 거래

**⚠️ 주의: 실제 자금이 사용됩니다!**

1. `.env`에서 `TRADING_ENABLED=true` 설정
2. 소액으로 테스트 시작 (MAX_CONCURRENT_MARKETS=1)
3. 봇 실행:

```bash
python3 btc_scalping_bot.py
```

---

## 전략 파라미터 조정

`scalping_strategy.py`에서 수정 가능:

```python
class BTCScalpingStrategy:
    def __init__(self, price_tracker: BTCPriceTracker):
        # 스캘핑 파라미터
        self.min_edge = 0.05           # 5% 최소 edge
        self.take_profit_pct = 0.03    # 3% 익절
        self.stop_loss_pct = 0.05      # 5% 손절
        self.min_confidence = 0.5      # 50% 최소 신뢰도

        # 포지션 관리
        self.max_position_size = 20    # 최대 20 shares
        self.scale_in_size = 10        # 10 shares씩 진입

        # 타이밍
        self.min_time_to_enter = 180   # 3분 전까지 진입
        self.force_exit_time = 60      # 1분 전 강제 청산
```

### 전략별 선택

**Basic Strategy** (보수적):
```python
bot = BTCScalpingBot(use_advanced_strategy=False)
```

**Advanced Strategy** (공격적):
```python
bot = BTCScalpingBot(use_advanced_strategy=True)
```

고급 전략 추가 기능:
- 스케일 인: Edge가 10% 이상이면 추가 진입
- 트레일링 스톱: 최고 수익에서 2% 하락 시 청산

---

## 리스크 관리

### 1. 포지션 사이즈

- 기본: 10 shares (약 $5 리스크)
- 최대: 20 shares (스케일 인 포함)

### 2. 손절/익절

- **익절**: +3% 수익 시 자동 청산
- **손절**: -5% 손실 시 자동 청산
- **시간 청산**: 만료 1분 전 강제 청산

### 3. 일일 손실 한도

`.env`에서 설정:
```bash
DAILY_LOSS_LIMIT_USDC=50.0
```

일일 손실이 $50에 도달하면 봇 자동 중지

### 4. 동시 마켓 제한

```bash
MAX_CONCURRENT_MARKETS=2
```

최대 2개 마켓만 동시 거래

---

## 모니터링

### 실시간 로그

봇 실행 중 다음 정보 출력:

```
[market_id] YES 10.0 @ 0.450 | PnL: +2.5% ($0.25) | Exit: 0.525 | 180s left
```

- 포지션 사이드 (YES/NO)
- 포지션 크기
- 평균 진입 가격
- 실시간 PnL (% 및 USDC)
- 청산 가격
- 남은 시간

### 통계

봇 종료 시 통계 출력:

```
TRADING STATISTICS
Total Trades: 15
Winning Trades: 10
Win Rate: 66.7%
Total PnL: $12.50
```

---

## 문제 해결

### 1. "No BTC price available"

**원인**: 외부 거래소 API 접속 실패

**해결**:
- 인터넷 연결 확인
- Binance/Coinbase API 상태 확인
- 방화벽 설정 확인

### 2. "No active BTC 15m markets found"

**원인**: 현재 활성화된 15분 마켓이 없음

**해결**:
- 시간대 확인 (거래 활발한 시간)
- 마켓이 생성될 때까지 대기
- 검색 쿼리 수정 (`btc_market_scanner.py`)

### 3. 주문 실패

**원인**: API 인증 문제 또는 잔액 부족

**해결**:
- `.env` 파일의 인증 정보 확인
- 지갑 잔액 확인
- API 권한 확인

### 4. WebSocket 연결 끊김

**원인**: 네트워크 불안정

**해결**:
- 자동 재연결 (봇이 자동 처리)
- 안정적인 네트워크 환경 사용

---

## 고급 사용법

### 1. 커스텀 전략 만들기

`scalping_strategy.py`를 상속하여 커스텀 전략 작성:

```python
class MyCustomStrategy(BTCScalpingStrategy):
    def check_entry(self, ctx: MarketContext):
        # 커스텀 진입 로직
        signal = super().check_entry(ctx)

        # 추가 필터링
        if signal and self._my_custom_filter(ctx):
            return signal
        return None

    def _my_custom_filter(self, ctx):
        # 커스텀 필터 로직
        return True
```

### 2. 알림 추가

Telegram/Discord 알림 추가:

```python
def on_trade_executed(signal, pnl):
    # Telegram 메시지 전송
    send_telegram_message(f"Trade: {signal.action} | PnL: ${pnl:+.2f}")
```

### 3. 백테스팅

과거 데이터로 전략 테스트:

```python
# 과거 마켓 데이터 로드
historical_markets = load_historical_data()

# 시뮬레이션 실행
for market in historical_markets:
    result = simulate_strategy(market)
    print(f"PnL: ${result.pnl}")
```

---

## 주의사항

1. **실전 투자 전 충분한 테스트 필수**
2. **소액으로 시작하여 전략 검증**
3. **시장 변동성에 따라 파라미터 조정 필요**
4. **API Rate Limit 주의**
5. **지갑 보안 유지**

---

## 라이센스 및 면책

이 봇은 교육 목적으로 제공됩니다. 실제 거래로 인한 손실에 대해 개발자는 책임지지 않습니다.

**투자 결정은 본인의 책임입니다.**

---

## 지원

문제가 발생하면:
1. 로그 확인 (`arbitrage_scanner.log`)
2. GitHub Issues 등록
3. 커뮤니티 포럼 질문

---

**Happy Trading! 🚀**
