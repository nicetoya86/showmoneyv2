# HiTalk Model 재학습 가이드

## 현재 상태

Phase 1-2 개선사항은 **Rule-based 레이어**로 구현되었으며, 기존 ML 모델 재학습이 **불필요**합니다.

### 아키텍처

```
[데이터 입력]
    ↓
[ML Layer: HiTalk Model]
    - 19개 daily features
    - Logistic Regression
    - 확률 출력: pUP (단타), pMAT (스윙)
    ↓
[Rule-based Enhancement Layer] ← Phase 1-2 개선사항
    - Volume confirmation (OBV + surge)
    - RSI-MACD combination
    - Bearish divergence filter
    - VWAP distance
    - Multi-timeframe confirmation
    - Dynamic ATR optimization
    ↓
[최종 점수 및 진입 결정]
```

## Phase 1-2가 Rule-based인 이유

### 1. **실시간 데이터 의존성**
- **VWAP**: 일중 계속 변화하는 indicator
- **OBV**: 실시간 volume flow 추적
- **MACD**: 단기 momentum 신호
- **MTF**: 여러 timeframe 동시 확인

→ ML 모델은 **daily close 기준**으로 학습되므로, 이러한 intraday 신호는 rule-based가 적합

### 2. **해석 가능성 (Interpretability)**
- Rule-based 신호: "VWAP 상회", "RSI-MACD 확인" 등 명확한 이유 제공
- ML 특성 중요도: 블랙박스, 설명 어려움

→ 트레이딩 알림에서 **신호 설명**이 중요하므로 rule-based가 유리

### 3. **유지보수 용이성**
- Rule-based: 파라미터 조정만으로 즉시 변경 가능
- ML 재학습: 데이터 수집 → 학습 → 검증 → 배포 (수일 소요)

→ 백테스트 결과에 따라 **빠른 조정**이 필요한 경우 rule-based가 효율적

## 언제 ML 재학습이 필요한가?

다음과 같은 경우 ML 모델 재학습을 고려해야 합니다:

### 1. **새로운 Daily Feature 추가**
예시:
- `bollinger_width`: Bollinger Bands 폭 (변동성 지표)
- `volume_spike_3d`: 최근 3일 volume spike 여부
- `sector_momentum`: 섹터별 상대 강도

→ 이런 feature는 daily close 기준으로 계산 가능하므로 ML 학습에 포함 가능

### 2. **HiTalk 실적 데이터 업데이트**
- `hitalk_full_data.xlsx` 파일에 최근 추천 실적 추가
- 더 많은 데이터로 모델 정확도 향상

### 3. **모델 알고리즘 변경**
- Logistic Regression → XGBoost/LightGBM
- 앙상블 모델 도입
- Deep Learning (LSTM, Transformer) 시도

## ML 재학습 실행 방법

### 전제조건
- `hitalk_full_data.xlsx` 파일 준비 (최신 데이터)
- Python 환경 및 라이브러리 설치

### 단계 1: 학습 데이터 준비
```bash
# hitalk_full_data.xlsx 파일 위치 확인
# 컬럼: type, name, code, rec_price, hit_price, return_pct, hit_days, rec_date, sell_date
```

### 단계 2: 모델 학습
```bash
cd d:\vibecording\showmoneyv2
python ml\hitalk_train_type_model.py --xlsx hitalk_full_data.xlsx --max-samples 1200
```

### 단계 3: 모델 평가
학습 후 출력되는 metrics 확인:
- **AUC (Area Under Curve)**: >0.85 목표
- **Precision/Recall**: 균형 확인
- **Confusion Matrix**: False Positive/Negative 비율

### 단계 4: 모델 적용
1. 생성된 `models/hitalk_type_model.json` 파일 확인
2. 모델 JSON 내용을 n8n workflow의 `HITALK_UP_MODEL`에 복사
3. Workflow 저장 및 테스트

## 새 Feature 추가 예시

만약 `bollinger_width` feature를 추가하고 싶다면:

### 1. Feature 계산 함수 추가 (hitalk_train_type_model.py)
```python
def build_features_daily(series: YahooSeries, idx: int) -> Dict[str, float]:
    # ... 기존 features ...
    
    # Bollinger Bands width
    bb_upper = sma20[i] + 2 * std20[i]
    bb_lower = sma20[i] - 2 * std20[i]
    bollinger_width = (bb_upper - bb_lower) / sma20[i] if sma20[i] > 0 else 0
    
    return {
        # ... 기존 features ...
        "bollinger_width": float(bollinger_width),
    }
```

### 2. Feature 목록 업데이트
```python
feature_cols = [
    "daily_change",
    # ... 기존 features ...
    "bollinger_width",  # 새 feature 추가
]
```

### 3. 재학습 및 배포
```bash
python ml\hitalk_train_type_model.py
# 새 모델을 n8n workflow에 적용
```

## 현재 권장사항

### ✅ 당장 할 일
1. **백테스팅 실행**: Phase 1-2 개선 효과 검증
   ```bash
   python ml\backtesting\backtest_scalping.py
   ```

2. **파라미터 최적화**: Rule-based 임계값 조정
   ```bash
   python ml\backtesting\optimize_thresholds.py
   ```

3. **실전 모니터링**: 1-2주간 알림 품질 모니터링

### ⏳ 추후 검토 (3-6개월 후)
- HiTalk 실적 데이터 충분히 축적된 후 ML 재학습
- 새로운 daily feature 도입 (Bollinger, Stochastic 등)
- 앙상블 모델 (ML + Rule-based 가중 평균) 실험

## 요약

**현재 단계에서는 ML 재학습 불필요**

이유:
1. Phase 1-2 개선사항은 rule-based로 구현 완료
2. 기존 ML 모델(daily features)과 새 rule-based layer(intraday signals)가 상호보완적
3. Rule-based 접근이 실시간 트레이딩에 더 적합

다음 단계:
1. 백테스팅으로 효과 검증
2. 파라미터 최적화
3. 실전 모니터링 후 미세 조정

ML 재학습은 **데이터 충분히 축적** + **새 daily feature 도입 시** 고려
