# -*- coding: utf-8 -*-
import pandas as pd

from data_pipeline import fetch_finance_one, ACCOUNT_MAP

# Use account names directly from ACCOUNT_MAP to ensure encoding consistency
# This avoids any encoding issues with literal Korean characters in the test file
_op_income_acc = next(k for k, v in ACCOUNT_MAP.items() if v == "op_income" and "손실" not in k)  # not '손실'
_net_income_acc = next(k for k, v in ACCOUNT_MAP.items() if v == "net_income" and "손실" not in k)  # not '손실'
_revenue_acc = next(k for k, v in ACCOUNT_MAP.items() if v == "revenue" and "(" not in k)
_total_equity_acc = next(k for k, v in ACCOUNT_MAP.items() if v == "total_equity")
_total_liab_acc = next(k for k, v in ACCOUNT_MAP.items() if v == "total_liabilities")
_cash_equiv_acc = next(k for k, v in ACCOUNT_MAP.items() if v == "cash_equivalents")


class FakeDart:
    """dart 클라이언트를 흉내내는 테스트 더블. fetch_finance_one은 dart를
    이미 인자로 주입받는 구조라 실제 네트워크 호출 없이 검증 가능하다."""

    def finstate(self, corp_code, year, reprt_code):
        if year == 2025 and reprt_code == "11011":  # annual_year FY
            return pd.DataFrame([
                {"account_nm": _revenue_acc, "thstrm_amount": "100000",
                 "frmtrm_amount": "90000", "bfefrmtrm_amount": "80000"},
                {"account_nm": _op_income_acc, "thstrm_amount": "10000",
                 "frmtrm_amount": "9000", "bfefrmtrm_amount": "8000"},
                {"account_nm": _net_income_acc, "thstrm_amount": "8000",
                 "frmtrm_amount": "7000", "bfefrmtrm_amount": "6000"},
                {"account_nm": _total_equity_acc, "thstrm_amount": "50000",
                 "frmtrm_amount": "48000", "bfefrmtrm_amount": "46000"},
                {"account_nm": _total_liab_acc, "thstrm_amount": "20000",
                 "frmtrm_amount": "19000", "bfefrmtrm_amount": "18000"},
                {"account_nm": _cash_equiv_acc, "thstrm_amount": "5000",
                 "frmtrm_amount": "4500", "bfefrmtrm_amount": "4000"},
            ])
        if year == 2026 and reprt_code == "11012":  # ttm_year H1
            return pd.DataFrame([
                {"account_nm": _revenue_acc, "thstrm_amount": "55000", "frmtrm_amount": "44000"},
                {"account_nm": _op_income_acc, "thstrm_amount": "6000", "frmtrm_amount": "4000"},
                {"account_nm": _net_income_acc, "thstrm_amount": "5000", "frmtrm_amount": "3500"},
                {"account_nm": _total_equity_acc, "thstrm_amount": "52000", "frmtrm_amount": "47000"},
                {"account_nm": _total_liab_acc, "thstrm_amount": "21000", "frmtrm_amount": "18500"},
            ])
        if year == 2020 and reprt_code == "11011":  # annual_year - 5 FY
            return pd.DataFrame([
                {"account_nm": _op_income_acc, "thstrm_amount": "3000",
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


def test_extract_year_preserves_value_from_first_matching_account_variant():
    """Regression test: _extract_year must preserve the first non-nan value when
    multiple ACCOUNT_MAP keys map to the same eng value (e.g., "영업이익" and
    "영업이익(손실)" both map to "op_income"). Only the variant present in
    row_by_account should contribute its value; absent variants must not overwrite
    with nan.

    This test verifies the bug fix in _extract_year that prevents nan from
    subsequent unmapped keys from overwriting real data from earlier keys.
    """
    from data_pipeline import _extract_year
    import numpy as np

    # Get both Korean variants that map to 'op_income'
    op_income_variants = [k for k, v in ACCOUNT_MAP.items() if v == "op_income"]
    assert len(op_income_variants) == 2, "Expected exactly 2 variants for op_income"

    # Variant 1: without 손실 (should be "영업이익")
    variant_with_value = next(k for k in op_income_variants if "손실" not in k)
    # Variant 2: with 손실 (should be "영업이익(손실)")
    variant_without_value = next(k for k in op_income_variants if "손실" in k)

    # Create row_by_account with only the first variant having data
    row_by_account = {
        variant_with_value: {
            "thstrm_amount": "10000",
            "frmtrm_amount": "9000",
            "bfefrmtrm_amount": "8000",
        }
    }

    # Extract for current year column
    result = _extract_year(row_by_account, "thstrm_amount")

    # The real value from variant_with_value (10000) must be preserved
    # and not overwritten by nan from the absent variant_without_value
    assert result["op_income"] == 10000.0, (
        f"Expected op_income=10000.0, got {result['op_income']}. "
        "Bug: nan from absent variant overwrote the real value."
    )

    # Verify that other eng keys that don't have variants present are still nan
    assert np.isnan(result["revenue"]), "revenue should be nan (not in row_by_account)"
    assert np.isnan(result["net_income"]), "net_income should be nan (not in row_by_account)"


# Task 2: 52주 최저가 rolling 캐시 테스트
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
