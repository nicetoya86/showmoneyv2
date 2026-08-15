# Swing Scanner Weekly-Cap Restoration Design

## Problem

The live Swing Scanner Function node in n8n (workflow `ScHaeFdneOoH1ZNZ`) currently has **no weekly send cap at all** — confirmed by pulling the live node's `functionCode` directly from the n8n API and grepping it: no `MAX_WEEKLY_SENDS`, no `thisWeekCount` gate, only the existing per-cycle cap (`MAX_STOCK_PER_SEND = 3`, applied every ~10 minutes during the 09:00–11:30 KST scan window).

Git history shows a `MAX_WEEKLY_SENDS = 15` gate has existed in `src/swing-scanner.src.js` since 2026-05-09 (`21e7974`, "swing-quality-improvement") and has never been removed by any commit. It correctly triggered a skip on 2026-08-12 (that day's cumulative weekly count — 08-10's 12 + 08-11's 3 — hit exactly 15), matching [[swing-algo-weekly-cap-silent-skip-2026-08-12]]'s "왜 스캔 안 됨" finding: the cap worked, but skipped silently with no Telegram notice, confusing the user.

Separately, `D:\vibecording\showmoneyv2\src\swing-scanner.src.js` (the **main checkout**, outside this worktree) currently has this same gate **removed** in its uncommitted working tree — byte-identical in that region to the live deployed code. This was very likely an uncommitted local edit that got deployed live directly (bypassing the commit → `build_deploy_bundle.js` → deploy pipeline this repo otherwise follows), probably as a quick reaction to the 2026-08-12 confusion — removing the cap instead of fixing its silent-skip UX. No commit or `.bkit` state explains this change; it is simply sitting uncommitted in the main checkout right now. **This is flagged as an open risk below — it must be reconciled with the user before this design's deploy step runs**, since it's their in-progress local state, not something this plan should silently overwrite.

Effect of the missing cap: on 2026-08-13, the scanner sent 32 recommendations in one day (vs 12 on 08-10, 3 on 08-11, 0 on 08-12, 7 on 08-14 — 54 total for the week, both from live `staticData.global.weeklyRecommendations` for 2026-08-10..14 and from `store.scanLog` per-cycle history, both pulled live from the n8n API). Of that week's 18 evaluated (win+partial+loss) positions on 08-13, only 38.9% won — versus 66.7% on 08-10 (9 evaluated). `score`/`grade` do not explain the gap: `grade` was `강매` for literally every rec all week (the whole week ran under `regimeLevel=2`, which restricts grade to `강매` only), and win-group mean score (138.3) vs loss-group mean score (127.9) overlap heavily (loss scores ranged 110–212, win scores 110–239) — consistent with [[swing-algo-sub-project-10-signal-weight-refit]]'s AUC≈0.53 (near-chance) finding, now reconfirmed on live data. Tightening score thresholds is not a well-evidenced fix; capping volume on a day that already dwarfs every other day in the week is.

## Goal

Restore the weekly volume ceiling on the **live** Swing Scanner, without reintroducing the silent-skip confusion that likely caused it to be pulled in the first place.

## Approaches Considered

- **A. Raise the score/grade bar instead of capping volume.** Rejected — this week's real data shows score barely separates win from loss within the `강매`-only regime; tightening it would not have reliably filtered out 08-13's losers specifically (some of that day's high scorers still lost), and would resurface the AUC≈0.53 dead end already closed by sub-project 10.
- **B. Restore the old cap exactly as it was (silent skip).** Rejected — this is what generated the 2026-08-12 confusion in the first place, and looks like what led someone to strip it out live rather than fix it properly.
- **C. Restore the cap + add a one-time weekly notice when it first triggers.** **Chosen.** Keeps the proven volume ceiling (its removal is the one change most directly tied to 08-13's quality drop) and closes the exact gap ([[swing-algo-weekly-cap-silent-skip-2026-08-12]]'s "improvement idea not started") that made the cap unpopular enough to get quietly removed.

## Design

**Cap value:** keep `MAX_WEEKLY_SENDS = 15` — this is the pre-existing, already-reasoned value ("일 3건 × 5일" — 3/cycle-day × 5 trading days), not a new number invented for this fix. No new evidence in this investigation argues for a different threshold.

**Gate placement:** same as before removal — checked once per run, right after `thisWeekCount` is computed from `store.weeklyRecommendations` over the current Mon–Fri window, before the grade/score sort and `selected` slice. Unchanged from the pre-removal design; this design only adds the notice.

**One-time notice:** when the gate trips, send a Telegram message the *first* time the cap is hit for the current week (tracked via a `store` flag keyed by the week's Monday date, reset like the existing `store.weeklyRecommendations` week-rollover), then continue returning the same silent `{ skipped: true, reason: 'Weekly limit' }} json` on every subsequent run that week without re-sending. This avoids two failure modes: total silence (the original bug) and a notice every 10 minutes for the rest of the week (spam).

Message (Korean, matching existing tone):
```
📊 [주간 발송 한도 도달]
이번 주 스윙 추천 15건 발송 완료 — 신규 추천 종료
(다음 주 월요일부재개)
```

**Scope:** `src/swing-scanner.src.js` only (reinstate the gate + add the notice), then `node scripts/build_deploy_bundle.js` to regenerate `swing_scanner_code.js`, then deploy live via the same n8n Cloud REST API mechanism already identified for the Daily Position Monitor deploy (`PUT /workflows/ScHaeFdneOoH1ZNZ`, API key from `export_n8n_executions.py`). This is a separate concern from the Daily Position Monitor shock-alert work (already implemented in Tasks 1-3 of the sibling plan) — different node (`Swing Scanner`, not a new node), same workflow, same deploy mechanism.

**Testing:** a `scripts/verify_*.js` self-check mirroring the gate + one-time-notice logic (same convention as `scripts/verify_intraday_stop_breaker.js` and the position-monitor shock-alert check), covering: under-cap (no skip, no notice), at-cap first hit (skip + notice fires), at-cap repeat hit same week (skip, no duplicate notice), new week rollover (counter/flag resets).

## Risks / Open Questions

1. **Uncommitted main-checkout conflict (blocking):** `D:\vibecording\showmoneyv2\src\swing-scanner.src.js` and `swing_scanner_code.js` have uncommitted local changes that already match the live (cap-less) state. Before this plan's deploy step runs, the user needs to say what to do with that uncommitted work — discard it (it appears to be exactly the unreviewed change this design reverses), or explain what it was for if it's unrelated/still needed. This plan's implementation happens in this isolated worktree and won't touch the main checkout, but the live deploy step affects the same production system that uncommitted local state was apparently pushed from.
2. Sample size is one week (n=54, 30 evaluated). The 08-13-vs-08-10 hit-rate gap (38.9% vs 66.7%) is the most concrete lead available, but it's one week of data, not a multi-week backtest — reasonable to revisit if a couple more weeks under the restored cap don't show the same pattern.

## Testing Plan

Self-check script (`scripts/verify_swing_scanner_weekly_cap.js`), same style as existing verify scripts — no test framework, `assertEq` + `process.exit(1)` on failure, mirrors the gate/notice logic since the source file can't be `require()`d directly (top-level `return run();`, same constraint as the other n8n Function-node scripts in this repo).
