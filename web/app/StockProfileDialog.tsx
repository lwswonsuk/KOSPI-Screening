"use client";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import type { StockProfile } from "@/lib/types";

const TEXT_SECTIONS: { key: "business" | "sector" | "products"; label: string }[] = [
  { key: "business", label: "사업 내용" },
  { key: "sector", label: "섹터" },
  { key: "products", label: "대표 상품·브랜드" },
];

// results.json이 다음 파이프라인 실행 전까지는 예전(콤마로 구분된 문자열) 형식의
// competitors를 담고 있을 수 있어, 배열이 아니어도 안전하게 표시되도록 정규화한다.
function normalizeCompetitors(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.filter((v): v is string => typeof v === "string" && v.trim().length > 0);
  }
  if (typeof value === "string") {
    return value.split(/,\s*/).map((s) => s.trim()).filter(Boolean);
  }
  return [];
}

export default function StockProfileDialog({
  open,
  onOpenChange,
  stockName,
  profile,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  stockName: string;
  profile: StockProfile | null | undefined;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{stockName} — 종목 프로필</DialogTitle>
        </DialogHeader>

        <div className="mt-2 rounded-2xl rounded-tl-none bg-muted p-4 text-sm leading-relaxed">
          {profile ? (
            <div className="space-y-3">
              {TEXT_SECTIONS.map(({ key, label }) => (
                <div key={key}>
                  <div className="font-medium text-foreground">{label}</div>
                  <div className="mt-0.5 text-muted-foreground">{profile[key]}</div>
                </div>
              ))}
              <div>
                <div className="font-medium text-foreground">주요 경쟁사</div>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {normalizeCompetitors(profile.competitors).map((competitor) => (
                    <Badge key={competitor} variant="secondary">
                      {competitor}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            "아직 분석이 준비되지 않았습니다."
          )}
        </div>

        {profile && (
          <p className="mt-1 text-xs text-muted-foreground">
            AI가 생성한 정보로 부정확하거나 최신이 아닐 수 있습니다.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
