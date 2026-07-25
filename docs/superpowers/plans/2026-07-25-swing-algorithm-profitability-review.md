# Swing Algorithm Profitability Review — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faithfully port the *currently deployed* swing-scanner trading algorithm (`src/swing-scanner.src.js`, patterns A/B/C/D + full scoring + DART/supply data) into the Python backtest suite, run it over 200 KRX tickers × 2024-01-01→2026-01-01, and produce a combined code-review + empirical profitability report (markdown doc + Artifact dashboard) answering: *how sophisticated and how profitable is this system, really?*

**Architecture:** New, isolated Python modules under `backtest/` (kept separate from the existing stale `strategy_rules.py`/`run_backtest_swing.py` so nothing currently working is touched) implement: (1) the missing technical indicators, (2) historical KRX supply-demand + DART disclosure fetchers (both are market-wide daily pulls, not per-ticker, so ~500 API calls total for the whole date range), (3) a single pure function that reproduces the production pattern/scoring/grade/target/stop logic exactly, (4) a day-by-day exit simulator, and (5) an orchestration script that wires these into a full backtest run mirroring production's daily/weekly selection caps. A separate analysis script turns the resulting trade log into win-rate/PnL/MDD statistics, broken down by pattern and score tier, plus a secondary "what if the currently-dead regime gate still worked" comparison. The final deliverable combines this with the qualitative code-review findings already surfaced during brainstorming.

**Tech Stack:** Python 3.11, pandas, numpy, requests, pytest (all already used in `backtest/`). No new dependencies.

## Global Constraints

- Every new module lives under `backtest/` and does not modify `backtest/strategy_rules.py`, `backtest/run_backtest_swing.py`, or `backtest/models.py` (those stay as historical reference / unmodified).
- All monetary/percentage constants must be copied verbatim from `src/swing-scanner.src.js` (cited by line number below) — no re-derivation or "close enough" approximation.
- Toss real-time order-book confirmation is explicitly OUT of scope (no historical tick data exists) — every task that touches candidate generation must leave a `# NOT MODELED: Toss real-time confirm (see report §Limitations)` comment at the relevant point, not silently omit it.
- The regime entry-blocking gate (`if (regimeLevel >= 2 && grade !== '강매') return;`) is **not** present in current production (confirmed dead/regressed — see brainstorming notes). The *primary* backtest run must NOT apply this gate (to faithfully match what production actually does today). It is computed only for the secondary comparison in Task 9.
- Every numeric port (indicators, patterns, scoring) must ship with a unit test that pins down the exact expected value — no test that only asserts "runs without error."

---

## File Structure Overview

| File | Status | Responsibility |
|---|---|---|
| `backtest/indicators.py` | Modify | Add `ema`, `rsi14`, `adx`, `macd`, `obv` (existing `sma`/`atr`/`max_drawdown` untouched) |
| `backtest/krx_supply_history.py` | Create | Historical foreign/institutional net-buy, 1 call/trading day, disk-cached |
| `backtest/dart_history.py` | Create | Historical disclosure list, 1 call/trading day, disk-cached |
| `backtest/market_regime_history.py` | Create | KOSPI/KOSDAQ regimeLevel + macro overlay per day (secondary comparison only) |
| `backtest/swing_signal_engine.py` | Create | Faithful port: patterns A/B/C/D + scoring + grade + target/stop/RR |
| `backtest/simulate_exits.py` | Create | Day-by-day exit walk (target/stop/timeout) given entry+holdDays |
| `backtest/run_swing_v2_backtest.py` | Create | Orchestration: 200 tickers × date range, daily/weekly selection caps, writes trades JSON |
| `backtest/analyze_swing_v2_results.py` | Create | Stats: overall + per-pattern + per-score-tier + regime what-if |
| `docs/03-analysis/swing-algorithm-profitability-review.analysis.md` | Create | Final combined report |
| `swing-algorithm-profitability-review` Artifact (HTML) | Create | Visual dashboard |

---

### Task 1: Missing technical indicators

**Files:**
- Modify: `backtest/indicators.py`
- Test: `backtest/tests/test_indicators.py`

**Interfaces:**
- Produces: `ema(arr: np.ndarray, window: int) -> np.ndarray`, `rsi14(close: np.ndarray, idx: int) -> float`, `adx(high, low, close, idx, period=14) -> dict{adx,plusDI,minusDI}`, `macd(close, idx) -> dict{macd,signal,hist,histPrev,goldenCross}`, `obv(close, vol, idx) -> dict{obvTrend}` — all consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

Create `backtest/tests/__init__.py` (empty file) if it doesn't exist, then create `backtest/tests/test_indicators.py`:

```python
import numpy as np
from backtest.indicators import ema, rsi14, adx, macd, obv


def test_ema_matches_hand_computed_seed():
    # k = 2/(3+1) = 0.5; seed=first value; then v*k + prev*(1-k)
    arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    out = ema(arr, 2)
    assert out[0] == 1.0
    assert abs(out[1] - (2.0 * 0.6666666666666666 + 1.0 * 0.3333333333333334)) < 1e-9
    assert out[4] > out[3]  # rising series -> rising EMA


def test_rsi14_all_gains_is_100():
    close = np.array([float(i) for i in range(1, 20)])  # strictly increasing, no losses
    r = rsi14(close, len(close) - 1)
    assert r == 100.0


def test_rsi14_flat_series_is_nan_or_neutral():
    close = np.array([100.0] * 20)
    r = rsi14(close, len(close) - 1)
    # avgLoss == 0 and avgGain == 0 -> JS calcRSI14 returns 100 (avgLoss===0 branch)
    assert r == 100.0


def test_rsi14_insufficient_history_is_nan():
    close = np.array([1.0, 2.0, 3.0])
    r = rsi14(close, 2)
    assert np.isnan(r)


def test_adx_uptrend_plusDI_greater_than_minusDI():
    n = 60
    high = np.array([100.0 + i * 1.5 for i in range(n)])
    low = np.array([99.0 + i * 1.5 for i in range(n)])
    close = np.array([99.5 + i * 1.5 for i in range(n)])
    r = adx(high, low, close, n - 1, 14)
    assert r["plusDI"] > r["minusDI"]
    assert r["adx"] >= 0


def test_macd_golden_cross_detects_crossover():
    # Build a series that dips then rallies hard enough to flip MACD below->above signal
    n = 60
    close = np.array(
        [100.0 - i * 0.5 for i in range(30)] + [85.0 + i * 2.0 for i in range(30)]
    )
    r = macd(close, n - 1)
    assert r["hist"] > r["histPrev"]  # histogram expanding on the rally


def test_obv_uptrend_gives_positive_trend():
    n = 25
    close = np.array([100.0 + i for i in range(n)])  # steadily rising close
    vol = np.array([1000.0] * n)
    r = obv(close, vol, n - 1)
    assert r["obvTrend"] == 1


def test_obv_downtrend_gives_negative_trend():
    n = 25
    close = np.array([100.0 - i for i in range(n)])  # steadily falling close
    vol = np.array([1000.0] * n)
    r = obv(close, vol, n - 1)
    assert r["obvTrend"] == -1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_indicators.py -v`
Expected: FAIL with `ImportError: cannot import name 'ema' from 'backtest.indicators'` (functions don't exist yet)

- [ ] **Step 3: Implement the indicators**

Append to `backtest/indicators.py` (after the existing `max_drawdown` function):

```python
def ema(arr: np.ndarray, window: int) -> np.ndarray:
    """Port of swing-scanner.src.js `ema()` — seeded EMA (first finite value seeds, not SMA-seeded)."""
    out = np.full(len(arr), np.nan, dtype="float64")
    k = 2.0 / (window + 1)
    prev = np.nan
    for i, raw in enumerate(arr):
        v = float(raw)
        if not np.isfinite(v):
            continue
        if not np.isfinite(prev):
            out[i] = v
            prev = v
            continue
        out[i] = v * k + prev * (1 - k)
        prev = out[i]
    return out


def rsi14(close: np.ndarray, idx: int) -> float:
    """Port of swing-scanner.src.js `calcRSI14()` — simple (non-Wilder) rolling avg gain/loss."""
    period = 14
    start = max(0, idx - period * 3)
    sl = close[start : idx + 1]
    if len(sl) < period + 1:
        return float("nan")
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        d = float(sl[i]) - float(sl[i - 1])
        if d > 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(sl)):
        d = float(sl[i]) - float(sl[i - 1])
        avg_gain = (avg_gain * (period - 1) + max(d, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0.0)) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, idx: int, period: int = 14) -> dict:
    """Port of swing-scanner.src.js `calcADX()`."""
    need = period * 3 + 2
    start = max(0, idx - need)
    hi = high[start : idx + 1].astype("float64")
    lo = low[start : idx + 1].astype("float64")
    cl = close[start : idx + 1].astype("float64")
    n = len(hi)
    if n < period + 2:
        return {"adx": float("nan"), "plusDI": float("nan"), "minusDI": float("nan")}

    plus_dm, minus_dm, tr = [], [], []
    for i in range(1, n):
        up_move = hi[i] - hi[i - 1]
        down_move = lo[i - 1] - lo[i]
        plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
        tr.append(max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])))

    def smooth(arr):
        s = sum(arr[:period])
        out = [s]
        for i in range(period, len(arr)):
            s = s - s / period + arr[i]
            out.append(s)
        return out

    s_tr, s_pdm, s_mdm = smooth(tr), smooth(plus_dm), smooth(minus_dm)
    dx = []
    for i in range(len(s_tr)):
        if s_tr[i] == 0:
            dx.append(0.0)
            continue
        pdi = (s_pdm[i] / s_tr[i]) * 100
        mdi = (s_mdm[i] / s_tr[i]) * 100
        total = pdi + mdi
        dx.append(0.0 if total == 0 else (abs(pdi - mdi) / total) * 100)
    if len(dx) < period:
        return {"adx": float("nan"), "plusDI": float("nan"), "minusDI": float("nan")}
    adx_val = sum(dx[:period]) / period
    for i in range(period, len(dx)):
        adx_val = (adx_val * (period - 1) + dx[i]) / period
    last = len(s_tr) - 1
    plus_di = (s_pdm[last] / s_tr[last]) * 100 if s_tr[last] > 0 else 0.0
    minus_di = (s_mdm[last] / s_tr[last]) * 100 if s_tr[last] > 0 else 0.0
    return {"adx": adx_val, "plusDI": plus_di, "minusDI": minus_di}


def macd(close: np.ndarray, idx: int) -> dict:
    """Port of swing-scanner.src.js `calcMACD()` — 12/26/9."""
    nan = {"macd": float("nan"), "signal": float("nan"), "hist": float("nan"), "histPrev": float("nan"), "goldenCross": False}
    start = max(0, idx - 26 * 4)
    sl = close[start : idx + 1]
    if len(sl) < 35:
        return nan
    fast = ema(sl, 12)
    slow = ema(sl, 26)
    macd_line = np.array([
        (f - s) if (np.isfinite(f) and np.isfinite(s)) else np.nan
        for f, s in zip(fast, slow)
    ])
    macd_valid = macd_line[np.isfinite(macd_line)]
    if len(macd_valid) < 9:
        return nan
    signal_arr = ema(macd_valid, 9)
    n = min(len(macd_valid), len(signal_arr))
    if n < 2:
        return nan
    last_macd, last_signal = macd_valid[n - 1], signal_arr[n - 1]
    prev_macd, prev_signal = macd_valid[n - 2], signal_arr[n - 2]
    return {
        "macd": last_macd,
        "signal": last_signal,
        "hist": last_macd - last_signal,
        "histPrev": prev_macd - prev_signal,
        "goldenCross": bool(prev_macd < prev_signal and last_macd >= last_signal),
    }


def obv(close: np.ndarray, vol: np.ndarray, idx: int) -> dict:
    """Port of swing-scanner.src.js `calcOBV()` — slope of last-5 vs prior-5 OBV average."""
    n = min(len(close), len(vol), idx + 1)
    if n < 20:
        return {"obvTrend": 0}
    running = 0.0
    obv_arr = []
    for i in range(n):
        if i > 0:
            d = float(close[i]) - float(close[i - 1])
            if d > 0:
                running += float(vol[i]) if np.isfinite(vol[i]) else 0.0
            elif d < 0:
                running -= float(vol[i]) if np.isfinite(vol[i]) else 0.0
        obv_arr.append(running)
    recent = sum(obv_arr[-5:]) / 5
    prior = sum(obv_arr[-10:-5]) / 5
    if prior == 0:
        return {"obvTrend": 0}
    slope = (recent - prior) / abs(prior)
    if slope > 0.005:
        return {"obvTrend": 1}
    if slope < -0.005:
        return {"obvTrend": -1}
    return {"obvTrend": 0}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_indicators.py -v`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/indicators.py backtest/tests/__init__.py backtest/tests/test_indicators.py
git commit -m "feat(backtest): port RSI/ADX/MACD/OBV indicators from production JS"
```

---

### Task 2: Historical KRX supply-demand fetcher

**Files:**
- Create: `backtest/krx_supply_history.py`
- Test: `backtest/tests/test_krx_supply_history.py`

**Interfaces:**
- Consumes: none (standalone HTTP + disk cache)
- Produces: `fetch_supply_for_date(trd_dd: str, *, cache_dir: Path = Path("backtest/cache/krx_supply")) -> dict[code -> {"frgn": float, "org": float}]` — consumed by Task 5/7.

**Reference (production, `src/swing-scanner.src.js:640-665`):** `POST https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd` with body `bld=dbms/MDC/STAT/standard/MDCSTAT02023&mktId=ALL&trdDd={date}&share=1&money=1&csvxls_isNo=false`; response rows have `ISU_SRT_CD`, `FRGN_NETBUY_TRDVAL`, `ORG_NETBUY_TRDVAL` (comma-formatted numbers).

- [ ] **Step 1: Write the failing test**

```python
# backtest/tests/test_krx_supply_history.py
import json
from pathlib import Path
from unittest.mock import patch

from backtest.krx_supply_history import fetch_supply_for_date


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def test_fetch_supply_for_date_parses_and_caches(tmp_path):
    payload = {
        "output": [
            {"ISU_SRT_CD": "005930", "FRGN_NETBUY_TRDVAL": "1,234,567", "ORG_NETBUY_TRDVAL": "-500,000"},
            {"ISU_SRT_CD": "000660", "FRGN_NETBUY_TRDVAL": "0", "ORG_NETBUY_TRDVAL": "600,000,000"},
        ]
    }
    cache_dir = tmp_path / "krx_supply"
    with patch("backtest.krx_supply_history.requests.post", return_value=_FakeResp(payload)) as mock_post:
        result = fetch_supply_for_date("20240105", cache_dir=cache_dir)
        assert result["005930"] == {"frgn": 1234567.0, "org": -500000.0}
        assert result["000660"] == {"frgn": 0.0, "org": 600000000.0}
        assert mock_post.call_count == 1

    # second call must hit the cache, not the network again
    with patch("backtest.krx_supply_history.requests.post", side_effect=AssertionError("should not be called")):
        cached = fetch_supply_for_date("20240105", cache_dir=cache_dir)
        assert cached["005930"]["frgn"] == 1234567.0

    assert (cache_dir / "20240105.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backtest/tests/test_krx_supply_history.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.krx_supply_history'`

- [ ] **Step 3: Implement**

```python
# backtest/krx_supply_history.py
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict

import requests

_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://data.krx.co.kr",
    "Referer": "https://data.krx.co.kr/",
    "User-Agent": "Mozilla/5.0",
}


def _to_num(v) -> float:
    try:
        return float(str(v or "0").replace(",", ""))
    except ValueError:
        return 0.0


def fetch_supply_for_date(
    trd_dd: str,
    *,
    cache_dir: Path = Path("backtest/cache/krx_supply"),
    min_sleep_s: float = 0.2,
) -> Dict[str, Dict[str, float]]:
    """Foreign/institutional net-buy value per stock code for one KRX trading day (market-wide, 1 call)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{trd_dd}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    body = f"bld=dbms/MDC/STAT/standard/MDCSTAT02023&mktId=ALL&trdDd={trd_dd}&share=1&money=1&csvxls_isNo=false"
    resp = requests.post(_URL, headers=_HEADERS, data=body, timeout=20)
    resp.raise_for_status()
    rows = (resp.json() or {}).get("output") or []

    result: Dict[str, Dict[str, float]] = {}
    for row in rows:
        code = str(row.get("ISU_SRT_CD") or "").strip()
        if not code:
            continue
        result[code] = {
            "frgn": _to_num(row.get("FRGN_NETBUY_TRDVAL")),
            "org": _to_num(row.get("ORG_NETBUY_TRDVAL")),
        }

    cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    if min_sleep_s > 0:
        time.sleep(min_sleep_s)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backtest/tests/test_krx_supply_history.py -v`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/krx_supply_history.py backtest/tests/test_krx_supply_history.py
git commit -m "feat(backtest): historical KRX foreign/institutional net-buy fetcher"
```

---

### Task 3: Historical DART disclosure fetcher

**Files:**
- Create: `backtest/dart_history.py`
- Test: `backtest/tests/test_dart_history.py`

**Interfaces:**
- Produces: `fetch_disclosures_for_date(trd_dd: str, *, cache_dir: Path = Path("backtest/cache/dart")) -> dict[code -> list[str]]` — consumed by Task 5/7.

**Reference (production, `src/swing-scanner.src.js:694-712`):** `GET https://opendart.fss.or.kr/api/list.json?crtfc_key={key}&bgn_de={date}&end_de={date}&page_no=1&page_count=100`; response `list[]` has `stock_code`, `report_nm`. Negative-keyword hard filter (`소송|횡령|배임|감사의견|불성실|조회`) and positive-keyword scoring (`계약체결|특허|인허가|수주|투자유치|증자`) are applied later in Task 5 — this fetcher only returns the raw report-name list per code.

- [ ] **Step 1: Write the failing test**

```python
# backtest/tests/test_dart_history.py
from unittest.mock import patch

from backtest.dart_history import fetch_disclosures_for_date


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def test_fetch_disclosures_groups_by_code_and_caches(tmp_path):
    payload = {
        "list": [
            {"stock_code": "005930", "report_nm": "단일판매 공급계약체결"},
            {"stock_code": "005930", "report_nm": "특허권취득"},
            {"stock_code": "000660", "report_nm": "감사보고서제출"},
        ]
    }
    cache_dir = tmp_path / "dart"
    with patch("backtest.dart_history.requests.get", return_value=_FakeResp(payload)) as mock_get:
        result = fetch_disclosures_for_date("20240105", api_key="dummy", cache_dir=cache_dir)
        assert result["005930"] == ["단일판매 공급계약체결", "특허권취득"]
        assert result["000660"] == ["감사보고서제출"]
        assert mock_get.call_count == 1

    with patch("backtest.dart_history.requests.get", side_effect=AssertionError("no network")):
        cached = fetch_disclosures_for_date("20240105", api_key="dummy", cache_dir=cache_dir)
        assert cached["005930"] == ["단일판매 공급계약체결", "특허권취득"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backtest/tests/test_dart_history.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.dart_history'`

- [ ] **Step 3: Implement**

```python
# backtest/dart_history.py
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List

import requests

_URL = "https://opendart.fss.or.kr/api/list.json"


def fetch_disclosures_for_date(
    trd_dd: str,
    *,
    api_key: str,
    cache_dir: Path = Path("backtest/cache/dart"),
    min_sleep_s: float = 0.2,
) -> Dict[str, List[str]]:
    """Disclosure report names per stock code for one calendar day (market-wide, 1 call)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{trd_dd}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    params = {"crtfc_key": api_key, "bgn_de": trd_dd, "end_de": trd_dd, "page_no": 1, "page_count": 100}
    resp = requests.get(_URL, params=params, timeout=20)
    resp.raise_for_status()
    items = (resp.json() or {}).get("list") or []

    result: Dict[str, List[str]] = {}
    for item in items:
        code = str(item.get("stock_code") or "").strip()
        if not code:
            continue
        result.setdefault(code, []).append(str(item.get("report_nm") or "")[:40])

    cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    if min_sleep_s > 0:
        time.sleep(min_sleep_s)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backtest/tests/test_dart_history.py -v`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/dart_history.py backtest/tests/test_dart_history.py
git commit -m "feat(backtest): historical DART disclosure fetcher"
```

---

### Task 4: Historical market regime (secondary comparison only)

**Files:**
- Create: `backtest/market_regime_history.py`
- Test: `backtest/tests/test_market_regime_history.py`

**Interfaces:**
- Consumes: `backtest.yahoo_cache.fetch_yahoo_chart`, `backtest.yahoo_cache.chart_to_ohlcv_daily`, `backtest.indicators.sma`
- Produces: `compute_regime_series(start: str, end: str) -> pd.DataFrame` indexed by date with column `regime_level` (0/1/2) — consumed ONLY by Task 9 (the what-if comparison), never by Task 5/7's primary path (per Global Constraints).

**Reference (production, `src/swing-scanner.src.js:400-530`):** `regimeLevel = max(ksLevel, kqLevel)`; each of KOSPI/KOSDAQ: level=2 if SMA20<SMA60, else level=1 if SMA5<SMA20; plus macro adjustment (+1 if NASDAQ 1-day return < -1% OR S&P futures < -0.7%; +1 if VIX>25), capped at 2. We simplify the gap-detection sub-logic (today-vs-yesterday gap source switching) out of scope for this historical reconstruction — it only nudges level 1→2 on gap-down days and the SMA-based level already dominates; note this simplification in the report.

- [ ] **Step 1: Write the failing test**

```python
# backtest/tests/test_market_regime_history.py
import pandas as pd

from backtest.market_regime_history import _regime_level_for_index
from backtest.indicators import sma
import numpy as np


def test_regime_level_bear_when_sma20_below_sma60():
    close = np.array([100.0 - i * 0.3 for i in range(70)])  # steady downtrend
    sma20 = sma(close, 20)
    sma60 = sma(close, 60)
    sma5 = sma(close, 5)
    level = _regime_level_for_index(69, sma5, sma20, sma60)
    assert level == 2


def test_regime_level_bull_when_all_aligned_up():
    close = np.array([100.0 + i * 0.3 for i in range(70)])  # steady uptrend
    sma20 = sma(close, 20)
    sma60 = sma(close, 60)
    sma5 = sma(close, 5)
    level = _regime_level_for_index(69, sma5, sma20, sma60)
    assert level == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backtest/tests/test_market_regime_history.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.market_regime_history'`

- [ ] **Step 3: Implement**

```python
# backtest/market_regime_history.py
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import sma
from .yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart

NASDAQ_DOWN_THRESH = -0.01
SP500_DOWN_THRESH = -0.007
VIX_HIGH_THRESH = 25.0


def _regime_level_for_index(i: int, sma5: np.ndarray, sma20: np.ndarray, sma60: np.ndarray) -> int:
    if not (np.isfinite(sma20[i]) and np.isfinite(sma60[i])):
        return 0
    if sma20[i] <= sma60[i]:
        return 2
    if np.isfinite(sma5[i]) and sma5[i] <= sma20[i]:
        return 1
    return 0


def _single_index_regime(ticker: str, start: str, end: str) -> pd.Series:
    data = fetch_yahoo_chart(YahooFetchSpec(ticker=ticker, range="5y", interval="1d"))
    df, _ = chart_to_ohlcv_daily(data)
    close = df["close"].to_numpy(dtype="float64")
    sma5, sma20, sma60 = sma(close, 5), sma(close, 20), sma(close, 60)
    levels = [_regime_level_for_index(i, sma5, sma20, sma60) for i in range(len(close))]
    s = pd.Series(levels, index=df["timestamp_utc"].dt.date)
    mask = (s.index >= pd.to_datetime(start).date()) & (s.index <= pd.to_datetime(end).date())
    return s[mask]


def compute_regime_series(start: str, end: str) -> pd.DataFrame:
    """Daily regime_level (0=bull,1=neutral,2=bear) for KOSPI∪KOSDAQ + NASDAQ/VIX/ES=F macro overlay."""
    ks = _single_index_regime("%5EKS11", start, end)
    kq = _single_index_regime("%5EKQ11", start, end)
    base = pd.concat([ks, kq], axis=1).max(axis=1).fillna(0).astype(int)

    nasdaq_data = fetch_yahoo_chart(YahooFetchSpec(ticker="%5EIXIC", range="5y", interval="1d"))
    nasdaq_df, _ = chart_to_ohlcv_daily(nasdaq_data)
    nasdaq_ret = nasdaq_df["close"].pct_change()
    nasdaq_ret.index = nasdaq_df["timestamp_utc"].dt.date

    vix_data = fetch_yahoo_chart(YahooFetchSpec(ticker="%5EVIX", range="5y", interval="1d"))
    vix_df, _ = chart_to_ohlcv_daily(vix_data)
    vix_level = vix_df.set_index(vix_df["timestamp_utc"].dt.date)["close"]

    macro_adj = pd.Series(0, index=base.index)
    for d in base.index:
        adj = 0
        if d in nasdaq_ret.index and pd.notna(nasdaq_ret.get(d)) and nasdaq_ret[d] < NASDAQ_DOWN_THRESH:
            adj += 1
        if d in vix_level.index and vix_level[d] > VIX_HIGH_THRESH:
            adj += 1
        macro_adj[d] = adj

    regime_level = (base + macro_adj).clip(upper=2)
    return pd.DataFrame({"regime_level": regime_level})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backtest/tests/test_market_regime_history.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/market_regime_history.py backtest/tests/test_market_regime_history.py
git commit -m "feat(backtest): historical market regime reconstruction for what-if comparison"
```

---

### Task 5: Faithful swing signal engine (patterns A/B/C/D + scoring + grade + target/stop/RR)

This is the fidelity-critical task — every other task's results are only as trustworthy as this one.

**Files:**
- Create: `backtest/swing_signal_engine.py`
- Test: `backtest/tests/test_swing_signal_engine.py`

**Interfaces:**
- Consumes: `backtest.indicators.{sma,atr,rsi14,adx,macd,obv}`
- Produces: `evaluate_candidate(df: pd.DataFrame, idx: int, *, supply: dict, dart_items: list[str], day_of_week: int) -> Optional[SwingCandidate]` where `SwingCandidate` is a dataclass with fields `pattern_type: str, score: int, rank_score: int, grade: str, entry: float, target: float, stop: float, hold_days: int`. Consumed by Task 7.

- [ ] **Step 1: Write the failing tests**

```python
# backtest/tests/test_swing_signal_engine.py
import numpy as np
import pandas as pd

from backtest.swing_signal_engine import evaluate_candidate, MIN_SCORE_FINAL, SCORE_STRONG_FINAL


def _flat_df(n=300, base=10000.0, vol=2_000_000.0):
    close = np.full(n, base)
    df = pd.DataFrame(
        {
            "open": close, "high": close * 1.001, "low": close * 0.999,
            "close": close, "volume": np.full(n, vol),
        }
    )
    return df


def test_no_pattern_returns_none():
    df = _flat_df()
    result = evaluate_candidate(df, len(df) - 1, supply={}, dart_items=[], day_of_week=2)
    assert result is None


def test_pattern_d_box_breakout_produces_candidate():
    n = 300
    df = _flat_df(n=n, base=10000.0)
    # box ceiling for last PD_DAYS(25) days stays at 10000, then breaks out hard on the last bar
    df.loc[n - 1, "close"] = 11000.0
    df.loc[n - 1, "open"] = 10050.0
    df.loc[n - 1, "high"] = 11050.0
    df.loc[n - 1, "low"] = 10000.0
    df.loc[n - 1, "volume"] = 2_000_000.0 * 3.0  # PD_VOL_MULT=2.5 -> use 3x
    # daily_uptrend requires sma20 > sma60 at breakout bar: ramp last 60 bars up slightly
    for i in range(n - 60, n - 1):
        df.loc[i, "close"] = 10000.0 + (i - (n - 60)) * 2.0
        df.loc[i, "open"] = df.loc[i, "close"]
        df.loc[i, "high"] = df.loc[i, "close"] * 1.001
        df.loc[i, "low"] = df.loc[i, "close"] * 0.999

    result = evaluate_candidate(df, n - 1, supply={}, dart_items=[], day_of_week=2)
    assert result is not None
    assert result.pattern_type == "D박스"
    assert result.score >= MIN_SCORE_FINAL
    assert result.stop < result.entry < result.target


def test_score_below_min_returns_none():
    # A pattern D breakout too weak on volume (only 2.6x, right at threshold but no other bonuses)
    # combined with RSI < 40 hard filter should reject via F-filter
    n = 300
    df = _flat_df(n=n, base=10000.0)
    for i in range(n - 30, n):
        df.loc[i, "close"] = 10000.0 - (i - (n - 30)) * 50.0  # sharp decline -> RSI < 40
        df.loc[i, "open"] = df.loc[i, "close"]
        df.loc[i, "high"] = df.loc[i, "close"]
        df.loc[i, "low"] = df.loc[i, "close"]
    result = evaluate_candidate(df, n - 1, supply={}, dart_items=[], day_of_week=2)
    assert result is None


def test_negative_dart_keyword_hard_blocks():
    n = 300
    df = _flat_df(n=n, base=10000.0)
    df.loc[n - 1, "close"] = 11000.0
    df.loc[n - 1, "high"] = 11050.0
    df.loc[n - 1, "volume"] = 2_000_000.0 * 3.0
    for i in range(n - 60, n - 1):
        df.loc[i, "close"] = 10000.0 + (i - (n - 60)) * 2.0
        df.loc[i, "high"] = df.loc[i, "close"] * 1.001
        df.loc[i, "low"] = df.loc[i, "close"] * 0.999
    result = evaluate_candidate(
        df, n - 1, supply={}, dart_items=["소송 제기 관련 조회공시"], day_of_week=2
    )
    assert result is None


def test_negative_supply_hard_blocks():
    n = 300
    df = _flat_df(n=n, base=10000.0)
    df.loc[n - 1, "close"] = 11000.0
    df.loc[n - 1, "high"] = 11050.0
    df.loc[n - 1, "volume"] = 2_000_000.0 * 3.0
    for i in range(n - 60, n - 1):
        df.loc[i, "close"] = 10000.0 + (i - (n - 60)) * 2.0
        df.loc[i, "high"] = df.loc[i, "close"] * 1.001
        df.loc[i, "low"] = df.loc[i, "close"] * 0.999
    result = evaluate_candidate(
        df, n - 1, supply={"frgn": -2_000_000_000, "org": 0}, dart_items=[], day_of_week=2
    )
    assert result is None


def test_grade_strong_when_score_at_least_110():
    n = 300
    df = _flat_df(n=n, base=10000.0)
    df.loc[n - 1, "close"] = 12000.0
    df.loc[n - 1, "high"] = 12050.0
    df.loc[n - 1, "open"] = 10100.0
    df.loc[n - 1, "low"] = 10000.0
    df.loc[n - 1, "volume"] = 2_000_000.0 * 9.0  # >=8x RVOL bonus
    for i in range(n - 60, n - 1):
        df.loc[i, "close"] = 10000.0 + (i - (n - 60)) * 2.0
        df.loc[i, "high"] = df.loc[i, "close"] * 1.001
        df.loc[i, "low"] = df.loc[i, "close"] * 0.999
    result = evaluate_candidate(
        df, n - 1, supply={"frgn": 600_000_000, "org": 600_000_000}, dart_items=[], day_of_week=2
    )
    assert result is not None
    if result.score >= SCORE_STRONG_FINAL:
        assert result.grade == "강매"
        assert result.hold_days == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_swing_signal_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.swing_signal_engine'`

- [ ] **Step 3: Implement**

```python
# backtest/swing_signal_engine.py
"""
Faithful Python port of the swing-scanner pattern/scoring/grade/target/stop logic
in src/swing-scanner.src.js (as of 2026-07-25). Every constant below is copied
verbatim from that file; line numbers refer to that source at port time.

NOT MODELED: Toss real-time order-book confirmation (src/swing-scanner.src.js:1562-1700+) —
no historical tick/orderbook data exists to replay this gate. See report §Limitations.

NOT APPLIED: market-regime entry blocking. getMarketRegime()'s blocking logic
(`if regimeLevel>=2 and grade!='강매': return`) exists in an older commit
(see docs/03-analysis/trailing-stop-regime-fix.analysis.md, 2026-05-02) but is
absent from the current production file — the function is computed but never
called. This engine matches CURRENT production behavior (regime-blind).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .indicators import adx as calc_adx
from .indicators import atr as calc_atr
from .indicators import macd as calc_macd
from .indicators import obv as calc_obv
from .indicators import rsi14 as calc_rsi14
from .indicators import sma

MIN_PRICE = 1000.0
MIN_TURNOVER_ALGO = 5_000_000_000.0
MIN_SCORE_FINAL = 60
SCORE_STRONG_FINAL = 110
MIN_RR_RATIO_FINAL = 1.5

PA_VOL_MULT, PA_PRICE_MOVE, PA_DAYS_MIN, PA_DAYS_MAX = 3.0, 0.05, 1, 10
PA_PULLBACK_MAX, PA_PULLBACK_MIN = 0.15, 0.03
PB_CORR_MIN, PB_CORR_MAX, PB_LEVEL_PROX = 0.20, 0.50, 0.08
PC_VOL_MULT, PC_PRICE_MIN, PC_STR_MIN = 5.0, 0.05, 0.50
PD_VOL_MULT, PD_BREAK_MIN, PD_DAYS = 2.5, 0.02, 25

NEGATIVE_DART_RE = "소송|횡령|배임|감사의견|불성실|조회"
POSITIVE_DART_RE = "계약체결|특허|인허가|수주|투자유치|증자"

import re as _re


@dataclass(frozen=True)
class SwingCandidate:
    pattern_type: str
    score: int
    rank_score: int
    grade: str
    entry: float
    target: float
    stop: float
    hold_days: int
    signals: List[str]


def _hold_days(grade: str, pattern_type: str) -> int:
    if grade == "강매":
        return 5
    if grade == "급등":
        return 2
    return {"C촉매": 2, "A눌림목": 3, "B지지선": 5, "D박스": 4}.get(pattern_type, 3)


def evaluate_candidate(
    df: pd.DataFrame,
    idx: int,
    *,
    supply: Optional[Dict[str, float]] = None,
    dart_items: Optional[List[str]] = None,
    day_of_week: int,
) -> Optional[SwingCandidate]:
    """
    df must have columns open/high/low/close/volume, sorted ascending by date.
    idx is the "as of close" evaluation day. day_of_week: Mon=1 .. Sun=0 (JS getUTCDay convention).
    """
    supply = supply or {}
    dart_items = dart_items or []

    close = df["close"].to_numpy(dtype="float64")
    high = df["high"].to_numpy(dtype="float64")
    low = df["low"].to_numpy(dtype="float64")
    openp = df["open"].to_numpy(dtype="float64")
    vol = df["volume"].to_numpy(dtype="float64")

    if idx < 70 or idx >= len(close):
        return None

    current_price = float(close[idx])
    prev_close = float(close[idx - 1]) if idx >= 1 else 0.0
    if current_price < MIN_PRICE:
        return None
    daily_change = (current_price / prev_close - 1.0) if prev_close > 0 else 0.0

    sma20 = sma(close, 20)
    sma60 = sma(close, 60)
    vol_window = vol[max(0, idx - 20) : idx]
    vol20_avg = float(vol_window.sum() / max(1, min(20, idx))) if len(vol_window) else 0.0
    rvol = (vol[idx] / vol20_avg) if vol20_avg > 0 else 0.0
    rsi14_val = calc_rsi14(close, idx)
    adx_result = calc_adx(high, low, close, idx, 14)
    high252 = float(np.max(high[max(0, idx - 252) : idx + 1]))
    day_range = high[idx] - low[idx]
    intraday_strength = ((close[idx] - openp[idx]) / day_range) if day_range > 0 else 0.0
    macd_result = calc_macd(close, idx)
    obv_result = calc_obv(close, vol, idx)

    # ---- F: base filters ----
    if current_price * (vol[idx] if np.isfinite(vol[idx]) else 0.0) < MIN_TURNOVER_ALGO:
        return None
    if rvol < 1.0:
        return None
    if np.isfinite(rsi14_val) and rsi14_val < 40:
        return None
    if dart_items and _re.search(NEGATIVE_DART_RE, " ".join(dart_items)):
        return None
    if supply.get("frgn", 0) < -1_000_000_000 or supply.get("org", 0) < -1_000_000_000:
        return None

    # ---- P: pattern pre-calcs ----
    window_start = max(0, idx - 15)
    event_idx = window_start + int(np.argmax(vol[window_start : idx + 1]))
    event_vol_mult = (vol[event_idx] / vol20_avg) if vol20_avg > 0 else 0.0
    event_days_ago = idx - event_idx
    event_day_change = (
        (close[event_idx] / close[event_idx - 1] - 1.0) if event_idx > 0 and close[event_idx - 1] > 0 else 0.0
    )
    event_high_since = float(np.max(high[event_idx : idx + 1])) if event_idx <= idx else current_price
    pullback_from_event = (current_price / event_high_since - 1.0) if event_high_since > 0 else 0.0

    high60 = float(np.max(high[max(0, idx - 60) : idx + 1]))
    corr_pct60 = (current_price / high60 - 1.0) if high60 > 0 else 0.0

    past_slice = close[max(0, idx - 50) : max(1, idx - 20)]
    past_avg_price = float(past_slice.mean()) if len(past_slice) else 0.0
    prox_to_past = abs(current_price / past_avg_price - 1.0) if past_avg_price > 0 else 1.0

    box25_high = float(np.max(high[max(0, idx - PD_DAYS) : idx])) if idx > 0 else current_price

    is_a = (
        event_vol_mult >= PA_VOL_MULT
        and event_day_change >= PA_PRICE_MOVE
        and PA_DAYS_MIN <= event_days_ago <= PA_DAYS_MAX
        and -PA_PULLBACK_MAX <= pullback_from_event <= -PA_PULLBACK_MIN
        and rvol >= 1.2
        and daily_change >= -0.03
    )
    is_b = (
        -PB_CORR_MAX <= corr_pct60 <= -PB_CORR_MIN
        and prox_to_past <= PB_LEVEL_PROX
        and daily_change >= 0.0
        and rvol >= 1.5
        and np.isfinite(rsi14_val) and 40 <= rsi14_val <= 72
    )
    is_c = (
        rvol >= PC_VOL_MULT
        and daily_change >= PC_PRICE_MIN
        and intraday_strength >= PC_STR_MIN
        and np.isfinite(rsi14_val) and rsi14_val <= 82
    )
    is_d = current_price > box25_high and rvol >= PD_VOL_MULT and daily_change >= PD_BREAK_MIN and sma20[idx] > sma60[idx]

    if not (is_a or is_b or is_c or is_d):
        return None

    # ---- S: scoring ----
    score = 0
    signals: List[str] = []
    if is_c:
        score += 60
        signals.append("촉매이벤트")
    if is_a:
        score += 50
        signals.append("급등후눌림목")
    if is_b:
        score += 45
        signals.append("지지선반등")
    if is_d:
        score += 40
        signals.append("박스권돌파")
    if is_a and is_b:
        score += 15
        signals.append("복합A+B")
    if is_c and is_d:
        score += 10
        signals.append("복합C+D")

    if rvol >= 8.0:
        score += 25
        signals.append("거래량8x+")
    elif rvol >= 5.0:
        score += 18
        signals.append("거래량5x")
    elif rvol >= 3.0:
        score += 12
        signals.append("거래량3x")
    elif rvol >= 2.0:
        score += 6
        signals.append("거래량2x")

    if obv_result["obvTrend"] == 1:
        score += 20
        signals.append("OBV수급↑")
    elif obv_result["obvTrend"] == -1:
        score -= 8

    if macd_result["goldenCross"]:
        score += 15
        signals.append("MACD골든크로스")
    elif np.isfinite(macd_result["hist"]) and macd_result["hist"] > 0:
        if np.isfinite(macd_result["histPrev"]) and macd_result["hist"] > macd_result["histPrev"]:
            score += 10
            signals.append("MACD↑")
    elif (
        np.isfinite(macd_result["hist"]) and np.isfinite(macd_result["histPrev"])
        and macd_result["hist"] < 0 and macd_result["histPrev"] < 0 and not is_c
    ):
        return None

    if sma20[idx] > sma60[idx]:
        score += 15
        signals.append("일봉정배열")
    if intraday_strength >= 0.7:
        score += 12
        signals.append("장마감강세")
    elif intraday_strength >= 0.5:
        score += 6
        signals.append("장마감양호")

    frgn, org = supply.get("frgn", 0), supply.get("org", 0)
    if frgn > 500_000_000 and org > 500_000_000:
        score += 20
        signals.append("외국인+기관동반")
    elif frgn > 500_000_000:
        score += 12
        signals.append("외국인순매수")
    elif org > 500_000_000:
        score += 8
        signals.append("기관순매수")

    if dart_items:
        if _re.search(POSITIVE_DART_RE, " ".join(dart_items)):
            score += 20
            signals.append("긍정공시")
        else:
            score += 5
            signals.append("당일공시")

    if np.isfinite(rsi14_val) and 50 <= rsi14_val <= 70:
        score += 8
        signals.append("RSI골든존")
    if np.isfinite(adx_result["adx"]) and adx_result["adx"] >= 20 and adx_result["plusDI"] > adx_result["minusDI"]:
        score += 10
        signals.append("ADX추세↑")
    if current_price >= high252:
        score += 25
        signals.append("52주신고가")
    elif high252 > 0 and current_price / high252 >= 0.95:
        score += 10
        signals.append("신고가근접")

    if score < MIN_SCORE_FINAL:
        return None

    # ---- G2: grade ----
    is_strong = score >= SCORE_STRONG_FINAL
    is_surge = is_c and rvol >= 8.0 and daily_change >= 0.08
    is_short_trade = (not is_strong) and (not is_surge) and is_c and rvol >= 5.0
    grade = "강매" if is_strong else "급등" if is_surge else "매도차익" if is_short_trade else "매수"

    # ---- T: target/stop (priority: strong > C > A > B > D) ----
    atr_abs = calc_atr(high, low, close, 14)[idx - 1] if idx >= 1 else float("nan")
    # calcAtrAbs in JS excludes the current bar (mean(high-low) over trailing window ending idx-1);
    # backtest/indicators.atr() is a rolling mean of true range INCLUDING the bar at each position,
    # so we deliberately read index idx-1 to get the same "as of yesterday's close of window" value.
    if not np.isfinite(atr_abs) or atr_abs <= 0:
        atr_abs = float(np.nanmean(high[max(0, idx - 14) : idx] - low[max(0, idx - 14) : idx]))
    atr_pct = atr_abs / current_price if current_price > 0 else 0.0

    if is_strong:
        target_pct, stop_pct = max(0.10, atr_pct * 1.9), max(0.04, atr_pct * 1.0)
    elif is_c:
        target_pct, stop_pct = max(0.10, atr_pct * 1.8), max(0.04, atr_pct * 0.9)
    elif is_a:
        target_pct = max(abs(pullback_from_event) * 1.3 + 0.03, atr_pct * 1.6, 0.08)
        stop_pct = max(0.04, atr_pct * 0.9)
    elif is_b:
        target_pct = max(abs(corr_pct60) * 0.45, 0.10, atr_pct * 1.5)
        stop_pct = max(0.05, atr_pct * 1.0)
    else:
        target_pct, stop_pct = max(0.10, atr_pct * 1.5), max(0.04, atr_pct * 0.8)

    target_pct = min(target_pct, 0.30)
    stop_pct = min(stop_pct, 0.08)
    target = current_price * (1 + target_pct)
    stop = current_price * (1 - stop_pct)
    rr = (target - current_price) / max(current_price - stop, 1.0)
    if rr < MIN_RR_RATIO_FINAL:
        return None

    pattern_type = "C촉매" if is_c else "A눌림목" if is_a else "B지지선" if is_b else "D박스"
    dow_adj = 3 if day_of_week == 4 else 2 if day_of_week == 3 else -5 if day_of_week == 5 else 0
    rank_score = score + dow_adj

    return SwingCandidate(
        pattern_type=pattern_type,
        score=score,
        rank_score=rank_score,
        grade=grade,
        entry=current_price,
        target=target,
        stop=stop,
        hold_days=_hold_days(grade, pattern_type),
        signals=signals,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_swing_signal_engine.py -v`
Expected: `6 passed`. If any pattern-construction test fails to trigger the intended pattern, print `result` (or the intermediate `is_a/is_b/is_c/is_d` — temporarily add a debug print) and adjust the synthetic OHLCV fixture's numbers (not the engine code) until the intended pattern fires; the engine's formulas must stay byte-faithful to the JS source cited above.

- [ ] **Step 5: Commit**

```bash
git add backtest/swing_signal_engine.py backtest/tests/test_swing_signal_engine.py
git commit -m "feat(backtest): faithful port of production pattern/scoring/grade/target/stop engine"
```

---

### Task 6: Day-by-day exit simulator

**Files:**
- Create: `backtest/simulate_exits.py`
- Test: `backtest/tests/test_simulate_exits.py`

**Interfaces:**
- Consumes: nothing beyond a plain OHLC DataFrame
- Produces: `simulate_exit(df: pd.DataFrame, entry_idx: int, *, entry: float, stop: float, target: float, hold_days: int) -> dict{exit_idx,exit_price,result,days_held}` — consumed by Task 7.

- [ ] **Step 1: Write the failing tests**

```python
# backtest/tests/test_simulate_exits.py
import pandas as pd

from backtest.simulate_exits import simulate_exit


def _df(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_hits_target_first():
    df = _df([
        [100, 101, 99, 100],
        [100, 112, 99, 105],  # high >= target(110)
        [105, 106, 104, 105],
    ])
    r = simulate_exit(df, 1, entry=100.0, stop=90.0, target=110.0, hold_days=5)
    assert r["result"] == "target"
    assert r["exit_price"] == 110.0
    assert r["days_held"] == 0


def test_hits_stop_first():
    df = _df([
        [100, 101, 99, 100],
        [100, 101, 85, 95],  # low <= stop(90)
    ])
    r = simulate_exit(df, 1, entry=100.0, stop=90.0, target=110.0, hold_days=5)
    assert r["result"] == "stop"
    assert r["exit_price"] == 90.0


def test_both_hit_same_day_is_conservative_stop():
    df = _df([
        [100, 101, 99, 100],
        [100, 115, 85, 100],  # both target and stop touched same bar
    ])
    r = simulate_exit(df, 1, entry=100.0, stop=90.0, target=110.0, hold_days=5)
    assert r["result"] == "stop"
    assert r["exit_price"] == 90.0


def test_timeout_exits_at_close_of_last_holding_day():
    df = _df([
        [100, 101, 99, 100],
        [100, 105, 99, 103],
        [103, 106, 102, 104],
    ])
    r = simulate_exit(df, 1, entry=100.0, stop=50.0, target=200.0, hold_days=1)
    assert r["result"] == "timeout"
    assert r["exit_price"] == 104.0  # close of entry_idx+hold_days
    assert r["days_held"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_simulate_exits.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.simulate_exits'`

- [ ] **Step 3: Implement**

```python
# backtest/simulate_exits.py
from __future__ import annotations

from typing import Any, Dict

import pandas as pd


def simulate_exit(
    df: pd.DataFrame,
    entry_idx: int,
    *,
    entry: float,
    stop: float,
    target: float,
    hold_days: int,
) -> Dict[str, Any]:
    """Day-by-day forward walk from entry_idx: exits on first target/stop touch, else at hold_days timeout."""
    end = min(len(df) - 1, entry_idx + hold_days)
    for i in range(entry_idx, end + 1):
        hi = float(df.loc[i, "high"])
        lo = float(df.loc[i, "low"])
        hit_target = hi >= target
        hit_stop = lo <= stop
        if hit_target and hit_stop:
            return {"exit_idx": i, "exit_price": stop, "result": "stop", "days_held": i - entry_idx}
        if hit_target:
            return {"exit_idx": i, "exit_price": target, "result": "target", "days_held": i - entry_idx}
        if hit_stop:
            return {"exit_idx": i, "exit_price": stop, "result": "stop", "days_held": i - entry_idx}
    exit_price = float(df.loc[end, "close"])
    return {"exit_idx": end, "exit_price": exit_price, "result": "timeout", "days_held": end - entry_idx}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_simulate_exits.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/simulate_exits.py backtest/tests/test_simulate_exits.py
git commit -m "feat(backtest): day-by-day target/stop/timeout exit simulator"
```

---

### Task 7: Backtest orchestration script (200 tickers, weekly/daily selection caps)

**Files:**
- Create: `backtest/run_swing_v2_backtest.py`
- Test: `backtest/tests/test_run_swing_v2_backtest.py`

**Interfaces:**
- Consumes: `swing_signal_engine.evaluate_candidate`, `simulate_exits.simulate_exit`, `krx_supply_history.fetch_supply_for_date`, `dart_history.fetch_disclosures_for_date`, `yahoo_cache.{fetch_yahoo_chart,chart_to_ohlcv_daily,YahooFetchSpec}`
- Produces: a JSON file `{"stats": {...}, "trades": [...]}` written to the path given by `--out`. Consumed by Task 9.

**Reference for weekly/daily selection caps (`src/swing-scanner.src.js:1520-1554`):** sort all-qualified-today candidates by `rank_score` desc; drop any whose `code` was already recommended this ISO week (Mon-Fri); if this week's cumulative recommendation count is already ≥15, skip the whole day; otherwise re-sort the remaining candidates by `(grade tier desc, rank_score desc)` and take the top 3 as "sent" for that day, adding them to the week's running list.

- [ ] **Step 1: Write the failing test**

This test uses a tiny synthetic 2-ticker universe with monkeypatched fetchers so it never hits the network — it validates the *selection/cap* wiring, not indicator fidelity (that's Task 5's job).

```python
# backtest/tests/test_run_swing_v2_backtest.py
from unittest.mock import patch

import numpy as np
import pandas as pd

from backtest.run_swing_v2_backtest import GRADE_ORDER, apply_daily_selection
from backtest.swing_signal_engine import SwingCandidate


def _cand(code, rank_score, grade="매수"):
    return (code, SwingCandidate(
        pattern_type="D박스", score=rank_score, rank_score=rank_score, grade=grade,
        entry=1000.0, target=1100.0, stop=960.0, hold_days=4, signals=[],
    ))


def test_weekly_cap_stops_new_selections():
    week_state = {"count": 15, "codes": set()}
    todays = [_cand("000001", 90), _cand("000002", 80)]
    selected = apply_daily_selection(todays, week_state, max_per_day=3, max_per_week=15)
    assert selected == []


def test_dedup_same_code_within_week():
    week_state = {"count": 1, "codes": {"000001"}}
    todays = [_cand("000001", 95), _cand("000002", 90)]
    selected = apply_daily_selection(todays, week_state, max_per_day=3, max_per_week=15)
    assert [c for c, _ in selected] == ["000002"]


def test_grade_order_wins_over_rank_score():
    week_state = {"count": 0, "codes": set()}
    todays = [
        _cand("000001", 200, grade="매수"),
        _cand("000002", 60, grade="강매"),
    ]
    selected = apply_daily_selection(todays, week_state, max_per_day=3, max_per_week=15)
    assert [c for c, _ in selected][0] == "000002"  # 강매 outranks 매수 regardless of score


def test_max_per_day_caps_selection():
    week_state = {"count": 0, "codes": set()}
    todays = [_cand(f"{i:06d}", 100 - i) for i in range(5)]
    selected = apply_daily_selection(todays, week_state, max_per_day=3, max_per_week=15)
    assert len(selected) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backtest/tests/test_run_swing_v2_backtest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.run_swing_v2_backtest'`

- [ ] **Step 3: Implement**

```python
# backtest/run_swing_v2_backtest.py
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from .dart_history import fetch_disclosures_for_date
from .indicators import max_drawdown
from .krx_supply_history import fetch_supply_for_date
from .simulate_exits import simulate_exit
from .swing_signal_engine import SwingCandidate, evaluate_candidate
from .yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart

GRADE_ORDER = {"강매": 4, "급등": 3, "매도차익": 2, "매수": 1}
MAX_STOCK_PER_SEND = 3
MAX_WEEKLY_SENDS = 15
DART_API_KEY = "34a9b090d2a7b1ee689a240fef68667d36b389e7"  # matches production (already public in this repo)


def _load_tickers(path: Path) -> List[str]:
    lines = [x.strip() for x in path.read_text(encoding="utf-8").splitlines()]
    return [x for x in lines if x and not x.startswith("#")]


def _code_of(ticker: str) -> str:
    return ticker[:-3] if ticker.endswith(".KS") or ticker.endswith(".KQ") else ticker


def apply_daily_selection(
    todays_candidates: List[Tuple[str, SwingCandidate]],
    week_state: Dict[str, Any],
    *,
    max_per_day: int = MAX_STOCK_PER_SEND,
    max_per_week: int = MAX_WEEKLY_SENDS,
) -> List[Tuple[str, SwingCandidate]]:
    """Mirrors src/swing-scanner.src.js:1520-1554 (weekly cap -> dedup -> grade/rank sort -> top-N/day)."""
    if week_state["count"] >= max_per_week:
        return []
    qualified = [(code, c) for code, c in todays_candidates if code not in week_state["codes"]]
    qualified.sort(key=lambda pair: (GRADE_ORDER.get(pair[1].grade, 0), pair[1].rank_score), reverse=True)
    selected = qualified[:max_per_day]
    for code, _ in selected:
        week_state["codes"].add(code)
        week_state["count"] += 1
    return selected


def _iso_week_key(date: pd.Timestamp) -> Tuple[int, int]:
    iso = date.isocalendar()
    return (int(iso[0]), int(iso[1]))


def backtest_swing_v2(
    tickers: List[str],
    *,
    start: str,
    end: str,
    dart_api_key: str = DART_API_KEY,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    per_ticker: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        data = fetch_yahoo_chart(YahooFetchSpec(ticker=t, range="5y", interval="1d"))
        df, _ = chart_to_ohlcv_daily(data)
        df = df.sort_values("timestamp_utc").reset_index(drop=True)
        per_ticker[t] = df

    start_ts = pd.to_datetime(start, utc=True)
    end_ts = pd.to_datetime(end, utc=True)
    all_days = sorted({d for df in per_ticker.values() for d in df["timestamp_utc"].tolist()})
    all_days = [d for d in all_days if start_ts <= d <= end_ts]

    trades: List[Dict[str, Any]] = []
    week_state: Dict[str, Any] = {"key": None, "count": 0, "codes": set()}

    for day in all_days:
        week_key = _iso_week_key(day)
        if week_key != week_state["key"]:
            week_state = {"key": week_key, "count": 0, "codes": set()}

        trd_dd = day.strftime("%Y%m%d")
        supply_map = fetch_supply_for_date(trd_dd)
        dart_map = fetch_disclosures_for_date(trd_dd, api_key=dart_api_key)

        todays_candidates: List[Tuple[str, SwingCandidate]] = []
        for t, df in per_ticker.items():
            idxs = df.index[df["timestamp_utc"] == day].tolist()
            if not idxs:
                continue
            idx = int(idxs[0])
            if idx + 1 >= len(df):
                continue
            code = _code_of(t)
            cand = evaluate_candidate(
                df, idx,
                supply=supply_map.get(code, {}),
                dart_items=dart_map.get(code, []),
                day_of_week=int(day.isoweekday() % 7),  # Mon=1..Sun=0, matches JS getUTCDay()
            )
            if cand is not None:
                todays_candidates.append((code, cand))

        selected = apply_daily_selection(todays_candidates, week_state)
        code_to_ticker = {_code_of(t): t for t in tickers}
        for code, cand in selected:
            ticker = code_to_ticker[code]
            df = per_ticker[ticker]
            entry_idx = int(df.index[df["timestamp_utc"] == day][0]) + 1
            if entry_idx >= len(df):
                continue
            sim = simulate_exit(
                df, entry_idx,
                entry=cand.entry, stop=cand.stop, target=cand.target, hold_days=cand.hold_days,
            )
            pnl = (float(sim["exit_price"]) - cand.entry) / cand.entry
            trades.append({
                "date": day.isoformat(), "ticker": ticker, "code": code,
                "pattern_type": cand.pattern_type, "grade": cand.grade,
                "score": cand.score, "rank_score": cand.rank_score,
                "entry": cand.entry, "stop": cand.stop, "target": cand.target,
                "exit_price": float(sim["exit_price"]), "result": sim["result"],
                "days_held": sim["days_held"], "pnl": pnl,
            })

    df_trades = pd.DataFrame(trades)
    if df_trades.empty:
        return df_trades, {"reason": "no_trades"}

    df_trades["date_ts"] = pd.to_datetime(df_trades["date"])
    df_trades = df_trades.sort_values(["date_ts", "code"]).reset_index(drop=True)

    equity = [1.0]
    for pnl in df_trades["pnl"].astype(float).tolist():
        equity.append(equity[-1] * (1.0 + pnl))
    equity_arr = np.asarray(equity, dtype="float64")

    stats = {
        "trades": int(len(df_trades)),
        "win_rate": float((df_trades["pnl"] > 0).mean()),
        "avg_pnl": float(df_trades["pnl"].mean()),
        "median_pnl": float(df_trades["pnl"].median()),
        "mdd": float(max_drawdown(equity_arr)),
        "equity_end": float(equity_arr[-1]),
    }
    return df_trades, stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-01-01")
    ap.add_argument("--out", default="backtest_out_swing_v2.json")
    args = ap.parse_args()

    tickers = _load_tickers(Path(args.tickers))
    df_trades, stats = backtest_swing_v2(tickers, start=args.start, end=args.end)

    out = {
        "params": {"start": args.start, "end": args.end, "tickers": len(tickers)},
        "stats": stats,
        "trades": df_trades.to_dict(orient="records") if not df_trades.empty else [],
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_run_swing_v2_backtest.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/run_swing_v2_backtest.py backtest/tests/test_run_swing_v2_backtest.py
git commit -m "feat(backtest): orchestrate full swing v2 backtest with weekly/daily selection caps"
```

---

### Task 8: Run the real backtest (200 tickers × 2024-01-01→2026-01-01)

**Files:** none created — this is an execution-only task.

- [ ] **Step 1: Install/confirm dependencies**

Run: `python -m pip install -r backtest/requirements.txt`
Expected: `Requirement already satisfied` for pandas/numpy/requests (already used elsewhere in this repo)

- [ ] **Step 2: Kick off the backtest run in the background**

Run (background — this will take an estimated 20-40 minutes due to ~500 sequential KRX + DART daily calls with rate-limit sleeps, plus 200 Yahoo chart fetches):

```bash
python -m backtest.run_swing_v2_backtest --tickers backtest/tickers_operating_200.txt --start 2024-01-01 --end 2026-01-01 --out backtest_out_swing_v2.json
```

Expected: eventually prints `wrote backtest_out_swing_v2.json` followed by a JSON stats block with `trades`, `win_rate`, `avg_pnl`, `median_pnl`, `mdd`, `equity_end`.

- [ ] **Step 3: Sanity-check the output**

Run: `python -c "import json; d=json.load(open('backtest_out_swing_v2.json')); print(d['stats']); print('sample trade:', d['trades'][0] if d['trades'] else None)"`
Expected: `trades` count in the hundreds-to-low-thousands range (200 tickers × ~2 years × daily-cap-3/weekly-cap-15 selection); `win_rate` between 0 and 1; no `NaN`/`null` in `avg_pnl`/`mdd`. If `trades` is 0 or `win_rate`/`avg_pnl` are `NaN`, stop and debug Task 5/7 before proceeding — do not analyze a broken run.

- [ ] **Step 4: Commit the raw result for reproducibility**

```bash
git add backtest_out_swing_v2.json
git commit -m "data(backtest): raw swing v2 backtest output, 200 tickers 2024-01-01..2026-01-01"
```

---

### Task 9: Results analysis (overall + per-pattern + per-score-tier + regime what-if)

**Files:**
- Create: `backtest/analyze_swing_v2_results.py`
- Test: `backtest/tests/test_analyze_swing_v2_results.py`

**Interfaces:**
- Consumes: the JSON written by Task 7/8, `backtest.market_regime_history.compute_regime_series` (Task 4)
- Produces: `analyze(trades: list[dict]) -> dict` with keys `overall`, `by_pattern`, `by_score_tier`; `regime_what_if(trades: list[dict], regime_df: pd.DataFrame) -> dict` with keys `as_deployed` (regime-blind, all trades) vs `if_gate_active` (trades filtered to `regime_level < 2 or grade=='강매'` and further `regime_level < 1 or grade != '매도차익'`, matching the *lost* production rule from Task 4's docstring). Both consumed by Task 11 (report) and Task 12 (dashboard).

- [ ] **Step 1: Write the failing test**

```python
# backtest/tests/test_analyze_swing_v2_results.py
import pandas as pd

from backtest.analyze_swing_v2_results import analyze, regime_what_if


def _trades():
    return [
        {"date": "2024-01-02", "pattern_type": "D박스", "score": 65, "pnl": 0.10, "grade": "매수"},
        {"date": "2024-01-03", "pattern_type": "D박스", "score": 65, "pnl": -0.04, "grade": "매수"},
        {"date": "2024-01-04", "pattern_type": "C촉매", "score": 120, "pnl": 0.15, "grade": "강매"},
        {"date": "2024-01-05", "pattern_type": "A눌림목", "score": 95, "pnl": -0.03, "grade": "매도차익"},
    ]


def test_analyze_overall_and_breakdowns():
    result = analyze(_trades())
    assert result["overall"]["trades"] == 4
    assert result["overall"]["win_rate"] == 0.5
    assert result["by_pattern"]["D박스"]["trades"] == 2
    assert result["by_pattern"]["C촉매"]["win_rate"] == 1.0
    assert result["by_score_tier"]["60-89"]["trades"] == 2
    assert result["by_score_tier"]["90-109"]["trades"] == 1
    assert result["by_score_tier"]["110+"]["trades"] == 1


def test_regime_what_if_drops_neutral_sell_profit_grade():
    trades = _trades()
    regime_df = pd.DataFrame(
        {"regime_level": [1, 1, 1, 1]},
        index=[pd.Timestamp(d).date() for d in ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]],
    )
    result = regime_what_if(trades, regime_df)
    assert result["as_deployed"]["trades"] == 4
    # regime_level=1 blocks grade=='매도차익' (the 2024-01-05 trade) per the lost production rule
    assert result["if_gate_active"]["trades"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backtest/tests/test_analyze_swing_v2_results.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.analyze_swing_v2_results'`

- [ ] **Step 3: Implement**

```python
# backtest/analyze_swing_v2_results.py
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

SCORE_TIERS = [("60-89", 60, 89), ("90-109", 90, 109), ("110+", 110, 10_000)]


def _stats_for(rows: List[dict]) -> Dict[str, Any]:
    if not rows:
        return {"trades": 0, "win_rate": 0.0, "avg_pnl": 0.0, "median_pnl": 0.0}
    df = pd.DataFrame(rows)
    return {
        "trades": int(len(df)),
        "win_rate": float((df["pnl"] > 0).mean()),
        "avg_pnl": float(df["pnl"].mean()),
        "median_pnl": float(df["pnl"].median()),
    }


def analyze(trades: List[dict]) -> Dict[str, Any]:
    overall = _stats_for(trades)

    by_pattern: Dict[str, Any] = {}
    for pattern in sorted({t["pattern_type"] for t in trades}):
        by_pattern[pattern] = _stats_for([t for t in trades if t["pattern_type"] == pattern])

    by_score_tier: Dict[str, Any] = {}
    for label, lo, hi in SCORE_TIERS:
        by_score_tier[label] = _stats_for([t for t in trades if lo <= t["score"] <= hi])

    return {"overall": overall, "by_pattern": by_pattern, "by_score_tier": by_score_tier}


def regime_what_if(trades: List[dict], regime_df: pd.DataFrame) -> Dict[str, Any]:
    """Compares as-deployed (regime-blind) results against the lost production rule:
    `if regimeLevel>=2 and grade!='강매': block` and `if regimeLevel>=1 and grade=='매도차익': block`.
    """
    as_deployed = _stats_for(trades)

    kept: List[dict] = []
    for t in trades:
        day = pd.Timestamp(t["date"]).date()
        level = int(regime_df["regime_level"].get(day, 0))
        if level >= 2 and t["grade"] != "강매":
            continue
        if level >= 1 and t["grade"] == "매도차익":
            continue
        kept.append(t)

    return {"as_deployed": as_deployed, "if_gate_active": _stats_for(kept)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_analyze_swing_v2_results.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/analyze_swing_v2_results.py backtest/tests/test_analyze_swing_v2_results.py
git commit -m "feat(backtest): profitability breakdown by pattern/score-tier + regime what-if comparison"
```

---

### Task 10: Run analysis on the real backtest output

**Files:** none created — execution-only task.

- [ ] **Step 1: Compute regime series for the same date range (for the what-if comparison)**

Run:
```bash
python -c "
from backtest.market_regime_history import compute_regime_series
df = compute_regime_series('2024-01-01', '2026-01-01')
df.to_json('backtest_regime_series.json', orient='index')
print(df['regime_level'].value_counts())
"
```
Expected: prints a count of how many days fell into level 0/1/2; writes `backtest_regime_series.json`.

- [ ] **Step 2: Run the full analysis and save it**

Run:
```bash
python -c "
import json
import pandas as pd
from backtest.analyze_swing_v2_results import analyze, regime_what_if

data = json.load(open('backtest_out_swing_v2.json'))
trades = data['trades']

result = analyze(trades)

regime_raw = json.load(open('backtest_regime_series.json'))
regime_df = pd.DataFrame({'regime_level': regime_raw}).rename(index=lambda k: pd.Timestamp(k).date())
result['regime_what_if'] = regime_what_if(trades, regime_df)

json.dump(result, open('backtest_analysis_swing_v2.json', 'w'), ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii=False, indent=2))
"
```
Expected: prints the full nested stats dict; writes `backtest_analysis_swing_v2.json`.

- [ ] **Step 3: Commit**

```bash
git add backtest_regime_series.json backtest_analysis_swing_v2.json
git commit -m "data(backtest): swing v2 profitability analysis results"
```

---

### Task 11: Write the combined markdown report

**Files:**
- Create: `docs/03-analysis/swing-algorithm-profitability-review.analysis.md`

- [ ] **Step 1: Draft the report**

Write `docs/03-analysis/swing-algorithm-profitability-review.analysis.md` with these sections (populate the bracketed placeholders with the actual numbers from `backtest_analysis_swing_v2.json` produced in Task 10 — this is the one place in the plan where exact numbers cannot be pre-written, since they don't exist until Task 10 runs):

```markdown
# Swing Algorithm Profitability Review

**Scope:** `src/swing-scanner.src.js` (production swing-recommendation engine) — code-review + empirical backtest (200 KRX tickers, 2024-01-01 ~ 2026-01-01).

## Executive Summary

| Item | Value |
|---|---|
| Backtest trades | [overall.trades] |
| Win rate | [overall.win_rate as %] |
| Avg PnL / trade | [overall.avg_pnl as %] |
| Median PnL / trade | [overall.median_pnl as %] |
| Max drawdown | [stats.mdd as %] |

## Code Review Findings

### 1. Market-regime bear protection has silently regressed to dead code
`getMarketRegime()` (src/swing-scanner.src.js:403-530) computes a 3-tier KOSPI/KOSDAQ + macro
(NASDAQ/VIX/S&P futures) regime level, but is **never called**. A prior gap-analysis
(`docs/03-analysis/trailing-stop-regime-fix.analysis.md`, 2026-05-02) confirms the blocking
rule `if (regimeLevel >= 2 && grade !== '강매') return;` existed and passed review at that
date. It is absent from the current file. Production has been trading regime-blind since
this regression, despite `store.regimeCache`/log lines still giving the impression the
safety layer is active. **Recommendation: restore the entry-blocking check** (see Task 9's
what-if comparison below for the quantified impact of restoring it).

### 2. Two indicator/pattern implementations are dead code
`calcBB()` (Bollinger Bands) and `detectCupAndHandle()` are fully implemented but never
called from the candidate-generation path. They add maintenance surface with zero effect
on trading decisions.

### 3. Scoring weights are hand-tuned on a 30-stock hindsight sample, never statistically validated
Per `docs/01-plan/features/showmoneyv2.plan.md`, the ~15 scoring bonuses/penalties were
set from reviewing 30 stocks in hindsight ("30종목 복기 기반"), not fit or cross-validated
against a larger out-of-sample dataset. This backtest is the first out-of-sample check
these weights have received.

### 4. The pipeline is fragile under upstream data-format changes
Earlier this session, a Naver API response-normalization regression (missing BOM/Buffer/
string-JSON handling in the newly-unified `lib/naverClient.js`) caused the weekly
performance report to silently show 0 entries for 15 real recommendations. The same
class of failure could silently zero out the *live* scanner's candidate generation without
any error surfacing, given the pattern of `catch(e) { return null }` swallowing seen
throughout this codebase.

### 5. Real-time order-book confirmation (Toss) cannot be backtested
`tossConfirm()` (src/swing-scanner.src.js:1613+) blocks sends when the ask/bid ratio or
buy-execution ratio look unfavorable, using live order-book data with no historical
equivalent. Its effect is unmeasured — it can only reduce trade count (never invents
trades), so the backtest below is an upper bound on trade frequency and a lower bound on
"how bad the worst-executed signals would have been" (Toss's job is specifically to catch
those).

## Empirical Backtest Results

### Overall
[insert overall stats table]

### By pattern type
[insert by_pattern table: A눌림목/B지지선/C촉매/D박스 — trades/win_rate/avg_pnl/median_pnl]

### By score tier
[insert by_score_tier table: 60-89/90-109/110+ — trades/win_rate/avg_pnl/median_pnl]

### Regime what-if: dead code vs. restored
| | As deployed (regime-blind) | If regime gate were restored |
|---|---|---|
| Trades | [regime_what_if.as_deployed.trades] | [regime_what_if.if_gate_active.trades] |
| Win rate | [as_deployed.win_rate] | [if_gate_active.win_rate] |
| Avg PnL | [as_deployed.avg_pnl] | [if_gate_active.avg_pnl] |

## Limitations

- Daily-bar backtest: entries are simulated at next-day open, exits check daily high/low
  against target/stop — this does not capture intraday order fills exactly the way the
  live 09:00-13:00 scanning cadence does (same caveat as `backtest/README.md`).
- Toss real-time confirmation not modeled (see Finding 5) — live win rate is plausibly
  *higher* than backtested win rate to the extent Toss successfully filters bad fills.
- Gap-detection nuance in `getMarketRegime` (today-vs-yesterday gap source switching) is
  simplified to pure SMA-based leveling in the what-if reconstruction (Task 4) — the
  what-if numbers are directionally, not exactly, faithful to the original blocking rule.

## Recommendations (priority order)

1. Restore the regime entry-blocking check (Finding 1) — quantified impact above.
2. Remove or genuinely wire up `calcBB`/`detectCupAndHandle` (Finding 2) — pick one.
3. Re-tune scoring weights using this backtest's per-signal breakdown rather than the
   original 30-stock hindsight sample (Finding 3).
4. Add the same BOM/Buffer response-normalization defense used in `swing_scanner_code.js`
   to any future shared HTTP client refactor (Finding 4 — already fixed once today for the
   weekly reporter; audit remaining call sites).
5. [Add a 5th recommendation once Task 10's numbers are in, prioritizing whichever
   pattern/score-tier shows the weakest risk-adjusted return.]
```

- [ ] **Step 2: Fill in every bracketed placeholder with the real numbers from `backtest_analysis_swing_v2.json`**

Run: `python -c "import json; print(json.dumps(json.load(open('backtest_analysis_swing_v2.json')), ensure_ascii=False, indent=2))"` and transcribe every value into the tables above. Do not leave any `[bracket]` placeholder in the committed file.

- [ ] **Step 3: Commit**

```bash
git add docs/03-analysis/swing-algorithm-profitability-review.analysis.md
git commit -m "docs: swing algorithm profitability review (code review + empirical backtest)"
```

---

### Task 12: Visual dashboard (Artifact)

**Files:**
- Create: `docs/03-analysis/swing-algorithm-profitability-review.artifact.html` (source, checked in for reproducibility)

- [ ] **Step 1: Load the `artifact-design` skill before writing the page** (per the Artifact tool's own requirement)

- [ ] **Step 2: Build the dashboard HTML** with, at minimum:
  - A bar chart of score-bonus elements (static, from the constants in Task 5 — e.g. "촉매이벤트 +60", "OBV수급↑ +20", ...), to visually communicate scoring composition
  - A pie/donut chart of trade count by pattern type (from `by_pattern` in Task 10's output)
  - A bar chart comparing win rate / avg PnL across the 3 score tiers
  - A small "as-deployed vs regime-gate-restored" comparison panel (the Task 9/10 what-if numbers)
  - The Finding 1-5 callouts from Task 11's report, condensed to short cards
  - Follow the `dataviz` skill's palette/accessibility guidance (this session has that skill available — invoke it before finalizing colors)

- [ ] **Step 3: Publish**

Use the Artifact tool with `file_path` pointing at the HTML from Step 2, a stable `favicon` (e.g. `📊`), and a `description` summarizing the verdict in one sentence.

- [ ] **Step 4: Commit the HTML source**

```bash
git add docs/03-analysis/swing-algorithm-profitability-review.artifact.html
git commit -m "docs: publish swing algorithm profitability review dashboard"
```

---

## Self-Review Notes

- **Spec coverage:** All three brainstorming decisions are covered — (1) full Python port of the current algorithm incl. DART/supply (Tasks 1-7), (2) 200 tickers × 2024-01-01..2026-01-01 (Task 8), (3) markdown report + Artifact dashboard (Tasks 11-12). Toss exclusion is explicit in Global Constraints and Finding 5.
- **Placeholder scan:** Task 11's report template intentionally contains bracketed numeric placeholders because those values are the *output* of Task 10, which hasn't run yet at plan-writing time — Step 2 of Task 11 explicitly requires filling every one in before committing. No other task contains a placeholder.
- **Type consistency:** `SwingCandidate` (Task 5) fields — `pattern_type, score, rank_score, grade, entry, target, stop, hold_days, signals` — are used with identical names in Task 7's `apply_daily_selection`/`backtest_swing_v2` and Task 9's trade dict keys (`pattern_type, score, grade, pnl, date`). Verified no drift.
- **Scope check:** Single cohesive subsystem (one backtest pipeline + one report). Not split further.
