import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("FilteredDownloadButton", () => {
  it("href를 prop으로 받고 /api/filtered를 하드코딩하지 않는다", () => {
    const source = fs.readFileSync(
      path.join(process.cwd(), "app/FilteredDownloadButton.tsx"),
      "utf8"
    );

    expect(source).toContain("href: string");
    expect(source).toContain("href={href}");
    expect(source).not.toContain('"/api/filtered"');
  });
});
