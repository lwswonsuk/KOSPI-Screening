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


_VALID_JSON = (
    '{"business": "반도체를 설계·제조한다.", "sector": "반도체", '
    '"products": "메모리 반도체", "competitors": ["경쟁사A", "경쟁사B"]}'
)
_VALID_RESULT = {
    "business": "반도체를 설계·제조한다.",
    "sector": "반도체",
    "products": "메모리 반도체",
    "competitors": ["경쟁사A", "경쟁사B"],
}


def test_generate_profile_returns_dict_on_valid_json():
    row = {"name": "테스트전자", "per": 7.3}
    result = generate_profile(row, client=_FakeClient(_VALID_JSON))
    assert result == _VALID_RESULT


def test_generate_profile_returns_none_on_malformed_json():
    row = {"name": "테스트전자", "per": 7.3}
    result = generate_profile(row, client=_FakeClient("이건 JSON이 아닙니다"))
    assert result is None


def test_generate_profile_returns_none_on_missing_field():
    row = {"name": "테스트전자", "per": 7.3}
    incomplete_json = '{"business": "설명", "sector": "반도체", "products": "메모리"}'
    result = generate_profile(row, client=_FakeClient(incomplete_json))
    assert result is None


def test_generate_profile_returns_none_when_competitors_is_a_string_not_a_list():
    row = {"name": "테스트전자", "per": 7.3}
    string_competitors_json = (
        '{"business": "반도체를 설계·제조한다.", "sector": "반도체", '
        '"products": "메모리 반도체", "competitors": "경쟁사A, 경쟁사B"}'
    )
    result = generate_profile(row, client=_FakeClient(string_competitors_json))
    assert result is None


def test_generate_profile_returns_none_when_competitors_list_is_empty():
    row = {"name": "테스트전자", "per": 7.3}
    empty_list_json = (
        '{"business": "반도체를 설계·제조한다.", "sector": "반도체", '
        '"products": "메모리 반도체", "competitors": []}'
    )
    result = generate_profile(row, client=_FakeClient(empty_list_json))
    assert result is None


def test_generate_profile_strips_markdown_code_fence():
    row = {"name": "테스트전자", "per": 7.3}
    fenced_json = f"```json\n{_VALID_JSON}\n```"
    result = generate_profile(row, client=_FakeClient(fenced_json))
    assert result == _VALID_RESULT


class _FlakyThenSucceedsClient:
    """첫 호출은 실패하고 두 번째 호출부터 성공하는 클라이언트 — 재시도 로직 검증용."""

    def __init__(self, text):
        self._text = text
        self.call_count = 0
        self.messages = self

    def create(self, **kwargs):
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("일시적 오류 시뮬레이션")
        return _FakeResponse(self._text)


def test_generate_profile_retries_once_after_transient_failure():
    row = {"name": "테스트전자", "per": 7.3}
    client = _FlakyThenSucceedsClient(_VALID_JSON)
    result = generate_profile(row, client=client)
    assert result == _VALID_RESULT
    assert client.call_count == 2


class _AlwaysFailingClient:
    def __init__(self):
        self.call_count = 0
        self.messages = self

    def create(self, **kwargs):
        self.call_count += 1
        raise RuntimeError("영구 오류 시뮬레이션")


def test_generate_profile_gives_up_after_max_attempts():
    row = {"name": "테스트전자", "per": 7.3}
    client = _AlwaysFailingClient()
    result = generate_profile(row, client=client, max_attempts=2)
    assert result is None
    assert client.call_count == 2


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
        "products": "캐시된 상품", "competitors": ["캐시된 경쟁사A", "캐시된 경쟁사B"],
    }
    cache = load_cache(cache_path)
    put(cache, "005930", "테스트전자", cached_profile)
    save_cache(cache, cache_path)

    records = [{"stock_code": "005930", "name": "테스트전자", "per": 7.3}]
    result = generate_all_profiles(records, cache_path=cache_path)

    assert result == {"005930": cached_profile}


def test_generate_all_profiles_ignores_cache_entry_with_old_string_competitors(monkeypatch, tmp_path):
    """예전(문자열) 형식의 캐시 항목은 새 형식 검증에 걸려 캐시 미스로 취급되고,
    API를 다시 호출해 새 형식(리스트)으로 갱신되어야 한다."""
    from profile_cache import load_cache, save_cache

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda: _FakeClient(_VALID_JSON))

    cache_path = tmp_path / "profile_cache.json"
    cache = load_cache(cache_path)
    cache["005930"] = {
        "name": "테스트전자",
        "profile": {
            "business": "낡은 형식", "sector": "반도체",
            "products": "낡은 상품", "competitors": "낡은 경쟁사A, 낡은 경쟁사B",
        },
        "generated_at": "2026-08-14T00:00:00+00:00",
    }
    save_cache(cache, cache_path)

    records = [{"stock_code": "005930", "name": "테스트전자", "per": 7.3}]
    result = generate_all_profiles(records, cache_path=cache_path)

    assert result == {"005930": _VALID_RESULT}
    assert isinstance(result["005930"]["competitors"], list)


def test_generate_all_profiles_calls_api_and_writes_cache_when_no_entry(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda: _FakeClient(_VALID_JSON))

    cache_path = tmp_path / "profile_cache.json"
    records = [{"stock_code": "005930", "name": "테스트전자", "per": 7.3}]
    result = generate_all_profiles(records, cache_path=cache_path)

    assert result == {"005930": _VALID_RESULT}

    from profile_cache import get_fresh, load_cache
    saved_cache = load_cache(cache_path)
    assert get_fresh(saved_cache, "005930", "테스트전자") == _VALID_RESULT


def test_generate_all_profiles_calls_api_when_cache_entry_is_stale(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda: _FakeClient(_VALID_JSON))

    cache_path = tmp_path / "profile_cache.json"
    stale_at = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        '{"005930": {"name": "테스트전자", "profile": {"business": "낡은 내용", '
        '"sector": "반도체", "products": "낡은 상품", "competitors": ["낡은 경쟁사"]}, '
        f'"generated_at": "{stale_at}"}}',
        encoding="utf-8",
    )

    records = [{"stock_code": "005930", "name": "테스트전자", "per": 7.3}]
    result = generate_all_profiles(records, cache_path=cache_path)

    assert result["005930"] == _VALID_RESULT


class _PerStockClient:
    """종목명별로 다른 응답을 반환하는 클라이언트 — 병렬 실행 시 각 종목이 올바른
    프로필로 매칭되는지 검증용. 프롬프트 문자열에서 종목명을 찾아 대응하는 JSON을 반환."""

    def __init__(self, name_to_json: dict):
        self._name_to_json = name_to_json
        self.messages = self

    def create(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        for name, payload in self._name_to_json.items():
            if f"종목명: {name}" in prompt:
                return _FakeResponse(payload)
        raise AssertionError(f"알 수 없는 프롬프트: {prompt}")


def test_generate_all_profiles_processes_multiple_records_concurrently(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    import anthropic

    name_to_json = {
        "테스트전자": _VALID_JSON,
        "테스트금융": (
            '{"business": "금융지주회사다.", "sector": "금융", '
            '"products": "예금, 대출", "competitors": ["경쟁사X", "경쟁사Y"]}'
        ),
    }
    monkeypatch.setattr(anthropic, "Anthropic", lambda: _PerStockClient(name_to_json))

    cache_path = tmp_path / "profile_cache.json"
    records = [
        {"stock_code": "005930", "name": "테스트전자", "per": 7.3},
        {"stock_code": "005380", "name": "테스트금융", "per": 5.0},
    ]
    result = generate_all_profiles(records, cache_path=cache_path)

    assert result["005930"] == _VALID_RESULT
    assert result["005380"] == {
        "business": "금융지주회사다.", "sector": "금융",
        "products": "예금, 대출", "competitors": ["경쟁사X", "경쟁사Y"],
    }
