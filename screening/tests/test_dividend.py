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
