# 🚀 BTC 15분 마켓 스캘핑 봇 (웹 UI 포함)

Polymarket의 비트코인 15분 up/down 마켓에서 자동 스캘핑을 수행하는 완전한 거래 시스템입니다.

## ✨ 주요 특징

### 🌐 **웹 대시보드 (NEW!)**
- ✅ 실시간 거래 체결 내역 표시
- ✅ WebSocket 기반 즉시 업데이트
- ✅ 브라우저에서 봇 시작/중지 제어
- ✅ 모바일 반응형 지원
- ✅ PnL, 승률 실시간 통계

### 🤖 **자동 거래 시스템**
- ✅ BTC 15분 마켓 자동 발견
- ✅ Binance/Coinbase 실시간 가격 추적
- ✅ 지능형 진입/청산 전략
- ✅ 리스크 관리 (손절/익절)

### 📊 **전략 기능**
- ✅ 기본 전략: 5%+ edge, ±3% TP/SL
- ✅ 고급 전략: 스케일 인/아웃, 트레일링 스톱
- ✅ 방향 전환 감지
- ✅ 파라미터 커스터마이징

---

## 📁 프로젝트 구조

```
PolyScalping/
├── btc_web_server.py           # 🌐 웹 UI 서버 (메인)
├── btc_scalping_bot.py          # 🤖 통합 스캘핑 봇
├── btc_market_scanner.py        # 🔍 마켓 스캐너
├── btc_price_tracker.py         # 📈 가격 추적기
├── scalping_strategy.py         # 🎯 전략 로직
├── test_scalping_strategy.py   # 🧪 테스트 스위트
├── test_specific_market.py      # 🔬 특정 마켓 테스트
│
├── clients.py                   # Polymarket 클라이언트
├── tracker.py                   # 오더북 추적기
├── config.py                    # 설정 관리
├── models.py                    # 데이터 모델
│
├── START_WEB_UI.md             # 🌐 웹 UI 빠른 시작 ⭐
├── WEB_UI_GUIDE.md             # 🌐 웹 UI 상세 가이드
├── QUICK_START.md              # ⚡ 봇 빠른 시작
├── BTC_SCALPING_GUIDE.md       # 📚 전략 가이드
│
├── requirements.txt             # 의존성
└── .env                         # 환경 변수
```

---

## 🚀 빠른 시작 (웹 UI)

### 1. 설치

```bash
# 의존성 설치
pip install -r requirements.txt
```

### 2. 설정

`.env` 파일 생성:

```bash
# Polymarket 인증
POLYMARKET_PRIVATE_KEY=your_private_key
POLYMARKET_WALLET_ADDRESS=your_wallet_address

# API 자격증명 (선택사항)
POLYMARKET_API_KEY=your_api_key
POLYMARKET_API_SECRET=your_api_secret
POLYMARKET_API_PASSPHRASE=your_passphrase

# 거래 설정
TRADING_ENABLED=false  # Dry Run
MAX_CONCURRENT_MARKETS=2
DAILY_LOSS_LIMIT_USDC=50.0
```

### 3. 웹 서버 시작

```bash
python3 btc_web_server.py
```

### 4. 브라우저 접속

```
http://localhost:8000
```

**완료!** 웹 대시보드에서 모든 것을 제어할 수 있습니다.

---

## 📊 웹 대시보드 스크린샷

```
┌──────────────────────────────────────────────────────────┐
│ 🚀 BTC Scalping Bot                                      │
│ Real-time 15-minute market trading dashboard             │
├──────────────────────────────────────────────────────────┤
│  Bot Status    BTC Price      Total PnL     Win Rate    │
│  🟢 RUNNING    $90,913.99     +$12.50       66.7%       │
├──────────────────────────────────────────────────────────┤
│  [▶ Start]  [⏹ Stop]  [🔄 Refresh]      🟢 Connected   │
├──────────────────────────────────────────────────────────┤
│  📊 Active Markets (2)                                   │
│                                                          │
│  Bitcoin Up or Down - Jan 20, 1:15-1:30 ET              │
│  YES: 0.565    NO: 0.435    Time: 12m 30s               │
│  Position: YES 10  |  PnL: +2.5% ($0.25)                │
├──────────────────────────────────────────────────────────┤
│  💰 Recent Trades                                        │
│                                                          │
│  EXIT | YES x10 @ 0.525 .................. +$0.75       │
│  ENTER_YES | YES x10 @ 0.450 ............. +$0.00       │
└──────────────────────────────────────────────────────────┘
```

---

## 🎯 사용 모드

### 모드 1: 웹 UI로 모니터링 (권장) ⭐

```bash
python3 btc_web_server.py
```

**장점:**
- 실시간 대시보드
- 브라우저에서 제어
- 모바일 접속 가능
- 거래 내역 시각화

### 모드 2: CLI로 실행

```bash
python3 btc_scalping_bot.py
```

**장점:**
- 가벼움 (GUI 없음)
- 서버 환경에 적합
- 터미널 로그만

### 모드 3: 테스트/시뮬레이션

```bash
python3 test_scalping_strategy.py
```

**용도:**
- 전략 검증
- 파라미터 튜닝
- 백테스팅

---

## ⚙️ 주요 기능

### 1. 실시간 BTC 가격 추적

```python
from btc_price_tracker import BTCPriceTracker

tracker = BTCPriceTracker()
await tracker.start()

price = tracker.get_current_price()  # $90,913.99
change = tracker.get_price_change_since(60)  # 60초 전 대비
```

**특징:**
- Binance + Coinbase 평균
- 1초마다 업데이트
- 가격 히스토리 저장

### 2. 마켓 스캐너

```python
from btc_market_scanner import BTCMarketScanner

scanner = BTCMarketScanner()
markets = await scanner.find_active_btc_15m_markets()

for market in markets:
    print(market.get('question'))
    print(f"Liquidity: ${market.get('liquidity'):,.0f}")
```

**필터링:**
- BTC 관련 마켓만
- 15분 마켓만
- 활성 + 최소 5분 남은 마켓
- 유동성 높은 마켓 우선

### 3. 스캘핑 전략

#### 기본 전략

```python
from scalping_strategy import BTCScalpingStrategy

strategy = BTCScalpingStrategy(price_tracker)

# 진입 조건
min_edge = 0.05        # 5% edge
min_confidence = 0.5   # 50% 신뢰도

# 청산 조건
take_profit = 0.03     # +3%
stop_loss = 0.05       # -5%
```

#### 고급 전략

```python
from scalping_strategy import AdvancedScalpingStrategy

strategy = AdvancedScalpingStrategy(price_tracker)

# 추가 기능
- 스케일 인 (10%+ edge)
- 트레일링 스톱 (2% 거리)
- 방향 전환 감지
```

### 4. 웹 UI 실시간 업데이트

**WebSocket 이벤트:**

```javascript
ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    if (msg.type === 'trade_executed') {
        // 거래 체결 → 즉시 표시
    } else if (msg.type === 'signal_generated') {
        // 신호 생성 → 로그 기록
    } else if (msg.type === 'market_update') {
        // 마켓 업데이트 → 가격 갱신
    }
}
```

---

## 📈 전략 파라미터

### 보수적 설정 (안전)

```python
min_edge = 0.10              # 10% edge 필요
min_confidence = 0.7         # 70% 신뢰도
take_profit_pct = 0.02       # 2% 익절
stop_loss_pct = 0.03         # 3% 손절
max_position_size = 10       # 작은 포지션
```

**예상 성과:**
- Win Rate: 70-75%
- 거래 빈도: 낮음
- 리스크: 낮음

### 기본 설정 (균형)

```python
min_edge = 0.05              # 5% edge
min_confidence = 0.5         # 50% 신뢰도
take_profit_pct = 0.03       # 3% 익절
stop_loss_pct = 0.05         # 5% 손절
max_position_size = 20       # 중간 포지션
```

**예상 성과:**
- Win Rate: 60-65%
- 거래 빈도: 중간
- 리스크: 중간

### 공격적 설정 (위험)

```python
min_edge = 0.03              # 3% edge
min_confidence = 0.4         # 40% 신뢰도
take_profit_pct = 0.05       # 5% 익절
stop_loss_pct = 0.07         # 7% 손절
max_position_size = 30       # 큰 포지션
```

**예상 성과:**
- Win Rate: 55-60%
- 거래 빈도: 높음
- 리스크: 높음

---

## 🔒 리스크 관리

### 포지션 제한

```python
max_position_size = 20       # 최대 20 shares
scale_in_size = 10           # 10씩 진입
max_concurrent_markets = 2   # 최대 2개 마켓
```

### 손실 제한

```python
daily_loss_limit = 50.0      # 일일 $50 손실 시 중지
stop_loss_pct = 0.05         # 거래당 -5% 손절
force_exit_time = 60         # 만료 1분 전 강제 청산
```

### 안전 장치

- ✅ 일일 손실 한도 도달 시 자동 중지
- ✅ 만료 임박 시 강제 청산
- ✅ 방향 전환 감지 시 조기 청산
- ✅ Dry Run 모드 지원

---

## 📱 모바일 접속

### 같은 WiFi

1. PC IP 확인:
   ```bash
   ifconfig | grep inet
   ```

2. 모바일 브라우저:
   ```
   http://192.168.1.XXX:8000
   ```

### 외부 접속 (ngrok)

```bash
ngrok http 8000
```

→ `https://abc123.ngrok.io`로 어디서든 접속

---

## 🧪 테스트

### 전체 테스트 스위트

```bash
python3 test_scalping_strategy.py
```

**4가지 테스트:**
1. ✅ 마켓 스캐너
2. ✅ 가격 추적기
3. ✅ 전략 로직
4. ✅ 통합 플로우

### 특정 마켓 테스트

```bash
python3 test_specific_market.py
```

30초 동안 실제 마켓 모니터링

### API 테스트

```bash
# 봇 상태
curl http://localhost:8000/api/status

# 거래 내역
curl http://localhost:8000/api/trades

# 봇 제어
curl -X POST http://localhost:8000/api/control \
  -H "Content-Type: application/json" \
  -d '{"action": "start"}'
```

---

## 📚 문서

### 빠른 시작
- [START_WEB_UI.md](START_WEB_UI.md) - 웹 UI 1분 시작 ⭐
- [QUICK_START.md](QUICK_START.md) - 봇 빠른 시작

### 상세 가이드
- [WEB_UI_GUIDE.md](WEB_UI_GUIDE.md) - 웹 UI 완전 가이드
- [BTC_SCALPING_GUIDE.md](BTC_SCALPING_GUIDE.md) - 전략 상세 가이드

### 코드 문서
- `btc_web_server.py` - 웹 서버 + 봇 통합
- `scalping_strategy.py` - 전략 로직 상세

---

## 🎓 예상 성과

### 기본 전략 (중간 설정)

**조건:**
- 15분 마켓 × 96회/일
- Edge 5%+ 마켓만 진입
- 실제 진입: ~10회/일

**예상:**
- Win Rate: 60%
- 평균 수익: +3%
- 평균 손실: -5%
- 일일 PnL: $5-15 (10 shares 기준)

**월 예상 (20 거래일):**
- 총 거래: 200회
- 승: 120회 (+$360)
- 패: 80회 (-$400)
- **순 손실: -$40**

→ **파라미터 튜닝 필수!**

### 최적화 후

**개선:**
- Edge 임계값 조정 (7%+)
- 승률 향상 (65%)
- 손절 빨리 (-3%)

**예상:**
- Win Rate: 65%
- 월 PnL: **+$50-100**

---

## ⚠️ 주의사항

### 실전 투자 전

1. ✅ Dry Run으로 충분히 테스트
2. ✅ 소액 (10 shares)으로 시작
3. ✅ 파라미터 최적화
4. ✅ 시장 변동성 확인

### 알아두기

- 📉 스캘핑은 승률보다 Risk/Reward 중요
- ⏰ 변동성 높은 시간대 유리 (미국 거래 시간)
- 💧 유동성 $10,000+ 마켓만
- 🔄 지속적인 파라미터 조정 필요

### 면책

- 이 봇은 교육 목적입니다
- 실제 거래 손실에 책임지지 않습니다
- 투자는 본인 책임입니다

---

## 🔧 문제 해결

### 웹 UI 접속 안됨

```bash
# 포트 확인
lsof -i :8000

# 재시작
pkill -f btc_web_server
python3 btc_web_server.py
```

### WebSocket 끊김

- 자동 재연결 (3초 후)
- 수동: F5로 새로고침

### 마켓 찾기 안됨

- 시간대 확인 (거래 활발 시간)
- 검색 쿼리 수정
- API 상태 확인

---

## 🚀 다음 단계

### 단기 (1주일)
1. ✅ Dry Run 테스트
2. ✅ 파라미터 튜닝
3. ✅ 소액 실전 테스트

### 중기 (1개월)
1. 📊 백테스팅 시스템 구축
2. 🔔 알림 시스템 (Telegram)
3. 📈 차트 추가 (PnL, BTC)

### 장기 (3개월)
1. 🤖 ML 가격 예측 모델
2. 🌍 다중 자산 (ETH, SOL)
3. ☁️ 클라우드 배포

---

## 📞 지원

### 문제 발생 시

1. 로그 확인:
   ```bash
   tail -f arbitrage_scanner.log
   ```

2. 이슈 등록:
   - GitHub Issues
   - 스크린샷 + 로그 첨부

3. 커뮤니티:
   - Discord
   - Telegram 그룹

---

## 📜 라이센스

MIT License - 자유롭게 사용, 수정, 배포 가능

---

## 🎉 완성!

**축하합니다!** 이제 완전한 BTC 스캘핑 봇 시스템을 갖추었습니다.

### 시작하기

```bash
# 1. 웹 서버 시작
python3 btc_web_server.py

# 2. 브라우저 접속
open http://localhost:8000

# 3. Start 버튼 클릭!
```

**Happy Scalping! 🚀📈💰**
