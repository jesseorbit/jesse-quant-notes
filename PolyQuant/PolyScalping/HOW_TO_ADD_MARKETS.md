# 🎯 마켓 수동 추가 가이드

현재 BTC 15분 마켓이 자동으로 발견되지 않는 경우, 웹 UI에서 수동으로 추가할 수 있습니다!

## 🚀 빠른 방법

### 1단계: 웹 서버 시작

```bash
python3 btc_web_server.py
```

### 2단계: 브라우저 접속

```
http://localhost:8000
```

### 3단계: 마켓 추가

1. **"➕ Add Market"** 버튼 클릭
2. 두 가지 방법 중 선택:

---

## 방법 1: URL로 직접 추가 (가장 빠름) ⭐

### Polymarket에서 마켓 찾기

1. https://polymarket.com 접속
2. 검색창에 "BTC" 또는 "Bitcoin" 입력
3. 원하는 마켓 클릭
4. URL 복사

**예시:**
```
https://polymarket.com/event/btc-updown-15m-1768889700
```

### 웹 UI에 붙여넣기

1. URL 입력란에 붙여넣기
2. **"Add"** 버튼 클릭
3. "Market added successfully!" 메시지 확인
4. Active Markets 섹션에 즉시 표시됨!

---

## 방법 2: 검색으로 추가

### 검색창 사용

1. **"➕ Add Market"** 버튼 클릭
2. 검색창에 키워드 입력:
   ```
   BTC
   Bitcoin
   crypto
   ```
3. **"Search"** 버튼 클릭
4. 결과 목록에서 원하는 마켓 찾기
5. 해당 마켓의 **"Add"** 버튼 클릭

### 검색 결과 예시

```
┌──────────────────────────────────────────────┐
│ Bitcoin Up or Down - Jan 20, 1:15-1:30 ET   │
│ Liquidity: $17,950 | 24h Vol: $5,488        │
│                                   [Add]      │
├──────────────────────────────────────────────┤
│ Will BTC hit $100k in January 2026?         │
│ Liquidity: $25,430 | 24h Vol: $12,340       │
│                                   [Add]      │
└──────────────────────────────────────────────┘
```

---

## 📊 마켓 추가 후

### 확인 사항

마켓이 추가되면:

1. **Active Markets** 섹션에 표시
   ```
   📊 Active Markets (1)

   Bitcoin Up or Down - Jan 20, 1:15-1:30 ET
   YES: 0.565    NO: 0.435
   Time Left: 12m 30s
   ```

2. **실시간 가격 업데이트** 시작
   - 5초마다 YES/NO 가격 갱신
   - 남은 시간 카운트다운

3. **봇이 자동으로 분석**
   - 진입 조건 체크
   - 신호 생성 시 거래 실행

---

## 🎯 실전 예시

### 시나리오: BTC 15분 마켓 거래

**상황:** 지금 당장 활성 BTC 15분 마켓이 있음

#### Step 1: Polymarket에서 URL 복사

```
1. https://polymarket.com 접속
2. 검색: "BTC 15m"
3. 마켓 클릭
4. URL 복사: https://polymarket.com/event/btc-updown-15m-1768889700
```

#### Step 2: 웹 UI에 추가

```
1. ➕ Add Market 클릭
2. URL 붙여넣기
3. Add 버튼 클릭
4. 성공 메시지 확인
```

#### Step 3: 모니터링 시작

```
Active Markets (1)
┌────────────────────────────────────────┐
│ Bitcoin Up or Down                     │
│ YES: 0.565    NO: 0.435                │
│ Time: 12m 30s                          │
│                                        │
│ [봇이 자동으로 분석 중...]             │
└────────────────────────────────────────┘
```

#### Step 4: 신호 생성

```
Event Log:
15:20:35  signal  ENTER_YES - UP predicted (65.2% confidence)
15:20:36  trade   ENTER_YES YES x10 @ 0.450
```

#### Step 5: 청산

```
Event Log:
15:23:10  signal  EXIT - Take Profit (+3.2%)
15:23:12  trade   EXIT YES x10 @ 0.525

Recent Trades:
EXIT | YES x10 @ 0.525 .................. +$0.75
```

---

## 💡 팁

### 좋은 마켓 찾기

다음 조건을 만족하는 마켓 선택:

✅ **유동성 $10,000+**
- 스프레드 좁음
- 슬리피지 적음

✅ **남은 시간 5분+**
- 진입/청산 시간 확보
- 강제 청산 방지

✅ **거래량 활발**
- 24h Volume $5,000+
- 가격 움직임 있음

### 피해야 할 마켓

❌ 유동성 너무 낮음 (<$5,000)
❌ 만료 3분 미만
❌ 이미 종료된 마켓
❌ 스프레드 너무 넓음 (YES + NO > 1.05)

---

## 🔧 문제 해결

### "Market not found"

**원인:** 잘못된 URL 또는 마켓이 삭제됨

**해결:**
1. URL 다시 확인
2. Polymarket에서 마켓이 아직 활성인지 확인
3. 다른 마켓 시도

### "Invalid market: missing tokens"

**원인:** 바이너리 마켓이 아님 (YES/NO가 아닌 경우)

**해결:**
- YES/NO 두 개 선택지가 있는 마켓만 선택
- Multi-outcome 마켓은 지원 안됨

### 마켓 추가했는데 안 보임

**원인:** 봇이 실행 중이 아님

**해결:**
1. **▶ Start** 버튼 클릭
2. 몇 초 기다리기
3. **🔄 Refresh** 클릭

### 마켓 추가했는데 거래 안됨

**원인:** 진입 조건 불만족

**확인:**
1. Event Log 확인
   - 신호가 생성되는지
   - 왜 진입 안하는지 이유 표시됨

2. 조건 확인:
   - Edge 5% 이상?
   - 신뢰도 50% 이상?
   - 남은 시간 3분 이상?

---

## 📋 API로 마켓 추가 (고급)

### cURL 사용

```bash
curl -X POST http://localhost:8000/api/add_market \
  -H "Content-Type: application/json" \
  -d '{
    "market_url": "https://polymarket.com/event/btc-updown-15m-1768889700"
  }'
```

### Python 스크립트

```python
import requests

url = "http://localhost:8000/api/add_market"
data = {
    "market_url": "https://polymarket.com/event/btc-updown-15m-1768889700"
}

response = requests.post(url, json=data)
print(response.json())
```

---

## 🎓 자동 스캔 vs 수동 추가

### 자동 스캔 (기본)

**장점:**
- 자동으로 새 마켓 발견
- 30초마다 스캔
- 여러 마켓 동시 추적

**단점:**
- 검색 정확도 의존
- BTC 15분 마켓 찾기 어려울 수 있음

### 수동 추가 (권장) ⭐

**장점:**
- 정확히 원하는 마켓 선택
- 즉시 추가 가능
- 실패율 낮음

**단점:**
- 수동으로 찾아야 함
- 하나씩 추가

---

## 🔄 마켓 제거

현재는 만료된 마켓 자동 제거만 지원:
- 만료 + 10분 후 자동 제거
- 수동 제거 기능은 곧 추가 예정

---

## ✅ 체크리스트

마켓 추가 전:

- [ ] 웹 서버 실행 중
- [ ] 브라우저에서 http://localhost:8000 접속
- [ ] Polymarket에서 원하는 마켓 URL 복사
- [ ] 마켓이 활성 상태인지 확인 (종료 안됨)
- [ ] 바이너리 마켓인지 확인 (YES/NO)

마켓 추가 후:

- [ ] Active Markets에 표시됨
- [ ] Start 버튼 클릭했음
- [ ] Event Log에 활동 보임
- [ ] BTC Price 업데이트됨

---

## 🎉 완료!

이제 원하는 BTC 마켓을 자유롭게 추가하고 거래할 수 있습니다!

**바로 시작하기:**
```bash
python3 btc_web_server.py
# → http://localhost:8000
# → ➕ Add Market
# → URL 붙여넣기
# → Add!
```

**Happy Trading! 🚀💰**
