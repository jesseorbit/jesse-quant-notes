# 전략 V2 리팩토링 요약

## 문제점 (V1)

### 1. 엑싯 후 2차 진입이 안 되는 문제
**원인**: `trade_count`가 잘못 증가
- TP limit order가 체결되면 `on_exit_filled()` 호출
- `trade_count` 증가 → `max_trades_per_market` (3회) 제한 도달
- 하지만 실제로는 1사이클만 완료했을 뿐

**결과**: 1번 익절하면 더 이상 진입 불가

### 2. 5분 남았는데 high scalping 안 하는 문제
**원인**: 여러 블로킹 조건이 복잡하게 얽힘
- `active_exit_orders` (TP limit order 추적)
- `last_tp_limit_price` (중복 limit order 방지)
- `has_active_exit_orders` 체크가 high scalping 진입도 막음

**결과**: 5분 미만에 TP limit order가 있으면 high scalping 진입 금지

### 3. 근본 원인: 상태 동기화 문제
V1은 5개의 독립적인 상태를 관리:
```python
self.active_exit_orders: dict[str, List[str]]  # TP limit order 추적
self.last_tp_limit_price: dict[str, tuple]     # 중복 방지
self.trade_count: dict[str, int]               # 거래 횟수
self.high_scalp_count: dict[str, int]          # high scalping 횟수
self.positions: dict[str, List[Position]]      # 포지션
```

이 상태들이 서로 다른 시점에 업데이트되면서 **동기화 문제** 발생:
- 주문 발행 시점에 카운터 증가 → 주문 실패해도 카운터 증가
- TP limit order 체결 시 `active_exit_orders` 클리어 → 하지만 포지션은 이미 제거됨
- `trade_count`는 엑싯 시마다 증가 → 하지만 실제로는 부분 엑싯일 수 있음

## 해결책 (V2)

### 핵심 원칙: Single Source of Truth

**포지션만이 상태의 단일 진실 원천**
```python
# V2는 단 하나의 상태만 관리
self.positions: dict[str, List[LevelPosition]]  # 포지션 리스트
self.completed_cycles: dict[str, int]           # 완료된 사이클 (LEVEL만)
```

**모든 통계는 포지션에서 실시간 계산**
```python
def _count_high_scalp_positions(self, market_id: str) -> int:
    """포지션에서 HIGH SCALP 개수 계산"""
    return sum(1 for p in self.positions[market_id] if p.is_high_scalp)

def _get_level_positions(self, market_id: str) -> List[LevelPosition]:
    """포지션에서 LEVEL만 필터링"""
    return [p for p in self.positions[market_id] if not p.is_high_scalp]
```

### 주요 변경사항

#### 1. 완료된 사이클 기반 제한
```python
# V1: trade_count (엑싯할 때마다 증가)
self.trade_count[market_id] += 1  # 잘못됨!

# V2: completed_cycles (LEVEL 포지션 전체 청산 시에만 증가)
def on_exit_filled(self, market_id: str, side: str, is_high_scalp: bool):
    # 포지션 제거
    self.positions[market_id] = [p for p in self.positions[market_id] if p.side != side]

    # LEVEL 포지션 청산이면 사이클 증가
    if not is_high_scalp:
        self.completed_cycles[market_id] += 1  # 올바름!
```

**결과**:
- 1사이클 = 진입 → 익절 완료
- `max_completed_cycles = 3` → 3번의 완전한 사이클 가능
- 부분 엑싯은 사이클로 카운트 안 됨

#### 2. TP Limit Order 관리를 봇으로 이동
```python
# V1: 전략에서 TP limit order 관리
class MultiLevelScalpingStrategy:
    self.active_exit_orders: dict[str, List[str]] = {}
    self.last_tp_limit_price: dict[str, tuple] = {}

    def _check_exit(self, ctx):
        # TP 조건 만족 시 PLACE_TP_LIMIT 신호
        return ScalpSignal(action="PLACE_TP_LIMIT", ...)

# V2: 봇에서 TP limit order 관리
class BTCScalpingBotV2:
    self.active_tp_orders: Dict[str, list] = {}

    async def execute_signal(self, market_id, ctx, signal):
        if signal.action == "PLACE_TP_LIMIT":
            # 기존 TP order 취소
            await self.cancel_tp_orders(market_id)

            # 새로운 TP order 발행
            await self.place_order(..., post_only=True)

            # 추적
            self.active_tp_orders[market_id].append(order_id)
```

**이점**:
- 전략은 단순히 "TP 조건 만족" 신호만 생성
- 실제 주문 관리는 봇에서 처리
- 전략과 실행 로직 분리

#### 3. 5분 미만에는 LIMIT Order 절대 금지
```python
# V2 봇
async def evaluate_market(self, market_id: str, ctx: MarketContext):
    time_remaining = ctx.end_time - time.time()

    # 5분 미만이면 모든 TP limit order 취소
    if time_remaining < 300:
        if market_id in self.active_tp_orders:
            logger.warning("⚠️  <5min: Cancelling all TP limit orders")
            await self.cancel_tp_orders(market_id)

    # 전략 실행
    signal = self.strategy.evaluate_market(ctx)
```

**결과**:
- 5분 미만에 도달하면 자동으로 모든 TP limit order 취소
- MARKET order로만 청산 (체결 보장)
- `active_exit_orders`가 high scalping을 막는 문제 해결

#### 4. 단순하고 명확한 진입 조건
```python
# V1: 복잡한 체크
def _check_entry(self, ctx):
    # 1. 거래 횟수 체크
    if self.trade_count[market_id] >= self.max_trades_per_market:
        return None

    # 2. 시간 체크 (여러 조건)
    if time_remaining < 420:
        return None

    # 3. active_exit_orders 체크
    if self.active_exit_orders[market_id]:
        return None

    # 4. 포지션 체크
    # ... 복잡한 로직

# V2: 단순 명확
def _check_level_entry(self, ctx):
    # 1. 완료된 사이클 체크
    cycles = self.completed_cycles.get(market_id, 0)
    if cycles >= self.max_completed_cycles:
        return None

    # 2. 시간 체크
    if time_remaining < 420:
        return None

    # 3. 헷징 방지 (YES와 NO 둘 다 있으면 진입 금지)
    level_positions = self._get_level_positions(market_id)
    yes_pos = [p for p in level_positions if p.side == "YES"]
    no_pos = [p for p in level_positions if p.side == "NO"]
    if yes_pos and no_pos:
        return None

    # 진입 체크
    # ... 단순 명확
```

## 코드 비교

### V1 (복잡)
```python
# 5개의 상태 관리
self.active_exit_orders = {}
self.last_tp_limit_price = {}
self.trade_count = {}
self.high_scalp_count = {}
self.positions = {}

# 카운터 증가 (주문 발행 시)
def _check_high_price_scalping(self, ctx):
    self.high_scalp_count[market_id] += 1  # 주문 실패해도 증가!
    return ScalpSignal(...)

# 포지션 제거 (즉시)
def _check_exit(self, ctx):
    self.positions[market_id] = [...]  # 주문 성공 전에 제거!
    return ScalpSignal(action="EXIT", ...)
```

### V2 (단순)
```python
# 2개의 상태만 관리
self.positions = {}
self.completed_cycles = {}

# 카운터는 포지션에서 계산
def _count_high_scalp_positions(self, market_id):
    return sum(1 for p in self.positions[market_id] if p.is_high_scalp)

# 포지션 제거 (체결 후에만)
def on_exit_filled(self, market_id, side, is_high_scalp):
    # 체결 확인 후에만 호출됨
    self.positions[market_id] = [p for p in self.positions[market_id] if p.side != side]
    if not is_high_scalp:
        self.completed_cycles[market_id] += 1
```

## 테스트 시나리오

### 시나리오 1: 엑싯 후 2차 진입
```
1. ENTER_YES @ 0.34 (1차 진입) → completed_cycles = 0
2. TP 도달, EXIT → completed_cycles = 1
3. 가격 다시 하락 @ 0.34 → ENTER_YES (2차 진입 가능!) ← V1에서는 불가
4. TP 도달, EXIT → completed_cycles = 2
5. 가격 다시 하락 @ 0.34 → ENTER_YES (3차 진입 가능!)
6. TP 도달, EXIT → completed_cycles = 3
7. 가격 다시 하락 @ 0.34 → 진입 금지 (max_completed_cycles 도달)
```

### 시나리오 2: 5분 남았을 때
```
1. 7분 남음: ENTER_YES @ 0.34
2. 6분 남음: TP 조건 만족 → PLACE_TP_LIMIT (봇에서 limit order 발행)
3. 5분 30초: limit order 대기 중
4. 4분 59초: 봇이 자동으로 limit order 취소 ← V1에서는 안 함
5. 4분 50초: 가격이 0.90으로 상승 → HIGH_SCALP 진입 가능! ← V1에서는 불가
```

### 시나리오 3: Force Unwind
```
1. 7분 남음: ENTER_YES @ 0.34, ENTER_YES @ 0.24 (2개 LEVEL 포지션)
2. 4분 59초: FORCE_UNWIND 발동 → BUY NO x20 @ 0.xx (MARKET order)
3. 4분 58초: LEVEL 포지션 청산 완료 → completed_cycles = 1
4. 4분 50초: 가격이 0.88로 상승 → HIGH_SCALP ENTER_YES 가능!
5. 3분 30초: HIGH_SCALP TP 도달 → EXIT (MARKET order)
6. 2분 00초: 가격이 0.90 → HIGH_SCALP ENTER_YES (2차)
7. ... 최대 4번까지 HIGH_SCALP 가능
```

## 실행 방법

```bash
# V2 봇 실행
python btc_scalping_bot_v2.py

# 기존 V1 봇 (백업)
python btc_scalping_bot_v1.py
```

## 파일 구조

```
/Users/jessesung/PolyScalping/
├── multi_level_scalping_strategy.py  # V1 (기존)
├── multi_level_strategy_v2.py        # V2 (새로운, 단순)
├── btc_scalping_bot.py               # 기존 봇 (다른 전략 사용)
├── btc_scalping_bot_v1.py            # 백업
├── btc_scalping_bot_v2.py            # V2 봇 (새로운, 단순)
└── REFACTORING_V2.md                 # 이 문서
```

## 핵심 개선 요약

| 항목 | V1 | V2 |
|------|----|----|
| **상태 관리** | 5개 독립 상태 | 2개 (포지션 + 사이클) |
| **카운터** | 별도 추적 (동기화 문제) | 포지션에서 계산 |
| **거래 제한** | trade_count (엑싯마다 증가) | completed_cycles (완전한 사이클만) |
| **TP 관리** | 전략에서 관리 | 봇에서 관리 |
| **5분 미만 LIMIT** | 가능 (체결 안 될 위험) | 불가능 (MARKET만) |
| **복잡도** | 높음 | 낮음 |
| **버그 가능성** | 높음 (상태 동기화) | 낮음 (단순) |

## 예상 효과

1. **엑싯 후 2차 진입 가능** → 더 많은 거래 기회
2. **5분 미만에 HIGH_SCALP 작동** → 고확률 기회 활용
3. **상태 동기화 문제 해결** → edge case 제거
4. **코드 가독성 향상** → 유지보수 용이
5. **버그 감소** → 안정성 향상
