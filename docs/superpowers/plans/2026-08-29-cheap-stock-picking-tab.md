# Cheap Stock Picking 탭 추가 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 "가치투자" 스크리닝 탭 옆에 3가지 규칙 기반의 "Cheap Stock Picking" 탭을 추가한다.

**Architecture:** Python 쪽에 새 재무 필드(현금성자산, 총부채, 5년 전 영업이익)와 52주 최저가
rolling 캐시를 데이터 파이프라인에 추가하고, 이를 소비하는 독립 스크리닝 모듈
(`screening/cheap_screen.py`)을 만들어 `web/data/results_cheap.json`을 생성한다. 프런트엔드는
기존 `page.tsx`의 결과 표시 블록을 `ScreeningSection` 컴포넌트로 추출해 재사용하고, 새로 만든
`Tabs` 컴포넌트로 두 스크리닝을 탭 전환한다.

**Tech Stack:** Python(pandas/numpy/OpenDartReader), Next.js 15(App Router, force-static),
TypeScript, radix-ui(Tabs 프리미티브), vitest, pytest.

## Global Constraints

- 통과 조건 3가지(AND, 모두 만족해야 함): (1) 종가가 52주 최저가의 10% 이내
  (`close <= low_52w * 1.10`), (2) 영업이익(TTM)이 5년 전 영업이익보다 큼
  (`op_ttm > op_income_5y_ago`), (3) EBIT(=op_ttm) > 0 이고 `EV/EBIT < 10`.
- EV = 시가총액 + 총부채 − 현금성자산 (근사치, 이자부채만 따로 파싱하지 않음).
- 시가총액/거래대금 유동성 하한선은 이 탭에 적용하지 않는다.
- 정렬은 EV/EBIT **오름차순**.
- 52주 최저가는 매일 실행 시 그날 일중 저가(KRX `TDD_LWPRC`)를 `screening/data/price_history.parquet`
  (git 추적)에 누적하는 rolling 캐시로 구한다. 윈도우는 370일.
- 결측치가 있는 조건은 통과 실패로 처리한다(관대하게 통과시키지 않는다).
- 기존 "가치투자" 탭의 동작/데이터/URL은 전혀 변경하지 않는다 — 순수 추가(additive)만 한다.
- 새 컴포넌트는 기존 코드베이스 관례를 따른다: `AlgorithmInfo.tsx`류는 `"use client"`나
  Radix `Collapsible`을 쓰지 않고 네이티브 `<details>`를 쓴다(`web/tests/import-boundaries.test.ts`가
  이를 강제한다). Radix 프리미티브를 쓰는 컴포넌트는 `radix-ui/<submodule>` 형태로 import한다
  (예: `radix-ui/tabs`, `radix-ui/dialog`) — 루트 배럴(`from "radix-ui"`)은 금지.
- 테스트는 이 저장소의 기존 관례를 따른다: Python은 순수 함수 위주 pytest, 웹은 JSX 렌더링
  하네스(RTL/jsdom) 없이 소스 텍스트 검증(`import-boundaries.test.ts` 패턴) 또는 라우트 핸들러
  직접 호출(`prices-route.test.ts` 패턴)로 테스트한다 — 새 테스트 도구/의존성을 추가하지 않는다.

---

### Task 1: `data_pipeline.py` — 현금성자산·총부채 노출 + 5년 전 영업이익 조회

**Files:**
- Modify: `screening/data_pipeline.py:82-92` (ACCOUNT_MAP), `screening/data_pipeline.py:327` 근처
  (새 함수 추가), `screening/data_pipeline.py:434-453` (fetch_finance_one 반환값)
- Test: Create `screening/tests/test_data_pipeline.py`

**Interfaces:**
- Produces: `fetch_op_income_5y_ago(dart, corp_code: str, year: int) -> float`
- Produces: `fetch_finance_one(...)` 반환 dict에 3개 키 추가: `total_liabilities: float`,
  `cash_equivalents: float`, `op_income_5y_ago: float` (이후 Task 4의 `cheap_screen.py`가 소비)

- [ ] **Step 1: 실패하는 테스트 작성**

`screening/tests/test_data_pipeline.py` 생성:

```python
import pandas as pd

from data_pipeline import fetch_finance_one


class FakeDart:
    """dart 클라이언트를 흉내내는 테스트 더블. fetch_finance_one은 dart를
    이미 인자로 주입받는 구조라 실제 네트워크 호출 없이 검증 가능하다."""

    def finstate(self, corp_code, year, reprt_code):
        if year == 2025 and reprt_code == "11011":  # annual_year FY
            return pd.DataFrame([
                {"account_nm": "매출액", "thstrm_amount": "100000",
                 "frmtrm_amount": "90000", "bfefrmtrm_amount": "80000"},
                {"account_nm": "영업이익", "thstrm_amount": "10000",
                 "frmtrm_amount": "9000", "bfefrmtrm_amount": "8000"},
                {"account_nm": "당기순이익", "thstrm_amount": "8000",
                 "frmtrm_amount": "7000", "bfefrmtrm_amount": "6000"},
                {"account_nm": "자본총계", "thstrm_amount": "50000",
                 "frmtrm_amount": "48000", "bfefrmtrm_amount": "46000"},
                {"account_nm": "부채총계", "thstrm_amount": "20000",
                 "frmtrm_amount": "19000", "bfefrmtrm_amount": "18000"},
                {"account_nm": "현금및현금성자산", "thstrm_amount": "5000",
                 "frmtrm_amount": "4500", "bfefrmtrm_amount": "4000"},
            ])
        if year == 2026 and reprt_code == "11012":  # ttm_year H1
            return pd.DataFrame([
                {"account_nm": "매출액", "thstrm_amount": "55000", "frmtrm_amount": "44000"},
                {"account_nm": "영업이익", "thstrm_amount": "6000", "frmtrm_amount": "4000"},
                {"account_nm": "당기순이익", "thstrm_amount": "5000", "frmtrm_amount": "3500"},
                {"account_nm": "자본총계", "thstrm_amount": "52000", "frmtrm_amount": "47000"},
                {"account_nm": "부채총계", "thstrm_amount": "21000", "frmtrm_amount": "18500"},
            ])
        if year == 2020 and reprt_code == "11011":  # annual_year - 5 FY
            return pd.DataFrame([
                {"account_nm": "영업이익", "thstrm_amount": "3000",
                 "frmtrm_amount": "2500", "bfefrmtrm_amount": "2000"},
            ])
        return pd.DataFrame()

    def report(self, corp_code, keyword, year, reprt_code):
        return pd.DataFrame()


def test_fetch_finance_one_exposes_total_liabilities_cash_and_5y_ago_op_income():
    result = fetch_finance_one(
        FakeDart(), "005930", "00126380", annual_year=2025, ttm_year=2026, ttm_quarter="H1",
    )

    assert result["total_liabilities"] == 21000.0
    assert result["cash_equivalents"] == 5000.0
    assert result["op_income_5y_ago"] == 3000.0
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd screening && python -m pytest tests/test_data_pipeline.py -v`
Expected: FAIL — `KeyError: 'total_liabilities'` (또는 `cash_equivalents`/`op_income_5y_ago`) —
아직 dict에 해당 키가 없으므로.

- [ ] **Step 3: ACCOUNT_MAP에 현금성자산 계정 추가**

`screening/data_pipeline.py:82-92`을 다음으로 교체:

```python
ACCOUNT_MAP = {
    "자산총계": "total_assets",
    "부채총계": "total_liabilities",
    "자본총계": "total_equity",
    "매출액": "revenue",
    "수익(매출액)": "revenue",
    "영업이익": "op_income",
    "영업이익(손실)": "op_income",
    "당기순이익": "net_income",
    "당기순이익(손실)": "net_income",
    "현금및현금성자산": "cash_equivalents",
}
```

- [ ] **Step 4: 5년 전 영업이익 조회 함수 추가**

`screening/data_pipeline.py`에서 `def fetch_finance_one(` 정의 바로 위(현재 327번째 줄 근처,
`_prefer_quarterly` 함수와 `fetch_finance_one` 사이)에 다음 함수를 추가:

```python
def fetch_op_income_5y_ago(dart, corp_code: str, year: int) -> float:
    """5년 전 사업연도(annual_year - 5) 사업보고서(FY)에서 영업이익만 추출한다.
    Cheap Stock Picking 스크리닝의 '5년 전보다 이익이 늘었는가' 조건에 쓰인다."""
    try:
        fs = dart.finstate(corp_code, year, reprt_code=QUARTER_CODES["FY"])
    except Exception:
        return np.nan
    if not isinstance(fs, pd.DataFrame) or len(fs) == 0:
        return np.nan
    y0, _, _ = _extract_financials_3col(fs)
    return y0["op_income"]
```

- [ ] **Step 5: fetch_finance_one 반환값에 3개 필드 추가**

`screening/data_pipeline.py:434-453`의 반환 dict를 다음으로 교체:

```python
    return {
        "stock_code": stock_code,
        "corp_code": corp_code,
        "bsns_year": annual_year,
        "ttm_basis": ttm_basis,
        "roe_3y_avg": np.mean(roe_series) if roe_series else np.nan,
        "roe_3y_std": np.std(roe_series) if len(roe_series) > 1 else np.nan,
        "debt_ratio": debt_ratio,
        "op_margin": op_margin,
        "op_ttm": op_income_ttm,
        "op_yoy": op_yoy,
        "rev_yoy": rev_yoy,
        "rev_cagr_3y": rev_cagr_3y,
        "years_no_rev_decline": years_no_decline,
        "net_income_ttm": net_income_ttm,
        "revenue_ttm": revenue_ttm,
        "total_equity": total_equity_latest,
        "total_liabilities": total_liab_latest,
        "cash_equivalents": y0["cash_equivalents"],
        "op_income_5y_ago": fetch_op_income_5y_ago(dart, corp_code, annual_year - 5),
        "cash_dividend_total": div["cash_dividend_total"],
        "payout_ratio": payout_ratio,
    }
```

- [ ] **Step 6: 테스트 실행해서 통과 확인**

Run: `cd screening && python -m pytest tests/test_data_pipeline.py -v`
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add screening/data_pipeline.py screening/tests/test_data_pipeline.py
git commit -m "feat: 재무 캐시에 현금성자산·총부채·5년전 영업이익 추가"
```

---

### Task 2: `data_pipeline.py` — 52주 최저가 rolling 캐시

**Files:**
- Modify: `screening/data_pipeline.py` (CACHE_DIR 정의부 근처에 상수 추가, `get_full_universe`
  함수 뒤에 새 함수 2개 추가)
- Test: Modify `screening/tests/test_data_pipeline.py` (Task 1에서 만든 파일에 이어서 작성)

**Interfaces:**
- Consumes: 없음 (독립적인 순수/파일I/O 함수)
- Produces: `update_price_history(universe: pd.DataFrame, date: str, path: Path = PRICE_HISTORY_FILE) -> pd.DataFrame`
- Produces: `get_52w_low(price_history: pd.DataFrame) -> pd.Series` (index=stock_code)
- Produces: 모듈 상수 `PRICE_HISTORY_FILE: Path`, `PRICE_HISTORY_WINDOW_DAYS: int = 370`
  (Task 4의 `cheap_screen.py`가 소비)

- [ ] **Step 1: 실패하는 테스트 작성**

`screening/tests/test_data_pipeline.py` 맨 아래에 추가:

```python
from pathlib import Path

from data_pipeline import update_price_history, get_52w_low, PRICE_HISTORY_WINDOW_DAYS


def _universe(prices: dict) -> pd.DataFrame:
    df = pd.DataFrame({"TDD_LWPRC": list(prices.values())}, index=list(prices.keys()))
    df.index.name = "stock_code"
    return df


def test_update_price_history_appends_across_days(tmp_path):
    path = tmp_path / "price_history.parquet"
    day1 = _universe({"005930": 70000, "000660": 120000})
    day2 = _universe({"005930": 69000, "000660": 121000})

    update_price_history(day1, "20260101", path=path)
    combined = update_price_history(day2, "20260102", path=path)

    assert len(combined) == 4
    assert set(combined["date"]) == {"20260101", "20260102"}


def test_update_price_history_dedupes_same_day_rerun(tmp_path):
    path = tmp_path / "price_history.parquet"
    update_price_history(_universe({"005930": 70000}), "20260101", path=path)
    combined = update_price_history(_universe({"005930": 68000}), "20260101", path=path)

    assert len(combined) == 1
    assert combined.iloc[0]["low"] == 68000


def test_update_price_history_drops_rows_older_than_window(tmp_path):
    path = tmp_path / "price_history.parquet"
    old_date = (pd.Timestamp("20260101") - pd.Timedelta(days=PRICE_HISTORY_WINDOW_DAYS + 1)).strftime("%Y%m%d")
    pd.DataFrame({"date": [old_date], "stock_code": ["005930"], "low": [50000]}).to_parquet(path, index=False)

    combined = update_price_history(_universe({"005930": 70000}), "20260101", path=path)

    assert old_date not in set(combined["date"])
    assert len(combined) == 1


def test_get_52w_low_returns_min_per_stock():
    history = pd.DataFrame({
        "date": ["20260101", "20260102", "20260101"],
        "stock_code": ["005930", "005930", "000660"],
        "low": [70000, 68000, 120000],
    })

    result = get_52w_low(history)

    assert result["005930"] == 68000
    assert result["000660"] == 120000
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd screening && python -m pytest tests/test_data_pipeline.py -v`
Expected: FAIL — `ImportError: cannot import name 'update_price_history'`

- [ ] **Step 3: 상수 추가**

`screening/data_pipeline.py:39` (`ANNUAL_YEAR_FILE = CACHE_DIR / "annual_year.txt"` 다음 줄)
바로 뒤에 추가:

```python
PRICE_HISTORY_FILE = Path("data") / "price_history.parquet"  # git 추적 대상 (.cache와 달리 커밋됨)
PRICE_HISTORY_WINDOW_DAYS = 370
```

- [ ] **Step 4: 함수 구현**

`get_full_universe` 함수 정의가 끝나는 지점(현재 234번째 줄, `raise RuntimeError(...)` 다음의
빈 줄) 바로 뒤, `# 2. 종목별 재무데이터 추출` 섹션 헤더 앞에 추가:

```python
def update_price_history(universe: pd.DataFrame, date: str,
                          path: Path = PRICE_HISTORY_FILE) -> pd.DataFrame:
    """universe(get_full_universe 반환값, index=stock_code, "TDD_LWPRC" 컬럼 포함)의
    당일 일중 저가를 누적 캐시(path)에 append하고, PRICE_HISTORY_WINDOW_DAYS보다 오래된
    행은 버린 뒤 저장한다. 갱신된 전체 히스토리를 반환한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    today_rows = pd.DataFrame({
        "date": date,
        "stock_code": universe.index,
        "low": universe["TDD_LWPRC"].values,
    })
    if path.exists():
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, today_rows], ignore_index=True)
    else:
        combined = today_rows
    combined = combined.drop_duplicates(subset=["date", "stock_code"], keep="last")
    cutoff = (pd.Timestamp(date) - pd.Timedelta(days=PRICE_HISTORY_WINDOW_DAYS)).strftime("%Y%m%d")
    combined = combined[combined["date"] >= cutoff].reset_index(drop=True)
    combined.to_parquet(path, index=False)
    return combined


def get_52w_low(price_history: pd.DataFrame) -> pd.Series:
    """stock_code -> 캐시에 쌓인 기간 내 최저가(low의 최솟값). 캐시가 아직 52주치
    쌓이지 않은 초기에는 '수집된 기간 내 최저가'가 된다."""
    return price_history.groupby("stock_code")["low"].min()
```

- [ ] **Step 5: 테스트 실행해서 통과 확인**

Run: `cd screening && python -m pytest tests/test_data_pipeline.py -v`
Expected: PASS (5개 테스트 모두)

- [ ] **Step 6: 커밋**

```bash
git add screening/data_pipeline.py screening/tests/test_data_pipeline.py
git commit -m "feat: 52주 최저가 rolling 가격 히스토리 캐시 추가"
```

---

### Task 3: `cheap_screen.py` — 파생 지표 계산 및 3조건 필터 (순수 함수)

**Files:**
- Create: `screening/cheap_screen.py`
- Test: Create `screening/tests/test_cheap_screen.py`

**Interfaces:**
- Consumes: 없음 (입력 DataFrame은 테스트에서 직접 구성)
- Produces: `add_cheap_metrics(df: pd.DataFrame) -> pd.DataFrame` — 컬럼
  `close, low_52w, mktcap, total_liabilities, cash_equivalents, op_ttm`을 받아
  `dist_from_52w_low_pct, ev, ebit, ev_ebit` 컬럼을 추가해 반환
- Produces: `apply_cheap_filters(df, max_dist_from_low_pct=10.0, max_ev_ebit=10.0) -> pd.DataFrame`
  — `dist_from_52w_low_pct, op_ttm, op_income_5y_ago, ebit, ev_ebit` 컬럼을 받아 `passed`
  bool 컬럼을 추가해 반환 (Task 4의 `load_cheap`/`run_cheap`이 소비)

- [ ] **Step 1: 실패하는 테스트 작성**

`screening/tests/test_cheap_screen.py` 생성:

```python
import numpy as np
import pandas as pd
import pytest

from cheap_screen import add_cheap_metrics, apply_cheap_filters


def _row(**overrides):
    base = dict(close=100, low_52w=95, mktcap=1000, total_liabilities=200,
                cash_equivalents=50, op_ttm=150, op_income_5y_ago=100)
    base.update(overrides)
    return base


def test_add_cheap_metrics_computes_dist_ev_and_ev_ebit():
    df = pd.DataFrame([_row()])

    out = add_cheap_metrics(df)

    assert out.loc[0, "dist_from_52w_low_pct"] == pytest.approx((100 / 95 - 1) * 100)
    assert out.loc[0, "ev"] == 1000 + 200 - 50
    assert out.loc[0, "ev_ebit"] == pytest.approx((1000 + 200 - 50) / 150)


def test_add_cheap_metrics_ev_ebit_is_nan_when_ebit_not_positive():
    df = pd.DataFrame([_row(op_ttm=0), _row(op_ttm=-10)])

    out = add_cheap_metrics(df)

    assert out["ev_ebit"].isna().all()


def test_apply_cheap_filters_passes_when_all_three_conditions_met():
    df = add_cheap_metrics(pd.DataFrame([_row()]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is True


def test_apply_cheap_filters_rejects_far_from_52w_low():
    df = add_cheap_metrics(pd.DataFrame([_row(close=130)]))  # 52주 저가 대비 +36.8%

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_rejects_earnings_not_growing():
    df = add_cheap_metrics(pd.DataFrame([_row(mktcap=500, op_ttm=90, op_income_5y_ago=100)]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_rejects_high_ev_ebit():
    df = add_cheap_metrics(pd.DataFrame([_row(mktcap=5000)]))  # ev_ebit ≈ 34.3

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_rejects_missing_52w_low():
    df = add_cheap_metrics(pd.DataFrame([_row(low_52w=np.nan)]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd screening && python -m pytest tests/test_cheap_screen.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cheap_screen'`

- [ ] **Step 3: 최소 구현 작성**

`screening/cheap_screen.py` 생성 (이 파일은 Task 4에서 I/O 함수가 추가되며 완성됨. 지금은
순수 함수 두 개만 작성):

```python
"""
cheap_screen.py — "Cheap Stock Picking" 스크리닝
================================================================
가치투자 스크리닝(ws_alpha.py)과 별개로, 3가지 조건만으로 종목을 거른다:
  1) 현재가가 52주 최저가의 10% 이내
  2) 영업이익(TTM)이 5년 전 영업이익보다 큼
  3) EBIT(영업이익 TTM 근사) > 0 이고 EV/EBIT < 10배
     (EV = 시가총액 + 총부채 - 현금성자산, 근사치)

가치투자 탭과 달리 시총/거래대금 유동성 하한선은 적용하지 않는다. 정렬은 EV/EBIT 오름차순.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_cheap_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """52주 저가 대비 괴리율, EV, EBIT, EV/EBIT 파생 컬럼을 계산해 추가한다."""
    d = df.copy()
    d["dist_from_52w_low_pct"] = (d["close"] / d["low_52w"] - 1) * 100
    d["ev"] = d["mktcap"] + d["total_liabilities"] - d["cash_equivalents"]
    d["ebit"] = d["op_ttm"]
    d["ev_ebit"] = d["ev"] / d["ebit"].where(d["ebit"] > 0)
    return d


def apply_cheap_filters(df: pd.DataFrame, max_dist_from_low_pct: float = 10.0,
                         max_ev_ebit: float = 10.0) -> pd.DataFrame:
    """3가지 통과 조건을 순수하게 적용한다 (유동성 하한선 없음). 결측치가 있는
    조건은 통과 실패로 처리한다."""
    d = df.copy()
    near_low = d["dist_from_52w_low_pct"] <= max_dist_from_low_pct
    earning_more = d["op_ttm"] > d["op_income_5y_ago"]
    cheap_ev = (d["ebit"] > 0) & (d["ev_ebit"] < max_ev_ebit)
    d["passed"] = near_low.fillna(False) & earning_more.fillna(False) & cheap_ev.fillna(False)
    return d
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd screening && python -m pytest tests/test_cheap_screen.py -v`
Expected: PASS (7개 테스트 모두)

- [ ] **Step 5: 커밋**

```bash
git add screening/cheap_screen.py screening/tests/test_cheap_screen.py
git commit -m "feat: Cheap Stock Picking 파생지표·필터 순수 함수 추가"
```

---

### Task 4: `cheap_screen.py` — 데이터 조립 및 CLI 실행기

**Files:**
- Modify: `screening/cheap_screen.py` (Task 3 파일에 이어서 작성)

**Interfaces:**
- Consumes: `data_pipeline.FINANCE_CACHE`, `data_pipeline.PRICE_HISTORY_FILE`,
  `data_pipeline.get_full_universe(date) -> tuple[pd.DataFrame, str]`,
  `data_pipeline.update_price_history(df, date) -> pd.DataFrame`,
  `data_pipeline.get_52w_low(history) -> pd.Series` (Task 1, 2),
  `add_cheap_metrics`, `apply_cheap_filters` (Task 3),
  `quotes.pick_quote_for_week() -> dict`, `stock_profile.generate_all_profiles(records) -> dict`
- Produces: `load_cheap(date: str, bsns_year: int) -> tuple[pd.DataFrame, str]`,
  `run_cheap(date, bsns_year, top_n, export_json=None, filtered_json=None) -> pd.DataFrame`
  (CLI에서 사용, Task 5의 GitHub Actions 워크플로우가 `--run` CLI로 호출)

이 태스크는 실제 DART/KRX API가 필요한 I/O 글루 코드라 이 저장소의 관례상(`ws_alpha.py`의
`load_real`/`run_real`도 동일하게 미테스트) 단위 테스트를 추가하지 않는다. Task 3의 순수 함수
테스트가 핵심 로직을 이미 검증한다.

- [ ] **Step 1: `screening/cheap_screen.py` 맨 위에 import 추가**

파일 상단의 `from __future__ import annotations` 바로 아래에 추가:

```python
import argparse

from quotes import pick_quote_for_week
from stock_profile import generate_all_profiles
```

- [ ] **Step 2: 컬럼 정의 추가**

`import` 구문들 바로 아래, `add_cheap_metrics` 정의 위에 추가:

```python
COLS = ["name", "sector_raw", "mktcap_eok", "close", "low_52w",
        "dist_from_52w_low_pct", "op_ttm_eok", "op_income_5y_ago_eok", "ev_ebit"]

KOR_NAMES = {
    "name": "종목명", "sector_raw": "시장", "mktcap_eok": "시가총액(억)",
    "close": "종가", "low_52w": "52주최저가", "dist_from_52w_low_pct": "52주저가대비(%)",
    "op_ttm_eok": "영업이익(TTM,억원)", "op_income_5y_ago_eok": "영업이익(5년전,억원)",
    "ev_ebit": "EV/EBIT",
}
```

- [ ] **Step 3: `load_cheap`/`run_cheap`/CLI 추가**

파일 맨 끝에 추가:

```python
def load_cheap(date: str, bsns_year: int) -> tuple[pd.DataFrame, str]:
    """가격·52주최저가·재무 캐시에서 Cheap Stock Picking에 필요한 컬럼을 조립한다."""
    from data_pipeline import FINANCE_CACHE, get_full_universe, update_price_history, get_52w_low

    if not FINANCE_CACHE.exists():
        raise RuntimeError(
            "재무 캐시가 없습니다. 먼저 실행하세요: "
            "python data_pipeline.py --build --year 2025 --date 20260807"
        )

    df, resolved_date = get_full_universe(date)
    df["mktcap_eok"] = df["mktcap"] / 1e8

    history = update_price_history(df, resolved_date)
    low_52w = get_52w_low(history)
    df["low_52w"] = df.index.map(low_52w)

    fin = pd.read_parquet(FINANCE_CACHE)
    fin = fin[fin["bsns_year"] == bsns_year].set_index("stock_code")
    df = df.join(fin, how="inner")

    df = add_cheap_metrics(df)
    df["op_ttm_eok"] = df["op_ttm"] / 1e8
    df["op_income_5y_ago_eok"] = df["op_income_5y_ago"] / 1e8

    return df, resolved_date


def _to_json_records(rows: pd.DataFrame, cols: list[str]) -> list[dict]:
    records = []
    for code, row in rows.iterrows():
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
    return records


def run_cheap(date: str, bsns_year: int, top_n: int,
              export_json: str | None = None, filtered_json: str | None = None) -> pd.DataFrame:
    d, resolved_date = load_cheap(date, bsns_year)
    if resolved_date != date:
        print(f"[알림] 요청한 기준일 {date}은 휴장일로 보여, 최근 개장일 {resolved_date}로 대체합니다")
    date = resolved_date

    filt = apply_cheap_filters(d)
    ranked = filt.sort_values("ev_ebit", ascending=True)

    print("=" * 78)
    print(f"Cheap Stock Picking — 유니버스 {len(d)} → 통과 {int(filt['passed'].sum())} "
          f"(가격기준일 {date} / 재무기준연도 {bsns_year})")
    print("=" * 78)
    cols = [c for c in COLS if c in ranked.columns]
    top = ranked[ranked["passed"]].head(top_n)[cols]
    print(top.round(3).to_string())

    if export_json:
        import json
        from pathlib import Path as _Path

        records = _to_json_records(top, cols)

        def _build_payload(recs):
            return {
                "as_of_date": date,
                "financial_year": bsns_year,
                "generated_at": pd.Timestamp.now("UTC").isoformat(),
                "quote_text": pick_quote_for_week()["text"],
                "quote_author": pick_quote_for_week()["author"],
                "universe_total": int(len(d)),
                "universe_passed": int(filt["passed"].sum()),
                "columns": cols,
                "column_labels_ko": {c: KOR_NAMES.get(c, c) for c in cols},
                "results": recs,
            }

        out_path = _Path(export_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        for rec in records:
            rec["profile"] = None
        out_path.write_text(json.dumps(_build_payload(records), ensure_ascii=False, indent=2), encoding="utf-8")

        profile_map = generate_all_profiles(records)
        for rec in records:
            rec["profile"] = profile_map.get(rec["stock_code"])

        out_path.write_text(json.dumps(_build_payload(records), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[export] JSON 저장 완료 → {export_json} ({len(records)}종목)")

    if filtered_json:
        import json
        from pathlib import Path as _Path

        passed_all = ranked[ranked["passed"]][cols]
        records = _to_json_records(passed_all, cols)

        payload = {
            "as_of_date": date,
            "financial_year": bsns_year,
            "columns": cols,
            "column_labels_ko": {c: KOR_NAMES.get(c, c) for c in cols},
            "results": records,
        }
        out_path = _Path(filtered_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[export] 필터통과 전체 JSON 저장 완료 → {filtered_json} ({len(records)}종목)")

    return ranked


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--date", default="20260810")
    ap.add_argument("--year", type=int, default=2025, help="재무캐시 사업연도")
    ap.add_argument("--top", type=int, default=50, help="화면·JSON에 보여줄 상위 종목 수")
    ap.add_argument("--export-json", default="", help="웹사이트용 JSON 저장 경로")
    ap.add_argument("--filtered-json", default="", help="필터통과 전체 종목 JSON 저장 경로")
    a = ap.parse_args()
    if a.run:
        run_cheap(a.date, a.year, a.top,
                   a.export_json if a.export_json else None,
                   a.filtered_json if a.filtered_json else None)
    else:
        print("사용법: python cheap_screen.py --run --date YYYYMMDD --year YYYY "
              "--export-json ... --filtered-json ...")
```

- [ ] **Step 4: 기존 테스트가 여전히 통과하는지 확인 (회귀 없음 확인)**

Run: `cd screening && python -m pytest tests/ -v`
Expected: PASS (전체 테스트, 새로 추가한 것 포함)

- [ ] **Step 5: 커밋**

```bash
git add screening/cheap_screen.py
git commit -m "feat: Cheap Stock Picking 데이터 조립·CLI 실행기 추가"
```

---

### Task 5: GitHub Actions 워크플로우에 Cheap Stock Picking 실행 스텝 추가

**Files:**
- Modify: `.github/workflows/daily-screen.yml`

**Interfaces:**
- Consumes: `screening/cheap_screen.py --run` (Task 4)
- Produces: `web/data/results_cheap.json`, `web/data/filtered_cheap_full.json`,
  `screening/data/price_history.parquet` (Task 11의 `page.tsx`가 소비)

- [ ] **Step 1: 스크리닝 실행 스텝 뒤에 Cheap Stock Picking 스텝 추가**

`.github/workflows/daily-screen.yml`에서 "오늘자 가격 기준 스크리닝 실행 + JSON 저장" 스텝
(현재 75-85번째 줄) 바로 뒤, "결과를 저장소에 커밋" 스텝 앞에 삽입:

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

- [ ] **Step 2: 커밋 스텝의 git add 대상에 새 파일 추가**

"결과를 저장소에 커밋" 스텝의 `git add` 줄(현재 91번째 줄)을 다음으로 교체:

```yaml
          git add web/data/results.json web/data/filtered_full.json \
                  web/data/results_cheap.json web/data/filtered_cheap_full.json \
                  screening/data/price_history.parquet
```

- [ ] **Step 3: YAML 문법 검증**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily-screen.yml', encoding='utf-8'))"`
Expected: 예외 없이 종료 (파싱 성공)

- [ ] **Step 4: 커밋**

```bash
git add .github/workflows/daily-screen.yml
git commit -m "ci: 일일 워크플로우에 Cheap Stock Picking 실행 스텝 추가"
```

---

### Task 6: `components/ui/tabs.tsx` — Tabs 프리미티브 래퍼

**Files:**
- Create: `web/components/ui/tabs.tsx`
- Test: Create `web/tests/tabs.test.ts`

**Interfaces:**
- Produces: `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent` (Task 11의 `page.tsx`가 소비)

- [ ] **Step 1: 실패하는 테스트 작성**

`web/tests/tabs.test.ts` 생성 (이 저장소의 `import-boundaries.test.ts`와 동일하게 소스 텍스트
검증 방식 — JSX 렌더링 하네스를 새로 추가하지 않는다):

```ts
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("components/ui/tabs.tsx", () => {
  it("radix-ui/tabs 서브모듈을 import하고 4개 컴포넌트를 export한다", () => {
    const source = fs.readFileSync(
      path.join(process.cwd(), "components/ui/tabs.tsx"),
      "utf8"
    );

    expect(source).toContain('from "radix-ui/tabs"');
    expect(source).not.toMatch(/from ["']radix-ui["']/);
    expect(source).toContain('"use client"');
    expect(source).toMatch(/export\s*\{\s*Tabs,\s*TabsList,\s*TabsTrigger,\s*TabsContent\s*\}/);
  });
});
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd web && npm test -- tabs.test.ts`
Expected: FAIL — `ENOENT: no such file or directory, open '.../components/ui/tabs.tsx'`

- [ ] **Step 3: 구현**

`web/components/ui/tabs.tsx` 생성:

```tsx
"use client"

import * as React from "react"
import * as TabsPrimitive from "radix-ui/tabs"

import { cn } from "@/lib/utils"

function Tabs({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  )
}

function TabsList({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(
        "inline-flex h-9 w-fit items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

function TabsTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "inline-flex flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-medium whitespace-nowrap transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-1 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm",
        className
      )}
      {...props}
    />
  )
}

function TabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn("flex-1 outline-none", className)}
      {...props}
    />
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent }
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd web && npm test -- tabs.test.ts`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/components/ui/tabs.tsx web/tests/tabs.test.ts
git commit -m "feat: Tabs UI 컴포넌트 추가"
```

---

### Task 7: `FilteredDownloadButton` — href를 prop으로 일반화

**Files:**
- Modify: `web/app/FilteredDownloadButton.tsx`
- Test: Create `web/tests/filtered-download-button.test.ts`

**Interfaces:**
- Produces: `FilteredDownloadButton({ href, passed, total })` (Task 10의 `ScreeningSection`이 소비)

- [ ] **Step 1: 실패하는 테스트 작성**

`web/tests/filtered-download-button.test.ts` 생성:

```ts
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("FilteredDownloadButton", () => {
  it("href를 prop으로 받고 /api/filtered를 하드코딩하지 않는다", () => {
    const source = fs.readFileSync(
      path.join(process.cwd(), "app/FilteredDownloadButton.tsx"),
      "utf8"
    );

    expect(source).toContain("href: string");
    expect(source).toContain("href={href}");
    expect(source).not.toContain('"/api/filtered"');
  });
});
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd web && npm test -- filtered-download-button.test.ts`
Expected: FAIL — 현재 소스는 `href="/api/filtered"`를 하드코딩하고 있어 마지막 assertion이 실패

- [ ] **Step 3: 구현**

`web/app/FilteredDownloadButton.tsx` 전체를 다음으로 교체:

```tsx
import { Download } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface Props {
  href: string;
  passed: number;
  total: number;
}

export default function FilteredDownloadButton({ href, passed, total }: Props) {
  return (
    <Badge asChild variant="secondary">
      <a href={href}>
        <Download className="mr-1 size-3" />
        필터 통과 {passed} / {total}
      </a>
    </Badge>
  );
}
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd web && npm test -- filtered-download-button.test.ts`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/app/FilteredDownloadButton.tsx web/tests/filtered-download-button.test.ts
git commit -m "refactor: FilteredDownloadButton href를 prop으로 일반화"
```

---

### Task 8: `CheapAlgorithmInfo.tsx` — Cheap Stock Picking 기준 설명

**Files:**
- Create: `web/app/CheapAlgorithmInfo.tsx`
- Modify: `web/tests/import-boundaries.test.ts:21-25`

**Interfaces:**
- Produces: `CheapAlgorithmInfo` 컴포넌트 (Task 11의 `page.tsx`가 소비)

- [ ] **Step 1: 기존 테스트를 확장해 실패하는 테스트로 만들기**

`web/tests/import-boundaries.test.ts:21-25`의 다음 블록:

```ts
  it("AlgorithmInfo는 client directive나 Radix Collapsible을 사용하지 않는다", () => {
    const source = fs.readFileSync(path.join(ROOT, "app/AlgorithmInfo.tsx"), "utf8");
    expect(source).not.toContain('"use client"');
    expect(source).not.toContain("Collapsible");
  });
```

를 다음으로 교체:

```ts
  it("AlgorithmInfo와 CheapAlgorithmInfo는 client directive나 Radix Collapsible을 사용하지 않는다", () => {
    for (const file of ["app/AlgorithmInfo.tsx", "app/CheapAlgorithmInfo.tsx"]) {
      const source = fs.readFileSync(path.join(ROOT, file), "utf8");
      expect(source, file).not.toContain('"use client"');
      expect(source, file).not.toContain("Collapsible");
    }
  });
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd web && npm test -- import-boundaries.test.ts`
Expected: FAIL — `ENOENT: no such file or directory, open '.../app/CheapAlgorithmInfo.tsx'`

- [ ] **Step 3: 구현**

`web/app/CheapAlgorithmInfo.tsx` 생성 (`AlgorithmInfo.tsx`와 동일한 `<details>` 카드 구조):

```tsx
import { ChevronDown, Info, ShieldAlert } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";

export default function CheapAlgorithmInfo() {
  return (
    <div className="mb-5 space-y-3">
      <details className="group">
        <summary className="inline-flex h-8 cursor-pointer list-none items-center justify-center gap-2 rounded-md border bg-background px-3 text-sm font-medium shadow-xs transition-all hover:bg-accent hover:text-accent-foreground [&::-webkit-details-marker]:hidden">
          <Info className="size-3.5" />
          이 스크리닝은 어떤 기준으로 종목을 골랐나요?
          <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
        </summary>
        <Card className="mt-3 py-5">
          <CardContent className="space-y-4 text-sm leading-relaxed text-foreground/90">
            <p className="text-muted-foreground">
              핵심 아이디어: <b className="text-foreground">싸게 사서 기다린다.</b> 아래 3가지
              조건을 모두 만족하는 종목만 통과시키며, 시가총액·거래대금 하한선은 두지 않습니다.
            </p>
            <section>
              <h4 className="mb-2 font-semibold text-foreground">통과 조건 (3가지 모두 충족)</h4>
              <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                <li>현재가가 52주 최저가의 10% 이내</li>
                <li>영업이익(TTM)이 5년 전 영업이익보다 큼 — 실적이 여전히 성장 중</li>
                <li>EV/EBIT 10배 미만 — EV(기업가치) = 시가총액 + 총부채 − 현금성자산(근사치)</li>
              </ul>
            </section>
            <section>
              <h4 className="mb-2 font-semibold text-foreground">정렬 기준</h4>
              <p className="text-muted-foreground">EV/EBIT이 낮은(가장 저평가된) 순으로 정렬합니다.</p>
            </section>
            <section>
              <h4 className="mb-2 font-semibold text-foreground">데이터 기준</h4>
              <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                <li>가격/52주 최저가: KRX 공식 API 일별 시세 누적 캐시 기준</li>
                <li>재무데이터: DART 공시자료, 최근 4분기(TTM) 누적 및 5년 전 사업보고서 기준</li>
                <li>대상: 코스피 전종목</li>
              </ul>
            </section>
          </CardContent>
        </Card>
      </details>

      <Alert className="border-muted-foreground/20 bg-transparent py-2.5">
        <ShieldAlert />
        <AlertDescription className="text-xs text-muted-foreground">
          이 페이지의 정보는 참고용 데이터이며 투자 조언이 아닙니다. 종목 선정 기준은 특정
          조건을 기계적으로 구현한 것으로, 정확성이나 완전성을 보장하지 않습니다. 투자 판단과
          그에 따른 손익에 대한 책임은 전적으로 투자자 본인에게 있습니다.
        </AlertDescription>
      </Alert>
    </div>
  );
}
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd web && npm test -- import-boundaries.test.ts`
Expected: PASS (전체 5개 테스트)

- [ ] **Step 5: 커밋**

```bash
git add web/app/CheapAlgorithmInfo.tsx web/tests/import-boundaries.test.ts
git commit -m "feat: CheapAlgorithmInfo 컴포넌트 추가"
```

---

### Task 9: `/api/filtered-cheap` 라우트

**Files:**
- Create: `web/app/api/filtered-cheap/route.ts`
- Test: Create `web/tests/filtered-cheap-route.test.ts`

**Interfaces:**
- Consumes: `createFilteredWorkbook(payload: FilteredPayload): ArrayBuffer` (기존
  `web/lib/filtered-workbook.ts`, 변경 없음)
- Produces: `GET(): Promise<Response>` — `web/data/filtered_cheap_full.json` 기반 xlsx 다운로드

- [ ] **Step 1: 실패하는 테스트 작성**

`web/tests/filtered-cheap-route.test.ts` 생성:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import fs from "fs";
import { GET } from "../app/api/filtered-cheap/route";

describe("GET /api/filtered-cheap", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("filtered_cheap_full.json이 없으면 404를 반환한다", async () => {
    vi.spyOn(fs, "existsSync").mockReturnValue(false);

    const response = await GET();

    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({
      error: "필터통과 데이터가 아직 생성되지 않았습니다.",
    });
  });

  it("filtered_cheap_full.json이 있으면 xlsx 파일을 반환한다", async () => {
    vi.spyOn(fs, "existsSync").mockReturnValue(true);
    vi.spyOn(fs, "readFileSync").mockReturnValue(
      JSON.stringify({
        columns: ["name"],
        column_labels_ko: { name: "종목명" },
        results: [{ name: "테스트종목" }],
      })
    );

    const response = await GET();

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe(
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    );
    expect(response.headers.get("Content-Disposition")).toContain("cheap-stocks.xlsx");
  });
});
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd web && npm test -- filtered-cheap-route.test.ts`
Expected: FAIL — `Cannot find module '../app/api/filtered-cheap/route'`

- [ ] **Step 3: 구현**

`web/app/api/filtered-cheap/route.ts` 생성 (기존 `web/app/api/filtered/route.ts`와 동일 구조,
대상 파일과 다운로드 파일명만 다름):

```ts
import fs from "fs";
import path from "path";
import { createFilteredWorkbook } from "@/lib/filtered-workbook";
import type { FilteredPayload } from "@/lib/types";

export const dynamic = "force-static"; // 빌드 시점 JSON을 그대로 굽는다

const XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const DOWNLOAD_NAME = encodeURIComponent("cheap-stocks.xlsx");

export async function GET() {
  const filePath = path.join(process.cwd(), "data", "filtered_cheap_full.json");
  if (!fs.existsSync(filePath)) {
    return Response.json({ error: "필터통과 데이터가 아직 생성되지 않았습니다." }, { status: 404 });
  }
  const payload: FilteredPayload = JSON.parse(fs.readFileSync(filePath, "utf-8"));
  const workbookBytes = createFilteredWorkbook(payload);
  return new Response(workbookBytes, {
    headers: {
      "Content-Type": XLSX_CONTENT_TYPE,
      "Content-Disposition": `attachment; filename="cheap-stocks.xlsx"; filename*=UTF-8''${DOWNLOAD_NAME}`,
      "Cache-Control": "public, max-age=0, s-maxage=31536000, immutable",
    },
  });
}
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd web && npm test -- filtered-cheap-route.test.ts`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/app/api/filtered-cheap/route.ts web/tests/filtered-cheap-route.test.ts
git commit -m "feat: /api/filtered-cheap 다운로드 라우트 추가"
```

---

### Task 10: `ScreeningSection.tsx` 추출 + `ScreeningTable` 신규 컬럼 서식

**Files:**
- Create: `web/app/ScreeningSection.tsx`
- Modify: `web/app/ScreeningTable.tsx:33-42`
- Test: Create `web/tests/screening-section.test.ts`, Create `web/tests/screening-table-formatting.test.ts`

**Interfaces:**
- Consumes: `ScreeningTable`, `FilteredDownloadButton({ href, passed, total })` (Task 7),
  `formatKoreanDate`, `ResultsPayload` (기존 `web/lib/format.ts`, `web/lib/types.ts`, 변경 없음)
- Produces: `ScreeningSection({ data, algorithmInfo, downloadHref })` (Task 11의 `page.tsx`가 소비)

- [ ] **Step 1: 실패하는 테스트 작성**

`web/tests/screening-section.test.ts` 생성:

```ts
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("ScreeningSection", () => {
  it("빈 결과 상태와 정상 결과 상태를 모두 처리하고 downloadHref/algorithmInfo를 prop으로 받는다", () => {
    const source = fs.readFileSync(
      path.join(process.cwd(), "app/ScreeningSection.tsx"),
      "utf8"
    );

    expect(source).toContain("아직 결과가 없습니다");
    expect(source).toContain("downloadHref");
    expect(source).toContain("algorithmInfo");
    expect(source).toContain("<ScreeningTable");
    expect(source).toContain("<FilteredDownloadButton");
    expect(source).toContain("href={downloadHref}");
  });
});
```

`web/tests/screening-table-formatting.test.ts` 생성:

```ts
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("ScreeningTable 숫자 포맷", () => {
  it("Cheap Stock Picking 전용 컬럼이 서식 규칙에 포함된다", () => {
    const source = fs.readFileSync(
      path.join(process.cwd(), "app/ScreeningTable.tsx"),
      "utf8"
    );

    expect(source).toMatch(/TWO_DECIMAL_RIGHT_ALIGN = new Set\(\[[^\]]*"dist_from_52w_low_pct"/s);
    expect(source).toMatch(/TWO_DECIMAL_RIGHT_ALIGN = new Set\(\[[^\]]*"ev_ebit"/s);
    expect(source).toMatch(/RIGHT_ALIGN_ONLY = new Set\(\[[^\]]*"low_52w"/s);
    expect(source).toMatch(/RIGHT_ALIGN_ONLY = new Set\(\[[^\]]*"op_ttm_eok"/s);
  });
});
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd web && npm test -- screening-section.test.ts screening-table-formatting.test.ts`
Expected: FAIL — `ScreeningSection.tsx`가 없어서 첫 테스트가 ENOENT로 실패하고,
`ScreeningTable.tsx`에 아직 새 컬럼명이 없어서 두 번째 테스트도 실패

- [ ] **Step 3: `ScreeningTable.tsx` 서식 규칙 갱신**

`web/app/ScreeningTable.tsx:33-42`의 다음 블록:

```tsx
const TWO_DECIMAL_RIGHT_ALIGN = new Set([
  "per", "pbr", "roe_3y_avg", "debt_ratio", "div_yield", "payout_ratio_pct",
]);

// 소수점 4자리 + 우측 정렬 (종합점수 전용)
const FOUR_DECIMAL_RIGHT_ALIGN = new Set(["score"]);

// 우측 정렬만 적용할 컬럼 (숫자 포맷은 기본값 유지)
const RIGHT_ALIGN_ONLY = new Set(["close"]);
```

를 다음으로 교체:

```tsx
const TWO_DECIMAL_RIGHT_ALIGN = new Set([
  "per", "pbr", "roe_3y_avg", "debt_ratio", "div_yield", "payout_ratio_pct",
  "dist_from_52w_low_pct", "ev_ebit",
]);

// 소수점 4자리 + 우측 정렬 (종합점수 전용)
const FOUR_DECIMAL_RIGHT_ALIGN = new Set(["score"]);

// 우측 정렬만 적용할 컬럼 (숫자 포맷은 기본값 유지)
const RIGHT_ALIGN_ONLY = new Set(["close", "low_52w", "op_ttm_eok", "op_income_5y_ago_eok"]);
```

- [ ] **Step 4: `ScreeningSection.tsx` 생성**

`web/app/ScreeningSection.tsx` 생성 (기존 `page.tsx`의 결과 표시 블록을 그대로 옮긴 것):

```tsx
import type { ReactNode } from "react";
import ScreeningTable from "./ScreeningTable";
import FilteredDownloadButton from "./FilteredDownloadButton";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatKoreanDate } from "@/lib/format";
import type { ResultsPayload } from "@/lib/types";

export default function ScreeningSection({
  data,
  algorithmInfo,
  downloadHref,
}: {
  data: ResultsPayload;
  algorithmInfo: ReactNode;
  downloadHref: string;
}) {
  if (data.results.length === 0) {
    return (
      <Card>
        <CardContent className="text-sm text-muted-foreground">
          아직 결과가 없습니다. GitHub Actions가 처음 실행되면 자동으로 채워집니다.
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <Badge variant="secondary">가격 기준일 {formatKoreanDate(data.as_of_date)}</Badge>
        <Badge variant="secondary">재무 기준연도 {data.financial_year}</Badge>
        <FilteredDownloadButton
          href={downloadHref}
          passed={data.universe_passed}
          total={data.universe_total}
        />
        <Badge variant="outline">
          갱신{" "}
          {data.generated_at
            ? new Date(data.generated_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })
            : "-"}
        </Badge>
      </div>

      {algorithmInfo}

      <ScreeningTable
        columns={data.columns}
        labels={data.column_labels_ko}
        rows={data.results}
      />
    </>
  );
}
```

- [ ] **Step 5: 테스트 실행해서 통과 확인**

Run: `cd web && npm test -- screening-section.test.ts screening-table-formatting.test.ts`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add web/app/ScreeningSection.tsx web/app/ScreeningTable.tsx \
        web/tests/screening-section.test.ts web/tests/screening-table-formatting.test.ts
git commit -m "refactor: 결과 표시 블록을 ScreeningSection으로 추출하고 신규 컬럼 서식 추가"
```

---

### Task 11: `page.tsx` — 탭으로 재구성

**Files:**
- Modify: `web/app/page.tsx` (전체 교체)
- Test: Create `web/tests/page-tabs.test.ts`

**Interfaces:**
- Consumes: `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent` (Task 6),
  `ScreeningSection` (Task 10), `AlgorithmInfo` (기존), `CheapAlgorithmInfo` (Task 8)

- [ ] **Step 1: 실패하는 테스트 작성**

`web/tests/page-tabs.test.ts` 생성:

```ts
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("page.tsx 탭 구성", () => {
  it("가치투자/Cheap Stock Picking 두 탭을 각각 ScreeningSection으로 렌더링한다", () => {
    const source = fs.readFileSync(path.join(process.cwd(), "app/page.tsx"), "utf8");

    expect(source).toContain('from "@/components/ui/tabs"');
    expect(source).toContain(">가치투자<");
    expect(source).toContain(">Cheap Stock Picking<");
    expect(source).toContain('"results.json"');
    expect(source).toContain('"results_cheap.json"');
    expect(source).toContain('downloadHref="/api/filtered"');
    expect(source).toContain('downloadHref="/api/filtered-cheap"');
  });

  it("results_cheap.json이 없어도 죽지 않도록 존재 여부를 확인한다", () => {
    const source = fs.readFileSync(path.join(process.cwd(), "app/page.tsx"), "utf8");

    expect(source).toContain("existsSync");
  });
});
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd web && npm test -- page-tabs.test.ts`
Expected: FAIL — 현재 `page.tsx`에는 탭도, `results_cheap.json` 로딩도, `existsSync` 체크도 없음

- [ ] **Step 3: `page.tsx` 전체 교체**

`web/app/page.tsx` 전체를 다음으로 교체:

```tsx
import fs from "fs";
import path from "path";
import ScreeningSection from "./ScreeningSection";
import AlgorithmInfo from "./AlgorithmInfo";
import CheapAlgorithmInfo from "./CheapAlgorithmInfo";
import AdminGate from "./AdminGate";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ResultsPayload } from "@/lib/types";

export const dynamic = "force-static"; // 빌드 시점 JSON을 그대로 굽는다 (커밋될 때마다 재배포되며 갱신됨)

const EMPTY_PAYLOAD: ResultsPayload = {
  as_of_date: null,
  financial_year: null,
  generated_at: null,
  quote_text: null,
  quote_author: null,
  universe_total: 0,
  universe_passed: 0,
  columns: [],
  column_labels_ko: {},
  results: [],
};

function loadJsonPayload(filename: string): ResultsPayload {
  const filePath = path.join(process.cwd(), "data", filename);
  if (!fs.existsSync(filePath)) return EMPTY_PAYLOAD; // 최초 배포 등 파일이 아직 없는 경우
  const raw = fs.readFileSync(filePath, "utf-8");
  return JSON.parse(raw);
}

export default function Home() {
  const data = loadJsonPayload("results.json");
  const cheapData = loadJsonPayload("results_cheap.json");

  return (
    <main className="mx-auto max-w-6xl px-5 py-10">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">한국 주식 스크리닝</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {data.quote_text
            ? `"${data.quote_text}" — ${data.quote_author}`
            : "Stock Note 투자원칙 기반 코스피 종목 스크리닝"}
        </p>
      </div>

      <Tabs defaultValue="value">
        <TabsList className="mb-5">
          <TabsTrigger value="value">가치투자</TabsTrigger>
          <TabsTrigger value="cheap">Cheap Stock Picking</TabsTrigger>
        </TabsList>
        <TabsContent value="value">
          <ScreeningSection
            data={data}
            algorithmInfo={<AlgorithmInfo />}
            downloadHref="/api/filtered"
          />
        </TabsContent>
        <TabsContent value="cheap">
          <ScreeningSection
            data={cheapData}
            algorithmInfo={<CheapAlgorithmInfo />}
            downloadHref="/api/filtered-cheap"
          />
        </TabsContent>
      </Tabs>

      <AdminGate />
    </main>
  );
}
```

(제목을 "한국 가치투자 스크리닝"에서 "한국 주식 스크리닝"으로 변경했다 — 이제 페이지가
가치투자 전략만이 아니라 두 전략을 함께 보여주므로.)

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd web && npm test -- page-tabs.test.ts`
Expected: PASS

- [ ] **Step 5: 전체 웹 테스트 스위트 실행 (회귀 확인)**

Run: `cd web && npm test`
Expected: PASS (모든 테스트 스위트)

- [ ] **Step 6: 빌드 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공 (타입 에러 없음). `results_cheap.json`이 아직 저장소에 없어도
`loadJsonPayload`가 빈 payload로 대체하므로 빌드가 깨지지 않아야 한다.

- [ ] **Step 7: 커밋**

```bash
git add web/app/page.tsx web/tests/page-tabs.test.ts
git commit -m "feat: page.tsx를 탭 구조로 재구성해 Cheap Stock Picking 탭 추가"
```

- [ ] **Step 8: (수동 확인) 로컬에서 두 탭 동작 확인**

Run: `cd web && npm run dev` 후 브라우저에서 `http://localhost:3000` 접속.
확인 사항: "가치투자"/"Cheap Stock Picking" 탭 전환, 정렬 클릭, "최신 종가 새로고침" 버튼,
종목명 클릭 시 프로필 모달, "Cheap Stock Picking" 탭이 데이터 없을 때 빈 상태 문구가
정상 표시되는지.

---

## Self-Review 결과

**스펙 커버리지:** 설계 문서(`docs/superpowers/specs/2026-08-29-cheap-stock-picking-tab-design.md`)의
A~E절 전부에 대응하는 태스크가 있음 — A(Task 1, 2), B(Task 3, 4), C(Task 5), D(Task 6~11),
E(테스트는 각 태스크에 내장). 비용/성능 참고 섹션은 코드 변경이 아니므로 별도 태스크 없음(설계
문서 자체가 그 기록 역할을 함).

**플레이스홀더 스캔:** 없음 — 모든 스텝에 실행 가능한 전체 코드/명령어가 포함됨.

**타입/이름 일관성 확인:** `add_cheap_metrics`/`apply_cheap_filters`(Task 3) 시그니처가
`load_cheap`(Task 4)의 사용과 일치. `FilteredDownloadButton`의 `href` prop(Task 7)이
`ScreeningSection`(Task 10)과 `page.tsx`(Task 11)에서 동일하게 사용됨. `Tabs`/`TabsList`/
`TabsTrigger`/`TabsContent`(Task 6) export 이름이 `page.tsx`(Task 11) import와 일치.
`data_pipeline.py`의 `PRICE_HISTORY_FILE`/`update_price_history`/`get_52w_low`(Task 2)가
`cheap_screen.py`의 `load_cheap`(Task 4)에서 그대로 사용됨.
