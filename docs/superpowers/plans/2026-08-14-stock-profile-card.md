# 종목 프로필 카드 (투자자 코멘트 교체) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 상위 50종목 모달의 투자자별(Lynch/Buffett/Ackman) 코멘트를, 사업 내용/섹터/대표 상품·브랜드/주요 경쟁사를 담은 단일 종목 프로필 카드로 교체한다.

**Architecture:** `screening/commentary.py`를 `screening/profile.py`로 교체해 종목당 1회 Claude Haiku 4.5 호출로 JSON 프로필을 생성하고, `results.json`에 `commentary` 대신 `profile` 필드로 저장한다. 프런트는 `StockCommentaryDialog.tsx`를 `StockProfileDialog.tsx`로 교체해 탭 없이 단일 카드에 4개 필드를 표시한다.

**Tech Stack:** Python(anthropic SDK, pytest), Next.js/TypeScript(React, shadcn/ui Dialog)

## Global Constraints

- `ANTHROPIC_API_KEY`가 없으면 생성 단계 전체를 건너뛰고 `profile: null`로 채운다 (기존 `commentary.py` 패턴 유지).
- 종목·API 호출 단위의 실패는 예외를 삼키고 해당 종목만 `None`, 파이프라인은 중단 없이 계속 진행한다.
- 코멘트 생성 도중 프로세스가 중단되어도 유효한 `results.json`이 남도록, 먼저 `profile: null` 초안을 저장한 뒤 생성 결과로 덮어쓰는 기존 2단계 저장 패턴을 유지한다.
- 모델은 `claude-haiku-4-5`, `max_tokens=400` 그대로 유지.
- `results.json`에 `profile` 필드가 아예 없는 구버전 데이터에서도 프런트가 깨지지 않아야 한다 (옵셔널 타입).

---

### Task 1: `screening/profile.py` 작성 (프롬프트 조립 + JSON 파싱)

**Files:**
- Create: `screening/profile.py`
- Test: `screening/tests/test_profile.py`
- Delete: `screening/commentary.py`, `screening/tests/test_commentary.py` (Task 1 마지막 단계에서 삭제)

**Interfaces:**
- Consumes: 없음 (신규 독립 모듈)
- Produces:
  - `build_prompt(row: dict) -> str` — 종목 dict를 받아 사용자 프롬프트 문자열 반환
  - `SYSTEM_PROMPT: str` — 애널리스트 페르소나 시스템 프롬프트
  - `PROFILE_FIELDS: list[str] = ["business", "sector", "products", "competitors"]`
  - `generate_profile(row: dict, client=None) -> dict | None`
  - `generate_all_profiles(records: list[dict]) -> dict[str, dict | None]`

- [ ] **Step 1: 프롬프트 조립 실패 테스트 작성**

`screening/tests/test_profile.py` 새로 작성:

```python
from profile import build_prompt, PROFILE_FIELDS, SYSTEM_PROMPT


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
```

- [ ] **Step 2: 테스트 실행 확인 (실패해야 정상)**

Run: `cd screening && python -m pytest tests/test_profile.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'profile'` (아직 `profile.py`가 없으므로)

- [ ] **Step 3: `screening/profile.py` 최소 구현 작성**

```python
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

        data = json.loads(text)
        if not all(field in data and data[field] for field in PROFILE_FIELDS):
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
```

- [ ] **Step 4: 테스트 실행 확인 (통과해야 정상)**

Run: `cd screening && python -m pytest tests/test_profile.py -v`
Expected: PASS (4개 테스트 모두)

- [ ] **Step 5: 생성/실패 처리 단위 테스트 추가**

`screening/tests/test_profile.py`에 이어서 추가:

```python
from profile import generate_profile, generate_all_profiles


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
```

- [ ] **Step 6: 테스트 실행 확인 (통과해야 정상)**

Run: `cd screening && python -m pytest tests/test_profile.py -v`
Expected: PASS (전체 테스트, 9개 이상)

- [ ] **Step 7: 기존 `commentary.py`/`test_commentary.py` 삭제**

```bash
git rm screening/commentary.py screening/tests/test_commentary.py
```

- [ ] **Step 8: 전체 스크리닝 테스트 스위트 실행 확인**

Run: `cd screening && python -m pytest -v`
Expected: PASS (기존 테스트 전부 + 신규 `test_profile.py`, `commentary` 관련 테스트는 더 이상 존재하지 않음)

- [ ] **Step 9: Commit**

```bash
git add screening/profile.py screening/tests/test_profile.py
git commit -m "feat: 투자자 코멘트 대신 종목 프로필(사업내용/섹터/상품/경쟁사) 생성 모듈 추가"
```

---

### Task 2: `screening/ws_alpha.py` — 프로필 생성 호출부 교체

**Files:**
- Modify: `screening/ws_alpha.py:32` (import), `screening/ws_alpha.py:615-633` (코멘트 생성 → 프로필 생성)

**Interfaces:**
- Consumes: `screening.profile.generate_all_profiles(records: list[dict]) -> dict[str, dict | None]` (Task 1에서 정의)
- Produces: `results.json`의 각 레코드에 `profile: dict | None` 필드 (기존 `commentary` 필드 대체)

- [ ] **Step 1: import 교체**

`screening/ws_alpha.py:32` 수정:

```python
# 기존:
from commentary import generate_all_commentary
# 변경:
from profile import generate_all_profiles
```

- [ ] **Step 2: 코멘트 생성 호출부를 프로필 생성 호출부로 교체**

`screening/ws_alpha.py:615-629` 블록을 아래로 교체:

```python
        # 프로필 생성(수 분 소요, 종목당 1회 순차 API 호출)에 앞서 profile을 전부
        # None으로 채운 "초안" 버전을 먼저 저장해 둔다. DART/KRX 스크리닝 결과는 이미
        # 확보된 상태이므로, 이후 프로필 생성 도중 외부 요인(타임아웃, OOM, kill 등)으로
        # 프로세스가 중단되더라도 profile이 비어 있을 뿐인 유효한 results.json이
        # 디스크에 남는다(둘 다 없는 것보다 낫다).
        for rec in records:
            rec["profile"] = None
        draft_payload = _build_payload(records)
        out_path.write_text(json.dumps(draft_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        profile_map = generate_all_profiles(records)
        for rec in records:
            rec["profile"] = profile_map.get(rec["stock_code"])
```

(뒤이은 `payload = _build_payload(records)` 및 저장 라인은 그대로 유지)

- [ ] **Step 3: 파이썬 문법/임포트 오류 없는지 확인**

Run: `cd screening && python -c "import ws_alpha"`
Expected: 에러 없이 종료 (import 시점에 `commentary` 모듈을 찾지 못해 나던 오류가 없어야 함)

- [ ] **Step 4: 전체 스크리닝 테스트 스위트 실행 확인**

Run: `cd screening && python -m pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add screening/ws_alpha.py
git commit -m "feat: 스크리닝 파이프라인에서 투자자 코멘트 대신 종목 프로필 생성하도록 교체"
```

---

### Task 3: `web/app/StockProfileDialog.tsx` 작성 (기존 `StockCommentaryDialog.tsx` 대체)

**Files:**
- Create: `web/app/StockProfileDialog.tsx`
- Delete: `web/app/StockCommentaryDialog.tsx`

**Interfaces:**
- Consumes: 없음 (독립 컴포넌트)
- Produces:
  - `export interface StockProfile { business: string; sector: string; products: string; competitors: string }`
  - `export default function StockProfileDialog({ open, onOpenChange, stockName, profile }: { open: boolean; onOpenChange: (open: boolean) => void; stockName: string; profile: StockProfile | null | undefined })`

- [ ] **Step 1: `web/app/StockProfileDialog.tsx` 작성**

```tsx
"use client";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export interface StockProfile {
  business: string;
  sector: string;
  products: string;
  competitors: string;
}

const PROFILE_SECTIONS: { key: keyof StockProfile; label: string }[] = [
  { key: "business", label: "사업 내용" },
  { key: "sector", label: "섹터" },
  { key: "products", label: "대표 상품·브랜드" },
  { key: "competitors", label: "주요 경쟁사" },
];

export default function StockProfileDialog({
  open,
  onOpenChange,
  stockName,
  profile,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  stockName: string;
  profile: StockProfile | null | undefined;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{stockName} — 종목 프로필</DialogTitle>
        </DialogHeader>

        <div className="mt-2 rounded-2xl rounded-tl-none bg-muted p-4 text-sm leading-relaxed">
          {profile ? (
            <div className="space-y-3">
              {PROFILE_SECTIONS.map(({ key, label }) => (
                <div key={key}>
                  <div className="font-medium text-foreground">{label}</div>
                  <div className="mt-0.5 text-muted-foreground">{profile[key]}</div>
                </div>
              ))}
            </div>
          ) : (
            "아직 분석이 준비되지 않았습니다."
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: 기존 `StockCommentaryDialog.tsx` 삭제**

```bash
git rm web/app/StockCommentaryDialog.tsx
```

(이 시점에서는 `ScreeningTable.tsx`가 아직 옛 파일을 참조하므로 빌드가 깨지는 게 정상 — Task 4에서 고침)

- [ ] **Step 3: Commit**

```bash
git add web/app/StockProfileDialog.tsx
git commit -m "feat: 투자자 탭 대신 단일 카드로 종목 프로필을 보여주는 다이얼로그 추가"
```

---

### Task 4: `ScreeningTable.tsx` / `page.tsx` — `commentary` → `profile` 교체

**Files:**
- Modify: `web/app/ScreeningTable.tsx:15,17,183-188`
- Modify: `web/app/page.tsx:14-16`

**Interfaces:**
- Consumes: `StockProfileDialog`, `StockProfile` (Task 3에서 정의)
- Produces: `ResultRow` 타입에 `profile?: StockProfile | null` 필드

- [ ] **Step 1: `web/app/ScreeningTable.tsx` import 및 타입 교체**

`web/app/ScreeningTable.tsx:15` 수정:

```tsx
// 기존:
import StockCommentaryDialog, { Commentary } from "./StockCommentaryDialog";
// 변경:
import StockProfileDialog, { StockProfile } from "./StockProfileDialog";
```

`web/app/ScreeningTable.tsx:17` 수정:

```tsx
// 기존:
type ResultRow = Record<string, string | number | null> & { commentary?: Commentary | null };
// 변경:
type ResultRow = Record<string, string | number | null> & { profile?: StockProfile | null };
```

- [ ] **Step 2: 다이얼로그 렌더링부 교체**

`web/app/ScreeningTable.tsx:183-188` 수정:

```tsx
      <StockProfileDialog
        open={dialogRow !== null}
        onOpenChange={(open) => !open && setDialogRow(null)}
        stockName={dialogRow ? String(dialogRow.name ?? "") : ""}
        profile={dialogRow?.profile}
      />
```

- [ ] **Step 3: `web/app/page.tsx`의 `ResultRow` 타입 교체**

`web/app/page.tsx:14-16` 수정:

```tsx
import { StockProfile } from "./StockProfileDialog";

type ResultRow = Record<string, string | number | null> & {
  profile?: StockProfile | null;
};
```

(`import { StockProfile } from "./StockProfileDialog";` 는 파일 상단 다른 import들 근처, `ResultRow` 타입 선언 바로 위에 추가)

- [ ] **Step 4: 빌드 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공, TypeScript 에러 없음 (특히 `commentary`/`Commentary` 참조 잔존 여부 확인)

- [ ] **Step 5: 잔존 참조 확인**

Run: `cd web && grep -rn "commentary\|Commentary" app/`
Expected: 결과 없음 (전부 `profile`/`StockProfile`로 교체 완료)

- [ ] **Step 6: Commit**

```bash
git add web/app/ScreeningTable.tsx web/app/page.tsx
git commit -m "feat: 프런트에서 투자자 코멘트 대신 종목 프로필 표시하도록 교체"
```

---

### Task 5: 더미 데이터로 로컬 동작 확인

**Files:**
- Modify (임시, 커밋 안 함): `web/data/results.json` — 로컬 확인용으로만 수정 후 `git checkout`으로 원복

**Interfaces:**
- Consumes: Task 1~4에서 완성된 전체 기능
- Produces: 없음 (검증 전용 태스크)

- [ ] **Step 1: `web/data/results.json`의 상위 몇 개 레코드에 테스트용 `profile` 값 임시 추가**

`web/data/results.json`을 열어 최상위 레코드 1개에는 `"profile": {"business": "...", "sector": "...", "products": "...", "competitors": "..."}`를, 다음 레코드 1개에는 `"profile": null`을(또는 필드 자체 생략), 이렇게 두 케이스를 확인할 수 있도록 임시로 편집한다.

- [ ] **Step 2: 개발 서버 실행 후 브라우저에서 확인**

`web` 디렉터리에서 `npm run dev`로 로컬 서버를 띄우고, 브라우저에서 종목명을 클릭해:
- `profile`이 채워진 종목: 모달에 탭 없이 사업 내용/섹터/대표 상품·브랜드/주요 경쟁사 4개 섹션이 순서대로 보이는지 확인
- `profile`이 `null`이거나 없는 종목: "아직 분석이 준비되지 않았습니다" 문구가 보이는지 확인

- [ ] **Step 3: `web/data/results.json` 원복**

```bash
git checkout -- web/data/results.json
```

- [ ] **Step 4: 원복 확인**

Run: `git status`
Expected: `web/data/results.json`에 변경 사항 없음 (clean)

(이 태스크는 검증 전용이라 커밋할 변경 사항이 없음)

---

## 영향받는 파일 요약

- `screening/profile.py` (신규, `commentary.py` 대체)
- `screening/tests/test_profile.py` (신규, `test_commentary.py` 대체)
- `screening/ws_alpha.py` (수정)
- `web/app/StockProfileDialog.tsx` (신규, `StockCommentaryDialog.tsx` 대체)
- `web/app/ScreeningTable.tsx` (수정)
- `web/app/page.tsx` (수정)
