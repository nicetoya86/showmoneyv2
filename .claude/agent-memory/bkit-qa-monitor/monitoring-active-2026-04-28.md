---
name: Monitoring Status 2026-04-28
description: Current monitoring state and key metrics to track
type: project
---

# Active Monitoring Dashboard - 2026-04-28

## System Status
**Logger Infrastructure**: ✅ OPERATIONAL  
**Last Test**: 2026-04-23 (All 9 tests passed)  
**Current Phase**: Production Monitoring  
**Session Start**: 2026-04-28

## Key Metrics to Track

### 1. Logger Output Quality
```
Required Fields Check:
✅ timestamp (ISO 8601)
✅ level (DEBUG|INFO|WARNING|ERROR)
✅ service (scanner|monitor|reporter)
✅ request_id (trading_YYYYMMDDHHMMSS_SERVICE)
✅ message (human-readable)
⬜ data (optional, context-specific)
```

### 2. Hold Days Implementation Verification

**Expected Values (Post 2026-04-23 Fix)**:
```javascript
- 급등 (SURGE): HOLD_SURGE = 1 (당일단타)  [was 2 days]
- 강매 (STRONG): HOLD_STRONG = 5 days     [unchanged]
- 매도차익 (SHORT TRADE): 3 days           [was 2 days]
- 약매 (WEAK): HOLD_WEAK = default
```

Watch for in logs:
- `"grade":"급등"` should correlate with same-day sell (1-day hold)
- Verify hold days match constants in code

### 3. Grade Distribution Analysis

Monitor frequency of each grade:
- 급등 (Surge) - High momentum signals
- 강매 (Strong Buy) - Strong indicators
- 매도차익 (Short Trade) - Quick profit opportunities
- 기타 (Other) - Miscellaneous signals

Expected pattern: 급등 and 강매 should be relatively infrequent (5-15% of signals), rest other grades.

### 4. Error Rate Threshold

**Alert Triggers**:
- Any ERROR level log → Investigate immediately
- 3+ consecutive ERRORs on same operation → Critical
- Missing request_id in logs → Format violation
- Non-JSON entries in log file → Parsing failure

### 5. Performance Metrics

**Watch for**:
- Log write time: Should be < 1ms
- Request completion: Should be < 3000ms for normal operations
- Slow operations (> 1000ms): Worth noting, not critical

### 6. Request ID Propagation

For any new trading cycle, track:
```
Request started: trading_20260428HHMMSS_SCAN
  → Grade assignment
  → Position update (if applicable)
  → Log entry
Request completed: trading_20260428HHMMSS_SCAN
```

All logs with same request_id = single transaction

## Critical Success Factors

### Must Have:
1. ✅ Logger module loads without errors
2. ✅ JSON format is parseable (valid syntax)
3. ✅ All required fields present
4. ✅ Request IDs consistent within transaction
5. ✅ No ERROR logs during normal operation

### Should Have:
1. ✅ Timestamp progression (newer logs have later timestamps)
2. ✅ Grade distribution makes sense
3. ✅ Hold days match code constants
4. ✅ File I/O reliable (no lost logs)
5. ✅ Performance metrics healthy

### Nice to Have:
1. Debug logs for complex operations
2. Detailed error messages with codes
3. Performance metrics included
4. Grade calculation details

## Known Working Cases

From test 2026-04-23 (can use as baseline):

**Log Entry (INFO level)**:
```json
{
  "timestamp": "2026-04-22T15:21:52.842Z",
  "level": "INFO",
  "service": "qa_test_20260423",
  "request_id": "trading_20260422152152_TEST",
  "message": "QA Test - Info log",
  "data": {
    "test": "info",
    "value": 123
  }
}
```

**Characteristics**:
- Timestamp: ISO 8601 ✅
- Level: Valid enum ✅
- Service: Non-empty string ✅
- Request ID: Format trading_YYYYMMDDHHMMSS_SERVICE ✅
- Message: Descriptive ✅
- Data: Optional but structured ✅

## Quick Reference: What to Check

### When Monitoring Logs

1. **First Entry Rule**:
   - Should be logger initialization with REQUEST_ID
   - Should have timestamp in ISO format
   - Should be JSON parseable

2. **Per Entry Check**:
   - Level is one of: DEBUG, INFO, WARNING, ERROR
   - Service matches component (scanner, monitor, reporter)
   - Request ID format is consistent
   - Timestamp progresses (usually seconds/ms increase)

3. **Error Detection**:
   - Search for `"level":"ERROR"`
   - Extract request_id
   - Find all logs with that request_id
   - Build timeline of that transaction

4. **Grade Distribution**:
   - Extract all `"grade":"..."` entries
   - Count frequency by grade type
   - Compare to expected distribution

## Alert Checklist

###🔴 CRITICAL - Investigate Immediately
- [ ] ERROR level log found
- [ ] JSON parse fails
- [ ] Required field missing
- [ ] Status code 5xx (if HTTP)
- [ ] Duration > 3000ms
- [ ] 3+ consecutive failures

### 🟡 WARNING - Document & Review
- [ ] Duration > 1000ms
- [ ] Missing optional fields
- [ ] Unexpected grade distribution
- [ ] Hold days mismatch
- [ ] Status 401/403 (auth issue)

### 🟢 INFO - Track Pattern
- [ ] Grade distribution
- [ ] Average response time
- [ ] Request volume
- [ ] Unique request IDs
- [ ] Date range of operations

## Log File Locations

### Primary
- `logs/swing_scanner_*.log` - New trading signal logs
- `logs/Daily_Position_Monitor_*.log` - Position updates
- `logs/weekly_reporter_*.log` - Weekly reports

### Format
- Filename pattern: `{service}_{YYYY-MM-DD}.log`
- Content: One JSON object per line
- Encoding: UTF-8

## How to Monitor

### Option 1: Real-time Streaming
```bash
cd D:/vibecording/showmoneyv2
tail -f logs/*.log | jq . 2>/dev/null
```

### Option 2: Batch Analysis
```bash
# Check recent logs
cat logs/swing_scanner_*.log | jq '.level' | sort | uniq -c

# Extract errors
cat logs/*.log | jq 'select(.level == "ERROR")'

# Count by service
cat logs/*.log | jq -r '.service' | sort | uniq -c
```

### Option 3: Request ID Tracing
```bash
# Find all logs for a request
grep 'trading_20260428' logs/*.log | jq .
```

## Next Actions

1. **Verify Logger Works**:
   - Check that new log files are being created
   - Verify JSON format is valid
   - Confirm all fields present

2. **Track First Trading Cycle**:
   - Document request ID
   - Verify grade assignment
   - Check hold days value
   - Confirm position update logged

3. **Analyze Results**:
   - Calculate metrics
   - Identify any anomalies
   - Document findings

4. **Iterate**:
   - Monitor subsequent cycles
   - Look for patterns
   - Alert on anomalies

---

**Monitoring Status**: ACTIVE  
**Last Updated**: 2026-04-28  
**Ready for**: Live log analysis

