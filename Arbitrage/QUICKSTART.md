# Arbitrage Scanner - Quick Start Guide

## 🚀 빠른 시작

### 1. 설치

```bash
cd /Users/jessesung/Arbitrage
pip3 install -r requirements.txt
```

### 2. Opinion Labs API Key 설정

```bash
# API key를 환경 변수로 설정
export OPINION_API_KEY="your_api_key_here"

# 또는 .env 파일 생성
cp .env.example .env
# .env 파일을 열어서 OPINION_API_KEY 입력
```

**API Key 받는 방법**:
- [Opinion Labs API 신청 폼](https://docs.opinion.trade/) 작성
- 승인 후 API key 이메일로 수신

### 2. 테스트 실행

```bash
python3 test_components.py
```

**예상 출력**:
```
================================================================================
ARBITRAGE SCANNER - COMPONENT TESTS
================================================================================

=== Testing Text Processing ===
✅ Text normalization working

=== Testing Fuzzy Matching ===
✅ Matching algorithm working

=== Testing Arbitrage Calculation ===
✅ Arbitrage Opportunity Found!
   Profit: $0.3300
   ROI: 49.25%

================================================================================
✅ All tests completed successfully!
================================================================================
```

### 3. 실제 스캐너 실행

```bash
python3 main.py
```

**Note**: Opinion Labs API가 실제로 작동하지 않을 수 있습니다. 이 경우 Polymarket 데이터만 수집됩니다.

---

## 📁 프로젝트 구조

```
Arbitrage/
├── main.py                 # 메인 실행 스크립트
├── models.py              # 데이터 모델
├── matcher.py             # 매칭 엔진
├── test_components.py     # 테스트 스크립트
├── requirements.txt       # 의존성
├── README.md             # 상세 문서
│
├── services/
│   ├── polymarket.py     # Polymarket 수집기
│   └── opinion.py        # Opinion Labs 수집기
│
└── utils/
    └── text_processing.py # 텍스트 처리
```

---

## 🎯 주요 기능

### 1. 데이터 수집
- **Polymarket**: Gamma API를 통한 실시간 마켓 데이터
- **Opinion Labs**: REST API를 통한 마켓 데이터
- **비동기 처리**: 두 플랫폼에서 동시 수집

### 2. 퍼지 매칭
- **알고리즘**: rapidfuzz (token_sort_ratio)
- **임계값**: 85점 이상
- **검증**: 공통 키워드 확인

### 3. 차익거래 계산
- **전략**: YES/NO 조합으로 무위험 수익 창출
- **조건**: Total Cost < 0.98 (2% 마진)
- **출력**: ROI 순으로 정렬

---

## 📊 사용 예시

### 테스트 실행 결과

```python
# 매칭 예시
Polymarket: "will bitcoin reach 100000 by 2024"
Opinion: "bitcoin price above 100k before 2025"
Match Score: 95.0/100 ✅

# 차익거래 계산
Strategy 1: Poly YES ($0.65) + Opinion NO ($0.68) = $1.33 ❌
Strategy 2: Poly NO ($0.35) + Opinion YES ($0.32) = $0.67 ✅

Profit: $0.33
ROI: 49.25%
```

---

## ⚙️ 설정 변경

### 매칭 임계값 조정

`main.py` 수정:
```python
matcher = MarketMatcher(
    similarity_threshold=85.0,  # 80-95 권장
    min_common_keywords=2       # 1-3 권장
)
```

### 차익거래 조건 조정

```python
opportunities = matcher.calculate_arbitrage(
    matches,
    min_margin=0.02,  # 최소 2% 수익
    max_cost=0.98     # 최대 98% 비용
)
```

---

## 🔍 문제 해결

### ModuleNotFoundError
```bash
pip3 install -r requirements.txt
```

### API 연결 실패
- Polymarket Gamma API: 공개 API, 인증 불필요
- Opinion Labs API: 실제 엔드포인트 확인 필요

### 매칭 결과 없음
- `similarity_threshold`를 낮춰보세요 (예: 75.0)
- `min_common_keywords`를 낮춰보세요 (예: 1)

---

## 📝 다음 단계

1. **실제 API 테스트**: Opinion Labs API 엔드포인트 확인
2. **웹 대시보드**: Next.js + Tailwind CSS로 UI 구축
3. **실시간 모니터링**: WebSocket으로 실시간 업데이트
4. **알림 시스템**: Telegram 봇 연동

---

## ✅ 완료된 기능

- [x] Polymarket Gamma API 연동
- [x] Opinion Labs API 구조 구현
- [x] 퍼지 매칭 엔진 (rapidfuzz)
- [x] 차익거래 계산 로직
- [x] 비동기 데이터 수집
- [x] 텍스트 정규화 및 키워드 추출
- [x] 테스트 스위트
- [x] 로깅 시스템
- [x] JSON 결과 저장
- [x] 한글 문서화

---

## 📞 지원

문제가 있으면 `arbitrage_scanner.log` 파일을 확인하세요.

```bash
tail -f arbitrage_scanner.log
```
