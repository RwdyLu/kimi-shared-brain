# Optimization Mission — Phase 3: Profitability Sprint

## Mission
Turn the crypto trading system from -4.11% paper trading loss into profitability by:
1. Integrating proven strategies from Freqtrade ecosystem
2. Rewriting risk management with strict drawdown limits, trailing stops, and position sizing
3. Installing Freqtrade for backtest/hyperopt engine

## Current State (2026-05-13)
- Paper trading: -4.11% overall, momentum_divergence bleeding at -37.56% with 5 open positions
- 6 strategies have NEVER triggered (0 trades)
- Backtest history: mostly zero trades, single backtest with 2.65% return on ema_cross_fast
- Risk management: static ATR stops, 20% max per position, no trailing, no Kelly sizing

## Execution Plan

### Phase A: Triage (immediate)
- [x] Disable bleeding strategies: momentum_divergence, ma_cross_trend, hilbert_cycle
- [ ] Close all open positions for disabled strategies
- [ ] Write strict risk module

### Phase B: Risk Management Rewrite
- [ ] New `app/risk_manager.py` with:
  - Trailing stop loss (ATR-based, moves with profit)
  - Max drawdown circuit breaker (5% per strategy, 10% portfolio)
  - Kelly Criterion position sizing
  - Volatility-adjusted exposure (reduce size in high ATR environments)
- [ ] Integrate into `paper_trading.py` and `signals/engine.py`

### Phase C: Freqtrade Strategy Import
- [x] Install Freqtrade (native Python, Docker unavailable)
- [x] Download historical OHLCV data for all watched symbols (BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT, AVAXUSDT, LINKUSDT, DOTUSDT)
- [x] Timeframes: 5m, 15m, 1h — downloaded Jan 1 - May 13, 2026
- [x] Verify installation with backtest (MinimalTestStrategy ran successfully)
- [ ] Port a proven Freqtrade strategy (e.g., NostalgiaForInfinity or EMA-RSI composite)
- [ ] Adapt strategy format to our signal engine
- [ ] Backtest with our data

### Phase D: Strategy Optimization
- [ ] Run Hyperopt on imported strategies
- [ ] Enable only top-performing strategies
- [ ] Add market regime detector (trend vs ranging vs volatile)
- [ ] Dynamic strategy switching based on regime

## References
- Freqtrade: https://github.com/freqtrade/freqtrade (25k stars, FreqAI ML)
- Hummingbot: https://github.com/hummingbot/hummingbot (market making)
- Strategy template target: EMA crossover + RSI filter + volume confirmation

## Notes
- This is a multi-day effort. Record progress in this file.
- Do NOT run real trading until paper trading shows 2+ weeks of positive returns.
