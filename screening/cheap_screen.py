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

import argparse

from quotes import pick_quote_for_week
from stock_profile import generate_all_profiles

import numpy as np
import pandas as pd

COLS = ["name", "sector_raw", "mktcap_eok", "close", "low_52w",
        "dist_from_52w_low_pct", "op_ttm_eok", "op_income_5y_ago_eok", "ev_ebit"]

KOR_NAMES = {
    "name": "종목명", "sector_raw": "시장", "mktcap_eok": "시가총액(억)",
    "close": "종가", "low_52w": "52주최저가", "dist_from_52w_low_pct": "52주저가대비(%)",
    "op_ttm_eok": "영업이익(TTM,억원)", "op_income_5y_ago_eok": "영업이익(5년전,억원)",
    "ev_ebit": "EV/EBIT",
}


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
