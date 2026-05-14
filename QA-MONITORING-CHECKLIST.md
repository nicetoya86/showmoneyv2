# QA Monitoring Checklist & Issue Template

**Date**: 2026-05-07  
**Version**: 1.0.0

---

## Daily Monitoring Checklist

### Pre-Monitoring (Before Trading Hours)

- [ ] **Logs Directory Check**
  - [ ] Logs directory exists: `logs/`
  - [ ] Previous day logs archived (optional)
  - [ ] Enough disk space available

- [ ] **Logger Verification**
  - [ ] Logger module loaded: `lib/logger.js`
  - [ ] Logger instantiated in all services
  - [ ] Log level set to DEBUG (development) or INFO (production)

- [ ] **n8n Workflow Status**
  - [ ] QA monitoring workflow enabled
  - [ ] Telegram/Email notifications configured
  - [ ] All environment variables set
  - [ ] Workflow scheduled correctly

- [ ] **Monitoring Setup**
  - [ ] Terminal open with log tailing: `tail -f logs/*.log`
  - [ ] jq tool installed and functional
  - [ ] Analysis scripts ready
  - [ ] Alert channels tested

### During Trading (Every 30 minutes)

- [ ] **Error Check**
  - [ ] Run: `grep '"level":"ERROR"' logs/*.log | wc -l`
  - [ ] Expected: 0 errors
  - [ ] If errors: Document immediately (see Issue Template below)

- [ ] **Performance Check**
  - [ ] Run: `grep -E '"duration_ms":[0-9]+' logs/*.log | jq 'select(.data.duration_ms > 1000)' | wc -l`
  - [ ] Expected: < 3 slow operations
  - [ ] If slow: Note operation type and investigate

- [ ] **Request ID Propagation**
  - [ ] Sample log shows: `"request_id": "trading_YYYYMMDDHHMMSS_CODE"`
  - [ ] Format correct: trading_{timestamp}_{stock_code}
  - [ ] No N/A or missing values

- [ ] **Log Quality**
  - [ ] All JSON logs parse correctly: `cat logs/*.log | jq . > /dev/null 2>&1`
  - [ ] No corrupted/truncated lines
  - [ ] Timestamps in ISO 8601 format

### Post-Trading (After Market Close)

- [ ] **Daily Summary Report**
  - [ ] Run daily aggregation: `jq -s 'length' logs/*.log`
  - [ ] Record total logs
  - [ ] Calculate error rate: `error_count / total_logs`
  - [ ] Grade distribution captured
  - [ ] Performance metrics recorded

- [ ] **Alert Review**
  - [ ] Check Telegram/Email alerts received
  - [ ] Review all critical issues
  - [ ] Verify issue documentation complete
  - [ ] Assign fixes if needed

- [ ] **Archive & Cleanup**
  - [ ] Logs backed up (if needed)
  - [ ] QA reports generated
  - [ ] Metrics logged to database
  - [ ] Old logs rotated (if > 10MB)

---

## Weekly Monitoring Checklist

### Monday (Week Start)

- [ ] **Previous Week Review**
  - [ ] All issues documented
  - [ ] All fixes tested
  - [ ] Success rate calculated
  - [ ] Performance trends analyzed

- [ ] **Grade Distribution Analysis**
  - [ ] Expected ranges:
    - 강매: 5-10%
    - 급등: 10-15%
    - 매도차익: 20-30%
    - 기타: 50-70%
  - [ ] If outside range: Investigate algorithm change

- [ ] **Hold Days Compliance**
  - [ ] Verify grade-to-hold-days mapping:
    - 강매 → 1 day
    - 급등 → 1 day
    - 매도차익 → 1-3 days
    - 기타 → 1-5 days
  - [ ] Check position_monitor logs for compliance
  - [ ] Document any deviations

### Wednesday (Mid-week Review)

- [ ] **Performance Trend**
  - [ ] Calculate average duration: `grep -E '"duration_ms"' logs/*.log | jq '.data.duration_ms' | awk '{sum+=$1; count++} END {print sum/count}'`
  - [ ] Compare to baseline (first monitoring)
  - [ ] Alert if degraded > 20%

- [ ] **Error Pattern Analysis**
  - [ ] Group errors by type: `grep '"level":"ERROR"' logs/*.log | jq -r '.message' | sort | uniq -c`
  - [ ] Identify recurring issues
  - [ ] Prioritize fixes

### Friday (Week End)

- [ ] **Weekly Report Generation**
  - [ ] Success rate: (total - errors) / total
  - [ ] Performance metrics: avg, min, max duration
  - [ ] Grade distribution: percentage per grade
  - [ ] Error summary: top issues
  - [ ] Recommendations: top 3 improvements

- [ ] **Planning Next Week**
  - [ ] Critical issues to fix
  - [ ] Optimizations to implement
  - [ ] New features to monitor
  - [ ] Team communication

---

## Issue Documentation Template

### Header

```
Issue ID: ISSUE-{number}
Title: {Concise description}
Date: YYYY-MM-DD HH:MM:SS UTC
Severity: Critical / Warning / Info
```

### Affected System

```
Service: swing_scanner / position_monitor / daily_healthcheck
Request ID: trading_YYYYMMDDHHMMSS_SYMBOL
Stock Code: {If applicable}
User Impact: {High / Medium / Low}
```

### Issue Description

```
### Problem
{Clear description of what went wrong}

### Evidence
```json
{
  "timestamp": "2026-05-07T10:30:45.000Z",
  "level": "ERROR",
  "service": "swing_scanner",
  "request_id": "trading_20260507103045_005930",
  "message": "{Error message}",
  "data": { ... }
}
```

### Reproduction
1. {Step 1}
2. {Step 2}
3. {Expected behavior}
4. {Actual behavior}

### Root Cause Analysis

```
### Investigation
- Checked: {What was checked}
- Found: {What was found}
- Cause: {Root cause identified}

### Related Code
File: path/to/file.js
Line: {line number}
Code snippet:
\`\`\`javascript
{relevant code}
\`\`\`
```

### Recommended Solution

```
### Fix Approach
1. {Step 1}
2. {Step 2}
3. {Step 3}

### Implementation
File: path/to/file.js
Change: {What should change}

### Validation
After fix, verify:
- [ ] No ERROR logs
- [ ] Performance within threshold
- [ ] Request ID properly formatted
- [ ] Grade distribution normal
```

### Example: Complete Issue

```markdown
## ISSUE-001: Grade Calculation Returns NULL

**Issue ID**: ISSUE-001  
**Date**: 2026-05-07 10:30:45 UTC  
**Severity**: Critical  
**Service**: swing_scanner  
**Request ID**: trading_20260507103045_005930  
**Stock Code**: 005930 (Samsung Electronics)

### Problem
Grade calculation occasionally returns NULL, causing analysis to fail for stock 005930.

### Evidence
```json
{
  "timestamp": "2026-05-07T10:30:45.000Z",
  "level": "ERROR",
  "service": "swing_scanner",
  "request_id": "trading_20260507103045_005930",
  "message": "Grade calculation failed",
  "data": {
    "stock_code": "005930",
    "error": "TypeError: Cannot read property 'grade' of undefined"
  }
}
```

### Reproduction Path
1. Run swing scanner
2. Process stock with incomplete OHLCV data
3. Grade calculation skipped due to missing data
4. Result: NULL grade returned

### Root Cause Analysis
In `swing_scanner_code.js` line 452, grade calculation doesn't check for missing MACD values:
```javascript
const grade = calculateGrade({
  rsi: rsi_value,
  macd: macd_value, // <- Can be undefined if data missing
  volume: vol_ratio
});
```

When `macd_value` is undefined, grade calculation fails.

### Recommended Fix
Add null-check before grade calculation:
```javascript
if (!macd_value || rsi_value === undefined) {
  logger.warning('Incomplete data', {
    stock_code: symbol,
    missing_data: { macd: !macd_value, rsi: !rsi_value }
  }, requestId);
  return null; // Skip this stock
}
```

### Validation After Fix
- [ ] Run scanner on 1000 stocks
- [ ] Check logs: `grep '"grade":null' logs/*.log` should be 0
- [ ] Verify: `grep '"level":"ERROR"' logs/*.log` should be 0
- [ ] Grade distribution within expected ranges
- [ ] All durations < 500ms

**Status**: OPEN → IN PROGRESS → TESTING → CLOSED
```

---

## Performance Baseline Template

### Recording Baseline (First Run)

```json
{
  "date": "2026-05-07",
  "monitoring_cycle": 1,
  "environment": "production",
  "test_duration_minutes": 60,
  
  "summary": {
    "total_stocks_scanned": 2000,
    "total_logs": 8500,
    "time_elapsed_seconds": 2700,
    "avg_logs_per_second": 3.15
  },
  
  "performance": {
    "analysis_per_stock_ms": {
      "min": 18,
      "max": 450,
      "avg": 78,
      "p95": 250
    },
    "full_scan_seconds": 45,
    "scan_rate_stocks_per_second": 44.4
  },
  
  "reliability": {
    "total_logs": 8500,
    "errors": 0,
    "error_rate_percent": 0.0,
    "warnings": 3,
    "warning_rate_percent": 0.035
  },
  
  "grades": {
    "total_grades_calculated": 500,
    "강매": { "count": 38, "percent": 7.6 },
    "급등": { "count": 72, "percent": 14.4 },
    "매도차익": { "count": 138, "percent": 27.6 },
    "기타": { "count": 252, "percent": 50.4 }
  },
  
  "quality": {
    "json_valid_percent": 100.0,
    "request_id_valid_percent": 100.0,
    "timestamp_valid_percent": 100.0,
    "data_complete_percent": 99.8
  }
}
```

### Comparison Template (Weekly)

```
Week 1 Baseline:
- Avg duration: 78ms
- Error rate: 0.0%
- Grade distribution: 7.6% / 14.4% / 27.6% / 50.4%

Week 2 Actual:
- Avg duration: 85ms (+9% slower) ⚠️
- Error rate: 0.15% (concerning)
- Grade distribution: 6.2% / 15.1% / 28.5% / 50.2%

Recommendation: Monitor duration trend
```

---

## Alert Severity Levels

### Critical (Immediate Action)

```
Condition | Action
-----------|--------
ERROR level log | Document, notify team, investigate immediately
duration > 3000ms | Check for system issues
5xx status code | System error alert
Consecutive failures (3+) | Pattern analysis, potential outage
```

**Response Time**: < 30 minutes

### Warning (Review & Monitor)

```
Condition | Action
-----------|--------
duration 1000-3000ms | Log, monitor trend
404 status code | Check configuration
Grade distribution anomaly | Verify algorithm parameters
Missing data fields | Quality check
```

**Response Time**: < 1 hour

### Info (Track & Optimize)

```
Condition | Action
-----------|--------
duration < 1000ms | Normal operation
All logs valid JSON | Log quality good
Request ID properly formatted | Tracing working
Grade within expected range | Algorithm healthy
```

**Response Time**: End of day review

---

## Issue Resolution Workflow

```
┌─────────────────────────────────────────┐
│ 1. DETECTION                             │
│ - Monitor real-time logs                 │
│ - Identify anomaly                       │
│ - Check severity                         │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 2. DOCUMENTATION                        │
│ - Create issue record                    │
│ - Gather evidence (logs)                 │
│ - Reproduce problem                      │
│ - Identify root cause                    │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 3. ANALYSIS                              │
│ - Review code                            │
│ - Determine fix approach                 │
│ - Estimate impact                        │
│ - Get approval if needed                 │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 4. IMPLEMENTATION                       │
│ - Make code change                       │
│ - Test locally                           │
│ - Commit to git                          │
│ - Deploy                                 │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 5. VALIDATION                            │
│ - Monitor logs post-fix                  │
│ - Verify no new errors                   │
│ - Check performance metrics              │
│ - Confirm grade distribution             │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 6. CLOSURE                               │
│ - Update issue record                    │
│ - Document fix applied                   │
│ - Archive evidence                       │
│ - Mark as RESOLVED                       │
└─────────────────────────────────────────┘
```

---

## Monitoring Schedule

### Daily

| Time (KST) | Activity | Responsibility |
|-----------|----------|-----------------|
| 08:45 | Pre-trading setup | QA Monitor |
| 09:00-11:30 | Morning monitoring | QA Monitor |
| 12:00 | Mid-day check | QA Monitor |
| 15:00 | Afternoon monitoring | QA Monitor |
| 16:00 | Post-trading review | QA Monitor |
| 18:00 | Daily report generation | Automated |

### Weekly

| Day | Time | Activity |
|-----|------|----------|
| Monday | 08:00 | Week planning |
| Wednesday | 14:00 | Mid-week review |
| Friday | 17:00 | Weekly report & analysis |

### Monthly

| Dates | Activity |
|-------|----------|
| 1st-5th | Previous month analysis |
| 2nd week | Optimization planning |
| 3rd week | Implementation & testing |
| 4th week | Validation & deployment |

---

## Key Metrics Dashboard

```
╔════════════════════════════════════════════╗
║       QA MONITORING DASHBOARD             ║
╠════════════════════════════════════════════╣
║ Errors Today:        0                     ║
║ Warnings Today:      2                     ║
║ Avg Duration:        78ms ✓                ║
║ Slow Operations:     1                     ║
║                                            ║
║ Grade Distribution:                        ║
║   강매:        7.6% ✓                      ║
║   급등:       14.4% ✓                      ║
║   매도차익:   27.6% ✓                      ║
║   기타:       50.4% ✓                      ║
║                                            ║
║ System Status:       HEALTHY ✓             ║
╚════════════════════════════════════════════╝
```

---

**Use this checklist daily. Print and keep handy during monitoring sessions.**
