# Zero Script QA Setup - showmoneyv2 Trading System

**Date**: 2026-05-07  
**Status**: Ready for Implementation  
**Logger Status**: ✅ Fully Integrated (JsonLogger)

---

## 1. Overview

This document outlines the Zero Script QA monitoring setup for the showmoneyv2 stock trading automation system. The system uses structured JSON logs with request ID tracing to validate trading operations without writing traditional test scripts.

### Current System Status

| Component | Status | Details |
|-----------|--------|---------|
| Logger Module | ✅ Complete | `lib/logger.js` - JsonLogger class |
| Integration | ✅ Complete | Integrated in swing_scanner, daily_position_monitor |
| Log Format | ✅ Valid | JSON with timestamp, level, service, request_id, message, data |
| Request ID | ✅ Active | Format: `trading_YYYYMMDDHHMMSS_STOCKCODE` |
| Test Results | ✅ Passed | 9/9 tests passed on 2026-04-23 |

---

## 2. Logging Architecture

### JSON Log Format Standard

All logs follow this structure:

```json
{
  "timestamp": "2026-05-07T10:30:00.000Z",
  "level": "INFO",
  "service": "swing_scanner",
  "request_id": "trading_20260507103000_005930",
  "message": "Stock analysis completed",
  "data": {
    "stock_code": "005930",
    "grade": "강매",
    "score": 125,
    "duration_ms": 450
  }
}
```

### Log Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| timestamp | ISO 8601 | Time of occurrence | "2026-05-07T10:30:00.000Z" |
| level | string | DEBUG, INFO, WARNING, ERROR | "INFO" |
| service | string | Service name | "swing_scanner", "position_monitor" |
| request_id | string | Request tracking ID | "trading_20260507103000_005930" |
| message | string | Log message | "Stock analysis completed" |
| data | object | Additional context | {stock_code, grade, score, duration_ms} |

### Log Levels

| Environment | Min Level | Purpose |
|-------------|-----------|---------|
| Development | DEBUG | Detailed debugging information |
| Staging | DEBUG | Full tracing for integration testing |
| Production | INFO | Operations only (no sensitive data) |

---

## 3. Request ID Propagation

### Flow Diagram

```
Swing Scanner Start
        ↓ [Request ID: trading_20260507103000_SYMBOL]
    ├─→ Stock Analysis
    │   └─→ request_id propagated through all steps
    ├─→ Grade Calculation
    │   └─→ request_id: SYMBOL-specific tracing
    └─→ Trading Decision
        └─→ request_id: Complete flow record
```

### Usage in Code

```javascript
const logger = new JsonLogger('swing_scanner');
const requestId = logger.generateRequestId('005930');

// Log start
logger.info('Starting stock analysis', { 
  stock_code: '005930',
  analysis_type: 'swing'
}, requestId);

// Log intermediate steps
logger.info('Calculating grades', {
  macd_status: 'golden_cross',
  rsi_value: 65
}, requestId);

// Log completion with metrics
logger.info('Analysis completed', {
  grade: '강매',
  score: 125,
  duration_ms: 450
}, requestId);
```

---

## 4. Service Integration

### 1. Swing Scanner (`swing_scanner_code.js`)

**Logging Points:**
- Scan started: timestamp, total symbols count
- Symbol processed: code, analysis duration
- Grade calculated: code, grade, score, confidence
- Alert sent: code, grade, telegram delivery status
- Scan completed: total processed, grades distribution

**Log Example:**
```json
{
  "timestamp": "2026-05-07T10:30:45.000Z",
  "level": "INFO",
  "service": "swing_scanner",
  "request_id": "trading_20260507103000_005930",
  "message": "Grade calculated",
  "data": {
    "stock_code": "005930",
    "grade": "강매",
    "score": 125,
    "confidence": 0.95
  }
}
```

### 2. Daily Position Monitor (`Daily_Position_Monitor.js`)

**Logging Points:**
- Monitor started: position count
- Position evaluated: code, current_price, profit_loss
- Hold decision: code, hold_reason, next_check_time
- Position closed: code, final_price, profit_loss_pct
- Monitor completed: total evaluated, actions taken

**Log Example:**
```json
{
  "timestamp": "2026-05-07T14:30:00.000Z",
  "level": "INFO",
  "service": "position_monitor",
  "request_id": "trading_20260507143000_005930",
  "message": "Position evaluated",
  "data": {
    "stock_code": "005930",
    "entry_price": 70000,
    "current_price": 74000,
    "profit_loss_pct": 5.71,
    "hold_days": 1
  }
}
```

### 3. Weekly Reporter (`weekly_reporter_code.js`)

**Logging Points:**
- Report generation started: week, total trades
- Trade statistics calculated: win_rate, avg_return
- Grade distribution: grades breakdown
- Risk metrics: max_loss, sharpe_ratio
- Report sent: telegram delivery status

---

## 5. QA Monitoring Patterns

### Pattern 1: Error Detection (Immediate Report)

**Monitor for:**
```json
{ "level": "ERROR" }
```

**Action:**
1. Record Request ID
2. Extract error message and data
3. Check related logs with same Request ID
4. Document in QA findings

**Example:**
```json
{
  "level": "ERROR",
  "message": "Failed to fetch stock data",
  "data": {
    "stock_code": "999999",
    "error": "Invalid symbol"
  }
}
```

### Pattern 2: Slow Response Detection (>1000ms)

**Monitor for:**
```json
{ "data": { "duration_ms": "> 1000" } }
```

**Action:**
1. Identify operation type
2. Check if timeout threshold exceeded
3. Analyze bottleneck (API? Processing? DB?)
4. Document performance issue
5. Suggest optimization

### Pattern 3: Grade Distribution Anomaly

**Monitor for:**
- Expected: 강매(5-10%), 급등(10-15%), 매도차익(20-30%), 기타(50-70%)
- Alert if: Any grade >50% or <0%

**Action:**
1. Check algorithm parameters
2. Review recent code changes
3. Validate input data quality
4. Document and investigate

### Pattern 4: Hold Days Verification

**Monitor for:**
- 강매: Should hold 1 day (당일청산)
- 급등: Should hold 1 day (당일청산)
- 매도차익: Should hold 1-3 days
- 기타: Should hold 1-5 days

**Verification:**
```json
{
  "message": "Position closed",
  "data": {
    "grade": "강매",
    "hold_days": 1,
    "expected_hold_days": 1,
    "compliance": true
  }
}
```

### Pattern 5: Request ID Propagation

**Verify:**
- All logs for single trade have same `request_id`
- Request ID format: `trading_YYYYMMDDHHMMSS_SYMBOL`
- No missing intermediate steps

**Test:**
```bash
# Extract all logs for specific trade
grep 'trading_20260507103000_005930' logs/*.log
# Should show: analysis start → grade calc → alert sent → complete
```

---

## 6. Issue Detection Thresholds

| Pattern | Severity | Threshold | Action |
|---------|----------|-----------|--------|
| **ERROR level** | Critical | Any occurrence | Immediate documentation |
| **Duration** | Critical | > 3000ms | Investigate bottleneck |
| **Status 5xx** | Critical | Any occurrence | System issue alert |
| **Duration** | Warning | 1000-3000ms | Performance note |
| **Status 4xx** | Warning | Auth failures | Check credentials |
| **Consecutive failures** | Warning | 3+ same endpoint | Pattern analysis |
| **Grade outlier** | Info | >50% single grade | Review algorithm |
| **Missing data** | Info | Null/undefined | Data quality check |

---

## 7. Docker-Based Real-time Monitoring

### Environment Setup

**Prerequisites:**
- Docker / Docker Compose installed
- n8n running with trading workflows
- Logs directory accessible: `logs/`

### Real-time Log Monitoring

```bash
# Monitor all service logs
tail -f logs/*.log | jq .

# Monitor specific service
grep -E '"service":"swing_scanner"' logs/swing_scanner*.log | tail -50

# Track specific stock
grep 'trading_20260507103000_005930' logs/*.log

# Filter errors only
grep '"level":"ERROR"' logs/*.log

# Real-time performance analysis
grep -E '"duration_ms":[0-9]+' logs/*.log | \
  jq -r '.data.duration_ms' | sort -n | tail -10
```

### Monitoring Dashboard (jq Filter)

```bash
# Count logs by level
grep -E '"level"' logs/*.log | \
  jq -r '.level' | sort | uniq -c

# Top 10 slowest operations
grep -E '"duration_ms"' logs/*.log | \
  jq -r '[.message, .data.duration_ms] | @csv' | \
  sort -t',' -k2 -rn | head -10

# Grade distribution
grep '"message":"Grade calculated"' logs/*.log | \
  jq -r '.data.grade' | sort | uniq -c
```

---

## 8. Test Cycle Workflow

### Cycle 1: Logger Verification

```
┌─ Start n8n workflow
├─ Monitor logs in real-time
├─ Verify JSON format validity
├─ Check Request ID propagation
└─ Record baseline metrics
```

### Cycle 2: Grade Distribution

```
┌─ Run full scan (100+ stocks)
├─ Verify grade distribution
├─ Check hold days compliance
├─ Validate score ranges
└─ Document any anomalies
```

### Cycle 3: Performance

```
┌─ Measure operation durations
├─ Identify bottlenecks (>1000ms)
├─ Check error rates
├─ Validate timeout handling
└─ Suggest optimizations
```

### Cycle 4: Error Handling

```
┌─ Inject invalid data
├─ Monitor error logs
├─ Verify error messages clarity
├─ Check error recovery
└─ Document error patterns
```

---

## 9. Issue Documentation Template

```markdown
## ISSUE-{number}: {Title}

**Request ID**: trading_20260507103000_005930
**Severity**: Critical/Warning/Info
**Service**: swing_scanner / position_monitor
**Time**: 2026-05-07 10:30:45 UTC
**Affected Stock**: 005930 (Samsung Electronics)

### Related Logs
\`\`\`json
{
  "timestamp": "2026-05-07T10:30:45.000Z",
  "level": "ERROR",
  "message": "Grade calculation failed",
  "data": { ... }
}
\`\`\`

### Analysis
- Root cause: [Description]
- Impact: [How it affects trading]
- Frequency: [First time / Recurring]

### Reproduction Path
1. [Step 1]
2. [Step 2]
3. [Observe error]

### Recommended Fix
- File: `path/to/file.js:line`
- Change: [What needs to change]
- Test: [How to verify fix]

### Verification
- [ ] Fix applied
- [ ] Logs show no errors
- [ ] Performance metrics normal
- [ ] Grade distribution correct
```

---

## 10. Checklist - QA Readiness

### Pre-Monitoring Setup
- [x] JsonLogger class implemented (`lib/logger.js`)
- [x] Logger integrated into all trading services
- [x] Request ID generation active
- [x] JSON format validated
- [x] Log files directory created (`logs/`)

### Monitoring Setup
- [ ] Real-time log monitoring configured
- [ ] jq filters created for analysis
- [ ] Alert thresholds defined
- [ ] Issue documentation templates ready
- [ ] Team notified of monitoring start

### During Monitoring
- [ ] Logs monitored continuously
- [ ] Errors documented immediately
- [ ] Performance metrics tracked
- [ ] Grade distribution verified
- [ ] Hold days compliance checked

### Post-Monitoring
- [ ] Summary report generated
- [ ] Issues categorized by severity
- [ ] Fixes implemented and tested
- [ ] Performance improvements deployed
- [ ] Monitoring cycle repeated

---

## 11. Performance Baseline

### Expected Metrics

| Metric | Expected Range | Warning Threshold |
|--------|-----------------|-------------------|
| Analysis per stock | 100-500ms | > 1000ms |
| Full scan (1000 stocks) | 30-60s | > 120s |
| Grade calculation | 50-200ms | > 500ms |
| Position evaluation | 20-100ms | > 200ms |
| Telegram alert send | 200-500ms | > 1000ms |
| Error rate | < 0.1% | > 1% |
| Grade distribution variance | < 10% | > 20% |

### Baseline Recording (First Monitoring)

Run scan and record:
```json
{
  "date": "2026-05-07",
  "cycle": 1,
  "total_stocks_scanned": 2000,
  "total_duration_s": 45,
  "avg_per_stock_ms": 22.5,
  "error_count": 0,
  "error_rate": 0.0,
  "grade_distribution": {
    "강매": 0.08,
    "급등": 0.12,
    "매도차익": 0.25,
    "기타": 0.55
  }
}
```

---

## 12. Next Steps

### Immediate (Week 1)
1. [ ] Start real-time log monitoring
2. [ ] Run full test scan
3. [ ] Record baseline metrics
4. [ ] Document first issues if found
5. [ ] Verify grade distribution

### Short-term (Week 2-3)
1. [ ] Complete 3 monitoring cycles
2. [ ] Implement any critical fixes
3. [ ] Generate performance report
4. [ ] Validate hold days compliance
5. [ ] Review error patterns

### Medium-term (Month 2)
1. [ ] Production deployment
2. [ ] Set up automated monitoring
3. [ ] Create alerting thresholds
4. [ ] Document SLA metrics
5. [ ] Plan next optimization cycle

---

## 13. Quick Reference

### View Live Logs
```bash
cd D:\vibecording\showmoneyv2
tail -f logs/*.log
```

### Filter Logs with jq
```bash
# Pretty print JSON logs
cat logs/swing_scanner_*.log | jq .

# Filter by service
jq 'select(.service == "swing_scanner")' logs/*.log

# Filter by level
jq 'select(.level == "ERROR")' logs/*.log

# Extract specific fields
jq -r '[.timestamp, .message, .request_id] | @csv' logs/*.log
```

### Generate Report
```bash
# Error summary
grep '"level":"ERROR"' logs/*.log | wc -l

# Slow operations
grep -E '"duration_ms":[0-9]+' logs/*.log | \
  jq 'select(.data.duration_ms > 1000)' | jq -r '.message'
```

---

## Contact & Support

**QA Monitor**: Claude Code (bkit-qa-monitor)
**Last Updated**: 2026-05-07
**Version**: 1.0.0 - Zero Script QA

For questions about monitoring setup, refer to:
- `.claude/agent-memory/bkit-qa-monitor/MONITORING-GUIDE.md`
- `lib/logger.js` - Logger implementation details
