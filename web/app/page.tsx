import fs from "fs";
import path from "path";
import ScreeningSection from "./ScreeningSection";
import CheapAlgorithmInfo from "./CheapAlgorithmInfo";
import AdminGate from "./AdminGate";
import type { ResultsPayload } from "@/lib/types";

export const dynamic = "force-static"; // 빌드 시점 JSON을 그대로 굽는다 (커밋될 때마다 재배포되며 갱신됨)

const EMPTY_PAYLOAD: ResultsPayload = {
  as_of_date: null,
  financial_year: null,
  financial_period_label: null,
  generated_at: null,
  quote_text: null,
  quote_author: null,
  universe_total: 0,
  universe_passed: 0,
  columns: [],
  column_labels_ko: {},
  results: [],
};

function loadJsonPayload(filename: string): ResultsPayload {
  const filePath = path.join(process.cwd(), "data", filename);
  if (!fs.existsSync(filePath)) return EMPTY_PAYLOAD; // 최초 배포 등 파일이 아직 없는 경우
  const raw = fs.readFileSync(filePath, "utf-8");
  return JSON.parse(raw);
}

export default function Home() {
  const cheapData = loadJsonPayload("results_cheap.json");

  return (
    <main className="mx-auto max-w-6xl px-5 py-10">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">한국주식 스크리닝</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {cheapData.quote_text
            ? `"${cheapData.quote_text}" — ${cheapData.quote_author}`
            : "저평가 우량주 스크리닝"}
        </p>
      </div>

      <ScreeningSection
        data={cheapData}
        algorithmInfo={<CheapAlgorithmInfo />}
        downloadHref="/api/filtered-cheap"
      />

      <AdminGate />
    </main>
  );
}
