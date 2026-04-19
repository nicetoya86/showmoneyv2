---
name: Real-time Monitoring Patterns
description: Log patterns to watch during Zero Script QA monitoring
type: project
---

## Pattern Detection Strategy

During QA monitoring, Claude Code watches for:
1. **Error patterns** — Immediate alerts
2. **Anomaly patterns** — Slow or strange behavior
3. **Flow patterns** — Correct lifecycle progression
4. **Data patterns** — Unexpected values or distributions

---

## Critical Patterns (Stop and Alert)

### Pattern 1: ERROR Level Logs
```json
{"level": "ERROR"}
```
**Action**: Report immediately with context
**Threshold**: Any occurrence
**Example**: `{"level": "ERROR", "message": "Failed to fetch stock data"}`

### Pattern 2: API Failures
```json
{"data": {"status": 500}}
{"message": ".*connection.*timeout.*"}
{"message": ".*API.*failed.*"}
```
**Action**: Alert user, may affect test validity
**Threshold**: 3+ consecutive failures
**Note**: May be environmental (API rate limit, network)

### Pattern 3: Calculation Anomalies
```json
{"data": {"score": "NaN"}}
{"data": {"score": -999999}}
{"data": {"target": "undefined"}}
```
**Action**: Critical — logic error
**Threshold**: Any occurrence
**Example**: Score calculation returning NaN suggests null in math operation

### Pattern 4: Type Mismatches
```json
{"data": {"grade": "강매 "}}         // Trailing space
{"data": {"grade": ""}}              // Empty string
{"data": {"grade": null}}            // Null value
```
**Action**: May cause silent failures (grade check doesn't match)
**Threshold**: Any occurrence
**Test**: Try entering position with that grade

---

## Warning Patterns (Investigate Next)

### Pattern 1: Positions Not Exiting
```json
{"message": "Current price", "currentPrice": 10560, "target": 10560}
// ...multiple logs, same position, still held
```
**What's happening**: Price hit target but position not closing
**Likely cause**: Comparison logic error, threshold off
**Test**: Manually check position in position monitor

### Pattern 2: Unusual Hold Periods
```json
{"message": "Position created", "grade": "강매", "holdDays": 5}     // ✅ OK
{"message": "Position created", "grade": "surge", "holdDays": 2}     // ❌ Should be 3
```
**What's happening**: Hold period not matching expected
**Likely cause**: Grade-to-hold mapping incorrect
**Test**: Check if that grade's constant was updated

### Pattern 3: Supply Check Blocking Too Many
```json
{"message": "Position rejected", "reason": "!hasSupply", "obvTrend": 0, "rvolGrade": "B"}
// ... multiple stocks with same issue pattern
```
**What's happening**: OBV supply requirement too strict
**Likely cause**: RVOL grade thresholds or OBV trend logic
**Test**: Check current market OBV distribution

### Pattern 4: Score Oddities
```json
{"message": "Stock scored", "score": 45, "grade": "강매"}     // Low score for forced buy
{"message": "Stock scored", "score": 180, "grade": "normal"}  // Very high normal score
```
**What's happening**: Scores inconsistent with grades
**Likely cause**: Score calculation not aligned with grade logic
**Test**: Recalculate manually for that stock

### Pattern 5: Slow Processing
```json
{"message": "Stock evaluation", "duration_ms": 500}
{"message": "Stock evaluation", "duration_ms": 3200}      // Timeout range
```
**What's happening**: Processing taking too long
**Likely cause**: API call stuck, loop inefficiency
**Test**: Check which API call is slow

---

## Success Patterns (Green Light Indicators)

### Pattern 1: Stock Discovery Pipeline
```json
{"request_id": "trading_20260419_005930", "message": "Stock detected", "code": "005930", "score": 95, "grade": "강매"}
{"request_id": "trading_20260419_005930", "message": "Entry conditions met", "entryPrice": 10000, "target": 10560}
```
**Meaning**: Stock correctly identified and scored
**Next step**: Should create position

### Pattern 2: Position Lifecycle
```json
{"request_id": "trading_20260419_005930", "message": "Position created", "days": 0}
{"request_id": "trading_20260419_005930", "message": "Position held", "days": 1, "price": 10100}
{"request_id": "trading_20260419_005930", "message": "Position held", "days": 2, "price": 10300}
{"request_id": "trading_20260419_005930", "message": "Position held", "days": 3, "price": 10560}
{"request_id": "trading_20260419_005930", "message": "Position exited", "reason": "target_hit", "pnl": 560}
```
**Meaning**: Position followed complete lifecycle correctly
**Success indicators**:
- 3-day hold period respected (or 2 for shorttrade)
- Exit at target price
- Proper P&L calculation

### Pattern 3: Day-of-Week Bonus Application
```json
{"data": {"dayOfWeek": "Thursday", "baseScore": 92, "dowAdj": 3, "finalScore": 95}}
{"data": {"dayOfWeek": "Friday", "baseScore": 98, "dowAdj": -5, "finalScore": 93}}
```
**Meaning**: Day-of-week adjustments applying correctly
**Expected**: Thu +3, Wed +2, Fri -5, others +0

### Pattern 4: ATR Multiplier By Grade
```json
{"grade": "강매", "targetMult": 2.8}
{"grade": "매도차익", "targetMult": 1.5}
{"grade": "normal", "targetMult": 2.0}
```
**Meaning**: ATR targets calculated with correct multipliers
**Success**: Each grade has its multiplier

### Pattern 5: Supply/Demand Check
```json
{"obvTrend": 1, "rvolGrade": "A", "hasSupply": true}        // ✅ Both conditions
{"obvTrend": 0, "rvolGrade": "A", "hasSupply": true}        // ✅ RVOL A meets requirement
{"obvTrend": 0, "rvolGrade": "B", "hasSupply": false}       // ✅ Neither met, blocked
```
**Meaning**: OBV supply logic working correctly
**Success**: `hasSupply = (obvTrend===1) OR (rvolVal>=RVOL_GRADE_A)`

---

## Monitoring Dashboard (Conceptual)

During a test cycle, Claude Code should maintain:

```
Active Monitoring - Test Cycle #1
═══════════════════════════════════════════
Time: 2026-04-19 09:00 - 15:30

Stocks Processed: 247
  Passed filtering: 189 (76%)
  Rejected: 58 (24%)

Positions Created: 12
  Avg Score: 94.3
  Grade breakdown:
    - 강매: 8 (67%)
    - 매도차익: 3 (25%)
    - 급등: 1 (8%)

Errors: 0 ✅
Warnings: 2 (investigate)
Success Rate: 100% ✅

Most Recent 5 Logs:
  [14:52] Position held, stock 005930, day 2/3
  [14:45] Stock discovered, code 051910, score 87
  [14:30] Position created, target 10560
  [14:15] Warning: slow API response (2.3s)
  [14:10] Position exited, pnl +450
```

---

## Filter Rules for Logs

To reduce noise and focus on signal:

### Show Immediately
- `level === "ERROR"`
- `duration_ms > 3000`
- Score or grade changed unexpectedly
- New issue pattern detected

### Check Periodically (Every 100 logs or every 5 min)
- `level === "WARNING"`
- Supply check rejection rate
- Position exit success rate
- API success rate

### Archive/Summary Only
- `level === "DEBUG"`
- Individual stock evaluations (unless ERROR)
- Routine position holds

---

## How to Use This During Monitoring

1. **Start monitoring**:
   ```bash
   docker compose logs -f | tee test_logs_$(date +%s).txt
   ```

2. **Claude Code tracks**:
   - Reads logs continuously
   - Matches against these patterns
   - Alerts on critical patterns immediately
   - Summarizes findings periodically

3. **User can**:
   - React to alerts
   - Request pattern summary
   - Ask "Why did position X exit?"
   - Ask "Why was stock Y rejected?"

4. **Documentation**:
   - Issues automatically documented
   - Success metrics tracked
   - Report generated at cycle end
