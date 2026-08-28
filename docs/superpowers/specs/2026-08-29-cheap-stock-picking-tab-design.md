# "Cheap Stock Picking" 탭 추가 설계

날짜: 2026-08-29

## 배경

현재 웹사이트는 단일 스크리닝(가치투자, Stock Note 4대 팩터 기반)만 보여준다
([page.tsx](../../../web/app/page.tsx)). 여기에 별도 알고리즘으로 종목을 고르는 두 번째
스크리닝을 탭으로 추가한다. 기존 화면은 "가치투자" 탭으로 이름을 바꾸고, 새 탭
"Cheap Stock Picking"을 추가한다.

새 알고리즘의 통과 조건 3가지:
1. 현재가가 52주 최저가의 10% 이내 (52주 최저가 근접)
2. 현재 이익이 5년 전보다 많음 (여전히 성장 중)
3. EV/EBIT < 10배 (저평가)

사용자 확인 사항:
- EV = 시가총액 + 총부채 − 현금성자산 (이자부채만 따로 파싱하지 않는 근사치)
- 이익 비교 기준은 영업이익(EBIT 근사, `op_income`)
- 52주 최저가는 매일 시세를 누적 캐싱하는 방식으로 새로 수집(git 추적 파일에 저장, 서비스
  초기에는 "수집된 기간 내 최저가"로 정확도가 점차 개선됨)
- 정렬 기준: EV/EBIT 오름차순
- 시총/거래대금 유동성 하한선은 적용하지 않음 (요청받은 3개 조건만 순수 적용)

## A. 데이터 파이프라인 (`screening/data_pipeline.py`)

### A-1. 현금성자산 계정 추가
`ACCOUNT_MAP`에 다음 항목 추가:
```python
"현금및현금성자산": "cash_equivalents",
```
기존 `_extract_year()`/`_extract_financials_3col()` 로직이 그대로 이 계정을 뽑아
`y0["cash_equivalents"]`로 사용 가능해진다 (코드 변경 불필요, 매핑 추가만).

### A-2. 5년 전 영업이익 조회
`fetch_finance_one()`에 DART `finstate` 호출을 1회 추가한다:
```python
def fetch_op_income_5y_ago(dart, corp_code: str, year: int) -> float:
    """5년 전 사업연도(annual_year - 5) 사업보고서(FY)에서 영업이익만 추출."""
    try:
        fs = dart.finstate(corp_code, year, reprt_code=QUARTER_CODES["FY"])
    except Exception:
        return np.nan
    if not isinstance(fs, pd.DataFrame) or len(fs) == 0:
        return np.nan
    y0, _, _ = _extract_financials_3col(fs)
    return y0["op_income"]
```
`fetch_finance_one()` 반환 dict에 추가:
- `"op_income_5y_ago": fetch_op_income_5y_ago(dart, corp_code, annual_year - 5)`
- `"cash_equivalents": y0["cash_equivalents"]`

이 호출은 재무 캐시가 분기 단위로만 갱신되므로(`daily-screen.yml`의 quarter 캐시 키)
매일 추가 API 부담이 생기지 않는다. 종목당 API 호출이 기존 2회(연간 finstate + 분기
finstate) + 배당 1회에서 4회로 늘어난다 — 분기 강제 재수집 시에만 영향.

### A-3. 52주 최저가 rolling 캐시
신규 저장 위치: `screening/data/price_history.parquet` (git 추적 — `screening/.cache/`와
달리 `.gitignore` 대상 아님. 매일 워크플로우가 커밋해 영구 보존).

```python
PRICE_HISTORY_FILE = Path("data") / "price_history.parquet"
PRICE_HISTORY_WINDOW_DAYS = 370

def update_price_history(universe: pd.DataFrame, date: str) -> pd.DataFrame:
    """universe(get_full_universe 반환값, index=stock_code)의 당일 일중 저가(TDD_LWPRC)를
    누적 캐시에 append하고, 윈도우(370일)보다 오래된 행은 버린 뒤 저장한다."""
    PRICE_HISTORY_FILE.parent.mkdir(exist_ok=True)
    today_rows = pd.DataFrame({
        "date": date,
        "stock_code": universe.index,
        "low": universe["TDD_LWPRC"].values,
    })
    if PRICE_HISTORY_FILE.exists():
        existing = pd.read_parquet(PRICE_HISTORY_FILE)
        combined = pd.concat([existing, today_rows], ignore_index=True)
    else:
        combined = today_rows
    combined = combined.drop_duplicates(subset=["date", "stock_code"], keep="last")
    cutoff = (pd.Timestamp(date) - pd.Timedelta(days=PRICE_HISTORY_WINDOW_DAYS)).strftime("%Y%m%d")
    combined = combined[combined["date"] >= cutoff]
    combined.to_parquet(PRICE_HISTORY_FILE, index=False)
    return combined

def get_52w_low(price_history: pd.DataFrame) -> pd.Series:
    """stock_code -> 캐시에 쌓인 기간 내 최저가(low의 최솟값)."""
    return price_history.groupby("stock_code")["low"].min()
```
`date` 컬럼은 `YYYYMMDD` 문자열이라 사전식 비교로 cutoff 필터링이 가능(기존 코드베이스의
날짜 문자열 관례를 그대로 따름).

## B. 새 스크리닝 모듈 (`screening/cheap_screen.py`)

`ws_alpha.py`의 `load_real`/`run_real` 패턴을 따르되 4대 팩터 스코어링은 없음.

```python
def load_cheap(date: str, bsns_year: int) -> tuple[pd.DataFrame, str]:
    # get_full_universe로 가격/시총 스냅샷 확보 (ws_alpha.load_real과 동일)
    # → update_price_history()로 오늘자 저가 append
    # → get_52w_low()로 종목별 52주 최저가 산출
    # → FINANCE_CACHE에서 bsns_year 재무 join (op_ttm, op_income_5y_ago, cash_equivalents,
    #   total_liabilities 포함 — data_pipeline.py A절 확장분)
    # → 파생 컬럼 계산:
    #     low_52w
    #     dist_from_52w_low_pct = (close / low_52w - 1) * 100
    #     ev = mktcap + total_liabilities - cash_equivalents
    #     ebit = op_ttm
    #     ev_ebit = ev / ebit  (ebit <= 0이면 NaN)
    ...

def apply_cheap_filters(df: pd.DataFrame) -> pd.DataFrame:
    # 3개 조건 모두 결측이면 탈락 처리
    #  1) dist_from_52w_low_pct <= 10
    #  2) op_ttm > op_income_5y_ago
    #  3) ebit > 0 and ev_ebit < 10
    ...
```
정렬: `ev_ebit` 오름차순.

출력 컬럼(및 한글 라벨):
```python
COLS = ["name", "sector_raw", "mktcap_eok", "close", "low_52w",
        "dist_from_52w_low_pct", "op_ttm", "op_income_5y_ago", "ev_ebit"]
KOR_NAMES = {
    "name": "종목명", "sector_raw": "시장", "mktcap_eok": "시가총액(억)",
    "close": "종가", "low_52w": "52주최저가", "dist_from_52w_low_pct": "52주저가대비(%)",
    "op_ttm": "영업이익(TTM,억원)", "op_income_5y_ago": "영업이익(5년전,억원)",
    "ev_ebit": "EV/EBIT",
}
```
`op_ttm`/`op_income_5y_ago`는 원 단위로 계산되므로 export 시 억원 단위로 나눠서 표시
(기존 `mktcap_eok`와 동일한 관례).

`run_cheap()`은 `ws_alpha.run_real()`과 동일하게:
- 상위 N종목(50) 프로필을 `stock_profile.generate_all_profiles()`로 생성(가치투자 탭과
  동일 UX — 종목명 클릭 시 사업내용/경쟁사 모달).
- `web/data/results_cheap.json` (draft-then-fill 패턴 유지 — 프로필 생성 중 중단돼도 유효한
  JSON이 남도록)
- `web/data/filtered_cheap_full.json` (통과 전체 종목, 프로필 없음 — 기존 `filtered_full.json`
  과 동일 패턴)

`results_cheap.json` 스키마는 `ResultsPayload`와 완전히 동일(컬럼만 다름). `quote_text`/
`quote_author`는 가치투자 탭과 동일 주간 명언(`quotes.pick_quote_for_week()`)을 재사용.

## C. GitHub Actions (`daily-screen.yml`)

"오늘자 가격 기준 스크리닝 실행 + JSON 저장" 스텝 뒤에 추가:
```yaml
      - name: Cheap Stock Picking 스크리닝 실행 + JSON 저장
        working-directory: screening
        env:
          KRX_API_KEY: ${{ secrets.KRX_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          TODAY=$(TZ=Asia/Seoul date -d '1 day ago' +%Y%m%d)
          YEAR=$(cat .cache/annual_year.txt 2>/dev/null || echo 2025)
          python cheap_screen.py --run --date $TODAY --year $YEAR --top 50 \
            --export-json "../web/data/results_cheap.json" \
            --filtered-json "../web/data/filtered_cheap_full.json"
```
커밋 스텝의 `git add` 대상에 다음 3개 파일 추가:
```
screening/data/price_history.parquet web/data/results_cheap.json web/data/filtered_cheap_full.json
```

## D. 프런트엔드

### D-1. Tabs 컴포넌트
`web/components/ui/tabs.tsx` 신규 — 이미 설치된 `radix-ui` 패키지의 `Tabs` export를
사용한 shadcn 스타일 래퍼(`TabsList`/`TabsTrigger`/`TabsContent`).

### D-2. 공통 스크리닝 뷰 추출
`page.tsx`에서 배지행(기준일/재무연도/다운로드/갱신시각) + `AlgorithmInfo` + `ScreeningTable`
블록을 `web/app/ScreeningSection.tsx`로 추출:
```tsx
export default function ScreeningSection({
  data, algorithmInfo, downloadHref,
}: {
  data: ResultsPayload;
  algorithmInfo: React.ReactNode;
  downloadHref: string;
}) { /* 기존 page.tsx의 결과 표시 블록 그대로 이동 */ }
```
빈 상태("아직 결과가 없습니다…") 분기도 이 컴포넌트 안으로 이동.

### D-3. `FilteredDownloadButton` 일반화
```tsx
interface Props { href: string; passed: number; total: number; }
```
`<a href="/api/filtered">` → `<a href={href}>`로 변경. 표시 텍스트(`필터 통과 ${passed} / ${total}`)는
두 탭 모두 동일하게 유지 — 탭 자체가 이미 어느 스크리닝인지 구분해주므로 버튼 문구를
탭별로 다르게 만들 필요가 없다.

### D-4. `CheapAlgorithmInfo.tsx` 신규
`AlgorithmInfo.tsx`와 동일한 `<details>` 카드 구조로 3가지 기준 설명:
- 52주 최저가 10% 이내
- 영업이익이 5년 전보다 증가
- EV/EBIT 10배 미만 (EV = 시총 + 총부채 − 현금성자산 근사치라는 점 명시)
- 데이터 기준 섹션(가격/재무 출처)도 동일하게 포함.

### D-5. `/api/filtered-cheap/route.ts` 신규
기존 `web/app/api/filtered/route.ts`와 동일 구조, `filtered_cheap_full.json` 대상,
다운로드 파일명만 다르게(`cheap-stocks.xlsx` 등).

### D-6. `page.tsx` 재구성
```tsx
const data = loadResults();              // 기존 results.json
const cheapData = loadResultsCheap();    // results_cheap.json, 없으면 빈 payload

<Tabs defaultValue="value">
  <TabsList>
    <TabsTrigger value="value">가치투자</TabsTrigger>
    <TabsTrigger value="cheap">Cheap Stock Picking</TabsTrigger>
  </TabsList>
  <TabsContent value="value">
    <ScreeningSection data={data} algorithmInfo={<AlgorithmInfo />}
      downloadHref="/api/filtered" />
  </TabsContent>
  <TabsContent value="cheap">
    <ScreeningSection data={cheapData} algorithmInfo={<CheapAlgorithmInfo />}
      downloadHref="/api/filtered-cheap" />
  </TabsContent>
</Tabs>
```
`loadResultsCheap()`은 파일이 없으면(최초 배포 시점) `results: []`인 빈 payload를 반환해
기존 "아직 결과가 없습니다" 빈 상태를 그대로 재사용한다.

`AdminGate`는 탭 바깥, 페이지 하단에 그대로 유지(두 탭 공용).

## E. 테스트

- `screening/tests/`:
  - `test_data_pipeline.py`(또는 신규 파일): `update_price_history()` append/중복제거/윈도우
    필터링 동작, `get_52w_low()` 집계 로직.
  - `test_cheap_screen.py` 신규: `apply_cheap_filters()` 3개 조건 각각 단독 테스트(경계값
    10% 정확히, 결측치 처리), `ev_ebit` 계산 순수 함수 테스트.
- `web/tests/`:
  - `FilteredDownloadButton` prop 변경 반영 테스트.
  - `/api/filtered-cheap` route 테스트(기존 `/api/filtered` 테스트 패턴 복제).
  - `ScreeningSection` 렌더링(빈 상태 포함) 테스트.
- 수동 확인: `npm run dev`로 두 탭 전환, 정렬/새로고침/모달 동작, 빌드(`npm run build`) 통과.

## 영향받는 파일

**Python**
- `screening/data_pipeline.py` (ACCOUNT_MAP 추가, `fetch_op_income_5y_ago`,
  `update_price_history`, `get_52w_low`, `fetch_finance_one` 반환값 확장)
- `screening/cheap_screen.py` (신규)
- `screening/tests/test_cheap_screen.py` (신규), 기존 파이프라인 테스트 파일 확장

**웹**
- `web/app/page.tsx` (탭 구조로 재구성)
- `web/app/ScreeningSection.tsx` (신규, `page.tsx`에서 추출)
- `web/app/CheapAlgorithmInfo.tsx` (신규)
- `web/app/FilteredDownloadButton.tsx` (props 일반화)
- `web/app/api/filtered-cheap/route.ts` (신규)
- `web/components/ui/tabs.tsx` (신규)
- `web/lib/types.ts` (변경 불필요 — 기존 제네릭 스키마 재사용)
- 관련 테스트 파일

**인프라**
- `.github/workflows/daily-screen.yml` (cheap_screen 실행 스텝 + 커밋 대상 추가)

## 비용/성능 참고

- 분기 재무 강제갱신 시 종목당 DART 호출 1회 추가(약 2500종목 × 0.3초 ≈ 12분 추가, 분기당
  1회이므로 매일 영향 없음).
- 프로필 생성(Claude Haiku) 호출이 하루 50회 → 100회로 증가(가치투자 탭 50 + Cheap 탭 50).
- `price_history.parquet`는 매일 커밋되어 git 리포지토리 크기가 점진적으로 증가하나,
  370일 윈도우로 상한이 있어 파일 자체 크기는 안정화됨.
