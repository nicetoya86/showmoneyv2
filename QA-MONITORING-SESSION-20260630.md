# Zero Script QA Monitoring - Session 2026-06-30

**Session Start**: 2026-06-30  
**Objective**: Real-time monitoring of recent algorithm updates  
**Status**: ACTIVE MONITORING

---

## Quick Start Commands

### 1. Check Code Syntax
```bash
node -c swing_scanner_code.js
# Should output nothing if OK
```

### 2. Monitor Recent Changes
```bash
git log --oneline -5
git diff HEAD~3 HEAD
```

### 3. Check Last QA Results
```bash
cat cache/qa_Swing_Scanner.txt | head -50
cat cache/qa_Weekly_Reporter.txt | head -30
```

### 4. Monitor Log Directory
```bash
ls -ltr logs/
tail -f logs/*.log  # Real-time monitoring (if available)
```

---

## What We're Testing

### Recent Changes (Last 3 Commits)

#### 1. Fix: getPrevTradingDay Duplicate Declaration (TODAY - Commit 1754528)
**Status**: Code syntax verified ✅
**Change**: 
- Renamed `getNaverPrevDay()` to avoid conflict with `getPrevTradingDay()`
- `getPrevTradingDay(todayStr)` — remains for index gap calculation (line 396)
- `getNaverPrevDay()` — used for Naver API date (line 1107)

**What to verify**:
- [ ] No "Identifier getPrevTradingDay has already been declared" errors
- [ ] Swing scanner runs without declaration errors
- [ ] Both functions working correctly

#### 2. Feature: Extended Scan Times (Commit 938ebf3)
**Status**: Code review needed
**Change**: 스캔 시간 확장 09:00~13:00 (패턴C는 11:30 유지)
- Expanded scan window from original
- Pattern C maintains 11:30 cutoff

**What to verify**:
- [ ] Scan starts at 09:00
- [ ] Scan continues until 13:00
- [ ] Pattern C still stops at 11:30
- [ ] No duplicate entries from extended window

#### 3. Feature: Algorithm v1.0 (Commit 4ffbea2)
**Status**: Implementation complete
**Change**: algo-v1.0 — 30종목 복기 기반 진입 신호 + 파라미터 확정
- New entry signal logic based on 30-stock backtesting
- Parameters finalized

**What to verify**:
- [ ] Entry signals accurate and not spam
- [ ] Position grades (A/B/C) distributed correctly
- [ ] No false positive alerts

---

## Monitoring Metrics

### Performance Targets (From Previous QA - 2026-06-03)

| Metric | Target | Status |
|--------|--------|--------|
| Single stock analysis | <1000ms | ✅ Baseline 450ms |
| 30-stock batch | <30s | ✅ Baseline 13.5s |
| Risk update | <5s | ✅ Baseline 3s |
| Overall error rate | 0% | ✅ Baseline 0% |
| Success rate | >90% | ✅ Baseline 100% |

### Quality Targets

| Check | Target | Status |
|-------|--------|--------|
| Syntax errors | 0 | ✅ VERIFIED |
| Runtime errors | 0 | TBD |
| Logic errors | 0 | TBD |
| Documentation | Complete | ✅ Updated |
| Test coverage | >90% | ✅ From 2026-06-03 |

---

## Monitoring Checklist

### Phase 1: Pre-Execution Verification
- [x] Code syntax verified (node -c check)
- [ ] N8N workflows updated with latest code
- [ ] logs/ directory accessible
- [ ] Cache files readable
- [ ] Memory files updated

### Phase 2: Real-time Monitoring (During Execution)

**Watch for these patterns**:

1. **Error Detection**
   ```
   Look for: "Error", "failed", "undefined", "null", "cannot read"
   Action: Document with timestamp and context
   ```

2. **Performance Issues**
   ```
   Look for: Execution times > 1000ms for single stock, > 30s for batch
   Action: Log duration and identify bottleneck
   ```

3. **Logic Issues**
   ```
   Look for: Scores outside 0-100 range, grades not A/B/C, gaps in dates
   Action: Trace back to algorithm change
   ```

4. **Spam Detection**
   ```
   Look for: >5 alerts per day for same stock, same alert repeatedly
   Action: Check algorithm v1.0 entry signal logic
   ```

### Phase 3: Analysis & Documentation
- [ ] Review all monitoring data
- [ ] Document any issues found
- [ ] Compare performance vs 2026-06-03 baseline
- [ ] Prepare recommendations

---

## Issue Tracking Format

When you find an issue, use this format:

```markdown
## ISSUE-001: [Brief Title]

**Component**: swing_scanner / position_monitor / weekly_reporter
**Severity**: 🔴 Critical / 🟡 Warning / 🟢 Info
**Detected**: 2026-06-30 HH:MM
**Commit**: 1754528 / 938ebf3 / 4ffbea2
**Status**: Open

### Evidence
```
[Log output, error message, or screenshot]
```

### Root Cause Analysis
[What is happening and why]

### Reproduction Steps
1. [Step 1]
2. [Step 2]

### Expected vs Actual
- Expected: [What should happen]
- Actual: [What is happening]

### Recommended Fix
[Suggested solution]

### Verification Plan
After fix applied, verify with:
[Testing steps]
```

---

## Key Files to Monitor

### Code Files
- `swing_scanner_code.js` — Main algorithm (most changed)
- `cache/qa_Swing_Scanner.txt` — Latest test results
- `autostock_showmoneyv2_20260603_algo_v1_send3_time1300.json` — Latest workflow

### Log Files
- `logs/*.log` — Any new log files created
- `cache/qa_*.txt` — Test result cache

### Documentation
- `.claude/agent-memory/bkit-qa-monitor/` — Session tracking

---

## Success Criteria

This monitoring session will be considered **SUCCESSFUL** if:

1. ✅ **No new errors** introduced by duplicate declaration fix
2. ✅ **Extended scan times** work correctly (09:00-13:00)
3. ✅ **Algorithm v1.0** produces high-quality entry signals
4. ✅ **Performance** remains within targets
5. ✅ **Error rate** stays at 0%

---

## Escalation Paths

### If Critical Error Found
1. Document issue with full context
2. Identify affected commit
3. Recommend rollback or hotfix
4. Request code review

### If Performance Degradation Found
1. Measure impact severity
2. Identify bottleneck
3. Compare vs baseline (2026-06-03)
4. Recommend optimization

### If Logic Error Found
1. Verify with multiple test cases
2. Check recent algorithm changes
3. Review backtesting data
4. Request logic review

---

## Session Timeline

| Phase | Est. Start | Est. Duration | Deliverable |
|-------|-----------|---------------|-------------|
| **Pre-Exec** | Now | 30 min | Checklist complete |
| **Monitoring** | When user runs workflow | 1-2 hrs | Live issue detection |
| **Analysis** | After execution | 30 min | Issue log |
| **Report** | Final | 30 min | QA session report |

---

## How to Use This Document

1. **Before Testing**: Review "What We're Testing" section
2. **During Testing**: Use "Monitoring Checklist" to track progress
3. **When Issues Found**: Use "Issue Tracking Format" to document
4. **After Testing**: Compare results vs "Success Criteria"

---

## Related Documents

- **Latest QA Results**: `QA-INDEX-20260603.md` (baseline for comparison)
- **Monitoring Guide**: `MONITORING-GUIDE.md` (general procedures)
- **Session Memory**: `.claude/agent-memory/bkit-qa-monitor/qa-session-20260630-start.md`

---

## Notes

- **N8N Execution**: Since this is N8N-based, actual monitoring depends on workflow runs
- **Log Format**: All logging should be in JSON format (as per infrastructure)
- **Baseline**: Compare all metrics against 2026-06-03 results (100% pass rate)
- **Focus Areas**: Duplicate declaration fix validation is highest priority

