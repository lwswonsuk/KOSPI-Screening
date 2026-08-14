"use client";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export interface StockProfile {
  business: string;
  sector: string;
  products: string;
  competitors: string;
}

const PROFILE_SECTIONS: { key: keyof StockProfile; label: string }[] = [
  { key: "business", label: "사업 내용" },
  { key: "sector", label: "섹터" },
  { key: "products", label: "대표 상품·브랜드" },
  { key: "competitors", label: "주요 경쟁사" },
];

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
              {PROFILE_SECTIONS.map(({ key, label }) => (
                <div key={key}>
                  <div className="font-medium text-foreground">{label}</div>
                  <div className="mt-0.5 text-muted-foreground">{profile[key]}</div>
                </div>
              ))}
            </div>
          ) : (
            "아직 분석이 준비되지 않았습니다."
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
