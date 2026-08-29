import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("ScreeningTable 숫자 포맷", () => {
  it("Cheap Stock Picking 전용 컬럼이 서식 규칙에 포함된다", () => {
    const source = fs.readFileSync(
      path.join(process.cwd(), "app/ScreeningTable.tsx"),
      "utf8"
    );

    expect(source).toMatch(/TWO_DECIMAL_RIGHT_ALIGN = new Set\(\[[^\]]*"dist_from_52w_low_pct"/);
    expect(source).toMatch(/TWO_DECIMAL_RIGHT_ALIGN = new Set\(\[[^\]]*"ev_ebit"/);
    expect(source).toMatch(/RIGHT_ALIGN_ONLY = new Set\(\[[^\]]*"low_52w"/);
    expect(source).toMatch(/RIGHT_ALIGN_ONLY = new Set\(\[[^\]]*"op_ttm_eok"/);
  });
});
