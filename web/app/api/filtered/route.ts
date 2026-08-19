import fs from "fs";
import path from "path";
import { createFilteredWorkbook } from "@/lib/filtered-workbook";
import type { FilteredPayload } from "@/lib/types";

export const dynamic = "force-static"; // 빌드 시점 JSON을 그대로 굽는다 (page.tsx의 results.json과 동일한 정적 배포 패턴)

const XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const DOWNLOAD_NAME = encodeURIComponent("필터통과종목.xlsx");

export async function GET() {
  const filePath = path.join(process.cwd(), "data", "filtered_full.json");
  if (!fs.existsSync(filePath)) {
    return Response.json({ error: "필터통과 데이터가 아직 생성되지 않았습니다." }, { status: 404 });
  }
  const payload: FilteredPayload = JSON.parse(fs.readFileSync(filePath, "utf-8"));
  const workbookBytes = createFilteredWorkbook(payload);
  return new Response(workbookBytes, {
    headers: {
      "Content-Type": XLSX_CONTENT_TYPE,
      "Content-Disposition": `attachment; filename="filtered-stocks.xlsx"; filename*=UTF-8''${DOWNLOAD_NAME}`,
      "Cache-Control": "public, max-age=0, s-maxage=31536000, immutable",
    },
  });
}
