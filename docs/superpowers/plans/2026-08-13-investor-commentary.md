# 투자자별 종목 분석 말풍선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 상위 50종목 각각에 대해 Peter Lynch·Warren Buffett·Bill Ackman 세 투자자 관점의 짧은 코멘트를
매일 스크리닝 파이프라인에서 미리 생성해 `results.json`에 저장하고, 웹사이트에서 종목명을 클릭하면
모달로 보여준다.

**Architecture:** Python 파이프라인(`ws_alpha.py`)이 top 50을 확정한 직후 Claude Haiku 4.5를 호출해
종목×투자자 150개 코멘트를 생성, `results.json`의 각 레코드에 `commentary` 객체로 포함시켜 커밋한다.
프런트는 이 정적 데이터를 그대로 렌더링만 하며 런타임에 API를 호출하지 않는다.

**Tech Stack:** Python `anthropic` SDK (Claude Haiku 4.5), Next.js 15 + React 19 + TypeScript, shadcn/ui Dialog.

## Global Constraints

- 모델은 `claude-haiku-4-5`로 고정(비용 최소화 목적, 다른 모델로 바꾸지 않는다).
- 투자자는 정확히 3명 고정: `peter_lynch`, `warren_buffett`, `bill_ackman` (영문 키, 표시명은 프런트에서 매핑).
- 종목·투자자 조합 하나가 실패해도 예외를 삼키고 해당 값만 `None`/`null`로 남기며, 전체 파이프라인은 중단하지 않는다.
- `ANTHROPIC_API_KEY` 환경변수가 없으면 전체 커멘터리 생성 단계를 건너뛰고 모든 값을 `None`으로 채운다
  (로컬 개발/테스트 환경에서 파이프라인이 죽지 않도록).
- 커멘터리는 상위 50종목(`results.json`)에만 생성한다. `filtered_full.json`(필터통과 전체)에는 포함하지 않는다
  — 비용 절감 목적.
- 새로 추가하는 프런트 코드는 기존 shadcn/ui 컴포넌트(`Dialog`, `Button`, `cn()`)를 재사용한다. 새 shadcn
  컴포넌트(Tabs 등)를 추가로 설치하지 않고, 탭 전환은 `useState` + 버튼 스타일로 직접 구현한다(불필요한
  의존성 추가 방지).

---

## 파일 구조

**신규 파일**
- `screening/commentary.py` — 페르소나 정의, 프롬프트 조립(순수 함수), Claude API 호출, 전체 생성 오케스트레이션
- `screening/tests/test_commentary.py`
- `web/app/StockCommentaryDialog.tsx` — 투자자 3명 탭 전환 모달

**수정 파일**
- `screening/ws_alpha.py` — top 50 확정 후 커멘터리 생성 호출, `export_json` 레코드에 `commentary` 필드 포함
- `screening/requirements.txt` — `anthropic` 패키지 추가
- `.github/workflows/daily-screen.yml` — 스크리닝 실행 스텝에 `ANTHROPIC_API_KEY` 환경변수 추가
- `web/app/page.tsx` — `ResultsPayload`/`ResultRow` 타입에 `commentary` 필드 반영(정의는 `ScreeningTable.tsx`와
  공유하지 않고 각자 파일에 동일한 타입을 유지하는 기존 패턴을 따름)
- `web/app/ScreeningTable.tsx` — `name` 컬럼을 클릭 가능하게 변경, `StockCommentaryDialog` 연동

---

### Task 1: 투자자 페르소나 + 프롬프트 조립 + Claude API 호출

**Files:**
- Create: `screening/commentary.py`
- Test: `screening/tests/test_commentary.py`

**Interfaces:**
- Produces: `INVESTORS: list[str]` (`["peter_lynch", "warren_buffett", "bill_ackman"]`),
  `build_prompt(row: dict, investor: str) -> str` (순수 함수),
  `generate_commentary(row: dict, investor: str, client=None) -> str | None`,
  `generate_all_commentary(records: list[dict]) -> dict[str, dict[str, str | None]]`
  (키: `stock_code` → `{"peter_lynch": ..., "warren_buffett": ..., "bill_ackman": ...}`)

- [ ] **Step 1: 페르소나·프롬프트 조립 함수의 실패하는 테스트 작성**

`screening/tests/test_commentary.py`:
```python
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
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd screening && python -m pytest tests/test_commentary.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'commentary'`

- [ ] **Step 3: 페르소나·프롬프트 조립·API 호출 함수 구현**

`screening/commentary.py`:
```python
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

    import anthropic
    client = anthropic.Anthropic()

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
```

- [ ] **Step 4: 테스트 재실행해서 통과 확인**

Run: `cd screening && python -m pytest tests/test_commentary.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: API 실패 시 None을 반환하는지 확인하는 테스트 추가 (fake client 사용)**

`screening/tests/test_commentary.py` 끝에 추가:
```python
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
```

- [ ] **Step 6: 전체 테스트 실행해서 통과 확인**

Run: `cd screening && python -m pytest tests/test_commentary.py -v`
Expected: 7 tests PASS

- [ ] **Step 7: `anthropic` 패키지를 requirements.txt에 추가**

`screening/requirements.txt`에 한 줄 추가:
```
anthropic
```

- [ ] **Step 8: 패키지 설치 후 모듈 임포트 확인**

Run: `cd screening && python -m pip install -r requirements.txt` (이미 설치되어 있으면 스킵됨),
이어서 `python -c "import commentary"` — 임포트 에러 없는지 확인.
Expected: 에러 없음.

- [ ] **Step 9: 커밋**

```bash
git add screening/commentary.py screening/tests/test_commentary.py screening/requirements.txt
git commit -m "feat: 투자자별(Lynch/Buffett/Ackman) 종목 코멘트 생성 모듈 추가"
```

---

### Task 2: ws_alpha.py에 커멘터리 생성 연동

**Files:**
- Modify: `screening/ws_alpha.py` (상단 import, `run_real()`의 `export_json` 블록)

**Interfaces:**
- Consumes: Task 1의 `generate_all_commentary(records: list[dict]) -> dict[str, dict[str, str | None]]`
- Produces: `export_json`으로 저장되는 각 레코드에 `commentary` 키 추가

- [ ] **Step 1: import 추가**

`screening/ws_alpha.py` 상단 import 블록(quotes import 근처)에 추가:
```python
from commentary import generate_all_commentary
```

- [ ] **Step 2: `export_json` 블록에서 `records`를 만든 직후 커멘터리 생성 후 병합**

`screening/ws_alpha.py:580-608`의 `if export_json:` 블록을 확인하면, `records` 리스트를 만든 다음
`payload`를 구성한다. `records` 리스트 빌드가 끝난 직후, `payload` 구성 전에 추가:

```python
    if export_json:
        import json
        from pathlib import Path as _Path

        records = []
        for code, row in top.iterrows():
            rec = {"stock_code": str(code)}
            for c in cols:
                v = row[c]
                if pd.isna(v):
                    rec[c] = None
                elif isinstance(v, (int, float, np.floating, np.integer)):
                    rec[c] = round(float(v), 4)
                else:
                    rec[c] = str(v)
            records.append(rec)

        commentary_map = generate_all_commentary(records)
        for rec in records:
            rec["commentary"] = commentary_map.get(rec["stock_code"], {
                "peter_lynch": None, "warren_buffett": None, "bill_ackman": None,
            })

        payload = {
```
(즉, 기존 `records = []` ~ `records.append(rec)` 루프는 그대로 두고, 그 다음에 `commentary_map = generate_all_commentary(records)`와
그 결과를 각 `rec`에 병합하는 for문을 추가한 뒤, 기존 `payload = {` 줄로 이어진다. `payload` 딕셔너리 내부 내용은
변경하지 않는다 — `records`가 이미 `commentary` 필드를 포함한 상태로 `"results": records`에 들어간다.)

- [ ] **Step 3: `filtered_json` 블록은 건드리지 않는다 (비용 절감 — 필터통과 전체에는 커멘터리 미포함)**

`screening/ws_alpha.py:615-644`의 `if filtered_json:` 블록은 수정하지 않는다. 이 블록은 독립적으로
`records`라는 지역 변수명을 재사용하므로(Python 함수 스코프상 `export_json` 블록의 `records`와는 다른
시점에 재할당됨), Step 2에서 추가한 `commentary` 필드가 `filtered_json` 쪽에 실수로 섞여 들어가지 않는지
Step 5에서 확인한다.

- [ ] **Step 4: 모듈 임포트 및 데모 실행으로 회귀 확인**

Run: `cd screening && python -c "import ws_alpha"` — 순환 임포트나 문법 오류 없는지 확인.
Run: `cd screening && PYTHONIOENCODING=utf-8 python ws_alpha.py --demo 2>&1 | tail -5` — 기존 데모 로직에
영향 없는지 확인(데모는 `run_real()`을 호출하지 않으므로 `generate_all_commentary`가 실행되지 않아야 함).
Expected: 데모가 기존과 동일하게 정상 출력.

- [ ] **Step 5: `filtered_json`에 `commentary`가 섞이지 않는지 코드 재확인**

`screening/ws_alpha.py`의 `if filtered_json:` 블록(약 615번째 줄 부근)을 다시 읽고, 그 블록 안의
`records = []` ~ `records.append(rec)` 루프가 Step 2에서 추가한 `commentary_map`/`rec["commentary"] = ...`
코드를 전혀 참조하지 않는지 확인한다(같은 함수 내 다른 `if` 블록이므로 변수명이 같아도 각자
독립적으로 재할당되어 문제없어야 하지만, 실수로 두 블록을 합치지 않았는지 눈으로 재확인).

- [ ] **Step 6: 커밋**

```bash
git add screening/ws_alpha.py
git commit -m "feat: 상위 50종목에 투자자별 코멘트 생성해 results.json에 포함"
```

---

### Task 3: GitHub Actions에 ANTHROPIC_API_KEY 연동

**Files:**
- Modify: `.github/workflows/daily-screen.yml`

**Interfaces:**
- Consumes: 없음(워크플로 설정 변경)

- [ ] **Step 1: 스크리닝 실행 스텝에 환경변수 추가**

`.github/workflows/daily-screen.yml:72-81`:
```yaml
      - name: 오늘자 가격 기준 스크리닝 실행 + JSON 저장
        working-directory: screening
        env:
          KRX_API_KEY: ${{ secrets.KRX_API_KEY }}
        run: |
```
를 다음으로 교체:
```yaml
      - name: 오늘자 가격 기준 스크리닝 실행 + JSON 저장
        working-directory: screening
        env:
          KRX_API_KEY: ${{ secrets.KRX_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
```

- [ ] **Step 2: YAML 문법 검증**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily-screen.yml', encoding='utf-8'))"`
Expected: 에러 없이 통과.

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/daily-screen.yml
git commit -m "ci: 스크리닝 실행 스텝에 ANTHROPIC_API_KEY 환경변수 추가"
```

**주의(구현자가 아닌 사용자가 처리할 항목, 코드로 자동화 불가):** GitHub 저장소 Settings → Secrets and
variables → Actions에 `ANTHROPIC_API_KEY`를 등록해야 실제로 동작한다. 이 키가 없으면 Task 1의
`generate_all_commentary`가 자동으로 전체를 건너뛰므로 파이프라인 자체는 실패하지 않는다.

---

### Task 4: 프런트 — 종목명 클릭 → 투자자별 코멘트 모달

**Files:**
- Create: `web/app/StockCommentaryDialog.tsx`
- Modify: `web/app/ScreeningTable.tsx`
- Modify: `web/app/page.tsx`

**Interfaces:**
- Consumes: `results.json`의 각 레코드에 있는 `commentary: {peter_lynch, warren_buffett, bill_ackman} | undefined`
- Produces: `StockCommentaryDialog` 컴포넌트 — props `{ open: boolean; onOpenChange: (open: boolean) => void; stockName: string; commentary: Commentary | null | undefined }`

- [ ] **Step 1: `StockCommentaryDialog.tsx` 작성**

`web/app/StockCommentaryDialog.tsx`:
```tsx
"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface Commentary {
  peter_lynch: string | null;
  warren_buffett: string | null;
  bill_ackman: string | null;
}

const INVESTOR_LABELS: Record<keyof Commentary, string> = {
  peter_lynch: "Peter Lynch",
  warren_buffett: "Warren Buffett",
  bill_ackman: "Bill Ackman",
};

const INVESTOR_KEYS: (keyof Commentary)[] = ["peter_lynch", "warren_buffett", "bill_ackman"];

export default function StockCommentaryDialog({
  open,
  onOpenChange,
  stockName,
  commentary,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  stockName: string;
  commentary: Commentary | null | undefined;
}) {
  const [activeInvestor, setActiveInvestor] = useState<keyof Commentary>("peter_lynch");

  const text = commentary?.[activeInvestor] ?? null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{stockName} — 투자자 관점 분석</DialogTitle>
        </DialogHeader>

        <div className="flex gap-2">
          {INVESTOR_KEYS.map((key) => (
            <Button
              key={key}
              type="button"
              size="sm"
              variant={activeInvestor === key ? "default" : "outline"}
              onClick={() => setActiveInvestor(key)}
            >
              {INVESTOR_LABELS[key]}
            </Button>
          ))}
        </div>

        <div className="mt-2 rounded-2xl rounded-tl-none bg-muted p-4 text-sm leading-relaxed">
          {text ?? "아직 분석이 준비되지 않았습니다."}
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: `ScreeningTable.tsx`에서 `name` 컬럼을 클릭 가능하게 변경**

`web/app/ScreeningTable.tsx` 상단 import(1-14행)에 추가:
```tsx
import StockCommentaryDialog, { Commentary } from "./StockCommentaryDialog";
```

`web/app/ScreeningTable.tsx:16`:
```tsx
type ResultRow = Record<string, string | number | null>;
```
를 다음으로 교체:
```tsx
type ResultRow = Record<string, string | number | null> & { commentary?: Commentary | null };
```

`web/app/ScreeningTable.tsx`의 컴포넌트 함수 내부, 기존 `useState` 선언들(44-49행) 바로 아래에 추가:
```tsx
  const [dialogRow, setDialogRow] = useState<ResultRow | null>(null);
```

`web/app/ScreeningTable.tsx:156-165`의 테이블 바디 렌더링:
```tsx
          <TableBody>
            {sorted.map((row, i) => (
              <TableRow key={(row.stock_code as string) ?? i}>
                <TableCell className="text-muted-foreground">{i + 1}</TableCell>
                {displayColumns.map((col) => (
                  <TableCell key={col} className={alignClass(col)}>
                    {formatValue(row[col], col)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
```
를 다음으로 교체:
```tsx
          <TableBody>
            {sorted.map((row, i) => (
              <TableRow key={(row.stock_code as string) ?? i}>
                <TableCell className="text-muted-foreground">{i + 1}</TableCell>
                {displayColumns.map((col) => (
                  <TableCell key={col} className={alignClass(col)}>
                    {col === "name" ? (
                      <button
                        type="button"
                        className="underline decoration-dotted underline-offset-2 hover:text-primary"
                        onClick={() => setDialogRow(row)}
                      >
                        {formatValue(row[col], col)}
                      </button>
                    ) : (
                      formatValue(row[col], col)
                    )}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
```

`web/app/ScreeningTable.tsx`의 최상위 반환 JSX 마지막(현재 `</div>` 닫는 태그 바로 앞, 168-170행 부근)에
`StockCommentaryDialog` 렌더링 추가 — 컴포넌트 최상위 `return (` 블록의 닫는 `</div>` 바로 앞에:
```tsx
      <StockCommentaryDialog
        open={dialogRow !== null}
        onOpenChange={(open) => !open && setDialogRow(null)}
        stockName={dialogRow ? String(dialogRow.name ?? "") : ""}
        commentary={dialogRow?.commentary}
      />
```

- [ ] **Step 3: `page.tsx`의 타입에 `commentary` 필드 반영**

`web/app/page.tsx:14`:
```tsx
type ResultRow = Record<string, string | number | null>;
```
를 다음으로 교체:
```tsx
type ResultRow = Record<string, string | number | null> & {
  commentary?: { peter_lynch: string | null; warren_buffett: string | null; bill_ackman: string | null } | null;
};
```

- [ ] **Step 4: 빌드 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공, 타입 에러 없음.

- [ ] **Step 5: 더미 데이터로 로컬 동작 확인**

Run: `cd web && npm run dev`. 브라우저에서 종목명을 클릭했을 때 모달이 열리고, 3개 버튼(Peter Lynch /
Warren Buffett / Bill Ackman)을 클릭하면 내용이 전환되는지 확인한다. 현재 `web/data/results.json`에는
아직 `commentary` 필드가 없으므로(다음 자동 갱신 전까지), 3개 탭 모두 "아직 분석이 준비되지 않았습니다"가
표시되는 것이 정상이다 — 이것으로 fallback 처리가 올바른지 확인된다.

- [ ] **Step 6: 커밋**

```bash
git add web/app/StockCommentaryDialog.tsx web/app/ScreeningTable.tsx web/app/page.tsx
git commit -m "feat: 종목명 클릭 시 투자자별(Lynch/Buffett/Ackman) 분석 모달 표시"
```

---

## 최종 통합 확인 (모든 Task 완료 후)

- [ ] **전체 파이썬 테스트 실행**

Run: `cd screening && python -m pytest tests/ -v`
Expected: 모든 테스트 PASS (기존 10개 + 이번에 추가한 7개 = 17개).

- [ ] **웹 빌드 최종 확인**

Run: `cd web && npm run build`
Expected: 빌드 성공, 타입 에러 없음.

- [ ] **사용자 액션 필요 (코드로 자동화 불가)**

GitHub 저장소 Settings → Secrets and variables → Actions에 `ANTHROPIC_API_KEY`를 등록해야 다음 자동
스크리닝 실행부터 실제로 코멘트가 생성된다. 등록 전까지는 `generate_all_commentary`가 자동으로 전체를
건너뛰므로 사이트는 정상 동작하되 모든 종목의 말풍선이 "아직 분석이 준비되지 않았습니다"로 표시된다.
