# Zero Script QA Monitoring Checklist - 2026-06-30

**Session Date**: 2026-06-30
**Scope**: Post-recent commits validation
**Status**: ACTIVE

---

## Phase 1: Pre-Execution Setup (Complete)

### Code Quality Checks
- [x] Code syntax verified (`node -c swing_scanner_code.js`)
- [x] No duplicate identifier errors
- [x] All recent commits reviewed
- [x] Changes documented and analyzed

### Infrastructure Checks
- [x] Logs directory accessible (`logs/`)
- [x] Cache directory writable (`cache/`)
- [x] Memory system configured (`.claude/agent-memory/`)
- [x] Monitoring documents created

### Documentation Checks
- [x] Session start document created
- [x] Monitoring guide prepared
- [x] Code analysis completed
- [x] This checklist created

---

## Phase 2: Execution Monitoring (User Action Required)

### When Running Swing Scanner Workflow

#### Step 1: Monitor for Errors
```
WATCH FOR:
❌ "Identifier getPrevTradingDay has already been declared"
❌ "Cannot read property of undefined"
❌ TypeError or SyntaxError messages
❌ N8N runtime errors

IF FOUND:
→ Note timestamp and exact message
→ Screenshot or copy error text
→ Document in QA session report
```

#### Step 2: Verify Duplicate Declaration Fix
```
VERIFY:
✅ getPrevTradingDay(todayStr) called at line 396+ — with parameter
✅ getNaverPrevDay() called at line 1107+ — without parameter
✅ No duplicate identifier errors
✅ Previous trading day calculation correct

TEST METHOD:
1. Check N8N execution logs
2. Verify no errors in console
3. Confirm dates look correct in output
```

#### Step 3: Monitor Extended Scan Times (09:00~13:00)
```
VERIFY:
✅ Scans started by 09:00 KST
✅ Scans continue until 13:00 KST
✅ Pattern C still stops at 11:30 KST
✅ No alerts after 13:00 (unless from earlier processing)

MONITOR:
⏱️ Track actual scan times
📊 Count alerts by time of day
📈 Compare against previous days
```

#### Step 4: Validate Algorithm v1.0 Entry Signals
```
VERIFY:
✅ Entry scores in range 0-100
✅ Grades assigned as A/B/C (no gaps, no invalid grades)
✅ Score distribution looks reasonable
✅ Alert count reasonable (not excessive spam)

SAMPLE CHECKS:
- Score 95+ = Grade A? ✅
- Score 70-95 = Grade B? ✅
- Score 40-70 = Grade C? ✅
- Score <40 = No alert? ✅
```

#### Step 5: Track Performance Metrics
```
MEASURE:
⏱️ Single stock analysis time (target: <1000ms, baseline: 450ms)
⏱️ 30-stock batch time (target: <30s, baseline: 13.5s)
⏱️ Overall execution time
📊 Memory usage (if available)

THRESHOLD:
🟢 OK: Within ±10% of baseline
🟡 Warning: 10-20% slower than baseline
🔴 Critical: >20% slower or >1000ms for single stock
```

---

## Phase 3: Issue Detection & Documentation

### Template for Found Issues

When you find any issue, create a document like this:

```markdown
## ISSUE-XXX: [Brief Title]

**Component**: swing_scanner / position_monitor / weekly_reporter
**Severity**: 🔴 Critical / 🟡 Warning / 🟢 Info
**Detected**: 2026-06-30 HH:MM
**Affected Commit**: 1754528 / 938ebf3 / 4ffbea2
**Status**: Open

### Evidence
[Error message, log output, or screenshot]

### Root Cause
[Analysis of what went wrong]

### Steps to Reproduce
1. [Step 1]
2. [Step 2]

### Expected vs Actual
- Expected: [What should happen]
- Actual: [What is happening]

### Recommended Fix
[Suggested solution]

### Priority
[Why this matters]
```

### Common Issues to Watch For

**Issue Type 1: Identifier Errors**
```
Pattern: "Identifier X has already been declared"
Cause: Duplicate function names
Fix: Verify function naming fix applied
Status: Should NOT appear (already fixed)
```

**Issue Type 2: Extended Scan Spam**
```
Pattern: >10 alerts in 1 hour, same stock repeatedly
Cause: Algorithm v1.0 producing duplicate signals
Fix: Review entry signal logic
Status: Monitor and report if found
```

**Issue Type 3: Performance Degradation**
```
Pattern: Single stock >1500ms, batch >45s
Cause: Logic change or inefficient new code
Fix: Optimize bottleneck
Status: Alert if found
```

**Issue Type 4: Invalid Grades**
```
Pattern: Grades outside A/B/C, or gaps in distribution
Cause: Algorithm v1.0 logic error
Fix: Debug grading logic
Status: Alert if found
```

---

## Phase 4: Post-Execution Analysis

### Step 1: Collect All Data
- [ ] N8N execution logs (screenshot or export)
- [ ] Cache file updates (cache/qa_Swing_Scanner.txt)
- [ ] New log files (logs/*.log)
- [ ] Performance metrics (if available)
- [ ] Issue list (if any found)

### Step 2: Compare Against Baseline (2026-06-03)

**Baseline Metrics**:
```
Error Rate: 0%
Single Stock: 450ms
30-Stock Batch: 13.5s
Success Rate: 100%
Grade Distribution: A=20%, B=35%, C=45%
```

**Comparison Checklist**:
- [ ] Error rate still 0%? 
- [ ] Performance within ±10%?
- [ ] Success rate >90%?
- [ ] Grade distribution similar?
- [ ] No new issues detected?

### Step 3: Create Final Summary
```markdown
## QA Session Summary - 2026-06-30

**Date**: 2026-06-30
**Duration**: [X minutes]
**Issues Found**: [X]
**Tests Passed**: [X/X]

### Results vs Baseline
- Error Rate: 0% (PASS) / X% (FAIL)
- Performance: ±X% (PASS) / >20% (FAIL)
- Quality: Maintained (PASS) / Degraded (FAIL)

### Conclusion
✅ PRODUCTION READY / ⚠️ NEEDS FIXES / ❌ DO NOT DEPLOY

### Recommended Actions
1. [Action 1]
2. [Action 2]
```

---

## Monitoring Metrics Tracking

### Real-time Metrics Log

Create a table as you monitor:

| Time | Metric | Value | Status | Notes |
|------|--------|-------|--------|-------|
| 09:00 | Scan start | ✅ | OK | Scan began on time |
| 09:05 | First stock | 450ms | ✅ | Within baseline |
| 09:15 | Grade A count | 2 | ✅ | Reasonable |
| 10:00 | Batch 30 stock | 13.2s | ✅ | Within target |
| 11:00 | Pattern C stop | ✅ | OK | Stopped at 11:30 |
| 13:00 | Scan stop | ✅ | OK | Extended window verified |
| 14:00 | Summary | - | ✅ | All checks passed |

---

## Success/Failure Criteria

### PASS Criteria (All Must Be True)
- ✅ No "getPrevTradingDay duplicate" errors
- ✅ Extended scan times working (09:00-13:00)
- ✅ Algorithm v1.0 scores valid (0-100)
- ✅ Grades properly assigned (A/B/C only)
- ✅ Performance within ±10% of baseline
- ✅ Alert count reasonable (<50/day)
- ✅ Error rate = 0%

### CONDITIONAL PASS (Needs Review)
- ⚠️ Alert count increased 10-20% (expected from extended times)
- ⚠️ Performance ±10-20% of baseline (acceptable)
- ⚠️ One minor issue found and documented

### FAIL (Do Not Deploy)
- ❌ Duplicate declaration error occurring
- ❌ Invalid grades or scores
- ❌ Error rate >0%
- ❌ Performance >20% slower
- ❌ Spam alerts (>100/day)
- ❌ Critical logic error found

---

## Quick Reference Commands

### Check Current State
```bash
# Verify syntax
node -c swing_scanner_code.js

# Check recent changes
git diff HEAD~3 HEAD

# View latest test results
cat cache/qa_Swing_Scanner.txt | head -50

# Check logs
ls -ltr logs/
```

### During Monitoring
```bash
# Watch for new logs (if available)
tail -f logs/*.log

# Check workflow status
# (In N8N interface)

# Monitor performance
# (In N8N execution logs)
```

### After Monitoring
```bash
# Check for new cache files
ls -ltr cache/qa_*.txt | tail -5

# Review latest results
cat cache/qa_Swing_Scanner.txt

# Compare with baseline
diff cache/qa_Swing_Scanner.txt [previous_baseline]
```

---

## Document Locations

**Main Documents**:
- `QA-MONITORING-SESSION-20260630.md` ← User guide
- `QA-CODE-ANALYSIS-20260630.md` ← Code review
- `QA-CHECKLIST-20260630.md` ← This document

**Session Memory**:
- `.claude/agent-memory/bkit-qa-monitor/qa-session-20260630-start.md` ← Session tracking

**Reference**:
- `QA-INDEX-20260603.md` ← Previous session (baseline)
- `MONITORING-GUIDE.md` ← General procedures

**Cache**:
- `cache/qa_Swing_Scanner.txt` ← Latest test results
- `logs/` ← Log directory

---

## Escalation Matrix

### If You Find an Error During Monitoring

| Scenario | Severity | Action |
|----------|----------|--------|
| "getPrevTradingDay duplicate" error | 🔴 CRITICAL | Halt testing, investigate immediately |
| Algorithm produces invalid grades | 🔴 CRITICAL | Stop, rollback commit 4ffbea2 |
| Performance >20% degradation | 🔴 CRITICAL | Document, halt, investigate |
| Spam alerts (>100/day) | 🟡 WARNING | Document, continue monitoring |
| Performance ±10-20% | 🟡 WARNING | Note and continue monitoring |
| Extended scan stops before 13:00 | 🟡 WARNING | Investigate, document |
| Minor formatting issues | 🟢 INFO | Document for next iteration |

---

## Final Sign-Off

Once monitoring is complete, update this section:

```markdown
## Session Sign-Off

**Monitoring Completed**: [Date/Time]
**QA Engineer**: Claude Code
**Status**: ✅ COMPLETE

### Final Results
- Tests Executed: X/X
- Issues Found: X
- Critical Issues: X
- Pass/Fail: [PASS/FAIL]

### Recommendation
[Deploy/Review/Do Not Deploy]

### Next Steps
1. [Action 1]
2. [Action 2]
```

---

## Notes & Tips

1. **Document Everything** — Even "seems OK" observations help
2. **Use Timestamps** — Precise timing crucial for debugging
3. **Compare Baseline** — Always reference 2026-06-03 results
4. **Be Systematic** — Follow the checklist in order
5. **When In Doubt** — Ask for clarification, don't assume
6. **Take Breaks** — Monitoring is detail-intensive work
7. **Review Often** — Don't wait until end to analyze

---

**Checklist Version**: 1.0
**Created**: 2026-06-30
**Next Update**: After monitoring session complete

