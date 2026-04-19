---
name: Zero Script QA Quick Start
description: Fast reference for implementing and running QA monitoring
type: reference
---

## 30-Second Summary

**Zero Script QA** = Monitor structured logs → Detect errors automatically → Document issues

**Setup time**: 4-5 hours | **Test time**: 1 trading day

---

## What You'll Do

### Phase 1: JSON Logging (2-3 hours)
```bash
# Create logger module
lib/logger.js              # ~50 lines

# Update 3 files (~5 lines each)
swing_scanner_code.js      # Replace console.log with logger.info
Daily_Position_Monitor.js  # Same
weekly_reporter_code.js    # Same

# Verify
cat logs/swing_scanner_*.log | jq .
```

### Phase 2: Request ID (1 hour)
```bash
# Add to position objects
position.request_id = "trading_20260419_005930"

# Propagate through lifecycle
logs will show: "request_id": "trading_20260419_005930" in every line
```

### Phase 3: Monitor (1 day)
```bash
# Run normal trading cycle
node swing_scanner_code.js

# Claude Code monitors automatically
# Issues documented as they occur
```

---

## Key Files

| File | Purpose | Action |
|------|---------|--------|
| `docs/03-analysis/zero-script-qa-setup.md` | Full implementation guide | Read for details |
| `docs/03-analysis/zero-script-qa-summary.md` | Executive summary | Read for overview |
| `.claude/agent-memory/bkit-qa-monitor/MEMORY.md` | Memory index | Reference |
| `.claude/agent-memory/bkit-qa-monitor/test_strategy.md` | What to test | Reference during testing |
| `.claude/agent-memory/bkit-qa-monitor/monitoring_patterns.md` | What patterns to watch | Reference during monitoring |

---

## One-Page Implementation

### Step 1: Create lib/logger.js
```javascript
const fs = require('fs');
const path = require('path');

class JsonLogger {
  constructor(service) {
    this.service = service;
    this.logFile = path.join(__dirname, '../logs', `${service}_${this.getDate()}.log`);
  }

  getDate() {
    return new Date().toISOString().split('T')[0];
  }

  log(level, message, data = {}) {
    const logEntry = JSON.stringify({
      timestamp: new Date().toISOString(),
      level,
      service: this.service,
      request_id: data.request_id || 'N/A',
      message,
      data: Object.keys(data).length > 0 ? data : undefined
    });
    
    fs.appendFileSync(this.logFile, logEntry + '\n');
    console.log(logEntry);
  }

  info(msg, data) { this.log('INFO', msg, data); }
  error(msg, data) { this.log('ERROR', msg, data); }
  warning(msg, data) { this.log('WARNING', msg, data); }
  debug(msg, data) { this.log('DEBUG', msg, data); }
}

module.exports = JsonLogger;
```

### Step 2: Update swing_scanner_code.js
```javascript
const JsonLogger = require('./lib/logger');
const logger = new JsonLogger('swing_scanner');

// Replace: console.log('Evaluating stock', code)
// With:
logger.info('Stock evaluation started', {
  request_id: `trading_${new Date().toISOString().split('T')[0]}_${code}`,
  code, price, atr
});

// On error:
logger.error('Stock evaluation failed', { code, error: err.message });
```

### Step 3: Update Daily_Position_Monitor.js
```javascript
const JsonLogger = require('./lib/logger');
const logger = new JsonLogger('position_monitor');

// Load positions with request_id
positions.forEach(pos => {
  if (!pos.request_id) pos.request_id = `trading_${new Date().toISOString().split('T')[0]}_${pos.code}`;
  logger.info('Position evaluated', { request_id: pos.request_id, code: pos.code, currentPrice: price });
});
```

### Step 4: Update weekly_reporter_code.js
```javascript
const JsonLogger = require('./lib/logger');
const logger = new JsonLogger('weekly_reporter');

logger.info('Report generation started', { request_id: 'weekly_reporter_' + new Date().toISOString() });
logger.info('Report generated', { totalPositions, winRate, totalPnL });
```

### Step 5: Test
```bash
mkdir -p logs
node swing_scanner_code.js
cat logs/swing_scanner_*.log | head -5 | jq .
```

---

## Monitoring Checklist

During test cycle, watch for:

```
✅ Check at cycle start
  □ logs/ directory exists
  □ JSON files being created
  □ All 3 services logging

✅ Check every 30 minutes
  □ No ERROR level logs
  □ Request IDs consistent for each stock
  □ Positions created as expected

✅ Check at cycle end
  □ All positions completed lifecycle (created → held → exited)
  □ No orphaned request IDs
  □ P&L calculation correct
  □ Hold periods respected (3 days)
```

---

## Expected Issues (and How to Fix)

| Issue | Symptom | Fix |
|-------|---------|-----|
| Logs not writing | logs/ empty | Check directory exists and writable |
| Invalid JSON | `jq .` fails | Verify JSON.stringify used correctly |
| Request IDs different | Position appears in 2 request IDs | Propagate request_id through position object |
| Grade not matching | position created with wrong grade | Check grade string matching (no extra spaces) |
| Hold period wrong | Positions held 2 days instead of 3 | Check HOLD_SURGE=3 constant updated |

---

## When Ready

1. Implement Phase 1-2 above
2. Test logging works
3. Tell me: "QA monitoring is live"
4. I monitor next trading cycle automatically
5. Get real-time alerts on any issues

---

## Questions?

Memory system persists across conversations. Ask:
- "What's the next step?"
- "How do I implement Phase 1?"
- "Why is my JSON invalid?"
- "How do I trace request ID XXX?"

All context saved!
