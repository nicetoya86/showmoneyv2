import pandas as pd

from backtest.fit_signal_weights import encode_features, fit_and_evaluate


def _trade(pattern_type, pnl, **aux_overrides):
    aux = {
        "rvol_tier": 0, "obv_trend": 0, "macd_state": "neutral", "sma_aligned": False,
        "intraday_tier": 0, "supply_tier": 0, "dart_tier": 0, "rsi_golden": False,
        "adx_trend": False, "high52_tier": 0,
    }
    aux.update(aux_overrides)
    return {"pattern_type": pattern_type, "pnl": pnl, "aux_features": aux}


def test_encode_features_produces_expected_columns():
    trades = [
        _trade("D박스", 0.05, rvol_tier=2, obv_trend=1, sma_aligned=True),
        _trade("A눌림목", -0.03, rvol_tier=0, obv_trend=-1, sma_aligned=False),
    ]
    X, y = encode_features(trades)
    assert len(X) == 2
    assert list(y) == [True, False]
    # one-hot dummy columns must exist for the non-default levels actually observed
    assert any(c.startswith("rvol_tier_") for c in X.columns)
    assert any(c.startswith("pattern_type_") for c in X.columns)
    assert "sma_aligned" in X.columns  # boolean features are not dummy-expanded


def test_encode_features_handles_missing_aux_features_gracefully():
    # a trade with an empty aux_features dict (shouldn't happen post-Task-3, but the encoder
    # must not crash on it -- treat every key as its zero/neutral default)
    trades = [{"pattern_type": "D박스", "pnl": 0.02, "aux_features": {}}]
    X, y = encode_features(trades)
    assert len(X) == 1


def test_fit_and_evaluate_returns_coefficients_and_auc():
    import numpy as np
    rng = np.random.RandomState(0)
    n = 200
    trades = []
    for i in range(n):
        rvol_tier = int(rng.randint(0, 5))
        # construct a clear, learnable relationship: higher rvol_tier -> more often a win
        pnl = 0.05 if rng.random() < (0.2 + 0.15 * rvol_tier) else -0.03
        trades.append(_trade("D박스", pnl, rvol_tier=rvol_tier))
    X, y = encode_features(trades)
    split = n // 2
    result = fit_and_evaluate(X.iloc[:split], y.iloc[:split], X.iloc[split:], y.iloc[split:])
    assert "coefficients" in result
    assert "train_auc" in result and "test_auc" in result
    assert 0.5 <= result["train_auc"] <= 1.0
    # rvol_tier's dummy columns should have a positive coefficient given the constructed
    # relationship (higher tier -> more wins) -- at least one rvol_tier_* coefficient > 0
    rvol_coefs = [v for k, v in result["coefficients"].items() if k.startswith("rvol_tier_")]
    assert any(c > 0 for c in rvol_coefs)
