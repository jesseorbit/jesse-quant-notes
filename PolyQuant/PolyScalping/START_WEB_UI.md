# 🌐 웹 UI로 BTC 스캘핑 봇 시작하기

## 🎯 최종 사용 가이드

웹 브라우저에서 실시간으로 봇을 모니터링하고 제어할 수 있습니다!

---

## ⚡ 1분 안에 시작하기

### 1단계: 웹 서버 실행

```bash
python3 btc_web_server.py
```

**출력 확인:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
Starting BTC Scalping Bot
BTC price tracker started
⚠️  TRADING DISABLED - Running in DRY RUN mode
Bot ready!
```

### 2단계: 브라우저에서 접속

```
http://localhost:8000
```

### 3단계: 대시보드에서 봇 제어

- **▶ Start** 버튼 클릭 → 봇 시작
- 실시간으로 거래 모니터링
- **⏹ Stop** 버튼 클릭 → 봇 중지

---

## 📊 대시보드 기능

### 실시간 모니터링

웹 UI에서 볼 수 있는 정보:

#### 1. 상태 표시줄
- 🟢 봇 상태 (실행/중지)
- 💰 BTC 현재 가격 (1초마다 업데이트)
- 📈 총 손익 (실시간)
- 🎯 승률 (%)

#### 2. 활성 마켓
```
Bitcoin Up or Down - Jan 20, 1:15-1:30 ET
┌─────────────────────────────────────────┐
│ YES: 0.565    NO: 0.435                 │
│                                         │
│ Position: YES 10 shares                 │
│ PnL: +2.5% ($0.25)                      │
│ Time Left: 12m 30s                      │
└─────────────────────────────────────────┘
```

#### 3. 거래 내역
```
✅ EXIT      | YES x10 @ 0.525    +$0.75    15:23:12
✅ ENTER_YES | YES x10 @ 0.450    +$0.00    15:20:35
✅ EXIT      | NO  x10 @ 0.450    +$0.30    15:18:45
```

#### 4. 이벤트 로그
```
15:23:10  signal  EXIT - Take Profit (+3.2%)
15:23:12  trade   EXIT YES x10 @ 0.525
15:20:33  signal  ENTER_YES - UP predicted (Conf: 65%)
15:20:35  trade   ENTER_YES YES x10 @ 0.450
```

### 실시간 업데이트

WebSocket으로 **즉시** 업데이트:
- ⚡ 거래 체결 → 1초 안에 화면에 표시
- ⚡ 신호 생성 → 이벤트 로그에 즉시 기록
- ⚡ 마켓 가격 → 5초마다 자동 갱신
- ⚡ 봇 상태 → 2초마다 업데이트

---

## 🎮 봇 제어

### 시작/중지

웹 UI에서 버튼 클릭만으로:

```
[▶ Start]  → 봇 시작 (마켓 스캔 및 거래 시작)
[⏹ Stop]   → 봇 중지 (모든 활동 중단)
[🔄 Refresh] → 데이터 새로고침
```

### Dry Run vs 실전 모드

`.env` 파일에서:

```bash
# Dry Run (시뮬레이션)
TRADING_ENABLED=false

# 실전 거래
TRADING_ENABLED=true
```

웹 UI 상단에 표시:
- Dry Run: ⚠️ **TRADING DISABLED - Running in DRY RUN mode**
- 실전: 🟢 **TRADING ENABLED**

---

## 📱 다양한 기기에서 접속

### PC에서

```
http://localhost:8000
```

### 같은 네트워크의 다른 기기 (휴대폰, 태블릿)

1. **PC IP 주소 확인:**

Mac/Linux:
```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

Windows:
```bash
ipconfig
```

예시: `192.168.1.100`

2. **모바일 브라우저에서 접속:**

```
http://192.168.1.100:8000
```

### 외부에서 접속 (선택사항)

**방법 1: ngrok 사용**

```bash
# ngrok 설치
brew install ngrok  # Mac
# 또는 https://ngrok.com/download

# 터널 생성
ngrok http 8000
```

출력:
```
Forwarding  https://abc123.ngrok.io -> http://localhost:8000
```

이제 `https://abc123.ngrok.io`로 어디서든 접속 가능!

**방법 2: 포트 포워딩**

라우터 설정에서:
- 외부 포트: 8000
- 내부 IP: 192.168.1.100
- 내부 포트: 8000

→ `http://YOUR_PUBLIC_IP:8000`으로 접속

---

## 🔔 알림 설정 (선택사항)

### 브라우저 알림

웹 UI에 추가할 수 있는 코드:

```javascript
// 거래 체결 시 브라우저 알림
if (msg.type === 'trade_executed') {
    if (Notification.permission === "granted") {
        new Notification("거래 체결!", {
            body: `${msg.data.action} ${msg.data.side} x${msg.data.size}`,
            icon: "/icon.png"
        });
    }
}
```

### 소리 알림

```javascript
// 거래 체결 시 소리
const audio = new Audio('data:audio/wav;base64,...');
audio.play();
```

---

## 🎨 UI 커스터마이징

### 다크 모드 (기본)

현재 설정:
- 배경: `bg-gray-900` (다크)
- 카드: `bg-gray-800`
- 텍스트: `text-gray-100`

### 라이트 모드로 변경

`btc_web_server.py`의 HTML 부분 수정:

```html
<!-- 기존 -->
<body class="bg-gray-900 text-gray-100">

<!-- 라이트 모드 -->
<body class="bg-gray-50 text-gray-900">
```

### 색상 테마

Tailwind CSS 색상:
- 🟢 수익: `text-green-400`
- 🔴 손실: `text-red-400`
- 🔵 정보: `text-blue-400`
- 🟣 강조: `text-purple-400`

---

## 📊 성능 모니터링

### 시스템 리소스

웹 서버는 가볍습니다:
- CPU: ~5% (idle)
- 메모리: ~150MB
- 네트워크: 거의 없음 (WebSocket 유지)

### 동시 접속

- 기본 제한: 제한 없음
- 권장: 5개 이하 (동일 브라우저 탭)
- WebSocket 연결: 클라이언트당 1개

---

## 🐛 트러블슈팅

### "Cannot connect"

**증상:** 브라우저에서 `localhost:8000`에 접속 안됨

**해결:**
1. 서버가 실행 중인지 확인
   ```bash
   ps aux | grep btc_web_server
   ```
2. 포트가 열려있는지 확인
   ```bash
   lsof -i :8000
   ```
3. 방화벽 확인
   ```bash
   sudo ufw allow 8000
   ```

### "WebSocket disconnected"

**증상:** 🔴 Disconnected 표시

**해결:**
- 자동으로 3초 후 재연결됨
- 수동 새로고침: F5
- 서버 재시작: `Ctrl+C` 후 다시 시작

### "No data showing"

**증상:** 대시보드가 비어있음

**해결:**
1. 봇이 실행 중인지 확인 (Start 버튼)
2. BTC 마켓이 활성화되어 있는지 확인
3. 콘솔 로그 확인 (F12 → Console)

### "Trades not appearing"

**증상:** 거래 히스토리가 비어있음

**원인:**
- Dry Run 모드에서는 시뮬레이션 거래만
- 실제 마켓이 없으면 거래 없음

**확인:**
```bash
# 로그 확인
tail -f arbitrage_scanner.log
```

---

## 📈 실전 사용 예시

### 시나리오 1: 점심시간 모니터링

1. 아침에 서버 시작:
   ```bash
   python3 btc_web_server.py &
   ```

2. 휴대폰으로 접속:
   ```
   http://192.168.1.100:8000
   ```

3. 점심 먹으면서 거래 확인
   - 실시간으로 거래 알림 확인
   - 필요시 Stop 버튼으로 중지

### 시나리오 2: 외출 중 모니터링

1. ngrok으로 외부 접속 활성화:
   ```bash
   ngrok http 8000
   ```

2. 링크 저장:
   ```
   https://abc123.ngrok.io
   ```

3. 어디서든 모바일로 접속
   - 카페, 지하철에서도 확인 가능
   - 봇 제어 가능

### 시나리오 3: 백그라운드 실행

1. tmux/screen으로 세션 생성:
   ```bash
   tmux new -s scalping
   python3 btc_web_server.py
   ```

2. Detach:
   ```
   Ctrl+B, D
   ```

3. 웹 UI는 계속 실행:
   ```
   http://localhost:8000
   ```

4. 필요시 다시 attach:
   ```bash
   tmux attach -t scalping
   ```

---

## 🎓 고급 팁

### 1. 여러 전략 동시 실행

```bash
# 터미널 1: 보수적 전략
STRATEGY_MODE=conservative python3 btc_web_server.py --port 8000

# 터미널 2: 공격적 전략
STRATEGY_MODE=aggressive python3 btc_web_server.py --port 8001
```

→ 두 개의 대시보드로 비교

### 2. 데이터 백업

거래 히스토리 자동 저장:

```python
# btc_web_server.py에 추가
import json
from datetime import datetime

# 주기적으로 저장
async def save_trades():
    while True:
        with open(f'trades_{datetime.now().strftime("%Y%m%d")}.json', 'w') as f:
            json.dump(trade_history, f)
        await asyncio.sleep(300)  # 5분마다
```

### 3. 성과 분석

브라우저 콘솔에서:

```javascript
// 평균 수익률
const avgProfit = trades
    .filter(t => t.pnl !== undefined)
    .reduce((sum, t) => sum + t.pnl, 0) / trades.length;

console.log('Average Profit:', avgProfit);
```

---

## 🎉 완성!

이제 웹 UI로 BTC 스캘핑 봇을 완전히 제어할 수 있습니다!

### 다음 단계

1. ✅ 웹 UI로 Dry Run 테스트
2. ✅ 실시간 거래 모니터링 확인
3. ✅ 모바일에서 접속 테스트
4. ⚡ 실전 모드로 전환 (소액)
5. 📊 성과 분석 및 파라미터 조정

---

## 📚 관련 문서

- [WEB_UI_GUIDE.md](WEB_UI_GUIDE.md) - 상세 웹 UI 가이드
- [QUICK_START.md](QUICK_START.md) - 봇 빠른 시작
- [BTC_SCALPING_GUIDE.md](BTC_SCALPING_GUIDE.md) - 전략 가이드

---

**Happy Trading! 🚀💻📱**
