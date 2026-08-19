import { describe, expect, it } from "vitest";
import * as XLSX from "xlsx";
import { createFilteredWorkbook } from "./filtered-workbook";
import type { FilteredPayload } from "./types";

const payload: FilteredPayload = {
  columns: ["stock_code", "name", "score"],
  column_labels_ko: { stock_code: "종목코드", name: "종목명", score: "종합점수" },
  results: [
    { stock_code: "005930", name: "테스트전자", score: 0.75 },
    { stock_code: "000660", name: "테스트반도체", score: 0.7 },
  ],
};

describe("createFilteredWorkbook", () => {
  it("한국어 헤더와 모든 행이 포함된 XLSX를 만든다", () => {
    const bytes = createFilteredWorkbook(payload);
    expect(Array.from(new Uint8Array(bytes, 0, 2))).toEqual([0x50, 0x4b]);

    const workbook = XLSX.read(bytes, { type: "array" });
    const sheet = workbook.Sheets["필터통과종목"];
    const rows = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet);

    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ 종목코드: "005930", 종목명: "테스트전자", 종합점수: 0.75 });
  });
});
