from stock_profile import build_prompt, PROFILE_FIELDS, SYSTEM_PROMPT, generate_profile, generate_all_profiles


def test_profile_fields_has_four_keys():
    assert PROFILE_FIELDS == ["business", "sector", "products", "competitors"]


def test_system_prompt_defined():
    assert len(SYSTEM_PROMPT) > 0


def test_build_prompt_includes_stock_name():
    row = {"name": "테스트전자", "per": 7.3, "pbr": 0.52}
    prompt = build_prompt(row)
    assert "테스트전자" in prompt
    assert "7.3" in prompt


def test_build_prompt_works_without_optional_metrics():
    row = {"name": "테스트전자"}
    prompt = build_prompt(row)
    assert "테스트전자" in prompt


class _RaisingClient:
    class messages:
        @staticmethod
        def create(**kwargs):
            raise RuntimeError("네트워크 오류 시뮬레이션")


def test_generate_profile_returns_none_on_api_failure():
    row = {"name": "테스트전자", "per": 7.3}
    result = generate_profile(row, client=_RaisingClient())
    assert result is None


class _TextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_TextBlock(text)]


class _FakeClient:
    def __init__(self, text):
        self._text = text
        self.messages = self._Messages(text)

    class _Messages:
        def __init__(self, text):
            self._text = text

        def create(self, **kwargs):
            return _FakeResponse(self._text)


def test_generate_profile_returns_dict_on_valid_json():
    row = {"name": "테스트전자", "per": 7.3}
    valid_json = (
        '{"business": "반도체를 설계·제조한다.", "sector": "반도체", '
        '"products": "메모리 반도체", "competitors": "경쟁사A, 경쟁사B"}'
    )
    result = generate_profile(row, client=_FakeClient(valid_json))
    assert result == {
        "business": "반도체를 설계·제조한다.",
        "sector": "반도체",
        "products": "메모리 반도체",
        "competitors": "경쟁사A, 경쟁사B",
    }


def test_generate_profile_returns_none_on_malformed_json():
    row = {"name": "테스트전자", "per": 7.3}
    result = generate_profile(row, client=_FakeClient("이건 JSON이 아닙니다"))
    assert result is None


def test_generate_profile_returns_none_on_missing_field():
    row = {"name": "테스트전자", "per": 7.3}
    incomplete_json = '{"business": "설명", "sector": "반도체", "products": "메모리"}'
    result = generate_profile(row, client=_FakeClient(incomplete_json))
    assert result is None


def test_generate_profile_returns_none_when_field_is_not_string():
    row = {"name": "테스트전자", "per": 7.3}
    non_string_field_json = (
        '{"business": "반도체를 설계·제조한다.", "sector": "반도체", '
        '"products": "메모리 반도체", "competitors": ["경쟁사A", "경쟁사B"]}'
    )
    result = generate_profile(row, client=_FakeClient(non_string_field_json))
    assert result is None


def test_generate_profile_strips_markdown_code_fence():
    row = {"name": "테스트전자", "per": 7.3}
    fenced_json = (
        "```json\n"
        '{"business": "반도체를 설계·제조한다.", "sector": "반도체", '
        '"products": "메모리 반도체", "competitors": "경쟁사A, 경쟁사B"}\n'
        "```"
    )
    result = generate_profile(row, client=_FakeClient(fenced_json))
    assert result == {
        "business": "반도체를 설계·제조한다.",
        "sector": "반도체",
        "products": "메모리 반도체",
        "competitors": "경쟁사A, 경쟁사B",
    }


def test_generate_all_profiles_skips_when_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    records = [{"stock_code": "005930", "name": "테스트전자", "per": 7.3}]
    result = generate_all_profiles(records)
    assert result == {"005930": None}


def test_generate_all_profiles_returns_none_when_client_construction_fails(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")

    import anthropic

    def _raise(*args, **kwargs):
        raise RuntimeError("클라이언트 초기화 실패 시뮬레이션")

    monkeypatch.setattr(anthropic, "Anthropic", _raise)

    records = [{"stock_code": "005930", "name": "테스트전자", "per": 7.3}]
    result = generate_all_profiles(records)
    assert result == {"005930": None}


class _RaisingIfCalledClient:
    """호출되면 실패하는 클라이언트 — 캐시 히트 시 API가 절대 호출되지 않는지 검증용."""

    class messages:
        @staticmethod
        def create(**kwargs):
            raise AssertionError("캐시가 신선한데도 API가 호출됨")


def test_generate_all_profiles_reuses_fresh_cache_without_calling_api(monkeypatch, tmp_path):
    from profile_cache import load_cache, put, save_cache

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda: _RaisingIfCalledClient())

    cache_path = tmp_path / "profile_cache.json"
    cached_profile = {
        "business": "캐시된 사업 내용", "sector": "반도체",
        "products": "캐시된 상품", "competitors": "캐시된 경쟁사",
    }
    cache = load_cache(cache_path)
    put(cache, "005930", "테스트전자", cached_profile)
    save_cache(cache, cache_path)

    records = [{"stock_code": "005930", "name": "테스트전자", "per": 7.3}]
    result = generate_all_profiles(records, cache_path=cache_path)

    assert result == {"005930": cached_profile}


def test_generate_all_profiles_calls_api_and_writes_cache_when_no_entry(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    import anthropic
    valid_json = (
        '{"business": "신규 생성된 사업 내용", "sector": "반도체", '
        '"products": "신규 상품", "competitors": "신규 경쟁사"}'
    )
    monkeypatch.setattr(anthropic, "Anthropic", lambda: _FakeClient(valid_json))

    cache_path = tmp_path / "profile_cache.json"
    records = [{"stock_code": "005930", "name": "테스트전자", "per": 7.3}]
    result = generate_all_profiles(records, cache_path=cache_path)

    expected = {
        "business": "신규 생성된 사업 내용", "sector": "반도체",
        "products": "신규 상품", "competitors": "신규 경쟁사",
    }
    assert result == {"005930": expected}

    from profile_cache import get_fresh, load_cache
    saved_cache = load_cache(cache_path)
    assert get_fresh(saved_cache, "005930", "테스트전자") == expected


def test_generate_all_profiles_calls_api_when_cache_entry_is_stale(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    import anthropic
    fresh_json = (
        '{"business": "새로 갱신된 사업 내용", "sector": "반도체", '
        '"products": "새 상품", "competitors": "새 경쟁사"}'
    )
    monkeypatch.setattr(anthropic, "Anthropic", lambda: _FakeClient(fresh_json))

    cache_path = tmp_path / "profile_cache.json"
    stale_at = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        '{"005930": {"name": "테스트전자", "profile": {"business": "낡은 내용", '
        '"sector": "반도체", "products": "낡은 상품", "competitors": "낡은 경쟁사"}, '
        f'"generated_at": "{stale_at}"}}',
        encoding="utf-8",
    )

    records = [{"stock_code": "005930", "name": "테스트전자", "per": 7.3}]
    result = generate_all_profiles(records, cache_path=cache_path)

    assert result["005930"]["business"] == "새로 갱신된 사업 내용"
