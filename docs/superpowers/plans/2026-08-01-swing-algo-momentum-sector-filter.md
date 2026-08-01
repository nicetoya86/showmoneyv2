# swing-algo-momentum-sector-filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the final, honest deployment recommendation for the momentum-continuation
pattern: commit the `sector_strong` filter comparison as a reproducible artifact, commit
reproductions of every "ruled out" exploration from this research line's investigation into
whether 90% hit_rate is achievable, and write the closing analysis document.

**Architecture:** No new source code — every function used already exists and is unmodified
(`candidate_signals.tag_candidates`, `target_stop_grid_search.run_one_config`,
`analyze_portfolio_return.simulate_portfolio`/`cagr_and_mdd`, `toss_liveprice.apply_toss_liveprice`,
`transaction_costs.apply_round_trip_cost`, `simulate_exits.simulate_exit`,
`run_swing_v2_backtest._iso_week_key`/`apply_daily_selection`). This plan is entirely
execution + analysis: run existing functions with specific parameters, save JSON outputs, write a
report.

**Tech Stack:** Python, pandas/numpy, existing `backtest/` modules. No new dependencies, no new
files under `backtest/` or `backtest/tests/`.

## Global Constraints

- **No source code is created or modified.** Every task in this plan produces only data JSON
  files and (in the final task) a markdown analysis document. If any step seems to require new
  logic beyond what's listed below, stop and flag it rather than writing new code — this plan was
  scoped assuming zero new code is needed.
- Reused, unmodified functions and their exact import paths (do not re-derive signatures — these
  are copied from the actual source):
  - `from backtest.candidate_signals import build_sector_returns_by_date, compute_sector_strength, tag_candidates`
  - `from backtest.generate_signal_candidates import CachedCandidate`
  - `from backtest.target_stop_grid_search import run_one_config, MIN_HIT_RATE, MIN_TRADES_PER_WEEK`
  - `from backtest.run_swing_v2_backtest import _iso_week_key, apply_daily_selection`
  - `from backtest.toss_liveprice import apply_toss_liveprice`
  - `from backtest.transaction_costs import apply_round_trip_cost, DEFAULT_ROUND_TRIP_COST_PCT`
  - `from backtest.simulate_exits import simulate_exit`
  - `from backtest.analyze_portfolio_return import simulate_portfolio, cagr_and_mdd`
  - `from backtest.indicators import sma`
  - `from backtest.yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart`
  - `from backtest.swing_signal_engine import MIN_PRICE, MIN_TURNOVER_ALGO`
- Reused, already-committed data files (do not re-fetch/regenerate): `backtest_momentum_candidates.json`
  (4,197 candidates), `backtest_sector_map.json`, `backtest_regime_lookup.json`,
  `backtest/tickers_operating.txt` (959 tickers).
- Deployment baseline ("Config A"): `target_pct=0.10, stop_pct=0.10, min_score=60,
  regime_gate=False, exclude_d_box=False, hold_days=10` (the value already baked into
  `backtest_momentum_candidates.json`'s cached candidates — no override needed for this config).
- Train split: `2022-01-01`..`2024-06-30`. Test split: `2024-07-01`..`2026-01-01`.
- **`run_one_config` does not filter candidates by date itself** — its `start`/`end` parameters
  are used only to compute the `trades_per_week` denominator. Every script in this plan must
  pre-filter the candidate list by date range before calling it, e.g.:
  ```python
  train_start_ts = pd.to_datetime('2022-01-01', utc=True)
  train_end_ts = pd.to_datetime('2024-06-30', utc=True)
  train_candidates = [c for c in candidates if train_start_ts <= pd.Timestamp(c.date) <= train_end_ts]
  ```
  Passing the full unfiltered candidate list for both "train" and "test" calls is a real bug that
  was caught and fixed during this session's exploration — every step below must filter first.
- No bracket placeholders or invented numbers in the final analysis document (Task 4) — every
  number must trace to a JSON file this plan commits.

---

### Task 1: Reproduce and commit `sector_strong` tags for the momentum pool

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Compute and save the `sector_strong` tag for every momentum candidate**

Run (re-reads each ticker's OHLCV from `yahoo_cache`'s disk cache — cache hits expected, no new
network fetch; low minutes):

```bash
python -c "
import json
import pandas as pd
from backtest.candidate_signals import build_sector_returns_by_date, compute_sector_strength
from backtest.generate_signal_candidates import CachedCandidate
from backtest.yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart

d = json.load(open('backtest_momentum_candidates.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]
sector_map = json.load(open('backtest_sector_map.json', encoding='utf-8'))

tickers = sorted({c.ticker for c in candidates})
per_ticker = {}
for t in tickers:
    data = fetch_yahoo_chart(YahooFetchSpec(ticker=t, range='5y', interval='1d'))
    df, _ = chart_to_ohlcv_daily(data)
    per_ticker[t] = df.sort_values('timestamp_utc').reset_index(drop=True)

sector_returns_by_date = build_sector_returns_by_date(sector_map, per_ticker)

tags = {}
for c in candidates:
    df = per_ticker.get(c.ticker)
    idxs = df.index[df['timestamp_utc'] == pd.Timestamp(c.date)].tolist()
    if not idxs:
        tags[(c.ticker, c.date)] = False
        continue
    date_key = pd.Timestamp(c.date).date().isoformat()
    tags[(c.ticker, c.date)] = compute_sector_strength(sector_returns_by_date, sector_map, c.code, date_key)

out = {f'{tk}|{dt}': v for (tk, dt), v in tags.items()}
json.dump(out, open('backtest_momentum_sector_tags.json', 'w', encoding='utf-8'), ensure_ascii=False)

n = len(tags)
n_strong = sum(1 for v in tags.values() if v)
print(f'tagged {n} candidates: sector_strong={n_strong}')
"
```

Expected: no exception; `tagged` count equals 4,197 (the full momentum candidate count from
`backtest_momentum_candidates.json`). `sector_strong` count is expected to be a substantial
fraction (roughly 60% based on this session's exploration) but this is not a strict pass/fail
check — report the actual number honestly in Task 4 regardless of what it is.

- [ ] **Step 2: Commit**

```bash
git add backtest_momentum_sector_tags.json
git commit -m "data(backtest): sector_strong tags for momentum-continuation pool (sub-project 6)"
```

---

### Task 2: Config A baseline vs. `sector_strong`-filtered comparison

**Files:** none created except the output JSON — this is an execution-only task.

**Interfaces:**
- Consumes: `backtest_momentum_candidates.json` (Task 5 of sub-project 5), `backtest_momentum_sector_tags.json` (Task 1 of this plan).

- [ ] **Step 1: Run Config A (target=10%, stop=10%, hold=10) with and without the `sector_strong` filter**

```bash
python -c "
import json
import pandas as pd
from backtest.generate_signal_candidates import CachedCandidate
from backtest.target_stop_grid_search import run_one_config

d = json.load(open('backtest_momentum_candidates.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]
regime_lookup = json.load(open('backtest_regime_lookup.json', encoding='utf-8'))
raw_tags = json.load(open('backtest_momentum_sector_tags.json', encoding='utf-8'))
tags_lookup = {tuple(k.split('|', 1)): {'sector_strong': v} for k, v in raw_tags.items()}

train_start_ts = pd.to_datetime('2022-01-01', utc=True)
train_end_ts = pd.to_datetime('2024-06-30', utc=True)
test_start_ts = pd.to_datetime('2024-07-01', utc=True)
test_end_ts = pd.to_datetime('2026-01-01', utc=True)
train_candidates = [c for c in candidates if train_start_ts <= pd.Timestamp(c.date) <= train_end_ts]
test_candidates = [c for c in candidates if test_start_ts <= pd.Timestamp(c.date) <= test_end_ts]

CONFIG = dict(target_pct=0.10, stop_pct=0.10, min_score=60, regime_gate=False, exclude_d_box=False)

results = {}
for label, required_tags in [('none', frozenset()), ('sector_strong', frozenset({'sector_strong'}))]:
    r_train = run_one_config(train_candidates, regime_lookup=regime_lookup, start='2022-01-01', end='2024-06-30',
                              required_tags=required_tags, tags_lookup=tags_lookup, **CONFIG)
    r_test = run_one_config(test_candidates, regime_lookup=regime_lookup, start='2024-07-01', end='2026-01-01',
                             required_tags=required_tags, tags_lookup=tags_lookup, **CONFIG)
    results[label] = {'train': r_train, 'test': r_test}
    print(f\"{label}: train(n={r_train['n_trades']} hit={r_train['hit_rate']*100:.2f}% tpw={r_train['trades_per_week']:.2f} cagr={r_train['cagr_15slot']*100:.2f}%) test(n={r_test['n_trades']} hit={r_test['hit_rate']*100:.2f}% tpw={r_test['trades_per_week']:.2f} cagr={r_test['cagr_15slot']*100:.2f}%)\")

json.dump(results, open('backtest_momentum_sectorfilter_results.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('wrote backtest_momentum_sectorfilter_results.json')
"
```

Expected: no exception; both `none` and `sector_strong` entries present with `train`/`test`
sub-results. Report the actual numbers honestly in Task 4, whatever they are — do not assume they
match this session's earlier exploratory run exactly (that run was ad hoc and uncommitted; this
one is the authoritative, committed figure).

- [ ] **Step 2: Commit**

```bash
git add backtest_momentum_sectorfilter_results.json
git commit -m "data(backtest): Config A baseline vs sector_strong-filtered comparison (sub-project 6)"
```

---

### Task 3: Reproduce and commit the ruled-out explorations

**Files:** none created except the output JSONs — this is an execution-only task with 6 independent steps, each producing its own artifact. Run each step's script exactly as written; each is
independent of the others (order doesn't matter, but numbering follows the design doc's Section 1.1 list).

**Interfaces:**
- Consumes: `backtest_momentum_candidates.json`, `backtest_regime_lookup.json`,
  `backtest/tickers_operating.txt`.

- [ ] **Step 1 (entry-tightening): re-run the tightened momentum-continuation scan and grid**

This reproduces the RS-top-2%/breakout-margin-2%/rvol-2.0/`hold_days=5` exploration. It re-fetches
per-ticker OHLCV (disk-cached) and re-fetches per-day DART/supply data (network — this step alone
can take several minutes, matching the original momentum scan's runtime):

```bash
python -c "
import json
import numpy as np
import pandas as pd
from backtest.generate_signal_candidates import CachedCandidate, _code_of
from backtest.generate_momentum_candidates import build_universe_return_lookup, compute_trailing_return, _passes_base_filters
from backtest.indicators import sma
from backtest.yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart
from backtest.dart_history import fetch_disclosures_for_date
from backtest.krx_supply_history import fetch_supply_for_date
from backtest.target_stop_grid_search import run_one_config

RS_TOP_FRAC_TIGHT = 0.02
BREAKOUT_MARGIN = 1.02
TRIGGER_RVOL_MIN = 2.0
HOLD_DAYS_NEW = 5
NEW_HIGH_LOOKBACK = 60

tickers = [x.strip() for x in open('backtest/tickers_operating.txt', encoding='utf-8').read().splitlines() if x.strip() and not x.startswith('#')]

per_ticker = {}
skipped = []
for t in tickers:
    try:
        data = fetch_yahoo_chart(YahooFetchSpec(ticker=t, range='5y', interval='1d'))
        df, _ = chart_to_ohlcv_daily(data)
        per_ticker[t] = df.sort_values('timestamp_utc').reset_index(drop=True)
    except Exception:
        skipped.append(t)

rs_lookup = build_universe_return_lookup(per_ticker, lookback=60, top_frac=RS_TOP_FRAC_TIGHT)
start_ts = pd.to_datetime('2022-01-01', utc=True); end_ts = pd.to_datetime('2026-01-01', utc=True)
all_days = sorted({d for df in per_ticker.values() for d in df['timestamp_utc'].tolist()})
all_days = [d for d in all_days if start_ts <= d <= end_ts]

candidates = []
for day in all_days:
    date_key = pd.Timestamp(day).date().isoformat()
    rs_threshold = rs_lookup.get(date_key)
    if rs_threshold is None:
        continue
    trd_dd = day.strftime('%Y%m%d')
    supply_map = fetch_supply_for_date(trd_dd)
    dart_map = fetch_disclosures_for_date(trd_dd, api_key='34a9b090d2a7b1ee689a240fef68667d36b389e7')
    for t, df in per_ticker.items():
        idxs = df.index[df['timestamp_utc'] == day].tolist()
        if not idxs:
            continue
        idx = int(idxs[0])
        entry_idx = idx + 1
        if entry_idx >= len(df):
            continue
        code = _code_of(t)
        if not _passes_base_filters(df, idx, supply=supply_map.get(code, {}), dart_items=dart_map.get(code, [])):
            continue
        close = df['close'].to_numpy(dtype='float64'); high = df['high'].to_numpy(dtype='float64'); vol = df['volume'].to_numpy(dtype='float64')
        if idx < NEW_HIGH_LOOKBACK:
            continue
        own_return = compute_trailing_return(df, idx, lookback=60)
        if not np.isfinite(own_return) or own_return < rs_threshold:
            continue
        high60 = float(np.max(high[idx-NEW_HIGH_LOOKBACK:idx]))
        if close[idx] < high60 * BREAKOUT_MARGIN:
            continue
        sma50 = sma(close, 50); sma200 = sma(close, 200)
        if not (np.isfinite(sma50[idx]) and np.isfinite(sma200[idx])):
            continue
        if not (close[idx] > sma50[idx] > sma200[idx]):
            continue
        vol_window = vol[max(0, idx-20):idx]
        vol20_avg = float(vol_window.sum()/max(1, min(20, idx))) if len(vol_window) else 0.0
        rvol = (vol[idx]/vol20_avg) if vol20_avg > 0 else 0.0
        if rvol < TRIGGER_RVOL_MIN:
            continue
        window = df.iloc[entry_idx:entry_idx+HOLD_DAYS_NEW]
        candidates.append(CachedCandidate(
            ticker=t, code=code, date=day.isoformat(), entry=float(close[idx]),
            pattern_type='F모멘텀v2', score=110, rank_score=110, grade='매수', hold_days=HOLD_DAYS_NEW,
            window_open=window['open'].astype(float).tolist(),
            window_high=window['high'].astype(float).tolist(),
            window_low=window['low'].astype(float).tolist(),
            window_close=window['close'].astype(float).tolist(),
        ))

regime_lookup = json.load(open('backtest_regime_lookup.json', encoding='utf-8'))
train_start_ts = pd.to_datetime('2022-01-01', utc=True); train_end_ts = pd.to_datetime('2024-06-30', utc=True)
test_start_ts = pd.to_datetime('2024-07-01', utc=True); test_end_ts = pd.to_datetime('2026-01-01', utc=True)
train_c = [c for c in candidates if train_start_ts <= pd.Timestamp(c.date) <= train_end_ts]
test_c = [c for c in candidates if test_start_ts <= pd.Timestamp(c.date) <= test_end_ts]

r_train = run_one_config(train_c, target_pct=0.03, stop_pct=0.50, min_score=60, regime_gate=False, exclude_d_box=False, regime_lookup=regime_lookup, start='2022-01-01', end='2024-06-30')
r_test = run_one_config(test_c, target_pct=0.03, stop_pct=0.50, min_score=60, regime_gate=False, exclude_d_box=False, regime_lookup=regime_lookup, start='2024-07-01', end='2026-01-01')

out = {
    'params': {'RS_TOP_FRAC': RS_TOP_FRAC_TIGHT, 'BREAKOUT_MARGIN': BREAKOUT_MARGIN, 'TRIGGER_RVOL_MIN': TRIGGER_RVOL_MIN, 'HOLD_DAYS': HOLD_DAYS_NEW, 'target_pct': 0.03, 'stop_pct': 0.50},
    'candidate_count': len(candidates), 'skipped_tickers': skipped,
    'train_result': r_train, 'test_result': r_test,
}
json.dump(out, open('backtest_momentum_entrytighten_explore.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('candidates:', len(candidates))
print('train:', r_train['n_trades'], r_train['hit_rate'], r_train['trades_per_week'], r_train['cagr_15slot'])
print('test:', r_test['n_trades'], r_test['hit_rate'], r_test['trades_per_week'], r_test['cagr_15slot'])
"
```

Expected: `candidate_count` around 697 (session's exploratory figure — report the actual number,
don't force a match). `train_result`/`test_result` show a collapsed `trades_per_week` (well under
5) and a low or negative `cagr_15slot` — this step exists to document a negative result, not to
find a positive one.

- [ ] **Step 2 (breakeven-ratchet, hold_days=5): reproduce the breakeven-or-better rate at the original hold_days=5 setting**

```bash
python -c "
import json
import dataclasses
import pandas as pd
from backtest.generate_signal_candidates import CachedCandidate
from backtest.toss_liveprice import apply_toss_liveprice
from backtest.transaction_costs import apply_round_trip_cost, DEFAULT_ROUND_TRIP_COST_PCT
from backtest.run_swing_v2_backtest import _iso_week_key, apply_daily_selection
from backtest.analyze_portfolio_return import simulate_portfolio, cagr_and_mdd

def simulate_exit_breakeven(df, entry_idx, *, entry, initial_stop, trigger_price, hold_days):
    stop = initial_stop
    active = False
    end = min(len(df)-1, entry_idx+hold_days-1)
    for i in range(entry_idx, end+1):
        lo = float(df.iloc[i]['low']); hi = float(df.iloc[i]['high'])
        if lo <= stop:
            return {'exit_idx': i, 'exit_price': stop, 'result': 'breakeven_stop' if active else 'initial_stop', 'days_held': i-entry_idx}
        if not active and hi >= trigger_price:
            active = True
            stop = entry * (1 + DEFAULT_ROUND_TRIP_COST_PCT)
    exit_price = float(df.iloc[end]['close'])
    return {'exit_idx': end, 'exit_price': exit_price, 'result': 'timeout_protected' if active else 'timeout', 'days_held': end-entry_idx}

def run_breakeven_config(candidates, *, initial_stop_pct, trigger_pct, hold_days, start, end):
    start_ts = pd.to_datetime(start, utc=True); end_ts = pd.to_datetime(end, utc=True)
    weeks = max((end_ts-start_ts).days/7.0, 1e-9)
    by_day = {}
    for c in candidates:
        by_day.setdefault(pd.Timestamp(c.date), []).append(c)
    week_state = {'key': None, 'count': 0, 'codes': set()}
    trades = []
    TOL = -1e-9
    for day in sorted(by_day.keys()):
        if not (start_ts <= day <= end_ts):
            continue
        wk = _iso_week_key(day)
        if wk != week_state['key']:
            week_state = {'key': wk, 'count': 0, 'codes': set()}
        filtered = [(c.code, c) for c in by_day[day]]
        selected = apply_daily_selection(filtered, week_state)
        for code, c in selected:
            initial_stop = c.entry*(1-initial_stop_pct)
            next_day_open = c.window_open[0] if c.window_open else c.entry
            toss = apply_toss_liveprice(c.entry, c.entry*10, initial_stop, next_day_open)
            if toss.status == 'blocked_stopped_out':
                continue
            df = pd.DataFrame({'open': c.window_open, 'high': c.window_high, 'low': c.window_low, 'close': c.window_close})
            if df.empty:
                continue
            sim = simulate_exit_breakeven(df, 0, entry=toss.entry, initial_stop=toss.stop, trigger_price=toss.entry*(1+trigger_pct), hold_days=hold_days)
            gross = (float(sim['exit_price']) - toss.entry) / toss.entry
            pnl = apply_round_trip_cost(gross)
            trades.append({'date': c.date, 'ticker': c.ticker, 'pnl': pnl, 'result': sim['result']})
    n = len(trades)
    if n == 0:
        return {'n_trades': 0}
    breakeven_or_better = sum(1 for t in trades if t['pnl'] >= TOL)/n
    avg_pnl = sum(t['pnl'] for t in trades)/n
    result_counts = {}
    for t in trades:
        result_counts[t['result']] = result_counts.get(t['result'], 0) + 1
    trades_sorted = sorted(trades, key=lambda t: (t['date'], t['ticker']))
    curve = simulate_portfolio(trades_sorted, 15)
    _, mdd, _, cagr = cagr_and_mdd(curve, trades_sorted[0]['date'], trades_sorted[-1]['date'])
    return {'n_trades': n, 'breakeven_rate': breakeven_or_better, 'trades_per_week': n/weeks, 'avg_pnl': avg_pnl, 'cagr_15slot': cagr, 'result_counts': result_counts}

d = json.load(open('backtest_momentum_candidates.json', encoding='utf-8'))
candidates_5d = [dataclasses.replace(CachedCandidate(**c), hold_days=5) for c in d['candidates']]

results = {}
for split, (s, e) in [('train', ('2022-01-01', '2024-06-30')), ('test', ('2024-07-01', '2026-01-01'))]:
    results[split] = run_breakeven_config(candidates_5d, initial_stop_pct=0.03, trigger_pct=0.015, hold_days=5, start=s, end=e)
    print(split, results[split])

json.dump({'params': {'initial_stop_pct': 0.03, 'trigger_pct': 0.015, 'hold_days': 5}, 'results': results},
          open('backtest_momentum_breakeven_hold5.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
"
```

- [ ] **Step 3 (breakeven-ratchet, hold_days=10, wide stop): reproduce the misleading-90% finding, including the outlier diagnostic**

```bash
python -c "
import json
import pandas as pd
import statistics
from backtest.generate_signal_candidates import CachedCandidate
from backtest.toss_liveprice import apply_toss_liveprice
from backtest.transaction_costs import apply_round_trip_cost, DEFAULT_ROUND_TRIP_COST_PCT
from backtest.run_swing_v2_backtest import _iso_week_key, apply_daily_selection
from backtest.analyze_portfolio_return import simulate_portfolio, cagr_and_mdd

def simulate_exit_breakeven(df, entry_idx, *, entry, initial_stop, trigger_price, hold_days):
    stop = initial_stop
    active = False
    end = min(len(df)-1, entry_idx+hold_days-1)
    for i in range(entry_idx, end+1):
        lo = float(df.iloc[i]['low']); hi = float(df.iloc[i]['high'])
        if lo <= stop:
            return {'exit_idx': i, 'exit_price': stop, 'result': 'breakeven_stop' if active else 'initial_stop', 'days_held': i-entry_idx}
        if not active and hi >= trigger_price:
            active = True
            stop = entry * (1 + DEFAULT_ROUND_TRIP_COST_PCT)
    exit_price = float(df.iloc[end]['close'])
    return {'exit_idx': end, 'exit_price': exit_price, 'result': 'timeout_protected' if active else 'timeout', 'days_held': end-entry_idx}

d = json.load(open('backtest_momentum_candidates.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]

start_ts = pd.to_datetime('2022-01-01', utc=True); end_ts = pd.to_datetime('2024-06-30', utc=True)
weeks = max((end_ts-start_ts).days/7.0, 1e-9)
by_day = {}
for c in candidates:
    by_day.setdefault(pd.Timestamp(c.date), []).append(c)
week_state = {'key': None, 'count': 0, 'codes': set()}
trades = []
TOL = -1e-9
for day in sorted(by_day.keys()):
    if not (start_ts <= day <= end_ts):
        continue
    wk = _iso_week_key(day)
    if wk != week_state['key']:
        week_state = {'key': wk, 'count': 0, 'codes': set()}
    filtered = [(c.code, c) for c in by_day[day]]
    selected = apply_daily_selection(filtered, week_state)
    for code, c in selected:
        initial_stop = c.entry*(1-0.20)
        next_day_open = c.window_open[0] if c.window_open else c.entry
        toss = apply_toss_liveprice(c.entry, c.entry*10, initial_stop, next_day_open)
        if toss.status == 'blocked_stopped_out':
            continue
        df = pd.DataFrame({'open': c.window_open, 'high': c.window_high, 'low': c.window_low, 'close': c.window_close})
        if df.empty:
            continue
        sim = simulate_exit_breakeven(df, 0, entry=toss.entry, initial_stop=toss.stop, trigger_price=toss.entry*1.005, hold_days=10)
        gross = (float(sim['exit_price']) - toss.entry) / toss.entry
        pnl = apply_round_trip_cost(gross)
        trades.append({'date': c.date, 'ticker': c.ticker, 'pnl': pnl, 'result': sim['result']})

n = len(trades)
breakeven_rate = sum(1 for t in trades if t['pnl'] >= TOL)/n
mean_pnl = statistics.mean(t['pnl'] for t in trades)
median_pnl = statistics.median(t['pnl'] for t in trades)
pnls_sorted = sorted(t['pnl'] for t in trades)
trades_sorted = sorted(trades, key=lambda t: (t['date'], t['ticker']))
curve = simulate_portfolio(trades_sorted, 15)
_, mdd, _, cagr = cagr_and_mdd(curve, trades_sorted[0]['date'], trades_sorted[-1]['date'])

out = {
    'params': {'initial_stop_pct': 0.20, 'trigger_pct': 0.005, 'hold_days': 10, 'split': 'train'},
    'n_trades': n, 'breakeven_rate': breakeven_rate, 'trades_per_week': n/weeks,
    'mean_pnl': mean_pnl, 'median_pnl': median_pnl, 'cagr_15slot': cagr,
    'top_10_pnls': pnls_sorted[-10:], 'bottom_10_pnls': pnls_sorted[:10],
}
json.dump(out, open('backtest_momentum_breakeven_hold10_wide.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('n=', n, 'breakeven_rate=', breakeven_rate, 'mean=', mean_pnl, 'median=', median_pnl, 'cagr=', cagr)
"
```

Expected: `breakeven_rate` around 94% (train), `mean_pnl` clearly higher than `median_pnl` (median
at or near 0.0), and `top_10_pnls` containing at least one extreme outlier (e.g. >100%) — this
step exists specifically to document why this configuration was rejected despite its high
headline rate, so the mean/median gap and the outlier list are the important output, not just the
rate itself.

- [ ] **Step 4 (weekly basket framing): reproduce the weekly-average-return distribution for Config A**

```bash
python -c "
import json
import pandas as pd
from backtest.generate_signal_candidates import CachedCandidate
from backtest.run_swing_v2_backtest import _iso_week_key, apply_daily_selection
from backtest.toss_liveprice import apply_toss_liveprice
from backtest.transaction_costs import apply_round_trip_cost
from backtest.simulate_exits import simulate_exit

def collect_trades(candidates, *, target_pct, stop_pct, start, end):
    start_ts = pd.to_datetime(start, utc=True); end_ts = pd.to_datetime(end, utc=True)
    by_day = {}
    for c in candidates:
        by_day.setdefault(pd.Timestamp(c.date), []).append(c)
    week_state = {'key': None, 'count': 0, 'codes': set()}
    trades = []
    for day in sorted(by_day.keys()):
        if not (start_ts <= day <= end_ts):
            continue
        wk = _iso_week_key(day)
        if wk != week_state['key']:
            week_state = {'key': wk, 'count': 0, 'codes': set()}
        filtered = [(c.code, c) for c in by_day[day]]
        selected = apply_daily_selection(filtered, week_state)
        for code, c in selected:
            new_target = c.entry*(1+target_pct); new_stop = c.entry*(1-stop_pct)
            next_day_open = c.window_open[0] if c.window_open else c.entry
            toss = apply_toss_liveprice(c.entry, new_target, new_stop, next_day_open)
            if toss.status in ('blocked_chasing', 'blocked_stopped_out'):
                continue
            df = pd.DataFrame({'open': c.window_open, 'high': c.window_high, 'low': c.window_low, 'close': c.window_close})
            if df.empty:
                continue
            sim = simulate_exit(df, 0, entry=toss.entry, stop=toss.stop, target=toss.target, hold_days=c.hold_days)
            gross = (float(sim['exit_price']) - toss.entry)/toss.entry
            pnl = apply_round_trip_cost(gross)
            trades.append({'date': day, 'week': wk, 'pnl': pnl})
    return trades

d = json.load(open('backtest_momentum_candidates.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]

out = {}
for split, (s, e) in [('train', ('2022-01-01', '2024-06-30')), ('test', ('2024-07-01', '2026-01-01'))]:
    trades = collect_trades(candidates, target_pct=0.10, stop_pct=0.10, start=s, end=e)
    by_week = {}
    for t in trades:
        by_week.setdefault(t['week'], []).append(t['pnl'])
    week_avgs = {str(wk): sum(pnls)/len(pnls) for wk, pnls in by_week.items()}
    n_weeks = len(week_avgs)
    pos_weeks = sum(1 for v in week_avgs.values() if v > 0)
    pos3_weeks = sum(1 for v in week_avgs.values() if v >= 0.03)
    out[split] = {
        'total_trades': len(trades), 'n_weeks': n_weeks,
        'avg_basket_size': len(trades)/n_weeks if n_weeks else 0,
        'weeks_positive': pos_weeks, 'weeks_positive_pct': pos_weeks/n_weeks*100 if n_weeks else 0,
        'weeks_ge_3pct': pos3_weeks, 'weeks_ge_3pct_pct': pos3_weeks/n_weeks*100 if n_weeks else 0,
    }
    print(split, out[split])

json.dump(out, open('backtest_momentum_weekly_basket.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
"
```

- [ ] **Step 5 (regime gate): reproduce the regime-gate comparison on Config A and Config B**

```bash
python -c "
import json
import pandas as pd
from backtest.generate_signal_candidates import CachedCandidate
from backtest.target_stop_grid_search import run_one_config

d = json.load(open('backtest_momentum_candidates.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]
regime_lookup = json.load(open('backtest_regime_lookup.json', encoding='utf-8'))

train_start_ts = pd.to_datetime('2022-01-01', utc=True); train_end_ts = pd.to_datetime('2024-06-30', utc=True)
test_start_ts = pd.to_datetime('2024-07-01', utc=True); test_end_ts = pd.to_datetime('2026-01-01', utc=True)
train_c = [c for c in candidates if train_start_ts <= pd.Timestamp(c.date) <= train_end_ts]
test_c = [c for c in candidates if test_start_ts <= pd.Timestamp(c.date) <= test_end_ts]

out = {}
for label, cfg in [('config_a_10_10', dict(target_pct=0.10, stop_pct=0.10)), ('config_b_3_100', dict(target_pct=0.03, stop_pct=1.00))]:
    out[label] = {}
    for rg in [False, True]:
        r_tr = run_one_config(train_c, min_score=60, regime_gate=rg, exclude_d_box=False, regime_lookup=regime_lookup, start='2022-01-01', end='2024-06-30', **cfg)
        r_te = run_one_config(test_c, min_score=60, regime_gate=rg, exclude_d_box=False, regime_lookup=regime_lookup, start='2024-07-01', end='2026-01-01', **cfg)
        out[label][str(rg)] = {'train': r_tr, 'test': r_te}
        print(label, rg, 'train:', r_tr['n_trades'], r_tr['hit_rate'], r_tr['trades_per_week'], r_tr['cagr_15slot'])
        print(label, rg, 'test :', r_te['n_trades'], r_te['hit_rate'], r_te['trades_per_week'], r_te['cagr_15slot'])

json.dump(out, open('backtest_momentum_regime_gate.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
"
```

- [ ] **Step 6 (low-volatility-accumulation gut-check + volume filters): reproduce both quick checks**

```bash
python -c "
import json
import numpy as np
import pandas as pd
from backtest.candidate_signals import compute_vol_contraction, build_sector_returns_by_date, compute_sector_strength
from backtest.indicators import sma
from backtest.swing_signal_engine import MIN_PRICE, MIN_TURNOVER_ALGO
from backtest.yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart
from backtest.generate_signal_candidates import CachedCandidate
from backtest.target_stop_grid_search import run_one_config

# --- Part A: low-volatility-accumulation gut-check on a 200-ticker sample ---
tickers = [x.strip() for x in open('backtest/tickers_operating.txt', encoding='utf-8').read().splitlines() if x.strip() and not x.startswith('#')]
tickers_sample = tickers[:200]

hits = 0; total = 0; returns_at_10d = []
for t in tickers_sample:
    try:
        data = fetch_yahoo_chart(YahooFetchSpec(ticker=t, range='5y', interval='1d'))
        df, _ = chart_to_ohlcv_daily(data)
        df = df.sort_values('timestamp_utc').reset_index(drop=True)
    except Exception:
        continue
    close = df['close'].to_numpy(dtype='float64'); high = df['high'].to_numpy(dtype='float64'); vol = df['volume'].to_numpy(dtype='float64')
    n = len(df)
    sma60 = sma(close, 60)
    for idx in range(70, n-11):
        current_price = close[idx]
        if current_price < MIN_PRICE:
            continue
        turnover = current_price * (vol[idx] if np.isfinite(vol[idx]) else 0.0)
        if turnover < MIN_TURNOVER_ALGO:
            continue
        if not np.isfinite(sma60[idx]) or current_price <= sma60[idx]:
            continue
        if not compute_vol_contraction(df.iloc[:idx+1], idx):
            continue
        fwd_high = high[idx+1:idx+11]
        if len(fwd_high) < 10:
            continue
        reached = np.max(fwd_high) >= current_price * 1.03
        hits += 1 if reached else 0
        total += 1
        returns_at_10d.append(close[idx+10]/current_price - 1)

lowvol_result = {
    'sample_tickers': len(tickers_sample), 'qualifying_samples': total,
    'forward_hit_rate_3pct_10d': (hits/total if total else 0),
    'avg_10d_return': float(np.mean(returns_at_10d)) if returns_at_10d else None,
    'median_10d_return': float(np.median(returns_at_10d)) if returns_at_10d else None,
}
print('low-vol-accumulation:', lowvol_result)

# --- Part B: moderate volume filters on Config A ---
d = json.load(open('backtest_momentum_candidates.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]
sector_map = json.load(open('backtest_sector_map.json', encoding='utf-8'))
raw_tags = json.load(open('backtest_momentum_sector_tags.json', encoding='utf-8'))
tags_lookup = {tuple(k.split('|', 1)): v for k, v in raw_tags.items()}

mom_tickers = sorted({c.ticker for c in candidates})
per_ticker = {}
for t in mom_tickers:
    data = fetch_yahoo_chart(YahooFetchSpec(ticker=t, range='5y', interval='1d'))
    df, _ = chart_to_ohlcv_daily(data)
    per_ticker[t] = df.sort_values('timestamp_utc').reset_index(drop=True)

rvol_map = {}
for c in candidates:
    df = per_ticker.get(c.ticker)
    idxs = df.index[df['timestamp_utc'] == pd.Timestamp(c.date)].tolist()
    if not idxs:
        continue
    idx = int(idxs[0])
    vol = df['volume'].to_numpy(dtype='float64')
    vol_window = vol[max(0, idx-20):idx]
    vol20_avg = float(vol_window.sum()/max(1, min(20, idx))) if len(vol_window) else 0.0
    rvol_map[(c.ticker, c.date)] = (vol[idx]/vol20_avg) if vol20_avg > 0 else 0.0

regime_lookup = json.load(open('backtest_regime_lookup.json', encoding='utf-8'))
train_start_ts = pd.to_datetime('2022-01-01', utc=True); train_end_ts = pd.to_datetime('2024-06-30', utc=True)
test_start_ts = pd.to_datetime('2024-07-01', utc=True); test_end_ts = pd.to_datetime('2026-01-01', utc=True)

def run_filtered(filter_fn):
    filt = [c for c in candidates if filter_fn(c)]
    train_c = [c for c in filt if train_start_ts <= pd.Timestamp(c.date) <= train_end_ts]
    test_c = [c for c in filt if test_start_ts <= pd.Timestamp(c.date) <= test_end_ts]
    r_tr = run_one_config(train_c, target_pct=0.10, stop_pct=0.10, min_score=60, regime_gate=False, exclude_d_box=False, regime_lookup=regime_lookup, start='2022-01-01', end='2024-06-30')
    r_te = run_one_config(test_c, target_pct=0.10, stop_pct=0.10, min_score=60, regime_gate=False, exclude_d_box=False, regime_lookup=regime_lookup, start='2024-07-01', end='2026-01-01')
    return {'pool_size': len(filt), 'train': r_tr, 'test': r_te}

volume_filter_results = {
    'rvol_1_3': run_filtered(lambda c: rvol_map.get((c.ticker, c.date), 0) >= 1.3),
    'rvol_1_5': run_filtered(lambda c: rvol_map.get((c.ticker, c.date), 0) >= 1.5),
}
for k, v in volume_filter_results.items():
    print(k, 'train:', v['train']['n_trades'], v['train']['hit_rate'], v['train']['cagr_15slot'],
          'test:', v['test']['n_trades'], v['test']['hit_rate'], v['test']['cagr_15slot'])

json.dump({'low_vol_accumulation': lowvol_result, 'volume_filters': volume_filter_results},
          open('backtest_momentum_lowvol_and_volume_explore.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
"
```

- [ ] **Step 7: Commit all six artifacts from this task together**

```bash
git add backtest_momentum_entrytighten_explore.json backtest_momentum_breakeven_hold5.json backtest_momentum_breakeven_hold10_wide.json backtest_momentum_weekly_basket.json backtest_momentum_regime_gate.json backtest_momentum_lowvol_and_volume_explore.json
git commit -m "data(backtest): reproduce ruled-out explorations for momentum win-rate investigation (sub-project 6)"
```

---

### Task 4: Write the final analysis document

**Files:**
- Create: `docs/03-analysis/swing-algo-momentum-sector-filter.analysis.md`

- [ ] **Step 1: Assemble the honest, fully-cited summary**

Using the real numbers from every JSON file committed in Tasks 1-3 (`backtest_momentum_sector_tags.json`,
`backtest_momentum_sectorfilter_results.json`, `backtest_momentum_entrytighten_explore.json`,
`backtest_momentum_breakeven_hold5.json`, `backtest_momentum_breakeven_hold10_wide.json`,
`backtest_momentum_weekly_basket.json`, `backtest_momentum_regime_gate.json`,
`backtest_momentum_lowvol_and_volume_explore.json`), write
`docs/03-analysis/swing-algo-momentum-sector-filter.analysis.md` with these sections (no bracket
placeholders — every number must be the actual value read from these JSON files, not copied from
this plan's or the design doc's prose without verification):

- **Header** matching the convention of `docs/03-analysis/swing-algo-momentum-continuation.analysis.md`
  (Analysis Type, Project, Feature, Design Doc / Implementation Plan links, Prior work, Date).
- **Method summary**: restate that this sub-project makes no changes to the momentum-continuation
  entry rule or `target_stop_grid_search.py`, only applies an additive `sector_strong` filter and
  documents a set of already-explored, ruled-out alternatives, linking to the design doc rather
  than re-deriving the reasoning.
- **Config A vs. sector_strong-filtered table**: from `backtest_momentum_sectorfilter_results.json`
  — train/test `n_trades`/reliability/`hit_rate`/`trades_per_week`/`cagr_15slot` for both the
  unfiltered and `sector_strong`-filtered pools.
- **Ruled-out explorations, one subsection each**, citing the specific committed JSON file and its
  actual numbers: entry-tightening, breakeven-ratchet at `hold_days=5`, breakeven-ratchet at
  `hold_days=10` with wide stop (explicitly include the mean-vs-median gap and the outlier list as
  the reason it was rejected, not just the headline rate), weekly-basket framing, regime-gate (both
  configs), low-volatility-accumulation gut-check, and moderate volume filters. Each subsection:
  what was tried, the actual result, why it doesn't change the sub-project's conclusion.
- **Decision-gate verdict**: state plainly that `hit_rate >= 90%` is not achieved by the
  `sector_strong`-filtered Config A (or by anything else tried), report its actual hit_rate/cagr/
  frequency using the three-way framework (target-met / target-not-met-but-reliable /
  underpowered) consistent with every prior sub-project, and confirm whether `n_trades >= 50`
  holds on both splits (both are expected to be comfortably above 50 given Config A's baseline
  scale, but confirm from the actual committed numbers).
- **Limitations**: restate the design doc's Section 6 limitations (train/test cagr divergence for
  the `sector_strong` filter, single train/test split, this being a settled-for-realistic outcome
  not a solved problem).
- **Final recommendation**: state plainly which configuration to treat as the production
  candidate (Config A, with or without the `sector_strong` filter — decide based on the actual
  numbers found in Task 2, weighing the hit_rate gain against the train-side cagr cost) and that
  no further hit-rate-chasing is recommended for momentum-continuation specifically.

State explicitly that no production code (`src/swing-scanner.src.js`) was changed by this
sub-project.

- [ ] **Step 2: Commit the analysis document**

```bash
git add docs/03-analysis/swing-algo-momentum-sector-filter.analysis.md
git commit -m "docs: final analysis for swing algo sub-project 6 (momentum win-rate investigation conclusion)"
```

---

## Self-Review Notes

- **Spec coverage**: Task 1 covers the design doc's Section 2 item 1 (`sector_strong` tagging).
  Task 2 covers item 2 (Config A comparison). Task 3 covers Section 1.1's full list of ruled-out
  explorations (entry-tightening, both breakeven variants, weekly basket, regime gate on both
  configs, low-vol-accumulation, volume filters). Task 4 covers item 3 (final analysis document)
  and Section 5's sanity-check requirement (compare against Section 1.2's ad hoc figures, flag if
  they don't match rather than assuming they will).
- **Placeholder scan**: no TBD/TODO. Every script is complete, runnable code copied from this
  session's actual validated exploration (including the train/test date-filtering fix and the
  floating-point tolerance fix for the breakeven rate calculation — both real bugs caught and
  fixed during this session, now baked into the scripts as written rather than left for the
  implementer to rediscover).
- **Type consistency**: `CachedCandidate` field names, `run_one_config`'s parameter names
  (`target_pct`, `stop_pct`, `min_score`, `regime_gate`, `exclude_d_box`, `regime_lookup`,
  `required_tags`, `tags_lookup`), and `tag_candidates`/`compute_sector_strength`'s signatures are
  used identically to their actual definitions in `backtest/target_stop_grid_search.py` and
  `backtest/candidate_signals.py` throughout every task — no invented parameter names.
