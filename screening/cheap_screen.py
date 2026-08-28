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
