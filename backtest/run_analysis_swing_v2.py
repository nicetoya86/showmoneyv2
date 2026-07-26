from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .analyze_swing_v2_results import analyze, regime_what_if


def main() -> None:
    trades = json.loads(Path("backtest_out_swing_v2.json").read_text(encoding="utf-8"))["trades"]
    result = analyze(trades)

    regime_raw = json.loads(Path("backtest_regime_series.json").read_text(encoding="utf-8"))
    regime_df = pd.DataFrame(
        {"regime_level": {k: v["regime_level"] for k, v in regime_raw.items()}}
    ).rename(index=lambda k: pd.Timestamp(k).date())
    result["regime_what_if"] = regime_what_if(trades, regime_df)

    Path("backtest_analysis_swing_v2.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
