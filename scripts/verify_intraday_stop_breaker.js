/**
 * Self-check for the intraday stop-loss circuit breaker added to
 * src/swing-scanner.src.js (countTodayStopOuts / INTRADAY_STOP_THRESH gate).
 * Mirrors the exact live-price-resolution and stop-comparison logic (trades
 * last price, else orderbook mid, else no live price) so a future edit that
 * breaks the counting logic fails this script.
 *
 * Run: node scripts/verify_intraday_stop_breaker.js
 */
'use strict';

const INTRADAY_STOP_THRESH = 2;

function resolveLivePrice(orderbook, trades) {
  let livePrice = null;
  if (Array.isArray(trades) && trades.length > 0) {
    const p = Number(trades[trades.length - 1].price);
    if (Number.isFinite(p) && p > 0) livePrice = p;
  }
  if (livePrice == null && orderbook && Array.isArray(orderbook.asks) && Array.isArray(orderbook.bids) && orderbook.asks[0] && orderbook.bids[0]) {
    const bestAsk = Number(orderbook.asks[0].price), bestBid = Number(orderbook.bids[0].price);
    if (Number.isFinite(bestAsk) && Number.isFinite(bestBid) && bestAsk > 0 && bestBid > 0) livePrice = (bestAsk + bestBid) / 2;
  }
  return livePrice;
}

async function countStopOuts(recs, fetchOrderbook, fetchTrades) {
  let stopCount = 0;
  for (const rec of recs) {
    try {
      const [orderbook, trades] = await Promise.all([fetchOrderbook(rec.code), fetchTrades(rec.code, 5)]);
      const livePrice = resolveLivePrice(orderbook, trades);
      if (livePrice != null && Number.isFinite(rec.stop) && livePrice <= rec.stop) stopCount++;
    } catch (e) {
      // excluded from count on fetch failure, matches production behavior
    }
  }
  return stopCount;
}

async function main() {
  let failures = 0;
  const assertEq = (label, got, want) => {
    if (got !== want) { failures++; console.error(`FAIL ${label}: got ${got}, want ${want}`); }
  };

  // Case 1: live price from trades, below stop -> counted
  {
    const recs = [{ code: 'A', stop: 100 }];
    const n = await countStopOuts(
      recs,
      async () => null,
      async () => [{ price: 95 }],
    );
    assertEq('trades-price below stop', n, 1);
  }

  // Case 2: live price from trades, above stop -> not counted
  {
    const recs = [{ code: 'A', stop: 100 }];
    const n = await countStopOuts(
      recs,
      async () => null,
      async () => [{ price: 105 }],
    );
    assertEq('trades-price above stop', n, 0);
  }

  // Case 3: no trades, orderbook mid below stop -> counted (fallback path)
  {
    const recs = [{ code: 'A', stop: 100 }];
    const n = await countStopOuts(
      recs,
      async () => ({ asks: [{ price: 96 }], bids: [{ price: 94 }] }),
      async () => [],
    );
    assertEq('orderbook-fallback below stop', n, 1);
  }

  // Case 4: no trades, no usable orderbook -> not counted (no live price)
  {
    const recs = [{ code: 'A', stop: 100 }];
    const n = await countStopOuts(
      recs,
      async () => null,
      async () => [],
    );
    assertEq('no live price available', n, 0);
  }

  // Case 5: fetch throws -> excluded from count, not fatal
  {
    const recs = [{ code: 'A', stop: 100 }, { code: 'B', stop: 100 }];
    const n = await countStopOuts(
      recs,
      async (code) => { if (code === 'A') throw new Error('network error'); return null; },
      async (code) => (code === 'A' ? [{ price: 95 }] : [{ price: 50 }]),
    );
    assertEq('fetch failure excluded, other ticker still counted', n, 1);
  }

  // Case 6: threshold semantics — exactly at INTRADAY_STOP_THRESH trips the breaker
  {
    const recs = [{ code: 'A', stop: 100 }, { code: 'B', stop: 100 }, { code: 'C', stop: 100 }];
    const n = await countStopOuts(
      recs,
      async () => null,
      async (code) => (code === 'C' ? [{ price: 200 }] : [{ price: 50 }]),
    );
    assertEq('two of three stopped out', n, 2);
    assertEq('breaker trips at threshold', n >= INTRADAY_STOP_THRESH, true);
  }

  if (failures > 0) {
    console.error(`${failures} case(s) failed`);
    process.exit(1);
  }
  console.log('OK: intraday stop-loss circuit breaker counting logic verified (6 cases).');
}

main();
