---
name: QA Monitoring Session Guide - 2026-05-11
description: Real-time QA monitoring session guide with procedures and issue templates
type: reference
---

# QA Monitoring Session Guide - 2026-05-11

**Session Status**: ACTIVE  
**Start Time**: 2026-05-11 09:00 KST  
**Duration**: Continuous

---

## Quick Start

### Infrastructure Status Check
```bash
# Verify logs directory
ls -lah /d/vibecording/showmoneyv2/logs/

# Check for recent logs
ls -lt /d/vibecording/showmoneyv2/logs/ | head -5

# Verify logger module
cat /d/vibecording/showmoneyv2/lib/logger.js | head -30
```

### Start Real-time Monitoring
```bash
# Monitor all logs in real-time
tail -f /d/vibecording/showmoneyv2/logs/*.log

# In separate terminal - filter errors only
grep -f <(echo '"level":"ERROR"') /d/vibecording/showmoneyv2/logs/*.log

# Or use tail with grep
tail -f /d/vibecording/showmoneyv2/logs/*.log | grep '"level":"ERROR"'
```

---

## What to Monitor

### 1. Error Patterns
Look for logs with:
```
"level":"ERROR"
"level":"WARNING"
```

**Action on Detection**:
1. Extract `request_id` from log
2. Grep all logs with same `request_id`
3. Trace entire flow from start to error
4. Document issue with full context

### 2. Performance Issues
Look for:
```
"duration_ms":3000  (or higher)
```

**Action on Detection**:
1. Note the operation in message field
2. Check if >3000ms (CRITICAL) or 1000-3000ms (WARNING)
3. Identify which component (service field)
4. Document as performance issue

### 3. Grade Distribution
Look for logs containing:
```
"grade":"강매"
"grade":"급등"
"grade":"매도차익"
"grade":"기타"
```

**Expected Distribution**:
- 강매 (Strong Buy): 5-10%
- 급등 (Surge): 10-15%
- 매도차익 (Profit Taking): 20-30%
- 기타 (Other): 50-70%

### 4. Hold Days Implementation
Look for logs with hold/expiry information:
```
"hold_days":1
"hold":1
```

**Expected**: All intraday trades should have hold=1 day

### 5. Request ID Propagation
Check that same request_id appears across related logs:
```
trading_20260511090000_AAPL appears in:
- swing_scanner logs
- position_monitor logs (if applicable)
```

---

## Issue Documentation Template

When you find an issue, document it using this format:

```markdown
## ISSUE-{NUM}: {TITLE}

**Detection Time**: {timestamp}  
**Request ID**: {request_id}  
**Severity**: 🔴 CRITICAL / 🟡 WARNING / 🟢 INFO  
**Service**: {service name}

### Related Logs
```json
{paste the ERROR log entry here}
```

### Full Flow Trace
```
{paste all logs with same request_id}
```

### Analysis
{Describe what went wrong and why}

### Reproduction Path
1. {Step to reproduce}
2. {Step to reproduce}

### Recommended Fix
{Suggestion for fixing this issue}

### Files Affected
- `path/to/file.js:line`
```

---

## Common Issue Types and Detection

### Type 1: Grade Distribution Abnormality

**Detection**:
Count grades in logs and compare to expected range

**Issue Template**:
```
ISSUE-001: Abnormal Grade Distribution
- Strong Buy (강매) below 5% threshold
- Surge (급등) significantly higher than 15%
- Cause: Likely algorithm or filter issue
- Fix: Review scoring logic
```

### Type 2: Performance Degradation

**Detection**:
Multiple logs showing duration_ms > 1000ms

**Issue Template**:
```
ISSUE-002: Slow Trading Signal Detection
- Duration: 2500ms (expected: <500ms)
- Service: swing_scanner
- Cause: Database query slow, API timeout, or compute intensive
- Fix: Optimize query, add caching, or parallelize operations
```

### Type 3: Consecutive Failures

**Detection**:
3+ ERROR logs on same endpoint within short time frame

**Issue Template**:
```
ISSUE-003: Repeated Position Monitor Failures
- Error count: 5 consecutive in 2 minutes
- Error type: DB connection timeout
- Cause: Database unreachable or overloaded
- Fix: Check database connection, add retry logic
```

### Type 4: Request ID Missing

**Detection**:
Logs with `"request_id":"N/A"` or no request_id field

**Issue Template**:
```
ISSUE-004: Request ID Not Propagated
- Missing in: position_monitor service
- Impact: Cannot trace request through system
- Fix: Ensure request_id passed from caller
```

### Type 5: Hold Days Violation

**Detection**:
Hold days != 1 for intraday trades

**Issue Template**:
```
ISSUE-005: Hold Days Not 1 for Intraday Trade
- Trade: AAPL
- Hold days: 2 (expected: 1)
- Cause: Hold days constant not set correctly
- Fix: Update HOLD_STRONG, HOLD_NORMAL, HOLD_WEAK to 1
```

---

## Metrics Tracking

### Create a Simple Metrics Log

Track during session:
```
Time     | Errors | Warnings | Avg Duration | Grade Distribution    | Notes
---------|--------|----------|--------------|----------------------|-------
09:00    | 0      | 0        | 150ms        | 강:8% 급:12% 매:25%  | Normal
09:30    | 1      | 2        | 200ms        | 강:5% 급:10% 매:28%  | Error found
10:00    | 2      | 3        | 350ms        | 강:3% 급:8%  매:30%  | Grade issue
```

### Calculate Metrics
```bash
# Error count
grep '"level":"ERROR"' /d/vibecording/showmoneyv2/logs/*.log | wc -l

# Warning count
grep '"level":"WARNING"' /d/vibecording/showmoneyv2/logs/*.log | wc -l

# Average duration (in ms)
grep '"duration_ms"' /d/vibecording/showmoneyv2/logs/*.log | \
  jq '.data.duration_ms' | awk '{sum+=$1; count++} END {print sum/count}'

# Grade distribution
grep '"grade":' /d/vibecording/showmoneyv2/logs/*.log | \
  jq -r '.data.grade' | sort | uniq -c
```

---

## Action Plan by Severity

### 🔴 CRITICAL (Immediate Response)

When you detect:
- ERROR logs
- duration_ms > 3000ms
- 3+ consecutive failures

**Your Action**:
1. Document issue immediately
2. Identify root cause
3. Suggest fix
4. Mark for developer review

**Example**:
```
ISSUE-001: Trading Signal Generation Failed
- Time: 09:15 KST
- Service: swing_scanner
- Error: "DB connection timeout"
- Severity: CRITICAL
- Recommendation: Restart database service, increase timeout
```

### 🟡 WARNING (Track and Document)

When you detect:
- WARNING level logs
- duration_ms 1000-3000ms
- Unusual patterns (e.g., grade distribution skewed)

**Your Action**:
1. Document issue
2. Note pattern
3. Recommend investigation
4. Track for trend analysis

**Example**:
```
ISSUE-002: Slow Position Monitor
- Time: 09:30 KST
- Service: position_monitor
- Duration: 1800ms (threshold: 1000ms)
- Severity: WARNING
- Recommendation: Monitor for degradation, optimize if persists
```

### 🟢 INFO (Metrics Only)

Normal INFO logs - just track metrics

---

## Session Checklist

### Start of Session
- [ ] Read logger.js to confirm implementation
- [ ] Check logs directory exists and is writable
- [ ] Verify recent log files are present
- [ ] Start real-time tail of logs
- [ ] Prepare issue documentation

### During Session (Every 30 minutes)
- [ ] Sample recent logs
- [ ] Check for ERROR or WARNING levels
- [ ] Note any performance issues
- [ ] Track metrics (error count, avg duration)
- [ ] Watch for patterns

### Continuous Monitoring
- [ ] Monitor for critical errors
- [ ] Track request ID propagation
- [ ] Watch grade distribution
- [ ] Check hold days implementation
- [ ] Document any issues immediately

### End of Session
- [ ] Summarize all issues found
- [ ] Calculate final metrics
- [ ] Identify patterns
- [ ] Provide recommendations
- [ ] Archive session report

---

## Testing the Logger

### Generate Test Logs
```bash
# Navigate to project
cd /d/vibecording/showmoneyv2

# Run a test script (if available)
node test_logger.js

# Or create a quick test:
cat > test_monitoring.js << 'EOF'
const JsonLogger = require('./lib/logger');
const logger = new JsonLogger('test_monitoring');
const requestId = logger.generateRequestId('TEST');

logger.info('Test started', { test: 'monitoring' }, requestId);
logger.warning('Test warning', { severity: 'low' }, requestId);
logger.info('Test completed', { result: 'success' }, requestId);

console.log('Test logs written to: /d/vibecording/showmoneyv2/logs/');
EOF

node test_monitoring.js
```

### Verify Logs
```bash
# View new test logs
tail -20 /d/vibecording/showmoneyv2/logs/test_monitoring_*.log

# Validate JSON format
cat /d/vibecording/showmoneyv2/logs/test_monitoring_*.log | jq .
```

---

## Monitoring for Recent Changes

### Focus Areas (Based on Recent Commits)

#### 1. swing-quality-improvement (2026-05-09)
Look for:
- ETF filtering effectiveness
- Score penalties applied (-15 for ETFs)
- Minimum score enforcement (100 instead of 80)
- Individual stock inclusion working

Monitor logs for:
```json
"data": {
  "is_etf": true,
  "score_penalty": 15,
  "final_score": 85,
  "grade": "non_tradeable"
}
```

#### 2. Position Monitor Fixes (2026-04-29)
Look for:
- Position update successes without error
- Political theme filtering applied
- Position tracking logic working

Monitor logs for:
```json
"service": "position_monitor",
"message": "Position updated successfully",
"data": {
  "positions_updated": 5,
  "duration_ms": 234
}
```

#### 3. MACD/RSI Risk Filter (2026-04-19)
Look for:
- MACD signal generation
- RSI threshold compliance
- High-risk filter blocking

Monitor logs for:
```json
"data": {
  "rsi": 35,
  "macd": "negative",
  "risk_filter": "blocked",
  "reason": "RSI below minimum"
}
```

---

## Grep Commands for Quick Analysis

```bash
# Find all errors
grep '"level":"ERROR"' /d/vibecording/showmoneyv2/logs/*.log

# Find specific error type
grep '"message":".*failed"' /d/vibecording/showmoneyv2/logs/*.log

# Track specific request ID
grep 'trading_20260511' /d/vibecording/showmoneyv2/logs/*.log

# Find slow operations
grep '"duration_ms":[0-9]\{4,\}' /d/vibecording/showmoneyv2/logs/*.log

# Count logs by service
grep '"service":' /d/vibecording/showmoneyv2/logs/*.log | jq -r '.service' | sort | uniq -c

# Find warnings
grep '"level":"WARNING"' /d/vibecording/showmoneyv2/logs/*.log

# Check for N/A request IDs
grep '"request_id":"N/A"' /d/vibecording/showmoneyv2/logs/*.log
```

---

## Tips for Effective Monitoring

1. **Use Multiple Terminals**
   - Terminal 1: Real-time tail -f
   - Terminal 2: Grep for specific patterns
   - Terminal 3: Analysis and documentation

2. **Parse JSON Properly**
   ```bash
   cat /d/vibecording/showmoneyv2/logs/*.log | jq '.data'
   ```

3. **Track by Request ID**
   - Copy request_id from error log
   - Grep all logs with that request_id
   - Follow entire request flow

4. **Document Issues Immediately**
   - Don't wait for session end
   - Capture exact error messages
   - Note timestamps and duration

5. **Watch for Patterns**
   - Same error repeating?
   - Performance degrading over time?
   - Grade distribution shifting?

---

## Session End Report

At the end of the session, provide:

```markdown
# QA Monitoring Session Report - 2026-05-11

## Summary
- **Duration**: {start} to {end}
- **Total Logs**: {count}
- **Errors Found**: {count}
- **Warnings Found**: {count}

## Metrics
- **Average Response Time**: {Xms}
- **Error Rate**: {X%}
- **Grade Distribution**: 강:{X}% 급:{X}% 매:{X}% 기:{X}%
- **Hold Days Compliance**: {X%}

## Issues Found
{List all documented issues}

## Recommendations
{Suggest fixes and improvements}
```

---

**Monitoring Session Active**: 2026-05-11 09:00 KST  
**Status**: Ready for real-time analysis  
**Next Update**: As issues are discovered
