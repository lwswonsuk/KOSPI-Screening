"""
data_pipeline.py — KOSPI 재무데이터 캐싱 레이어
================================================================
DART API를 매번 호출하지 않도록, 종목별 재무데이터를 로컬 parquet에
저장해두고 재사용한다. finstate() 한 번 호출로 당기/전기/전전기
3개년 데이터를 한꺼번에 받아오는 방식으로 API 호출 횟수를 최소화했다.

사용법:
    python data_pipeline.py --build          # 캐시 새로 만들기 (최초 1회, 시간 걸림)
    python data_pipeline.py --build --force  # 캐시 무시하고 전부 새로 받기
    python data_pipeline.py --status         # 캐시 현황 확인

캐시 파일:
    .cache/corp_codes.parquet   — 종목코드 ↔ DART 고유번호 매핑
    .cache/finance.parquet      — 종목별 재무비율 (ROE, 부채비율 등)
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)
ANNUAL_YEAR_FILE = CACHE_DIR / "annual_year.txt"  # 자동 감지된 사업연도를 다른 스크립트와 공유하기 위한 파일


def auto_ttm_params(today=None) -> tuple[int, int, str]:
    """
    오늘 날짜를 보고 '지금 시점에 이미 공시되어 있을 최신 분기'를 자동으로 추정한다.
    공시 마감 기한 기준 (45일/90일 규정):
      1분기보고서: 5월 15일경 마감      3분기보고서: 11월 14일경 마감
      반기보고서:  8월 14일경 마감      사업(연간)보고서: 다음해 3월 31일경 마감

    반환값: (annual_year, ttm_year, ttm_quarter)
      annual_year — 이미 확정된 직전 연간 사업보고서 연도
      ttm_year    — TTM 계산에 쓸 '올해' 분기누적 연도
      ttm_quarter — 그 분기 코드 (Q1/H1/Q3)
    """
    from datetime import date as _date
    if today is None:
        today = _date.today()
    y = today.year
    md = (today.month, today.day)

    if md < (5, 15):
        # 올해 1분기 보고서도 아직 안 나온 시기 → 작년 3분기 누적이 최신
        return y - 2, y - 1, "Q3"
    elif md < (8, 15):
        # 1분기는 나왔고(5/15~), 반기는 아직(8/15부터)
        return y - 1, y, "Q1"
    elif md < (11, 15):
        # 반기는 나왔고(8/15~), 3분기는 아직(11/15부터)
        return y - 1, y, "H1"
    else:
        # 3분기까지 나온 시기 (11/15~12월말)
        return y - 1, y, "Q3"
CORP_CODE_CACHE = CACHE_DIR / "corp_codes.parquet"
FINANCE_CACHE = CACHE_DIR / "finance.parquet"

# 재무제표에서 추출할 계정과목명 (DART 표준 계정명 기준 + IFRS 표기 차이 대응)
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
}

# 분기보고서 코드 (DART reprt_code)
QUARTER_CODES = {"Q1": "11013", "H1": "11012", "Q3": "11014", "FY": "11011"}


def get_dart_client():
    from opendartreader import OpenDartReader
    key = os.environ.get("DART_API_KEY")
    if not key:
        raise RuntimeError(
            "DART_API_KEY 환경변수가 없습니다. "
            "터미널에서 setx DART_API_KEY \"발급받은키\" 로 등록 후 새 터미널을 여세요."
        )
    return OpenDartReader(key)


# ═══════════════════════════════════════════════════════════════
# 1. 종목코드 ↔ DART 고유번호 매핑 캐시
# ═══════════════════════════════════════════════════════════════

def get_corp_codes(force: bool = False) -> pd.DataFrame:
    if CORP_CODE_CACHE.exists() and not force:
        return pd.read_parquet(CORP_CODE_CACHE)

    dart = get_dart_client()
    df = dart.corp_codes  # DataFrame: corp_code, corp_name, stock_code, modify_date
    df = df[df["stock_code"].notna() & (df["stock_code"] != "")].copy()
    df.to_parquet(CORP_CODE_CACHE, index=False)
    print(f"[corp_codes] {len(df)}개 상장사 매핑 저장 완료 → {CORP_CODE_CACHE}")
    return df


def get_kospi_universe(date: str) -> pd.DataFrame:
    """KRX 공식 Open API(유가증권 일별매매정보)로 코스피 전종목의
    가격·시가총액 스냅샷을 가져온다. (pykrx 스크래핑 대신 사용 —
    KRX가 스크래핑 방식 접근을 막고 있어 공식 API로 전환함)"""
    import requests

    key = os.environ.get("KRX_API_KEY")
    if not key:
        raise RuntimeError(
            "KRX_API_KEY 환경변수가 없습니다. "
            "터미널에서 setx KRX_API_KEY \"발급받은키\" 로 등록 후 새 터미널을 여세요."
        )

    url = "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"
    r = requests.get(url, params={"basDd": date}, headers={"AUTH_KEY": key}, timeout=30)
    r.raise_for_status()
    rows = r.json().get("OutBlock_1", [])
    if not rows:
        raise RuntimeError(f"KRX API 응답이 비어 있습니다 (날짜 {date} 확인 필요, 휴장일일 수 있음)")

    df = pd.DataFrame(rows)
    # 문자열로 오는 숫자 컬럼들을 숫자형으로 변환 (콤마 제거)
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
    (KRX SECT_TP_NM이 비어 있거나 다른 값을 줄 수 있어 여기서 명시적으로 덮어쓴다)

    코스닥 API(ksq_bydd_trd)는 KRX Open API 포털에서 별도 승인이 필요하다. 아직 승인 전이거나
    일시적으로 실패하면(401 등) 코스피만으로 계속 진행한다 — 승인이 완료되면 코드 수정 없이
    자동으로 코스닥이 합류한다."""
    kospi = get_kospi_universe(date).copy()
    kospi["sector_raw"] = "코스피"

    try:
        kosdaq = get_kosdaq_universe(date).copy()
        kosdaq["sector_raw"] = "코스닥"
    except Exception as e:
        print(f"[WARN] 코스닥 유니버스 조회 실패, 코스피만으로 계속 진행합니다: {e}")
        return kospi

    combined = pd.concat([kospi, kosdaq])
    return combined[~combined.index.duplicated(keep="first")]


# ═══════════════════════════════════════════════════════════════
# 2. 종목별 재무데이터 추출 (finstate 1콜 = 3개년)
# ═══════════════════════════════════════════════════════════════

def _extract_year(row_by_account: dict, col: str) -> dict:
    """thstrm_amount / frmtrm_amount / bfefrmtrm_amount 중 하나의 연도 컬럼을 뽑아 dict로."""
    out = {}
    for kor, eng in ACCOUNT_MAP.items():
        v = row_by_account.get(kor, {}).get(col)
        out[eng] = _to_float(v)
    return out


def _to_float(v) -> float:
    if v is None:
        return np.nan
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return np.nan


def _prefer_quarterly(quarterly_value: float, annual_value: float) -> float:
    """분기 값이 있으면 우선 사용, 없으면(NaN) 연간값으로 폴백."""
    return quarterly_value if not np.isnan(quarterly_value) else annual_value


def _extract_financials_3col(fs: pd.DataFrame) -> tuple[dict, dict, dict]:
    """finstate 응답 하나에서 당기/전기/전전기 3개 시점 금액을 계정별로 뽑는다."""
    row_by_account: dict[str, dict] = {}
    for _, r in fs.iterrows():
        acc = str(r.get("account_nm", "")).strip()
        if acc in ACCOUNT_MAP:
            row_by_account[acc] = {
                "thstrm_amount": r.get("thstrm_amount"),
                "frmtrm_amount": r.get("frmtrm_amount"),
                "bfefrmtrm_amount": r.get("bfefrmtrm_amount"),
            }
    return (
        _extract_year(row_by_account, "thstrm_amount"),
        _extract_year(row_by_account, "frmtrm_amount"),
        _extract_year(row_by_account, "bfefrmtrm_amount"),
    )


def _extract_financials(fs: pd.DataFrame) -> tuple[dict, dict]:
    """finstate 응답 하나에서 당기(thstrm)/전기(frmtrm) 금액을 계정별로 뽑는다."""
    row_by_account: dict[str, dict] = {}
    for _, r in fs.iterrows():
        acc = str(r.get("account_nm", "")).strip()
        if acc in ACCOUNT_MAP:
            row_by_account[acc] = {
                "thstrm_amount": r.get("thstrm_amount"),
                "frmtrm_amount": r.get("frmtrm_amount"),
            }
    return (
        _extract_year(row_by_account, "thstrm_amount"),
        _extract_year(row_by_account, "frmtrm_amount"),
    )


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


def fetch_finance_one(dart, stock_code: str, corp_code: str, annual_year: int,
                       ttm_year: int, ttm_quarter: str) -> Optional[dict]:
    """
    두 번의 finstate 호출로 TTM(최근 4분기 누적) 재무데이터를 구성한다.

    1) 연간(사업)보고서(annual_year) → 당기/전기/전전기 3개년, 장기 안정성 지표(ROE 3년평균 등)에 사용
    2) 분기누적보고서(ttm_year, ttm_quarter) → 당기누적(thstrm) + 전년동기누적(frmtrm)이 한 번에 나옴

    TTM = 당기누적(올해) + [작년 연간 - 작년동기누적]
        예) ttm_quarter='H1', ttm_year=2026, annual_year=2025 인 경우:
            TTM = 2026년 상반기 누적 + (2025년 연간 - 2025년 상반기 누적)
            = 2025년 3분기 ~ 2026년 2분기, 즉 최근 4개 분기
    """
    try:
        fs_annual = dart.finstate(corp_code, annual_year, reprt_code=QUARTER_CODES["FY"])
    except Exception as e:
        print(f"  [WARN] {stock_code} 연간 finstate 실패: {e}")
        return None
    if not isinstance(fs_annual, pd.DataFrame) or len(fs_annual) == 0:
        return None

    y0, y1, y2 = _extract_financials_3col(fs_annual)   # y0=annual_year(작년 연간), y1=재작년, y2=그전해

    def safe_div(a, b):
        if a is None or b is None or b == 0 or np.isnan(a) or np.isnan(b):
            return np.nan
        return a / b

    # ---- 장기 안정성 (연간 3개년 기준, 기존 로직 유지) ----
    roe0 = safe_div(y0["net_income"], y0["total_equity"]) * 100
    roe1 = safe_div(y1["net_income"], y1["total_equity"]) * 100
    roe2 = safe_div(y2["net_income"], y2["total_equity"]) * 100
    roe_series = [x for x in [roe0, roe1, roe2] if not np.isnan(x)]
    rev_cagr_3y = np.nan
    if not np.isnan(y0["revenue"]) and not np.isnan(y2["revenue"]) and y2["revenue"] > 0:
        rev_cagr_3y = (y0["revenue"] / y2["revenue"]) ** (1 / 2) - 1
    years_no_decline = 0
    for cur, prev in [(y0["revenue"], y1["revenue"]), (y1["revenue"], y2["revenue"])]:
        if not np.isnan(cur) and not np.isnan(prev) and cur >= prev:
            years_no_decline += 1

    # ---- TTM(최근 4분기) 계산 ----
    ttm_basis = f"TTM({ttm_year}{ttm_quarter})"
    quarter_order = ["Q1", "H1", "Q3", "FY"]
    tried = [ttm_quarter] + [q for q in quarter_order if q != ttm_quarter]

    fs_q, q_used = None, None
    for q in tried:
        try:
            candidate = dart.finstate(corp_code, ttm_year, reprt_code=QUARTER_CODES[q])
        except Exception:
            candidate = None
        # OpenDartReader가 데이터 없음(status 013 등)일 때 DataFrame이 아닌
        # dict나 None을 반환하는 경우가 있어, 명시적으로 DataFrame인지 확인
        if isinstance(candidate, pd.DataFrame) and len(candidate) > 0:
            fs_q, q_used = candidate, q
            break

    if fs_q is not None and q_used is not None:
        cur_cum, prior_cum = _extract_financials(fs_q)
        prior_annual = y0  # annual_year(=ttm_year-1 가정)의 연간 값

        def ttm_calc(key):
            a, b, c = cur_cum.get(key), prior_annual.get(key), prior_cum.get(key)
            if a is None or np.isnan(a):
                return np.nan
            if b is None or np.isnan(b) or c is None or np.isnan(c):
                return a  # 작년 비교값이 없으면 그냥 당해 누적치라도 사용 (완전 TTM은 아님)
            return a + (b - c)

        revenue_ttm = ttm_calc("revenue")
        op_income_ttm = ttm_calc("op_income")
        net_income_ttm = ttm_calc("net_income")
        # YoY는 "당기누적 vs 작년동기누적" 그대로 사용 (더 직관적)
        op_yoy = safe_div(cur_cum["op_income"] - prior_cum["op_income"], abs(prior_cum["op_income"])) \
            if not np.isnan(prior_cum.get("op_income", np.nan)) else np.nan
        rev_yoy = safe_div(cur_cum["revenue"] - prior_cum["revenue"], abs(prior_cum["revenue"])) \
            if not np.isnan(prior_cum.get("revenue", np.nan)) else np.nan
        # 재무상태표 항목은 분기 시점(가장 최신) 값 사용
        total_equity_latest = _prefer_quarterly(cur_cum.get("total_equity", np.nan), y0["total_equity"])
        total_liab_latest = _prefer_quarterly(cur_cum.get("total_liabilities", np.nan), y0["total_liabilities"])
        if q_used != ttm_quarter:
            ttm_basis = f"TTM 실패, {q_used} 누적치로 대체 (완전한 4분기 합산 아님)"
    else:
        # 분기 데이터를 전혀 못 받으면 연간 값으로 대체 (완전한 TTM 아님, 표시만 해둠)
        revenue_ttm, op_income_ttm, net_income_ttm = y0["revenue"], y0["op_income"], y0["net_income"]
        op_yoy = safe_div(y0["op_income"] - y1["op_income"], abs(y1["op_income"])) if not np.isnan(y1["op_income"]) else np.nan
        rev_yoy = safe_div(y0["revenue"] - y1["revenue"], abs(y1["revenue"])) if not np.isnan(y1["revenue"]) else np.nan
        total_equity_latest = y0["total_equity"]
        total_liab_latest = y0["total_liabilities"]
        ttm_basis = f"분기데이터 없음, FY{annual_year} 연간값 사용"

    debt_ratio = safe_div(total_liab_latest, total_equity_latest) * 100
    op_margin = safe_div(op_income_ttm, revenue_ttm) * 100

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
        "cash_dividend_total": div["cash_dividend_total"],
        "payout_ratio": payout_ratio,
    }


def build_finance_cache(annual_year: int, ttm_year: int, ttm_quarter: str, date: str,
                         force: bool = False, sleep_sec: float = 0.3):
    ANNUAL_YEAR_FILE.write_text(str(annual_year), encoding="utf-8")  # ws_alpha.py 등이 같은 연도 참조하도록 기록
    corp_codes = get_corp_codes(force=force)
    universe = get_full_universe(date).reset_index()

    merged = universe.merge(corp_codes[["stock_code", "corp_code"]], on="stock_code", how="inner")
    print(f"[universe] 전체(코스피+코스닥) {len(universe)}개 중 DART 매핑 성공 {len(merged)}개")

    existing = pd.DataFrame()
    done_codes = set()
    if FINANCE_CACHE.exists() and not force:
        existing = pd.read_parquet(FINANCE_CACHE)
        if "bsns_year" in existing.columns and len(existing) > 0:
            done_codes = set(existing.loc[existing["bsns_year"] == annual_year, "stock_code"])
            print(f"[cache] 기존 캐시 {len(done_codes)}개 종목 재사용")
        else:
            print("[cache] 기존 캐시가 비어 있거나 형식이 달라 무시하고 새로 받습니다")
            existing = pd.DataFrame()

    dart = get_dart_client()
    rows = []
    todo = merged[~merged["stock_code"].isin(done_codes)]
    print(f"[fetch] 신규로 받아올 종목: {len(todo)}개 (종목당 2콜, 예상 소요 약 {len(todo) * sleep_sec * 2 / 60:.1f}분)")

    for i, (_, r) in enumerate(todo.iterrows(), 1):
        res = fetch_finance_one(dart, r["stock_code"], r["corp_code"], annual_year, ttm_year, ttm_quarter)
        if res:
            rows.append(res)
        if i % 50 == 0:
            print(f"  진행 {i}/{len(todo)}")
        time.sleep(sleep_sec)

    new_df = pd.DataFrame(rows)
    combined = pd.concat([existing, new_df], ignore_index=True) if len(existing) else new_df
    combined = combined.drop_duplicates(subset=["stock_code", "bsns_year"], keep="last")
    combined.to_parquet(FINANCE_CACHE, index=False)
    print(f"[done] 재무캐시 저장 완료: {len(combined)}행 → {FINANCE_CACHE}")
    if len(new_df):
        print("[ttm_basis 샘플]")
        print(new_df["ttm_basis"].value_counts().head(10).to_string())
    return combined


def status():
    if CORP_CODE_CACHE.exists():
        cc = pd.read_parquet(CORP_CODE_CACHE)
        print(f"corp_codes 캐시: {len(cc)}개 ({CORP_CODE_CACHE})")
    else:
        print("corp_codes 캐시 없음")

    if FINANCE_CACHE.exists():
        fc = pd.read_parquet(FINANCE_CACHE)
        print(f"finance 캐시: {len(fc)}행")
        print(fc.groupby("bsns_year").size().to_string())
    else:
        print("finance 캐시 없음")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--auto", action="store_true",
                     help="오늘 날짜를 기준으로 사업연도·TTM분기를 자동 판단 (--year/--ttm-quarter 무시)")
    ap.add_argument("--year", type=int, default=2025,
                     help="직전 완료 사업연도 (예: 2025 = 2025년 연간 사업보고서, 장기 안정성 지표용)")
    ap.add_argument("--ttm-quarter", choices=["Q1", "H1", "Q3", "FY"], default="H1",
                     help="TTM 계산에 쓸 올해 최신 분기누적: Q1=1분기, H1=반기, Q3=3분기누적, FY=연간(사실상 TTM=연간과 동일)")
    ap.add_argument("--date", default="20260807", help="기준일자 YYYYMMDD (코스피 종목 목록 조회용, 최근 영업일 아무 날짜)")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    if a.status:
        status()
    elif a.build:
        if a.auto:
            annual_year, ttm_year, ttm_quarter = auto_ttm_params()
            print(f"[auto] 오늘 날짜 기준 자동 판단: 사업연도={annual_year}, "
                  f"TTM기준={ttm_year}년 {ttm_quarter}")
        else:
            annual_year, ttm_year, ttm_quarter = a.year, a.year + 1, a.ttm_quarter
        build_finance_cache(annual_year, ttm_year, ttm_quarter, a.date, force=a.force)
    else:
        print("사용법: python data_pipeline.py --build  또는  --status")
