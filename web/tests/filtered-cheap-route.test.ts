import { afterEach, describe, expect, it, vi } from "vitest";
import fs from "fs";
import { GET } from "../app/api/filtered-cheap/route";

describe("GET /api/filtered-cheap", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("filtered_cheap_full.json이 없으면 404를 반환한다", async () => {
    vi.spyOn(fs, "existsSync").mockReturnValue(false);

    const response = await GET();

    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({
      error: "필터통과 데이터가 아직 생성되지 않았습니다.",
    });
  });

  it("filtered_cheap_full.json이 있으면 xlsx 파일을 반환한다", async () => {
    vi.spyOn(fs, "existsSync").mockReturnValue(true);
    vi.spyOn(fs, "readFileSync").mockReturnValue(
      JSON.stringify({
        columns: ["name"],
        column_labels_ko: { name: "종목명" },
        results: [{ name: "테스트종목" }],
      })
    );

    const response = await GET();

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe(
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    );
    expect(response.headers.get("Content-Disposition")).toContain("cheap-stocks.xlsx");
  });
});
