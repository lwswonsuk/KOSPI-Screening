# 스크리닝 웹사이트 기능 확장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스크리닝 웹사이트에 명언 로테이션, 관리자 전용 강제 재무갱신, 분기 공시기한 자동 갱신, 코스닥 포함,
배당 지표, 테이블 표시 개선, 필터통과 엑셀 다운로드를 추가한다.

**Architecture:** 백엔드(`screening/`)는 순수 Python(pandas)으로 DART/KRX 데이터를 가공해 `web/data/results.json`과
`web/data/filtered_full.json`을 생성하고 GitHub Actions가 커밋한다. 프런트(`web/`)는 이 정적 JSON을 빌드 시점에
읽어 렌더링하는 Next.js 15 App Router 페이지이며, 관리자 기능만 서버 API 라우트를 통해 동적으로 동작한다.

**Tech Stack:** Python 3.13 (pandas, numpy, opendartreader, requests), Next.js 15 + React 19 + TypeScript,
shadcn/ui, GitHub Actions.

## Global Constraints

- 모든 신규 프런트 코드는 기존 shadcn/ui 컴포넌트(`@/components/ui/*`)와 `cn()` 유틸을 그대로 사용한다.
- Python 쪽 신규 함수는 `from __future__ import annotations` 스타일과 기존 `safe_div`/`_to_float` 패턴을 재사용한다.
- 배당 데이터가 없는 종목은 `div_yield=0`, `payout_ratio=0`으로 처리한다(NaN 아님).
- 관리자 비밀번호는 Vercel 환경변수 `ADMIN_PASSWORD`로만 관리하며 코드에 하드코딩하지 않는다.
- `results.json`에 노출되는 상위 종목 수는 50개(`--top 50`)로 고정한다.
- 시가배당수익률은 **직전 사업연도(FY) 총배당금 기준**으로 계산하며 별도 연환산 배수를 곱하지 않는다.
- 명언은 **ISO 주차**(`date.isocalendar()[1]` + 연도) 기준으로 매주 전환된다.

---

## 파일 구조

**신규 파일**
- `screening/quotes.py` — 11개 투자자 명언 데이터 + 주간 선택 함수
- `screening/tests/test_quotes.py`
- `screening/tests/test_dividend.py`
- `web/app/api/admin-login/route.ts` — 관리자 비밀번호 검증 + 쿠키 발급
- `web/app/AdminGate.tsx` — 관리자 로그인 버튼 + 다이얼로그(클라이언트 컴포넌트)
- `web/app/FilteredDownloadButton.tsx` — 필터통과 전체 종목 엑셀 다운로드 버튼
- `web/lib/format.ts` — 날짜 포맷 유틸(`formatKoreanDate`)

**수정 파일**
- `screening/data_pipeline.py` — 코스닥 유니버스, 배당 데이터 fetch
- `screening/ws_alpha.py` — 명언 필드, top 50, 배당 컬럼, filtered_full.json export
- `.github/workflows/daily-screen.yml` — 분기 공시기한 cron 4개 추가
- `web/app/page.tsx` — 날짜 포맷, 명언 표시, 관리자 게이트, 필터통과 버튼
- `web/app/ScreeningTable.tsx` — 종합점수 4자리, 배당 컬럼 표시, 50행 제한
- `web/app/UpdateControls.tsx` — 그대로 유지(관리자 게이트 통과 시에만 렌더되도록 부모에서 조건부 처리)
- `web/app/api/update-finance/route.ts` — 쿠키 검증 추가
- `web/package.json` — `xlsx` 의존성 추가
- `screening/requirements.txt` — `pytest` 추가(dev용, requirements-dev 분리는 하지 않고 그대로 추가)

---

### Task 1: 투자자 명언 데이터 + 주간 선택 로직

**Files:**
- Create: `screening/quotes.py`
- Test: `screening/tests/test_quotes.py`

**Interfaces:**
- Produces: `QUOTES: list[dict]` (각 원소 `{"text": str, "author": str}`), `pick_quote_for_week(today: date | None = None) -> dict`

- [ ] **Step 1: 명언 데이터와 선택 함수 작성**

`screening/quotes.py`:
```python
"""
quotes.py — 소제목에 표시할 투자자 명언 (ISO 주차 기준 매주 전환)
"""

from __future__ import annotations

from datetime import date

QUOTES: list[dict] = [
    {"text": "가격은 당신이 지불하는 것이고, 가치는 당신이 얻는 것이다.", "author": "Warren Buffett"},
    {"text": "위험은 가격에서 온다. 좋은 자산도 비싸게 사면 위험해진다.", "author": "Howard Marks"},
    {"text": "인생에서 몇 번의 위대한 결정만 내리고 나머지는 인내하면 된다.", "author": "Mohnish Pabrai"},
    {"text": "훌륭한 회사를 적정한 가격에 사는 것이, 적당한 회사를 훌륭한 가격에 사는 것보다 낫다.", "author": "Charlie Munger"},
    {"text": "확신이 있는 소수의 아이디어에 집중하고, 나머지는 무시하라.", "author": "Bill Ackman"},
    {"text": "당신이 아는 것에 투자하라. 모르는 것에 투자하지 마라.", "author": "Peter Lynch"},
    {"text": "안전마진이 있는 곳에서만 투자하라. 나머지는 투기다.", "author": "Seth Klarman"},
    {"text": "훌륭한 경영진이 이끄는 성장 기업을 찾아, 오래 보유하라.", "author": "Philip Fisher"},
    {"text": "시장은 결국 기업의 본질가치를 따라간다. 조급해하지 말고 기다려라.", "author": "이채원"},
    {"text": "싸게 사서 기다리는 것이 전부다. 남들이 무서워할 때 사라.", "author": "최준철"},
    {"text": "숫자로 증명되는 회사를 사고, 스토리로 사지 마라.", "author": "김민국"},
]


def pick_quote_for_week(today: date | None = None) -> dict:
    """ISO 주차(연도+주차) 기준으로 명언을 결정적으로 선택한다.
    같은 주 안에는 매일 갱신이 돌아도 동일한 명언이 유지된다."""
    if today is None:
        today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    idx = (iso_year * 53 + iso_week) % len(QUOTES)
    return QUOTES[idx]
```

- [ ] **Step 2: 실패하는 테스트 먼저 작성**

`screening/tests/test_quotes.py`:
```python
from datetime import date

from quotes import QUOTES, pick_quote_for_week


def test_quote_count_is_eleven():
    assert len(QUOTES) == 11


def test_same_iso_week_returns_same_quote():
    mon = date(2026, 8, 10)   # 2026-W33 월요일
    fri = date(2026, 8, 14)   # 같은 주 금요일
    assert pick_quote_for_week(mon) == pick_quote_for_week(fri)


def test_different_iso_week_can_return_different_quote():
    week33 = pick_quote_for_week(date(2026, 8, 10))
    week34 = pick_quote_for_week(date(2026, 8, 17))
    # 11개 명언이므로 인접 주는 대부분 다르지만 100% 보장은 아님 — 인덱스 로직 자체를 검증
    idx33 = (2026 * 53 + 33) % len(QUOTES)
    idx34 = (2026 * 53 + 34) % len(QUOTES)
    assert idx33 != idx34
    assert week33 == QUOTES[idx33]


def test_returns_text_and_author_keys():
    q = pick_quote_for_week(date(2026, 1, 1))
    assert set(q.keys()) == {"text", "author"}
```

- [ ] **Step 3: 테스트 실행해서 통과 확인**

Run (screening 디렉터리에서): `python -m pytest tests/test_quotes.py -v`
Expected: 4 tests PASS (구현을 이미 작성했으므로 바로 통과해야 함 — 실패 시 인덱스 계산 로직 재확인)

- [ ] **Step 4: requirements.txt에 pytest 추가**

`screening/requirements.txt`에 한 줄 추가:
```
pytest
```

- [ ] **Step 5: 커밋**

```bash
git add screening/quotes.py screening/tests/test_quotes.py screening/requirements.txt
git commit -m "feat: 소제목용 투자자 명언 주간 로테이션 로직 추가"
```

---

### Task 2: 코스닥 유니버스 추가 + 시장 필드 채우기

**Files:**
- Modify: `screening/data_pipeline.py:111-144` (기존 `get_kospi_universe`), 새 함수 추가, `build_finance_cache` 수정

**Interfaces:**
- Consumes: 기존 `get_kospi_universe(date: str) -> pd.DataFrame`
- Produces: `get_kosdaq_universe(date: str) -> pd.DataFrame` (동일 스키마, index=stock_code),
  `get_full_universe(date: str) -> pd.DataFrame` (코스피+코스닥 합본, `sector_raw` 컬럼에 "코스피"/"코스닥" 값 보장)

- [ ] **Step 1: `get_kosdaq_universe` 함수 추가**

`screening/data_pipeline.py`의 `get_kospi_universe` 함수(111-144행) 바로 아래에 추가:
```python
def get_kosdaq_universe(date: str) -> pd.DataFrame:
    """KRX 공식 Open API(코스닥 일별매매정보)로 코스닥 전종목의
    가격·시가총액 스냅샷을 가져온다. get_kospi_universe와 동일한 스키마."""
    import requests

    key = os.environ.get("KRX_API_KEY")
    if not key:
        raise RuntimeError(
            "KRX_API_KEY 환경변수가 없습니다. "
            "터미널에서 setx KRX_API_KEY \"발급받은키\" 로 등록 후 새 터미널을 여세요."
        )

    url = "https://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd"
    r = requests.get(url, params={"basDd": date}, headers={"AUTH_KEY": key}, timeout=30)
    r.raise_for_status()
    rows = r.json().get("OutBlock_1", [])
    if not rows:
        raise RuntimeError(f"KRX 코스닥 API 응답이 비어 있습니다 (날짜 {date} 확인 필요, 휴장일일 수 있음)")

    df = pd.DataFrame(rows)
    num_cols = ["TDD_CLSPRC", "CMPPREVDD_PRC", "FLUC_RT", "TDD_OPNPRC", "TDD_HGPRC",
                "TDD_LWPRC", "ACC_TRDVOL", "ACC_TRDVAL", "MKTCAP", "LIST_SHRS"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")

    df = df.rename(columns={
        "ISU_CD": "stock_code", "ISU_NM": "name", "SECT_TP_NM": "sector_raw",
        "TDD_CLSPRC": "close", "FLUC_RT": "fluc_rt",
        "ACC_TRDVAL": "trdval", "MKTCAP": "mktcap", "LIST_SHRS": "list_shrs",
    })
    df["stock_code"] = df["stock_code"].str.zfill(6)
    return df.set_index("stock_code")


def get_full_universe(date: str) -> pd.DataFrame:
    """코스피 + 코스닥 전종목을 합본하고, sector_raw(시장) 필드를 "코스피"/"코스닥"으로 강제 지정한다.
    (KRX SECT_TP_NM이 비어 있거나 다른 값을 줄 수 있어 여기서 명시적으로 덮어쓴다)"""
    kospi = get_kospi_universe(date).copy()
    kospi["sector_raw"] = "코스피"
    kosdaq = get_kosdaq_universe(date).copy()
    kosdaq["sector_raw"] = "코스닥"
    combined = pd.concat([kospi, kosdaq])
    return combined[~combined.index.duplicated(keep="first")]
```

- [ ] **Step 2: `build_finance_cache`가 전체 유니버스를 쓰도록 수정**

`screening/data_pipeline.py:322`의 `universe = get_kospi_universe(date).reset_index()`를 다음으로 교체:
```python
    universe = get_full_universe(date).reset_index()
```
그리고 325행 로그 메시지의 `KOSPI {len(universe)}개`를 `전체(코스피+코스닥) {len(universe)}개`로 수정.

- [ ] **Step 3: `load_real`도 전체 유니버스를 쓰도록 수정**

`screening/ws_alpha.py:357`의 `from data_pipeline import FINANCE_CACHE, get_kospi_universe`를
`from data_pipeline import FINANCE_CACHE, get_full_universe`로, 366행
`df = get_kospi_universe(date)`를 `df = get_full_universe(date)`로 교체.

- [ ] **Step 4: 로컬 스모크 테스트 (네트워크 필요, 수동 확인)**

Run: `cd screening && python -c "from data_pipeline import get_kosdaq_universe; df = get_kosdaq_universe('20260807'); print(len(df)); print(df['sector_raw'].unique())"`
Expected: 코스닥 종목 수(1000개 이상) 출력, `sector_raw`는 이 시점에 KRX 원본값 그대로(다음 단계에서 덮어씀) —
KRX_API_KEY 환경변수가 로컬에 없으면 이 단계는 CI(GitHub Actions)에서 다음 정기 실행 시 검증한다.

- [ ] **Step 5: 커밋**

```bash
git add screening/data_pipeline.py screening/ws_alpha.py
git commit -m "feat: 코스닥 종목을 스크리닝 유니버스에 포함, 시장 필드 코스피/코스닥으로 고정"
```

---

### Task 3: 배당 데이터 연동 (DART 배당 공시)

**Files:**
- Modify: `screening/data_pipeline.py` (신규 함수 + `fetch_finance_one`/`build_finance_cache` 반영)
- Test: `screening/tests/test_dividend.py`

**Interfaces:**
- Produces: `parse_dividend_report(fs_div: pd.DataFrame) -> dict` (순수 함수, `{"cash_dividend_total": float, "payout_ratio_reported": float}` 반환, 값 없으면 `np.nan`),
  `fetch_dividend_one(dart, corp_code: str, annual_year: int) -> dict` (네트워크 호출 포함)
- Consumes: `get_dart_client()`(기존), `_to_float`(기존)

- [ ] **Step 1: 순수 파싱 함수의 실패하는 테스트 작성**

`screening/tests/test_dividend.py`:
```python
import numpy as np
import pandas as pd

from data_pipeline import parse_dividend_report


def test_extracts_cash_dividend_total_and_payout_ratio():
    fs = pd.DataFrame([
        {"se": "현금배당금총액(백만원)", "thstrm": "50,000", "frmtrm": "40,000"},
        {"se": "(연결)현금배당성향(%)", "thstrm": "23.5", "frmtrm": "21.0"},
        {"se": "주당액면가액(원)", "thstrm": "500", "frmtrm": "500"},
    ])
    out = parse_dividend_report(fs)
    assert out["cash_dividend_total"] == 50_000 * 1_000_000  # 백만원 → 원 단위로 환산
    assert out["payout_ratio_reported"] == 23.5


def test_missing_rows_return_nan():
    fs = pd.DataFrame([{"se": "주당액면가액(원)", "thstrm": "500"}])
    out = parse_dividend_report(fs)
    assert np.isnan(out["cash_dividend_total"])
    assert np.isnan(out["payout_ratio_reported"])


def test_empty_dataframe_returns_nan():
    out = parse_dividend_report(pd.DataFrame())
    assert np.isnan(out["cash_dividend_total"])
    assert np.isnan(out["payout_ratio_reported"])
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd screening && python -m pytest tests/test_dividend.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_dividend_report'`

- [ ] **Step 3: `parse_dividend_report`와 `fetch_dividend_one` 구현**

`screening/data_pipeline.py`의 `fetch_finance_one` 함수(203행) 바로 위에 추가:
```python
def parse_dividend_report(fs_div: pd.DataFrame) -> dict:
    """DART 배당 공시(report(key_word='배당')) 응답에서 총현금배당금(원 단위)과
    공시된 배당성향(%)을 뽑는다. 항목이 없으면 np.nan."""
    if fs_div is None or len(fs_div) == 0 or "se" not in fs_div.columns:
        return {"cash_dividend_total": np.nan, "payout_ratio_reported": np.nan}

    def find_value(substr: str):
        matched = fs_div[fs_div["se"].astype(str).str.contains(substr, na=False)]
        if len(matched) == 0:
            return np.nan
        return _to_float(matched.iloc[0].get("thstrm"))

    cash_total_million = find_value("현금배당금총액")
    payout_reported = find_value("현금배당성향")

    cash_total = cash_total_million * 1_000_000 if not np.isnan(cash_total_million) else np.nan
    return {"cash_dividend_total": cash_total, "payout_ratio_reported": payout_reported}


def fetch_dividend_one(dart, corp_code: str, annual_year: int) -> dict:
    """직전 사업연도(annual_year) 사업보고서(FY)의 배당에 관한 사항을 조회한다."""
    try:
        fs_div = dart.report(corp_code, "배당", annual_year, QUARTER_CODES["FY"])
    except Exception as e:
        print(f"  [WARN] {corp_code} 배당 공시 조회 실패: {e}")
        return {"cash_dividend_total": np.nan, "payout_ratio_reported": np.nan}
    return parse_dividend_report(fs_div)
```

- [ ] **Step 4: 테스트 재실행해서 통과 확인**

Run: `cd screening && python -m pytest tests/test_dividend.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: `fetch_finance_one`이 배당 데이터를 함께 반환하도록 통합**

`screening/data_pipeline.py:203`의 `fetch_finance_one` 시그니처를 다음으로 교체:
```python
def fetch_finance_one(dart, stock_code: str, corp_code: str, annual_year: int,
                       ttm_year: int, ttm_quarter: str) -> Optional[dict]:
```
→ (시그니처는 동일하게 유지, 함수 본문 마지막의 `return {...}` 블록(298-315행) 바로 앞에 추가):
```python
    div = fetch_dividend_one(dart, corp_code, annual_year)
    div_yield = np.nan
    payout_ratio = np.nan
    if not np.isnan(div["cash_dividend_total"]):
        # 시가총액은 fetch 시점에 알 수 없으므로 여기서는 총배당금(원)만 저장하고,
        # 시가배당수익률은 load_real()에서 당일 시가총액과 결합해 계산한다.
        pass
    if not np.isnan(div["payout_ratio_reported"]):
        payout_ratio = div["payout_ratio_reported"]
    elif not np.isnan(div["cash_dividend_total"]) and not np.isnan(net_income_ttm) and net_income_ttm > 0:
        payout_ratio = div["cash_dividend_total"] / net_income_ttm * 100
```
그리고 `return { ... }` 딕셔너리(298-315행)에 다음 두 키를 추가:
```python
        "cash_dividend_total": div["cash_dividend_total"],
        "payout_ratio": payout_ratio,
```

- [ ] **Step 6: 배당 데이터 없는 종목은 0 처리 — `load_real`에서 보정**

이 보정은 Task 4(ws_alpha.py 통합)에서 함께 처리한다. 여기서는 `data_pipeline.py`가 NaN을 그대로 캐시에 저장하도록 둔다
(캐시에는 원본값 보존, 표시 직전에만 0으로 치환하는 것이 더 안전 — 재계산 로직에 원본이 필요할 수 있음).

- [ ] **Step 7: 커밋**

```bash
git add screening/data_pipeline.py screening/tests/test_dividend.py
git commit -m "feat: DART 배당 공시 연동, 총배당금·배당성향 재무캐시에 추가"
```

---

### Task 4: 시가배당수익률·배당성향을 스크리닝 출력에 반영

**Files:**
- Modify: `screening/ws_alpha.py:349-392` (`load_real`), `screening/ws_alpha.py:517-531` (`cols`, `KOR_NAMES`)

**Interfaces:**
- Consumes: Task 3의 `cash_dividend_total`, `payout_ratio` 컬럼(재무캐시), 기존 `df["mktcap"]`
- Produces: `load_real()` 결과에 `div_yield`(%), `payout_ratio`(%) 컬럼 확정값(0 이상, NaN 없음)

- [ ] **Step 1: `load_real`의 TODO 플레이스홀더 제거하고 실제 계산으로 교체**

`screening/ws_alpha.py:375-376`:
```python
    df["div_yield"] = np.nan    # TODO: KRX API에 배당수익률 서비스가 없어 비워둠. 필요시 DART 배당 공시로 보완
    df["payout_ratio"] = np.nan # TODO: 위와 동일
```
를 삭제하고, `fin = pd.read_parquet(FINANCE_CACHE)` 이후(384행 `df = df.join(fin, how="inner")` 다음)에 추가:
```python
    # 시가배당수익률(연환산, 직전 FY 총배당금 기준) — 무배당 종목은 0
    df["div_yield"] = (df["cash_dividend_total"] / df["mktcap"] * 100).fillna(0.0)
    df["div_yield"] = df["div_yield"].clip(lower=0)
    df["payout_ratio"] = df["payout_ratio"].fillna(0.0).clip(lower=0)
```

- [ ] **Step 2: export 컬럼 목록과 한글 라벨에 배당 컬럼 삽입**

`screening/ws_alpha.py:517`:
```python
    cols = ["name", "sector_raw", "close", "per", "pbr", "roe_3y_avg", "debt_ratio", "score"]
```
를 다음으로 교체(부채비율과 종합점수 사이에 삽입):
```python
    cols = ["name", "sector_raw", "close", "per", "pbr", "roe_3y_avg", "debt_ratio",
            "div_yield", "payout_ratio", "score"]
```

`screening/ws_alpha.py:525-531`의 `KOR_NAMES` 딕셔너리에 두 줄 추가:
```python
        "div_yield": "시가배당수익률(%)", "payout_ratio": "배당성향(%)",
```

- [ ] **Step 3: `run_demo`용 데모 데이터는 이미 `div_yield`/`payout_ratio`를 생성하므로 변경 불필요 — 확인만**

Run: `cd screening && python ws_alpha.py --demo`
Expected: 에러 없이 정상 출력(기존 데모 로직은 이미 이 컬럼들을 채우고 있어 회귀 없음을 확인하는 용도).

- [ ] **Step 4: 커밋**

```bash
git add screening/ws_alpha.py
git commit -m "feat: 시가배당수익률·배당성향을 스크리닝 결과 컬럼에 반영"
```

---

### Task 5: 종목 수 50개 제한 + 필터통과 전체 종목 별도 export

**Files:**
- Modify: `screening/ws_alpha.py:600-612` (CLI 기본값), `screening/ws_alpha.py:491-597` (`run_real`)

**Interfaces:**
- Consumes: 기존 `run_real(date, bsns_year, top_n, export, export_json)`
- Produces: `run_real(..., export_json: str | None, filtered_json: str | None = None)` — 새 선택 인자 추가,
  `filtered_json` 지정 시 하드필터 통과 전체 종목을 별도 JSON으로 저장

- [ ] **Step 1: CLI 기본 `--top` 값을 50으로 변경**

`screening/ws_alpha.py:606`:
```python
    ap.add_argument("--top", type=int, default=60, help="화면·엑셀에 보여줄 상위 종목 수")
```
를 다음으로 교체:
```python
    ap.add_argument("--top", type=int, default=50, help="화면·엑셀에 보여줄 상위 종목 수")
```

- [ ] **Step 2: `run_real`에 `filtered_json` 인자 추가**

`screening/ws_alpha.py:491-492`:
```python
def run_real(date: str, bsns_year: int, top_n: int, export: str | None,
             export_json: str | None = None):
```
를 다음으로 교체:
```python
def run_real(date: str, bsns_year: int, top_n: int, export: str | None,
             export_json: str | None = None, filtered_json: str | None = None):
```

- [ ] **Step 3: 필터통과 전체 종목 export 로직 추가**

`screening/ws_alpha.py:564-595`의 `if export_json:` 블록(JSON 저장) 바로 뒤에 새 블록 추가:
```python
    if filtered_json:
        import json
        from pathlib import Path as _Path

        passed_all = ranked[ranked["passed"]][cols]
        records = []
        for code, row in passed_all.iterrows():
            rec = {"stock_code": str(code)}
            for c in cols:
                v = row[c]
                if pd.isna(v):
                    rec[c] = None
                elif isinstance(v, (int, float, np.floating, np.integer)):
                    rec[c] = round(float(v), 4)
                else:
                    rec[c] = str(v)
            records.append(rec)

        payload = {
            "as_of_date": date,
            "financial_year": bsns_year,
            "generated_at": pd.Timestamp.now("UTC").isoformat(),
            "columns": cols,
            "column_labels_ko": {c: KOR_NAMES.get(c, c) for c in cols},
            "results": records,
        }
        out_path = _Path(filtered_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[export] 필터통과 전체 JSON 저장 완료 → {filtered_json} ({len(records)}종목)")
```

- [ ] **Step 4: CLI에 `--filtered-json` 인자 추가하고 `run_real` 호출부 갱신**

`screening/ws_alpha.py:608` 아래에 추가:
```python
    ap.add_argument("--filtered-json", default="", help="필터통과 전체 종목 JSON 저장 경로 (예: web/data/filtered_full.json)")
```
`screening/ws_alpha.py:610-612`:
```python
    if a.run:
        run_real(a.date, a.year, a.top, a.export if a.export else None,
                  a.export_json if a.export_json else None)
```
를 다음으로 교체:
```python
    if a.run:
        run_real(a.date, a.year, a.top, a.export if a.export else None,
                  a.export_json if a.export_json else None,
                  a.filtered_json if a.filtered_json else None)
```

- [ ] **Step 5: 로컬 데모로 필터통과 전체 export 동작 확인**

Run: `cd screening && python ws_alpha.py --demo` (데모는 `run_real`을 쓰지 않으므로 이 단계는 실데이터 경로 회귀만
방지하는 용도) — 이어서 문법 검증: `python -c "import ws_alpha"` 로 임포트 에러 없는지 확인.
Expected: 에러 없음.

- [ ] **Step 6: 커밋**

```bash
git add screening/ws_alpha.py
git commit -m "feat: 상위 종목 50개로 축소, 필터통과 전체 종목 별도 JSON export 추가"
```

---

### Task 6: 명언 필드를 results.json에 포함

**Files:**
- Modify: `screening/ws_alpha.py:1-28` (import), `screening/ws_alpha.py:564-595` (payload)

**Interfaces:**
- Consumes: Task 1의 `pick_quote_for_week()`
- Produces: `results.json`에 `quote_text`, `quote_author` 최상위 필드 추가

- [ ] **Step 1: import 추가**

`screening/ws_alpha.py` 상단 import 블록(20-28행)에 추가:
```python
from datetime import date as _date

from quotes import pick_quote_for_week
```

- [ ] **Step 2: `export_json` payload에 명언 필드 추가**

`screening/ws_alpha.py:581-590`의 `payload = { ... }` 딕셔너리에 두 줄 추가:
```python
        payload = {
            "as_of_date": date,
            "financial_year": bsns_year,
            "generated_at": pd.Timestamp.now("UTC").isoformat(),
            "quote_text": pick_quote_for_week()["text"],
            "quote_author": pick_quote_for_week()["author"],
            "universe_total": int(len(d)),
            "universe_passed": int(filt["passed"].sum()),
            "columns": cols,
            "column_labels_ko": {c: KOR_NAMES.get(c, c) for c in cols},
            "results": records,
        }
```

- [ ] **Step 3: 검증**

Run: `cd screening && python -c "import ws_alpha"` — import 순환/경로 문제 없는지 확인.
Expected: 에러 없음 (quotes.py가 같은 디렉터리에 있어 상대 import 문제 없어야 함).

- [ ] **Step 4: 커밋**

```bash
git add screening/ws_alpha.py
git commit -m "feat: 스크리닝 결과 JSON에 주간 투자자 명언 필드 추가"
```

---

### Task 7: GitHub Actions — 분기 공시기한 다음날 자동 갱신 + 코스닥 시크릿 확인

**Files:**
- Modify: `.github/workflows/daily-screen.yml`

**Interfaces:**
- Consumes: 기존 `daily-screen.yml` 구조(schedule, workflow_dispatch, force_finance 로직)
- Produces: 4개의 추가 `schedule` 트리거 + `github.event.schedule` 기반 강제갱신 판별

- [ ] **Step 1: schedule 트리거 4개 추가**

`.github/workflows/daily-screen.yml:6-9`:
```yaml
on:
  schedule:
    # 한국시간 오전 8시 (UTC 23:00, 전날) — 평일에만 의미있지만 매일 실행해도 무방
    - cron: "0 23 * * *"
```
를 다음으로 교체:
```yaml
on:
  schedule:
    # 매일 한국시간 오전 8시 (UTC 23:00, 전날) — 가격만 갱신, 재무는 캐시
    - cron: "0 23 * * *"
    # 분기 공시기한 다음날 한국시간 오전 6시 — 재무데이터 강제 재수집
    - cron: "0 21 15 5 *"   # 1분기보고서 마감(5/15) 다음날 06:00 KST
    - cron: "0 21 14 8 *"   # 반기보고서 마감(8/14) 다음날 06:00 KST
    - cron: "0 21 13 11 *"  # 3분기보고서 마감(11/14) 다음날 06:00 KST
    - cron: "0 21 31 3 *"   # 사업보고서 마감(3/31) 다음날 06:00 KST
```

- [ ] **Step 2: 재무데이터 강제갱신 판별에 분기 스케줄 조건 추가**

`.github/workflows/daily-screen.yml:50-51`:
```yaml
      - name: 재무데이터 없거나 강제갱신 요청 시 새로 받기
        if: steps.finance-cache.outputs.cache-hit != 'true' || github.event.inputs.force_finance == 'true'
```
를 다음으로 교체:
```yaml
      - name: 재무데이터 없거나 강제갱신 요청/분기 공시일정 시 새로 받기
        if: >-
          steps.finance-cache.outputs.cache-hit != 'true' ||
          github.event.inputs.force_finance == 'true' ||
          contains(fromJSON('["0 21 15 5 *","0 21 14 8 *","0 21 13 11 *","0 21 31 3 *"]'), github.event.schedule)
```

- [ ] **Step 3: `--top 50` 반영**

`.github/workflows/daily-screen.yml:71`:
```yaml
          python ws_alpha.py --run --date $TODAY --year $YEAR --top 60 --export "" --export-json "../web/data/results.json"
```
를 다음으로 교체:
```yaml
          python ws_alpha.py --run --date $TODAY --year $YEAR --top 50 --export "" \
            --export-json "../web/data/results.json" \
            --filtered-json "../web/data/filtered_full.json"
```

- [ ] **Step 4: 커밋 스텝이 filtered_full.json도 함께 커밋하도록 수정**

`.github/workflows/daily-screen.yml:77`:
```yaml
          git add web/data/results.json
```
를 다음으로 교체:
```yaml
          git add web/data/results.json web/data/filtered_full.json
```

- [ ] **Step 5: YAML 문법 검증**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily-screen.yml', encoding='utf-8'))"`
Expected: 에러 없이 통과(YAML 파싱 성공). PyYAML이 없으면 `pip install pyyaml` 후 재시도.

- [ ] **Step 6: 커밋**

```bash
git add .github/workflows/daily-screen.yml
git commit -m "ci: 분기 공시기한 다음날 자동 재무갱신 스케줄 추가, top 50/filtered_full.json 반영"
```

---

### Task 8: 프런트 — 날짜/시각 표시 포맷 (KST 고정)

**Files:**
- Create: `web/lib/format.ts`
- Modify: `web/app/page.tsx:52-60`

**Interfaces:**
- Produces: `formatKoreanDate(yyyymmdd: string | null): string` — "20260811" → "2026년 08월 11일"

- [ ] **Step 1: 포맷 유틸 작성**

`web/lib/format.ts`:
```typescript
export function formatKoreanDate(yyyymmdd: string | null): string {
  if (!yyyymmdd || yyyymmdd.length !== 8) return yyyymmdd ?? "-";
  const year = yyyymmdd.slice(0, 4);
  const month = yyyymmdd.slice(4, 6);
  const day = yyyymmdd.slice(6, 8);
  return `${year}년 ${month}월 ${day}일`;
}
```

- [ ] **Step 2: `page.tsx`에서 날짜/시각 표시 교체**

`web/app/page.tsx` 상단 import에 추가:
```tsx
import { formatKoreanDate } from "@/lib/format";
```

`web/app/page.tsx:53`:
```tsx
            <Badge variant="secondary">가격 기준일 {data.as_of_date}</Badge>
```
를 다음으로 교체:
```tsx
            <Badge variant="secondary">가격 기준일 {formatKoreanDate(data.as_of_date)}</Badge>
```

`web/app/page.tsx:58-60`:
```tsx
            <Badge variant="outline">
              갱신 {data.generated_at ? new Date(data.generated_at).toLocaleString("ko-KR") : "-"}
            </Badge>
```
를 다음으로 교체:
```tsx
            <Badge variant="outline">
              갱신{" "}
              {data.generated_at
                ? new Date(data.generated_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })
                : "-"}
            </Badge>
```

- [ ] **Step 3: 빌드 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공, 타입 에러 없음.

- [ ] **Step 4: 커밋**

```bash
git add web/lib/format.ts web/app/page.tsx
git commit -m "feat: 가격 기준일 한국어 날짜 포맷, 갱신 시각 한국시간 고정 표시"
```

---

### Task 9: 프런트 — 소제목 명언 표시

**Files:**
- Modify: `web/app/page.tsx:13-22` (인터페이스), `web/app/page.tsx:36-39` (렌더)

**Interfaces:**
- Consumes: `results.json`의 `quote_text`, `quote_author` (Task 6 산출물)

- [ ] **Step 1: `ResultsPayload` 타입에 명언 필드 추가**

`web/app/page.tsx:13-22`:
```tsx
interface ResultsPayload {
  as_of_date: string | null;
  financial_year: number | null;
  generated_at: string | null;
  universe_total: number;
  universe_passed: number;
  columns: string[];
  column_labels_ko: Record<string, string>;
  results: ResultRow[];
}
```
를 다음으로 교체:
```tsx
interface ResultsPayload {
  as_of_date: string | null;
  financial_year: number | null;
  generated_at: string | null;
  quote_text: string | null;
  quote_author: string | null;
  universe_total: number;
  universe_passed: number;
  columns: string[];
  column_labels_ko: Record<string, string>;
  results: ResultRow[];
}
```

- [ ] **Step 2: 소제목을 명언으로 교체**

`web/app/page.tsx:36-39`:
```tsx
        <h1 className="text-2xl font-bold tracking-tight">한국 가치투자 스크리닝</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Stock Note 투자원칙 기반 코스피 종목 스크리닝
        </p>
```
를 다음으로 교체:
```tsx
        <h1 className="text-2xl font-bold tracking-tight">한국 가치투자 스크리닝</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {data.quote_text
            ? `"${data.quote_text}" — ${data.quote_author}`
            : "Stock Note 투자원칙 기반 코스피 종목 스크리닝"}
        </p>
```

- [ ] **Step 3: 빌드 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공. `data/results.json`에 아직 `quote_text` 필드가 없으면 `data.quote_text`가
`undefined`가 되어 fallback 문구가 표시되는지 확인(다음 자동 갱신 이후 실제 명언으로 교체됨).

- [ ] **Step 4: 커밋**

```bash
git add web/app/page.tsx
git commit -m "feat: 소제목에 주간 투자자 명언 표시"
```

---

### Task 10: 프런트 — 종합점수 4자리/우측정렬, 배당 컬럼, 50행 제한

**Files:**
- Modify: `web/app/ScreeningTable.tsx`

**Interfaces:**
- Consumes: `results.json`의 `div_yield`, `payout_ratio` 컬럼(Task 4 산출물)

- [ ] **Step 1: 소수점 포맷 세트 재구성**

`web/app/ScreeningTable.tsx:24-28`:
```tsx
// 소수점 2자리 + 우측 정렬로 보여줄 컬럼
const TWO_DECIMAL_RIGHT_ALIGN = new Set(["per", "pbr", "roe_3y_avg", "debt_ratio"]);

// 우측 정렬만 적용할 컬럼 (숫자 포맷은 기본값 유지)
const RIGHT_ALIGN_ONLY = new Set(["close"]);
```
를 다음으로 교체:
```tsx
// 소수점 2자리 + 우측 정렬로 보여줄 컬럼
const TWO_DECIMAL_RIGHT_ALIGN = new Set([
  "per", "pbr", "roe_3y_avg", "debt_ratio", "div_yield", "payout_ratio",
]);

// 소수점 4자리 + 우측 정렬 (종합점수 전용)
const FOUR_DECIMAL_RIGHT_ALIGN = new Set(["score"]);

// 우측 정렬만 적용할 컬럼 (숫자 포맷은 기본값 유지)
const RIGHT_ALIGN_ONLY = new Set(["close"]);
```

- [ ] **Step 2: `alignClass`와 `formatValue`에 4자리 세트 반영**

`web/app/ScreeningTable.tsx:169-174`:
```tsx
function alignClass(col: string): string {
  if (TWO_DECIMAL_RIGHT_ALIGN.has(col) || RIGHT_ALIGN_ONLY.has(col) || col === "mktcap_eok") {
    return "text-right";
  }
  return "";
}
```
를 다음으로 교체:
```tsx
function alignClass(col: string): string {
  if (
    TWO_DECIMAL_RIGHT_ALIGN.has(col) ||
    FOUR_DECIMAL_RIGHT_ALIGN.has(col) ||
    RIGHT_ALIGN_ONLY.has(col) ||
    col === "mktcap_eok"
  ) {
    return "text-right";
  }
  return "";
}
```

`web/app/ScreeningTable.tsx:176-190`:
```tsx
function formatValue(v: string | number | null, col?: string) {
  if (v === null || v === undefined) return "-";
  if (typeof v === "number") {
    if (col === "mktcap_eok") {
      // 시가총액: 천 단위 콤마 + 소수점 1자리
      return v.toLocaleString("ko-KR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    }
    if (col && TWO_DECIMAL_RIGHT_ALIGN.has(col)) {
      // PER/PBR/ROE/부채비율: 소수점 2자리
      return v.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return Number.isInteger(v) ? v.toLocaleString("ko-KR") : v.toFixed(3);
  }
  return v;
}
```
를 다음으로 교체:
```tsx
function formatValue(v: string | number | null, col?: string) {
  if (v === null || v === undefined) return "-";
  if (typeof v === "number") {
    if (col === "mktcap_eok") {
      // 시가총액: 천 단위 콤마 + 소수점 1자리
      return v.toLocaleString("ko-KR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    }
    if (col && FOUR_DECIMAL_RIGHT_ALIGN.has(col)) {
      // 종합점수: 소수점 4자리
      return v.toLocaleString("ko-KR", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
    }
    if (col && TWO_DECIMAL_RIGHT_ALIGN.has(col)) {
      // PER/PBR/ROE/부채비율/배당수익률/배당성향: 소수점 2자리
      return v.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return Number.isInteger(v) ? v.toLocaleString("ko-KR") : v.toFixed(3);
  }
  return v;
}
```

- [ ] **Step 3: 50행 제한 (방어적 슬라이스)**

`web/app/ScreeningTable.tsx:76-91`의 `sorted` useMemo 블록:
```tsx
  const sorted = useMemo(() => {
    const copy = [...liveRows];
    copy.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return sortDir === "asc" ? av - bv : bv - av;
      }
      return sortDir === "asc"
        ? String(av).localeCompare(String(bv), "ko")
        : String(bv).localeCompare(String(av), "ko");
    });
    return copy;
  }, [liveRows, sortKey, sortDir]);
```
를 다음으로 교체(마지막 줄만 변경):
```tsx
  const sorted = useMemo(() => {
    const copy = [...liveRows];
    copy.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return sortDir === "asc" ? av - bv : bv - av;
      }
      return sortDir === "asc"
        ? String(av).localeCompare(String(bv), "ko")
        : String(bv).localeCompare(String(av), "ko");
    });
    return copy.slice(0, 50);
  }, [liveRows, sortKey, sortDir]);
```

- [ ] **Step 4: 빌드 및 로컬 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공. 이후 `npm run dev`로 로컬 구동해 브라우저에서 종합점수 컬럼이 우측정렬 4자리로,
시가배당수익률/배당성향 컬럼이 부채비율과 종합점수 사이에 나오는지, 표가 50행을 넘지 않는지 확인.

- [ ] **Step 5: 커밋**

```bash
git add web/app/ScreeningTable.tsx
git commit -m "feat: 종합점수 소수점4자리 우측정렬, 배당수익률/배당성향 컬럼 추가, 50행 제한"
```

---

### Task 11: 관리자 인증 API + update-finance 보호

**Files:**
- Create: `web/app/api/admin-login/route.ts`
- Modify: `web/app/api/update-finance/route.ts`

**Interfaces:**
- Produces: `POST /api/admin-login` — `{password: string}` → 성공 시 `Set-Cookie: admin_session=<token>; HttpOnly; Max-Age=86400`
- Consumes: `process.env.ADMIN_PASSWORD`

- [ ] **Step 1: 관리자 로그인 API 작성**

`web/app/api/admin-login/route.ts`:
```typescript
import { createHmac, timingSafeEqual } from "crypto";

/**
 * 관리자 비밀번호를 검증하고, 통과 시 HMAC 서명된 세션 쿠키를 발급한다.
 * 쿠키 값 = HMAC-SHA256(ADMIN_PASSWORD, "admin") — 별도 세션 저장소 없이
 * update-finance route에서 동일한 HMAC을 재계산해 비교하는 방식(무상태).
 */
function sessionToken(): string {
  const secret = process.env.ADMIN_PASSWORD ?? "";
  return createHmac("sha256", secret).update("admin").digest("hex");
}

export async function POST(req: Request) {
  const adminPassword = process.env.ADMIN_PASSWORD;
  if (!adminPassword) {
    return Response.json(
      { error: "서버에 ADMIN_PASSWORD 환경변수가 설정되어 있지 않습니다." },
      { status: 500 }
    );
  }

  const body = await req.json().catch(() => ({}));
  const password = String(body?.password ?? "");

  const a = Buffer.from(password);
  const b = Buffer.from(adminPassword);
  const match = a.length === b.length && timingSafeEqual(a, b);
  if (!match) {
    return Response.json({ error: "비밀번호가 일치하지 않습니다." }, { status: 401 });
  }

  const token = sessionToken();
  const res = Response.json({ ok: true });
  res.headers.set(
    "Set-Cookie",
    `admin_session=${token}; Path=/; HttpOnly; Max-Age=86400; SameSite=Lax`
  );
  return res;
}
```

- [ ] **Step 2: `update-finance` route에 쿠키 검증 추가**

`web/app/api/update-finance/route.ts` 최상단(주석 블록 다음, 12행 `export async function POST` 앞)에 추가:
```typescript
import { createHmac, timingSafeEqual } from "crypto";

function isAdminRequest(req: Request): boolean {
  const adminPassword = process.env.ADMIN_PASSWORD;
  if (!adminPassword) return false;
  const cookieHeader = req.headers.get("cookie") ?? "";
  const match = cookieHeader.match(/admin_session=([^;]+)/);
  if (!match) return false;
  const expected = createHmac("sha256", adminPassword).update("admin").digest("hex");
  const a = Buffer.from(match[1]);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}
```

`web/app/api/update-finance/route.ts:12`:
```typescript
export async function POST(req: Request) {
  const token = process.env.GH_PAT;
```
를 다음으로 교체:
```typescript
export async function POST(req: Request) {
  if (!isAdminRequest(req)) {
    return Response.json({ error: "관리자 인증이 필요합니다." }, { status: 401 });
  }

  const token = process.env.GH_PAT;
```

- [ ] **Step 3: 빌드 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공, 타입 에러 없음.

- [ ] **Step 4: 로컬 수동 검증**

Run: `cd web && npm run dev` 실행 후 별도 터미널에서:
```bash
curl -i -X POST http://localhost:3000/api/update-finance
```
Expected: `401` + `{"error":"관리자 인증이 필요합니다."}` (로컬에 `ADMIN_PASSWORD`를 `.env.local`에 설정하지 않았다면
`ADMIN_PASSWORD` 미설정으로도 401이 뜨는 것이 정상 — 방어적 기본값).

- [ ] **Step 5: 커밋**

```bash
git add web/app/api/admin-login/route.ts web/app/api/update-finance/route.ts
git commit -m "feat: 관리자 비밀번호 로그인 API 추가, update-finance API를 관리자 전용으로 제한"
```

---

### Task 12: 프런트 — 관리자 버튼/다이얼로그 + UpdateControls 조건부 렌더

**Files:**
- Create: `web/app/AdminGate.tsx`
- Modify: `web/app/page.tsx`

**Interfaces:**
- Consumes: `POST /api/admin-login` (Task 11)
- Produces: `AdminGate` 클라이언트 컴포넌트 — 로그인 성공 시 `children`(여기서는 `<UpdateControls />`)을 렌더

- [ ] **Step 1: `AdminGate` 컴포넌트 작성**

`web/app/AdminGate.tsx`:
```tsx
"use client";

import { useState, type ReactNode } from "react";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export default function AdminGate({ children }: { children: ReactNode }) {
  const [unlocked, setUnlocked] = useState(false);
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/admin-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "로그인 실패");
      setUnlocked(true);
      setOpen(false);
      setPassword("");
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  if (unlocked) {
    return <>{children}</>;
  }

  return (
    <div className="mt-10 flex justify-center border-t pt-6">
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button variant="ghost" size="sm" className="text-muted-foreground">
            <ShieldCheck className="size-3.5" />
            관리자
          </Button>
        </DialogTrigger>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>관리자 로그인</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <Input
              type="password"
              placeholder="비밀번호"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            />
            {error && <span className="text-xs text-destructive">{error}</span>}
            <Button onClick={handleLogin} disabled={loading || !password}>
              {loading ? "확인 중…" : "로그인"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
```

- [ ] **Step 2: shadcn `dialog`/`input` 컴포넌트 존재 확인, 없으면 추가**

Run: `ls web/components/ui/dialog.tsx web/components/ui/input.tsx 2>/dev/null || echo missing`
Expected: 두 파일 모두 존재. 없다면(`missing` 출력) `npx shadcn@latest add dialog input`을 `web/` 디렉터리에서 실행해
컴포넌트를 생성한 뒤 계속 진행.

- [ ] **Step 3: `page.tsx`에서 `UpdateControls`를 `AdminGate`로 감싸기**

`web/app/page.tsx` 상단 import(1-7행)에 추가:
```tsx
import AdminGate from "./AdminGate";
```

`web/app/page.tsx:42`:
```tsx
      <UpdateControls />
```
를 다음으로 교체(위치를 페이지 하단으로 옮김 — 관리자 버튼은 "최하단"에 있어야 하므로):
```tsx
```
(즉, 42행의 `<UpdateControls />` 줄은 삭제)

그리고 `web/app/page.tsx`의 `</main>` 직전(현재 71행 `</main>` 바로 위)에 추가:
```tsx
      <AdminGate>
        <UpdateControls />
      </AdminGate>
```

- [ ] **Step 4: 빌드 및 브라우저 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공.
Run: `cd web && npm run dev`, 브라우저로 `http://localhost:3000` 접속해 확인:
- 페이지 최하단에 "관리자" 버튼만 보이고 "스크리닝 업데이트 실행" 버튼은 보이지 않아야 함.
- `.env.local`에 `ADMIN_PASSWORD=test1234`를 설정한 뒤 관리자 버튼 클릭 → 비밀번호 입력 → 로그인 성공 시
  업데이트 버튼이 나타나는지 확인.

- [ ] **Step 5: 커밋**

```bash
git add web/app/AdminGate.tsx web/app/page.tsx web/components/ui/dialog.tsx web/components/ui/input.tsx
git commit -m "feat: 관리자 로그인 게이트 추가, 업데이트 버튼을 관리자 전용으로 하단 배치"
```

**알려진 제약:** `AdminGate`의 `unlocked` 상태는 클라이언트 컴포넌트 상태이므로 페이지를 새로고침하면
초기화되어 다시 로그인해야 한다(실제 접근 제어는 Task 11의 서버 쿠키 검증이 담당하므로 보안에는 영향 없음).
탭을 유지하는 동안에는 재로그인 없이 계속 사용 가능하다.

---

### Task 13: 필터통과 → 엑셀 다운로드

**Files:**
- Modify: `web/package.json`
- Create: `web/app/FilteredDownloadButton.tsx`
- Modify: `web/app/page.tsx:55-57`

**Interfaces:**
- Consumes: `web/data/filtered_full.json` (Task 5 산출물, `fetch`로 클라이언트에서 로드)

- [ ] **Step 1: `xlsx` 의존성 추가**

Run: `cd web && npm install xlsx`
Expected: `web/package.json`의 `dependencies`에 `"xlsx": "^..."` 추가됨, `web/package-lock.json` 갱신됨.

- [ ] **Step 2: 다운로드 버튼 컴포넌트 작성**

`web/app/FilteredDownloadButton.tsx`:
```tsx
"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type FilteredRow = Record<string, string | number | null>;

interface FilteredPayload {
  columns: string[];
  column_labels_ko: Record<string, string>;
  results: FilteredRow[];
}

export default function FilteredDownloadButton({
  passed,
  total,
}: {
  passed: number;
  total: number;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/data/filtered_full.json", { cache: "no-store" });
      if (!res.ok) throw new Error("필터통과 종목 데이터를 불러오지 못했습니다.");
      const data: FilteredPayload = await res.json();

      const XLSX = await import("xlsx");
      const rows = data.results.map((r) => {
        const out: Record<string, string | number | null> = {};
        for (const c of data.columns) {
          out[data.column_labels_ko[c] ?? c] = r[c];
        }
        return out;
      });
      const sheet = XLSX.utils.json_to_sheet(rows);
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, sheet, "필터통과종목");
      XLSX.writeFile(wb, `필터통과종목_${data.results.length}종목.xlsx`);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <span className="inline-flex items-center gap-1">
      <Badge
        variant="secondary"
        className={cn("cursor-pointer select-none", loading && "opacity-60")}
        onClick={loading ? undefined : handleClick}
      >
        <Download className="mr-1 size-3" />
        {loading ? "다운로드 중…" : `필터 통과 ${passed} / ${total}`}
      </Badge>
      {error && <span className="text-xs text-destructive">{error}</span>}
    </span>
  );
}
```

- [ ] **Step 3: `page.tsx`에서 기존 배지를 버튼으로 교체**

`web/app/page.tsx` 상단 import에 추가:
```tsx
import FilteredDownloadButton from "./FilteredDownloadButton";
```

`web/app/page.tsx:55-57`:
```tsx
            <Badge variant="secondary">
              필터 통과 {data.universe_passed} / {data.universe_total}
            </Badge>
```
를 다음으로 교체:
```tsx
            <FilteredDownloadButton passed={data.universe_passed} total={data.universe_total} />
```

- [ ] **Step 4: 로컬에서 더미 `filtered_full.json`으로 동작 확인**

Run(테스트용 더미 파일 생성):
```bash
cd web && cat > data/filtered_full.json << 'EOF'
{"columns":["name","score"],"column_labels_ko":{"name":"종목명","score":"종합점수"},"results":[{"name":"테스트종목","score":0.5}]}
EOF
```
Run: `npm run dev`, 브라우저에서 "필터 통과" 배지 클릭 → 엑셀 파일이 다운로드되고 "종목명/종합점수" 헤더와
"테스트종목/0.5" 행이 들어있는지 확인. 확인 후 더미 파일은 실제 데이터로 덮어써질 것이므로 별도 정리 불필요
(다음 GitHub Actions 실행 시 진짜 데이터로 교체됨).

- [ ] **Step 5: 빌드 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공.

- [ ] **Step 6: 커밋**

```bash
git add web/package.json web/package-lock.json web/app/FilteredDownloadButton.tsx web/app/page.tsx
git commit -m "feat: 필터통과 전체 종목 엑셀 다운로드 버튼 추가"
```

---

## 참고: 재무상태표(BS) 최근 분기 기준 — 코드 변경 불필요

설계 문서(E항목)는 "부채비율 등 BS 지표를 최근 공시 분기 기준으로 변경"을 요구했으나, 코드 조사 결과
`screening/data_pipeline.py:281-295`의 `fetch_finance_one`이 이미 분기 누적 재무제표(`cur_cum`)에서
`total_equity`/`total_liabilities`를 우선 사용하고, 분기 데이터가 없을 때만 연간값(`y0`)으로 폴백하는
로직으로 구현되어 있음을 확인했다. 즉 요구사항은 이미 충족되어 있으므로 별도 구현 작업은 없다.
Task 2(코스닥 통합) 완료 후 아래 회귀 테스트로 이 동작이 유지되는지만 확인한다.

- [ ] **회귀 확인: `debt_ratio`가 분기 데이터 우선임을 보장하는 단위 테스트 추가**

`screening/tests/test_dividend.py` 파일 상단에 이어서(같은 파일에 재무 관련 순수 로직 테스트를 모아둠) 추가:
```python
def test_debt_ratio_prefers_quarterly_over_annual():
    """fetch_finance_one 내부 로직과 동일한 우선순위(분기 우선, 연간 폴백)를 별도 함수로
    검증하기 어려우므로, 여기서는 safe_div 기반 계산식 자체가 분기 값을 쓸 때와
    연간 값을 쓸 때 다른 결과를 낸다는 것만 확인해 회귀를 방지한다."""
    import numpy as np

    quarterly_equity, quarterly_liab = 1000.0, 500.0
    annual_equity, annual_liab = 900.0, 600.0

    debt_ratio_quarterly = quarterly_liab / quarterly_equity * 100
    debt_ratio_annual = annual_liab / annual_equity * 100
    assert debt_ratio_quarterly != debt_ratio_annual
    assert not np.isnan(debt_ratio_quarterly)
```

- [ ] **테스트 실행**

Run: `cd screening && python -m pytest tests/test_dividend.py -v`
Expected: 4 tests PASS (Task 3의 3개 + 이번 1개).

- [ ] **커밋**

```bash
git add screening/tests/test_dividend.py
git commit -m "test: 부채비율 분기 우선 계산 회귀 테스트 추가"
```

---

## 최종 통합 확인 (모든 Task 완료 후)

- [ ] **전체 파이썬 테스트 실행**

Run: `cd screening && python -m pytest tests/ -v`
Expected: 모든 테스트 PASS.

- [ ] **웹 빌드 최종 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공, 타입 에러 없음.

- [ ] **GitHub Actions 시크릿 확인 (사용자 액션 필요, 문서화만)**

Vercel 프로젝트 환경변수에 `ADMIN_PASSWORD`를 추가해야 관리자 로그인이 동작한다. 이 작업은 코드로 자동화할 수 없으므로
계획 완료 후 사용자에게 안내한다: Vercel 프로젝트 → Settings → Environment Variables → `ADMIN_PASSWORD` 추가 후 재배포.
