# Gap Analysis: trailing-stop-regime-fix

- **Date**: 2026-05-02
- **Design**: `docs/02-design/features/trailing-stop-regime-fix.design.md`
- **Implementation**: `swing_scanner_code.js`
- **Match Rate**: **95%** ✅ (above 90% threshold)

---

## Item-by-Item Results

### C-1 — Constants — 90%

| Constant | Design | Implementation | Status |
|---|---|---|---|
| `REGIME_YEST_DOWN` | `-0.015` | `-0.015` (line 23) | ✅ |
| `REGIME_GAP_DOWN` | `-0.007` | `-0.007` (line 24) | ✅ |
| `REGIME_SMA_FAST` | `5` | `5` (line 25) | ✅ |
| `REGIME_LOG_EMOJI` | `'📊'` | **hardcoded literal** | ⚠️ Minor |

`📊` is hardcoded at line 1539 instead of referencing the constant. Functionally equivalent.

### A-1 — `fetchDailyOHLC` — 100% ✅

Implementation at lines 365–380 matches the design exactly:
- Wraps `fetchDailyFchart` with symbolMap
- Returns `{date, open, high, low, close}` array
- Same fallback (open/high/low → close when ≤ 0)
- Correct placement after `fetchDailyClose`

### B-1 — `getMarketRegime` 3-tier — 95% ✅

All required behaviors present (lines 384–462):

| Element | Status |
|---|---|
| Cache check on `regimeLevel` | ✅ |
| 3-tier `regimeLevel` (0 Bull / 1 Neutral / 2 Bear) | ✅ |
| SMA20 vs SMA60 (mid-term trend) | ✅ |
| SMA5 vs SMA20 (uses `REGIME_SMA_FAST=5`) | ✅ |
| `gapSource` tracking ('today' vs 'yesterday') | ✅ |
| Today gap = open/yest_close − 1 | ✅ |
| Yesterday fallback = close/prev_close − 1 | ✅ |
| Bear (level=2) on SMA20 < SMA60 | ✅ |
| Neutral (level=1) on SMA5 < SMA20 | ✅ |
| Gap-down override → level=2 | ✅ |
| `downThreshold` var (REGIME_GAP_DOWN vs REGIME_YEST_DOWN) | ✅ improvement over design |
| Backward-compat `riskOn = regimeLevel < 2` | ✅ |
| Cache write with all fields | ✅ |
| Fallback `regimeLevel = 0` on error | ✅ |

Minor structural deviations (no behavioral impact):
- KOSPI/KOSDAQ gap branches merged into single block
- `ksYestChange`/`kqYestChange` named locals removed — values written directly to `ksGap`/`kqGap`

**Improvement over design**: `downThreshold` correctly uses `REGIME_YEST_DOWN` for the yesterday-fallback path (design code block only used `REGIME_GAP_DOWN`, which would have left `REGIME_YEST_DOWN` unused).

### D-1 — Entry blocking — 100% ✅

Lines 1531–1532 are byte-exact to design:
```javascript
if (regimeLevel >= 2 && grade !== '강매') return;
if (regimeLevel >= 1 && grade === '매도차익') return;
```
Correct placement: after `getMarketRegime` call, before `sizeFactor`.

### E-1 — REGIME-LOG — 90% ✅

| Element | Status |
|---|---|
| Once-per-day guard via `store.regimeLogSent` | ✅ |
| `📊` prefix | ✅ (hardcoded, same as C-1 note) |
| Telegram POST via `http()` | ✅ |
| Silent failure on error | ✅ |
| Placement after D-1 | ✅ |
| Level label with action description | ✅ enhanced |
| Trailing summary line as separate message part | ⚠️ merged into levelLabel |

---

## Match Rate Summary

| Item | Weight | Score | Weighted |
|---|---|---|---|
| C-1 Constants | 15% | 90% | 13.5 |
| A-1 fetchDailyOHLC | 15% | 100% | 15.0 |
| B-1 getMarketRegime | 35% | 95% | 33.25 |
| D-1 Entry blocking | 20% | 100% | 20.0 |
| E-1 REGIME-LOG | 15% | 90% | 13.5 |
| **Total** | **100%** | | **95.25%** |

---

## Gaps (Minor)

1. **`REGIME_LOG_EMOJI` constant not defined** — `'📊'` hardcoded at line 1539. Add `const REGIME_LOG_EMOJI = '📊';` after line 25.
2. **E-1 trailing summary line merged** into `levelLabel` rather than appended separately. Functionally equivalent.
3. **Design doc B-1 code block** doesn't show `downThreshold` logic — should be updated to reflect the implementation (which is actually correct).

---

## Conclusion

All 5 design items (C-1, A-1, B-1, D-1, E-1) are implemented and functionally correct. The `downThreshold` bug fix is an improvement over the design. Proceed to `/pdca report trailing-stop-regime-fix`.
