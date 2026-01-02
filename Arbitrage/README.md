# Prediction Market Arbitrage Scanner

실시간으로 Polymarket, Kalshi, Opinion Labs의 예측 시장을 스캔하여 무위험 차익거래 기회를 찾는 도구입니다.

## 🎯 Features

- **다중 플랫폼 지원**: Polymarket, Kalshi, Opinion Labs 연동
- **실시간 데이터 수집**: 각 플랫폼의 공식 API 사용
- **지능형 매칭**: Fuzzy matching을 통한 동일 이벤트 자동 식별
- **차익거래 계산**: 무위험 수익 기회 자동 탐지 및 ROI 계산
- **비동기 처리**: 빠른 데이터 수집을 위한 async/await 구현

## 🏢 지원 플랫폼

| 플랫폼 | API 인증 | 상태 |
|--------|----------|------|
| **Polymarket** | 불필요 | ✅ 항상 활성화 |
| **Kalshi** | 불필요 | ✅ 항상 활성화 |
| **Opinion Labs** | API Key 필요 | ⚠️ 선택적 |

## 📁 Project Structure

```
Arbitrage/
├── main.py                 # 메인 실행 스크립트
├── models.py              # 데이터 모델 정의
├── matcher.py             # Fuzzy matching 엔진
├── services/
│   ├── __init__.py
│   ├── polymarket.py      # Polymarket 데이터 수집
│   └── opinion.py         # Opinion Labs 데이터 수집
├── utils/
│   ├── __init__.py
│   └── text_processing.py # 텍스트 정규화 유틸리티
├── requirements.txt       # Python 의존성
└── README.md             # 이 파일
```

## 🚀 Quick Start

### 1. 의존성 설치

```bash
cd Arbitrage
pip install -r requirements.txt
```

### 2. Opinion Labs API Key 설정

Opinion Labs API를 사용하려면 API key가 필요합니다.

**API Key 받기**:
1. [Opinion Labs API 신청 폼](https://docs.opinion.trade/) 작성
2. API key 받기

**설정 방법**:

```bash
# 방법 1: 환경 변수 설정
export OPINION_API_KEY="your_api_key_here"

# 방법 2: .env 파일 생성
cp .env.example .env
# .env 파일을 열어서 API key 입력
```

### 3. 스캐너 실행

```bash
python main.py
```

## 📊 How It Works

### 1. Data Collection (데이터 수집)

**Polymarket (Gamma API)**
- Endpoint: `GET https://gamma-api.polymarket.com/events`
- Parameters: `active=true`, `closed=false`, `limit=100`
- Parsing: `outcomePrices[0]` = YES, `outcomePrices[1]` = NO
- 인증: 불필요

**Kalshi**
- Endpoint: `GET https://api.elections.kalshi.com/trade-api/v2/markets`
- Parameters: `status=open`, `limit=100`
- Parsing: `yes_price` (cents → decimal), `no_price` (cents → decimal)
- 인증: 불필요

**Opinion Labs**
- Endpoint: `GET https://proxy.opinion.trade:8443/openapi/market`
- Parameters: `limit=100`
- Headers: `apikey: your_api_key`
- Parsing: `yes_price`, `no_price` 또는 `probability` 필드 사용
- 인증: API Key 필요

### 2. Data Normalization (정규화)

모든 마켓 데이터를 `StandardMarket` 형식으로 변환:
```python
@dataclass
class StandardMarket:
    platform: str        # 'POLY' or 'OPINION'
    market_id: str       # 플랫폼별 고유 ID
    title: str           # 정규화된 제목
    price_yes: float     # YES 가격 (0.0 ~ 1.0)
    price_no: float      # NO 가격 (0.0 ~ 1.0)
    volume: float        # 거래량 (USD)
    url: str             # 마켓 링크
```

### 3. Fuzzy Matching (퍼지 매칭)

- **Algorithm**: `rapidfuzz.fuzz.token_sort_ratio`
- **Threshold**: 유사도 85점 이상
- **Validation**: 최소 2개 이상의 공통 키워드 확인

### 4. Arbitrage Calculation (차익거래 계산)

**전략**:
- Strategy 1: Polymarket YES + Opinion NO
- Strategy 2: Polymarket NO + Opinion YES

**조건**:
- Total Cost < 0.98 (최소 2% 마진 확보)
- Profit = 1.0 - Total Cost

**ROI 계산**:
```
ROI% = (Profit / Total Cost) × 100
```

## 📈 Output Example

```
================================================================================
ARBITRAGE SCANNER RESULTS
================================================================================

Found 5 arbitrage opportunities!

--- Opportunity #1 ---
ROI: 3.45%
Profit Margin: $0.0332
Total Cost: $0.9668
Match Score: 92.5/100

Polymarket:
  Title: will bitcoin reach 100000 by end of 2024
  YES: $0.6500 | NO: $0.3500
  URL: https://polymarket.com/event/bitcoin-100k-2024

Opinion Labs:
  Title: bitcoin price above 100k before 2025
  YES: $0.3168 | NO: $0.6832
  URL: https://opinion.trade/market/btc-100k-2024
```

## 🔧 Configuration

`main.py`에서 설정 변경 가능:

```python
# Matching 설정
matcher = MarketMatcher(
    similarity_threshold=85.0,  # 유사도 임계값 (0-100)
    min_common_keywords=2       # 최소 공통 키워드 수
)

# Arbitrage 설정
opportunities = matcher.calculate_arbitrage(
    matches,
    min_margin=0.02,  # 최소 수익률 (2%)
    max_cost=0.98     # 최대 비용 (98%)
)
```

## 📝 Output Files

- `arbitrage_results.json`: 발견된 차익거래 기회 상세 정보
- `arbitrage_scanner.log`: 실행 로그

## ⚠️ Important Notes

1. **API Rate Limits**: 각 플랫폼의 API rate limit을 준수하세요
2. **수수료 고려**: 실제 거래 시 플랫폼 수수료를 반드시 고려하세요
3. **가격 변동**: 실시간 가격은 빠르게 변동될 수 있습니다
4. **리스크**: 이 도구는 교육 목적이며, 실제 거래 시 손실 가능성이 있습니다

## 🔮 Future Enhancements

- [ ] FastAPI 웹 서버 구현
- [ ] Next.js 대시보드 UI
- [ ] 실시간 WebSocket 업데이트
- [ ] 알림 시스템 (Telegram/Discord)
- [ ] 백테스팅 기능
- [ ] 자동 거래 실행 (선택적)

## 📄 License

MIT License
