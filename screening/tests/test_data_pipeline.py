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
