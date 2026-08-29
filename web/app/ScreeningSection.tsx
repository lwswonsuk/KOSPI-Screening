import type { ReactNode } from "react";
import ScreeningTable from "./ScreeningTable";
import FilteredDownloadButton from "./FilteredDownloadButton";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatKoreanDate } from "@/lib/format";
import type { ResultsPayload } from "@/lib/types";

export default function ScreeningSection({
  data,
  algorithmInfo,
  downloadHref,
}: {
  data: ResultsPayload;
  algorithmInfo: ReactNode;
  downloadHref: string;
}) {
  if (data.results.length === 0) {
    return (
      <Card>
        <CardContent className="text-sm text-muted-foreground">
          아직 결과가 없습니다. GitHub Actions가 처음 실행되면 자동으로 채워집니다.
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <Badge variant="secondary">가격 기준일 {formatKoreanDate(data.as_of_date)}</Badge>
        <Badge variant="secondary">
          재무 기준 {data.financial_period_label ?? `${data.financial_year}년`}
        </Badge>
        <FilteredDownloadButton
          href={downloadHref}
          passed={data.universe_passed}
          total={data.universe_total}
        />
        <Badge variant="outline">
          갱신{" "}
          {data.generated_at
            ? new Date(data.generated_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })
            : "-"}
        </Badge>
      </div>

      {algorithmInfo}

      <ScreeningTable
        columns={data.columns}
        labels={data.column_labels_ko}
        rows={data.results}
      />
    </>
  );
}
