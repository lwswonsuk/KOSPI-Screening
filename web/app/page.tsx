import fs from "fs";
import path from "path";
import ScreeningTable from "./ScreeningTable";
import UpdateControls from "./UpdateControls";
import AlgorithmInfo from "./AlgorithmInfo";
import AdminGate from "./AdminGate";
import FilteredDownloadButton from "./FilteredDownloadButton";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatKoreanDate } from "@/lib/format";

export const dynamic = "force-static"; // 빌드 시점 JSON을 그대로 굽는다 (커밋될 때마다 재배포되며 갱신됨)

type ResultRow = Record<string, string | number | null>;

interface ResultsPayload {
  as_of_date: string | null;
  financial_year: number | null;
  generated_at: string | null;
  quote_text: string | null;
  quote_author: string | null;
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
    <main className="mx-auto max-w-6xl px-5 py-10">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">한국 가치투자 스크리닝</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {data.quote_text
            ? `"${data.quote_text}" — ${data.quote_author}`
            : "Stock Note 투자원칙 기반 코스피 종목 스크리닝"}
        </p>
      </div>

      {data.results.length === 0 ? (
        <Card>
          <CardContent className="text-sm text-muted-foreground">
            아직 결과가 없습니다. GitHub Actions가 처음 실행되면 자동으로 채워집니다.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-2">
            <Badge variant="secondary">가격 기준일 {formatKoreanDate(data.as_of_date)}</Badge>
            <Badge variant="secondary">재무 기준연도 {data.financial_year}</Badge>
            <FilteredDownloadButton passed={data.universe_passed} total={data.universe_total} />
            <Badge variant="outline">
              갱신{" "}
              {data.generated_at
                ? new Date(data.generated_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })
                : "-"}
            </Badge>
          </div>

          <AlgorithmInfo />

          <ScreeningTable
            columns={data.columns}
            labels={data.column_labels_ko}
            rows={data.results}
          />
        </>
      )}

      <AdminGate>
        <UpdateControls />
      </AdminGate>
    </main>
  );
}

