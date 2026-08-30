import numpy as np
import pandas as pd
import pytest

from cheap_screen import add_cheap_metrics, apply_cheap_filters, print_diagnostics


def _row(**overrides):
    base = dict(close=100, low_52w=95, mktcap=1000, total_liabilities=200,
                net_income_ttm=150, eps_now=10.0, eps_years_ago=8.0, op_ttm=150)
    base.update(overrides)
    return base


def test_add_cheap_metrics_computes_dist_per_ev_and_ev_ebit():
    df = pd.DataFrame([_row()])

    out = add_cheap_metrics(df)

    assert out.loc[0, "dist_from_52w_low_pct"] == pytest.approx((100 / 95 - 1) * 100)
    assert out.loc[0, "per"] == pytest.approx(1000 / 150)
    assert out.loc[0, "ev"] == 1000 + 200
    assert out.loc[0, "ev_ebit"] == pytest.approx((1000 + 200) / 150)


def test_add_cheap_metrics_per_is_nan_when_net_income_not_positive():
    df = pd.DataFrame([_row(net_income_ttm=0), _row(net_income_ttm=-10)])

    out = add_cheap_metrics(df)

    assert out["per"].isna().all()


def test_add_cheap_metrics_ev_ebit_is_nan_when_ebit_not_positive():
    df = pd.DataFrame([_row(op_ttm=0), _row(op_ttm=-10)])

    out = add_cheap_metrics(df)

    assert out["ev_ebit"].isna().all()


def test_apply_cheap_filters_passes_when_all_four_conditions_met():
    df = add_cheap_metrics(pd.DataFrame([_row()]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is True


def test_apply_cheap_filters_rejects_far_from_52w_low():
    df = add_cheap_metrics(pd.DataFrame([_row(close=130)]))  # 52주 저가 대비 +36.8%

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_rejects_eps_not_growing():
    df = add_cheap_metrics(pd.DataFrame([_row(eps_now=7.0, eps_years_ago=8.0)]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_rejects_high_per():
    df = add_cheap_metrics(pd.DataFrame([_row(net_income_ttm=50)]))  # per = 1000/50 = 20

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_rejects_high_ev_ebit():
    df = add_cheap_metrics(pd.DataFrame([_row(mktcap=5000, net_income_ttm=600)]))
    # per = 5000/600 ≈ 8.3 (<10, 통과) 이지만 ev_ebit = (5000+200)/150 ≈ 34.7 (>10, 탈락)

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_rejects_missing_52w_low():
    df = add_cheap_metrics(pd.DataFrame([_row(low_52w=np.nan)]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_rejects_missing_eps_years_ago():
    df = add_cheap_metrics(pd.DataFrame([_row(eps_years_ago=np.nan)]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_print_diagnostics_reports_missing_field_counts(capsys):
    df = add_cheap_metrics(pd.DataFrame([
        _row(),  # 모든 조건 충족
        _row(total_liabilities=np.nan),  # ev_ebit 결측 유발
        _row(eps_years_ago=np.nan),  # 3~5년전 EPS 결측
    ]))

    print_diagnostics(df)

    out = capsys.readouterr().out
    assert "total_liabilities 결측 1/3" in out
    assert "eps_years_ago 결측 1/3" in out
    assert "ev_ebit 결측 1/3" in out
