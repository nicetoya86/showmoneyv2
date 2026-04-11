"""
Parameter Optimization Script using vectorbt
Optimizes key parameters for the enhanced scalping strategy:
- Volume surge thresholds
- RSI boundaries
- ATR multipliers
- VWAP distance thresholds
"""

import pandas as pd
import numpy as np
import yfinance as yf
import vectorbt as vbt
from datetime import datetime, timedelta
import matplotlib.pyplot as plt


def download_korean_stock_data(ticker, start_date, end_date):
    """Download Korean stock data"""
    if not ticker.endswith('.KS') and not ticker.endswith('.KQ'):
        ticker = ticker + '.KS'
    
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)
    return data


def optimize_scalping_parameters(ticker='005930.KS', start_date='2024-01-01', end_date='2026-02-13'):
    """
    Optimize scalping strategy parameters using grid search with vectorbt
    """
    print(f"Downloading data for {ticker}...")
    data = download_korean_stock_data(ticker, start_date, end_date)
    
    if data.empty:
        print(f"No data available for {ticker}")
        return None
    
    close = data['Close']
    high = data['High']
    low = data['Low']
    volume = data['Volume']
    
    # Calculate base indicators
    rsi = vbt.RSI.run(close, window=14).rsi
    macd = vbt.MACD.run(close, fast_window=12, slow_window=26, signal_window=9)
    
    # Volume indicators
    volume_sma = volume.rolling(window=20).mean()
    volume_surge = volume / volume_sma
    
    # ATR
    atr = vbt.ATR.run(high, low, close, window=14).atr
    atr_pct = atr / close
    
    # SMA for trend
    sma20 = close.rolling(window=20).mean()
    sma60 = close.rolling(window=60).mean()
    uptrend = sma20 > sma60
    
    # VWAP (daily approximation)
    typical_price = (high + low + close) / 3
    vwap = (typical_price * volume).cumsum() / volume.cumsum()
    vwap_distance = (close - vwap) / vwap
    
    print("\nOptimizing parameters...")
    print("This may take a few minutes...")
    
    # Parameter ranges to test
    volume_surge_thresholds = np.arange(1.5, 3.0, 0.25)
    rsi_lower_bounds = np.arange(30, 45, 5)
    rsi_upper_bounds = np.arange(65, 80, 5)
    atr_stop_mults = np.arange(1.4, 2.2, 0.2)
    atr_target_mults = np.arange(2.0, 3.5, 0.3)
    
    best_sharpe = -np.inf
    best_params = {}
    results = []
    
    total_combinations = (len(volume_surge_thresholds) * len(rsi_lower_bounds) * 
                         len(rsi_upper_bounds) * len(atr_stop_mults) * len(atr_target_mults))
    
    print(f"Testing {total_combinations} parameter combinations...")
    
    count = 0
    for vol_thresh in volume_surge_thresholds:
        for rsi_low in rsi_lower_bounds:
            for rsi_high in rsi_upper_bounds:
                for stop_mult in atr_stop_mults:
                    for target_mult in atr_target_mults:
                        count += 1
                        if count % 100 == 0:
                            print(f"Progress: {count}/{total_combinations} ({count*100/total_combinations:.1f}%)")
                        
                        # Generate signals
                        entries = (
                            uptrend &  # Trend alignment
                            (rsi > rsi_low) & (rsi < rsi_high) &  # RSI range
                            (macd.macd > macd.signal) &  # MACD bullish
                            (volume_surge > vol_thresh) &  # Volume surge
                            (vwap_distance > 0.005) & (vwap_distance < 0.03)  # VWAP alignment
                        )
                        
                        # Calculate stops and targets
                        stop_distance = atr * stop_mult
                        target_distance = atr * target_mult
                        
                        # Cap stops
                        stop_distance = np.minimum(stop_distance, close * 0.06)  # Max 6%
                        target_distance = np.minimum(target_distance, close * 0.12)  # Max 12%
                        
                        sl = close - stop_distance
                        tp = close + target_distance
                        
                        # Run portfolio simulation
                        try:
                            pf = vbt.Portfolio.from_signals(
                                close,
                                entries,
                                sl_stop=sl,
                                tp_stop=tp,
                                fees=0.0025,
                                init_cash=10000000
                            )
                            
                            sharpe = pf.sharpe_ratio()
                            total_return = pf.total_return() * 100
                            win_rate = pf.trades.win_rate() * 100 if pf.trades.count() > 0 else 0
                            num_trades = pf.trades.count()
                            
                            if not np.isnan(sharpe) and sharpe > best_sharpe and num_trades >= 5:
                                best_sharpe = sharpe
                                best_params = {
                                    'volume_surge_threshold': vol_thresh,
                                    'rsi_lower': rsi_low,
                                    'rsi_upper': rsi_high,
                                    'atr_stop_mult': stop_mult,
                                    'atr_target_mult': target_mult,
                                    'sharpe_ratio': sharpe,
                                    'total_return': total_return,
                                    'win_rate': win_rate,
                                    'num_trades': num_trades
                                }
                            
                            results.append({
                                'vol_thresh': vol_thresh,
                                'rsi_low': rsi_low,
                                'rsi_high': rsi_high,
                                'stop_mult': stop_mult,
                                'target_mult': target_mult,
                                'sharpe': sharpe,
                                'return': total_return,
                                'win_rate': win_rate,
                                'trades': num_trades
                            })
                        except Exception as e:
                            continue
    
    print("\n" + "="*70)
    print("OPTIMIZATION RESULTS")
    print("="*70)
    print("\nBest Parameters:")
    for key, value in best_params.items():
        print(f"  {key}: {value:.4f}")
    print("="*70)
    
    # Save results
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('sharpe', ascending=False)
    results_df.to_csv('d:\\vibecording\\showmoneyv2\\ml\\backtesting\\optimization_results.csv', index=False)
    print("\nTop 10 parameter combinations:")
    print(results_df.head(10).to_string(index=False))
    print("\nFull results saved to optimization_results.csv")
    
    # Visualize parameter impact
    if len(results_df) > 0:
        fig, axes = plt.subplots(2, 3, figsize=(15, 10))
        fig.suptitle('Parameter Impact on Sharpe Ratio', fontsize=16)
        
        # Volume threshold impact
        vol_grouped = results_df.groupby('vol_thresh')['sharpe'].mean()
        axes[0, 0].plot(vol_grouped.index, vol_grouped.values, marker='o')
        axes[0, 0].set_xlabel('Volume Surge Threshold')
        axes[0, 0].set_ylabel('Avg Sharpe Ratio')
        axes[0, 0].grid(True)
        
        # RSI bounds impact
        rsi_low_grouped = results_df.groupby('rsi_low')['sharpe'].mean()
        axes[0, 1].plot(rsi_low_grouped.index, rsi_low_grouped.values, marker='o')
        axes[0, 1].set_xlabel('RSI Lower Bound')
        axes[0, 1].set_ylabel('Avg Sharpe Ratio')
        axes[0, 1].grid(True)
        
        rsi_high_grouped = results_df.groupby('rsi_high')['sharpe'].mean()
        axes[0, 2].plot(rsi_high_grouped.index, rsi_high_grouped.values, marker='o')
        axes[0, 2].set_xlabel('RSI Upper Bound')
        axes[0, 2].set_ylabel('Avg Sharpe Ratio')
        axes[0, 2].grid(True)
        
        # ATR multipliers impact
        stop_grouped = results_df.groupby('stop_mult')['sharpe'].mean()
        axes[1, 0].plot(stop_grouped.index, stop_grouped.values, marker='o')
        axes[1, 0].set_xlabel('ATR Stop Multiplier')
        axes[1, 0].set_ylabel('Avg Sharpe Ratio')
        axes[1, 0].grid(True)
        
        target_grouped = results_df.groupby('target_mult')['sharpe'].mean()
        axes[1, 1].plot(target_grouped.index, target_grouped.values, marker='o')
        axes[1, 1].set_xlabel('ATR Target Multiplier')
        axes[1, 1].set_ylabel('Avg Sharpe Ratio')
        axes[1, 1].grid(True)
        
        # Sharpe distribution
        axes[1, 2].hist(results_df['sharpe'].dropna(), bins=30, edgecolor='black')
        axes[1, 2].set_xlabel('Sharpe Ratio')
        axes[1, 2].set_ylabel('Frequency')
        axes[1, 2].grid(True)
        
        plt.tight_layout()
        plt.savefig('d:\\vibecording\\showmoneyv2\\ml\\backtesting\\parameter_optimization.png', dpi=150)
        print("\nVisualization saved to parameter_optimization.png")
        plt.show()
    
    return best_params


if __name__ == '__main__':
    print("Enhanced Scalping Strategy - Parameter Optimization")
    print("Using vectorbt for fast grid search\n")
    
    # Optimize on Samsung Electronics
    best_params = optimize_scalping_parameters('005930.KS', '2024-01-01', '2026-02-13')
    
    if best_params:
        print("\n\nRECOMMENDED PARAMETER UPDATE:")
        print("-" * 70)
        print("Update these values in scalping_scanner_code.js:")
        print(f"  volume_surge threshold: {best_params['volume_surge_threshold']:.2f}")
        print(f"  RSI range: {best_params['rsi_lower']:.0f} - {best_params['rsi_upper']:.0f}")
        print(f"  ATR stop multiplier: {best_params['atr_stop_mult']:.2f}")
        print(f"  ATR target multiplier: {best_params['atr_target_mult']:.2f}")
        print("-" * 70)
