/**
 * 웹사이트의 "업데이트" 버튼이 이 API를 호출하면, GitHub Actions의
 * daily-screen.yml 워크플로우를 즉시 실행시킨다(workflow_dispatch).
 * 실제 스크리닝 계산은 Vercel이 아니라 GitHub Actions 서버에서 돌아간다
 * (830종목 × DART 호출은 서버리스 함수의 실행시간 제한을 넘기 때문).
 *
 * 필요한 Vercel 환경변수 (Vercel 프로젝트 설정 → Environment Variables):
 *   GH_PAT   : GitHub Personal Access Token (repo, workflow 권한 필요)
 *   GH_OWNER : GitHub 사용자명/조직명
 *   GH_REPO  : 저장소 이름
 */
export async function POST(req: Request) {
  const token = process.env.GH_PAT;
  const owner = process.env.GH_OWNER;
  const repo = process.env.GH_REPO;

  if (!token || !owner || !repo) {
    return Response.json(
      {
        error:
          "서버 환경변수(GH_PAT / GH_OWNER / GH_REPO)가 설정되어 있지 않습니다. " +
          "Vercel 프로젝트 설정에서 등록해주세요.",
      },
      { status: 500 }
    );
  }

  let forceFinance = false;
  let ttmQuarter = "auto";
  try {
    const body = await req.json();
    forceFinance = Boolean(body?.forceFinance);
    ttmQuarter = body?.ttmQuarter || "auto";
  } catch {
    // body 없이 호출된 경우 기본값 사용
  }

  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/actions/workflows/daily-screen.yml/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: {
          force_finance: String(forceFinance),
          ttm_quarter: ttmQuarter,
        },
      }),
    }
  );

  if (!res.ok) {
    const text = await res.text();
    return Response.json(
      { error: `GitHub 워크플로우 실행 요청 실패 (${res.status}): ${text}` },
      { status: 502 }
    );
  }

  return Response.json({
    ok: true,
    message:
      "업데이트가 요청되었습니다. GitHub Actions에서 실행 중이며, 완료 후 " +
      "자동으로 사이트가 재배포됩니다 (보통 2~10분 정도 걸립니다).",
  });
}
