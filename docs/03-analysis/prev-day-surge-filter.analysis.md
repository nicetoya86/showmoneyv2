# Gap Analysis: prev-day-surge-filter

- **Date**: 2026-05-02
- **Design**: `docs/02-design/features/prev-day-surge-filter.design.md`
- **Implementation**: `swing_scanner_code.js`
- **Match Rate**: **100%** ✅ (above 90% threshold)

---

## Item-by-Item Results

### C-2 — Constants — 100% ✅

| Constant | Design Value | Implementation | Line | Status |
|---|---|---|---|---|
| `MAX_ENTRY_SURGE_PCT` | `0.10` | `0.10` | 28 | ✅ |
| `SURGE_ZONE_PCT` | `0.08` | `0.08` | 29 | ✅ |
| `SURGE_ZONE_MIN_SCORE` | `270` | `270` | 30 | ✅ |

Position: After line 26 (`// ===== /Regime 임계값 상수 =====`), inside dedicated comment block. ✅

### D-2 — Filter Lines — 100% ✅

Implementation at lines 1538–1540:

```javascript
// [SURGE-FILTER] 전일 급등 종목 진입 억제 (2026-05-02)
if (dailyChange > MAX_ENTRY_SURGE_PCT) return; // +10% 초과: 절대 차단
if (dailyChange > SURGE_ZONE_PCT && score < SURGE_ZONE_MIN_SCORE) return; // +8%+: 점수 270 미만 차단
```

| Element | Design | Implementation | Status |
|---|---|---|---|
| 절대 차단 조건 | `dailyChange > MAX_ENTRY_SURGE_PCT` | byte-exact | ✅ |
| 구간 차단 조건 | `dailyChange > SURGE_ZONE_PCT && score < SURGE_ZONE_MIN_SCORE` | byte-exact | ✅ |
| 변수명 | `dailyChange` (로컬, line 1168) | `dailyChange` | ✅ |
| 삽입 위치 | D-1 직후 (line 1537 다음) | line 1538 | ✅ |
| candidates.push 이전 | 필수 | line 1539–1540 < push(line 1574) | ✅ |

### NFR — Fallback 안전성 — 100% ✅

`dailyChange` 소스 (line 1168):
```javascript
const dailyChange = prevClose > 0 ? (currentPrice / prevClose - 1) : 0;
```

`prevClose <= 0`이면 `dailyChange = 0` → D-2 필터 자동 통과. 별도 방어 코드 불필요. ✅

---

## Match Rate Summary

| Item | Weight | Score | Weighted |
|---|---|---|---|
| C-2 Constants | 40% | 100% | 40.0 |
| D-2 Filter Lines | 40% | 100% | 40.0 |
| NFR Fallback | 20% | 100% | 20.0 |
| **Total** | **100%** | | **100%** |

---

## 4/27~30 시나리오 검증

| 종목 | dailyChange | score | MAX(0.10) | ZONE(0.08+270) | 판정 | 실제 결과 |
|---|---|---|---|---|---|---|
| LS머트리얼즈 | +0.164 | 230 | **0.164 > 0.10** | — | 차단 ✅ | 손절 방지 |
| LS네트웍스 | +0.098 | 250 | 통과 | **0.098 > 0.08 && 250 < 270** | 차단 ✅ | 손절 방지 |
| SIMPAC | +0.093 | 238 | 통과 | **0.093 > 0.08 && 238 < 270** | 차단 ✅ | 손절 방지 |
| 상도어메니티 | +0.098 | 255 | 통과 | **0.098 > 0.08 && 255 < 270** | 차단 (의도적 트레이드오프) | 수익 1건 포기 |
| 글로벌텍스프리 | +0.066 | 255 | 통과 | **0.066 ≤ 0.08** → 통과 | 통과 ✅ | 수익 유지 |
| 씨아이이스 | +0.062 | 228 | 통과 | **0.062 ≤ 0.08** → 통과 | 통과 ✅ | 수익 유지 |

손절 3건 차단 / 수익 1건 포기 — 기대값 순개선 확인.

---

## Gaps

없음. 설계와 구현이 완전히 일치함.

---

## Conclusion

C-2 상수 3개 및 D-2 필터 2줄 모두 설계와 완전 일치. 4/27~30 시나리오 검증 통과. Match Rate 100%. `/pdca report prev-day-surge-filter` 진행 가능.
