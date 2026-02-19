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
  rsi: number | null;
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
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async (manual = false) => {
      if (!token) return;
      if (manual) setRefreshing(true);
      else setLoading(true);
      try {
        const d = await apiFetch<MarketOverview>("/api/market/overview", { token });
        setData(d);
      } catch {
        // ignore
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [token],
  );

  useEffect(() => {
    load();
    const id = setInterval(() => load(), 30_000);
    return () => clearInterval(id);
  }, [load]);

  if (!checked || !token) return null;

  return (
    <div className="space-y-8">
      {/* 헤더 + 새로고침 */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-gray-200">시황 개요</h1>
        <div className="flex items-center gap-3">
          {data && (
            <span className="text-[10px] text-gray-600">
              {new Date(data.updated_at).toLocaleString("ko-KR")}
            </span>
          )}
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-800/60 px-3 py-1.5 text-xs text-gray-300 transition-colors hover:border-gray-600 hover:bg-gray-800 disabled:opacity-50"
          >
            <svg
              className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            새로고침
          </button>
        </div>
      </div>

      {loading && !data ? (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-600 border-t-blue-400" />
          데이터 로딩 중...
        </div>
      ) : !data ? (
        <p className="text-sm text-gray-600">시황 데이터를 불러올 수 없습니다</p>
      ) : (
        <>
          {/* 국내 지수 */}
          <section>
            <h2 className="mb-3 text-sm font-semibold text-gray-400">국내 지수</h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {data.domestic.map((idx) => (
                <IndexCard key={idx.code} data={idx} />
              ))}
            </div>
          </section>

          {/* 해외 지수 */}
          <section>
            <h2 className="mb-3 text-sm font-semibold text-gray-400">해외 지수</h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {data.global.map((idx) => (
                <IndexCard key={idx.code} data={idx} />
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

/* ── RSI 라벨 ── */
function rsiLabel(rsi: number): { text: string; cls: string } {
  if (rsi >= 70) return { text: "과매수", cls: "text-red-400 bg-red-500/15" };
  if (rsi >= 60) return { text: "강세", cls: "text-orange-400 bg-orange-500/15" };
  if (rsi <= 30) return { text: "과매도", cls: "text-blue-400 bg-blue-500/15" };
  if (rsi <= 40) return { text: "약세", cls: "text-cyan-400 bg-cyan-500/15" };
  return { text: "중립", cls: "text-gray-400 bg-gray-500/15" };
}

/* ── RSI 바 ── */
function RsiBar({ rsi }: { rsi: number }) {
  const label = rsiLabel(rsi);
  const pct = Math.min(Math.max(rsi, 0), 100);
  const barColor =
    rsi >= 70
      ? "bg-red-500"
      : rsi >= 60
        ? "bg-orange-500"
        : rsi <= 30
          ? "bg-blue-500"
          : rsi <= 40
            ? "bg-cyan-500"
            : "bg-gray-500";

  return (
    <div className="mt-3 pt-2 border-t border-gray-800/50">
      <div className="flex items-center justify-between text-[10px]">
        <span className="text-gray-500">RSI(14)</span>
        <span className={`rounded px-1.5 py-0.5 font-medium ${label.cls}`}>
          {rsi.toFixed(1)} {label.text}
        </span>
      </div>
      <div className="relative mt-1 h-1.5 w-full overflow-hidden rounded-full bg-gray-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-0.5 flex justify-between text-[8px] text-gray-700">
        <span>0</span>
        <span className="ml-[28%]">30</span>
        <span className="ml-auto mr-[28%]">70</span>
        <span>100</span>
      </div>
    </div>
  );
}

/* ── IndexCard ── */
function IndexCard({ data }: { data: IndexData }) {
  const color =
    data.change_rate > 0
      ? "text-up"
      : data.change_rate < 0
        ? "text-down"
        : "text-flat";
  const bg =
    data.change_rate > 0
      ? "border-red-500/20 bg-red-500/5"
      : data.change_rate < 0
        ? "border-blue-500/20 bg-blue-500/5"
        : "border-gray-800 bg-gray-900/60";
  const isUp = data.change_rate >= 0;
  const noData = data.value === 0;

  return (
    <div className={`rounded-xl border p-4 transition-colors ${bg}`}>
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <p className="truncate text-xs text-gray-500">{data.name}</p>
          {noData ? (
            <p className="mt-1 text-sm text-gray-600">데이터 없음</p>
          ) : (
            <p className={`mt-1 text-xl font-bold tabular-nums ${color}`}>
              {data.value.toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </p>
          )}
        </div>
        {!noData && (
          <div className={`text-right ${color}`}>
            <p className="text-sm font-semibold tabular-nums">
              {isUp ? "+" : ""}
              {data.change.toFixed(2)}
            </p>
            <p className="text-xs tabular-nums">
              {isUp ? "+" : ""}
              {data.change_rate.toFixed(2)}%
            </p>
          </div>
        )}
      </div>

      {!noData && (
        <div className="mt-2 flex gap-4 text-[10px] text-gray-600">
          <span>
            고가 {data.high.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </span>
          <span>
            저가 {data.low.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </span>
          {data.volume > 0 && (
            <span>
              거래량{" "}
              {data.volume >= 10000
                ? (data.volume / 10000).toFixed(0) + "만"
                : data.volume.toLocaleString()}
            </span>
          )}
        </div>
      )}

      {/* RSI 바 */}
      {data.rsi != null && <RsiBar rsi={data.rsi} />}
    </div>
  );
}
