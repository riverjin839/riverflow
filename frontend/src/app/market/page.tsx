"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/use-auth";

/* ── Types ── */
interface IndexData {
  name: string;
  code: string;
  value: number;
  change: number;
  change_rate: number;
  high: number;
  low: number;
  volume: number;
}

interface MarketOverview {
  domestic: IndexData[];
  global: IndexData[];
  updated_at: string;
}

/* ── Component ── */
export default function MarketPage() {
  const { token, checked } = useAuth();
  const [data, setData] = useState<MarketOverview | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const d = await apiFetch<MarketOverview>("/api/market/overview", { token });
      setData(d);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [load]);

  if (!checked || !token) return null;

  return (
    <div className="space-y-8">
      <h1 className="text-lg font-bold text-gray-200">시황 개요</h1>

      {loading && !data ? (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-600 border-t-blue-400" />
          데이터 로딩 중…
        </div>
      ) : !data ? (
        <p className="text-sm text-gray-600">시황 데이터를 불러올 수 없습니다</p>
      ) : (
        <>
          {/* 국내 지수 */}
          <section>
            <h2 className="mb-3 text-sm font-semibold text-gray-400">국내 지수</h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.domestic.map((idx) => (
                <IndexCard key={idx.code} data={idx} />
              ))}
            </div>
          </section>

          {/* 해외 지수 */}
          <section>
            <h2 className="mb-3 text-sm font-semibold text-gray-400">해외 지수</h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.global.map((idx) => (
                <IndexCard key={idx.code} data={idx} />
              ))}
            </div>
          </section>

          <p className="text-right text-[10px] text-gray-700">
            마지막 업데이트: {new Date(data.updated_at).toLocaleString("ko-KR")}
          </p>
        </>
      )}
    </div>
  );
}

function IndexCard({ data }: { data: IndexData }) {
  const isUp = data.change_rate >= 0;
  const color = data.change_rate > 0 ? "text-up" : data.change_rate < 0 ? "text-down" : "text-flat";
  const bg = data.change_rate > 0
    ? "border-red-500/20 bg-red-500/5"
    : data.change_rate < 0
      ? "border-blue-500/20 bg-blue-500/5"
      : "border-gray-800 bg-gray-900/60";

  return (
    <div className={`rounded-xl border p-4 transition-colors ${bg}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-500">{data.name}</p>
          <p className={`mt-1 text-xl font-bold tabular-nums ${color}`}>
            {data.value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
        </div>
        <div className={`text-right ${color}`}>
          <p className="text-sm font-semibold tabular-nums">
            {isUp ? "+" : ""}{data.change.toFixed(2)}
          </p>
          <p className="text-xs tabular-nums">
            {isUp ? "+" : ""}{data.change_rate.toFixed(2)}%
          </p>
        </div>
      </div>
      <div className="mt-3 flex gap-4 text-[10px] text-gray-600">
        <span>고가 {data.high.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
        <span>저가 {data.low.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
        {data.volume > 0 && <span>거래량 {(data.volume / 10000).toFixed(0)}만</span>}
      </div>
    </div>
  );
}
