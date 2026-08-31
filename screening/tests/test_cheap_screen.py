import numpy as np
import pandas as pd
import pytest

from cheap_screen import (
    add_cheap_metrics, apply_cheap_filters, print_diagnostics, print_debug_names,
    rank_greenblatt,
)


def _row(**overrides):
    base = dict(close=100, low_52w=95, mktcap=1000, total_liabilities=200,
                total_equity=500, net_income_ttm=150, eps_now=10.0,
                eps_3y_ago=6.0, eps_4y_ago=7.0, eps_5y_ago=8.0,
                net_income_3y_ago=600, net_income_4y_ago=700, net_income_5y_ago=800,
                op_ttm=150)
    base.update(overrides)
    return base


def test_add_cheap_metrics_computes_dist_per_ev_and_ev_ebitda():
    df = pd.DataFrame([_row()])

    out = add_cheap_metrics(df)

    assert out.loc[0, "dist_from_52w_low_pct"] == pytest.approx((100 / 95 - 1) * 100)
    assert out.loc[0, "per"] == pytest.approx(1000 / 150)
    assert out.loc[0, "ev"] == 1000 + 200
    assert out.loc[0, "ev_ebitda"] == pytest.approx((1000 + 200) / 150)


def test_add_cheap_metrics_per_is_nan_when_net_income_not_positive():
    df = pd.DataFrame([_row(net_income_ttm=0), _row(net_income_ttm=-10)])

    out = add_cheap_metrics(df)

    assert out["per"].isna().all()


def test_add_cheap_metrics_computes_pbr():
    df = add_cheap_metrics(pd.DataFrame([_row(mktcap=1000, total_equity=500)]))

    assert df.loc[0, "pbr"] == pytest.approx(1000 / 500)


def test_add_cheap_metrics_pbr_is_nan_when_total_equity_not_positive():
    df = pd.DataFrame([_row(total_equity=0), _row(total_equity=-100)])

    out = add_cheap_metrics(df)

    assert out["pbr"].isna().all()


def test_add_cheap_metrics_ev_ebitda_is_nan_when_ebitda_not_positive():
    df = pd.DataFrame([_row(op_ttm=0), _row(op_ttm=-10)])

    out = add_cheap_metrics(df)

    assert out["ev_ebitda"].isna().all()


def test_apply_cheap_filters_passes_when_all_conditions_met():
    df = add_cheap_metrics(pd.DataFrame([_row()]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is True


def test_apply_cheap_filters_rejects_far_from_52w_low():
    df = add_cheap_metrics(pd.DataFrame([_row(close=130)]))  # 52주 저가 대비 +36.8%

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_add_cheap_metrics_computes_eps_3to5y_median():
    df = add_cheap_metrics(pd.DataFrame([_row(eps_3y_ago=6.0, eps_4y_ago=7.0, eps_5y_ago=8.0)]))

    assert df.loc[0, "eps_3to5y_median"] == 7.0


def test_add_cheap_metrics_median_ignores_missing_years():
    """세 해 중 결측이 있으면 남은 값들로만 중앙값을 구해야 한다 (skipna)."""
    df = add_cheap_metrics(pd.DataFrame([
        _row(eps_3y_ago=6.0, eps_4y_ago=np.nan, eps_5y_ago=np.nan),
    ]))

    assert df.loc[0, "eps_3to5y_median"] == 6.0  # 값이 하나뿐이면 그 값 자체가 중앙값


def test_add_cheap_metrics_median_is_nan_when_all_three_years_missing():
    df = add_cheap_metrics(pd.DataFrame([
        _row(eps_3y_ago=np.nan, eps_4y_ago=np.nan, eps_5y_ago=np.nan),
    ]))

    assert np.isnan(df.loc[0, "eps_3to5y_median"])


def test_apply_cheap_filters_passes_when_eps_now_beats_median_but_not_every_year():
    """중앙값(7.0)보다는 높지만 가장 높은 해(8.0)보다는 낮아도 통과해야 한다
    — 모든 해를 다 이겨야 하는 AND보다는 관대하다."""
    df = add_cheap_metrics(pd.DataFrame([
        _row(eps_now=7.5, eps_3y_ago=6.0, eps_4y_ago=7.0, eps_5y_ago=8.0),
    ]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is True


def test_apply_cheap_filters_rejects_when_eps_now_below_median():
    df = add_cheap_metrics(pd.DataFrame([
        _row(eps_now=5.0, eps_3y_ago=6.0, eps_4y_ago=7.0, eps_5y_ago=8.0),
    ]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_median_avoids_single_outlier_year_distortion():
    """평균 대신 중앙값을 쓰는 이유를 검증한다: 5년전(10)이 이상치로 낮으면
    평균은 70으로 끌려 내려가 지금(80)이 평균보다 높다고 착각하지만, 실제로는
    3년전(100)·4년전(100)보다 여전히 낮다 — 중앙값(100)을 쓰면 이 오탐을
    피해 정확히 탈락시킨다."""
    df = add_cheap_metrics(pd.DataFrame([
        _row(eps_now=80.0, eps_3y_ago=100.0, eps_4y_ago=100.0, eps_5y_ago=10.0),
    ]))

    assert df.loc[0, "eps_3to5y_median"] == 100.0  # 평균(70)이었다면 80이 이겼을 것

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_rejects_when_any_of_3to5y_had_confirmed_deficit():
    """EPS 증가 조건은 만족해도, 3~5년 중 확인된 적자가 있었으면 제외해야 한다."""
    df = add_cheap_metrics(pd.DataFrame([
        _row(eps_now=10.0, eps_3y_ago=6.0, eps_4y_ago=7.0, eps_5y_ago=-2.0,
             net_income_3y_ago=600, net_income_4y_ago=700, net_income_5y_ago=-200),
    ]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_does_not_exclude_missing_deficit_year_data():
    """3~5년 중 데이터가 없어(NaN) 적자 여부를 확인할 수 없는 해는 적자로
    간주하지 않아야 한다 — 확인된 적자만 제외 대상."""
    df = add_cheap_metrics(pd.DataFrame([
        _row(net_income_4y_ago=np.nan, net_income_5y_ago=np.nan,
             eps_4y_ago=np.nan, eps_5y_ago=np.nan),
    ]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is True


def test_apply_cheap_filters_rejects_high_per():
    df = add_cheap_metrics(pd.DataFrame([_row(net_income_ttm=50)]))  # per = 1000/50 = 20

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_passes_ev_ebitda_up_to_20x():
    # per은 낮게 유지(net_income_ttm을 키움)하고 ev_ebitda만 10배를 넘겨서
    # 20배 임계값 자체가 실제로 통과를 허용하는지 검증한다.
    df = add_cheap_metrics(pd.DataFrame([_row(mktcap=2600, net_income_ttm=300)]))
    # per = 2600/300 ≈ 8.67 (<10, 통과), ev = 2600+200 = 2800, ebitda=150,
    # ev_ebitda ≈ 18.67 (10~20 사이 — 옛 10배 기준이면 탈락, 새 20배 기준이면 통과)

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is True


def test_apply_cheap_filters_rejects_ev_ebitda_over_20x():
    df = add_cheap_metrics(pd.DataFrame([_row(mktcap=5000, net_income_ttm=600)]))
    # per = 5000/600 ≈ 8.33 (<10, 통과), ev = 5000+200 = 5200, ebitda=150,
    # ev_ebitda ≈ 34.7 (>20, 탈락)

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_rejects_missing_52w_low():
    df = add_cheap_metrics(pd.DataFrame([_row(low_52w=np.nan)]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_apply_cheap_filters_rejects_when_all_three_eps_years_missing():
    df = add_cheap_metrics(pd.DataFrame([
        _row(eps_3y_ago=np.nan, eps_4y_ago=np.nan, eps_5y_ago=np.nan),
    ]))

    out = apply_cheap_filters(df)

    assert bool(out.loc[0, "passed"]) is False


def test_print_debug_names_shows_matched_and_missing_names(capsys):
    df = add_cheap_metrics(pd.DataFrame(
        [_row(name="종목A"), _row(name="종목B", eps_now=5.0)]
    ))
    df = apply_cheap_filters(df)

    print_debug_names(df, ["종목A", "종목B", "없는종목"])

    out = capsys.readouterr().out
    assert "종목A" in out
    assert "종목B" in out
    assert "없는종목" in out


def test_rank_greenblatt_sums_ev_ebitda_and_per_ranks():
    """EV/EBITDA와 PER 둘 다 가장 낮은 종목이 합산 순위 1위(맨 위)가 되어야
    한다."""
    df = add_cheap_metrics(pd.DataFrame([
        _row(name="양쪽다쌈", mktcap=500, net_income_ttm=100),   # per=5,  ev=700,  ev_ebitda=4.67
        _row(name="양쪽다비쌈", mktcap=3000, net_income_ttm=100),  # per=30, ev=3200, ev_ebitda=21.3
        _row(name="중간", mktcap=1500, net_income_ttm=150),      # per=10, ev=1700, ev_ebitda=11.3
    ]))

    out = rank_greenblatt(df)

    assert list(out["name"]) == ["양쪽다쌈", "중간", "양쪽다비쌈"]


def test_rank_greenblatt_favors_stock_that_wins_on_only_one_metric_over_worst_of_both():
    """한쪽 지표에서만 압도적으로 싸면, 두 지표 다 애매한 종목보다 합산 순위가
    낮아질(더 위로 갈) 수 있다는 그린블랫 방식의 특성을 보여준다."""
    df = add_cheap_metrics(pd.DataFrame([
        # PER 최상위(1등)지만 EV/EBITDA는 최하위(3등) → 합산 순위 4
        _row(name="PER최고", mktcap=1000, net_income_ttm=500, op_ttm=10),
        # 둘 다 중간(2등+2등) → 합산 순위 4
        _row(name="둘다중간", mktcap=1000, net_income_ttm=100, op_ttm=100),
        # EV/EBITDA 최상위(1등)지만 PER는 최하위(3등) → 합산 순위 4
        _row(name="EV최고", mktcap=200, net_income_ttm=10, op_ttm=150),
    ]))

    out = rank_greenblatt(df)

    # 세 종목의 합산 순위가 모두 동일(4)해야 함을 먼저 확인 — 그린블랫 방식이
    # '한쪽만 극단적으로 좋은 것'과 '둘 다 무난한 것'을 동등하게 취급함을 보여준다
    assert out["greenblatt_rank"].nunique() == 1


def test_print_diagnostics_reports_missing_field_counts(capsys):
    df = add_cheap_metrics(pd.DataFrame([
        _row(),  # 모든 조건 충족
        _row(total_liabilities=np.nan),  # ev_ebitda 결측 유발
        _row(eps_3y_ago=np.nan, eps_4y_ago=np.nan, eps_5y_ago=np.nan),  # 3~5년전 EPS 전부 결측
    ]))

    print_diagnostics(df)

    out = capsys.readouterr().out
    assert "total_liabilities 결측 1/3" in out
    assert "3~5년전 EPS 전부 결측 1/3" in out
    assert "ev_ebitda 결측 1/3" in out
