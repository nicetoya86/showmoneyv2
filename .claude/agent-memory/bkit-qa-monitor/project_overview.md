---
name: Project Overview - showmoneyv2
description: Stock trading automation system with swing algorithm, multiple components running as cron jobs and daily services
type: project
---

## What is showmoneyv2?

**showmoneyv2** is a sophisticated **stock trading automation system** designed to identify and trade swing opportunities in Korean stock markets (KRX).

### Core Components

#### 1. Swing Scanner (`swing_scanner_code.js`)
- Real-time analysis of stock candidates
- Scoring algorithm based on:
  - ATR (Average True Range) targets
  - OBV (On Balance Volume) supply/demand
  - Price proximity to 52-week highs
  - Day-of-week adjustments
  - Multiple grade classifications (강매/Forced Buy, 매도차익/Short Trade Profit, etc.)
- Hold period management (2-5 trading days based on grade)
- Recently improved (2026-04-18):
  - ATR target multipliers by grade (2.8x for forced buy, 1.5x for short trade, 2.0x normal)
  - Hold periods extended (2→3 days for surge and short trade)
  - OBV supply/demand requirements added
  - High proximity scoring adjusted (25→15, 15→8)

#### 2. Position Monitor (`Daily_Position_Monitor.js`)
- Monitors current positions
- Tracks P&L (Profit & Loss)
- Manages position lifecycle

#### 3. Weekly Reporter (`weekly_reporter_code.js`)
- Generates weekly trading summaries
- Performance tracking across time periods

#### 4. Support Services
- Risk/blacklist management
- Theme-based filtering
- Cron job scheduling

### Environment
- **Language**: JavaScript/Node.js
- **Data Source**: Korean stock market data (Naver, KRX APIs)
- **Execution**: Scheduled cron jobs + daily monitoring
- **Database**: JSON-based state files (likely in .bkit/state/ based on bkit v1.5.8 structure)

### Key Recent Activity (2026-04-18 to 2026-04-19)
- Swing algorithm improvements completed (7 items per plan)
- Analysis document generated confirming 100% match rate with plan
- Two new workflow JSON files created (indicating testing/analysis cycles)

### Testing State
- Code passes plan verification (100% match)
- Running in production/staging environment
- Need to establish comprehensive QA monitoring during the next test cycle

---

## Why Zero Script QA Matters Here

This project has:
1. **Complex business logic** — Multiple scoring algorithms, conditional branches
2. **Time-dependent behavior** — Day-of-week bonuses, hold period tracking
3. **Real data dependencies** — Fetching live market data
4. **Multiple operational components** — Cron jobs that can fail independently
5. **P&L sensitive** — Incorrect logic directly impacts trading profit/loss

**Zero Script QA approach**:
- Monitor trading engine logs during actual algorithm execution
- Track entire flow of a stock from discovery → position management → exit
- Detect when scoring logic produces unexpected grades or scores
- Catch timing issues (incorrect day-of-week detection, hold period miscalculation)
- Alert on data fetch failures before they cause trades

---

## Current Logging State

As of 2026-04-19:
- **Logging infrastructure**: Not yet structured as JSON with Request ID propagation
- **Current logs**: Using standard console.log() in JS files
- **Monitoring capability**: Manual/ad-hoc, not real-time structured

**Gap**: Need to add:
1. JSON-structured logging with timestamps
2. Request ID propagation through trading flows
3. Real-time monitoring hooks for docker compose logs
4. Automatic error detection and issue documentation
