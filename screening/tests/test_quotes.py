from datetime import date

from quotes import QUOTES, pick_quote_for_week


def test_quote_count_is_eleven():
    assert len(QUOTES) == 11


def test_same_iso_week_returns_same_quote():
    mon = date(2026, 8, 10)   # 2026-W33 월요일
    fri = date(2026, 8, 14)   # 같은 주 금요일
    assert pick_quote_for_week(mon) == pick_quote_for_week(fri)


def test_different_iso_week_can_return_different_quote():
    week33 = pick_quote_for_week(date(2026, 8, 10))
    week34 = pick_quote_for_week(date(2026, 8, 17))
    # 11개 명언이므로 인접 주는 대부분 다르지만 100% 보장은 아님 — 인덱스 로직 자체를 검증
    idx33 = (2026 * 53 + 33) % len(QUOTES)
    idx34 = (2026 * 53 + 34) % len(QUOTES)
    assert idx33 != idx34
    assert week33 == QUOTES[idx33]


def test_returns_text_and_author_keys():
    q = pick_quote_for_week(date(2026, 1, 1))
    assert set(q.keys()) == {"text", "author"}
