"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { ArrowUpDown, ArrowUp, ArrowDown, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { getErrorMessage } from "@/lib/errors";
import type { PriceResponse, ResultRow } from "@/lib/types";

const StockProfileDialog = dynamic(() => import("./StockProfileDialog"), {
  loading: () => (
    <p role="status" aria-live="polite" className="sr-only">
      종목 프로필을 불러오는 중…
    </p>
  ),
});

// 화면에서 아예 안 보여줄 컬럼 (JSON에 남아있어도 숨김)
const HIDDEN_COLUMNS = new Set([
  "ret_12m", "op_yoy", "fluc_rt",
  "s_quality", "s_value", "s_gap", "s_payout",   // 개별 팩터 점수는 숨기고 종합점수만 노출
]);

// 소수점 2자리 + 우측 정렬로 보여줄 컬럼
const TWO_DECIMAL_RIGHT_ALIGN = new Set([
  "per", "pbr", "roe_3y_avg", "debt_ratio", "div_yield", "payout_ratio_pct",
  "dist_from_52w_low_pct", "ev_ebitda", "eps_now", "eps_3to5y_median",
]);

// 소수점 4자리 + 우측 정렬 (종합점수 전용)
const FOUR_DECIMAL_RIGHT_ALIGN = new Set(["score"]);

// 우측 정렬만 적용할 컬럼 (숫자 포맷은 기본값 유지)
const RIGHT_ALIGN_ONLY = new Set(["close"]);

export default function ScreeningTable({
  columns,
  labels,
  rows,
}: {
  columns: string[];
  labels: Record<string, string>;
  rows: ResultRow[];
}) {
  // 데이터셋마다 있는 컬럼이 달라(예: Cheap Korean Stocks에는 "score"가 없음),
  // "score"가 있을 때만 기본 정렬 기준으로 삼는다. 없으면 백엔드가 이미
  // 정해둔 순서(JSON에 저장된 순서)를 그대로 유지한다.
  const [sortKey, setSortKey] = useState<string>(() => (columns.includes("score") ? "score" : ""));
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [liveRows, setLiveRows] = useState<ResultRow[]>(rows);
  const [priceAsOf, setPriceAsOf] = useState<string | null>(null);
  const [priceLoading, setPriceLoading] = useState(false);
  const [priceError, setPriceError] = useState<string | null>(null);
  const [dialogRow, setDialogRow] = useState<ResultRow | null>(null);

  const displayColumns = useMemo(
    () => columns.filter((c) => !HIDDEN_COLUMNS.has(c)),
    [columns]
  );

  async function refreshPrices() {
    setPriceLoading(true);
    setPriceError(null);
    try {
      const codes = rows.map((r) => String(r.stock_code)).join(",");
      const res = await fetch(`/api/prices?codes=${codes}`, { cache: "no-store" });
      const data: PriceResponse = await res.json();
      if (!res.ok) {
        throw new Error("error" in data ? data.error : "시세 조회 실패");
      }
      if ("error" in data) throw new Error(data.error || "시세 조회 실패");

      setLiveRows(
        rows.map((r) => {
          const code = String(r.stock_code);
          const live = data.prices[code];
          if (!live) return r;
          return { ...r, close: live.close };   // 등락률(fluc_rt)은 더 이상 반영하지 않음
        })
      );
      setPriceAsOf(data.as_of);
    } catch (error: unknown) {
      setPriceError(getErrorMessage(error, "시세 조회 실패"));
    } finally {
      setPriceLoading(false);
    }
  }

  const sorted = useMemo(() => {
    const copy = [...liveRows];
    copy.sort((a, b) => {
      if (!sortKey) return 0; // 활성화된 정렬 기준 없음 → 백엔드가 정한 순서 유지 (안정 정렬)
      const av = a[sortKey];
      const bv = b[sortKey];
      const aMissing = av === null || av === undefined;
      const bMissing = bv === null || bv === undefined;
      if (aMissing && bMissing) return 0;
      if (aMissing) return 1;
      if (bMissing) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return sortDir === "asc" ? av - bv : bv - av;
      }
      return sortDir === "asc"
        ? String(av).localeCompare(String(bv), "ko")
        : String(bv).localeCompare(String(av), "ko");
    });
    return copy.slice(0, 200);
  }, [liveRows, sortKey, sortDir]);

  function onSort(col: string) {
    if (col === sortKey) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(col);
      setSortDir("desc");
    }
  }

  function SortIcon({ col }: { col: string }) {
    if (sortKey !== col) return <ArrowUpDown className="ml-1 inline size-3 opacity-40" />;
    return sortDir === "asc" ? (
      <ArrowUp className="ml-1 inline size-3" />
    ) : (
      <ArrowDown className="ml-1 inline size-3" />
    );
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          onClick={refreshPrices}
          disabled={priceLoading}
        >
          <RefreshCw className={cn("size-3.5", priceLoading && "animate-spin")} />
          {priceLoading ? "불러오는 중…" : "최신 종가 새로고침"}
        </Button>
        {priceAsOf && (
          <span className="text-xs text-muted-foreground">
            시세 기준일: {priceAsOf} (장마감 확정 종가 기준, 실시간 체결가 아님)
          </span>
        )}
        {priceError && <span className="text-xs text-destructive">{priceError}</span>}
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-10">#</TableHead>
              {displayColumns.map((col) => (
                <TableHead
                  key={col}
                  className={cn(
                    "cursor-pointer select-none",
                    alignClass(col)
                  )}
                  onClick={() => onSort(col)}
                >
                  {labels[col] ?? col}
                  <SortIcon col={col} />
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((row, i) => (
              <TableRow key={row.stock_code}>
                <TableCell className="text-muted-foreground">{i + 1}</TableCell>
                {displayColumns.map((col) => (
                  <TableCell key={col} className={alignClass(col)}>
                    {col === "name" ? (
                      <button
                        type="button"
                        className="underline decoration-dotted underline-offset-2 hover:text-primary"
                        onClick={() => setDialogRow(row)}
                      >
                        {formatValue(row[col], col)}
                      </button>
                    ) : (
                      formatValue(row[col], col)
                    )}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {dialogRow && (
        <StockProfileDialog
          open
          onOpenChange={(open) => !open && setDialogRow(null)}
          stockName={dialogRow.name}
          profile={dialogRow.profile}
        />
      )}
    </div>
  );
}

function alignClass(col: string): string {
  if (
    TWO_DECIMAL_RIGHT_ALIGN.has(col) ||
    FOUR_DECIMAL_RIGHT_ALIGN.has(col) ||
    RIGHT_ALIGN_ONLY.has(col) ||
    col === "mktcap_eok"
  ) {
    return "text-right";
  }
  return "";
}

function formatValue(v: unknown, col?: string) {
  if (v === null || v === undefined) return "-";
  if (typeof v === "number") {
    if (col === "mktcap_eok") {
      // 시가총액: 천 단위 콤마 + 소수점 1자리
      return v.toLocaleString("ko-KR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    }
    if (col && FOUR_DECIMAL_RIGHT_ALIGN.has(col)) {
      // 종합점수: 소수점 4자리
      return v.toLocaleString("ko-KR", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
    }
    if (col && TWO_DECIMAL_RIGHT_ALIGN.has(col)) {
      // PER/PBR/ROE/부채비율/배당수익률/배당성향: 소수점 2자리
      return v.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return Number.isInteger(v) ? v.toLocaleString("ko-KR") : v.toFixed(3);
  }
  if (typeof v === "string") return v;
  return "-";
}


