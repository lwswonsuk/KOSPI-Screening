from datetime import datetime, timedelta, timezone

from profile_cache import get_fresh, load_cache, put, save_cache


def test_load_cache_missing_file_returns_empty_dict(tmp_path):
    result = load_cache(tmp_path / "nope" / "profile_cache.json")
    assert result == {}


def test_load_cache_corrupted_file_returns_empty_dict(tmp_path):
    path = tmp_path / "profile_cache.json"
    path.write_text("이건 JSON이 아닙니다", encoding="utf-8")
    result = load_cache(path)
    assert result == {}


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "sub" / "profile_cache.json"
    cache = {"005930": {"name": "테스트전자", "profile": {"business": "..."}, "generated_at": "2026-08-14T00:00:00+00:00"}}
    save_cache(cache, path)
    assert load_cache(path) == cache


def test_get_fresh_returns_none_when_missing():
    assert get_fresh({}, "005930", "테스트전자") is None


def test_get_fresh_returns_none_when_name_mismatch():
    cache = {"005930": {"name": "다른회사", "profile": {"business": "x"}, "generated_at": _now_iso()}}
    assert get_fresh(cache, "005930", "테스트전자") is None


def test_get_fresh_returns_profile_when_within_max_age():
    profile = {"business": "x", "sector": "y", "products": "z", "competitors": "w"}
    cache = {"005930": {"name": "테스트전자", "profile": profile, "generated_at": _now_iso()}}
    assert get_fresh(cache, "005930", "테스트전자", max_age_days=90) == profile


def test_get_fresh_returns_none_when_stale():
    old = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
    cache = {"005930": {"name": "테스트전자", "profile": {"business": "x"}, "generated_at": old}}
    assert get_fresh(cache, "005930", "테스트전자", max_age_days=90) is None


def test_get_fresh_returns_none_when_generated_at_malformed():
    cache = {"005930": {"name": "테스트전자", "profile": {"business": "x"}, "generated_at": "not-a-date"}}
    assert get_fresh(cache, "005930", "테스트전자") is None


def test_put_adds_entry_with_name_profile_and_timestamp():
    cache = {}
    profile = {"business": "x", "sector": "y", "products": "z", "competitors": "w"}
    put(cache, "005930", "테스트전자", profile)
    assert cache["005930"]["name"] == "테스트전자"
    assert cache["005930"]["profile"] == profile
    assert "generated_at" in cache["005930"]
    assert get_fresh(cache, "005930", "테스트전자") == profile


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
