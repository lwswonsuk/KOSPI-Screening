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
