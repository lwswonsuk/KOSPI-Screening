"use client";

import { useMemo, useState } from "react";

type ResultRow = Record<string, string | number | null>;

// 화면에서 아예 안 보여줄 컬럼 (JSON에 남아있어도 숨김)
const HIDDEN_COLUMNS = new Set([
  "ret_12m", "op_yoy", "fluc_rt",
  "s_quality", "s_value", "s_gap", "s_payout",   // 개별 팩터 점수는 숨기고 종합점수만 노출
]);

// 소수점 2자리 + 우측 정렬로 보여줄 컬럼
const TWO_DECIMAL_RIGHT_ALIGN = new Set(["per", "pbr", "roe_3y_avg", "debt_ratio"]);

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
  const [sortKey, setSortKey] = useState<string>("score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [liveRows, setLiveRows] = useState<ResultRow[]>(rows);
  const [priceAsOf, setPriceAsOf] = useState<string | null>(null);
  const [priceLoading, setPriceLoading] = useState(false);
  const [priceError, setPriceError] = useState<string | null>(null);

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
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "시세 조회 실패");

      setLiveRows(
        rows.map((r) => {
          const code = String(r.stock_code);
          const live = data.prices[code];
          if (!live) return r;
          return { ...r, close: live.close };   // 등락률(fluc_rt)은 더 이상 반영하지 않음
        })
      );
      setPriceAsOf(data.as_of);
    } catch (e: any) {
      setPriceError(e.message ?? String(e));
    } finally {
      setPriceLoading(false);
    }
  }

  const sorted = useMemo(() => {
    const copy = [...liveRows];
    copy.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return sortDir === "asc" ? av - bv : bv - av;
      }
      return sortDir === "asc"
        ? String(av).localeCompare(String(bv), "ko")
        : String(bv).localeCompare(String(av), "ko");
    });
    return copy;
  }, [liveRows, sortKey, sortDir]);

  function onSort(col: string) {
    if (col === sortKey) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(col);
      setSortDir("desc");
    }
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 10,
          flexWrap: "wrap",
        }}
      >
        <button
          onClick={refreshPrices}
          disabled={priceLoading}
          style={{
            padding: "6px 14px",
            borderRadius: 6,
            border: "1px solid #3b82f6",
            background: "transparent",
            color: "#93c5fd",
            cursor: priceLoading ? "default" : "pointer",
            fontSize: 13,
          }}
        >
          {priceLoading ? "불러오는 중…" : "최신 종가 새로고침"}
        </button>
        {priceAsOf && (
          <span style={{ fontSize: 13, color: "#9aa0a6" }}>
            시세 기준일: {priceAsOf} (장마감 확정 종가 기준, 실시간 체결가 아님)
          </span>
        )}
        {priceError && <span style={{ fontSize: 13, color: "#f87171" }}>{priceError}</span>}
      </div>

      <div style={{ overflowX: "auto", border: "1px solid #2a2f3a", borderRadius: 8 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ background: "#161a22" }}>
              <th style={thStyle}>#</th>
              {displayColumns.map((col) => (
                <th
                  key={col}
                  style={{ ...thStyle, ...alignStyle(col), cursor: "pointer", userSelect: "none" }}
                  onClick={() => onSort(col)}
                >
                  {labels[col] ?? col}
                  {sortKey === col ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => (
              <tr
                key={row.stock_code ?? i}
                style={{
                  borderTop: "1px solid #232733",
                  background: i % 2 === 0 ? "transparent" : "#0f1218",
                }}
              >
                <td style={tdStyle}>{i + 1}</td>
                {displayColumns.map((col) => (
                  <td key={col} style={{ ...tdStyle, ...alignStyle(col) }}>
                    {formatValue(row[col], col)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function alignStyle(col: string): React.CSSProperties {
  if (TWO_DECIMAL_RIGHT_ALIGN.has(col) || RIGHT_ALIGN_ONLY.has(col) || col === "mktcap_eok") {
    return { textAlign: "right" };
  }
  return {};
}

function formatValue(v: string | number | null, col?: string) {
  if (v === null || v === undefined) return "-";
  if (typeof v === "number") {
    if (col === "mktcap_eok") {
      // 시가총액: 천 단위 콤마 + 소수점 1자리
      return v.toLocaleString("ko-KR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    }
    if (col && TWO_DECIMAL_RIGHT_ALIGN.has(col)) {
      // PER/PBR/ROE/부채비율: 소수점 2자리
      return v.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return Number.isInteger(v) ? v.toLocaleString("ko-KR") : v.toFixed(3);
  }
  return v;
}

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "10px 12px",
  fontWeight: 600,
  color: "#c7cad1",
  whiteSpace: "nowrap",
};

const tdStyle: React.CSSProperties = {
  padding: "8px 12px",
  whiteSpace: "nowrap",
  color: "#e6e6e6",
};

