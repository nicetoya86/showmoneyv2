"""
Scalping Strategy Backtesting Script
Tests the enhanced scalping algorithm with Phase 1 improvements:
- Volume confirmation (OBV + surge)
- RSI-MACD combination
- Bearish divergence filter
- VWAP distance
- Multi-timeframe confirmation
- Dynamic ATR optimization
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import ta


class EnhancedScalpingStrategy(Strategy):
    # Parameters (can be optimized)
    rsi_period = 14
    macd_fast = 12
    macd_slow = 26
    macd_signal = 9
    volume_surge_threshold = 2.0  # Relaxed from 2.5
    atr_period = 14
    atr_stop_mult_low = 1.4
    atr_stop_mult_medium = 1.7
    atr_stop_mult_high = 2.0
    atr_target_mult_low = 2.1
    atr_target_mult_medium = 2.4
    atr_target_mult_high = 3.0
    
    def init(self):
        # Calculate indicators
        close = self.data.Close
        high = self.data.High
        low = self.data.Low
        volume = self.data.Volume
        
        # RSI
        self.rsi = self.I(ta.momentum.rsi, pd.Series(close), window=self.rsi_period)
        
        # MACD
        macd_indicator = ta.trend.MACD(
            pd.Series(close),
            window_slow=self.macd_slow,
            window_fast=self.macd_fast,
            window_sign=self.macd_signal
        )
        self.macd = self.I(lambda: macd_indicator.macd())
        self.macd_signal_line = self.I(lambda: macd_indicator.macd_signal())
        self.macd_histogram = self.I(lambda: macd_indicator.macd_diff())
        
        # Volume indicators
        self.volume_sma = self.I(ta.trend.sma_indicator, pd.Series(volume), window=20)
        self.volume_surge = self.I(lambda: volume / self.volume_sma)
        
        # OBV
        self.obv = self.I(ta.volume.on_balance_volume, pd.Series(close), pd.Series(volume))
        self.obv_sma = self.I(ta.trend.sma_indicator, self.obv, window=5)
        
        # VWAP (approximation using daily reset)
        typical_price = (high + low + close) / 3
        self.vwap = self.I(lambda: (typical_price * volume).cumsum() / volume.cumsum())
        
        # ATR for dynamic stops
        self.atr = self.I(ta.volatility.average_true_range, 
                         pd.Series(high), pd.Series(low), pd.Series(close),
                         window=self.atr_period)
        
        # Moving averages for trend
        self.sma20 = self.I(ta.trend.sma_indicator, pd.Series(close), window=20)
        self.sma60 = self.I(ta.trend.sma_indicator, pd.Series(close), window=60)
        
    def next(self):
        # Skip if not enough data
        if len(self.data) < 60:
            return
            
        # Exit conditions (hit stop or target)
        if self.position:
            current_price = self.data.Close[-1]
            if current_price <= self.position.sl or current_price >= self.position.tp:
                self.position.close()
                return
        
        # Don't enter new position if already in one
        if self.position:
            return
        
        # Entry conditions
        # 1. Uptrend (daily SMA alignment)
        if self.sma20[-1] <= self.sma60[-1]:
            return
        
        # 2. RSI in range (not overbought, not oversold)
        if self.rsi[-1] < 40 or self.rsi[-1] > 70:
            return
        
        # 3. MACD bullish
        if self.macd_histogram[-1] <= 0:
            return
        if self.macd[-1] <= self.macd_signal_line[-1]:
            return
        
        # 4. Volume confirmation with OBV
        if self.volume_surge[-1] < self.volume_surge_threshold:
            return
        if self.obv[-1] <= self.obv_sma[-1]:
            return
        
        # 5. VWAP alignment (price above VWAP but not overextended)
        vwap_distance = (self.data.Close[-1] - self.vwap[-1]) / self.vwap[-1]
        if vwap_distance < 0.005 or vwap_distance > 0.03:
            return
        
        # 6. Bearish divergence check (simplified)
        # Check if price made higher high but RSI made lower high
        if len(self.data) >= 20:
            recent_high_price = max(self.data.Close[-10:])
            prev_high_price = max(self.data.Close[-20:-10])
            recent_high_rsi_idx = list(self.data.Close[-10:]).index(recent_high_price) + len(self.data) - 10
            prev_high_rsi_idx = list(self.data.Close[-20:-10]).index(prev_high_price) + len(self.data) - 20
            
            if recent_high_price > prev_high_price:
                if self.rsi[recent_high_rsi_idx] < self.rsi[prev_high_rsi_idx]:
                    return  # Bearish divergence detected, skip entry
        
        # Dynamic ATR-based stops and targets
        atr_ratio = self.atr[-1] / self.data.Close[-1]
        
        if atr_ratio > 0.05:
            volatility_regime = 'high'
            stop_mult = self.atr_stop_mult_high
            target_mult = self.atr_target_mult_high
        elif atr_ratio > 0.03:
            volatility_regime = 'medium'
            stop_mult = self.atr_stop_mult_medium
            target_mult = self.atr_target_mult_medium
        else:
            volatility_regime = 'low'
            stop_mult = self.atr_stop_mult_low
            target_mult = self.atr_target_mult_low
        
        entry_price = self.data.Close[-1]
        stop_loss = entry_price - self.atr[-1] * stop_mult
        take_profit = entry_price + self.atr[-1] * target_mult
        
        # Cap stops for scalping
        stop_loss = max(stop_loss, entry_price * 0.94)  # Max 6% stop
        take_profit = min(take_profit, entry_price * 1.12)  # Max 12% target
        
        # Enter long position
        self.buy(sl=stop_loss, tp=take_profit)


def download_korean_stock_data(ticker, start_date, end_date):
    """Download Korean stock data from Yahoo Finance"""
    # Korean stocks use .KS (KOSPI) or .KQ (KOSDAQ) suffix
    if not ticker.endswith('.KS') and not ticker.endswith('.KQ'):
        ticker = ticker + '.KS'
    
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)
    return data


def run_backtest(ticker='005930.KS', start_date='2023-01-01', end_date='2026-02-13'):
    """Run backtest on a single stock"""
    print(f"Downloading data for {ticker}...")
    data = download_korean_stock_data(ticker, start_date, end_date)
    
    if data.empty:
        print(f"No data available for {ticker}")
        return None
    
    print(f"Running backtest...")
    bt = Backtest(data, EnhancedScalpingStrategy, cash=10000000, commission=0.0025)
    stats = bt.run()
    
    print("\n" + "="*60)
    print(f"Backtest Results for {ticker}")
    print("="*60)
    print(stats)
    print("="*60)
    
    # Plot results
    bt.plot()
    
    return stats


def run_multiple_stocks_backtest(tickers, start_date='2023-01-01', end_date='2026-02-13'):
    """Run backtest on multiple stocks and aggregate results"""
    results = []
    
    for ticker in tickers:
        print(f"\n\nProcessing {ticker}...")
        try:
            stats = run_backtest(ticker, start_date, end_date)
            if stats is not None:
                results.append({
                    'Ticker': ticker,
                    'Return': stats['Return [%]'],
                    'Sharpe Ratio': stats['Sharpe Ratio'],
                    'Max Drawdown': stats['Max. Drawdown [%]'],
                    'Win Rate': stats['Win Rate [%]'],
                    'Trades': stats['# Trades']
                })
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
    
    if results:
        results_df = pd.DataFrame(results)
        print("\n\n" + "="*80)
        print("AGGREGATE RESULTS")
        print("="*80)
        print(results_df.to_string(index=False))
        print("\nAverage Metrics:")
        print(f"  Avg Return: {results_df['Return'].mean():.2f}%")
        print(f"  Avg Sharpe Ratio: {results_df['Sharpe Ratio'].mean():.2f}")
        print(f"  Avg Win Rate: {results_df['Win Rate'].mean():.2f}%")
        print("="*80)
        
        results_df.to_csv('d:\\vibecording\\showmoneyv2\\ml\\backtesting\\scalping_results.csv', index=False)
        print("\nResults saved to scalping_results.csv")
    
    return results


if __name__ == '__main__':
    # Test on Samsung Electronics (005930.KS)
    print("Testing Enhanced Scalping Strategy")
    print("Phase 1 improvements included:")
    print("- Volume confirmation (OBV + surge)")
    print("- RSI-MACD combination")
    print("- Bearish divergence filter")
    print("- VWAP distance")
    print("- Dynamic ATR optimization")
    print("\n")
    
    # Single stock test
    run_backtest('005930.KS', '2024-01-01', '2026-02-13')
    
    # Multiple stocks test (top KOSPI stocks)
    # tickers = ['005930.KS', '000660.KS', '035420.KS', '005380.KS', '051910.KS']
    # run_multiple_stocks_backtest(tickers, '2024-01-01', '2026-02-13')
