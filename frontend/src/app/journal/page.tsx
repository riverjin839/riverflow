"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

interface JournalEntry {
  id: number;
  trade_date: string;
  ticker: string;
  ticker_name: string | null;
  side: string;
  quantity: number;
  price: number;
  pnl: number | null;
  pnl_pct: number | null;
  notes: string | null;
  emotion: string | null;
}

export default function JournalPage() {
  const [token, setToken] = useState<string | null>(null);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    setToken(stored);
  }, []);

  const fetchJournal = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await apiFetch<JournalEntry[]>("/api/journal", { token });
      setEntries(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchJournal();
  }, [fetchJournal]);

  if (!token) {
    return (
      <main>
        <h1 style={titleStyle}>매매일지</h1>
        <p style={{ color: "#999", textAlign: "center", marginTop: "3rem" }}>
          로그인이 필요합니다.
        </p>
      </main>
    );
  }

  return (
    <main>
      <h1 style={titleStyle}>매매일지</h1>

      {loading ? (
        <p style={{ color: "#999" }}>로딩 중...</p>
      ) : entries.length === 0 ? (
        <div style={{ textAlign: "center", color: "#999", marginTop: "3rem" }}>
          <p>매매일지가 비어있습니다.</p>
          <p style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>
            자동매매 또는 수동 기록을 시작하면 여기에 표시됩니다.
          </p>
        </div>
      ) : (
        <div style={{ background: "#fff", border: "1px solid #e0e0e0", borderRadius: 8, overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                <th style={thStyle}>날짜</th>
                <th style={thStyle}>종목</th>
                <th style={thStyle}>매매</th>
                <th style={thStyle}>수량</th>
                <th style={thStyle}>가격</th>
                <th style={thStyle}>손익</th>
                <th style={thStyle}>수익률</th>
                <th style={thStyle}>메모</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td style={tdStyle}>{e.trade_date}</td>
                  <td style={tdStyle}>
                    {e.ticker_name || e.ticker}
                    <span style={{ color: "#999", fontSize: "0.75rem", marginLeft: 4 }}>
                      {e.ticker_name ? e.ticker : ""}
                    </span>
                  </td>
                  <td style={{ ...tdStyle, color: e.side === "BUY" ? "#e74c3c" : "#3498db", fontWeight: 600 }}>
                    {e.side === "BUY" ? "매수" : "매도"}
                  </td>
                  <td style={tdStyle}>{e.quantity.toLocaleString()}</td>
                  <td style={tdStyle}>{e.price.toLocaleString()}원</td>
                  <td
                    style={{
                      ...tdStyle,
                      color: (e.pnl ?? 0) >= 0 ? "#e74c3c" : "#3498db",
                      fontWeight: 600,
                    }}
                  >
                    {e.pnl != null ? `${e.pnl >= 0 ? "+" : ""}${e.pnl.toLocaleString()}원` : "-"}
                  </td>
                  <td
                    style={{
                      ...tdStyle,
                      color: (e.pnl_pct ?? 0) >= 0 ? "#e74c3c" : "#3498db",
                    }}
                  >
                    {e.pnl_pct != null
                      ? `${e.pnl_pct >= 0 ? "+" : ""}${e.pnl_pct.toFixed(2)}%`
                      : "-"}
                  </td>
                  <td style={{ ...tdStyle, color: "#666", maxWidth: 200 }}>
                    {e.notes || "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

const titleStyle: React.CSSProperties = {
  fontSize: "1.3rem",
  borderBottom: "2px solid #333",
  paddingBottom: "0.5rem",
  marginBottom: "1rem",
};

const thStyle: React.CSSProperties = {
  padding: "0.5rem 0.6rem",
  fontWeight: 600,
  fontSize: "0.8rem",
  color: "#555",
};

const tdStyle: React.CSSProperties = {
  padding: "0.5rem 0.6rem",
};
