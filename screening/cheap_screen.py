"""
cheap_screen.py — "Cheap Korean Stocks" 스크리닝
================================================================
가치투자 스크리닝(ws_alpha.py)과 완전히 다른 알고리즘. 코스피+코스닥 전종목을
대상으로 4가지 조건을 모두 만족해야 통과한다:
  1) 현재가가 52주 최저가의 10% 이내
  2) EPS(TTM)가 3년 전 OR 4년 전 OR 5년 전 EPS보다 큼 (셋 중 하나만 만족해도 됨)
     단, 3~5년 중 확인된 적자(당기순손실)가 있는 해가 하나라도 있으면 제외
     (데이터가 없어서 확인이 안 되는 해는 적자로 간주하지 않음)
  3) PER < 10배
  4) EBITDA(영업이익 TTM 근사) > 0 이고 EV/EBITDA < 20배
     (EV = 시가총액 + 총부채, 근사치 — DART finstate API가 현금성자산을
     제공하지 않아 차감하지 않음. EBITDA도 감가상각비 데이터가 없어
     영업이익으로 근사)

가치투자 탭과 달리 시총/거래대금 유동성 하한선은 적용하지 않는다. 정렬은 EV/EBITDA 오름차순.
"""

from __future__ import annotations

import argparse

from data_pipeline import format_financial_period_label
from quotes import pick_quote_for_week
from stock_profile import generate_all_profiles

import numpy as np
import pandas as pd

COLS = ["name", "sector_raw", "mktcap_eok", "close", "low_52w",
        "dist_from_52w_low_pct", "per", "eps_now", "eps_3y_ago", "eps_4y_ago",
        "eps_5y_ago", "ev_ebitda"]

KOR_NAMES = {
    "name": "종목명", "sector_raw": "시장", "mktcap_eok": "시가총액(억)",
    "close": "종가", "low_52w": "52주최저가", "dist_from_52w_low_pct": "52주저가대비(%)",
    "per": "PER", "eps_now": "EPS(TTM)", "eps_3y_ago": "EPS(3년전)",
    "eps_4y_ago": "EPS(4년전)", "eps_5y_ago": "EPS(5년전)", "ev_ebitda": "EV/EBITDA",
}


def add_cheap_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """52주 저가 대비 괴리율, PER, EV, EBITDA, EV/EBITDA 파생 컬럼을 계산해
    추가한다. eps_now/eps_3y_ago/eps_4y_ago/eps_5y_ago/net_income_Xy_ago는
    재무 캐시(data_pipeline.fetch_finance_one)에서 이미 계산되어 들어온 값을
    그대로 쓴다.

    EV = 시가총액 + 총부채 (현금성자산 제외). DART의 finstate("재무제표
    주요계정") 응답에는 현금및현금성자산이 포함되지 않아(전종목 100% 결측
    확인됨) 뺄 수 없다. EBITDA도 감가상각비(D&A) 데이터가 없어 영업이익(TTM)
    으로 근사한다."""
    d = df.copy()
    d["dist_from_52w_low_pct"] = (d["close"] / d["low_52w"] - 1) * 100
    d["per"] = d["mktcap"] / d["net_income_ttm"].where(d["net_income_ttm"] > 0)
    d["ev"] = d["mktcap"] + d["total_liabilities"]
    d["ebitda"] = d["op_ttm"]
    d["ev_ebitda"] = d["ev"] / d["ebitda"].where(d["ebitda"] > 0)
    return d


def apply_cheap_filters(df: pd.DataFrame, max_dist_from_low_pct: float = 10.0,
                         max_per: float = 10.0, max_ev_ebitda: float = 20.0) -> pd.DataFrame:
    """4가지 통과 조건을 순수하게 적용한다 (유동성 하한선 없음). 결측치가 있는
    조건은 통과 실패로 처리한다 — 단, '3~5년 적자 제외'는 확인된 적자만
    걸러내며 데이터 결측은 적자로 간주하지 않는다(NaN과의 비교는 항상 False가
    되므로 별도 처리 없이 자연스럽게 그렇게 동작한다)."""
    d = df.copy()
    near_low = d["dist_from_52w_low_pct"] <= max_dist_from_low_pct

    eps_growing = (
        (d["eps_now"] > d["eps_3y_ago"])
        | (d["eps_now"] > d["eps_4y_ago"])
        | (d["eps_now"] > d["eps_5y_ago"])
    )
    had_deficit_3to5y = (
        (d["net_income_3y_ago"] < 0)
        | (d["net_income_4y_ago"] < 0)
        | (d["net_income_5y_ago"] < 0)
    )

    cheap_per = (d["net_income_ttm"] > 0) & (d["per"] < max_per)
    cheap_ev = (d["ebitda"] > 0) & (d["ev_ebitda"] < max_ev_ebitda)

    d["passed"] = (
        near_low.fillna(False)
        & eps_growing.fillna(False)
        & ~had_deficit_3to5y.fillna(False)
        & cheap_per.fillna(False)
        & cheap_ev.fillna(False)
    )
    return d


def load_cheap(date: str, bsns_year: int) -> tuple[pd.DataFrame, str]:
    """가격·52주최저가·재무 캐시에서 Cheap Korean Stocks에 필요한 컬럼을
    조립한다. 코스피+코스닥 전종목이 대상이다."""
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


def print_diagnostics(df: pd.DataFrame) -> None:
    """조건별 결측치/충족 현황을 출력한다. `add_cheap_metrics`가 이미 적용된
    데이터프레임(dist_from_52w_low_pct/per/ebitda/ev_ebitda 컬럼 포함)을
    받는다. 통과율이 비정상적으로 낮을 때 '조건이 엄격해서'인지 'DART 데이터를
    못 받아서 결측치가 나서'인지 구분하기 위한 운영 진단용 출력이다."""
    total = len(df)
    n_low_missing = int(df["low_52w"].isna().sum())
    n_near_low = int((df["dist_from_52w_low_pct"] <= 10.0).sum())

    n_eps_now_missing = int(df["eps_now"].isna().sum())
    n_eps_all_missing = int(
        (df["eps_3y_ago"].isna() & df["eps_4y_ago"].isna() & df["eps_5y_ago"].isna()).sum()
    )
    eps_growing = (
        (df["eps_now"] > df["eps_3y_ago"])
        | (df["eps_now"] > df["eps_4y_ago"])
        | (df["eps_now"] > df["eps_5y_ago"])
    )
    n_eps_growing = int(eps_growing.sum())

    had_deficit_3to5y = (
        (df["net_income_3y_ago"] < 0)
        | (df["net_income_4y_ago"] < 0)
        | (df["net_income_5y_ago"] < 0)
    )
    n_had_deficit = int(had_deficit_3to5y.sum())

    n_per_missing = int(df["per"].isna().sum())
    n_cheap_per = int(((df["net_income_ttm"] > 0) & (df["per"] < 10.0)).sum())

    n_liab_missing = int(df["total_liabilities"].isna().sum())
    n_ebitda_missing = int(df["ebitda"].isna().sum())
    n_ev_ebitda_missing = int(df["ev_ebitda"].isna().sum())
    n_cheap_ev = int(((df["ebitda"] > 0) & (df["ev_ebitda"] < 20.0)).sum())

    print("-" * 78)
    print("[진단] 조건별 결측치/충족 현황")
    print(f"  1) 52주최저가 10% 이내       : low_52w 결측 {n_low_missing}/{total}, 충족 {n_near_low}/{total}")
    print(f"  2) 3/4/5년전 대비 EPS 증가  : eps_now 결측 {n_eps_now_missing}/{total}, "
          f"3~5년전 EPS 전부 결측 {n_eps_all_missing}/{total}, "
          f"EPS증가 충족 {n_eps_growing}/{total}, 3~5년내 확인된 적자 {n_had_deficit}/{total}")
    print(f"  3) PER < 10배                : per 결측 {n_per_missing}/{total}, 충족 {n_cheap_per}/{total}")
    print(f"  4) EV/EBITDA < 20배          : total_liabilities 결측 {n_liab_missing}/{total}, "
          f"ebitda(<=0 포함) 결측 {n_ebitda_missing}/{total}, "
          f"ev_ebitda 결측 {n_ev_ebitda_missing}/{total}, 충족 {n_cheap_ev}/{total}")
    print("-" * 78)


def print_debug_names(df: pd.DataFrame, names: list[str]) -> None:
    """지정한 종목명이 통과/탈락한 이유를 조건별 수치와 함께 출력한다.
    `apply_cheap_filters`가 이미 적용된 데이터프레임(passed 컬럼 포함)을 받는다.
    사용자가 '이 종목은 왜 안 나오지?'라고 물었을 때 바로 답할 수 있도록 하는
    운영 디버그용 출력이다."""
    debug_cols = ["name", "sector_raw", "close", "low_52w", "dist_from_52w_low_pct",
                  "eps_now", "eps_3y_ago", "eps_4y_ago", "eps_5y_ago",
                  "net_income_3y_ago", "net_income_4y_ago", "net_income_5y_ago",
                  "net_income_ttm", "per", "ebitda", "ev", "ev_ebitda", "passed"]
    debug_cols = [c for c in debug_cols if c in df.columns]

    matched = df[df["name"].isin(names)]
    found_names = set(matched["name"])
    missing_names = [n for n in names if n not in found_names]

    print("=" * 78)
    print("[디버그] 지정 종목 상세")
    if len(matched) > 0:
        print(matched[debug_cols].to_string())
    if missing_names:
        print(f"유니버스에 없음 (재무캐시에 조인되지 않음): {missing_names}")
    print("=" * 78)


def run_cheap(date: str, bsns_year: int, top_n: int,
              export_json: str | None = None, filtered_json: str | None = None,
              debug_names: list[str] | None = None) -> pd.DataFrame:
    d, resolved_date = load_cheap(date, bsns_year)
    if resolved_date != date:
        print(f"[알림] 요청한 기준일 {date}은 휴장일로 보여, 최근 개장일 {resolved_date}로 대체합니다")
    date = resolved_date

    filt = apply_cheap_filters(d)
    if debug_names:
        print_debug_names(filt, debug_names)
    print_diagnostics(filt)
    ranked = filt.sort_values("ev_ebitda", ascending=True)

    print("=" * 78)
    print(f"Cheap Korean Stocks — 유니버스 {len(d)} → 통과 {int(filt['passed'].sum())} "
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
                "financial_period_label": format_financial_period_label(bsns_year),
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
    ap.add_argument("--debug-names", default="",
                     help="쉼표로 구분한 종목명 목록 — 통과 여부와 무관하게 조건별 수치를 출력 (예: 'CJ대한통운,효성ITX')")
    a = ap.parse_args()
    if a.run:
        run_cheap(a.date, a.year, a.top,
                   a.export_json if a.export_json else None,
                   a.filtered_json if a.filtered_json else None,
                   [n.strip() for n in a.debug_names.split(",") if n.strip()] if a.debug_names else None)
    else:
        print("사용법: python cheap_screen.py --run --date YYYYMMDD --year YYYY "
              "--export-json ... --filtered-json ...")
