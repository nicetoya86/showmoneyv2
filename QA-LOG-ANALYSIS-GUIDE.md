# QA Log Analysis Guide

**Created**: 2026-05-07  
**Version**: 1.0.0  
**Target Audience**: QA Analysts, Developers

---

## Table of Contents

1. [Log File Overview](#log-file-overview)
2. [Analysis Commands](#analysis-commands)
3. [Pattern Recognition](#pattern-recognition)
4. [Performance Analysis](#performance-analysis)
5. [Error Investigation](#error-investigation)
6. [Grade Distribution Analysis](#grade-distribution-analysis)
7. [Request ID Tracing](#request-id-tracing)
8. [Trend Analysis](#trend-analysis)
9. [Report Generation](#report-generation)

---

## Log File Overview

### Log Directory Structure

```
logs/
├── swing_scanner_2026-05-07.log        # Daily swing scanner logs
├── position_monitor_2026-05-07.log     # Daily position monitor logs
├── daily_healthcheck_2026-05-07.log    # Daily health check logs
├── weekly_reporter_2026-05-07.log      # Weekly reporter logs
└── archived/                            # Old logs (optional)
    └── swing_scanner_2026-05-01.log
```

### Log File Size & Rotation

```
Typical daily logs:
- swing_scanner:    2-4 MB
- position_monitor: 0.5-1 MB
- daily_healthcheck: 0.1-0.2 MB
- Total:            2.6-5.2 MB per day

Recommendation: Archive logs > 30 days old
```

---

## Analysis Commands

### 1. Basic Log Exploration

#### Count Total Logs
```bash
# All logs
cat logs/*.log | wc -l

# By service
grep -c '"service":"swing_scanner"' logs/*.log
grep -c '"service":"position_monitor"' logs/*.log

# By level
grep -c '"level":"ERROR"' logs/*.log
grep -c '"level":"WARNING"' logs/*.log
grep -c '"level":"INFO"' logs/*.log
```

#### Show First/Last Entries
```bash
# First 5 logs (chronologically)
head -5 logs/swing_scanner_*.log | jq .

# Last 5 logs
tail -5 logs/swing_scanner_*.log | jq .

# Specific date range
grep '2026-05-07T10:3[0-5]' logs/*.log | jq .
```

### 2. Filtering & Searching

#### Filter by Log Level
```bash
# All errors
jq 'select(.level == "ERROR")' logs/*.log

# All warnings
jq 'select(.level == "WARNING")' logs/*.log

# All info (exclude debug)
jq 'select(.level == "INFO" or .level == "WARNING" or .level == "ERROR")' logs/*.log
```

#### Filter by Service
```bash
# Only swing_scanner
jq 'select(.service == "swing_scanner")' logs/*.log

# Only position_monitor
jq 'select(.service == "position_monitor")' logs/*.log
```

#### Filter by Message Type
```bash
# Grade calculations
grep '"message":"Grade calculated"' logs/*.log | jq .

# Position evaluations
grep '"message":"Position evaluated"' logs/*.log | jq .

# Analysis start/end
grep -E '"message":"(Starting|Analysis completed)"' logs/*.log
```

### 3. Advanced Filtering

#### Find Logs with Specific Data
```bash
# Grade = 강매
jq 'select(.data.grade == "강매")' logs/*.log

# Duration > 1000ms
jq 'select(.data.duration_ms > 1000)' logs/*.log

# Specific stock
jq 'select(.data.stock_code == "005930")' logs/*.log

# Profit > 5%
jq 'select(.data.profit_loss_pct > 5)' logs/*.log
```

#### Complex Filters
```bash
# Errors with stock code
jq 'select(.level == "ERROR" and .data.stock_code != null)' logs/*.log

# Slow errors (duration + error)
jq 'select(.level == "ERROR" and .data.duration_ms > 500)' logs/*.log

# Recent errors (last hour)
jq "select(.level == \"ERROR\" and .timestamp > \"2026-05-07T15:00:00\")" logs/*.log
```

---

## Pattern Recognition

### 1. Error Patterns

#### Identify Error Types
```bash
# Group errors by message
grep '"level":"ERROR"' logs/*.log | \
  jq -r '.message' | sort | uniq -c | sort -rn

# Output example:
#   5 Failed to fetch stock data
#   3 Grade calculation failed
#   2 Telegram send error
```

#### Find Recurring Errors
```bash
# Errors in last 24 hours
grep '"level":"ERROR"' logs/*.log | \
  jq -r '.message' | sort | uniq -c | sort -rn | head -10
```

#### Error Impact Analysis
```bash
# Which stocks have errors
grep '"level":"ERROR"' logs/*.log | \
  jq -r '.data.stock_code' | sort | uniq -c | sort -rn

# Output: Shows which stocks are problematic
```

### 2. Performance Patterns

#### Identify Slow Operations
```bash
# Operations over 1000ms
grep -E '"duration_ms":[0-9]+' logs/*.log | \
  jq 'select(.data.duration_ms > 1000)' | \
  jq -r '[.message, .data.duration_ms] | @csv'

# Output: Slowest operations listed
```

#### Duration Distribution
```bash
# Get all durations
grep -E '"duration_ms":[0-9]+' logs/*.log | \
  jq -r '.data.duration_ms' | sort -n

# Statistics
grep -E '"duration_ms":[0-9]+' logs/*.log | \
  jq -r '.data.duration_ms' | \
  awk '{sum+=$1; count++; if (NR==1 || $1<min) min=$1; if (NR==1 || $1>max) max=$1} END {print "Min:"min", Max:"max", Avg:"int(sum/count)}'
```

### 3. Grade Distribution Patterns

#### Get Grade Distribution
```bash
# Count by grade
grep '"message":"Grade calculated"' logs/*.log | \
  jq -r '.data.grade' | sort | uniq -c

# Output:
#  38 강매
#  72 급등
# 138 매도차익
# 252 기타
```

#### Grade Percentage
```bash
# With percentages
grep '"message":"Grade calculated"' logs/*.log | \
  jq -r '.data.grade' | sort | uniq -c | \
  awk '{total+=$1; grades[$2]=$1} END {for (g in grades) printf "%s: %.1f%%\n", g, (grades[g]/total)*100}' | sort
```

#### Grade Anomalies
```bash
# Find stocks with unusual grades
# E.g., multiple same-grade reports for single stock
grep '"message":"Grade calculated"' logs/*.log | \
  jq -r '[.data.stock_code, .data.grade] | @csv' | \
  sort | uniq -c | sort -rn | \
  awk '$1 > 1' # Shows duplicates
```

---

## Performance Analysis

### 1. Duration Metrics

#### Calculate Performance Statistics
```bash
# Using awk for statistics
grep -E '"duration_ms":[0-9]+' logs/*.log | \
  jq -r '.data.duration_ms' | \
  awk '{
    sum += $1
    count++
    if (NR==1 || $1<min) min=$1
    if (NR==1 || $1>max) max=$1
    arr[NR] = $1
  }
  END {
    asort(arr)
    print "Count: " count
    print "Min: " min "ms"
    print "Max: " max "ms"
    print "Avg: " int(sum/count) "ms"
    print "P50: " arr[int(count*0.5)] "ms"
    print "P95: " arr[int(count*0.95)] "ms"
  }'
```

#### Performance by Service
```bash
# Swing scanner performance
grep '"service":"swing_scanner"' logs/*.log | \
  jq -r '.data.duration_ms' | \
  awk '{sum+=$1; count++} END {print "Avg duration: "int(sum/count)"ms"}'

# Position monitor performance
grep '"service":"position_monitor"' logs/*.log | \
  jq -r '.data.duration_ms' | \
  awk '{sum+=$1; count++} END {print "Avg duration: "int(sum/count)"ms"}'
```

### 2. Throughput Metrics

#### Logs Per Minute
```bash
# Count logs per minute
grep -oE '2026-05-07T[0-9]{2}:[0-9]{2}' logs/*.log | sort | uniq -c

# Output:
# 145 2026-05-07T10:00
# 198 2026-05-07T10:01
# 167 2026-05-07T10:02
```

#### Stocks Processed Per Hour
```bash
# Count unique stocks per hour
grep '"message":"Grade calculated"' logs/*.log | \
  grep '2026-05-07T10:[0-5][0-9]' | \
  jq -r '.data.stock_code' | sort -u | wc -l
```

### 3. Optimization Opportunities

#### Find Operations > 2x Baseline
```bash
# Baseline: 78ms (from first monitoring)
# Alert if > 156ms (2x)
grep -E '"duration_ms":[0-9]+' logs/*.log | \
  jq 'select(.data.duration_ms > 156)' | \
  jq -r '[.message, .data.duration_ms, .data.stock_code] | @csv' | \
  head -20
```

---

## Error Investigation

### 1. Error Discovery

#### Comprehensive Error Report
```bash
# All errors with context
grep '"level":"ERROR"' logs/*.log | \
  jq -r '[.timestamp, .service, .message, .request_id, .data.stock_code] | @csv' | \
  column -t -s','

# Output table format
```

#### Error Timeline
```bash
# Show errors chronologically
grep '"level":"ERROR"' logs/*.log | \
  jq -r '.timestamp + " - " + .message' | \
  sort
```

### 2. Error Clustering

#### Errors by Service
```bash
# Count errors per service
grep '"level":"ERROR"' logs/*.log | \
  jq -r '.service' | sort | uniq -c | sort -rn
```

#### Errors by Time of Day
```bash
# When do errors occur most?
grep '"level":"ERROR"' logs/*.log | \
  grep -oE 'T[0-9]{2}:[0-9]{2}' | \
  sort | uniq -c | sort -rn
```

#### Errors by Stock
```bash
# Which stocks cause most errors?
grep '"level":"ERROR"' logs/*.log | \
  jq -r '.data.stock_code // "UNKNOWN"' | \
  sort | uniq -c | sort -rn | head -10
```

### 3. Root Cause Investigation

#### Trace Full Request Flow
```bash
# For request ID: trading_20260507103045_005930
REQUEST_ID="trading_20260507103045_005930"
grep "$REQUEST_ID" logs/*.log | jq -r '[.timestamp, .level, .message, .data] | @json'
```

#### Before/After Log Context
```bash
# Get 5 lines before and after error
grep -B5 -A5 '"level":"ERROR"' logs/swing_scanner_*.log | jq .
```

---

## Grade Distribution Analysis

### 1. Basic Distribution

#### Current Distribution
```bash
# Simple distribution
grep '"message":"Grade calculated"' logs/*.log | \
  jq -r '.data.grade' | sort | uniq -c | \
  awk '{printf "%s: %d (%.1f%%)\n", $2, $1, ($1/NR)*100}'
```

#### Expected vs Actual
```bash
# Expected ranges
# 강매: 5-10%
# 급등: 10-15%
# 매도차익: 20-30%
# 기타: 50-70%

# Check if within range
grep '"message":"Grade calculated"' logs/*.log | \
  jq -r '.data.grade' | sort | uniq -c | \
  awk '{
    grade=$2; count=$1
    pct=(count/2000)*100  # assuming 2000 total
    
    if (grade == "강매" && pct >= 5 && pct <= 10) status="✓"
    else if (grade == "강매") status="✗"
    else if (grade == "급등" && pct >= 10 && pct <= 15) status="✓"
    else if (grade == "급등") status="✗"
    else if (grade == "매도차익" && pct >= 20 && pct <= 30) status="✓"
    else if (grade == "매도차익") status="✗"
    else if (grade == "기타" && pct >= 50 && pct <= 70) status="✓"
    else status="✗"
    
    printf "%s: %d (%.1f%%) %s\n", grade, count, pct, status
  }'
```

### 2. Grade Quality Analysis

#### Average Score by Grade
```bash
# Score breakdown
grep '"message":"Grade calculated"' logs/*.log | \
  jq -r '[.data.grade, .data.score] | @csv' | \
  awk -F, '{
    grade=$1; score=$2
    sum[grade] += score
    count[grade]++
  }
  END {
    for (g in count) printf "%s: avg=%.0f (n=%d)\n", g, sum[g]/count[g], count[g]
  }'
```

#### Score Distribution
```bash
# Score statistics per grade
grep '"message":"Grade calculated"' logs/*.log | \
  jq -r '[.data.grade, .data.score] | @csv' | \
  awk -F, '{
    grade=$1; score=$2
    scores[grade][NR] = score
  }
  END {
    for (g in scores) {
      for (s in scores[g]) sum[g] += scores[g][s]
      printf "%s: min=%d, max=%d, avg=%.0f\n", 
        g, min[g], max[g], sum[g]/length(scores[g])
    }
  }'
```

---

## Request ID Tracing

### 1. Single Request Trace

#### View Complete Request Flow
```bash
# Extract all logs for single request
REQUEST_ID="trading_20260507103045_005930"
jq "select(.request_id == \"$REQUEST_ID\")" logs/*.log | \
  jq -r '[.timestamp, .level, .service, .message] | @csv'

# Output shows complete flow:
# 2026-05-07T10:30:45.000Z,INFO,swing_scanner,Starting stock analysis
# 2026-05-07T10:30:45.450Z,INFO,swing_scanner,Grade calculated
# 2026-05-07T10:30:45.500Z,INFO,swing_scanner,Analysis completed
```

### 2. Multi-Request Tracing

#### Request Success Rate
```bash
# Count requests by outcome
grep '"message":"Analysis completed"' logs/*.log | \
  jq -r '.request_id' | wc -l  # Successful

grep '"message":"Grade calculated"' logs/*.log | \
  jq -r '.request_id' | sort -u | wc -l  # Total initiated
```

#### Request ID Format Validation
```bash
# Verify format: trading_YYYYMMDDHHMMSS_CODE
grep '"request_id"' logs/*.log | \
  grep -v '"request_id":"trading_[0-9]\{14\}_' | \
  jq .request_id  # Shows invalid IDs
```

---

## Trend Analysis

### 1. Daily Trends

#### Compare Days
```bash
# Performance: Day 1 vs Day 2
echo "=== 2026-05-06 ==="
grep '"duration_ms"' logs/swing_scanner_2026-05-06.log | jq '.data.duration_ms' | awk '{sum+=$1; count++} END {print "Avg: "int(sum/count)"ms"}'

echo "=== 2026-05-07 ==="
grep '"duration_ms"' logs/swing_scanner_2026-05-07.log | jq '.data.duration_ms' | awk '{sum+=$1; count++} END {print "Avg: "int(sum/count)"ms"}'
```

#### Error Trend
```bash
# Error count over days
for file in logs/swing_scanner_*.log; do
  date=$(basename $file | grep -oE '2026-[0-9]{2}-[0-9]{2}')
  errors=$(grep -c '"level":"ERROR"' $file)
  echo "$date: $errors errors"
done | sort
```

### 2. Weekly Trends

#### Weekly Performance
```bash
# Aggregate by week
# Week of 2026-05-05 to 2026-05-11
grep -h '2026-05-0[5-9]\|2026-05-1[01]' logs/*.log | \
  jq -r '.data.duration_ms' | \
  awk '{sum+=$1; count++} END {print "Week Avg: "int(sum/count)"ms"}'
```

#### Grade Trend
```bash
# Grade distribution change
echo "=== Week 1 ===" 
grep '2026-05-01\|2026-05-02\|2026-05-03\|2026-05-04' logs/swing_scanner_*.log | \
  jq -r '.data.grade' | sort | uniq -c

echo "=== Week 2 ==="
grep '2026-05-08\|2026-05-09\|2026-05-10\|2026-05-11' logs/swing_scanner_*.log | \
  jq -r '.data.grade' | sort | uniq -c
```

---

## Report Generation

### 1. Daily Report

```bash
#!/bin/bash
# daily-qa-report.sh

echo "📊 Daily QA Report - $(date +%Y-%m-%d)"
echo "=================================="
echo ""

# 1. Summary Statistics
echo "📈 Summary:"
TOTAL=$(cat logs/*.log | wc -l)
ERRORS=$(grep -c '"level":"ERROR"' logs/*.log)
echo "  Total Logs: $TOTAL"
echo "  Errors: $ERRORS"
echo "  Error Rate: $(echo "scale=2; $ERRORS * 100 / $TOTAL" | bc)%"

# 2. Performance
echo ""
echo "⚡ Performance:"
grep -E '"duration_ms":[0-9]+' logs/*.log | \
  jq -r '.data.duration_ms' | \
  awk '{sum+=$1; count++; if (NR==1 || $1<min) min=$1; if (NR==1 || $1>max) max=$1} END {print "  Avg: "int(sum/count)"ms, Min: "min"ms, Max: "max"ms"}'

# 3. Grade Distribution
echo ""
echo "🎯 Grades:"
grep '"message":"Grade calculated"' logs/swing_scanner_*.log | \
  jq -r '.data.grade' | sort | uniq -c | \
  awk '{printf "  %s: %d\n", $2, $1}'

# 4. Top Errors
echo ""
echo "⚠️  Top Errors:"
grep '"level":"ERROR"' logs/*.log | \
  jq -r '.message' | sort | uniq -c | sort -rn | head -5 | \
  awk '{printf "  %s: %d\n", $2, $1}'

echo ""
echo "=================================="
```

### 2. Weekly Summary Template

```markdown
# Weekly QA Report - Week of 2026-05-05

## Summary
- **Total Logs**: 62,500
- **Errors**: 2 (0.003% error rate)
- **Warnings**: 15
- **Avg Performance**: 82ms
- **Status**: ✅ HEALTHY

## Performance Metrics
| Metric | Value | Baseline | Status |
|--------|-------|----------|--------|
| Avg Duration | 82ms | 78ms | ↑ 5% |
| Min Duration | 15ms | 18ms | ✓ |
| Max Duration | 420ms | 450ms | ✓ |
| P95 Duration | 220ms | 250ms | ✓ |

## Grade Distribution
| Grade | Count | % | Range |
|-------|-------|---|-------|
| 강매 | 465 | 7.8% | 5-10% ✓ |
| 급등 | 870 | 14.6% | 10-15% ✓ |
| 매도차익 | 1560 | 26.2% | 20-30% ✓ |
| 기타 | 3105 | 52.1% | 50-70% ✓ |

## Issues Found
1. **Minor**: 2 slow operations (> 300ms) - No action required
2. **Info**: Grade distribution normal

## Recommendations
- Continue monitoring performance trend
- No optimization needed this week
- Maintain current configuration
```

---

## Quick Reference Scripts

### Performance Report
```bash
#!/bin/bash
grep -E '"duration_ms":[0-9]+' logs/*.log | \
  jq -s '[.[] | .data.duration_ms] | {
    count: length,
    min: min,
    max: max,
    avg: (add / length | round),
    p50: (sort | .[length/2]),
    p95: (sort | .[length*0.95|floor])
  }' | jq .
```

### Error Report
```bash
#!/bin/bash
grep '"level":"ERROR"' logs/*.log | \
  jq -s 'group_by(.message) | map({
    message: .[0].message,
    count: length,
    services: [.[].service] | unique,
    stocks: [.[].data.stock_code] | unique
  }) | sort_by(.count) | reverse'
```

### Grade Report
```bash
#!/bin/bash
grep '"message":"Grade calculated"' logs/*.log | \
  jq -s 'group_by(.data.grade) | map({
    grade: .[0].data.grade,
    count: length,
    avg_score: (map(.data.score) | add / length | round),
    min_score: (map(.data.score) | min),
    max_score: (map(.data.score) | max)
  })'
```

---

**These commands and scripts form the foundation of daily QA analysis. Customize as needed for your monitoring needs.**
