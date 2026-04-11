from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


@dataclass(frozen=True)
class BuildResult:
    tickers: List[str]
    meta: Dict[str, Any]


def _kst_today_yyyymmdd() -> str:
    now_utc = datetime.now(timezone.utc)
    kst = now_utc + timedelta(hours=9)
    return f"{kst.year:04d}{kst.month:02d}{kst.day:02d}"


def _krx_fetch_universe(trd_dd: str, *, timeout_s: int = 20) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Try KRX universe endpoint used in workflow (MDCSTAT01501).
    Returns (rows, error).
    """
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://data.krx.co.kr",
        "Referer": "https://data.krx.co.kr/contents/MDC/CM/MDI/mdiLoader/index.cmd",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }
    body = (
        "bld=dbms/MDC/STAT/standard/MDCSTAT01501"
        f"&mktId=ALL&trdDd={trd_dd}&share=1&money=1&csvxls_isNo=false"
    )
    try:
        r = requests.post(
            "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
            headers=headers,
            data=body,
            timeout=timeout_s,
        )
        r.raise_for_status()
        j = r.json()
        rows = (j.get("output") or j.get("OutBlock_1") or []) if isinstance(j, dict) else []
        if not isinstance(rows, list):
            return [], "KRX response missing list rows"
        return rows, None
    except Exception as e:
        return [], f"KRX error: {e}"


def _krx_load_from_cache_dir(
    cache_dir: Path,
    *,
    min_rows: int = 1500,
    max_files_to_try: int = 30,
) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
    """
    Load KRX universe rows from local cache directory (cache/krx).

    Many files are large; we try the most recently modified ones first.
    Returns (rows, error, picked_filename).
    """
    if not cache_dir.exists() or not cache_dir.is_dir():
        return [], f"cache dir not found: {cache_dir}", None

    files = sorted(cache_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return [], "cache dir empty", None

    tried = 0
    last_err: Optional[str] = None
    for fp in files[: max_files_to_try]:
        tried += 1
        try:
            # these files can be very large single-line JSON
            j = json.loads(fp.read_text(encoding="utf-8"))
            if not isinstance(j, dict):
                last_err = "cache json is not dict"
                continue
            rows = j.get("OutBlock_1") or j.get("output") or j.get("block1") or []
            if not isinstance(rows, list):
                last_err = "cache json rows not list"
                continue
            if len(rows) < min_rows:
                last_err = f"rows too small: {len(rows)}"
                continue
            return rows, None, fp.name
        except Exception as e:
            last_err = f"{fp.name}: {e}"
            continue

    return [], f"failed to load usable cache rows (tried={tried}) last={last_err}", None


def _to_int(x: Any) -> int:
    try:
        if x is None:
            return 0
        s = str(x).replace(",", "").strip()
        return int(float(s))
    except Exception:
        return 0


def _krx_rows_to_tickers(
    rows: List[Dict[str, Any]],
    *,
    min_price: int,
    min_turnover: int,
    max_tickers: int,
) -> List[str]:
    seen: set[str] = set()
    tmp: List[Tuple[int, str]] = []
    for row in rows:
        code = str(row.get("ISU_SRT_CD") or "").strip()
        # KRX can include non-standard 6-char symbols (e.g., with letters) that Yahoo doesn't support.
        # We only keep standard 6-digit equity codes.
        if not code or not re.fullmatch(r"\d{6}", code):
            continue

        mkt = str(row.get("MKT_NM") or "").lower()
        if "konex" in mkt or "코넥스" in mkt:
            continue

        price = _to_int(row.get("TDD_CLSPRC"))
        turnover = _to_int(row.get("ACC_TRDVAL"))
        if price < min_price or turnover < min_turnover:
            continue

        suffix = ".KS"
        if "kosdaq" in mkt or "코스닥" in mkt:
            suffix = ".KQ"
        t = f"{code}{suffix}"
        if t in seen:
            continue
        seen.add(t)
        tmp.append((turnover, t))

    # sort by turnover desc for representativeness and to cap size
    tmp.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in tmp[: max_tickers]]


def _naver_fetch_volume_rank(*, sosok: int, page: int, timeout_s: int = 20) -> str:
    url = f"https://finance.naver.com/sise/sise_quant.nhn?sosok={sosok}&page={page}"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}, timeout=timeout_s)
    r.raise_for_status()
    return r.text


def _naver_extract_codes(html: str) -> List[str]:
    # <a class="tltle" href="/item/main.naver?code=005930">삼성전자</a>
    out: List[str] = []
    re_code = re.compile(r"/item/main\.naver\?code=(\d{6})")
    for m in re_code.finditer(html):
        out.append(m.group(1))
    return out


def _naver_fetch_market_cap(*, sosok: int, page: int, timeout_s: int = 20) -> str:
    # market cap list (KOSPI/KOSDAQ)
    url = f"https://finance.naver.com/sise/sise_market_sum.nhn?sosok={sosok}&page={page}"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}, timeout=timeout_s)
    r.raise_for_status()
    return r.text


def _naver_build_tickers(*, quant_pages: int, mktcap_pages: int, max_tickers: int, sleep_s: float) -> List[str]:
    seen: set[str] = set()
    tickers: List[str] = []
    for sosok, suffix in [(0, ".KS"), (1, ".KQ")]:
        # 1) volume ranking pages
        for p in range(1, max(0, quant_pages) + 1):
            html = _naver_fetch_volume_rank(sosok=sosok, page=p)
            for code in _naver_extract_codes(html):
                t = f"{code}{suffix}"
                if t in seen:
                    continue
                seen.add(t)
                tickers.append(t)
                if len(tickers) >= max_tickers:
                    return tickers
            if sleep_s > 0:
                import time

                time.sleep(sleep_s)

        # 2) market cap pages (fallback to increase coverage)
        for p in range(1, max(0, mktcap_pages) + 1):
            html = _naver_fetch_market_cap(sosok=sosok, page=p)
            for code in _naver_extract_codes(html):
                t = f"{code}{suffix}"
                if t in seen:
                    continue
                seen.add(t)
                tickers.append(t)
                if len(tickers) >= max_tickers:
                    return tickers
            if sleep_s > 0:
                import time

                time.sleep(sleep_s)
    return tickers[:max_tickers]


def build_operating_universe(
    *,
    trd_dd: str,
    min_price: int,
    min_turnover: int,
    max_tickers: int,
    naver_quant_pages: int,
    naver_mktcap_pages: int,
    sleep_s: float,
) -> BuildResult:
    meta: Dict[str, Any] = {
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "trdDd": trd_dd,
        "minPrice": min_price,
        "minTurnover": min_turnover,
        "maxTickers": max_tickers,
        "naverQuantPages": naver_quant_pages,
        "naverMktcapPages": naver_mktcap_pages,
        "sleepMs": int(sleep_s * 1000),
        "source": None,
        "errors": [],
    }

    rows, err = _krx_fetch_universe(trd_dd)
    if err:
        meta["errors"].append(err)
    if rows:
        tickers = _krx_rows_to_tickers(rows, min_price=min_price, min_turnover=min_turnover, max_tickers=max_tickers)
        meta["source"] = "KRX_MDCSTAT01501"
        meta["krxRows"] = len(rows)
        meta["tickersCount"] = len(tickers)
        return BuildResult(tickers=tickers, meta=meta)

    # fallback 0) local KRX cache dir (best effort)
    cache_rows, cache_err, cache_file = _krx_load_from_cache_dir(Path("cache") / "krx")
    if cache_err:
        meta["errors"].append(cache_err)
    if cache_rows:
        tickers = _krx_rows_to_tickers(cache_rows, min_price=min_price, min_turnover=min_turnover, max_tickers=max_tickers)
        meta["source"] = "CACHE_KRX_DIR"
        meta["krxCacheFile"] = cache_file
        meta["krxRows"] = len(cache_rows)
        meta["tickersCount"] = len(tickers)
        return BuildResult(tickers=tickers, meta=meta)

    # fallback to Naver
    try:
        tickers = _naver_build_tickers(
            quant_pages=naver_quant_pages,
            mktcap_pages=naver_mktcap_pages,
            max_tickers=max_tickers,
            sleep_s=sleep_s,
        )
        meta["source"] = "NAVER_QUANT_PLUS_MKTCAP"
        meta["tickersCount"] = len(tickers)
        return BuildResult(tickers=tickers, meta=meta)
    except Exception as e:
        meta["errors"].append(f"Naver error: {e}")
        meta["source"] = "NONE"
        meta["tickersCount"] = 0
        return BuildResult(tickers=[], meta=meta)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="backtest/tickers_operating.txt")
    ap.add_argument("--meta", default="backtest/tickers_operating.meta.json")
    ap.add_argument("--trd-dd", default=_kst_today_yyyymmdd(), help="YYYYMMDD (KST 기준)")
    ap.add_argument("--max", type=int, default=1200, help="티커 최대 개수(튜닝/백테스트 속도 고려)")
    ap.add_argument("--min-price", type=int, default=1000)
    ap.add_argument("--min-turnover", type=int, default=1_000_000_000)  # 10억
    ap.add_argument("--naver-quant-pages", type=int, default=20, help="네이버 거래량랭킹 페이지 수(1페이지 ~약 50개)")
    ap.add_argument("--naver-mktcap-pages", type=int, default=20, help="네이버 시총상위 페이지 수(1페이지 ~약 50개)")
    ap.add_argument("--sleep-ms", type=int, default=120, help="네이버 페이지 요청 간 sleep(ms)")
    args = ap.parse_args()

    res = build_operating_universe(
        trd_dd=str(args.trd_dd),
        min_price=int(args.min_price),
        min_turnover=int(args.min_turnover),
        max_tickers=int(args.max),
        naver_quant_pages=int(args.naver_quant_pages),
        naver_mktcap_pages=int(args.naver_mktcap_pages),
        sleep_s=max(0.0, float(args.sleep_ms) / 1000.0),
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(res.tickers) + ("\n" if res.tickers else ""), encoding="utf-8")
    Path(args.meta).write_text(json.dumps(res.meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out} tickers={len(res.tickers)} source={res.meta.get('source')}")


if __name__ == "__main__":
    main()

