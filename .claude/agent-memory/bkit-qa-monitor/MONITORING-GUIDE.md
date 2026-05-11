---
name: QA Monitoring Guide
description: Real-time monitoring procedures for showmoneyv2 trading system
type: project
---

# QA Monitoring Guide - Zero Script QA

## Quick Start

The showmoneyv2 trading system has integrated JSON logging via `lib/logger.js`. This guide explains how to monitor, analyze, and respond to logs in real-time.

## Key Monitoring Points

### 1. Log Stream Monitoring

**To view real-time logs**:
```bash
# Monitor all logs
cd D:/vibecording/showmoneyv2
tail -f logs/*.log

# Monitor specific service
tail -f logs/swing_scanner_*.log       # Trading signals
tail -f logs/Daily_Position_Monitor_*.log  # Position tracking
tail -f logs/weekly_reporter_*.log     # Weekly reports
```

**What to look for**:
- JSON format (should be parseable)
- Required fields present
- No ERROR level logs (during normal operation)
- Timestamps progressing forward

### 2. Log File Structure

Each service creates daily log files:
- **Naming**: `{service}_{YYYY-MM-DD}.log`
- **Location**: `logs/` directory
- **Format**: One JSON object per line
- **Content Type**: UTF-8 encoded text

**Example**:
```
logs/
├── swing_scanner_2026-04-28.log
├── Daily_Position_Monitor_2026-04-28.log
└── weekly_reporter_2026-04-28.log
```

### 3. JSON Log Format

**Standard structure**:
```json
{
  "timestamp": "2026-04-28T10:30:45.123Z",
  "level": "INFO",
  "service": "swing_scanner",
  "request_id": "trading_20260428103045_SCAN",
  "message": "Trading signal identified",
  "data": {
    "grade": "급등",
    "symbol": "000000",
    "hold_days": 1
  }
}
```

**Field meanings**:
- `timestamp` - When the event occurred (ISO 8601 format)
- `level` - Log severity (DEBUG, INFO, WARNING, ERROR)
- `service` - Which component generated the log
- `request_id` - Transaction identifier for tracing
- `message` - Human-readable description
- `data` - Context-specific information (optional)

## Real-time Monitoring Procedures

### Procedure 1: Check Logger Health

**When**: Each monitoring session start

**Steps**:
1. Verify logs directory exists
2. Check recent log files for new entries
3. Validate JSON format (try parsing with jq)
4. Check timestamps are recent

**Command**:
```bash
cd D:/vibecording/showmoneyv2
ls -lah logs/
head -5 logs/swing_scanner_*.log | jq . 2>&1 | head -20
```

**Expected output**:
- Recent log files (today's date)
- Valid JSON (no parse errors)
- Timestamps within last hour

**Alert if**:
- No new log files created (logger not running)
- JSON parse fails (corrupted format)
- Timestamps are stale (> 1 hour old)

### Procedure 2: Monitor for Errors

**When**: Continuous during trading hours

**Steps**:
1. Watch for ERROR level logs
2. Extract associated request_id
3. Trace entire transaction with that request_id
4. Document the error context

**Command**:
```bash
# Find all errors
cd D:/vibecording/showmoneyv2
grep '"level":"ERROR"' logs/*.log | head -10

# For a specific error, trace the request
REQUEST_ID="trading_20260428103045_SCAN"
grep "$REQUEST_ID" logs/*.log
```

**Expected behavior**:
- No ERROR logs during normal operation
- If ERROR occurs, should have clear context in data

**Alert if**:
- Multiple errors in quick succession
- Same error repeating
- Vague error message (no details)

### Procedure 3: Validate Grade Distribution

**When**: After each trading cycle (daily/weekly)

**Steps**:
1. Extract all grade values from logs
2. Count frequency by grade
3. Analyze for anomalies
4. Compare to baseline

**Command**:
```bash
# Count grades in last 24 hours
cd D:/vibecording/showmoneyv2
grep '"grade":"' logs/swing_scanner_*.log | grep -oP '"\K[^"]+(?=")' | sort | uniq -c
```

**Expected pattern**:
- 급등 (Surge): 5-15% of signals
- 강매 (Strong): 10-20% of signals
- 매도차익 (Short Trade): 20-30% of signals
- Others: Remaining percentage

**Alert if**:
- One grade dominates (> 70%)
- Expected grades missing completely
- Distribution inverts (e.g., 급등 > 50%)

### Procedure 4: Verify Hold Days

**When**: After grade assignment logged

**Steps**:
1. Find logs with grade assignments
2. Check associated hold_days value
3. Verify against code constants
4. Note any mismatches

**Code constants (expected)**:
```javascript
HOLD_SURGE = 1           // 급등 = 1 day (same-day sell)
HOLD_STRONG = 5          // 강매 = 5 days
HOLD_SHORTTRADE = 3      // 매도차익 = 3 days
HOLD_WEAK = [default]    // 약매 = default value
```

**Command**:
```bash
# Extract grade and hold_days
cd D:/vibecording/showmoneyv2
grep '"grade":"' logs/*.log | jq '.data | {grade, hold_days}'
```

**Expected output**:
- 급등 → hold_days: 1
- 강매 → hold_days: 5
- 매도차익 → hold_days: 3

**Alert if**:
- Hold days don't match expected
- Hold days missing from data
- Grade present but hold_days null

### Procedure 5: Track Request ID Flow

**When**: Analyzing a specific transaction

**Steps**:
1. Identify request_id from initial log
2. Find all logs with same request_id
3. Build timeline of transaction
4. Verify complete flow

**Command**:
```bash
# Example: trace request trading_20260428103045_SCAN
REQUEST_ID="trading_20260428103045_SCAN"
cd D:/vibecording/showmoneyv2
grep "$REQUEST_ID" logs/*.log | jq '.'
```

**Expected flow**:
1. Request started log (INFO)
2. Grade assignment logs
3. Position update log (if applicable)
4. Request completed log (INFO)

**Alert if**:
- Request ID not found in logs
- Partial flow (missing expected steps)
- Out-of-order timestamps

## Issue Analysis Process

### When You Find an ERROR

**Step 1: Extract Context**
```bash
# Find the error
grep '"level":"ERROR"' logs/*.log

# Get the request_id
ERROR_REQUEST_ID=$(grep '"level":"ERROR"' logs/*.log | jq -r '.request_id' | head -1)

# Trace the complete request
grep "$ERROR_REQUEST_ID" logs/*.log
```

**Step 2: Analyze**
- What was the operation? (check message field)
- When did it happen? (check timestamp)
- What was the context? (check data field)
- Was it preceded by warnings?

**Step 3: Document**
```
## ERROR FOUND

**Request ID**: {request_id}
**Time**: {timestamp}
**Message**: {error message}
**Context**: {data field}
**Preceding Logs**: {logs before error}

**Analysis**: [What happened]
**Impact**: [What it affects]
**Recommendation**: [How to fix]
```

**Step 4: Alert**
- If ERROR is NEW: Create new issue document
- If ERROR is RECURRING: Update existing issue
- If ERROR is CRITICAL: Escalate immediately

### When You Find a WARNING

**Similar to ERROR process but**:
- Not immediately critical
- Log for pattern analysis
- Escalate if recurring (3+ times)

### When You Find SLOW Performance

**Performance threshold**: > 1000ms

**Command**:
```bash
# Find slow operations
grep 'duration_ms' logs/*.log | jq 'select(.data.duration_ms > 1000)'
```

**Document**:
- Affected endpoint/operation
- Duration value
- Frequency
- Surrounding context

## Issue Documentation Template

When you identify an issue, document it with this structure:

```markdown
# ISSUE-{number}: {title}

**Request ID**: {request_id}  
**Severity**: CRITICAL|WARNING|INFO  
**Service**: {swing_scanner|position_monitor|reporter}  
**Time**: {timestamp}  
**Component**: {code location}  

## Reproduction
1. {step 1}
2. {step 2}
3. {step 3}

## Related Logs
```json
[Relevant log entries]
```
```

## Error Cause Analysis
[What went wrong and why]

## Impact
[How this affects trading/monitoring]

## Recommended Fix
[What to change and where]

## References
- Code file: {path}:{line_number}
- Previous issues: {links if any}
```

## Alert Decision Tree

Use this to decide what to do:

```
Is it an ERROR log?
├─ YES → Is it a known/recurring error?
│   ├─ YES → Document as recurring pattern
│   └─ NO → Document and investigate
└─ NO → Is it a WARNING log?
    ├─ YES → Note pattern
    │   └─ 3+ occurrences? → Escalate
    └─ NO → Is performance degraded?
        ├─ YES (> 1000ms) → Document performance issue
        └─ NO → Log for analysis
```

## Performance Baseline

From testing (2026-04-23):
- Log write: 0.0-0.002 ms per entry
- Average timestamp gap: 1-2 ms
- File I/O: Reliable and fast
- JSON stringify: No issues even with large data

**If slower than baseline**: Investigate external factors

## Daily Monitoring Checklist

### Start of Day
- [ ] Verify logs directory exists
- [ ] Check for logs from yesterday (should exist if system ran)
- [ ] Verify today's log files created
- [ ] Check timestamps are current

### During Trading Hours
- [ ] Monitor for ERROR logs (none expected)
- [ ] Track request throughput (how many requests per hour?)
- [ ] Spot check grade distribution
- [ ] Note any unusual patterns

### End of Day
- [ ] Count total requests processed
- [ ] Summarize grade distribution
- [ ] Document any issues found
- [ ] Note recommendations for next day

### Weekly Summary
- [ ] Aggregate all issues found
- [ ] Analyze patterns across week
- [ ] Calculate error rate
- [ ] Prepare report

## Quick Reference Commands

### View Recent Logs
```bash
cd D:/vibecording/showmoneyv2
tail -20 logs/swing_scanner_*.log | jq .
```

### Count Log Entries by Level
```bash
cd D:/vibecording/showmoneyv2
cat logs/*.log | jq '.level' | sort | uniq -c
```

### Find Errors
```bash
cd D:/vibecording/showmoneyv2
grep '"level":"ERROR"' logs/*.log
```

### List All Request IDs
```bash
cd D:/vibecording/showmoneyv2
cat logs/*.log | jq -r '.request_id' | sort -u
```

### Extract Grade Distribution
```bash
cd D:/vibecording/showmoneyv2
cat logs/*.log | jq '.data.grade' | sort | uniq -c
```

### Parse a Specific Request
```bash
REQUEST_ID="trading_20260428103045_SCAN"
cd D:/vibecording/showmoneyv2
grep "$REQUEST_ID" logs/*.log | jq '.'
```

## Troubleshooting

### "No logs being created"
**Check**:
1. Is logs/ directory writable?
2. Is logger module being required?
3. Check for permission errors in console

### "JSON parse fails"
**Check**:
1. Is file UTF-8 encoded?
2. Is each entry one complete line?
3. Are special characters escaped?

### "Request ID inconsistent"
**Check**:
1. Is request_id field present in all logs?
2. Does format match pattern?
3. Are multiple request IDs being used?

### "Missing log entries"
**Check**:
1. Is there a time gap?
2. Did system pause/crash?
3. Are expected operations running?

## Need to Add New Monitoring?

If you need to add new metrics:

1. **Add to logger.data**: Include in the data object
2. **Test format**: Ensure JSON parseable
3. **Document pattern**: Add to this guide
4. **Update checklist**: Add to daily procedures

## Current Monitoring Status

**As of 2026-04-28**:
- Logger infrastructure: ✅ Active
- Test suite: ✅ All passed (9/9)
- Hold days fix: ✅ Implemented (3 days for 급등/매도차익)
- Request tracking: ✅ Ready
- Alert system: ✅ Ready

**Ready for**: Real trading log analysis

