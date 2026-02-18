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
}

export default function JournalPage() {
  const [token, setToken] = useState<string | null>(null);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setToken(typeof window !== "undefined" ? localStorage.getItem("token") : null);
  }, []);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const d = await apiFetch<JournalEntry[]>("/api/journal", { token });
      setEntries(d);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  if (!token) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-gray-500">
        <p className="text-lg">로그인이 필요합니다</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-gray-200">매매일지</h1>

      {loading ? (
        <p className="text-sm text-gray-600">로딩 중…</p>
      ) : entries.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-gray-600">
          <p>매매일지가 비어있습니다</p>
          <p className="mt-1 text-xs text-gray-700">자동매매 또는 수동 기록을 시작하면 여기에 표시됩니다</p>
        </div>
      ) : (
        <div className="overflow-auto rounded-xl border border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-900/60 text-left text-xs text-gray-500">
                <th className="px-4 py-2.5">날짜</th>
                <th className="px-4 py-2.5">종목</th>
                <th className="px-4 py-2.5">매매</th>
                <th className="px-4 py-2.5 text-right">수량</th>
                <th className="px-4 py-2.5 text-right">가격</th>
                <th className="px-4 py-2.5 text-right">손익</th>
                <th className="px-4 py-2.5 text-right">수익률</th>
                <th className="px-4 py-2.5">메모</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const pnlColor = (e.pnl ?? 0) >= 0 ? "text-up" : "text-down";
                return (
                  <tr key={e.id} className="border-b border-gray-800/50 hover:bg-gray-900/40 transition-colors">
                    <td className="px-4 py-2 text-gray-400">{e.trade_date}</td>
                    <td className="px-4 py-2">
                      <span className="text-gray-200">{e.ticker_name || e.ticker}</span>
                      {e.ticker_name && <span className="ml-1 text-[10px] text-gray-600">{e.ticker}</span>}
                    </td>
                    <td className={`px-4 py-2 font-medium ${e.side === "BUY" ? "text-up" : "text-down"}`}>
                      {e.side === "BUY" ? "매수" : "매도"}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-gray-300">{e.quantity.toLocaleString()}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-gray-300">{e.price.toLocaleString()}</td>
                    <td className={`px-4 py-2 text-right tabular-nums font-medium ${pnlColor}`}>
                      {e.pnl != null ? `${e.pnl >= 0 ? "+" : ""}${e.pnl.toLocaleString()}` : "―"}
                    </td>
                    <td className={`px-4 py-2 text-right tabular-nums ${pnlColor}`}>
                      {e.pnl_pct != null ? `${e.pnl_pct >= 0 ? "+" : ""}${e.pnl_pct.toFixed(2)}%` : "―"}
                    </td>
                    <td className="max-w-[200px] truncate px-4 py-2 text-gray-600">{e.notes || "―"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
