---
name: Issue Resolution Log
description: Completed issue fixes and their verification results
type: project
---

## Closed Issues

When issues are fixed during QA monitoring, they move here with verification details.

### Format

```markdown
## ISSUE-XXX: [Title] ✅ FIXED

**Request ID**: trading_YYYYMMDD_STOCKCODE
**Component**: swing_scanner / position_monitor / weekly_reporter
**Detected**: YYYY-MM-DD HH:MM
**Fixed**: YYYY-MM-DD HH:MM
**Duration**: X minutes to fix

### Problem
{Description of issue}

### Root Cause
{What was wrong in the code}

### Fix Applied
{Code change made}

**File**: path/to/file.js:line_number
\`\`\`javascript
// Before:
{old code}

// After:
{new code}
\`\`\`

### Verification
\`\`\`json
{Log output showing fix works}
\`\`\`

### Re-test Result
- **Cycle**: N+1
- **Duration**: X minutes
- **Outcome**: ✅ Pass
- **Notes**: No related issues in follow-up run
```

---

## Issue Statistics

| Metric | Count |
|--------|-------|
| Total Issues Found | 0 (pending test) |
| Critical (🔴) | 0 |
| Warnings (🟡) | 0 |
| Info (🟢) | 0 |
| **Resolved** | 0 |
| **Pass Rate** | N/A (pending test) |

---

## Notes on Fixing Issues

### Process During QA Monitoring

1. **Detection**: Claude Code identifies error/anomaly in logs
2. **Analysis**: Extract root cause from log evidence
3. **Communication**: Present issue to user with evidence
4. **Diagnosis**: User confirms/refines root cause analysis
5. **Fix**: User applies code fix (or Claude suggests specific change)
6. **Deployment**: Code reloaded/redeployed
7. **Verification**: Claude monitors next test cycle for same issue
8. **Documentation**: Issue moved here with all details

### Common Fix Categories

**Type Issues** (strings, numbers, types not matching)
- Example: `"강매"` vs `"강매 "` (trailing space)
- Fix: Normalize strings or fix comparison
- Test: Re-check grade assignment logic

**Calculation Issues** (off-by-one, rounding, precision)
- Example: Hold period counting 0-2 instead of 1-3
- Fix: Adjust counter logic
- Test: Log shows correct day count

**Logic Issues** (conditions not firing)
- Example: Supply check too strict, blocking valid entries
- Fix: Adjust condition threshold or logic
- Test: Re-check entries being created

**Data Issues** (null, undefined, missing fields)
- Example: RVOL data missing for some stocks
- Fix: Add null checks or default values
- Test: Verify handling gracefully

---

## Continuous Improvement Notes

### Patterns to Watch Across Multiple Test Cycles

As more cycles run, look for:
- **Recurring issues**: If same bug appears again, may be environmental
- **Edge cases**: Certain market conditions triggering new issues
- **Performance patterns**: Certain days slower than others
- **Data quality**: Specific data sources less reliable

### Learning Log

When closing issues, note:
- What kind of bug was it?
- How could testing have caught it earlier?
- Can this pattern be automated in the logger?
- What should monitoring watch for next time?

---

## Relationship to Plan/Design

All issues should be cross-referenced:
- **Plan Document**: `docs/01-plan/features/swing-algorithm-improvement.plan.md`
- **Design Document**: `docs/02-design/features/swing-algorithm-improvement.design.md`

If issue contradicts plan requirements → severity = Critical
If issue is enhancement beyond plan → severity = Info/Warning
