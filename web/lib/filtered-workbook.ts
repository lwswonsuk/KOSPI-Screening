import * as XLSX from "xlsx";
import type { FilteredPayload } from "./types";

export function createFilteredWorkbook(payload: FilteredPayload): ArrayBuffer {
  const rows = payload.results.map((row) =>
    Object.fromEntries(
      payload.columns.map((column) => [payload.column_labels_ko[column] ?? column, row[column] ?? null]),
    ),
  );
  const sheet = XLSX.utils.json_to_sheet(rows);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, sheet, "필터통과종목");
  return XLSX.write(workbook, { type: "array", bookType: "xlsx", compression: true });
}
