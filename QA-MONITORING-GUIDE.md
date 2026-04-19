# QA Monitoring Guide - Zero Script QA

## Quick Start

### Watch Logs in Real-time

```bash
# Monitor all logs (follow tail)
tail -f logs/*.log

# Monitor scanner logs only
tail -f logs/swing_scanner_*.log

# Monitor position monitor logs
tail -f logs/position_monitor_*.log

# Monitor weekly reporter logs
tail -f logs/weekly_reporter_*.log
```

### Parse and Query Logs

```bash
# Parse as JSON
cat logs/*.log | jq .

# Filter by level
grep '"level":"ERROR"' logs/*.log | jq .

# Filter by service
grep '"service":"swing_scanner"' logs/*.log | jq .

# Track specific request ID
grep 'trading_' logs/*.log | jq . | grep -A 10 'request_id'

# Pretty print a log file
jq . logs/swing_scanner_YYYY-MM-DD.log
```

### Analysis Commands

```bash
# Count logs by service
jq -r '.service' logs/*.log | sort | uniq -c

# Count logs by level
jq -r '.level' logs/*.log | sort | uniq -c

# Find all errors
jq 'select(.level == "ERROR")' logs/*.log

# Find all warnings
jq 'select(.level == "WARNING")' logs/*.log

# Get performance data (response times)
jq 'select(.data.duration_ms) | .data.duration_ms' logs/*.log | sort -n

# Show slowest operations
jq 'select(.data.duration_ms) | {message, duration: .data.duration_ms}' logs/*.log | sort -rn -k3
```

---

## Key Logging Points

### Swing Scanner Logs

#### 1. Scanner Initialization
```json
{
  "message": "Swing scanner started",
  "data": { "phase": "initialization" },
  "level": "INFO"
}
```

#### 2. Grade Assignment (Stock Passed Filters)
```json
{
  "message": "Stock grade assigned: {ticker}",
  "data": {
    "ticker": "005930.KS",
    "code": "005930",
    "grade": "강매",
    "score": 125,
    "target": "70000",
    "stop": "60000",
    "rvolVal": "3.45",
    "dailyChange": "5.2%",
    "signals": "RSI,ADX,RVOL"
  },
  "level": "INFO"
}
```
**When to see**: Every stock that passes grade assignment stage

#### 3. Successful Notification Send
```json
{
  "message": "Stock notification sent: {ticker}",
  "data": {
    "ticker": "005930.KS",
    "grade": "강매",
    "entry": "66500",
    "target": "70000",
    "stop": "60000",
    "rankScore": 125
  },
  "level": "INFO"
}
```
**When to see**: Stock notification successfully sent to Telegram

#### 4. Failed Notification Send
```json
{
  "message": "Failed to send notification: {ticker}",
  "data": {
    "ticker": "005930.KS",
    "grade": "강매",
    "error": "HTTP 429: Too Many Requests"
  },
  "level": "ERROR"
}
```
**When to see**: Telegram API error (rate limit, connection, etc.)

#### 5. Scanner Completion
```json
{
  "message": "Swing scanner completed",
  "data": {
    "scanTime": "2026-04-19T09:15:00.000Z",
    "totalUniverse": 1500,
    "candidates": 45,
    "sent": 3,
    "sentTickers": "005930.KS,000660.KS,035720.KS",
    "excludedRisk": 12,
    "excludedTheme": 8,
    "naverApiStats": { "ok": 1500, "noResult": 0, "error": 2 }
  },
  "level": "INFO"
}
```
**When to see**: End of scanner execution (always)

---

### Position Monitor Logs

#### 1. Monitor Initialization
```json
{
  "message": "Position monitor started",
  "data": { "phase": "initialization" },
  "level": "INFO"
}
```

#### 2. Position Monitoring Start
```json
{
  "message": "Position monitoring started",
  "data": {
    "today": "2026-04-19",
    "activePositions": 5,
    "positions": "005930(강매),000660(급등),035720(매도차익),051910(급등),122190(매도차익)"
  },
  "level": "INFO"
}
```
**When to see**: Start of position monitoring (if positions exist)

#### 3. No Active Positions
```json
{
  "message": "No active positions found",
  "data": {
    "today": "2026-04-19",
    "message": "활성 포지션 없음"
  },
  "level": "INFO"
}
```
**When to see**: No positions to monitor (early exit)

#### 4. Stop Level Raised (Key Event!)
```json
{
  "message": "Stop level raised: 005930",
  "data": {
    "code": "005930",
    "ticker": "005930.KS",
    "grade": "강매",
    "currentPrice": 67500,
    "gain": "+2.3%",
    "oldStop": "60000",
    "newStop": "62500",
    "atr": "3200"
  },
  "level": "INFO"
}
```
**When to see**: Position is profitable and stop is being trailed up

#### 5. Monitor Completion
```json
{
  "message": "Position monitoring completed",
  "data": {
    "today": "2026-04-19",
    "activePositions": 5,
    "updated": 2,
    "alertsSent": 2
  },
  "level": "INFO"
}
```
**When to see**: End of position monitoring (daily)

---

### Weekly Reporter Logs

#### 1. Reporter Initialization
```json
{
  "message": "Weekly reporter started",
  "data": { "phase": "initialization" },
  "level": "INFO"
}
```

#### 2. Weekly Statistics
```json
{
  "message": "Weekly report generated",
  "data": {
    "reportDate": "2026-04-19",
    "totalPositions": 47,
    "wins": 18,
    "partialWins": 8,
    "losses": 12,
    "holding": 9,
    "winRate": "55.1%",
    "enteredCount": 38
  },
  "level": "INFO"
}
```
**When to see**: Report statistics calculated

#### 3. Report Sent
```json
{
  "message": "Weekly report sent",
  "data": {
    "reportDate": "2026-04-19",
    "messageChunks": 1,
    "totalChars": 2847,
    "positions": 47,
    "enteredCount": 38
  },
  "level": "INFO"
}
```
**When to see**: Report successfully sent to Telegram

---

## QA Monitoring Workflow

### Daily Morning (Before/During Scanner)

1. Start log monitoring:
   ```bash
   tail -f logs/swing_scanner_*.log
   ```

2. Look for:
   - Grade assignments (how many stocks pass?)
   - Send successes (notifications working?)
   - Send failures (API issues?)
   - Final scan stats (expected universe size?)

3. Check JSON format:
   ```bash
   cat logs/swing_scanner_*.log | jq . | head -50
   ```

### Daily Afternoon (Position Monitor)

1. Check positions:
   ```bash
   tail -f logs/position_monitor_*.log
   ```

2. Look for:
   - How many positions are active?
   - Are stops being trailed up?
   - Any errors in price fetching?

### Weekly Report (Weekend)

1. Check report generation:
   ```bash
   tail -f logs/weekly_reporter_*.log
   ```

2. Verify:
   - Win rate calculated correctly
   - Total positions match
   - Report sent successfully

---

## Performance Monitoring

### Check Average Response Times

```bash
# Naver API response times
jq '.data.duration_ms' logs/swing_scanner_*.log | \
  awk '{sum+=$1; count++} END {print "Average:", sum/count, "ms"}'
```

### Find Slow Operations (>2 seconds)

```bash
jq 'select(.data.duration_ms > 2000) | 
    {message, duration: .data.duration_ms, service}' \
  logs/*.log
```

### API Statistics

```bash
jq '.data.naverApiStats' logs/swing_scanner_*.log | tail -1 | jq .
```

---

## Error Detection

### Find All Errors

```bash
grep '"level":"ERROR"' logs/*.log | jq .
```

### Group Errors by Type

```bash
grep '"level":"ERROR"' logs/*.log | \
  jq -r '.message' | sort | uniq -c | sort -rn
```

### Track Error Timeline

```bash
grep '"level":"ERROR"' logs/*.log | \
  jq '{timestamp, message, error: .data.error}' | less
```

---

## Request ID Tracing

### Trace Single Request

```bash
# Find a request ID first
REQUEST_ID="trading_202604190915"

# Trace all logs for this request
grep "$REQUEST_ID" logs/*.log | jq .
```

### Timeline for Request

```bash
REQUEST_ID="trading_202604190915"
grep "$REQUEST_ID" logs/*.log | \
  jq '{timestamp, service, message, level}' | \
  jq -s 'sort_by(.timestamp)' | jq .
```

---

## Expected Log Patterns

### Healthy Scanner Run

```
1. "Swing scanner started" — INFO
2. Multiple "Stock grade assigned" entries — INFO
3. Multiple "Stock notification sent" entries — INFO
4. Few/no "Failed to send notification" — ERROR (OK if <5%)
5. "Swing scanner completed" — INFO
   - Should show: sent > 0, candidates > 0, errors < 5%
```

### Healthy Position Monitor Run

```
1. "Position monitor started" — INFO
2. "Position monitoring started" or "No active positions" — INFO
3. Multiple "Stop level raised" entries (if profitable) — INFO
4. "Position monitoring completed" — INFO
```

### Healthy Weekly Report Run

```
1. "Weekly reporter started" — INFO
2. "Weekly report generated" — INFO
   - Should show: win rate > 40%, enteredCount > 0
3. "Weekly report sent" — INFO
```

---

## Troubleshooting

### No Logs Appearing

```bash
# Check if logs directory exists
ls -la logs/

# Check if files have content
wc -l logs/*.log

# Check if they're being written
tail -1 logs/swing_scanner_*.log
```

### Invalid JSON in Logs

```bash
# Test parsing entire log
jq . logs/swing_scanner_*.log > /dev/null

# Find bad lines
while IFS= read -r line; do 
  jq . <<< "$line" > /dev/null || echo "Bad: $line"
done < logs/swing_scanner_*.log
```

### Missing Request IDs

```bash
# Check if request_id is in all logs
jq 'select(.request_id == "N/A")' logs/*.log | wc -l
```

### Performance Issues

```bash
# Find operations taking >5 seconds
jq 'select(.data.duration_ms > 5000) | 
    {timestamp, message, duration: .data.duration_ms}' \
  logs/*.log | jq -s 'sort_by(.duration) | reverse'
```

---

## Best Practices

1. **Always parse with jq**: Ensures valid JSON
2. **Check timestamps**: Understand execution timeline
3. **Track request IDs**: Trace complete flows
4. **Monitor levels**: INFO = normal, ERROR = problems
5. **Check service names**: Understand which component logged
6. **Review data fields**: Verify expected metrics are present
7. **Set up alerts**: Monitor for ERROR level entries
8. **Rotate logs**: Keep ~7 days of logs (auto-cleaned by filename)

---

## Commands Reference

```bash
# Most useful commands for daily use:

# Live tail of all logs
tail -f logs/*.log

# Watch scanner only
tail -f logs/swing_scanner_*.log

# Parse today's scanner logs
jq . logs/swing_scanner_$(date +%Y-%m-%d).log

# Count sent notifications
grep "Stock notification sent" logs/swing_scanner_*.log | wc -l

# Find all errors
grep '"level":"ERROR"' logs/*.log | jq .

# Get last entry timestamp
tail -1 logs/swing_scanner_*.log | jq .timestamp

# Watch in real-time with parsing
tail -f logs/swing_scanner_*.log | while IFS= read -r line; do jq . <<< "$line"; done
```

---

## Next Steps

1. Execute first test run
2. Monitor with these commands
3. Verify log structure is correct
4. Check for any missing data
5. Refine logging as needed

---

**Last Updated**: 2026-04-19  
**Version**: 1.0  
**Status**: Ready for QA monitoring
