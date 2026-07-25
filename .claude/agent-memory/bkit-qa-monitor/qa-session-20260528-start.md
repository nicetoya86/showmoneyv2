---
name: QA Session 2026-05-28 Start
description: Real-time QA monitoring session initiated for showmoneyv2 trading system
metadata:
  type: project
---

# Zero Script QA Monitoring Session - 2026-05-28

**Session Start**: 2026-05-28 (Current Date)
**Status**: ACTIVE
**Objective**: Real-time monitoring and analysis of showmoneyv2 trading automation system

## Session Context

### Project State
- **Latest commit** (ac1add6): swing-scanner-v5 — 수익 포착 정확도 개선 3항목 (조건 충돌/과잉 차단 해소)
- **System**: Stock trading automation with swing algorithm scanner
- **Components**: swing_scanner_code.js, Daily_Position_Monitor.js, weekly_reporter_code.js
- **Recent Activity**: Risk-blacklist and swing-scanner fixes (last 5 commits)

### Infrastructure Status
- **Logger Module**: ✅ JsonLogger fully integrated (`lib/logger.js`)
- **JSON Compliance**: ✅ 100% valid JSON format
- **Request ID**: ✅ Active (format: `trading_YYYYMMDDHHMMSS_STOCKCODE`)
- **Last Validation**: 2026-04-23 (9/9 tests passed)

### Monitoring Readiness
- **Log Format**: ✅ Structured JSON with all required fields
- **Request Tracing**: ✅ Full flow tracking by stock code and timestamp
- **Real-time Capability**: ✅ Ready for docker compose logs monitoring
- **Error Detection**: ✅ Patterns configured for trading-specific issues

---

## Monitoring Scope

### What to Monitor
1. **Swing Scanner Output**
   - Stock analysis completion
   - Grade calculations (강매, 매도차익, 강보, etc.)
   - Score values and thresholds
   - Error handling for data fetch failures

2. **Position Monitor Activity**
   - Position entry logging
   - P&L tracking
   - Position exit/hold decisions
   - Data consistency checks

3. **Risk Management**
   - Blacklist application
   - Grade filtering logic
   - Risk thresholds enforcement

4. **Performance Metrics**
   - Analysis duration (target: <1000ms per stock)
   - Data fetch latency
   - Processing overhead

### Critical Thresholds

| Item | Warning | Critical |
|------|---------|----------|
| Stock analysis duration | >1000ms | >3000ms |
| Data fetch failure | ⚠️ Log warning | 🔴 Stop analysis |
| Grade calc mismatch | ⚠️ Flag pattern | 🔴 Review logic |
| P&L calc error | ⚠️ Manual review | 🔴 Position risk |

---

## Session Workflow

### Phase 1: Environment Verification (Current)
- [x] Check project structure
- [x] Verify logger integration
- [x] Review recent commits
- [ ] Confirm all n8n nodes have logging
- [ ] Test request ID propagation

### Phase 2: Real-time Monitoring
- [ ] Stream docker compose logs (if available)
- [ ] Monitor for ERROR level logs
- [ ] Track slow operations (>1000ms)
- [ ] Validate request ID consistency
- [ ] Collect sample flows for analysis

### Phase 3: Issue Analysis
- [ ] Identify patterns in logs
- [ ] Classify by severity
- [ ] Trace root causes
- [ ] Document findings

### Phase 4: Recommendations
- [ ] Suggest improvements
- [ ] Priority fixes
- [ ] Prevention strategies

---

## Expected Log Analysis Patterns

### Normal Operations
```json
{
  "timestamp": "2026-05-28T10:30:00.000Z",
  "level": "INFO",
  "service": "swing_scanner",
  "request_id": "trading_20260528103000_005930",
  "message": "Stock analysis completed",
  "data": {
    "stock_code": "005930",
    "grade": "강매",
    "score": 125,
    "duration_ms": 450
  }
}
```

### Error Pattern (to detect)
```json
{
  "level": "ERROR",
  "message": "Stock analysis failed",
  "data": {
    "error": "Data fetch timeout",
    "stock_code": "005930"
  }
}
```

### Slow Operation Pattern (to detect)
```json
{
  "data": {
    "duration_ms": 2500
  }
}
```

---

## Commands for Monitoring

```bash
# Stream all logs
docker compose logs -f

# Filter ERROR logs only
docker compose logs -f | grep '"level":"ERROR"'

# Track specific stock code
docker compose logs -f | grep 'trading_20260528.*005930'

# Find slow operations (>1000ms)
docker compose logs -f | grep -E '"duration_ms":[0-9]{4,}'

# Save logs to file for analysis
docker compose logs > qa_logs_20260528.txt
```

---

## Session Notes

- Previous session (2026-05-15) confirmed all systems operational with 0% error rate
- Recent fixes focus on swing-scanner accuracy and risk-blacklist KRX API issues
- System ready for production monitoring
- All logging infrastructure in place and validated

**Next Steps**:
1. Await user's testing activity
2. Monitor logs in real-time
3. Document any issues found
4. Provide analysis with fixes

