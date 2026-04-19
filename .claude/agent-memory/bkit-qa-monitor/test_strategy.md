---
name: Zero Script QA Test Strategy for showmoneyv2
description: QA testing approach using structured logs and real-time monitoring
type: project
---

## Test Cycle Overview

**Zero Script QA for showmoneyv2** validates the swing algorithm improvements without writing test scripts. Instead:

1. **Add JSON logging** to all trading components
2. **Run actual trading cycle** (or backtest with live logging)
3. **Monitor logs in real-time** for errors and anomalies
4. **Auto-detect issues** and document them immediately
5. **Fix and re-test** in iterative cycles

---

## Key Test Scenarios

### Scenario 1: Swing Algorithm Scoring Validation
**What to test**: The recent algorithm changes work correctly

| Change | Expected Behavior | Log Indicators |
|--------|------------------|-----------------|
| ATR_TARGET_MULT_NORMAL = 2.0 | Normal grade stocks get 2.0x multiplier | `"targetMult": 2.0, "grade": "normal"` |
| Forced Buy (강매) → 2.8x | Forced buy grade gets 2.8x multiplier | `"targetMult": 2.8, "grade": "강매"` |
| Short Trade (매도차익) → 1.5x | Short trade grade gets 1.5x multiplier | `"targetMult": 1.5, "grade": "매도차익"` |
| HOLD_SURGE 2→3 days | Surge positions held 3 days | `"holdDays": 3, "category": "surge"` |
| HOLD_SHORTTRADE 2→3 days | Short trade positions held 3 days | `"holdDays": 3, "category": "shorttrade"` |
| OBV Supply Check | Only buy if OBV trend = 1 OR RVOL >= A | `"hasSupply": true/false, "obvTrend": X, "rvolGrade": X` |
| High Proximity Score Down | pth 0.95 gets 15 (was 25), pth 0.90 gets 8 (was 15) | `"proximityScore": 15 or 8, "pth": 0.95 or 0.90` |

### Scenario 2: Position Lifecycle Tracking
**What to test**: Position flows from discovery to exit correctly

```
Scanner detects stock (req_id: trading_20260419_005930)
  → Logs: discovered, score, grade, target price
  → Monitor logs in real-time

Position Monitor picks it up
  → Logs: position created, entry price, hold period
  → Same req_id propagated through logs

Daily cycle N: check entry conditions
  → Logs: checking entry, price vs target, decision

Daily cycle M: position held
  → Logs: current position, P&L, days held remaining

Daily cycle Z: exit triggered
  → Logs: exit reason (target hit / stop loss / hold expired), exit price, P&L
```

**Monitoring**: All logs for `req_id: trading_20260419_005930` should tell coherent story

### Scenario 3: Day-of-Week Bonus Application
**What to test**: Day-of-week adjustments apply correctly

| Day | Expected Bonus | Log Check |
|-----|----------------|-----------|
| Thursday | +3 | `"dowAdj": 3, "dayOfWeek": "Thursday"` |
| Wednesday | +2 | `"dowAdj": 2, "dayOfWeek": "Wednesday"` |
| Friday | -5 | `"dowAdj": -5, "dayOfWeek": "Friday"` |
| Other days | 0 | `"dowAdj": 0` |

### Scenario 4: Error Conditions
**What to test**: System handles errors gracefully

| Error Condition | Expected Log | Action |
|-----------------|--------------|--------|
| API fetch fails | `"level": "ERROR", "message": "API call failed", "endpoint": "..."` | Skip stock, log error, continue |
| Invalid data | `"level": "WARNING", "issue": "missing field", "field": "..."` | Use default or skip |
| Calculation edge case | `"level": "DEBUG", "case": "edge", "values": {...}` | Verify correct handling |
| Position exists already | `"level": "WARNING", "message": "Position already exists"` | Merge or update |

---

## Iterative Test Cycle Pattern

Based on successful bkamp.ai notification feature testing:

```
Cycle 1: First run with logging
  - Enable JSON logging in all components
  - Run scanner + monitor for 1 day
  - Identify missing log points → PAUSE for fixes
  
Cycle 2-8: Iterative testing with fixes
  - Run full cycle (scanner → monitor → reporter)
  - Monitor logs in real-time
  - Detect issues immediately
  - Fix code → Hot reload
  - Rerun cycle
  - Document: Bug found → Root cause → Fix applied

Success Criteria: No ERROR level logs, all positions trace correctly
```

### Example: "Position not exiting on target" Bug Discovery

**Cycle N logs show**:
```json
{"request_id": "trading_20260419_005930", "message": "Position created", "entryPrice": 10000, "target": 10560}
{"request_id": "trading_20260419_005930", "message": "Current price", "currentPrice": 10600, "status": "held"}
{"request_id": "trading_20260419_005930", "message": "Current price", "currentPrice": 10700, "status": "held"}
// ... price keeps rising past target but position never exits
```

**Root cause analysis**:
- Check position monitoring logic in `Daily_Position_Monitor.js`
- Likely: target comparison using wrong symbol or missing decimal precision check
- Log shows issue immediately without manual test

**Fix**: Correct comparison logic → Redeploy → Cycle N+1

**Log proof of fix**:
```json
{"request_id": "trading_20260419_005930", "message": "Current price", "currentPrice": 10560, "status": "exiting", "reason": "target_hit"}
{"request_id": "trading_20260419_005930", "message": "Position closed", "exitPrice": 10560, "pnl": 560, "pnlPercent": 5.6}
```

---

## Log Patterns to Monitor

### Critical (Report Immediately)
```json
{"level": "ERROR"}                          // Any ERROR
{"data": {"status": 500}}                   // API errors
{"data": {"requestDuration_ms": 5000}}     // Timeouts
```

### Warning (Investigate Next)
```json
{"level": "WARNING"}                        // Warnings
{"message": ".*undefined.*"}               // Undefined values in scoring
{"message": ".*NaN.*"}                     // NaN in calculations
```

### Success Indicators
```json
{"message": "Position created", "grade": "강매"}      // Strong buy detected
{"message": "Target hit", "pnlPercent": 5.6}          // Profitable exit
{"message": "Hold expired", "days": 3}                // Correct hold period
```

---

## Expected Issues During Testing

Based on similar projects (bkamp.ai), likely issues:

1. **Type mismatches** — Grade strings not matching conditions (e.g., '강매' vs '강매 ')
2. **Null/undefined in calculations** — Missing data handling
3. **Off-by-one in hold period** — Day counting logic
4. **ATR multiplier not applying** — Conditional logic error
5. **Request ID not propagating** — Logs show different request IDs for same position
6. **Supply check too strict** — Blocking too many valid positions with new OBV requirement

---

## Success Criteria

**Cycle completes successfully when**:
- [ ] No ERROR level logs in scanner
- [ ] No ERROR level logs in position monitor
- [ ] No ERROR level logs in reporter
- [ ] All positions traced through with consistent request ID
- [ ] ATR multipliers match expected grades in logs
- [ ] Hold periods match expected durations
- [ ] Day-of-week bonuses apply correctly
- [ ] Supply requirement filters as expected
- [ ] Score adjustments for high proximity apply correctly
- [ ] Positions exit with proper reason (target/stop/expired)

**Pass rate target**: >90% of test positions should complete full lifecycle without errors

---

## How Claude Code Will Monitor

During test cycle:

```bash
# 1. Monitor logs in real-time
docker compose logs -f 2>&1 | tee test_logs.txt

# 2. Claude Code reads logs continuously:
# - Extracts JSON lines
# - Groups by request_id
# - Checks for patterns
# - Documents issues immediately

# 3. On error detection:
# - Alert user with log excerpt
# - Suggest root cause
# - Recommend fix
# - Test confirms fix works
```

---

## Next Steps

1. **When ready**: Implement JSON logging (Phase 1)
2. **First test run**: Execute with logging enabled
3. **Monitor actively**: Watch for patterns, issues
4. **Document findings**: Create issue cards for any gaps
5. **Iterate**: Fix → Re-test → Confirm
6. **Sign off**: Final report with 0 ERROR logs
