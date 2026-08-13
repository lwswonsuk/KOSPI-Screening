import fs from "fs";
import path from "path";

export const dynamic = "force-static"; // 빌드 시점 JSON을 그대로 굽는다 (page.tsx의 results.json과 동일한 정적 배포 패턴)

export async function GET() {
  const filePath = path.join(process.cwd(), "data", "filtered_full.json");
  if (!fs.existsSync(filePath)) {
    return Response.json({ error: "필터통과 데이터가 아직 생성되지 않았습니다." }, { status: 404 });
  }
  const raw = fs.readFileSync(filePath, "utf-8");
  return new Response(raw, {
    headers: { "Content-Type": "application/json" },
  });
}
