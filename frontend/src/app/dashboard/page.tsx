"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

/* ── Types ── */
interface SupplyTrend {
  index_value: number;
  index_change_rate: number;
  foreign_net_buy: number;
  institution_net_buy: number;
  individual_net_buy: number;
  foreign_trend: string;
  institution_trend: string;
  snapshot_time: string;
}

interface NewsItem {
  id: number;
  title: string;
  source: string;
  impact_score: number;
  theme: string;
  is_leading: boolean;
  crawled_at: string;
}

interface SectorItem {
  sector_name: string;
  market: string;
  top3_avg_change_rate: number;
  sector_volume_ratio: number;
  is_leading: boolean;
  leader_ticker: string;
  leader_name: string;
  leader_change_rate: number;
}

interface AutoTradeStatus {
  enabled: boolean;
  is_virtual: boolean;
  daily_order_count: number;
  daily_order_amount: number;
  max_daily_orders: number;
  max_daily_amount: number;
}

/* ── Helpers ── */
function trendArrow(t: string) {
  if (t === "rising") return "▲";
  if (t === "falling") return "▼";
  return "―";
}

function trendCls(t: string) {
  if (t === "rising") return "text-up";
  if (t === "falling") return "text-down";
  return "text-flat";
}

function fmtNum(n: number) {
  if (Math.abs(n) >= 1_0000_0000) return (n / 1_0000_0000).toFixed(1) + "억";
  if (Math.abs(n) >= 1_0000) return (n / 1_0000).toFixed(0) + "만";
  return n.toLocaleString();
}

/* ── Component ── */
export default function DashboardPage() {
  const [token, setToken] = useState<string | null>(null);
  const [supply, setSupply] = useState<Record<string, SupplyTrend | null>>({});
  const [news, setNews] = useState<NewsItem[]>([]);
  const [sectors, setSectors] = useState<SectorItem[]>([]);
  const [trade, setTrade] = useState<AutoTradeStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setToken(typeof window !== "undefined" ? localStorage.getItem("token") : null);
  }, []);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    const [s, n, sec, t] = await Promise.allSettled([
      apiFetch<Record<string, SupplyTrend | null>>("/api/supply/trend", { token }),
      apiFetch<NewsItem[]>("/api/news?impact_min=8&limit=10", { token }),
      apiFetch<SectorItem[]>("/api/sectors/latest?limit=10&leading_only=false", { token }),
      apiFetch<AutoTradeStatus>("/api/auto-trade/status", { token }),
    ]);
    if (s.status === "fulfilled") setSupply(s.value);
    if (n.status === "fulfilled") setNews(n.value);
    if (sec.status === "fulfilled") setSectors(sec.value);
    if (t.status === "fulfilled") setTrade(t.value);
    setLoading(false);
  }, [token]);

  useEffect(() => {
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, [load]);

  /* ── Not logged in ── */
  if (!token) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-gray-500">
        <p className="text-lg">로그인이 필요합니다</p>
        <p className="mt-2 text-sm text-gray-600">JWT 토큰을 localStorage에 설정하세요</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Top: Market Index + Supply ── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {(["KOSPI", "KOSDAQ"] as const).map((mkt) => {
          const d = supply[mkt];
          return (
            <div key={mkt} className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-gray-400">{mkt}</span>
                {d ? (
                  <span className={`text-lg font-bold ${d.index_change_rate >= 0 ? "text-up" : "text-down"}`}>
                    {d.index_value.toFixed(2)}
                    <span className="ml-1 text-xs">
                      ({d.index_change_rate >= 0 ? "+" : ""}{d.index_change_rate.toFixed(2)}%)
                    </span>
                  </span>
                ) : (
                  <span className="text-sm text-gray-600">―</span>
                )}
              </div>
              {d && (
                <div className="mt-3 flex gap-4 text-xs text-gray-400">
                  <span>
                    외인 <span className={trendCls(d.foreign_trend)}>{trendArrow(d.foreign_trend)}</span>{" "}
                    {fmtNum(d.foreign_net_buy)}
                  </span>
                  <span>
                    기관 <span className={trendCls(d.institution_trend)}>{trendArrow(d.institution_trend)}</span>{" "}
                    {fmtNum(d.institution_net_buy)}
                  </span>
                  <span>개인 {fmtNum(d.individual_net_buy)}</span>
                </div>
              )}
            </div>
          );
        })}

        {/* Auto‑trade status */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
          <span className="text-xs font-medium text-gray-400">자동매매</span>
          {trade ? (
            <div className="mt-1">
              <span className={`text-sm font-bold ${trade.is_virtual ? "text-emerald-400" : "text-up"}`}>
                {trade.is_virtual ? "모의투자" : "실전"}
              </span>
              <p className="mt-1 text-xs text-gray-500">
                주문 {trade.daily_order_count}/{trade.max_daily_orders} &middot;{" "}
                {fmtNum(trade.daily_order_amount)}/{fmtNum(trade.max_daily_amount)}원
              </p>
            </div>
          ) : (
            <p className="mt-1 text-sm text-gray-600">미연결</p>
          )}
        </div>
      </div>

      {/* ── Body: News + Sectors ── */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Left: High‑impact news */}
        <section className="rounded-xl border border-gray-800 bg-gray-900/40 p-5">
          <h2 className="mb-4 text-sm font-semibold text-gray-300">핵심 뉴스 (영향도 8+)</h2>
          {loading && news.length === 0 ? (
            <p className="text-xs text-gray-600">로딩 중…</p>
          ) : news.length === 0 ? (
            <p className="text-xs text-gray-600">고영향 뉴스 없음</p>
          ) : (
            <ul className="space-y-3">
              {news.map((n) => (
                <li key={n.id} className="border-b border-gray-800/60 pb-3 last:border-0">
                  <div className="flex items-center gap-2">
                    <span className="inline-flex h-5 w-5 items-center justify-center rounded bg-red-500/20 text-[10px] font-bold text-red-400">
                      {n.impact_score}
                    </span>
                    {n.theme && (
                      <span className="rounded bg-blue-500/20 px-1.5 py-0.5 text-[10px] text-blue-400">
                        {n.theme}
                      </span>
                    )}
                    {n.is_leading && (
                      <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-400">주도</span>
                    )}
                  </div>
                  <p className="mt-1 text-sm leading-snug text-gray-200">{n.title}</p>
                  <span className="text-[10px] text-gray-600">
                    {n.source} · {new Date(n.crawled_at).toLocaleString("ko-KR")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Right: Sector ranking */}
        <section className="rounded-xl border border-gray-800 bg-gray-900/40 p-5">
          <h2 className="mb-4 text-sm font-semibold text-gray-300">섹터 강세 랭킹</h2>
          {loading && sectors.length === 0 ? (
            <p className="text-xs text-gray-600">로딩 중…</p>
          ) : sectors.length === 0 ? (
            <p className="text-xs text-gray-600">섹터 데이터 없음</p>
          ) : (
            <div className="space-y-2">
              {sectors.map((s, i) => (
                <div
                  key={s.sector_name}
                  className={`rounded-lg border px-3 py-2 ${
                    s.is_leading
                      ? "border-red-500/30 bg-red-500/5"
                      : "border-gray-800 bg-gray-900/30"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">#{i + 1}</span>
                    <span className="text-sm font-medium text-gray-200">{s.sector_name}</span>
                    {s.is_leading && (
                      <span className="rounded bg-red-500/20 px-1 py-0.5 text-[10px] text-red-400">주도</span>
                    )}
                    <span className="ml-auto text-[10px] text-gray-600">{s.market}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-4 text-xs text-gray-400">
                    <span>
                      Top3{" "}
                      <b className={s.top3_avg_change_rate >= 0 ? "text-up" : "text-down"}>
                        {s.top3_avg_change_rate >= 0 ? "+" : ""}
                        {s.top3_avg_change_rate.toFixed(2)}%
                      </b>
                    </span>
                    <span>거래대금비 {s.sector_volume_ratio.toFixed(0)}%</span>
                    <span className="ml-auto">
                      <span className="text-gray-600">대장</span>{" "}
                      {s.leader_name}{" "}
                      <b className={s.leader_change_rate >= 0 ? "text-up" : "text-down"}>
                        {s.leader_change_rate >= 0 ? "+" : ""}
                        {s.leader_change_rate.toFixed(2)}%
                      </b>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
