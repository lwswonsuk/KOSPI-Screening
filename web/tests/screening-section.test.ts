import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("ScreeningSection", () => {
  it("빈 결과 상태와 정상 결과 상태를 모두 처리하고 downloadHref/algorithmInfo를 prop으로 받는다", () => {
    const source = fs.readFileSync(
      path.join(process.cwd(), "app/ScreeningSection.tsx"),
      "utf8"
    );

    expect(source).toContain("아직 결과가 없습니다");
    expect(source).toContain("downloadHref");
    expect(source).toContain("algorithmInfo");
    expect(source).toContain("<ScreeningTable");
    expect(source).toContain("<FilteredDownloadButton");
    expect(source).toContain("href={downloadHref}");
  });
});
