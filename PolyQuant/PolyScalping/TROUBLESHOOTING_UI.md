# 🔧 웹 UI 문제 해결

## ❌ "Add Market 버튼이 안 보여요"

### 원인
서버가 오래된 코드로 실행 중일 수 있습니다.

### 해결 방법

#### 방법 1: 서버 재시작 (가장 쉬움) ⭐

```bash
# 터미널에서 실행 중인 서버 찾기
# Ctrl+C 눌러서 종료

# 또는 강제 종료
pkill -f btc_web_server

# 새로 시작
python3 btc_web_server.py
```

#### 방법 2: 스크립트 사용

```bash
# 실행 권한 부여 (처음 한 번만)
chmod +x run_web_ui.sh

# 실행
./run_web_ui.sh
```

#### 방법 3: 포트 확인 후 재시작

```bash
# 8000 포트 사용 중인 프로세스 찾기
lsof -i :8000

# PID 확인 후 종료
kill -9 <PID>

# 서버 재시작
python3 btc_web_server.py
```

---

## ✅ 제대로 작동하는지 확인

### 1. 브라우저 접속
```
http://localhost:8000
```

### 2. 버튼 확인
다음 버튼들이 보여야 합니다:

```
[▶ Start]  [⏹ Stop]  [🔄 Refresh]  [➕ Add Market]
```

**➕ Add Market** 버튼이 보이면 성공! 🎉

### 3. Add Market 클릭
버튼 클릭 시 다음이 나타나야 함:

```
┌─────────────────────────────────────────────┐
│ Add Market Manually                         │
│                                             │
│ URL: [________________]  [Add]              │
│ Paste a Polymarket market URL               │
│                                             │
│ Search: [_____________]  [Search]           │
└─────────────────────────────────────────────┘
```

---

## 🔍 추가 디버깅

### 브라우저 콘솔 확인

1. **F12** 또는 **우클릭 → 검사**
2. **Console** 탭 확인
3. 에러 메시지 있는지 확인

**정상:**
```
WebSocket connected
```

**비정상:**
```
Error loading data: ...
Failed to fetch
```

### 네트워크 탭 확인

1. **F12 → Network** 탭
2. **🔄 Refresh** 버튼 클릭
3. `/api/status` 요청 확인

**정상:**
- Status: 200 OK
- Response: JSON 데이터

**비정상:**
- Status: 500, 404
- 요청 자체가 안 나감

---

## 📋 체크리스트

웹 UI가 작동하려면:

- [ ] Python 서버 실행 중 (`python3 btc_web_server.py`)
- [ ] 포트 8000 사용 가능
- [ ] 브라우저에서 http://localhost:8000 접속
- [ ] WebSocket 연결됨 (🟢 Connected)
- [ ] ➕ Add Market 버튼 보임

모두 체크되면 정상! ✅

---

## 🐛 자주 발생하는 문제

### "Address already in use"

**증상:**
```
ERROR: address already in use
```

**해결:**
```bash
# 이미 실행 중인 서버 종료
pkill -f btc_web_server

# 또는
lsof -i :8000
kill -9 <PID>
```

### "Cannot GET /"

**증상:** 빈 화면 또는 404

**해결:**
- 서버가 완전히 시작될 때까지 기다리기 (3-5초)
- 브라우저 새로고침 (F5)

### "WebSocket disconnected"

**증상:** 🔴 Disconnected 표시

**해결:**
- 자동으로 3초 후 재연결됨
- 수동: F5로 새로고침

### UI가 업데이트 안됨

**증상:** 버튼 클릭해도 반응 없음

**해결:**
1. 브라우저 캐시 삭제
   - Chrome: Ctrl+Shift+Delete
   - 캐시된 이미지 및 파일 삭제
2. 시크릿/프라이빗 모드로 접속
3. 다른 브라우저 시도

---

## 🔄 완전 초기화

모든 방법이 안 되면:

```bash
# 1. 모든 프로세스 종료
pkill -f btc_web_server
pkill -f python

# 2. 포트 확인
lsof -i :8000
# 결과 없으면 OK

# 3. 브라우저 캐시 삭제
# Chrome: Ctrl+Shift+Delete

# 4. 서버 재시작
python3 btc_web_server.py

# 5. 브라우저 새 탭으로 접속
# http://localhost:8000
```

---

## 📱 모바일에서 안 보임

### 같은 WiFi 확인

```bash
# PC IP 확인
ifconfig | grep "inet "
# 예: 192.168.1.100

# 모바일 브라우저
http://192.168.1.100:8000
```

### 방화벽 확인

```bash
# Mac
sudo ufw status
sudo ufw allow 8000

# 포트 테스트
curl http://localhost:8000/api/status
```

---

## ✅ 정상 작동 확인

다음이 모두 되면 OK:

1. ✅ http://localhost:8000 접속됨
2. ✅ 상단에 4개 버튼 보임 (Start/Stop/Refresh/Add Market)
3. ✅ BTC Price 표시됨
4. ✅ 🟢 Connected 표시
5. ✅ ➕ Add Market 클릭 시 폼 나타남

---

## 🆘 그래도 안 되면

1. **파일 확인**
   ```bash
   ls -la btc_web_server.py
   # 파일 크기: ~30KB 정도
   ```

2. **버전 확인**
   ```bash
   grep "Add Market" btc_web_server.py
   # 결과가 나와야 함
   ```

3. **로그 확인**
   ```bash
   python3 btc_web_server.py 2>&1 | tee server.log
   # 에러 메시지 확인
   ```

4. **문의하기**
   - 스크린샷 첨부
   - 에러 메시지 복사
   - 브라우저 콘솔 로그

---

## 💡 빠른 테스트

서버가 정상인지 확인:

```bash
# API 테스트
curl http://localhost:8000/api/status

# 정상이면 JSON 응답:
{
  "running": true,
  "btc_price": 91155.71,
  ...
}
```

---

**대부분의 문제는 서버 재시작으로 해결됩니다!** 🔄
