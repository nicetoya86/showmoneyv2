# swing-algo-oversold-bounce-hitrate Design

> **Project**: showmoneyv2
> **Feature**: Swing Algo Enhancement Sub-project 4 ("Phase C") — E반등(oversold-bounce) 패턴
> hit_rate 개선, 전문 트레이더 진단 5개 항목 전부 적용
> **Prior work**: [2026-07-30-swing-algo-oversold-bounce-design.md](2026-07-30-swing-algo-oversold-bounce-design.md)
> (Phase B, 초기+재시도 완료) / [swing-algo-oversold-bounce.analysis.md](../../03-analysis/swing-algo-oversold-bounce.analysis.md)
> (Phase B 결론: bounce-confirmation 완화는 효과 없었음, 진짜 병목은 entry-signal 품질)
> **Date**: 2026-08-01

---

## 1. Background & Trigger

Phase B(및 재시도)는 최선의 그리드 셀에서도 hit_rate 43.3% 수준(train)에 그쳐 90% 게이트에 크게
못 미쳤고, test 표본(n=41~42)도 신뢰 기준(n≥50) 미달. 사용자가 "전문 트레이더 관점" 리뷰를
요청했고, 5개 항목을 진단함:

1. 거래량 확인 (trigger day rvol, 기존 base filter `rvol>=1.0`보다 강화)
2. 섹터 상대강도/레짐 맥락 (Phase A `sector_strong` 재사용)
3. 2일 확인 (단일일 RSI cross 대신 휩쏘 방지)
4. 지지선 근접 (임의 8% 되돌림 대신 실제 기술적 지지)
5. ATR 기반 변동성-조정 target/stop (기존 고정 %대신)

사용자 지시: **1번부터 5번까지 전부, 순서대로, 빠짐없이** 적용.

## 2. Architecture — 실행 순서와 이유

문자 그대로 "1→5 순서"로 구현하면 문제가 생김: 항목3(2일 확인)은 entry-rule 자체를 바꿔 새
candidate pool을 만드는 변경이고, 항목1/2/4는 기존 pool 위에 얹는 boolean 태그. 태그를 먼저
"1번 풀"에 계산했다가 나중에 3번이 풀을 바꿔버리면 태그를 전부 다시 계산해야 함. 따라서 **실행
순서는 3 → 1,2,4 → 5**로 재배치 (사용자 승인됨). 보고 시에는 5개 항목 모두 커버하므로
"1번부터 5번까지 빠짐없이"라는 지시를 충족.

**Stage 1 — 항목3: 2일 확인 (entry-rule 변경, v3 pool 생성)**

`_is_oversold_bounce`의 기존 5조건은 trigger day `idx`에서 그대로 평가(provisional). 추가:
`rsi14[idx+1] >= 40`도 유지되는지 확인. 통과 시 실제 candidate는 `idx+1`을 새 trigger day로
써서 생성 — `entry = close[idx+1]`, `entry_idx = idx+2`. (Phase B의 `entry_idx = idx+1`
관례를 그대로 한 칸 밀어서 적용.)

이유: RSI가 40을 넘었다가 바로 다음날 되돌아가는 휩쏘를 걸러내기 위함. 조건 자체(RSI/oversold
depth/pullback/SMA60/직전종가돌파)는 전부 Phase B와 동일하게 유지, 오직 "그 상태가 하루 더
유지되는가"만 추가.

출력: `backtest_oversold_candidates_v3.json`. v2(127건) 대비 후보 수가 더 줄어들 것으로
예상됨 — 정직하게 보고.

**Stage 2 — 항목1/2/4: v3 pool 위에 boolean 태그 (Phase A 방식 그대로)**

신규 모듈 `backtest/oversold_candidate_signals.py`:

- `compute_volume_confirm(df, idx) -> bool`: trigger day rvol(거래량/과거 평균 거래량) `>= 1.5`.
  rvol 계산 방식은 기존 `swing_signal_engine.py`의 rvol 산출 로직과 동일하게 맞춤(재구현 아님,
  같은 공식 재사용).
- `compute_sector_strong(...)`: `backtest/candidate_signals.py`의 `compute_sector_strength`를
  **그대로 재사용** (재구현 없음). 필요한 `sector_returns_by_date`/`sector_map` 준비만 새로 함.
- `compute_support_confluence(df, idx) -> bool`: 신규 구현. 직전 40일 구간에서 피봇로우(좌우
  각 3일보다 낮은 국소 최저 종가) 탐색, trigger day 종가가 그 피봇로우들 중 하나에 `±3%` 이내로
  근접해 있으면 True. `swing_signal_engine.py`의 B지지선 패턴(`prox_to_past`, 과거 20~50일
  평균가 근접)과는 다른 정의이므로 재사용하지 않고 신규 구현 — 사용자가 "피봇로우 근접"을
  명시적으로 선택했기 때문.
- `tag_candidates_oversold(candidates, per_ticker_ohlcv, sector_map) -> Dict[(ticker,date), Dict[str,bool]]`:
  위 3개 태그를 candidate별로 계산해 딕셔너리로 aggregate (Phase A `tag_candidates`와 동일 패턴).

`target_stop_grid_search.py`는 **무수정**. 기존 `required_tags: FrozenSet[str]` /
`tags_lookup` 파라미터를 그대로 사용해 `{volume_confirm}`, `{sector_strong}`,
`{support_confluence}`, 그리고 이들의 2/3-조합까지 총 `2^3 - 1 = 7`개 비어있지 않은 부분집합을
Phase A와 동일하게 스윕. 각 부분집합의 train/test 결과에 `n_trades`, `n_trades>=50` 신뢰도
열을 포함해 정직 보고 — 필터링할수록 표본이 더 줄 것으로 예상됨(사용자 확인됨, 소프트 스코어링으로
회피하지 않음).

**Stage 3 — 항목5: ATR 기반 target/stop (신규 사이드 스크립트)**

`target_stop_grid_search.py`는 여기서도 무수정 유지. 신규 `backtest/atr_stop_grid_search.py`:

- `entry_idx` 시점 `atr14`를 signal day(`idx`, lookahead 없음) 기준으로 계산해
  `atr_pct = atr14[idx] / close[idx]`로 candidate별 side-lookup 파일에 캐시
  (`backtest_oversold_atr_lookup.json`, `(ticker,date) -> atr_pct`).
- target/stop을 고정 %가 아니라 `target = entry * (1 + target_mult * atr_pct)`,
  `stop = entry * (1 - stop_mult * atr_pct)`로 계산.
- 그리드: `target_mult=[1, 1.5, 2, 3]`, `stop_mult=[0.5, 1, 1.5, 2]` (16셀,
  `min_score`/`regime_gate`/`exclude_d_box` 축은 이번 스크립트 범위 밖 — ATR 배수 자체가
  핵심 변수이므로).
- `simulate_exit`/`apply_toss_liveprice`/`apply_round_trip_cost`/`simulate_portfolio`/
  `cagr_and_mdd`는 전부 기존 것 그대로 호출 (target_stop_grid_search와 같은 시뮬레이션 primitive,
  단지 target/stop 계산식만 다르므로 새 스크립트가 필요하지만 내부 시뮬레이션 로직은 무수정 재사용).
- 적용 대상 pool: Stage 2 결과 중 분석 시점에 정함 (전체 v3 풀 또는 `n_trades>=50`을 유지하는
  가장 관대한 태그 부분집합 — 분석 문서에서 실제로 정하고 근거를 밝힘).
- select_best_config과 동일한 3단계 선택 로직(목표 클리어 → trades_per_week 폴백 →
  best_cagr_overall 폴백)을 `atr_stop_grid_search.py` 안에 그대로 복제 구현 (기존 함수를
  import해서 재사용 가능하면 재사용, target_stop_grid_search의 그리드 셀 구조와 다르므로
  로직만 복제).

## 3. 데이터 흐름

```
backtest_oversold_candidates.json (v2, 127건, Phase B 산출물)
  -> generate_oversold_candidates.py (2일 확인 추가)
  -> backtest_oversold_candidates_v3.json

backtest_oversold_candidates_v3.json + per_ticker_ohlcv + sector_map
  -> oversold_candidate_signals.py
  -> backtest_oversold_v3_tags.json (태그 lookup)
  -> backtest_oversold_v3_atr_lookup.json (atr_pct lookup, Stage 3용, Stage 2와 병행 생성)

backtest_oversold_v3_tags.json
  -> target_stop_grid_search.run_grid_search (무수정) x 7 부분집합
  -> backtest_oversold_v3_tagsweep_results.json

backtest_oversold_v3_atr_lookup.json + (Stage 2에서 정한 pool)
  -> atr_stop_grid_search.py
  -> backtest_oversold_atr_grid_results.json

전부 종합 -> docs/03-analysis/swing-algo-oversold-bounce-hitrate.analysis.md
```

## 4. 컴포넌트 요약

| 파일 | 상태 | 역할 |
|---|---|---|
| `backtest/generate_oversold_candidates.py` | 수정 | 2일 확인 추가, v3 생성 |
| `backtest/oversold_candidate_signals.py` | 신규 | volume_confirm, sector_strong(재사용), support_confluence 태그 계산 |
| `backtest/target_stop_grid_search.py` | **무수정** | 기존 `required_tags` 파라미터로 7개 부분집합 스윕 |
| `backtest/atr_stop_grid_search.py` | 신규 | ATR 기반 target/stop 그리드서치, 기존 시뮬레이션 primitive 재사용 |
| `docs/03-analysis/swing-algo-oversold-bounce-hitrate.analysis.md` | 신규 | Stage 1/2/3 각각의 단독 효과 + 최종 종합, 정직 보고 |

## 5. 에러 처리

Phase A/B와 동일한 컨벤션 그대로:
- 티커별 fetch 실패는 `skipped_tickers`에 기록하고 스캔은 계속 진행 (버그 아님, Phase B에서
  이미 확인된 4개 상장폐지/코드변경 티커 재발생 예상).
- 지표 계산에 필요한 lookback 구간이 부족한 인덱스(`idx < 70` 등)는 조용히 `False`/스킵 처리
  (기존 `_is_oversold_bounce`와 동일 패턴).
- 태그/ATR lookup에 없는 `(ticker,date)` 키는 `required_tags` 필터링 시 자동으로 후보 제외
  (Phase A `tags_lookup.get(key, {})` 패턴 재사용).

## 6. 테스트 계획

Phase A/B와 동일한 value-pinning 스타일 (synthetic DataFrame 고정값 assert, monkeypatch로
네트워크 격리):

- `_is_oversold_bounce` 2일 확인 로직: RSI가 idx+1에 40 밑으로 재하락하면 후보 미생성 케이스,
  유지되면 생성 케이스, entry/entry_idx가 한 칸 밀렸는지 확인하는 케이스.
- `compute_volume_confirm`: rvol 1.5 이상/미만 케이스.
- `compute_support_confluence`: 피봇로우 탐지 성공(±3% 이내)/실패(범위 밖) 케이스, 피봇로우가
  없는 평탄한 구간에서 False 반환하는 케이스.
- `tag_candidates_oversold`: 3개 태그가 각 candidate에 올바르게 매핑되는지.
- `atr_stop_grid_search.py`: `atr_pct` 계산값 고정 검증, target/stop 계산식(`entry*(1±mult*atr_pct)`)
  고정값 검증, 그리드 16셀 생성 및 선택 로직 검증.

전체 스위트(`pytest backtest/tests/`)는 매 단계 종료 시 그린 상태 유지.

## 7. 한계

- **파라미터 증가**: 이번 sub-project는 2일 확인 임계, rvol 1.5, 피봇로우 lookback(40일)/근접
  허용치(3%), ATR 배수 그리드(4x4)까지 여러 개의 새 자유 파라미터를 동시에 도입 — Phase A/B의
  "레버 하나씩" 원칙보다 많음. data-snooping 위험 완화를 위해 Stage 1(v2→v3 단독 효과)과
  Stage 2(태그 부분집합별 개별 결과)를 최종 조합 결과와 별도로, 반드시 함께 보고.
  최종 조합 결과만 골라서 보고하지 않음.
  - 피봇로우 `lookback=40일`, 근접 허용치 `±3%`는 이 설계 문서에서 처음 확정하는 값이며 기존
  코드에서 유래한 값이 아님 — 트레이더 상식(단기 스윙 지지선은 최근 1.5~2개월 이내가 유의미)에
  근거한 초기값이고, 분석 단계에서 그리드서치 대상은 아님(추가 파라미터 증식 방지).
- **샘플 사이즈 위험 지속**: Stage 1의 2일 확인 자체가 후보를 추가로 줄이고, Stage 2의 AND
  필터가 더 줄이므로, 최종적으로 `n_trades>=50` 신뢰 기준을 만족하는 조합이 거의 없을 가능성이
  높음 — 이 경우도 Phase B처럼 "underpowered"로 정직하게 보고(소프트 필터링으로 회피하지 않음).
- Phase 1/2/3의 기존 한계(고정% 시뮬레이션 대신 이번엔 ATR 기반이라 일부 해소되지만, 호가/체결
  모델링 부재, flat-fee 가정 등)는 그대로 상속.
- 단일 train/test 분할, 기존 전 sub-project와 동일한 한계.

프로덕션 코드(`src/swing-scanner.src.js`) 변경 없음 — 연구 단계, 별도 결정 사항.
