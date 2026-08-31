import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("ScreeningTable 숫자 포맷", () => {
  it("Cheap Korean Stocks 전용 컬럼이 서식 규칙에 포함된다", () => {
    const source = fs.readFileSync(
      path.join(process.cwd(), "app/ScreeningTable.tsx"),
      "utf8"
    );

    expect(source).toMatch(/TWO_DECIMAL_RIGHT_ALIGN = new Set\(\[[^\]]*"dist_from_52w_low_pct"/);
    expect(source).toMatch(/TWO_DECIMAL_RIGHT_ALIGN = new Set\(\[[^\]]*"ev_ebitda"/);
    expect(source).toMatch(/TWO_DECIMAL_RIGHT_ALIGN = new Set\(\[[^\]]*"eps_now"/);
    expect(source).toMatch(/TWO_DECIMAL_RIGHT_ALIGN = new Set\(\[[^\]]*"eps_3to5y_median"/);
    expect(source).toMatch(/TWO_DECIMAL_RIGHT_ALIGN = new Set\(\[[^\]]*"pbr"/);
  });
});
