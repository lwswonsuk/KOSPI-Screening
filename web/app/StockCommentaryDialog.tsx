"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface Commentary {
  peter_lynch: string | null;
  warren_buffett: string | null;
  bill_ackman: string | null;
}

const INVESTOR_LABELS: Record<keyof Commentary, string> = {
  peter_lynch: "Peter Lynch",
  warren_buffett: "Warren Buffett",
  bill_ackman: "Bill Ackman",
};

const INVESTOR_KEYS: (keyof Commentary)[] = ["peter_lynch", "warren_buffett", "bill_ackman"];

export default function StockCommentaryDialog({
  open,
  onOpenChange,
  stockName,
  commentary,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  stockName: string;
  commentary: Commentary | null | undefined;
}) {
  const [activeInvestor, setActiveInvestor] = useState<keyof Commentary>("peter_lynch");

  const text = commentary?.[activeInvestor] ?? null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{stockName} — 투자자 관점 분석</DialogTitle>
        </DialogHeader>

        <div className="flex gap-2">
          {INVESTOR_KEYS.map((key) => (
            <Button
              key={key}
              type="button"
              size="sm"
              variant={activeInvestor === key ? "default" : "outline"}
              onClick={() => setActiveInvestor(key)}
            >
              {INVESTOR_LABELS[key]}
            </Button>
          ))}
        </div>

        <div className="mt-2 rounded-2xl rounded-tl-none bg-muted p-4 text-sm leading-relaxed">
          {text ?? "아직 분석이 준비되지 않았습니다."}
        </div>
      </DialogContent>
    </Dialog>
  );
}
