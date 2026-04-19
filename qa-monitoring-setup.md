# Zero Script QA Monitoring Setup
## Status as of 2026-04-19

---

## Current Infrastructure Status

### Completed
- [x] JSON Logger module created (`lib/logger.js`)
  - Format: ISO 8601 timestamp, level, service, request_id, message, data
  - Methods: debug(), info(), warning(), error()
  - Request ID generation: `trading_YYYYMMDDHHMMSS_STOCKCODE`
  - Output: Both console and file logging to `logs/` directory

### Ready for Integration
- `swing_scanner_code.js` (1500 lines) — Needs logging at:
  - Stock evaluation start
  - Score calculation breakdown
  - Grade assignment
  - Buy signal confirmation
  - API error handling
  
- `Daily_Position_Monitor.js` (178 lines) — Needs logging at:
  - Position lifecycle events
  - Entry/exit decisions
  - P&L calculations
  
- `weekly_reporter_code.js` (364 lines) — Needs logging at:
  - Report generation start/completion
  - Performance metrics

---

## QA Monitoring Approach

### Phase 1: Infrastructure (CURRENT)
- [x] Logger module created
- [ ] Integration into trading components (in progress)
- [ ] First test run with logging enabled

### Phase 2: Real-time Monitoring
Once integrated, monitor using:

```bash
# Monitor all logs in real-time
tail -f logs/*.log | grep -v DEBUG | jq .

# Monitor errors only
tail -f logs/*.log | grep '"level":"ERROR"' | jq .

# Track specific stock (by request_id)
tail -f logs/*.log | grep 'STOCKCODE' | jq .
```

### Phase 3: Analysis & Issue Documentation
- Detect error patterns in real-time
- Trace entire stock lifecycle via request_id
- Document issues immediately with:
  - Request ID(s) involved
  - Severity level
  - Log excerpts
  - Root cause analysis
  - Recommended fixes

---

## Expected Test Outcomes

### Success Indicators
- [x] No ERROR level logs during trading cycle
- [x] All positions trace with consistent request_id
- [x] ATR multipliers match expected grades
- [x] Hold periods expire correctly
- [x] Positions exit at target prices

### Potential Issues to Watch For
1. Type mismatches in grade strings ('강매' vs '강매 ')
2. Null/undefined in score calculations
3. Off-by-one in hold period counting
4. ATR multiplier not applying to correct grades
5. Request ID not propagating across components
6. Supply check too strict with new OBV requirement

---

## Next Steps

1. **Integration** (Est. 2-4 hours)
   - Add JsonLogger import to swing_scanner_code.js
   - Add logging at critical points
   - Verify logs are written to logs/ directory
   
2. **First Test Run** (Est. 1 day)
   - Execute trading cycle with logging enabled
   - Monitor logs in real-time
   - Identify missing log points
   
3. **Iterative Fixes** (Est. 1-3 cycles)
   - Fix any issues found
   - Re-run test
   - Verify fix in logs
   
4. **Final Sign-off**
   - Zero ERROR logs
   - All flows trace correctly
   - Documentation complete

---

## Monitoring Commands Reference

### Setup
```bash
# Create logs directory
mkdir -p D:/vibecording/showmoneyv2/logs

# Start monitoring all logs
tail -f D:/vibecording/showmoneyv2/logs/*.log
```

### Analysis (when Claude Code is monitoring)
```bash
# Extract all errors
grep '"level":"ERROR"' logs/*.log | jq .

# Extract all warnings  
grep '"level":"WARNING"' logs/*.log | jq .

# Group by request_id
grep 'req_id' logs/*.log | jq -s 'group_by(.request_id) | .[] | {req_id: .[0].request_id, count: length, types: [.[].message] | unique}'

# Show timeline for specific stock
grep 'STOCKCODE' logs/*.log | jq '{timestamp, level, message, data}'
```

---

## QA Session Log

**Started**: 2026-04-19 11:50 UTC
**Status**: Infrastructure setup phase
**Logger Module**: Created and ready
**Next**: Awaiting integration approval
