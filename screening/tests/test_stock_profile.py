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
