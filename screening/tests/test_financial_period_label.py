from data_pipeline import auto_ttm_params, format_financial_period_label


def test_matches_current_auto_ttm_params():
    annual_year, ttm_year, ttm_quarter = auto_ttm_params()
    label = format_financial_period_label(annual_year)
    quarter_label = {"Q1": "1분기", "H1": "2분기", "Q3": "3분기", "FY": "연간"}[ttm_quarter]
    assert label == f"{ttm_year}년 {quarter_label}"


def test_falls_back_to_year_only_when_bsns_year_mismatches_auto_detection():
    annual_year, _, _ = auto_ttm_params()
    mismatched_year = annual_year - 1
    assert format_financial_period_label(mismatched_year) == f"{mismatched_year}년"
