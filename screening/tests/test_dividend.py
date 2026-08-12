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
