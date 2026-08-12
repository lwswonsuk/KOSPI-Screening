import { createHmac, timingSafeEqual } from "crypto";

/**
 * 관리자 비밀번호를 검증하고, 통과 시 HMAC 서명된 세션 쿠키를 발급한다.
 * 쿠키 값 = HMAC-SHA256(ADMIN_PASSWORD, "admin") — 별도 세션 저장소 없이
 * update-finance route에서 동일한 HMAC을 재계산해 비교하는 방식(무상태).
 */
function sessionToken(): string {
  const secret = process.env.ADMIN_PASSWORD ?? "";
  return createHmac("sha256", secret).update("admin").digest("hex");
}

export async function POST(req: Request) {
  const adminPassword = process.env.ADMIN_PASSWORD;
  if (!adminPassword) {
    return Response.json(
      { error: "서버에 ADMIN_PASSWORD 환경변수가 설정되어 있지 않습니다." },
      { status: 500 }
    );
  }

  const body = await req.json().catch(() => ({}));
  const password = String(body?.password ?? "");

  const a = Buffer.from(password);
  const b = Buffer.from(adminPassword);
  const match = a.length === b.length && timingSafeEqual(a, b);
  if (!match) {
    return Response.json({ error: "비밀번호가 일치하지 않습니다." }, { status: 401 });
  }

  const token = sessionToken();
  const res = Response.json({ ok: true });
  res.headers.set(
    "Set-Cookie",
    `admin_session=${token}; Path=/; HttpOnly; Max-Age=86400; SameSite=Lax`
  );
  return res;
}
