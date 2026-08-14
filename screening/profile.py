"""
profile.py — 종목별 프로필(사업 내용/섹터/대표 상품·브랜드/주요 경쟁사) 생성
================================================================
매일 스크리닝 파이프라인이 상위 50종목을 확정한 직후 호출된다. Claude Haiku 4.5로
종목당 1회 호출하며, 실패한 종목은 profile을 None으로 남기고 전체 파이프라인은
계속 진행한다. ANTHROPIC_API_KEY가 없으면 전체 생성 단계를 건너뛴다.
"""

from __future__ import annotations

import json
import os

PROFILE_FIELDS: list[str] = ["business", "sector", "products", "competitors"]

SYSTEM_PROMPT = (
    "당신은 한국 주식시장에 정통한 애널리스트입니다. 종목명을 보고 알고 있는 사실에 "
    "근거해 간결하게 설명합니다. 모르는 내용은 추측하지 말고 일반적인 수준에서만 "
    "설명하세요. 반드시 요청받은 JSON 형식으로만 응답하세요."
)

_METRIC_LABELS = {
    "per": "PER", "pbr": "PBR", "roe_3y_avg": "ROE(3년평균%)",
    "debt_ratio": "부채비율(%)", "div_yield": "시가배당수익률(%)",
    "payout_ratio_pct": "배당성향(%)", "score": "종합점수",
}


def build_prompt(row: dict) -> str:
    """종목 지표 딕셔너리로 사용자 프롬프트 문자열을 조립한다."""
    name = row.get("name", "이 종목")
    lines = [f"종목명: {name}"]
    for key, label in _METRIC_LABELS.items():
        if key in row and row[key] is not None:
            lines.append(f"{label}: {row[key]}")
    metrics_block = "\n".join(lines)

    return (
        f"다음은 한 상장 종목입니다.\n\n{metrics_block}\n\n"
        "이 종목에 대해 아래 JSON 형식으로만 응답해주세요. 다른 설명 문구는 포함하지 마세요.\n"
        '{"business": "사업 내용 2~3문장", "sector": "섹터/업종", '
        '"products": "대표 상품 또는 브랜드", "competitors": "주요 경쟁사 2~4곳"}'
    )


def _strip_code_fence(text: str) -> str:
    """마크다운 코드펜스(```json ... ``` 또는 ``` ... ```)로 감싸인 응답에서
    펜스를 제거한다. 펜스가 없으면 입력을 그대로 반환한다."""
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()
    return text


def generate_profile(row: dict, client=None) -> dict | None:
    """단일 종목에 대해 Claude Haiku 4.5로 프로필을 생성한다.
    실패(네트워크 오류, API 오류, JSON 파싱 실패, 필드 누락) 시 예외를 삼키고 None을 반환한다.
    client를 주입하면(테스트용) 그 client를 사용하고, 없으면 anthropic.Anthropic()을 새로 만든다."""
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()

        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_prompt(row)}],
        )
        text = None
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text = block.text.strip()
                break
        if text is None:
            return None

        text = _strip_code_fence(text)

        data = json.loads(text)
        if not all(isinstance(data.get(field), str) and data[field].strip() for field in PROFILE_FIELDS):
            return None
        return {field: data[field] for field in PROFILE_FIELDS}
    except Exception as e:
        print(f"  [WARN] 프로필 생성 실패 ({row.get('name', '?')}): {e}")
        return None


def generate_all_profiles(records: list[dict]) -> dict[str, dict | None]:
    """상위 종목 레코드 리스트(각 dict는 최소 stock_code, name, per, pbr, ... 포함)를 받아
    종목코드별로 프로필을 생성한다. ANTHROPIC_API_KEY가 없으면 전체를 건너뛰고
    모든 값을 None으로 채운다."""
    result: dict[str, dict | None] = {}

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[profile] ANTHROPIC_API_KEY 없음 — 프로필 생성을 건너뜁니다.")
        for rec in records:
            result[rec["stock_code"]] = None
        return result

    try:
        import anthropic
        client = anthropic.Anthropic()
    except Exception as e:
        print(f"[profile] anthropic 클라이언트 초기화 실패, 프로필 생성을 건너뜁니다: {e}")
        for rec in records:
            result[rec["stock_code"]] = None
        return result

    total = len(records)
    done = 0
    for rec in records:
        code = rec["stock_code"]
        result[code] = generate_profile(rec, client=client)
        done += 1
        if done % 10 == 0:
            print(f"  [profile] 진행 {done}/{total}")

    print(f"[profile] 프로필 생성 완료: {len(records)}종목")
    return result
