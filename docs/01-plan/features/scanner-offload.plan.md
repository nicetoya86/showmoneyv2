# scanner-offload Planning Document

> **Summary**: n8n Cloud의 Code 노드 task timeout(60초)과 Function 노드 수정 차단 때문에, 스캐너·리포터·모니터 등 8개 노드를 GitHub Actions(public 저장소, 무료)로 이전한다. 코드 본문은 그대로 두고 얇은 러너가 `this.helpers`/`getWorkflowStaticData`를 흉내 낸다.
>
> **Project**: showmoneyv2 (n8n workflow `ScHaeFdneOoH1ZNZ`)
> **Author**: kevin
> **Date**: 2026-10-31
> **Status**: Draft
> **관련**: [function-to-code-node-migration](function-to-code-node-migration.plan.md) (Phase 0 결과로 대체됨), [market-state-shadow](../../02-design/features/market-state-shadow.design.md) (이전 후 라이브 반영 가능)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | n8n에서는 어떤 로직 수정도 라이브에 못 넣는다(Function 노드 수정·생성 차단, Code 노드는 60초 제한이라 스캐너 300~409초·리포터 약 200초가 못 돈다). 동시에 텔레그램 봇 토큰·DART 키가 public 저장소 히스토리에 평문으로 있다. |
| **Solution** | 8개 노드를 GitHub Actions 스케줄 잡으로 이전. 러너(`runner/run.js`)가 기존 번들을 그대로 실행하고 `this` 대용 객체로 HTTP·정적 데이터를 제공. 상태는 비공개 저장소(`showmoneyv2-state`)의 `state.json`(약 0.5MB)에 키 단위 병합으로 저장. 시크릿은 GitHub Secrets. |
| **Function UX Effect** | 알림·리포트 문구와 시각은 불변이 목표. 이전 기간 동안 DRY_RUN 섀도 실행으로 n8n 결과와 대조한 뒤에만 전환. |
| **Core Value** | 승률 개선 로직(SURGE/CRASH 신규 중단, 일 진입 상한, 레짐별 전략, market-state-shadow)을 라이브에 반영할 수 있는 상태 복구. 비용 0원. 토큰 노출 해소. |

---

## 1. 배경과 근거

| 사실 | 출처 |
|---|---|
| Code 노드 task timeout = 60초 (이 n8n Cloud), 200초 sleep이 60초에 중단 | 2026-10-31 Phase 0 프로브 |
| Function 노드는 API로 생성 불가(400, violation "added"), 수정도 불가 | 2026-10-19 PUT 400 + 2026-10-31 프로브 |
| 스캐너 300~409초, 리포터 약 200초 | 라이브 실행 기록 |
| 봇 토큰·DART 키가 public 저장소 푸시된 히스토리(첫 커밋부터)에 평문 | git grep, 2026-10-31 |

사용자 결정(2026-10-31): 옵션 C(n8n 밖으로 이전), GitHub Actions, **public 저장소 유지**, **토큰 교체는 전환 직전**, 페이퍼 전환 동의.

## 2. 목표 / 비목표

- **목표**: 8개 노드를 Actions로 이전해 코드 수정이 `git push`만으로 라이브 반영되게 한다. 이전 전후 출력(추천 목록, 발송 문구, 상태 키) 동치. 월 비용 0원.
- **비목표**: 로직 개선(이전 후 별도 작업), 스케줄 정밀도 개선(측정 후 필요 시), n8n 완전 폐기(워크플로는 비활성화만).
- **안티 목표**: 이전 중 알림 이중 발송 또는 누락, 시그널·상태의 공개 노출.

## 3. 현재 구조 (조사 결과)

| 항목 | 내용 |
|---|---|
| 노드 | Swing Scanner, Weekly Reporter, Daily Position Monitor(트리거 6개), Risk/Theme Blacklist Updater, Healthcheck, Backup Watchdog, Log Viewer(수동) |
| 소스 경계면 | 노드당 `this.getWorkflowStaticData('global')` 1곳 + `this.helpers.httpRequest`. HTTP 옵션은 `json, method, headers, url, timeout, encoding, body` 7종만 사용. `process.env`/외부 `require` 없음(logger는 try/catch 폴백) |
| 상태 | 8개 노드가 공유하는 단일 `global` 객체, 총 약 524KB. 최대 `krxUniverseCache` 358KB(캐시, 재생성 가능), `naverNames` 56KB, `weeklyRecommendations` 47KB, `scanLog` 26KB |
| 시크릿(평문 하드코딩) | `BOT`, `CHAT`(전 노드), `DART_API_KEY`(스캐너) |
| 스케줄(KST, 평일 1-5) | 스캐너 `*/10 9-11`, 헬스체크 09:00, 워치독 09:10, 리스크 08:30, 테마 08:45, 포지션 모니터 10:00/11:00/12:30/13:30/14:30/16:00, 위클리 토 09:00 |
| 시간대 | n8n `Asia/Seoul` → Actions cron은 UTC |

## 4. 설계

### 4.1 구성

```
.github/workflows/swing.yml      cron 다수(아래 표) + workflow_dispatch(job 선택, dry_run)
runner/run.js                    번들을 AsyncFunction으로 실행, this/items/SECRETS 제공, 상태 로드·저장
runner/state.js                  비공개 저장소 Contents API로 state.json 읽기/키 병합 쓰기(409 재시도)
scripts/build_deploy_bundle.js   기존 번들러에 Actions용 산출물 추가 (n8n 산출물은 동결)
```

- **`this` 보강**: `this.helpers.httpRequest(opts)`는 Node 내장 `fetch`로 구현(신규 의존성 0). n8n 헬퍼 의미 재현: 비 2xx는 throw, `json:true`면 파싱, `encoding`(arraybuffer 계열)과 `timeout`(AbortSignal) 지원. `this.getWorkflowStaticData('global')`은 로드한 상태 객체를 반환.
- **시크릿 주입**: 소스의 `const BOT = '…'` 등 리터럴을 `SECRETS.TELEGRAM_BOT_TOKEN` 참조로 교체(소스 11줄). 러너가 `new AsyncFunction('items','SECRETS', code)`로 주입. 이후 소스에서 리터럴이 사라진다.
- **상태 저장**: 비공개 저장소 `showmoneyv2-state`의 `state.json`. 잡 시작 시 읽고 스냅샷 보관, 종료 시 *변경된 최상위 키만* 최신 원격본에 병합해 PUT(sha 낙관적 락, 409면 재병합 재시도). 전역 직렬화(concurrency) 대신 이 방식을 쓰는 이유: concurrency는 대기열이 1개라 동시 트리거 시 실행이 조용히 취소된다(스캐너와 포지션 모니터가 같은 분에 겹침).
- **로그 위생(public 로그 대응)**: 러너가 `console.*`를 무음 처리하고 `job / ok|err / 소요시간` 한 줄만 출력. 에러 메시지는 시크릿 마스킹 후 200자 절단. 상태·추천·종목코드는 로그에 절대 출력하지 않는다.
- **DRY_RUN**: 텔레그램 전송을 캡처만 하고 보내지 않음. 상태도 `state.dryrun.json`에 따로 저장해 실제 n8n 상태를 건드리지 않는다.

### 4.2 cron (UTC)

| 잡 | KST | UTC cron |
|---|---|---|
| 스캐너 | 평일 09:00~11:50 매 10분 | `*/10 0-2 * * 1-5` |
| 헬스체크 / 워치독 | 09:00 / 09:10 | `0 0 * * 1-5` / `10 0 * * 1-5` |
| 리스크 / 테마 블랙리스트 | 08:30 / 08:45 | `30 23 * * 0-4` / `45 23 * * 0-4` |
| 포지션 모니터 | 10:00 11:00 12:30 13:30 14:30 16:00 | `0 1 * * 1-5`, `0 2 * * 1-5`, `30 3 …`, `30 4 …`, `30 5 …`, `0 7 …` |
| 위클리 리포터 | 토 09:00 | `0 0 * * 6` |
| 로그 뷰어 | 수동 | `workflow_dispatch` |

공휴일은 기존 `lib/holidays.js` 로직이 처리하므로 cron은 평일만 맞춘다.

### 4.3 스케줄 정확도 (알려진 한계)
Actions cron은 SLA가 없고 5~30분 지연이 흔하며 60일 무활동 시 비활성화된다(커밋이 계속 있으므로 후자는 낮은 위험). **섀도 기간에 실제 지연을 측정**하고, 스캐너 시작 지연이 허용치(제안: 중앙값 5분 이내, 최대 15분 이내)를 넘으면 n8n에 *새* 워크플로(HTTP Request 노드로 `workflow_dispatch` 호출)를 만들어 정시 트리거만 맡긴다. 새 워크플로 생성은 막혀 있지 않다. 지금은 YAGNI로 보류.

## 5. 단계 계획

### Phase 0 — 사전 준비 (사용자 작업 포함)
1. 비공개 저장소 `showmoneyv2-state` 생성(무료, git 작업은 Actions 분 미사용).
2. 세분화된 PAT 발급: 해당 저장소 Contents 읽기/쓰기만. 발급은 UI에서만 가능하므로 사용자가 만들어 `STATE_PAT` 시크릿으로 등록.
3. 섀도 단계 시크릿 등록: `DART_API_KEY`(현재 값, 어차피 전환 시 재발급). 텔레그램 값은 DRY_RUN이라 불필요.
4. 현재 상태 시드: 라이브 워크플로 GET의 `staticData.global`을 `state.json`으로 저장(읽기 전용, 라이브 무변경).

### Phase 1 — 러너와 로컬 검증
- `runner/run.js`, `runner/state.js` 작성. 소스의 시크릿 리터럴 11곳을 `SECRETS` 참조로 교체.
- 로컬 vm 하네스: 기존 `verify_*.js` 입력으로 n8n 산출물과 Actions 산출물의 출력 동치 확인. HTTP 헬퍼는 로컬 모의 서버로 `json/encoding/timeout/비 2xx` 동작 검증.
- 종료 기준: 로컬 검증 전부 PASS, 번들에 시크릿 리터럴 0건(grep 게이트).

### Phase 2 — 섀도 실행 (DRY_RUN, 최소 5거래일)
- 스캐너·리포터·모니터를 전부 DRY_RUN으로 돌려 n8n 라이브 결과와 대조.
- 게이트: ① 스캐너 추천 종목 집합이 n8n과 동일(시각 차이로 인한 1~2건 차이는 원인 설명 가능해야 함) ② 상태 키 구조 동치 ③ 실패 0건 ④ 소요시간 10분 이내 ⑤ 스케줄 지연 통계 기록(4.3 판정). 위클리 리포터는 토요일 1회 필수 대조.

### Phase 3 — 전환 (장 시작 전, 하루 안에)
1. BotFather `/newbot`으로 새 봇 생성, 새 토큰·chat id를 `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` 시크릿으로 등록. DART 키 재발급 후 교체.
2. 최신 상태를 `state.json`에 재시드하고 DRY_RUN 해제.
3. n8n 워크플로 **비활성화**(삭제 아님, 가역). 이중 발송 방지를 위해 순서는 반드시 "n8n 비활성화 → Actions 실발송 활성화". 이 두 단계는 라이브 변경이므로 [feedback-production-deploy-confirmation] 절차대로 사용자 재확인 후 실행.
4. 옛 봇 처리 정책은 전환 시점에 결정: 즉시 삭제(롤백 불가, 가장 안전) vs 1주 유지 후 삭제(롤백 가능, 노출 토큰이 1주 더 살아 있음).

### Phase 4 — 정리
- `src/`, 루트 `*_code.js`, `backups/`, 워크플로 JSON에 남은 시크릿 리터럴 제거(히스토리는 교체로 무효화되므로 재작성 불필요). `.gitignore`에 백업·export 패턴 추가.
- `scripts/patch_*.py`(n8n PUT 방식) 폐기 표기, 배포는 `git push`로 대체.

### Phase 5 — 막혀 있던 작업 해제
- `feat/market-state-shadow` 병합 및 반영, 승률 개선 액션플랜 P0 규칙(SURGE/CRASH 신규 중단, 일 진입 상한) 구현, P1 검증 하네스, P2 레짐별 전략북.

## 6. 위험

| # | 위험 | 대응 |
|---|---|---|
| R1 | `fetch` 기반 헬퍼가 n8n 헬퍼와 미묘하게 달라 파싱 결과가 다름(BOM, 문자열/객체 혼재, 인코딩) | 소스에 이미 방어 코드가 있음. Phase 1 모의 서버 테스트 + Phase 2 라이브 대조로 판정 |
| R2 | Actions IP 대역에서 네이버·KIND·DART 호출이 차단/제한됨 | Phase 2 첫날 확인(n8n Cloud는 통과). 차단 시 대안은 사용자와 재논의(자체 PC 러너 등) |
| R3 | cron 지연·누락으로 스캔 시각이 밀림 | 4.3 측정 후 n8n 디스패처 도입 |
| R4 | 상태 병합 충돌/손상 | 키 단위 병합 + sha 낙관적 락 + 실행 전 `state.json` 백업 사본 보관(저장소 내 `backup/` 일 1회) |
| R5 | public 로그/저장소로 시그널·상태 유출 | 4.1 로그 위생, 상태는 비공개 저장소, 리포트는 텔레그램에만 |
| R6 | 전환 중 이중 발송 | 순서 고정(n8n 비활성화 먼저), DRY_RUN 해제는 전환 시점 1회 |
| R7 | 노출된 토큰이 전환 전까지 유효 | 사용자 결정(전환 직전 교체). 그 사이 가짜 알림 가능성을 인지하고, 알림은 페이퍼 참고용으로만 사용 |

## 7. 성공 기준
- 8개 잡 모두 Actions에서 정상 실행, 5거래일 섀도 게이트 통과.
- 전환 후 1주 연속: 발송 정상, 누락 0건, 이중 발송 0건.
- 코드 수정이 `git push`만으로 반영됨(market-state-shadow 반영으로 실증).
- 저장소·로그에 시크릿·시그널 노출 0건, 월 비용 0원.

## 8. 사용자 결정·작업이 필요한 항목
1. 비공개 상태 저장소 생성 승인(내가 `gh`로 만들 수 있음) + **PAT 발급은 사용자가 UI에서**(Contents 읽기/쓰기, 해당 저장소 한정).
2. 섀도 기간(제안: 5거래일).
3. 전환 시 옛 봇 처리 정책(즉시 삭제 vs 1주 유지).
