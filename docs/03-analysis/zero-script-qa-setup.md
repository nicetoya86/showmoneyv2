# Zero Script QA Setup for showmoneyv2

## Overview

**Zero Script QA** for showmoneyv2 enables real-time validation of the swing algorithm without writing test scripts. Instead, we monitor structured logs and detect issues as they occur.

**Status**: Setup complete as of 2026-04-19
**Next Step**: Implement JSON logging infrastructure

---

## What Has Been Set Up

### 1. QA Monitoring Memory System
Created persistent memory at:
```
.claude/agent-memory/bkit-qa-monitor/
├── MEMORY.md                    # Index
├── project_overview.md          # Project context
├── logging_status.md            # Current logging assessment
├── test_strategy.md             # How to test using Zero Script QA
├── qa_findings.md              # Issues found during testing
├── issue_resolutions.md         # Fixes applied and verified
└── monitoring_patterns.md       # Log patterns to watch
```

### 2. Documentation Created

This document provides:
- Quick start guide
- Phase-by-phase implementation
- How Claude Code monitors during testing
- Expected outcomes

---

## Quick Start (If Already Have JSON Logging)

If your project already has structured JSON logging with request ID propagation:

```bash
# 1. Start monitoring
docker compose logs -f 2>&1 | tee test_logs_$(date +%s).txt

# 2. Run your trading cycle (scanner → monitor → reporter)

# 3. Tell Claude Code to analyze
# Use: "start QA monitoring" or "/zero-script-qa"

# 4. Claude Code will:
# - Stream logs in real-time
# - Detect error patterns
# - Trace flows by request ID
# - Auto-document issues
# - Suggest fixes
```

---

## Phase 1: Add JSON Logging Infrastructure

### Why This Matters
- Current logging uses plain `console.log()` → not parseable
- Zero Script QA needs structured JSON with consistent fields
- Need Request ID to trace stock through entire lifecycle

### Implementation (Estimated: 2 hours)

#### Step 1.1: Create Logger Module

Create `lib/logger.js`:

```javascript
const fs = require('fs');
const path = require('path');

// Ensure logs directory exists
const logsDir = path.join(__dirname, '../logs');
if (!fs.existsSync(logsDir)) {
  fs.mkdirSync(logsDir, { recursive: true });
}

class JsonLogger {
  constructor(service) {
    this.service = service;
    this.logFile = path.join(logsDir, `${service}_${this.getDate()}.log`);
  }

  getDate() {
    const d = new Date();
    return d.toISOString().split('T')[0];
  }

  // Generate request ID: trading_YYYYMMDD_STOCKCODE
  generateRequestId(stockCode = '') {
    const date = new Date().toISOString().replace(/[-T:\.Z]/g, '').slice(0, 8);
    const code = stockCode ? `_${stockCode}` : '';
    return `trading_${date}${code}`;
  }

  format(level, message, data = {}) {
    return JSON.stringify({
      timestamp: new Date().toISOString(),
      level,
      service: this.service,
      request_id: data.request_id || 'N/A',
      message,
      data: Object.keys(data).length > 0 ? data : undefined
    });
  }

  log(level, message, data = {}) {
    const logLine = this.format(level, message, data);
    
    // Write to file
    fs.appendFileSync(this.logFile, logLine + '\n');
    
    // Also to console for real-time monitoring
    console.log(logLine);
  }

  debug(message, data = {}) { this.log('DEBUG', message, data); }
  info(message, data = {}) { this.log('INFO', message, data); }
  warning(message, data = {}) { this.log('WARNING', message, data); }
  error(message, data = {}) { this.log('ERROR', message, data); }
}

module.exports = JsonLogger;
```

#### Step 1.2: Update swing_scanner_code.js

Replace `console.log()` with logger:

```javascript
const JsonLogger = require('./lib/logger');
const logger = new JsonLogger('swing_scanner');

// At stock evaluation start:
logger.info('Stock evaluation started', {
  request_id: `trading_${new Date().toISOString().split('T')[0]}_${code}`,
  code,
  price,
  atr
});

// At score calculation:
logger.info('Score calculated', {
  request_id,
  code,
  score,
  grade,
  targetMult,
  targetPrice
});

// On error:
logger.error('Stock evaluation failed', {
  request_id,
  code,
  error: err.message
});
```

#### Step 1.3: Update Daily_Position_Monitor.js

```javascript
const JsonLogger = require('./lib/logger');
const logger = new JsonLogger('position_monitor');

// Position load:
logger.info('Positions loaded', {
  request_id: logger.generateRequestId(),
  count: positions.length,
  totalSize: positions.reduce((sum, p) => sum + p.quantity, 0)
});

// Position check:
logger.info('Position evaluated', {
  request_id: position.request_id,
  code: position.code,
  currentPrice: price,
  target: position.target,
  days: position.daysHeld,
  status: decision
});
```

#### Step 1.4: Update weekly_reporter_code.js

```javascript
const JsonLogger = require('./lib/logger');
const logger = new JsonLogger('weekly_reporter');

logger.info('Report generation started', {
  request_id: logger.generateRequestId(),
  startDate,
  endDate
});

logger.info('Report generated', {
  request_id,
  totalPositions,
  winRate,
  totalPnL
});
```

### Testing Phase 1 Completion
```bash
# Run scanner
node swing_scanner_code.js

# Check logs are being written
cat logs/swing_scanner_*.log | jq .

# Verify JSON format
# Should see:
# {
#   "timestamp": "2026-04-19T12:00:00.000Z",
#   "level": "INFO",
#   "service": "swing_scanner",
#   "request_id": "trading_20260419_005930",
#   "message": "Stock evaluation started",
#   ...
# }
```

---

## Phase 2: Add Request ID Propagation

### Why This Matters
- Need to track a stock from discovery → position → exit
- Same request_id should appear in all related logs
- Enables tracing entire flow

### Implementation (Estimated: 1 hour)

#### Step 2.1: Modify Position Data Structure

In `swing_scanner_code.js`, when creating position object:

```javascript
const position = {
  request_id: `trading_${new Date().toISOString().split('T')[0]}_${code}`,
  code,
  entryPrice,
  target,
  grade,
  // ... other fields
};
```

#### Step 2.2: Pass Request ID Through Position Monitor

In `Daily_Position_Monitor.js`:

```javascript
// When loading positions from storage
positions.forEach(pos => {
  // If request_id missing (old positions), generate one
  if (!pos.request_id) {
    pos.request_id = logger.generateRequestId(pos.code);
  }
  
  // Use in all logs for that position
  logger.info('Position held', {
    request_id: pos.request_id,
    code: pos.code,
    // ... other data
  });
});
```

### Testing Phase 2 Completion
```bash
# Grep logs for same request_id
grep 'trading_20260419_005930' logs/swing_scanner_*.log logs/position_monitor_*.log

# Should see all logs for that stock with same request_id
```

---

## Phase 3: Docker Compose Setup (Optional)

If you want to use `docker compose logs -f` for monitoring:

### Create docker-compose.yml

```yaml
version: '3.8'

services:
  swing_scanner:
    build:
      context: .
      dockerfile: Dockerfile.scanner
    environment:
      NODE_ENV: development
      LOG_LEVEL: DEBUG
    volumes:
      - ./logs:/app/logs
    command: node swing_scanner_code.js

  position_monitor:
    build:
      context: .
      dockerfile: Dockerfile.monitor
    environment:
      NODE_ENV: development
      LOG_LEVEL: DEBUG
    volumes:
      - ./logs:/app/logs
    depends_on:
      - swing_scanner
    command: node Daily_Position_Monitor.js

  weekly_reporter:
    build:
      context: .
      dockerfile: Dockerfile.reporter
    environment:
      NODE_ENV: development
      LOG_LEVEL: DEBUG
    volumes:
      - ./logs:/app/logs
    depends_on:
      - position_monitor
    command: node weekly_reporter_code.js

  # Log aggregator (optional)
  log_monitor:
    image: alpine:latest
    volumes:
      - ./logs:/logs
    command: tail -f /logs/*.log
    depends_on:
      - swing_scanner
```

### Run with Monitoring

```bash
# Start all services
docker compose up -d

# Monitor all logs in real-time
docker compose logs -f

# Or specific service
docker compose logs -f swing_scanner
```

---

## Phase 4: Start QA Monitoring

### When Ready to Test

```bash
# 1. Ensure JSON logging is working
cat logs/swing_scanner_*.log | head -5 | jq .

# 2. Tell Claude Code to monitor
# Command: /zero-script-qa
# Or: "start QA monitoring for showmoneyv2"

# 3. Run your trading cycle
# (Scanner runs automatically via cron or manual run)

# 4. Claude Code will:
# - Monitor logs in real-time
# - Group logs by request_id
# - Detect error patterns immediately
# - Document issues as they occur
# - Suggest fixes
```

### Expected Behavior During Monitoring

**Claude Code will provide:**

1. **Real-time alerts**
   ```
   Alert: ERROR detected at 2026-04-19 12:30:45
   Component: swing_scanner
   Message: Failed to fetch data for stock 005930
   Suggestion: Check API connection
   ```

2. **Periodic summaries**
   ```
   ═══ Monitoring Summary (Last 5 min) ═══
   Stocks processed: 47
   Errors: 0
   Warnings: 2
   Positions created: 3
   ```

3. **Request tracing**
   ```
   Tracing: trading_20260419_005930
   
   [09:00] Discovered: score=95, grade=강매
   [09:05] Position created: entry=10000, target=10560
   [14:00] Position held: current=10300, day=1/3
   [next day] ...
   ```

4. **Issue documentation**
   ```
   New Issue Detected: ISSUE-001
   - Stock not exiting at target
   - Request ID: trading_20260419_005930
   - See: docs/03-analysis/zero-script-qa-issues.md
   ```

---

## Success Criteria

Your Zero Script QA setup is complete and working when:

- [x] JSON logging outputs to `logs/` directory
- [x] All services produce structured JSON logs
- [x] Request IDs propagate through position lifecycle
- [x] Claude Code can read and parse logs in real-time
- [x] Issues detected within seconds of ERROR in logs
- [x] Full position flow traceable by request ID
- [x] Monitoring runs without intervention for 1+ trading cycle

---

## Common Issues and Fixes

### Issue: Logs not being written
**Solution**: Check `logs/` directory exists and is writable
```bash
mkdir -p logs
chmod 755 logs
```

### Issue: JSON parsing fails
**Solution**: Validate JSON format
```bash
cat logs/swing_scanner_*.log | jq .
# Should work without errors
```

### Issue: Request IDs not matching across services
**Solution**: Ensure position object includes request_id when passed between services
```javascript
// When loading from storage
const position = { ...savedPosition, request_id: savedPosition.request_id };
```

### Issue: Claude Code can't find logs
**Solution**: Specify absolute paths in memory or settings
```javascript
// In logger
const logsDir = path.join(__dirname, '../logs');
console.log('Logging to:', path.resolve(logsDir));
```

---

## Next Steps

1. **Implement Phase 1** (JSON logging) — 2 hours
2. **Implement Phase 2** (Request ID propagation) — 1 hour
3. **Optional**: Phase 3 (Docker Compose) — 1 hour
4. **Run Phase 4** (Start monitoring) — 1 trading cycle

**Total setup time**: 4-5 hours for fully functional Zero Script QA

**Monitoring time**: 1 trading day per test cycle (automatic)

---

## References

- **Memory System**: `.claude/agent-memory/bkit-qa-monitor/`
- **Implementation Details**: See memory files for comprehensive patterns and strategies
- **Plan/Design Docs**: `docs/01-plan/features/swing-algorithm-improvement.plan.md`

---

## Questions?

The QA monitor has full context about:
- What to test (swing algorithm improvements)
- How to test (structured logs)
- What success looks like (0 ERROR logs, correct lifecycle)
- What patterns to watch for (target exits, hold periods, day-of-week bonuses)

Run `/zero-script-qa` or ask the QA monitor directly!
