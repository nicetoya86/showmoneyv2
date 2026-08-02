"""
Sub-project 10: fits an L2-regularized logistic regression predicting `pnl > 0` from the
auxiliary scoring-signal features (aux_features on each committed trade record), to check
whether src/swing-scanner.src.js's hand-tuned auxiliary weights (never statistically validated,
per docs/03-analysis/swing-algorithm-profitability-review.analysis.md Finding #3) are supported
by real backtest outcome data. Pattern base weights (60/50/45/40) are NOT refit here -- see
docs/superpowers/specs/2026-08-02-swing-algo-signal-weight-refit-design.md Section 1 for the
confirmed scope decision.

Does not change any production code or recommend a literal weight replacement -- see that
design doc's Section 5.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score


def encode_features(trades: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, pd.Series]:
    rows = []
    labels = []
    for t in trades:
        aux = t.get("aux_features") or {}
        row = {
            "pattern_type": t["pattern_type"],
            "rvol_tier": aux.get("rvol_tier", 0),
            "obv_trend": aux.get("obv_trend", 0),
            "macd_state": aux.get("macd_state", "neutral"),
            "sma_aligned": bool(aux.get("sma_aligned", False)),
            "intraday_tier": aux.get("intraday_tier", 0),
            "supply_tier": aux.get("supply_tier", 0),
            "dart_tier": aux.get("dart_tier", 0),
            "rsi_golden": bool(aux.get("rsi_golden", False)),
            "adx_trend": bool(aux.get("adx_trend", False)),
            "high52_tier": aux.get("high52_tier", 0),
        }
        rows.append(row)
        labels.append(t["pnl"] > 0)

    df = pd.DataFrame(rows)
    # rvol_tier/obv_trend/intraday_tier/supply_tier/dart_tier/high52_tier are ordinal ints but
    # not assumed linear in score contribution -- one-hot them; macd_state/pattern_type are
    # already categorical strings.
    dummy_cols = ["pattern_type", "rvol_tier", "obv_trend", "macd_state", "intraday_tier",
                  "supply_tier", "dart_tier", "high52_tier"]
    X = pd.get_dummies(df, columns=dummy_cols, drop_first=True)
    y = pd.Series(labels, name="win")
    return X, y


def fit_and_evaluate(
    train_X: pd.DataFrame, train_y: pd.Series, test_X: pd.DataFrame, test_y: pd.Series,
) -> Dict[str, Any]:
    # Align columns in case train/test one-hot encoding produced different dummy sets (a level
    # present in one split but not the other) -- reindex test to train's columns, filling 0.
    test_X = test_X.reindex(columns=train_X.columns, fill_value=0)

    model = LogisticRegression(penalty="l2", C=1.0, max_iter=1000)
    model.fit(train_X, train_y)

    train_pred = model.predict_proba(train_X)[:, 1]
    test_pred = model.predict_proba(test_X)[:, 1]

    coefficients = dict(zip(train_X.columns, model.coef_[0].tolist()))
    coefficients["intercept"] = float(model.intercept_[0])

    return {
        "coefficients": coefficients,
        "train_auc": float(roc_auc_score(train_y, train_pred)),
        "test_auc": float(roc_auc_score(test_y, test_pred)),
        "n_train": int(len(train_y)),
        "n_test": int(len(test_y)),
        "train_positive_rate": float(train_y.mean()),
        "test_positive_rate": float(test_y.mean()),
    }


def main() -> None:
    d = json.load(open("backtest_out_swing_v2_with_features.json", encoding="utf-8"))
    trades = d["trades"]

    train_trades = [t for t in trades if "2022-01-01" <= t["date"] <= "2024-06-30"]
    test_trades = [t for t in trades if "2024-07-01" <= t["date"] <= "2026-01-01"]
    print(f"train trades: {len(train_trades)}  test trades: {len(test_trades)}")

    train_X, train_y = encode_features(train_trades)
    test_X, test_y = encode_features(test_trades)

    result = fit_and_evaluate(train_X, train_y, test_X, test_y)
    print(json.dumps({k: v for k, v in result.items() if k != "coefficients"}, indent=2))
    print("coefficients:")
    for k, v in sorted(result["coefficients"].items(), key=lambda kv: -abs(kv[1])):
        print(f"  {k}: {v:.4f}")

    json.dump(result, open("backtest_signal_weight_fit.json", "w", encoding="utf-8"),
               ensure_ascii=False, indent=2)
    print("wrote backtest_signal_weight_fit.json")


if __name__ == "__main__":
    main()
