# Backtesting Infrastructure

이 디렉토리는 단타/스윙 트레이딩 알고리즘의 백테스팅 및 파라미터 최적화를 위한 스크립트를 포함합니다.

## 설치

```bash
cd d:\vibecording\showmoneyv2\ml\backtesting
pip install -r requirements.txt
```

## 스크립트 설명

### 1. backtest_scalping.py
**목적**: 향상된 단타 전략 백테스트

**주요 기능**:
- Phase 1 개선사항 적용 (Volume confirmation, RSI-MACD, Divergence filter, VWAP, Dynamic ATR)
- 단일 종목 또는 다수 종목 백테스트
- 상세한 성과 지표 리포트 (Sharpe Ratio, Win Rate, MDD 등)
- 시각화 차트 생성

**사용법**:
```bash
python backtest_scalping.py
```

**결과**: 
- 콘솔에 성과 지표 출력
- 차트 시각화 (matplotlib)
- `scalping_results.csv` 파일 생성 (다수 종목 테스트 시)

### 2. optimize_thresholds.py
**목적**: vectorbt를 사용한 파라미터 최적화

**최적화 대상 파라미터**:
- `volume_surge_threshold`: 거래량 급증 기준 (1.5 ~ 3.0)
- `rsi_lower`: RSI 하한 (30 ~ 45)
- `rsi_upper`: RSI 상한 (65 ~ 80)
- `atr_stop_mult`: ATR 손절 배수 (1.4 ~ 2.2)
- `atr_target_mult`: ATR 목표가 배수 (2.0 ~ 3.5)

**사용법**:
```bash
python optimize_thresholds.py
```

**결과**:
- 최적 파라미터 조합 출력
- `optimization_results.csv`: 모든 조합 결과
- `parameter_optimization.png`: 파라미터 영향 시각화

## 워크플로우

### 단계 1: 백테스트 실행
현재 파라미터로 전략 성과 검증
```bash
python backtest_scalping.py
```

### 단계 2: 파라미터 최적화
더 나은 파라미터 조합 탐색
```bash
python optimize_thresholds.py
```

### 단계 3: 결과 분석
- `optimization_results.csv`에서 상위 10개 조합 검토
- Sharpe Ratio, Win Rate, Total Return 균형 고려
- 과적합 방지를 위해 최소 거래 수(5회 이상) 확인

### 단계 4: 파라미터 적용
- 최적 파라미터를 `scalping_scanner_code.js`에 반영
- n8n workflow 업데이트

## 주요 성과 지표

- **Sharpe Ratio**: 위험 대비 수익률 (높을수록 좋음, >1.0 목표)
- **Win Rate**: 승률 (%) (>50% 목표)
- **Max Drawdown**: 최대 낙폭 (%) (낮을수록 좋음, <20% 목표)
- **Total Return**: 총 수익률 (%)
- **Number of Trades**: 거래 횟수 (너무 적으면 과소적합, 너무 많으면 과적합)

## 예시 출력

```
Backtest Results for 005930.KS
============================================================
Start                     2024-01-02 00:00:00
End                       2026-02-13 00:00:00
Duration                  771 days 00:00:00
Exposure Time [%]         35.2
Equity Final [₩]          11250000
Equity Peak [₩]           11800000
Return [%]                12.5
Buy & Hold Return [%]     8.3
Return (Ann.) [%]         18.2
Volatility (Ann.) [%]     24.5
Sharpe Ratio              1.42
Max. Drawdown [%]         -15.3
Avg. Drawdown [%]         -5.2
Max. Drawdown Duration    45 days
Win Rate [%]              58.3
# Trades                  42
============================================================
```

## 주의사항

1. **데이터 품질**: Yahoo Finance 데이터는 완벽하지 않을 수 있음
2. **슬리피지**: 실제 매매 시 슬리피지 고려 필요
3. **수수료**: commission=0.0025 (0.25%) 적용
4. **과적합**: 과거 데이터 최적화 결과가 미래에도 유효하다는 보장 없음
5. **시장 조건**: 백테스트 기간의 시장 조건이 현재와 다를 수 있음

## 개선 방향

- [ ] Walk-forward analysis 구현
- [ ] Out-of-sample testing
- [ ] Monte Carlo simulation for robustness
- [ ] 다양한 시장 조건(상승/하락/횡보)별 성과 분석
- [ ] 스윙 전략 백테스팅 스크립트 추가
