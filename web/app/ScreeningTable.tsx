"use client";

import { useMemo, useState } from "react";

type ResultRow = Record<string, string | number | null>;

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
          return { ...r, close: live.close, fluc_rt: live.fluc_rt };
        })
      );
      setPriceAsOf(data.as_of);
    } catch (e: any) {
      setPriceError(e.message ?? String(e));
    } finally {
      setPriceLoading(false);
    }
  }

  const displayColumns = useMemo(() => {
    if (!columns.includes("close")) return columns;
    // fluc_rt(등락률)이 아직 컬럼 목록에 없으면 close 바로 뒤에 추가
    if (columns.includes("fluc_rt")) return columns;
    const idx = columns.indexOf("close");
    return [...columns.slice(0, idx + 1), "fluc_rt", ...columns.slice(idx + 1)];
  }, [columns]);

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
                  style={{ ...thStyle, cursor: "pointer", userSelect: "none" }}
                  onClick={() => onSort(col)}
                >
                  {labels[col] ?? (col === "fluc_rt" ? "등락률(%)" : col)}
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
                  <td
                    key={col}
                    style={{
                      ...tdStyle,
                      color:
                        col === "fluc_rt" && typeof row[col] === "number"
                          ? (row[col] as number) > 0
                            ? "#f87171"
                            : (row[col] as number) < 0
                            ? "#60a5fa"
                            : tdStyle.color
                          : tdStyle.color,
                    }}
                  >
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

function formatValue(v: string | number | null, col?: string) {
  if (v === null || v === undefined) return "-";
  if (typeof v === "number") {
    if (col === "fluc_rt") return (v > 0 ? "+" : "") + v.toFixed(2) + "%";
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

