# 웹앱 성능·번들·코드 품질 최적화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Next.js 정적 배포 구조와 사용자 기능을 유지하면서 초기 JavaScript, 전체 종목 XLSX 다운로드 비용, 불필요한 hydration, 타입 불안정성을 줄인다.

**Architecture:** Radix 루트 배럴을 직접 하위 경로 import로 교체하고 단순 Collapsible을 서버 렌더링 `<details>`로 바꾼다. 전체 종목 데이터는 정적 Route Handler가 빌드 시 XLSX로 변환하며, 저사용 관리자 UI와 종목 Dialog는 조건부 dynamic import한다. 공유 데이터 타입과 오류 변환은 `web/lib/`의 작은 모듈로 통합한다.

**Tech Stack:** Next.js 15.5 App Router, React 19, TypeScript 5, Tailwind CSS 4, Vitest, SheetJS `xlsx` 0.18.5

**Spec:** `docs/superpowers/specs/2026-08-19-web-performance-optimization-design.md`

## Global Constraints

- 수정 범위는 `web/`와 이 계획/설계 문서뿐이다.
- `screening/` Python 코드와 `.github/workflows/`는 수정하지 않는다.
- 기준선은 `/` Route Size 95 kB, First Load JS 197 kB, 공통 JS 102 kB이다.
- `results.json` 상위 50종목 테이블 UX와 정렬·종가 새로고침·프로필 Dialog 동작을 유지한다.
- `/api/filtered`는 `force-static`을 유지하되 XLSX 바이너리를 반환한다.
- 전체 545종목은 다운로드 전용이므로 페이지네이션·가상 스크롤을 추가하지 않는다.
- `xlsx`는 서버 빌드 경로에서만 import하고 클라이언트 모듈에서는 import하지 않는다.
- `lucide-react`, Tailwind 4, `tw-animate-css`는 유지한다.
- 행동 변경은 테스트를 먼저 작성하고 예상한 이유로 실패하는 것을 확인한 뒤 구현한다.

---

### Task 1: 테스트 기반과 공유 타입·오류 처리 추가

**Files:**
- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Create: `web/lib/errors.ts`
- Create: `web/lib/errors.test.ts`
- Create: `web/lib/types.ts`

**Interfaces:**
- Produces: `getErrorMessage(error: unknown, fallback: string): string`
- Produces: `StockProfile`, `ResultRow`, `ResultsPayload`, `FilteredPayload`, `PriceResponse`, `KrxPriceRow`

- [ ] **Step 1: Vitest 개발 의존성과 test script 추가**

Run:

```powershell
cd web
npm.cmd install --save-dev vitest
```

`package.json` scripts에 다음을 추가한다.

```json
"test": "vitest run"
```

- [ ] **Step 2: 오류 변환 실패 테스트 작성**

`web/lib/errors.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { getErrorMessage } from "./errors";

describe("getErrorMessage", () => {
  it("Error 메시지를 반환한다", () => {
    expect(getErrorMessage(new Error("실패"), "기본 오류")).toBe("실패");
  });

  it("비어 있지 않은 문자열 오류를 반환한다", () => {
    expect(getErrorMessage("문자열 오류", "기본 오류")).toBe("문자열 오류");
  });

  it("알 수 없는 값에는 fallback을 반환한다", () => {
    expect(getErrorMessage({ code: 500 }, "기본 오류")).toBe("기본 오류");
  });
});
```

- [ ] **Step 3: 테스트가 예상한 이유로 실패하는지 확인**

Run: `cd web && npm.cmd test -- lib/errors.test.ts`

Expected: `Cannot find module './errors'`로 FAIL.

- [ ] **Step 4: 최소 오류 변환 구현 작성**

`web/lib/errors.ts`:

```ts
export function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  if (typeof error === "string" && error.trim()) return error;
  return fallback;
}
```

- [ ] **Step 5: 공유 타입 작성**

`web/lib/types.ts`에 다음 타입을 둔다.

```ts
export interface StockProfile {
  business: string;
  sector: string;
  products: string;
  competitors: string[];
}

export type CellValue = string | number | null;

export type ResultRow = Record<string, unknown> & {
  stock_code: string;
  name: string;
  profile?: StockProfile | null;
};

export interface ResultsPayload {
  as_of_date: string | null;
  financial_year: number | null;
  generated_at: string | null;
  quote_text: string | null;
  quote_author: string | null;
  universe_total: number;
  universe_passed: number;
  columns: string[];
  column_labels_ko: Record<string, string>;
  results: ResultRow[];
}

export type FilteredRow = Record<string, CellValue>;

export interface FilteredPayload {
  columns: string[];
  column_labels_ko: Record<string, string>;
  results: FilteredRow[];
}

export interface PriceSuccessResponse {
  as_of: string;
  prices: Record<string, { close: number; fluc_rt: number }>;
}

export interface ApiErrorResponse { error: string }

export type PriceResponse = PriceSuccessResponse | ApiErrorResponse;

export interface KrxPriceRow {
  ISU_CD: string | number;
  TDD_CLSPRC: string | number;
  FLUC_RT: string | number;
}
```

- [ ] **Step 6: 테스트와 타입 검사 확인**

Run:

```powershell
cd web
npm.cmd test -- lib/errors.test.ts
npx.cmd tsc --noEmit
```

Expected: 모두 PASS.

- [ ] **Step 7: Commit**

```powershell
git add web/package.json web/package-lock.json web/lib/errors.ts web/lib/errors.test.ts web/lib/types.ts
git commit -m "test: web 최적화용 Vitest와 공유 타입 추가"
```

---

### Task 2: Radix 배럴 제거와 AlgorithmInfo 서버 컴포넌트화

**Files:**
- Create: `web/tests/import-boundaries.test.ts`
- Modify: `web/components/ui/badge.tsx`
- Modify: `web/components/ui/button.tsx`
- Modify: `web/components/ui/checkbox.tsx`
- Modify: `web/components/ui/dialog.tsx`
- Modify: `web/app/AlgorithmInfo.tsx`
- Delete: `web/components/ui/collapsible.tsx`

**Interfaces:**
- Consumes: 기존 shadcn UI component API
- Produces: Radix 직접 하위 경로 import만 사용하는 동일 UI API
- Produces: hydration 없는 서버 컴포넌트 `AlgorithmInfo`

- [ ] **Step 1: 번들 경계 실패 테스트 작성**

`web/tests/import-boundaries.test.ts`:

```ts
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = process.cwd();
const RADIX_FILES = [
  "components/ui/badge.tsx",
  "components/ui/button.tsx",
  "components/ui/checkbox.tsx",
  "components/ui/dialog.tsx",
];

describe("client bundle import boundaries", () => {
  it("radix-ui 루트 배럴을 import하지 않는다", () => {
    for (const relativePath of RADIX_FILES) {
      const source = fs.readFileSync(path.join(ROOT, relativePath), "utf8");
      expect(source, relativePath).not.toMatch(/from ["']radix-ui["']/);
    }
  });

  it("AlgorithmInfo는 client directive나 Radix Collapsible을 사용하지 않는다", () => {
    const source = fs.readFileSync(path.join(ROOT, "app/AlgorithmInfo.tsx"), "utf8");
    expect(source).not.toContain('"use client"');
    expect(source).not.toContain("Collapsible");
  });
});
```

- [ ] **Step 2: 테스트가 현재 배럴 import 때문에 실패하는지 확인**

Run: `cd web && npm.cmd test -- tests/import-boundaries.test.ts`

Expected: 두 테스트 모두 FAIL.

- [ ] **Step 3: Radix import를 직접 하위 경로로 교체**

정확한 교체:

```ts
// badge.tsx, button.tsx
import * as SlotPrimitive from "radix-ui/slot";

// checkbox.tsx
import * as CheckboxPrimitive from "radix-ui/checkbox";

// dialog.tsx
import * as DialogPrimitive from "radix-ui/dialog";
```

기존 `SlotPrimitive.Root`, `CheckboxPrimitive.Root`, `DialogPrimitive.Root` 호출 방식을
유지하도록 `badge.tsx`와 `button.tsx`의 `Slot.Root` 두 곳만 `SlotPrimitive.Root`로 바꾼다.

- [ ] **Step 4: AlgorithmInfo를 네이티브 details로 교체**

`"use client"`, `useState`, Chevron icon, Button, Collapsible import를 제거한다.
상단 구조를 다음으로 바꾸고 기존 Card 내부 설명 및 Alert는 그대로 유지한다.

```tsx
<details className="group">
  <summary className="inline-flex h-8 cursor-pointer list-none items-center justify-center gap-2 rounded-md border bg-background px-3 text-sm font-medium shadow-xs transition-all hover:bg-accent hover:text-accent-foreground [&::-webkit-details-marker]:hidden">
    <Info className="size-3.5" />
    이 스크리닝은 어떤 기준으로 종목을 골랐나요?
    <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
  </summary>
  <Card className="mt-3 py-5">
    <CardContent className="space-y-4 text-sm leading-relaxed text-foreground/90">
      <p className="text-muted-foreground">
        핵심 아이디어: <b className="text-foreground">실적·경쟁력은 괜찮은데 주가만 안 오른 종목을 찾아서 모아두고 기다린다.</b>
      </p>
      <section>
        <h4 className="mb-2 font-semibold text-foreground">1단계 — 하드 필터 (자동 제외 기준)</h4>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li>시가총액 800억 원 이상 ~ 40조 원 이하</li>
          <li>최근 거래대금 3억 원 이상 (유동성 필터)</li>
          <li>부채비율 200% 초과 제외</li>
          <li>ROE(3년 평균) 5% 미만 제외</li>
          <li>최근 영업이익(TTM 기준) 적자 제외</li>
          <li>최근 3개월 수익률 +60% 이상인 테마 급등 종목 제외</li>
          <li>관리종목 제외</li>
        </ul>
      </section>
      <section>
        <h4 className="mb-2 font-semibold text-foreground">2단계 — 4대 팩터 종합 점수</h4>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li><b className="text-foreground">체력 (30%)</b> — ROE 수준·안정성, 영업이익률, 부채비율, 매출 성장</li>
          <li><b className="text-foreground">가격 (28%)</b> — PER·PBR 저평가 정도</li>
          <li><b className="text-foreground">★괴리 (27%, 핵심 팩터)</b> — 실적은 개선되는데 주가는 빠진 정도</li>
          <li><b className="text-foreground">환원여력 (15%)</b> — 배당 확대 여력</li>
        </ul>
        <p className="mt-2 text-muted-foreground">
          각 팩터는 전체 종목 대비 백분위로 점수화되며, 위 가중치로 합산해 <b className="text-foreground">종합점수</b>를 만듭니다.
          음식료·화장품·방산 등 특정 업종엔 가산점을, 테마성 업종엔 감점을 반영합니다.
        </p>
      </section>
      <section>
        <h4 className="mb-2 font-semibold text-foreground">데이터 기준</h4>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li>가격/시가총액: KRX 공식 API, 표 상단에 표시된 기준일 종가</li>
          <li>재무데이터: DART 공시자료, 최근 4분기(TTM) 누적 기준</li>
          <li>대상: 코스피 전종목</li>
        </ul>
      </section>
    </CardContent>
  </Card>
</details>
```

`components/ui/collapsible.tsx`를 삭제한다.

- [ ] **Step 5: 테스트 및 빌드 확인**

Run:

```powershell
cd web
npm.cmd test -- tests/import-boundaries.test.ts
npm.cmd run build
```

Expected: 테스트 PASS, 빌드 PASS, client reference manifest에 Radix 전체 모듈 목록이 더 이상 없어야 한다.

- [ ] **Step 6: Commit**

```powershell
git add web/tests/import-boundaries.test.ts web/components/ui web/app/AlgorithmInfo.tsx
git commit -m "perf: Radix 배럴 제거와 설명 UI 서버 렌더링"
```

---

### Task 3: 필터 통과 전체 데이터를 정적 XLSX로 제공

**Files:**
- Create: `web/lib/filtered-workbook.ts`
- Create: `web/lib/filtered-workbook.test.ts`
- Modify: `web/app/api/filtered/route.ts`
- Modify: `web/app/FilteredDownloadButton.tsx`

**Interfaces:**
- Consumes: `FilteredPayload`
- Produces: `createFilteredWorkbook(payload: FilteredPayload): ArrayBuffer`
- Produces: `GET /api/filtered` 정적 XLSX 응답

- [ ] **Step 1: 워크북 생성 실패 테스트 작성**

`web/lib/filtered-workbook.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import * as XLSX from "xlsx";
import { createFilteredWorkbook } from "./filtered-workbook";
import type { FilteredPayload } from "./types";

const payload: FilteredPayload = {
  columns: ["stock_code", "name", "score"],
  column_labels_ko: { stock_code: "종목코드", name: "종목명", score: "종합점수" },
  results: [
    { stock_code: "005930", name: "테스트전자", score: 0.75 },
    { stock_code: "000660", name: "테스트반도체", score: 0.7 },
  ],
};

describe("createFilteredWorkbook", () => {
  it("한국어 헤더와 모든 행이 포함된 XLSX를 만든다", () => {
    const bytes = createFilteredWorkbook(payload);
    expect(Array.from(new Uint8Array(bytes, 0, 2))).toEqual([0x50, 0x4b]);

    const workbook = XLSX.read(bytes, { type: "array" });
    const sheet = workbook.Sheets["필터통과종목"];
    const rows = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet);

    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ 종목코드: "005930", 종목명: "테스트전자", 종합점수: 0.75 });
  });
});
```

- [ ] **Step 2: 테스트가 모듈 부재로 실패하는지 확인**

Run: `cd web && npm.cmd test -- lib/filtered-workbook.test.ts`

Expected: `Cannot find module './filtered-workbook'`로 FAIL.

- [ ] **Step 3: 워크북 생성 함수 구현**

`web/lib/filtered-workbook.ts`:

```ts
import * as XLSX from "xlsx";
import type { FilteredPayload } from "./types";

export function createFilteredWorkbook(payload: FilteredPayload): ArrayBuffer {
  const rows = payload.results.map((row) =>
    Object.fromEntries(
      payload.columns.map((column) => [payload.column_labels_ko[column] ?? column, row[column] ?? null]),
    ),
  );
  const sheet = XLSX.utils.json_to_sheet(rows);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, sheet, "필터통과종목");
  return XLSX.write(workbook, { type: "array", bookType: "xlsx", compression: true });
}
```

- [ ] **Step 4: `/api/filtered`를 XLSX 정적 응답으로 변경**

파일이 없을 때의 404는 유지한다. 파일이 있으면 `FilteredPayload`로 파싱하고
`createFilteredWorkbook` 결과를 반환한다.

```ts
const XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const DOWNLOAD_NAME = encodeURIComponent("필터통과종목.xlsx");

return new Response(workbookBytes, {
  headers: {
    "Content-Type": XLSX_CONTENT_TYPE,
    "Content-Disposition": `attachment; filename="filtered-stocks.xlsx"; filename*=UTF-8''${DOWNLOAD_NAME}`,
    "Cache-Control": "public, max-age=0, s-maxage=31536000, immutable",
  },
});
```

- [ ] **Step 5: 다운로드 버튼을 서버 렌더링 링크로 단순화**

`FilteredDownloadButton.tsx`에서 `"use client"`, state, fetch, `xlsx` dynamic import,
오류 UI를 제거한다.

```tsx
export default function FilteredDownloadButton({ passed, total }: Props) {
  return (
    <Badge asChild variant="secondary">
      <a href="/api/filtered">
        <Download className="mr-1 size-3" />
        필터 통과 {passed} / {total}
      </a>
    </Badge>
  );
}
```

- [ ] **Step 6: 테스트와 정적 Route 빌드 검증**

Run:

```powershell
cd web
npm.cmd test -- lib/filtered-workbook.test.ts
npm.cmd run build
```

Expected:

- 테스트 PASS
- 빌드 PASS
- `.next/server/app/api/filtered.body` 첫 두 byte가 `PK` (`0x50 0x4b`)
- `.next/server/app/api/filtered.meta`에 XLSX Content-Type과 Content-Disposition 존재
- `.next/static/chunks`에서 `SheetJS`가 포함된 클라이언트 XLSX chunk가 사라짐

- [ ] **Step 7: Commit**

```powershell
git add web/lib/filtered-workbook.ts web/lib/filtered-workbook.test.ts web/app/api/filtered/route.ts web/app/FilteredDownloadButton.tsx
git commit -m "perf: 전체 종목 XLSX를 빌드 시 정적으로 생성"
```

---

### Task 4: 저사용 UI 지연 로딩과 타입 안정성 개선

**Files:**
- Modify: `web/app/page.tsx`
- Modify: `web/app/ScreeningTable.tsx`
- Modify: `web/app/StockProfileDialog.tsx`
- Modify: `web/app/AdminGate.tsx`
- Modify: `web/app/UpdateControls.tsx`
- Modify: `web/app/api/prices/route.ts`
- Modify: `web/tests/import-boundaries.test.ts`

**Interfaces:**
- Consumes: Task 1의 공유 타입과 `getErrorMessage`
- Produces: 클릭 후에만 로드되는 `StockProfileDialog`
- Produces: 관리자 인증 후에만 로드되는 `UpdateControls`

- [ ] **Step 1: 지연 로딩 경계 실패 테스트 추가**

`import-boundaries.test.ts`에 다음 테스트를 추가한다.

```ts
it("저사용 Dialog와 관리자 컨트롤은 dynamic import한다", () => {
  const table = fs.readFileSync(path.join(ROOT, "app/ScreeningTable.tsx"), "utf8");
  const admin = fs.readFileSync(path.join(ROOT, "app/AdminGate.tsx"), "utf8");
  expect(table).toContain('dynamic(() => import("./StockProfileDialog")');
  expect(table).toMatch(/dialogRow\s*&&\s*\(\s*<StockProfileDialog/);
  expect(admin).toContain('dynamic(() => import("./UpdateControls")');
});
```

- [ ] **Step 2: 테스트가 static import 때문에 실패하는지 확인**

Run: `cd web && npm.cmd test -- tests/import-boundaries.test.ts`

Expected: 새 테스트 FAIL.

- [ ] **Step 3: StockProfileDialog를 조건부 dynamic import**

`ScreeningTable.tsx`:

```ts
import dynamic from "next/dynamic";
import type { ResultRow, PriceResponse } from "@/lib/types";

const StockProfileDialog = dynamic(() => import("./StockProfileDialog"), {
  loading: () => null,
});
```

기존 항상 렌더링하던 Dialog를 다음으로 바꾼다.

```tsx
{dialogRow && (
  <StockProfileDialog
    open
    onOpenChange={(open) => !open && setDialogRow(null)}
    stockName={dialogRow.name}
    profile={dialogRow.profile}
  />
)}
```

가격 API 응답은 `const data: PriceResponse = await res.json()`으로 지정하고 catch는
`catch (error: unknown)` + `getErrorMessage`를 사용한다. `formatValue`는 `unknown`을
받고 문자열·숫자·null 외에는 `"-"`를 반환한다.

- [ ] **Step 4: 관리자 컨트롤을 인증 후 dynamic import**

`AdminGate.tsx`:

```ts
import dynamic from "next/dynamic";
const UpdateControls = dynamic(() => import("./UpdateControls"), {
  loading: () => <p className="mt-10 text-center text-xs text-muted-foreground">관리자 도구를 불러오는 중…</p>,
});
```

children prop을 제거하고 `unlocked`일 때 `<UpdateControls />`를 반환한다. `page.tsx`는
`UpdateControls` import를 제거하고 `<AdminGate />`만 렌더링한다.

- [ ] **Step 5: 공유 타입과 unknown 오류 처리 적용**

- `page.tsx`: 로컬 `ResultRow`, `ResultsPayload` 제거 후 `import type`
- `StockProfileDialog.tsx`: 로컬 `StockProfile` 제거 후 `import type`
- `AdminGate.tsx`, `UpdateControls.tsx`: `catch (error: unknown)`과 `getErrorMessage`
- `api/prices/route.ts`: `KrxPriceRow[]`, `unknown` JSON 검사, unknown catch 사용
- `TableRow key`: `key={row.stock_code}`만 사용

- [ ] **Step 6: 전체 테스트와 빌드 확인**

Run:

```powershell
cd web
npm.cmd test
npx.cmd tsc --noEmit
npm.cmd run build
```

Expected: 모두 PASS, `rg -n "catch \([^)]*: any\)|Promise<any|any\[\]" app lib` 결과 없음.

- [ ] **Step 7: Commit**

```powershell
git add web/app web/lib web/tests/import-boundaries.test.ts
git commit -m "perf: 저사용 UI 지연 로딩과 web 타입 안정성 개선"
```

---

### Task 5: Next.js 설정 및 최종 성능 검증

**Files:**
- Modify: `web/next.config.js`
- Create: `docs/superpowers/reports/2026-08-19-web-performance-results.md`

**Interfaces:**
- Produces: 올바른 tracing root와 비활성화된 X-Powered-By 헤더
- Produces: 변경 전후 번들 측정 보고서

- [ ] **Step 1: Next.js 설정 적용**

`web/next.config.js`:

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingRoot: __dirname,
  poweredByHeader: false,
};

module.exports = nextConfig;
```

`compress`와 `images` 설정은 추가하지 않는다.

- [ ] **Step 2: 깨끗한 최종 검증 실행**

Run:

```powershell
cd web
npm.cmd test
npx.cmd tsc --noEmit
npm.cmd run build
```

Expected:

- 모든 테스트 PASS
- TypeScript 오류 없음
- build PASS
- workspace root 추론 경고 없음

- [ ] **Step 3: 번들과 정적 산출물 측정**

기록할 항목:

- `/` Route Size
- `/` First Load JS
- 공통 First Load JS
- 생성 CSS bytes
- XLSX 정적 body bytes
- client chunk에서 SheetJS/XLSX 문자열 검색 결과
- client reference manifest에서 불필요한 Radix 모듈 검색 결과

- [ ] **Step 4: 브라우저 동작 확인**

로컬 production server에서 다음을 확인한다.

1. 초기 페이지와 상위 50종목 표 표시
2. 열 정렬
3. 최신 종가 새로고침의 로딩 및 오류 UI
4. 종목명 클릭 후 프로필 Dialog 지연 로드 및 닫기
5. 알고리즘 `<details>` 열기/닫기
6. 필터 통과 링크가 `.xlsx` 파일을 다운로드
7. 관리자 로그인 Dialog와 인증 후 UpdateControls 로드

- [ ] **Step 5: 결과 보고서 작성**

`docs/superpowers/reports/2026-08-19-web-performance-results.md`에 기준선과 최종값,
절감량, 변경 이유, 보류한 항목을 기록한다. 보류 항목에는 다음을 포함한다.

- 50행뿐이므로 페이지네이션·가상 스크롤 미도입
- 이미지가 없어 `next/image`/images config 미도입
- 기본값이므로 `compress` 미설정
- 정상 범위이고 애니메이션이 실제 사용되므로 Tailwind/tw-animate 유지
- named import가 트리셰이킹되므로 lucide-react 유지

- [ ] **Step 6: Commit**

```powershell
git add web/next.config.js docs/superpowers/reports/2026-08-19-web-performance-results.md
git commit -m "chore: Next.js tracing 설정과 성능 결과 기록"
```

---

## 최종 완료 기준

- `web/` 밖의 애플리케이션 코드가 변경되지 않는다.
- `npm test`, `tsc --noEmit`, `npm run build`가 모두 통과한다.
- `/` First Load JS가 기준선 197 kB보다 감소한다.
- `radix-ui` 루트 import가 없다.
- 클라이언트 XLSX chunk가 없다.
- `/api/filtered` 정적 산출물이 유효한 XLSX다.
- 기존 사용자 기능이 로컬 브라우저에서 정상 동작한다.
