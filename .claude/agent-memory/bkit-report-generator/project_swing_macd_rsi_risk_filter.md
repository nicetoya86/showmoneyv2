---
name: swing-macd-rsi-risk-filter Feature Completion
description: PDCA completion for MACD/RSI indicator strengthening and risk filter activation; 100% Match Rate; critical Logger bug fixed during implementation
type: project
---

## Feature Overview

**Name:** swing-macd-rsi-risk-filter  
**Completed:** 2026-04-19  
**Match Rate:** 100% (20/20 sub-items)  
**PDCA Phases:** Plan → Design → Do → Check (no Act iteration needed)

## What Was Delivered

### Core Algorithm Changes (5 items)

1. **CONST-01**: Added 3 constants — RSI_RISING_BONUS=10, DELIST_CONSEC_DOWN=5, DELIST_VOL_DROP=0.3
2. **THEME-01**: Theme filter default 'off' → 'on' (Line 426)
3. **DELIST-01**: 5-day consecutive down + 30% volume drop pattern detection (Lines 1001-1010)
4. **RSI-01**: RSI directional momentum check (5-day prior vs current) + +10 bonus if rising (Lines 1086-1092)
5. **MACD-01**: Continuous MACD histogram decline → hard block except for grade='강매' (Lines 1243-1247)

### Critical Bug Fixed (During Do phase)

**Logger require() crash in n8n sandbox:**
- `/zero-script-qa` had added top-level `require('./lib/logger')` 
- n8n Function node sandbox prohibits local file requires → MODULE_NOT_FOUND → entire scanning function crashed before any stock processed
- **Impact without fix:** 100% scanning failure, 0 Telegram messages
- **Fix applied:** Lines 72-82, try/catch wrapper + no-op logger fallback

## Simulation Results

Backtesting 200 KOSPI/KOSDAQ tickers showed improvement:
- Median PnL: -1.53% → +0.27% (+1.80pp)
- Stop-loss rate: 45.6% → 41.5% (-4.1pp)
- Max drawdown: -82.55% → -78.25% (+4.30pp)

**Contribution by filter:** MACD-01 is largest contributor (≈+1.2pp)

## Key Learnings

**What went well:**
- Clear Plan document with 6 checklist items and implementation positions enabled 0 implementation errors
- Critical Logger bug caught in code review before deployment (Impact avoidance)
- Simulation validation quantified each filter's contribution

**To apply next time:**
- Sandbox environment compatibility checks for require() in n8n/Lambda/Workers
- Risk filters default to 'on' for safety (vs 'off')
- Bug fixes after code review → new workflow file version (enables rollback)

## Monitoring Points

- Weekly report: expect 10-15% fewer recommended stocks (risk reduction)
- Stop-loss rate: monitor if drops below 41.5%
- Theme/delist risk stocks in output: should be 0 (if workflows running correctly)
