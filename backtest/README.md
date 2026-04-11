## 목적(쉬운 설명)
이 폴더는 **n8n 추천 로직이 과거에도 통했는지**를 “대략이라도” 검증하기 위한 **오프라인 백테스트** 도구입니다.

중요:
- 여기 백테스트는 **일봉(1일 단위) 데이터**로만 계산합니다.  
  그래서 실제 장중(5분봉) 체결과 100% 같지 않습니다.  
  다만 **임계값(확률/점수)을 너무 높게 잡아서 추천이 안 나오는 문제**와, **보수완화(min2) 정책의 효과**를 비교하기엔 충분합니다.

---

## 설치(1회)
PowerShell에서 프로젝트 루트(`showmoneyv2`)로 이동한 뒤 아래를 실행하세요.

```bash
python -m pip install -r backtest/requirements.txt
```

---

## 준비물: 티커 목록 파일
예: `backtest/tickers_example.txt`처럼 한 줄에 하나씩.

형식:
- 코스피: `005930.KS`
- 코스닥: `035720.KQ`

---

## (추천) 운영 유니버스 티커 파일 자동 생성
현재 워크플로우의 유니버스 정책과 최대한 비슷하게, 아래 스크립트가 **KRX가 되면 KRX 전체→필터→상위 거래대금**, 막히면 **네이버 거래량 랭킹 폴백**으로 티커 목록을 만듭니다.

```bash
python -m backtest.build_operating_universe_tickers --out backtest/tickers_operating.txt --meta backtest/tickers_operating.meta.json --max 800
```

생성물:
- `backtest/tickers_operating.txt`
- `backtest/tickers_operating.meta.json` (어떤 소스를 썼는지/에러가 있었는지 기록)

---

## 단타(Scalping) 백테스트 실행
```bash
python -m backtest.run_backtest --tickers backtest/tickers_example.txt --start 2024-01-01 --end 2026-01-01 --out backtest_out_scalping.json
```

---

## 스윙(Swing) 백테스트 실행
```bash
python -m backtest.run_backtest_swing --tickers backtest/tickers_example.txt --start 2024-01-01 --end 2026-01-01 --out backtest_out_swing.json
```

---

## (추천) 운영 유니버스로 임계값 튜닝(min2 기준)
```bash
python -m backtest.tune_thresholds_min2 --tickers backtest/tickers_operating.txt --start 2024-01-01 --end 2026-01-01 --years 5y --out thresholds_min2.json
```

## 결과에서 볼 핵심(이 프로젝트 목표 기준)
- **trades**: 체결된 거래 수(추천 수의 대체 지표)
- **win_rate**: 수익으로 끝난 비율(승률)
- **avg_pnl / median_pnl**: 평균/중앙 손익률
- **mdd**: 최대낙폭(보수형에서 매우 중요)
- **strict_ratio**: 엄격(Strict) 추천 비율(낮으면 완화 종목이 많이 섞인다는 뜻)

