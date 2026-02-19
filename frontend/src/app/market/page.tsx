"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/use-auth";

/* ── Types ── */
interface IndexData {
  name: string;
  code: string;
  link?: string;
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
interface ChartPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/* ── Page ── */
export default function MarketPage() {
  const { token, checked } = useAuth();
  const [data, setData] = useState<MarketOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [chartTarget, setChartTarget] = useState<IndexData | null>(null);
  const [customCodes, setCustomCodes] = useState<string[]>([]);
  const [customCards, setCustomCards] = useState<IndexData[]>([]);
  const [addInput, setAddInput] = useState("");
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState("");

  // localStorage에서 커스텀 종목 로드
  useEffect(() => {
    const saved = localStorage.getItem("market_custom_codes");
    if (saved) setCustomCodes(JSON.parse(saved));
  }, []);

  const load = useCallback(
    async (manual = false) => {
      if (!token) return;
      if (manual) setRefreshing(true);
      else setLoading(true);
      setError("");
      try {
        const d = await apiFetch<MarketOverview>("/api/market/overview", { token });
        setData(d);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [token],
  );

  // 커스텀 종목 로드
  const loadCustom = useCallback(async () => {
    if (!token || customCodes.length === 0) { setCustomCards([]); return; }
    const results = await Promise.allSettled(
      customCodes.map((c) => apiFetch<IndexData>(`/api/market/quote?code=${c}`, { token })),
    );
    const cards: IndexData[] = [];
    results.forEach((r) => {
      if (r.status === "fulfilled" && !("error" in r.value) && r.value.value > 0) cards.push(r.value);
    });
    setCustomCards(cards);
  }, [token, customCodes]);

  useEffect(() => { load(); const id = setInterval(() => load(), 30_000); return () => clearInterval(id); }, [load]);
  useEffect(() => { loadCustom(); }, [loadCustom]);

  const addCustom = async () => {
    const code = addInput.trim();
    if (!code || !token) return;
    setAddLoading(true);
    setAddError("");
    try {
      const r = await apiFetch<IndexData & { error?: string }>(`/api/market/quote?code=${code}`, { token });
      if ("error" in r && r.error) { setAddError(r.error); return; }
      const next = [...customCodes.filter((c) => c !== code), code];
      setCustomCodes(next);
      localStorage.setItem("market_custom_codes", JSON.stringify(next));
      setAddInput("");
    } catch { setAddError("조회 실패"); } finally { setAddLoading(false); }
  };

  const removeCustom = (code: string) => {
    const next = customCodes.filter((c) => c !== code);
    setCustomCodes(next);
    localStorage.setItem("market_custom_codes", JSON.stringify(next));
    setCustomCards((prev) => prev.filter((c) => c.code !== code));
  };

  if (!checked || !token) return null;

  return (
    <div className="space-y-8">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-gray-200">시황 개요</h1>
        <div className="flex items-center gap-3">
          {data && <span className="text-[10px] text-gray-600">{new Date(data.updated_at).toLocaleString("ko-KR")}</span>}
          <button onClick={() => { load(true); loadCustom(); }} disabled={refreshing}
            className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-800/60 px-3 py-1.5 text-xs text-gray-300 transition-colors hover:border-gray-600 hover:bg-gray-800 disabled:opacity-50">
            <svg className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
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
        <div className="space-y-2">
          <p className="text-sm text-gray-600">시황 데이터를 불러올 수 없습니다</p>
          {error && <p className="text-xs text-red-400">오류: {error}</p>}
          <button onClick={() => load(true)} className="rounded bg-gray-800 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-700">
            다시 시도
          </button>
        </div>
      ) : (
        <>
          <Section title="국내 지수" items={data.domestic} token={token} onChart={setChartTarget} />
          <Section title="해외 지수" items={data.global} token={token} onChart={setChartTarget} />
        </>
      )}

      {/* 커스텀 종목 */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-400">관심 종목</h2>
        </div>
        {customCards.length > 0 && (
          <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {customCards.map((idx) => (
              <IndexCard key={idx.code} data={idx} token={token} onChart={setChartTarget}
                onRemove={() => removeCustom(idx.code)} />
            ))}
          </div>
        )}
        <div className="flex items-center gap-2">
          <input value={addInput} onChange={(e) => { setAddInput(e.target.value); setAddError(""); }}
            onKeyDown={(e) => e.key === "Enter" && addCustom()}
            placeholder="종목코드 입력 (예: 005930, 035720)"
            className="w-56 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500" />
          <button onClick={addCustom} disabled={addLoading || !addInput.trim()}
            className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-40">
            {addLoading ? "..." : "+ 추가"}
          </button>
          {addError && <span className="text-xs text-red-400">{addError}</span>}
        </div>
      </section>

      {/* 차트 모달 */}
      {chartTarget && <ChartModal data={chartTarget} token={token} onClose={() => setChartTarget(null)} />}
    </div>
  );
}

/* ── Section ── */
function Section({ title, items, token, onChart }: { title: string; items: IndexData[]; token: string; onChart: (d: IndexData) => void }) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-gray-400">{title}</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((idx) => <IndexCard key={idx.code} data={idx} token={token} onChart={onChart} />)}
      </div>
    </section>
  );
}

/* ── RSI ── */
function rsiLabel(rsi: number) {
  if (rsi >= 70) return { text: "과매수", cls: "text-red-400 bg-red-500/15" };
  if (rsi >= 60) return { text: "강세", cls: "text-orange-400 bg-orange-500/15" };
  if (rsi <= 30) return { text: "과매도", cls: "text-blue-400 bg-blue-500/15" };
  if (rsi <= 40) return { text: "약세", cls: "text-cyan-400 bg-cyan-500/15" };
  return { text: "중립", cls: "text-gray-400 bg-gray-500/15" };
}
function RsiBar({ rsi }: { rsi: number }) {
  const label = rsiLabel(rsi);
  const pct = Math.min(Math.max(rsi, 0), 100);
  const barColor = rsi >= 70 ? "bg-red-500" : rsi >= 60 ? "bg-orange-500" : rsi <= 30 ? "bg-blue-500" : rsi <= 40 ? "bg-cyan-500" : "bg-gray-500";
  return (
    <div className="mt-3 pt-2 border-t border-gray-800/50">
      <div className="flex items-center justify-between text-[10px]">
        <span className="text-gray-500">RSI(14)</span>
        <span className={`rounded px-1.5 py-0.5 font-medium ${label.cls}`}>{rsi.toFixed(1)} {label.text}</span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-gray-800">
        <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/* ── IndexCard ── */
function IndexCard({ data, token, onChart, onRemove }: { data: IndexData; token: string; onChart: (d: IndexData) => void; onRemove?: () => void }) {
  const color = data.change_rate > 0 ? "text-up" : data.change_rate < 0 ? "text-down" : "text-flat";
  const bg = data.change_rate > 0 ? "border-red-500/20 bg-red-500/5" : data.change_rate < 0 ? "border-blue-500/20 bg-blue-500/5" : "border-gray-800 bg-gray-900/60";
  const isUp = data.change_rate >= 0;
  const noData = data.value === 0;

  return (
    <div className={`group relative rounded-xl border p-4 transition-colors cursor-pointer hover:brightness-110 ${bg}`}
      onClick={() => !noData && onChart(data)}>
      {/* 액션 버튼 (우상단) */}
      <div className="absolute right-2 top-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {data.link && (
          <a href={data.link} target="_blank" rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="rounded p-1 text-gray-500 hover:bg-gray-700 hover:text-gray-300" title="Naver Finance에서 보기">
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
        )}
        {onRemove && (
          <button onClick={(e) => { e.stopPropagation(); onRemove(); }}
            className="rounded p-1 text-gray-500 hover:bg-red-900/40 hover:text-red-400" title="삭제">
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      <div className="flex items-start justify-between">
        <div className="min-w-0 pr-6">
          <p className="truncate text-xs text-gray-500">{data.name}</p>
          {noData ? (
            <p className="mt-1 text-sm text-gray-600">데이터 없음</p>
          ) : (
            <p className={`mt-1 text-xl font-bold tabular-nums ${color}`}>
              {data.value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          )}
        </div>
        {!noData && (
          <div className={`text-right ${color}`}>
            <p className="text-sm font-semibold tabular-nums">{isUp ? "+" : ""}{data.change.toFixed(2)}</p>
            <p className="text-xs tabular-nums">{isUp ? "+" : ""}{data.change_rate.toFixed(2)}%</p>
          </div>
        )}
      </div>
      {!noData && (
        <div className="mt-2 flex gap-4 text-[10px] text-gray-600">
          {data.high > 0 && <span>고가 {data.high.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>}
          {data.low > 0 && <span>저가 {data.low.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>}
          {data.volume > 0 && <span>거래량 {data.volume >= 10000 ? (data.volume / 10000).toFixed(0) + "만" : data.volume.toLocaleString()}</span>}
        </div>
      )}
      {data.rsi != null && <RsiBar rsi={data.rsi} />}
    </div>
  );
}

/* ── Sparkline SVG ── */
function Sparkline({ prices, width = 600, height = 200 }: { prices: ChartPoint[]; width?: number; height?: number }) {
  if (prices.length < 2) return null;
  const closes = prices.map((p) => p.close);
  const min = Math.min(...closes) * 0.999;
  const max = Math.max(...closes) * 1.001;
  const range = max - min || 1;
  const pad = 4;

  const points = closes.map((c, i) => {
    const x = pad + (i / (closes.length - 1)) * (width - pad * 2);
    const y = pad + (1 - (c - min) / range) * (height - pad * 2);
    return `${x},${y}`;
  }).join(" ");

  const isUp = closes[closes.length - 1] >= closes[0];
  const strokeColor = isUp ? "#ef4444" : "#3b82f6";
  const fillColor = isUp ? "rgba(239,68,68,0.08)" : "rgba(59,130,246,0.08)";

  // Area fill path
  const firstX = pad;
  const lastX = pad + ((closes.length - 1) / (closes.length - 1)) * (width - pad * 2);
  const areaPath = `M${firstX},${height} L${points.replace(/ /g, " L")} L${lastX},${height} Z`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" preserveAspectRatio="none">
      <path d={areaPath} fill={fillColor} />
      <polyline points={points} fill="none" stroke={strokeColor} strokeWidth="2" strokeLinejoin="round" />
      {/* 눈금선 */}
      {[0.25, 0.5, 0.75].map((pct) => {
        const y = pad + pct * (height - pad * 2);
        return <line key={pct} x1={pad} x2={width - pad} y1={y} y2={y} stroke="#374151" strokeWidth="0.5" />;
      })}
    </svg>
  );
}

/* ── Chart Modal ── */
function ChartModal({ data, token, onClose }: { data: IndexData; token: string; onClose: () => void }) {
  const [prices, setPrices] = useState<ChartPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  const isCustomStock = /^\d{6}$/.test(data.code);
  const chartType = isCustomStock ? "stock" : data.code.includes("@") ? "global" : "domestic";

  useEffect(() => {
    setLoading(true);
    apiFetch<{ prices: ChartPoint[] }>(`/api/market/chart?code=${encodeURIComponent(data.code)}&type=${chartType}&days=${days}`, { token })
      .then((r) => setPrices(r.prices || []))
      .catch(() => setPrices([]))
      .finally(() => setLoading(false));
  }, [data.code, chartType, days, token]);

  const color = data.change_rate > 0 ? "text-up" : data.change_rate < 0 ? "text-down" : "text-flat";
  const isUp = data.change_rate >= 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="mx-4 w-full max-w-2xl rounded-2xl border border-gray-700 bg-gray-900 p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* 헤더 */}
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h3 className="text-lg font-bold text-gray-200">{data.name}</h3>
            <div className="mt-1 flex items-baseline gap-3">
              <span className={`text-2xl font-bold tabular-nums ${color}`}>
                {data.value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span className={`text-sm tabular-nums ${color}`}>
                {isUp ? "+" : ""}{data.change.toFixed(2)} ({isUp ? "+" : ""}{data.change_rate.toFixed(2)}%)
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {data.link && (
              <a href={data.link} target="_blank" rel="noopener noreferrer"
                className="rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-400 hover:border-gray-500 hover:text-gray-200">
                상세 보기 ↗
              </a>
            )}
            <button onClick={onClose} className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-800 hover:text-gray-300">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 기간 선택 */}
        <div className="mb-3 flex gap-1">
          {[{ d: 7, l: "1주" }, { d: 30, l: "1개월" }, { d: 60, l: "2개월" }, { d: 90, l: "3개월" }].map(({ d, l }) => (
            <button key={d} onClick={() => setDays(d)}
              className={`rounded px-2.5 py-1 text-xs transition-colors ${days === d ? "bg-blue-600 text-white" : "text-gray-500 hover:bg-gray-800 hover:text-gray-300"}`}>
              {l}
            </button>
          ))}
        </div>

        {/* 차트 */}
        <div className="h-52 rounded-xl border border-gray-800 bg-gray-950 p-2">
          {loading ? (
            <div className="flex h-full items-center justify-center text-sm text-gray-600">차트 로딩 중...</div>
          ) : prices.length < 2 ? (
            <div className="flex h-full items-center justify-center text-sm text-gray-600">차트 데이터 없음</div>
          ) : (
            <Sparkline prices={prices} />
          )}
        </div>

        {/* 하단 정보 */}
        <div className="mt-3 flex flex-wrap gap-4 text-xs text-gray-500">
          {data.high > 0 && <span>고가 <b className="text-gray-300">{data.high.toLocaleString(undefined, { maximumFractionDigits: 2 })}</b></span>}
          {data.low > 0 && <span>저가 <b className="text-gray-300">{data.low.toLocaleString(undefined, { maximumFractionDigits: 2 })}</b></span>}
          {data.volume > 0 && <span>거래량 <b className="text-gray-300">{data.volume >= 10000 ? (data.volume / 10000).toFixed(0) + "만" : data.volume.toLocaleString()}</b></span>}
          {data.rsi != null && <span>RSI(14) <b className={rsiLabel(data.rsi).cls.split(" ")[0]}>{data.rsi.toFixed(1)}</b></span>}
        </div>
      </div>
    </div>
  );
}
