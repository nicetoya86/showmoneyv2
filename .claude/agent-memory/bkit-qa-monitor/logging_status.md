---
name: Logging Infrastructure Status
description: Assessment of current logging setup and gaps for Zero Script QA
type: project
---

## Current State (2026-04-19)

### What We Have
- Multiple JavaScript files logging events
- Code review capability (git + code analysis)
- Structured plan/design/implementation documentation
- Daily execution logs (from cron jobs and manual runs)

### What We Need for Zero Script QA

#### 1. JSON Structured Logging
**Status**: NOT IMPLEMENTED
- Currently using plain `console.log()` statements
- Need to convert to JSON format with standard fields

**Required Fields**:
```json
{
  "timestamp": "ISO 8601 timestamp",
  "level": "DEBUG|INFO|WARNING|ERROR",
  "service": "swing_scanner|position_monitor|weekly_reporter",
  "request_id": "trading_flow_YYYYMMDD_HHmmss",
  "message": "Brief description",
  "data": {
    "additional": "context fields"
  }
}
```

#### 2. Request ID Propagation
**Status**: NOT IMPLEMENTED
- No mechanism to track a stock through entire trading lifecycle
- Cannot correlate logs across components

**Need**:
- Generate unique request ID when stock enters system (e.g., from scanner)
- Propagate through position monitoring → exit decision
- Include in all logs related to that position
- Format: `trading_YYYYMMDD_STOCKCODE` (e.g., `trading_20260419_005930`)

#### 3. Docker Compose Setup
**Status**: PARTIAL
- Local execution model (cron jobs on single machine)
- No docker-compose.yml yet
- Would need containers for:
  - API data sources
  - Scanner service
  - Position monitor
  - Reporter service

**Alternative**: Structured file-based logging that can be monitored directly

#### 4. Real-time Monitoring Hooks
**Status**: NOT IMPLEMENTED
- Need to log to files in JSON format
- Point Claude Code to monitor those logs during testing
- Real-time error detection

---

## Implementation Roadmap for Zero Script QA

### Phase 1: Add JSON Logging (Low Effort, High Value)
1. Create `lib/logger.js` with JSON formatting
2. Update main files to use new logger:
   - `swing_scanner_code.js`
   - `Daily_Position_Monitor.js`
   - `weekly_reporter_code.js`

### Phase 2: Add Request ID Tracking (Medium Effort)
1. Generate request ID at scanner entry point
2. Pass through position data structures
3. Include in all logs for a stock position

### Phase 3: Structured Monitoring (During Testing)
1. Point monitoring to log files
2. Real-time pattern detection
3. Auto-issue documentation

---

## Critical Logging Points

These locations MUST have structured logging for effective QA:

### Swing Scanner (`swing_scanner_code.js`)
```
✅ Stock evaluation start (code, grade candidate)
✅ Score calculation breakdown (score, grade, mult, target)
✅ Buy signal confirmation (final grade, ATR, price, target)
✅ Supply/demand check (OBV, RVOL, hasSupply)
✅ Filtering decisions (why rejected)
✅ Errors during fetch (API failures, data issues)
```

### Position Monitor (`Daily_Position_Monitor.js`)
```
✅ Position load (count, total size)
✅ Position evaluation (current price, P&L)
✅ Hold period check (days held, remaining)
✅ Exit signal (target hit, stop loss, hold expired)
✅ Position closure (exit price, P&L)
```

### Weekly Reporter (`weekly_reporter_code.js`)
```
✅ Report generation start
✅ Position summary compilation
✅ Win/loss calculation
✅ Report completion
```

---

## Log File Location Strategy

Recommend:
```
logs/
├── swing_scanner_YYYYMMDD.log      (JSON, real-time)
├── position_monitor_YYYYMMDD.log   (JSON, real-time)
├── weekly_reporter_YYYYMMDD.log    (JSON, real-time)
└── trading_errors_YYYYMMDD.log     (ERROR level only)
```

These can be:
1. Monitored by `docker compose logs -f` or file watcher
2. Analyzed in real-time by Claude Code
3. Parsed for automated issue detection
4. Archived for post-mortem analysis

---

## Next Steps

When user is ready to implement Zero Script QA:
1. Ask: "Ready to add JSON logging to showmoneyv2?"
2. Create logger module
3. Update main files to use it
4. Set up monitoring during next trading cycle
5. Monitor logs in real-time and auto-document issues
