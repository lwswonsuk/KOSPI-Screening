"""
commentary.py — 투자자별(Peter Lynch / Warren Buffett / Bill Ackman) 종목 코멘트 생성
================================================================
매일 스크리닝 파이프라인이 상위 50종목을 확정한 직후 호출된다. Claude Haiku 4.5로
종목당 3명 × 50종목 = 150회 호출하며, 실패한 조합은 None으로 남기고 전체 파이프라인은
계속 진행한다. ANTHROPIC_API_KEY가 없으면 전체 생성 단계를 건너뛴다.
"""

from __future__ import annotations

import os

INVESTORS: list[str] = ["peter_lynch", "warren_buffett", "bill_ackman"]

PERSONAS: dict[str, str] = {
    "peter_lynch": (
        "당신은 Peter Lynch입니다. 성장주 발굴과 PEG 비율, 일상에서 발견하는 투자 아이디어를 "
        "중시하며, 이해하기 쉬운 비즈니스와 꾸준한 이익 성장을 선호합니다."
    ),
    "warren_buffett": (
        "당신은 Warren Buffett입니다. 안전마진, 우량한 비즈니스의 장기 보유, 낮은 부채비율과 "
        "꾸준한 ROE를 중시하며, 가격보다 가치를 먼저 봅니다."
    ),
    "bill_ackman": (
        "당신은 Bill Ackman입니다. 행동주의 투자자로서 명확한 촉매(catalyst)와 확신도 높은 "
        "소수 종목 집중 투자를 선호하며, 저평가된 이유와 반전 가능성을 날카롭게 짚습니다."
    ),
}

_METRIC_LABELS = {
    "per": "PER", "pbr": "PBR", "roe_3y_avg": "ROE(3년평균%)",
    "debt_ratio": "부채비율(%)", "div_yield": "시가배당수익률(%)",
    "payout_ratio_pct": "배당성향(%)", "score": "종합점수",
}


def build_prompt(row: dict, investor: str) -> str:
    """종목 지표 딕셔너리와 투자자 키로 사용자 프롬프트 문자열을 조립한다.
    investor가 PERSONAS/INVESTORS에 없으면 KeyError."""
    if investor not in INVESTORS:
        raise KeyError(f"알 수 없는 투자자: {investor}")

    name = row.get("name", "이 종목")
    lines = [f"종목명: {name}"]
    for key, label in _METRIC_LABELS.items():
        if key in row and row[key] is not None:
            lines.append(f"{label}: {row[key]}")
    metrics_block = "\n".join(lines)

    return (
        f"다음은 한 상장 종목의 재무 지표입니다.\n\n{metrics_block}\n\n"
        "이 지표들을 근거로, 당신의 투자 철학 관점에서 이 종목을 3~4문장으로 평가해주세요. "
        "숫자를 인용하며 구체적으로 설명하고, 매수/매도를 직접 권유하지는 마세요."
    )


def generate_commentary(row: dict, investor: str, client=None) -> str | None:
    """단일 종목·투자자 조합에 대해 Claude Haiku 4.5로 코멘트를 생성한다.
    실패(네트워크 오류, API 오류 등) 시 예외를 삼키고 None을 반환한다.
    client를 주입하면(테스트용) 그 client를 사용하고, 없으면 anthropic.Anthropic()을 새로 만든다."""
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()

        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=400,
            system=PERSONAS[investor],
            messages=[{"role": "user", "content": build_prompt(row, investor)}],
        )
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text.strip()
        return None
    except Exception as e:
        print(f"  [WARN] 코멘트 생성 실패 ({row.get('name', '?')} / {investor}): {e}")
        return None


def generate_all_commentary(records: list[dict]) -> dict[str, dict[str, str | None]]:
    """상위 종목 레코드 리스트(각 dict는 최소 stock_code, name, per, pbr, ... 포함)를 받아
    종목코드별로 3명 투자자의 코멘트를 생성한다. ANTHROPIC_API_KEY가 없으면 전체를 건너뛰고
    모든 값을 None으로 채운다."""
    result: dict[str, dict[str, str | None]] = {}

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[commentary] ANTHROPIC_API_KEY 없음 — 코멘트 생성을 건너뜁니다.")
        for rec in records:
            result[rec["stock_code"]] = {investor: None for investor in INVESTORS}
        return result

    try:
        import anthropic
        client = anthropic.Anthropic()
    except Exception as e:
        print(f"[commentary] anthropic 클라이언트 초기화 실패, 코멘트 생성을 건너뜁니다: {e}")
        for rec in records:
            result[rec["stock_code"]] = {investor: None for investor in INVESTORS}
        return result

    total = len(records) * len(INVESTORS)
    done = 0
    for rec in records:
        code = rec["stock_code"]
        result[code] = {}
        for investor in INVESTORS:
            result[code][investor] = generate_commentary(rec, investor, client=client)
            done += 1
            if done % 30 == 0:
                print(f"  [commentary] 진행 {done}/{total}")

    print(f"[commentary] 코멘트 생성 완료: {len(records)}종목 × {len(INVESTORS)}명")
    return result
