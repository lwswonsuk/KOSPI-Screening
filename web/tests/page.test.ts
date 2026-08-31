import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("page.tsx 단일 화면 구성", () => {
  it("탭 없이 Cheap Korean Stocks 화면 하나만 렌더링한다", () => {
    const source = fs.readFileSync(path.join(process.cwd(), "app/page.tsx"), "utf8");

    expect(source).not.toContain('from "@/components/ui/tabs"');
    expect(source).not.toContain('from "./AlgorithmInfo"');
    expect(source).toContain('from "./CheapAlgorithmInfo"');
    expect(source).toContain('"results_cheap.json"');
    expect(source).not.toContain('"results.json"');
    expect(source).toContain('downloadHref="/api/filtered-cheap"');
  });
});
