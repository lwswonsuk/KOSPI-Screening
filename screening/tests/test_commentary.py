from commentary import INVESTORS, PERSONAS, build_prompt


def test_investors_list_has_three_fixed_keys():
    assert INVESTORS == ["peter_lynch", "warren_buffett", "bill_ackman"]


def test_personas_defined_for_every_investor():
    for investor in INVESTORS:
        assert investor in PERSONAS
        assert len(PERSONAS[investor]) > 0


def test_build_prompt_includes_key_metrics():
    row = {
        "name": "테스트전자", "per": 7.3, "pbr": 0.52, "roe_3y_avg": 12.4,
        "debt_ratio": 45.1, "div_yield": 3.2, "payout_ratio_pct": 18.5, "score": 0.6123,
    }
    prompt = build_prompt(row, "warren_buffett")
    assert "테스트전자" in prompt
    assert "7.3" in prompt
    assert "45.1" in prompt


def test_build_prompt_unknown_investor_raises():
    row = {"name": "테스트전자"}
    try:
        build_prompt(row, "unknown_investor")
        assert False, "should have raised"
    except KeyError:
        pass


from commentary import generate_commentary, generate_all_commentary


class _RaisingClient:
    class messages:
        @staticmethod
        def create(**kwargs):
            raise RuntimeError("네트워크 오류 시뮬레이션")


def test_generate_commentary_returns_none_on_failure():
    row = {"name": "테스트전자", "per": 7.3}
    result = generate_commentary(row, "warren_buffett", client=_RaisingClient())
    assert result is None


class _TextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_TextBlock(text)]


class _FakeClient:
    class messages:
        @staticmethod
        def create(**kwargs):
            return _FakeResponse("이 종목은 훌륭한 성장주입니다.")


def test_generate_commentary_returns_text_on_success():
    row = {"name": "테스트전자", "per": 7.3}
    result = generate_commentary(row, "peter_lynch", client=_FakeClient())
    assert result == "이 종목은 훌륭한 성장주입니다."


def test_generate_all_commentary_skips_when_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    records = [{"stock_code": "005930", "name": "테스트전자", "per": 7.3}]
    result = generate_all_commentary(records)
    assert result == {"005930": {"peter_lynch": None, "warren_buffett": None, "bill_ackman": None}}


def test_generate_all_commentary_returns_all_none_when_client_construction_fails(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")

    import anthropic

    def _raise(*args, **kwargs):
        raise RuntimeError("클라이언트 초기화 실패 시뮬레이션")

    monkeypatch.setattr(anthropic, "Anthropic", _raise)

    records = [{"stock_code": "005930", "name": "테스트전자", "per": 7.3}]
    result = generate_all_commentary(records)
    assert result == {"005930": {"peter_lynch": None, "warren_buffett": None, "bill_ackman": None}}
