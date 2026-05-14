# QA Monitoring - Quick Start Guide

**Created**: 2026-05-07  
**Status**: Ready to Use  
**Version**: 1.0.0

---

## 5-Minute Setup

### Step 1: Verify Logger Integration (30 seconds)

```bash
# Check logger module exists
ls -la lib/logger.js

# Check recent logs
ls -la logs/ | head
```

**Expected Output:**
- `lib/logger.js` exists
- `logs/` directory has `.log` files from recent dates

### Step 2: Import n8n Workflow (2 minutes)

**In n8n:**
1. Click "Import Workflow" 
2. Select `n8n-qa-monitoring-workflow.json`
3. Set environment variables:
   - `SENDGRID_API_KEY`: Your SendGrid API key
   - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
   - `TELEGRAM_CHAT_ID`: Your Telegram chat ID
4. Update paths in workflow:
   - `/path/to/logs` → Your actual logs directory
   - `/path/to/qa-logs` → Your QA logs directory
5. Click "Save"

### Step 3: Monitor Logs in Real-time (2 minutes)

```bash
# Open new terminal in project directory
cd D:\vibecording\showmoneyv2

# Start monitoring all logs
tail -f logs/*.log | jq .

# OR: Monitor specific service
grep -E '"service":"swing_scanner"' logs/*.log | tail -50
```

### Step 4: Run First Test Cycle

```bash
# Start your n8n trading workflow
# Monitor logs in real-time (from Step 3)

# When workflow completes, check for:
# 1. No ERROR level logs
# 2. All duration_ms < 1000
# 3. Grade distribution reasonable
# 4. Request IDs properly formatted
```

---

## Real-time Log Analysis

### Quick Commands

```bash
# Count errors in last hour
grep '"level":"ERROR"' logs/*.log | wc -l

# Find slowest operations (>1000ms)
grep -E '"duration_ms":[0-9]+' logs/*.log | \
  jq 'select(.data.duration_ms > 1000)' | \
  jq -r '.message' | sort | uniq -c

# Show error summary
grep '"level":"ERROR"' logs/*.log | \
  jq -r '.message' | sort | uniq -c

# Track specific stock
grep '005930' logs/*.log | jq .

# Grade distribution (today)
grep '"message":"Grade calculated"' logs/swing_scanner_*.log | \
  jq -r '.data.grade' | sort | uniq -c
```

### Pretty Print Logs

```bash
# Format all logs as JSON
cat logs/*.log | jq .

# Filter by log level
jq 'select(.level == "ERROR")' logs/*.log

# Extract specific fields (CSV format)
jq -r '[.timestamp, .level, .service, .message] | @csv' logs/*.log

# Find logs for specific Request ID
jq "select(.request_id == \"trading_20260507103000_005930\")" logs/*.log
```

---

## Interpreting Log Output

### Healthy Log Example

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
    "duration_ms": 450
  }
}
```

✅ Indicators:
- `level: INFO` (not ERROR)
- `duration_ms: 450` (< 1000ms)
- `request_id` format valid
- All data fields present

### Error Example (Alert!)

```json
{
  "timestamp": "2026-05-07T10:35:12.000Z",
  "level": "ERROR",
  "service": "swing_scanner",
  "request_id": "trading_20260507103512_999999",
  "message": "Failed to fetch stock data",
  "data": {
    "stock_code": "999999",
    "error": "Invalid symbol"
  }
}
```

🔴 Indicators:
- `level: ERROR`
- Contains error message
- Check n8n alert or dashboard

### Slow Operation Example (Warning)

```json
{
  "timestamp": "2026-05-07T10:40:20.000Z",
  "level": "INFO",
  "service": "position_monitor",
  "request_id": "trading_20260507104020_005930",
  "message": "Position evaluation completed",
  "data": {
    "stock_code": "005930",
    "duration_ms": 2500
  }
}
```

⚠️ Indicators:
- `duration_ms: 2500` (> 1000ms)
- No error, but slow
- Investigate performance bottleneck

---

## Daily Check (5 minutes)

```bash
#!/bin/bash
# Daily QA Check Script

echo "=== QA Health Check ==="
echo ""

# 1. Error count
ERRORS=$(grep '"level":"ERROR"' logs/*.log | wc -l)
echo "Errors today: $ERRORS"

# 2. Total logs
TOTAL=$(cat logs/*.log | wc -l)
echo "Total logs: $TOTAL"

# 3. Slow operations
SLOW=$(grep -E '"duration_ms":[0-9]+' logs/*.log | \
  jq 'select(.data.duration_ms > 1000)' | wc -l)
echo "Slow operations: $SLOW"

# 4. Grade distribution
echo ""
echo "Grade Distribution:"
grep '"message":"Grade calculated"' logs/swing_scanner_*.log | \
  jq -r '.data.grade' | sort | uniq -c

# 5. Error summary
if [ $ERRORS -gt 0 ]; then
  echo ""
  echo "ERROR SUMMARY:"
  grep '"level":"ERROR"' logs/*.log | \
    jq -r '.message' | sort | uniq -c
fi

echo ""
echo "=== End Check ==="
```

---

## Troubleshooting

### Issue: "No logs found"

**Solution:**
```bash
# Check logs directory exists
ls -la logs/

# If empty, run a trade workflow first
# Then check again
ls -la logs/
```

### Issue: "jq: command not found"

**Solution:**
```bash
# Install jq (Windows)
choco install jq

# OR install via npm
npm install -g jq
```

### Issue: "Permission denied" when reading logs

**Solution:**
```bash
# Check file permissions
ls -la logs/

# If needed, change permissions
chmod 644 logs/*.log
```

### Issue: Logs not being written

**Check:**
1. Logger module integrated in code: `require('./lib/logger')`
2. JsonLogger instantiated: `new JsonLogger('service_name')`
3. Logs directory writable: `touch logs/test.log`
4. n8n process running: `docker ps | grep n8n`

---

## What to Monitor

### Critical (Check Every Day)

- [ ] No ERROR logs
- [ ] Average duration < 1000ms
- [ ] Error rate < 0.1%
- [ ] Request IDs properly formatted

### Important (Check Weekly)

- [ ] Grade distribution reasonable:
  - 강매: 5-10%
  - 급등: 10-15%
  - 매도차익: 20-30%
  - 기타: 50-70%
- [ ] No consecutive failures (3+)
- [ ] Hold days compliance verified
- [ ] No missing log fields

### Nice to Have (Monthly)

- [ ] Performance trend analysis
- [ ] Service reliability metrics
- [ ] User impact assessment
- [ ] Optimization opportunities

---

## Log File Locations

```
D:\vibecording\showmoneyv2\
├── logs/                          # Daily log files
│   ├── swing_scanner_2026-05-07.log
│   ├── position_monitor_2026-05-07.log
│   └── ...
├── lib/
│   └── logger.js                  # Logger module
├── ZERO-SCRIPT-QA-SETUP.md        # Complete QA guide
├── QA-MONITORING-QUICK-START.md   # This file
└── n8n-qa-monitoring-workflow.json # n8n workflow template
```

---

## Sample Monitoring Session

### Time: 10:00 AM (Start)

```bash
$ tail -f logs/*.log | jq .

# Monitor starts
# [Waiting for logs...]
```

### Time: 10:05 AM (First logs appear)

```json
{
  "timestamp": "2026-05-07T10:05:12.000Z",
  "level": "INFO",
  "service": "swing_scanner",
  "request_id": "trading_20260507100512_005930",
  "message": "Starting stock analysis",
  "data": { "stock_code": "005930", "analysis_type": "swing" }
}
```

✅ First log received - monitoring active!

### Time: 10:15 AM (Analysis complete)

```bash
# 100+ grades calculated
# All duration_ms < 500ms
# No errors detected
# Grade distribution:
#   강매: 8 (8%)
#   급등: 12 (12%)
#   매도차익: 25 (25%)
#   기타: 55 (55%)
```

✅ Analysis complete - metrics healthy!

### Time: 10:20 AM (Analysis)

```bash
# Summary:
# - Total logs: 256
# - Errors: 0
# - Performance: Excellent (avg 320ms)
# - Status: HEALTHY
```

✅ QA Check passed - ready for deployment!

---

## Next Steps

1. **Import n8n Workflow**
   - File: `n8n-qa-monitoring-workflow.json`
   - Configure environment variables
   - Enable notifications (Telegram/Email)

2. **Set Up Monitoring**
   - Start log tailing: `tail -f logs/*.log`
   - Run first test cycle
   - Record baseline metrics

3. **Configure Alerts**
   - Error alerts: Immediate
   - Slow operation alerts: >1000ms
   - Daily summary: 6 PM KST

4. **Schedule Reviews**
   - Daily: 5-minute health check
   - Weekly: Full metrics review
   - Monthly: Optimization analysis

---

## Support & Resources

- **Logger Documentation**: `ZERO-SCRIPT-QA-SETUP.md`
- **Monitoring Guide**: `.claude/agent-memory/bkit-qa-monitor/MONITORING-GUIDE.md`
- **Logger Code**: `lib/logger.js`

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `tail -f logs/*.log \| jq .` | Real-time log monitoring |
| `grep '"level":"ERROR"' logs/*.log` | Find all errors |
| `grep '"message":"Grade calculated"' logs/*.log \| jq -r '.data.grade' \| sort \| uniq -c` | Grade distribution |
| `grep 'trading_XXXX' logs/*.log` | Track specific request |
| `jq 'select(.level == "ERROR")' logs/*.log` | Filter by level |

---

**Ready to monitor? Start with Step 1 above!**

Questions? Check `ZERO-SCRIPT-QA-SETUP.md` for detailed information.
