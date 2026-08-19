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
