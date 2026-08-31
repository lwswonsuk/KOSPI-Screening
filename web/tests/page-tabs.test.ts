import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("page.tsx 탭 구성", () => {
  it("Korean Value Stocks/Cheap Korean Stocks 두 탭을 각각 ScreeningSection으로 렌더링한다", () => {
    const source = fs.readFileSync(path.join(process.cwd(), "app/page.tsx"), "utf8");

    expect(source).toContain('from "@/components/ui/tabs"');
    expect(source).toContain(">Korean Value Stocks<");
    expect(source).toContain(">Cheap Korean Stocks<");
    expect(source).toContain('"results.json"');
    expect(source).toContain('"results_cheap.json"');
    expect(source).toContain('downloadHref="/api/filtered"');
    expect(source).toContain('downloadHref="/api/filtered-cheap"');
  });

  it("results_cheap.json이 없어도 죽지 않도록 존재 여부를 확인한다", () => {
    const source = fs.readFileSync(path.join(process.cwd(), "app/page.tsx"), "utf8");

    expect(source).toContain("existsSync");
  });
});
