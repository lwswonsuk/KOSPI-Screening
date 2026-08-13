import pandas as pd

from ws_alpha import score_payout


def test_lower_payout_ratio_scores_higher_on_s_payout():
    """score_payout()은 '배당성향이 낮을수록(=여력이 많을수록) 우대'하는 로직이다.
    payout_ratio는 load_real()/make_demo() 양쪽 모두 fraction 단위(0.05 = 5%)로
    맞춰져 있어야 하며, score_payout() 내부의 room 임계값(0.50)도 같은 단위를 전제한다.
    이 테스트는 5% 배당성향 종목이 40% 배당성향 종목보다 s_payout 점수가 높게
    나오는지를 확인해, payout_ratio 단위 불일치로 인한 회귀(예: percent 값이 그대로
    들어와 모든 실지급 종목의 room이 0으로 클립되는 버그)를 잡는다."""
    df = pd.DataFrame(
        {
            "payout_ratio": [0.05, 0.40],       # 5%, 40% (fraction 단위)
            "net_cash_to_mktcap": [0.10, 0.10],
            "roe_3y_avg": [10.0, 10.0],
            "treasury_ratio": [0.02, 0.02],
        },
        index=["low_payout", "high_payout"],
    )

    scores = score_payout(df)

    assert scores["low_payout"] > scores["high_payout"]
