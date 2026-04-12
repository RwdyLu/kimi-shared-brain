#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, '/tmp/kimi-shared-brain')
os.chdir('/tmp/kimi-shared-brain')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

try:
    import ccxt
    print('Using ccxt to fetch market data...')
    exchange = ccxt.binance({'enableRateLimit': True})
    
    # Fetch OHLCV data
    symbol_btc = 'BTC/USDT'
    symbol_eth = 'ETH/USDT'
    timeframe = '4h'
    limit = 540  # ~90 days of 4h data
    
    print('Fetching BTC data...')
    btc_ohlcv = exchange.fetch_ohlcv(symbol_btc, timeframe, limit=limit)
    print('Fetching ETH data...')
    eth_ohlcv = exchange.fetch_ohlcv(symbol_eth, timeframe, limit=limit)
    
    # Convert to DataFrame
    btc_df = pd.DataFrame(btc_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    eth_df = pd.DataFrame(eth_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    print(f'\nBTC data points: {len(btc_df)}')
    print(f'ETH data points: {len(eth_df)}')
    
    # Calculate returns
    btc_returns = btc_df['close'].pct_change().dropna()
    eth_returns = eth_df['close'].pct_change().dropna()
    
    # Align data
    min_len = min(len(btc_returns), len(eth_returns))
    btc_returns = btc_returns.iloc[-min_len:].reset_index(drop=True)
    eth_returns = eth_returns.iloc[-min_len:].reset_index(drop=True)
    
    # Calculate correlation
    correlation = btc_returns.corr(eth_returns)
    
    print(f'\n=== CORRELATION ANALYSIS ===')
    print(f'Overall Correlation: {correlation:.4f}')
    
    if correlation > 0.8:
        corr_strength = 'Very Strong Positive'
    elif correlation > 0.6:
        corr_strength = 'Strong Positive'
    elif correlation > 0.4:
        corr_strength = 'Moderate Positive'
    elif correlation > 0.2:
        corr_strength = 'Weak Positive'
    else:
        corr_strength = 'Very Weak / No Correlation'
    
    print(f'Correlation Strength: {corr_strength}')
    
    # Rolling correlation (30 periods ~ 5 days)
    rolling_window = 30
    rolling_corr = btc_returns.rolling(window=rolling_window).corr(eth_returns.shift(-rolling_window+1))
    
    print(f'\nRolling Correlation ({rolling_window}-period / ~5 days):')
    print(f'  Current: {rolling_corr.iloc[-1]:.4f}')
    print(f'  Recent Mean: {rolling_corr.tail(50).mean():.4f}')
    print(f'  Range: {rolling_corr.min():.4f} to {rolling_corr.max():.4f}')
    
    # Beta calculation
    covariance = btc_returns.cov(eth_returns)
    btc_variance = btc_returns.var()
    beta_eth = covariance / btc_variance if btc_variance != 0 else 0
    
    print(f'\n=== BETA ANALYSIS ===')
    print(f'ETH Beta relative to BTC: {beta_eth:.4f}')
    print(f'Interpretation: When BTC moves 1%, ETH typically moves {beta_eth:.2f}%')
    
    if beta_eth > 1.0:
        print(f'ETH is MORE volatile than BTC ({beta_eth:.2f}x)')
    else:
        print(f'ETH is LESS volatile than BTC ({beta_eth:.2f}x)')
    
    # Price statistics
    print(f'\n=== PRICE STATISTICS (90 Days) ===')
    btc_current = btc_df['close'].iloc[-1]
    btc_90d_ago = btc_df['close'].iloc[0]
    btc_return = ((btc_current / btc_90d_ago) - 1) * 100
    
    eth_current = eth_df['close'].iloc[-1]
    eth_90d_ago = eth_df['close'].iloc[0]
    eth_return = ((eth_current / eth_90d_ago) - 1) * 100
    
    print(f'\nBTC/USDT:')
    print(f'  Current: ${btc_current:,.2f}')
    print(f'  90d High: ${btc_df["high"].max():,.2f}')
    print(f'  90d Low: ${btc_df["low"].min():,.2f}')
    print(f'  90d Return: {btc_return:.2f}%')
    print(f'  Volatility (std): {btc_returns.std()*100:.2f}%')
    
    print(f'\nETH/USDT:')
    print(f'  Current: ${eth_current:,.2f}')
    print(f'  90d High: ${eth_df["high"].max():,.2f}')
    print(f'  90d Low: ${eth_df["low"].min():,.2f}')
    print(f'  90d Return: {eth_return:.2f}%')
    print(f'  Volatility (std): {eth_returns.std()*100:.2f}%')
    
    # Linear regression (simple cointegration test)
    x = btc_df['close'].values
    y = eth_df['close'].values
    n = len(x)
    x_mean = np.mean(x)
    y_mean = np.mean(y)
    
    slope = np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean) ** 2)
    intercept = y_mean - slope * x_mean
    
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y_mean) ** 2)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
    
    # Simple p-value approximation (not exact but useful)
    # Using correlation coefficient t-statistic
    r = np.corrcoef(x, y)[0, 1]
    t_stat = r * np.sqrt((n - 2) / (1 - r**2)) if r != 1 else float('inf')
    # Very rough approximation - if |t| > 2, p < 0.05
    p_value = 0.001 if abs(t_stat) > 3 else (0.05 if abs(t_stat) > 2 else 0.1)
    
    print(f'\n=== LINEAR RELATIONSHIP TEST ===')
    print(f'R-squared: {r_squared:.4f}')
    print(f'Correlation (price level): {r:.4f}')
    print(f'Approximate P-value: < {p_value}')
    print(f'Status: {"Strong Linear Relationship" if r_squared > 0.8 else "Moderate Relationship" if r_squared > 0.5 else "Weak Relationship"}')
    
    # Summary
    print(f'\n=== SUMMARY ===')
    print(f'1. Correlation: {correlation:.4f} ({corr_strength})')
    print(f'2. Beta: {beta_eth:.4f} (ETH is {"more" if beta_eth > 1 else "less"} volatile)')
    print(f'3. 90d Performance: BTC {btc_return:+.2f}%, ETH {eth_return:+.2f}%')
    print(f'4. Price Relationship: R² = {r_squared:.4f} ({"Strong" if r_squared > 0.8 else "Moderate" if r_squared > 0.5 else "Weak"})')
    
    # Investment insights
    print(f'\n=== INVESTMENT INSIGHTS ===')
    if correlation > 0.7:
        print('• HIGH CORRELATION: BTC and ETH move together most of the time')
        print('  → Diversification benefits are LIMITED')
        print('  → Both assets face similar market risks')
    elif correlation > 0.4:
        print('• MODERATE CORRELATION: Some co-movement but not perfect')
        print('  → Limited diversification benefits')
    else:
        print('• LOW CORRELATION: Assets move somewhat independently')
        print('  → Good diversification potential')
    
    if beta_eth > 1.1:
        print(f'• HIGH BETA ({beta_eth:.2f}): ETH amplifies BTC moves')
        print('  → Higher risk, higher potential reward')
        print('  → In bull markets: ETH outperforms')
        print('  → In bear markets: ETH underperforms')
    elif beta_eth < 0.9:
        print(f'• LOW BETA ({beta_eth:.2f}): ETH is more stable than BTC')
        print('  → Lower volatility relative to BTC')
    else:
        print(f'• BETA ~1.0 ({beta_eth:.2f}): Similar volatility profile')
    
    if btc_return > eth_return:
        print(f'• Recent 90d: BTC outperformed ETH by {btc_return - eth_return:.1f}%')
    else:
        print(f'• Recent 90d: ETH outperformed BTC by {eth_return - btc_return:.1f}%')
    
    # Save results for report
    results = {
        'correlation': correlation,
        'correlation_strength': corr_strength,
        'beta': beta_eth,
        'btc_current': btc_current,
        'eth_current': eth_current,
        'btc_return_90d': btc_return,
        'eth_return_90d': eth_return,
        'btc_volatility': btc_returns.std() * 100,
        'eth_volatility': eth_returns.std() * 100,
        'r_squared': r_squared,
        'price_correlation': r,
        'analysis_time': datetime.now().isoformat()
    }
    
    # Write to file for report generation
    import json
    with open('/tmp/kimi-shared-brain/outputs/btc_eth_correlation_analysis.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f'\nResults saved to outputs/btc_eth_correlation_analysis.json')
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
