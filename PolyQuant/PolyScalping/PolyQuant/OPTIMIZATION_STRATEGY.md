# Parameter Optimization for DCA Unwind Strategy

## Current Performance (Baseline)

**Parameters**:
- Entry threshold: 0.35
- Hedge threshold: 0.65
- DCA levels: (0.25, 0.15, 0.05)
- Force unwind: 5 minutes

**Results** (200 BTC markets, 7 days):
- Markets entered: 66/200 (33%)
- Win rate: 43.9%
- Avg PnL: +0.079 USDC
- Avg win: +18.19 USDC
- Avg loss: -14.12 USDC
- **Expected value**: 0.439 × 18.19 + 0.561 × (-14.12) = **+0.08 USDC**
- Forced unwind rate: 60.6%

## Optimization Strategy

Testing combinations of:

### 1. Entry Threshold (when to enter)
- **0.25**: Very aggressive (enter when price ≤ 0.25)
- **0.30**: Aggressive
- **0.35**: Current baseline
- **0.40**: Conservative (enter when price ≤ 0.40)

**Trade-off**: Lower threshold = fewer entries but better entry prices

### 2. Hedge Threshold (when to buy opposite side)
- **0.60**: Aggressive hedging
- **0.65**: Current baseline
- **0.70**: Conservative hedging

**Trade-off**: Lower threshold = hedge sooner, reduce risk but cap upside

### 3. DCA Levels (when to add to losing position)
- **(0.25, 0.15, 0.05)**: Original - 3 levels
- **(0.20, 0.10)**: Fewer levels, more aggressive
- **(0.30, 0.20, 0.10)**: More conservative
- **(0.25, 0.15)**: Medium - 2 levels

**Trade-off**: More levels = more capital at risk, but better avg entry

### 4. Force Unwind Time (minutes before expiry)
- **3 min**: Exit very early
- **5 min**: Current baseline
- **7 min**: Exit earlier
- **10 min**: Exit much earlier

**Trade-off**: Earlier exit = less time for favorable move, but avoid last-minute volatility

## Optimization Objective

**Maximize Expected Value** = Win Rate × Avg Win + (1 - Win Rate) × Avg Loss

This balances:
- Win rate (how often we profit)
- Win size (how much we make when we win)
- Loss size (how much we lose when we lose)

## Running the Optimization

```bash
python3 optimize_backtest_params.py
```

This will:
1. Test 192 parameter combinations (4 × 3 × 4 × 4)
2. Run full backtest for each combination
3. Calculate expected value for each
4. Save results to `optimization_results.csv`
5. Display top 10 best combinations

**Estimated time**: ~15-20 minutes (192 backtests × ~5 seconds each)

## Expected Improvements

Based on the current results:
- **High forced unwind rate (60.6%)** suggests we should exit earlier
- **Negative skew** (avg loss > avg win) suggests we need better entry prices
- **Low win rate (43.9%)** suggests entry threshold might be too high

**Hypotheses to test**:
1. **Lower entry threshold (0.25-0.30)** → Better entry prices → Higher win rate
2. **Earlier force unwind (7-10 min)** → Avoid last-minute adverse moves → Lower forced loss rate
3. **Fewer DCA levels** → Less capital at risk → Smaller losses

## Interpreting Results

The optimization will rank combinations by expected value. Look for:

1. **Highest EV** - Best risk-adjusted returns
2. **High win rate + positive EV** - Consistent profitability
3. **Low forced unwind rate** - Strategy exits gracefully
4. **Reasonable entry rate** - Not too selective (>20% of markets)

## Next Steps After Optimization

1. **Validate best parameters** on different time periods
2. **Test on other assets** (ETH, SOL, XRP)
3. **Consider transaction costs** - Add realistic fee_bps
4. **Live paper trading** - Test in real-time before deploying capital
