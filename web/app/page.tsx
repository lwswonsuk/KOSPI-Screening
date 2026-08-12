import fs from "fs";
import path from "path";
import ScreeningTable from "./ScreeningTable";
import UpdateControls from "./UpdateControls";
import AlgorithmInfo from "./AlgorithmInfo";

export const dynamic = "force-static"; // 빌드 시점 JSON을 그대로 굽는다 (커밋될 때마다 재배포되며 갱신됨)

type ResultRow = Record<string, string | number | null>;

interface ResultsPayload {
  as_of_date: string | null;
  financial_year: number | null;
  generated_at: string | null;
  universe_total: number;
  universe_passed: number;
  columns: string[];
  column_labels_ko: Record<string, string>;
  results: ResultRow[];
}

function loadResults(): ResultsPayload {
  const filePath = path.join(process.cwd(), "data", "results.json");
  const raw = fs.readFileSync(filePath, "utf-8");
  return JSON.parse(raw);
}

export default function Home() {
  const data = loadResults();

  return (
    <main style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 20px" }}>
      <h1 style={{ fontSize: 26, marginBottom: 4 }}>주식 스크리닝 결과</h1>
      <p style={{ color: "#9aa0a6", marginTop: 0, marginBottom: 20 }}>
        Stock Note 투자원칙 기반 코스피 종목 스크리닝
      </p>

      <UpdateControls />

      {data.results.length === 0 ? (
        <div
          style={{
            padding: 24,
            border: "1px solid #2a2f3a",
            borderRadius: 8,
            background: "#12151c",
          }}
        >
          아직 결과가 없습니다. GitHub Actions가 처음 실행되면 자동으로 채워집니다.
        </div>
      ) : (
        <>
          <div
            style={{
              display: "flex",
              gap: 20,
              marginBottom: 20,
              flexWrap: "wrap",
              color: "#9aa0a6",
              fontSize: 14,
            }}
          >
            <span>가격 기준일: {data.as_of_date}</span>
            <span>재무 기준연도: {data.financial_year}</span>
            <span>
              필터 통과: {data.universe_passed} / {data.universe_total}
            </span>
            <span>갱신: {data.generated_at ? new Date(data.generated_at).toLocaleString("ko-KR") : "-"}</span>
          </div>
          <AlgorithmInfo />
          <ScreeningTable
            columns={data.columns}
            labels={data.column_labels_ko}
            rows={data.results}
          />
        </>
      )}
    </main>
  );
}
