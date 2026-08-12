"use client";

import { useState } from "react";

export default function UpdateControls() {
  const [forceFinance, setForceFinance] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);

  async function handleUpdate() {
    setLoading(true);
    setMessage(null);
    try {
      const res = await fetch("/api/update-finance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ forceFinance, ttmQuarter: "auto" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "요청 실패");
      setMessage({ text: data.message, error: false });
    } catch (e: any) {
      setMessage({ text: e.message ?? String(e), error: true });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        border: "1px solid #2a2f3a",
        borderRadius: 8,
        padding: 16,
        marginBottom: 20,
        display: "flex",
        alignItems: "center",
        gap: 16,
        flexWrap: "wrap",
        background: "#12151c",
      }}
    >
      <button
        onClick={handleUpdate}
        disabled={loading}
        style={{
          padding: "8px 16px",
          borderRadius: 6,
          border: "none",
          background: loading ? "#555" : "#3b82f6",
          color: "white",
          cursor: loading ? "default" : "pointer",
          fontWeight: 600,
        }}
      >
        {loading ? "요청 중…" : "스크리닝 업데이트 실행"}
      </button>

      <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14, color: "#c7cad1" }}>
        <input
          type="checkbox"
          checked={forceFinance}
          onChange={(e) => setForceFinance(e.target.checked)}
        />
        재무데이터도 강제로 새로 받기 (평소엔 체크 안 해도 됨, 몇 분 더 걸림)
      </label>

      {message && (
        <span style={{ fontSize: 13, color: message.error ? "#f87171" : "#4ade80" }}>
          {message.text}
        </span>
      )}
    </div>
  );
}
