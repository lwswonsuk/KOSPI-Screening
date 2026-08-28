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
