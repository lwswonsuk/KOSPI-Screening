import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("ScreeningTable 기본 정렬", () => {
  it("score 컬럼이 없는 데이터셋에서는 백엔드 순서를 그대로 유지한다", () => {
    const source = fs.readFileSync(
      path.join(process.cwd(), "app/ScreeningTable.tsx"),
      "utf8"
    );

    // "score"가 있을 때만 기본 정렬 기준으로 삼아야 한다 (Cheap Korean Stocks처럼
    // score 컬럼이 없는 탭에서 존재하지 않는 컬럼으로 정렬을 시도해 순서가
    // 뒤섞이는 회귀를 방지한다).
    expect(source).toMatch(/columns\.includes\(["']score["']\)/);

    // 정렬 기준 컬럼이 없거나(sortKey가 빈 문자열) 두 행 모두 해당 값이
    // 없으면 순서를 그대로 유지(0 반환)해야 한다 — 한쪽만 undefined일 때만
    // 뒤로 보내야 하며, 둘 다 undefined인 경우를 먼저 걸러야 한다.
    expect(source).toContain("if (!sortKey) return 0;");
    expect(source).toMatch(/aMissing\s*&&\s*bMissing/);
  });
});
