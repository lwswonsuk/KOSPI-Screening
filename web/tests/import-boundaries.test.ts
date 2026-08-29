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

  it("AlgorithmInfo와 CheapAlgorithmInfo는 client directive나 Radix Collapsible을 사용하지 않는다", () => {
    for (const file of ["app/AlgorithmInfo.tsx", "app/CheapAlgorithmInfo.tsx"]) {
      const source = fs.readFileSync(path.join(ROOT, file), "utf8");
      expect(source, file).not.toContain('"use client"');
      expect(source, file).not.toContain("Collapsible");
    }
  });

  it("저사용 Dialog와 관리자 컨트롤은 dynamic import한다", () => {
    const table = fs.readFileSync(path.join(ROOT, "app/ScreeningTable.tsx"), "utf8");
    const admin = fs.readFileSync(path.join(ROOT, "app/AdminGate.tsx"), "utf8");
    expect(table).toContain('dynamic(() => import("./StockProfileDialog")');
    expect(table).toMatch(/dialogRow\s*&&\s*\(\s*<StockProfileDialog/);
    expect(admin).toContain('dynamic(() => import("./UpdateControls")');
  });

  it("Dialog 지연 로딩 fallback은 보조기술에 상태를 알린다", () => {
    const table = fs.readFileSync(path.join(ROOT, "app/ScreeningTable.tsx"), "utf8");
    expect(table).toMatch(/loading:\s*\(\)\s*=>\s*\([\s\S]*?role="status"[\s\S]*?aria-live="polite"/);
  });

  it("관리자 도구 지연 로딩 fallback은 보조기술에 상태를 알린다", () => {
    const admin = fs.readFileSync(path.join(ROOT, "app/AdminGate.tsx"), "utf8");
    expect(admin).toMatch(/loading:\s*\(\)\s*=>\s*\([\s\S]*?role="status"[\s\S]*?aria-live="polite"/);
  });
});
