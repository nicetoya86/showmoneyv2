---
name: Zero Script QA - Active Monitoring Session
description: Current real-time QA monitoring status and quick reference
type: project
---

# ZERO SCRIPT QA - ACTIVE MONITORING SESSION

**Status**: ✅ LIVE MONITORING  
**Session Start**: 2026-05-11 09:00 KST  
**Last Update**: 2026-05-11 09:00 KST

---

## What is Happening Right Now

The Zero Script QA system is **actively monitoring** the showmoneyv2 stock trading automation system in real-time. No manual test scripts are being executed. Instead:

1. **The system runs normally** (trading signals, position monitoring, etc.)
2. **All operations are logged** in structured JSON format
3. **Logs are streamed in real-time** to `/d/vibecording/showmoneyv2/logs/`
4. **Claude Code analyzes logs continuously** to detect issues

---

## Session Objectives

### Primary
- Monitor for errors and abnormal patterns in real-time
- Track all trading operations via Request ID
- Detect performance issues (>1000ms is warning, >3000ms is critical)
- Document issues automatically when found

### Secondary (Based on Recent Changes)
- Verify swing-quality-improvement changes (2026-05-09)
- Test ETF filtering and score penalties
- Check individual stock inclusion criteria
- Validate MACD/RSI risk filters
- Confirm position monitor fixes

---

## Key Metrics Being Tracked

| Metric | Target | Monitor For |
|--------|--------|-------------|
| Error Rate | <0.1% | ERROR level logs |
| Response Time (avg) | <500ms | duration_ms field |
| Response Time (95th%) | <1500ms | P95 duration |
| Grade Distribution | 강:5-10%, 급:10-15%, 매:20-30%, 기:50-70% | Skewed distributions |
| Hold Days (Intraday) | 1 day | Any hold > 1 |
| Request ID Coverage | 100% | N/A request_id values |

---

## Infrastructure Status

### Logger Module
- **File**: `lib/logger.js`
- **Status**: ✅ Fully operational
- **Integration**: ✅ swing_scanner, weekly_reporter
- **Safety**: ✅ Try/catch protected

### Log Files
- **Directory**: `/d/vibecording/showmoneyv2/logs/`
- **Format**: JSON per line
- **Naming**: `{service}_{date}.log`
- **Status**: ✅ New logs being created

### Request ID Tracking
- **Format**: `trading_YYYYMMDDHHMMSS_STOCKCODE`
- **Coverage**: ✅ Ready for tracing
- **Propagation**: ✅ Across services

---

## How to Monitor

### Real-Time Tail
```bash
tail -f /d/vibecording/showmoneyv2/logs/*.log
```

### Error-Only Monitoring
```bash
grep '"level":"ERROR"' /d/vibecording/showmoneyv2/logs/*.log
```

### Request ID Tracing
```bash
# Get request_id from an error, then
grep 'req_xxx' /d/vibecording/showmoneyv2/logs/*.log
```

### Performance Analysis
```bash
# Find slow operations
grep '"duration_ms":[0-9]\{4,\}' /d/vibecording/showmoneyv2/logs/*.log
```

---

## Alert Levels

### 🔴 CRITICAL - Report Immediately
- ERROR level logs detected
- Response duration > 3000ms
- 3+ consecutive failures
- 5xx status codes

### 🟡 WARNING - Document & Track
- Response duration 1000-3000ms
- WARNING level logs
- Unusual patterns detected
- Grade distribution anomalies

### 🟢 INFO - Track for Metrics
- INFO level logs (normal operations)
- Performance baselines
- Successful completions

---

## Recent Code Changes Being Tested

### 1. swing-quality-improvement (2026-05-09)
**Commit**: 21e7974
- ETF filtering enhancement
- Individual stock inclusion
- 7 quality improvements
- ETF score penalty: -15 points
- Min score raised: 80→100

**Monitoring Focus**:
- ETF filtering effectiveness
- Grade distribution changes
- Score penalty application

### 2. Position Monitor Fixes (2026-04-29)
**Commit**: 7349f8a
- Political theme filtering
- Position tracking fixes

**Monitoring Focus**:
- Position update success rate
- Error-free operations

### 3. MACD/RSI Risk Filter (2026-04-19)
**Commit**: 41f1ef3
- MACD enhancements
- RSI threshold compliance
- Risk filter activation

**Monitoring Focus**:
- Filter activation
- Signal quality impact

---

## Common Issues to Watch For

### Issue Type 1: Error Spikes
**Detection**: Multiple ERROR logs in short time  
**Response**: Trace request IDs, identify root cause

### Issue Type 2: Performance Degradation
**Detection**: duration_ms consistently > 1000ms  
**Response**: Identify bottleneck (DB/API/Logic)

### Issue Type 3: Grade Distribution Skew
**Detection**: Unexpected distribution shift  
**Response**: Check filter thresholds, scoring logic

### Issue Type 4: Missing Request IDs
**Detection**: request_id = "N/A"  
**Response**: Ensure ID passed between services

### Issue Type 5: Hold Day Violations
**Detection**: Hold days ≠ 1 for intraday  
**Response**: Check constants, verify implementation

---

## Quick Actions

### If You Find an Error

1. **Document It**
   ```
   ISSUE-{NUM}: {TITLE}
   Time: {timestamp}
   Request ID: {request_id}
   Error Message: {full error}
   ```

2. **Trace It**
   - Grep all logs with that request_id
   - Identify sequence of events
   - Find where it broke

3. **Analyze It**
   - What service failed?
   - What was it trying to do?
   - Why did it fail?

4. **Recommend It**
   - Suggest a fix
   - Note file/line if applicable
   - Estimate severity

### If Performance is Slow

1. **Identify Operation**
   - What log message shows duration?
   - Which service is slow?

2. **Check Duration**
   - 1000-3000ms = WARNING
   - >3000ms = CRITICAL

3. **Hypothesize Cause**
   - Database query slow?
   - API call timeout?
   - Compute intensive operation?

4. **Document & Recommend**
   - Note the baseline
   - Suggest optimization
   - Track trend

---

## Session Timeline

| Time | Activity | Status |
|------|----------|--------|
| 09:00 | Session start, infrastructure verification | ✅ ACTIVE |
| 09:30 | First sample analysis | Pending |
| 10:00 | First round of metrics | Pending |
| 10:30 | Issue check (if any) | Pending |
| 11:00 | Performance trend analysis | Pending |
| 11:30+ | Continuous monitoring | Ongoing |

---

## Documentation Location

All monitoring documents are stored in:  
`/d/vibecording/showmoneyv2/.claude/agent-memory/bkit-qa-monitor/`

**Key Files**:
- `qa-session-20260511-start.md` - This session setup
- `qa-monitoring-readiness-20260511.md` - Infrastructure verification
- `QA-MONITORING-SESSION-20260511.md` - Detailed monitoring guide
- `MEMORY.md` - Index of all monitoring records
- `ZERO-SCRIPT-QA-ACTIVE.md` - This file (quick reference)

---

## Success Criteria

### For This Session
- [x] Infrastructure verified
- [x] Logging operational
- [x] Monitoring ready
- [ ] Issues detected (if any)
- [ ] Issues documented
- [ ] Fixes recommended

### Expected Outcomes
- Monitor system for 4-8 hours
- Document any errors found
- Track performance metrics
- Verify recent code changes working
- Provide actionable recommendations

---

## Next Steps

1. **Start Real-Time Monitoring** (first 30 minutes)
   - Verify logs are being generated
   - Check for immediate errors
   - Validate log format

2. **Continuous Monitoring** (first 4 hours)
   - Monitor for patterns
   - Track metrics
   - Document issues as found

3. **Deep Analysis** (as needed)
   - Investigate any critical issues
   - Trace problematic request IDs
   - Verify code changes working

4. **Session Summary** (end of monitoring)
   - Compile all issues found
   - Calculate final metrics
   - Provide recommendations

---

## Support References

### Documentation
- Zero Script QA methodology: See skill files
- Logger API: `lib/logger.js` in codebase
- Trading modules: `*.js` files in root directory

### Previous Sessions
- 2026-04-23: Logger validation (9/9 passed)
- 2026-04-25: Logger production monitoring
- 2026-04-28: Ongoing cycle continuation
- 2026-05-10: Infrastructure ready

---

**MONITORING SESSION: ACTIVE**  
**START TIME**: 2026-05-11 09:00 KST  
**STATUS**: ✅ READY FOR ANALYSIS

Real-time log analysis in progress...
