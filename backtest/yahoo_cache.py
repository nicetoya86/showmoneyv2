from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import requests


@dataclass(frozen=True)
class YahooFetchSpec:
    ticker: str
    range: str = "2y"
    interval: str = "1d"


def _cache_key(spec: YahooFetchSpec) -> str:
    raw = f"{spec.ticker}|{spec.range}|{spec.interval}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _default_cache_dir() -> Path:
    # repo root/cache/yahoo already exists in this project
    return Path("cache") / "yahoo"


def fetch_yahoo_chart(
    spec: YahooFetchSpec,
    *,
    cache_dir: Optional[Path] = None,
    use_cache: bool = True,
    min_sleep_s: float = 0.15,
) -> Dict[str, Any]:
    """
    Fetch Yahoo Finance chart data with simple file cache.

    - Uses: https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=...&interval=...
    - Cache: cache/yahoo/{sha1}.json (same folder used elsewhere in this repo)
    """
    cache_dir = cache_dir or _default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(spec)
    cache_path = cache_dir / f"{key}.json"

    if use_cache and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{spec.ticker}"
    params = {"range": spec.range, "interval": spec.interval}
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    if min_sleep_s > 0:
        time.sleep(min_sleep_s)
    return data


def chart_to_ohlcv_daily(data: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Convert Yahoo chart response (interval=1d) to a DataFrame with:
    - timestamp_utc (datetime64[ns, UTC])
    - open/high/low/close/volume (float)
    """
    result = (((data or {}).get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise ValueError("Yahoo chart: missing result")

    ts = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote") or [None])[0]) or {}
    df = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(ts, unit="s", utc=True),
            "open": quote.get("open", []),
            "high": quote.get("high", []),
            "low": quote.get("low", []),
            "close": quote.get("close", []),
            "volume": quote.get("volume", []),
        }
    )
    # clean NaNs
    df = df.dropna(subset=["timestamp_utc", "close"]).reset_index(drop=True)
    meta = result.get("meta") or {}
    return df, meta

