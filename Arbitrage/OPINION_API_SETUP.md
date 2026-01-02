# Opinion Labs API 설정 가이드

## ✅ 완료된 업데이트

Opinion Labs API 인증 기능이 추가되었습니다!

### 변경 사항

1. **API Endpoint 수정**
   - 이전: `https://api.opinion.trade/v1/markets`
   - 현재: `https://proxy.opinion.trade:8443/openapi/market`

2. **API Key 인증 추가**
   - `apikey` 헤더에 API key 전송
   - 환경 변수 `OPINION_API_KEY` 지원
   - 파라미터로 직접 전달 가능

3. **에러 처리 개선**
   - API key 없을 때 명확한 경고 메시지
   - API key 설정 방법 안내

---

## 🔑 API Key 설정 방법

### 1. API Key 받기

[Opinion Labs API 신청 폼](https://docs.opinion.trade/)을 작성하여 API key를 받으세요.

### 2. API Key 설정

**방법 1: 환경 변수 (추천)**
```bash
export OPINION_API_KEY="your_api_key_here"
```

**방법 2: .env 파일**
```bash
# .env.example 복사
cp .env.example .env

# .env 파일 편집
nano .env

# 아래 내용 입력
OPINION_API_KEY=your_actual_api_key_here
```

**방법 3: 코드에서 직접 전달**
```python
from services import OpinionCollector

collector = OpinionCollector(api_key="your_api_key_here")
markets = collector.fetch_active_markets()
```

---

## 🧪 테스트

### API Key 없이 실행
```bash
python3 main.py
```

**결과**:
```
WARNING - No Opinion Labs API key provided.
ERROR - Cannot fetch markets: API key not configured
```

### API Key와 함께 실행
```bash
export OPINION_API_KEY="your_key"
python3 main.py
```

**결과**:
```
INFO - Opinion Labs API key configured
INFO - Fetching Opinion Labs markets...
INFO - Fetched X Opinion Labs markets
```

---

## 📝 코드 예시

### main.py에서 사용
```python
# 환경 변수에서 자동으로 읽음
opinion_collector = OpinionCollector()

# 또는 직접 전달
opinion_collector = OpinionCollector(api_key="your_key")
```

### 테스트 스크립트
```python
import os
from services import OpinionCollector

# API key 설정
os.environ["OPINION_API_KEY"] = "your_key_here"

# 수집기 생성
collector = OpinionCollector()

# 마켓 가져오기
markets = collector.fetch_active_markets(limit=10)

print(f"Fetched {len(markets)} markets")
for market in markets:
    print(f"- {market.title}")
```

---

## ⚠️ 주의사항

1. **API Key 보안**: `.env` 파일은 절대 Git에 커밋하지 마세요
2. **Rate Limiting**: API 호출 제한이 있을 수 있으니 주의하세요
3. **에러 처리**: API key가 유효하지 않으면 401/403 에러가 발생합니다

---

## 📂 관련 파일

- [`services/opinion.py`](file:///Users/jessesung/Arbitrage/services/opinion.py) - Opinion Labs 수집기
- [`.env.example`](file:///Users/jessesung/Arbitrage/.env.example) - 환경 변수 예시
- [`README.md`](file:///Users/jessesung/Arbitrage/README.md) - 전체 문서
- [`QUICKSTART.md`](file:///Users/jessesung/Arbitrage/QUICKSTART.md) - 빠른 시작 가이드
