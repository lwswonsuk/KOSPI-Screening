import type { NextRequest } from "next/server";
import { getErrorMessage } from "@/lib/errors";
import type { KrxPriceRow } from "@/lib/types";

export const dynamic = "force-dynamic"; // 매 요청마다 새로 실행 (캐시 안 함)

/**
 * KRX '유가증권 일별매매정보'는 장 마감 후 확정되는 일별 종가 데이터다.
 * 틱 단위 실시간 체결가가 아니라는 점에 유의 — 여기서는 "최신 종가를
 * 그때그때 다시 불러오기" 기능만 제공한다.
 */

function todayKstString(offsetDays = 0): string {
  const now = new Date(Date.now() + 9 * 60 * 60 * 1000); // KST 보정
  now.setUTCDate(now.getUTCDate() - offsetDays);
  return now.toISOString().slice(0, 10).replace(/-/g, "");
}

async function fetchKrxDay(dateStr: string): Promise<KrxPriceRow[] | null> {
  const key = process.env.KRX_API_KEY;
  if (!key) throw new Error("서버에 KRX_API_KEY 환경변수가 설정되어 있지 않습니다.");

  const url = `https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd?basDd=${dateStr}`;
  const res = await fetch(url, { headers: { AUTH_KEY: key }, cache: "no-store" });
  if (!res.ok) return null;

  const json: unknown = await res.json();
  if (typeof json !== "object" || json === null || !("OutBlock_1" in json)) return null;

  const rows = json.OutBlock_1;
  if (
    !Array.isArray(rows) ||
    rows.length === 0 ||
    !rows.every(
      (row): row is KrxPriceRow =>
        typeof row === "object" &&
        row !== null &&
        "ISU_CD" in row &&
        (typeof row.ISU_CD === "string" || typeof row.ISU_CD === "number") &&
        "TDD_CLSPRC" in row &&
        (typeof row.TDD_CLSPRC === "string" || typeof row.TDD_CLSPRC === "number") &&
        "FLUC_RT" in row &&
        (typeof row.FLUC_RT === "string" || typeof row.FLUC_RT === "number")
    )
  ) {
    return null;
  }
  return rows;
}

export async function GET(req: NextRequest) {
  const codesParam = req.nextUrl.searchParams.get("codes");
  const wanted = codesParam
    ? new Set(codesParam.split(",").map((s) => s.trim()).filter(Boolean))
    : null;

  let rows: KrxPriceRow[] | null = null;
  let usedDate = "";

  try {
    // 오늘부터 최대 7일 전까지 거슬러 올라가며 데이터가 있는 날을 찾는다
    // (주말·공휴일에는 그날 데이터가 없으므로)
    for (let offset = 0; offset < 7; offset++) {
      const d = todayKstString(offset);
      rows = await fetchKrxDay(d);
      if (rows) {
        usedDate = d;
        break;
      }
    }
  } catch (error: unknown) {
    return Response.json({ error: getErrorMessage(error, "KRX 시세 조회 실패") }, { status: 500 });
  }

  if (!rows) {
    return Response.json(
      { error: "최근 7일 내 KRX 시세 데이터를 찾지 못했습니다." },
      { status: 502 }
    );
  }

  const prices: Record<string, { close: number; fluc_rt: number }> = {};
  for (const r of rows) {
    const code = String(r.ISU_CD).padStart(6, "0");
    if (wanted && !wanted.has(code)) continue;
    prices[code] = {
      close: Number(String(r.TDD_CLSPRC).replace(/,/g, "")),
      fluc_rt: Number(String(r.FLUC_RT).replace(/,/g, "")),
    };
  }

  return Response.json({ as_of: usedDate, prices });
}
