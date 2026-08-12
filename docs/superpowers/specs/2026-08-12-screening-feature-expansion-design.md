# 스크리닝 웹사이트 기능 확장 설계

날짜: 2026-08-12

## 배경

`stock_screen_web`은 코스피 종목을 4팩터(퀄리티/밸류/괴리/배당여력) 기준으로 스크리닝해 매일 자동 갱신되는
정적 Next.js 사이트다. 이번 작업은 다음 8가지 기능을 한 번에 확장한다: 소제목 명언 로테이션, 관리자 인증 기반
강제 재무 갱신, 분기 공시기한 다음날 자동 갱신, 날짜/시각 표시 포맷, 재무 데이터 기준(P/L TTM, BS 최근 분기),
코스닥 포함, 테이블 표시(50개 제한/종합점수 4자리/배당 컬럼), 필터통과 종목 엑셀 다운로드.

## A. 소제목 명언 로테이션 (주간)

- 11명의 투자자(Warren Buffett, Howard Marks, Mohnish Pabrai, Charlie Munger, Bill Ackman, Peter Lynch,
  Seth Klarman, Philip Fisher, 이채원, 최준철, 김민국) 명언을 `screening/quotes.py`에 하드코딩(한국어 번역 포함,
  11개, Claude가 각자의 가치투자 철학을 대표하는 문구로 선정).
- `ws_alpha.py` 실행 시 **ISO 주차**(`datetime.date.isocalendar().week` + `year`)를 시드로 `quotes[iso_week % 11]`
  선택 → `results.json`에 `quote_text`, `quote_author` 필드로 저장.
- 프런트(`page.tsx`)는 소제목 자리에 `"{quote_text}" — {quote_author}` 형태로 표시. 같은 ISO 주차 내에는 매일
  갱신이 돌아도 동일 명언 유지, 주가 바뀌면 자동으로 다음 명언으로 전환.

## B. 관리자 인증 + 강제 재무 갱신

- Vercel 환경변수 `ADMIN_PASSWORD` 신설.
- 신규 API 라우트 `web/app/api/admin-login/route.ts`: POST로 비밀번호 받아 일치하면 `httpOnly` 쿠키
  (`admin_session`, 값은 랜덤 토큰이 아니라 단순 서명된 플래그 — 예: `ADMIN_PASSWORD`의 HMAC, 1일 만료)를 설정.
- `page.tsx` 최하단에 "관리자" 버튼 → 클릭 시 비밀번호 입력 다이얼로그 → 로그인 성공 시 페이지가 관리자 모드로
  전환되어 기존 `UpdateControls`(업데이트 실행 버튼 + "재무데이터 새로 받기" 체크박스)가 노출됨. 비로그인 상태에서는
  이 컨트롤 자체가 렌더링되지 않음(서버 컴포넌트에서 쿠키 검사 후 조건부 렌더).
- `web/app/api/update-finance/route.ts`에도 동일 쿠키 검증 추가 → 비인증 요청은 401 반환(현재는 완전 공개 상태였음,
  이 부분이 이번 변경의 보안 수정 포함).

## C. 분기 공시기한 자동 갱신 스케줄

- `.github/workflows/daily-screen.yml`에 매일 cron과 별개로 4개 cron 트리거 추가, 모두 KST 06:00 실행
  (UTC 21:00 전날 → `cron: "0 21 15 5 *"`(5/16 KST06시), `"0 21 14 8 *"`(8/15), `"0 21 13 11 *"`(11/14),
  `"0 21 31 3 *"`(4/1)).
- 이 4개 스케줄 실행 시에는 `force_finance: true`로 재무데이터 캐시를 무시하고 강제 재수집. 기존 매일 cron은
  `force_finance: false`(캐시 활용) 그대로 유지.
- 워크플로 내부에서 `github.event.schedule` 값으로 어떤 cron이 트리거했는지 구분해 `force_finance` 입력을 조건부로
  설정.

## D. 날짜/시각 표시 포맷

- `as_of_date`("20260811") 원본 데이터는 그대로 두고, `page.tsx`에서 표시할 때만
  `YYYY년 MM월 DD일` 형태로 파싱해 렌더링하는 포맷 함수 추가.
- `generated_at`(ISO8601 UTC) 표시에 `toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })` 명시 → 사용자
  브라우저 타임존과 무관하게 항상 한국시간으로 표시.

## E. 재무 데이터 기준 변경

- **P/L**: 이미 `ttm_calc()`으로 최근 4분기 합산(TTM) 계산 중 → 변경 없음.
- **재무상태표(BS)**: 현재 `fetch_finance_one()`이 연간(FY) `finstate` 호출 1회로 자산총계/부채총계/자본총계까지
  가져오는 구조 → **가장 최근 공시된 분기의 분기 `finstate` 호출**(이미 TTM용으로 호출 중인 분기 데이터)에서
  자산총계/부채총계/자본총계를 함께 추출하도록 변경. `debt_ratio` 계산식은 동일(부채총계/자본총계×100), 데이터
  소스만 연간 → 최근 분기로 교체.
- `auto_ttm_params()`가 이미 "가장 최근 공시된 분기"를 결정하므로 이 로직을 그대로 재사용.

## F. 코스닥 포함

- `data_pipeline.py`에 `get_kosdaq_universe(date)` 함수 신설(KRX 코스닥 일별매매정보 API, 기존
  `get_kospi_universe()`와 동일 패턴, `mktId=KSQ`만 다름).
- `get_kospi_universe()` + `get_kosdaq_universe()` 결과를 합쳐 전체 유니버스 구성, 각 종목에 시장 구분값
  ("코스피"/"코스닥")을 `sector_raw` 필드에 정확히 채움(현재 빈 문자열로 나오는 버그 수정 포함).

## G. 테이블 표시 변경

- `ws_alpha.py run_real()`의 `--top 60` 기본값 → `50`으로 변경. `ScreeningTable`에서도 방어적으로
  `rows.slice(0, 50)` 적용.
- `formatValue`에서 `score` 컬럼을 소수점 4자리(`toFixed(4)`) + 우측 정렬(`text-right` 클래스, 기존
  `TWO_DECIMAL_RIGHT_ALIGN` 패턴과 동일하게 별도 4자리 우측정렬 세트에 포함)로 변경.
- 컬럼 순서: `... , debt_ratio, div_yield, payout_ratio, score` — 부채비율과 종합점수 사이에 "시가배당수익률"
  (`div_yield`, %, 소수점 2자리, 우측정렬), "배당성향"(`payout_ratio`, %, 소수점 2자리, 우측정렬) 신규 컬럼 삽입.
  `ws_alpha.py`의 `cols` 리스트와 `KOR_NAMES`에 반영.

## H. 배당 데이터 연동 (연환산 시가배당수익률)

- `data_pipeline.py`에 DART 배당 관련 공시 API(OpenDartReader의 배당 관련 엔드포인트, 주당배당금·총배당금 계정)
  호출 추가, **직전 사업연도(FY, 연간 결산 기준) 총배당금**을 사용(중간배당 포함된 연간 합계).
- 시가배당수익률 = 직전 FY 총배당금(또는 주당배당금×발행주식수) / 현재 시가총액 × 100. 이미 연간 기준이므로
  별도 연환산 배수 계산 불필요.
- 배당성향 = 직전 FY 총배당금 / TTM 당기순이익 × 100.
- 배당 데이터가 없는(무배당) 종목은 `div_yield=0`, `payout_ratio=0`으로 처리(NaN 아님 — 필터/정렬 시 정상 동작
  하도록).

## I. 필터통과 → 엑셀 다운로드

- `ws_alpha.py run_real()`에서 하드필터 통과한 **전체** 종목(50개 제한 없이, `score` 내림차순)을
  `web/data/filtered_full.json`으로 별도 export(동일 컬럼 구조, `results.json`과 같은 커밋에 포함).
- `web/package.json`에 `xlsx`(SheetJS) 의존성 추가.
- `page.tsx`의 "필터 통과 N/M" 배지를 버튼으로 변경 → 클릭 시 `filtered_full.json`을 fetch, `xlsx` 라이브러리로
  브라우저에서 즉석 워크북 생성(`XLSX.utils.json_to_sheet` + `XLSX.writeFile`) 후 다운로드. 서버 API 불필요.

## 영향받는 파일

- `screening/quotes.py` (신규), `screening/ws_alpha.py`, `screening/data_pipeline.py`
- `.github/workflows/daily-screen.yml`
- `web/app/page.tsx`, `web/app/ScreeningTable.tsx`, `web/app/UpdateControls.tsx`(관리자 조건부 렌더 반영)
- `web/app/api/update-finance/route.ts`, `web/app/api/admin-login/route.ts`(신규)
- `web/package.json`(xlsx 의존성)
- `web/data/filtered_full.json`(신규, 자동 생성 커밋 대상)

## 테스트/검증 방침

- Python 쪽: 새 함수(코스닥 유니버스, 분기 BS 추출, 배당 계산, 명언 선택)에 대해 스크리닝 로직 기존 테스트 패턴을
  따라 단위 테스트 추가(있다면 `screening/tests/` 위치 확인 후 배치).
- 프런트: `npm run build` 통과 확인, 로컬에서 `results.json` 샘플로 테이블/포맷/관리자 흐름 브라우저 확인.
- 배포 전 GitHub Actions 워크플로 문법(`workflow_dispatch` 유지, 신규 cron 표현식)을 `act` 또는 dry-run으로
  확인하거나 최소한 YAML lint.
