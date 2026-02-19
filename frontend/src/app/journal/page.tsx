"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/use-auth";

/* ── Types ── */
interface JournalEntry {
  id: number;
  trade_date: string;
  ticker: string;
  ticker_name: string | null;
  buy_price: number | null;
  sell_price: number | null;
  quantity: number | null;
  profit_rate: number | null;
  buy_reason: string | null;
  ai_feedback: string | null;
  tags: string[] | null;
}

interface KISTrade {
  order_date: string;
  ticker: string;
  ticker_name: string;
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  total_amount: number;
  order_id: string;
  selected?: boolean;
}

interface StockSearchResult {
  ticker: string;
  ticker_name: string;
  market: string;
}

const EMPTY_FORM = {
  trade_date: new Date().toISOString().split("T")[0],
  ticker: "",
  ticker_name: "",
  buy_price: "",
  sell_price: "",
  quantity: "",
  buy_reason: "",
  tags: "",
};

function formatDate(d: Date) { return d.toISOString().split("T")[0].replace(/-/g, ""); }

export default function JournalPage() {
  const { token, checked } = useAuth();
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [detail, setDetail] = useState<JournalEntry | null>(null);

  // KIS 가져오기
  const [showKIS, setShowKIS] = useState(false);
  const [kisTrades, setKisTrades] = useState<KISTrade[]>([]);
  const [kisLoading, setKisLoading] = useState(false);
  const [kisError, setKisError] = useState("");
  const [kisImporting, setKisImporting] = useState(false);
  const today = new Date().toISOString().split("T")[0];
  const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().split("T")[0];
  const [kisStart, setKisStart] = useState(weekAgo);
  const [kisEnd, setKisEnd] = useState(today);

  // 종목 검색
  const [stockQuery, setStockQuery] = useState("");
  const [stockResults, setStockResults] = useState<StockSearchResult[]>([]);
  const [stockSearching, setStockSearching] = useState(false);
  const [showStockDropdown, setShowStockDropdown] = useState(false);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const searchStock = useCallback(async (query: string) => {
    if (!token || query.length === 0) {
      setStockResults([]);
      return;
    }
    setStockSearching(true);
    try {
      const r = await apiFetch<{ results: StockSearchResult[] }>(
        `/api/journal/search-stock?q=${encodeURIComponent(query)}`, { token },
      );
      setStockResults(r.results);
      setShowStockDropdown(r.results.length > 0);
    } catch {
      setStockResults([]);
    } finally {
      setStockSearching(false);
    }
  }, [token]);

  const handleStockQueryChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setStockQuery(val);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    if (val.length > 0) {
      searchTimerRef.current = setTimeout(() => searchStock(val), 300);
    } else {
      setStockResults([]);
      setShowStockDropdown(false);
    }
  };

  const searchBoxRef = useRef<HTMLDivElement>(null);

  const selectStock = (item: StockSearchResult) => {
    setForm((prev) => ({ ...prev, ticker: item.ticker, ticker_name: item.ticker_name }));
    setStockQuery(`${item.ticker_name} (${item.ticker})`);
    setShowStockDropdown(false);
    setStockResults([]);
  };

  // 드롭다운 외부 클릭 시 닫기
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchBoxRef.current && !searchBoxRef.current.contains(e.target as Node)) {
        setShowStockDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const fetchKIS = async () => {
    if (!token) return;
    setKisLoading(true);
    setKisError("");
    try {
      const start = kisStart.replace(/-/g, "");
      const end = kisEnd.replace(/-/g, "");
      const r = await apiFetch<{ trades: KISTrade[]; is_virtual: boolean }>(
        `/api/journal/kis-trades?start_date=${start}&end_date=${end}`, { token },
      );
      setKisTrades(r.trades.map((t) => ({ ...t, selected: true })));
      if (r.trades.length === 0) setKisError("해당 기간 체결 내역이 없습니다");
    } catch (err) {
      setKisError(err instanceof Error ? err.message : "조회 실패");
    } finally {
      setKisLoading(false);
    }
  };

  const toggleKISTrade = (idx: number) => {
    setKisTrades((prev) => prev.map((t, i) => i === idx ? { ...t, selected: !t.selected } : t));
  };

  const importKIS = async () => {
    if (!token) return;
    const selected = kisTrades.filter((t) => t.selected);
    if (selected.length === 0) return;
    setKisImporting(true);
    try {
      await apiFetch("/api/journal/import-kis", {
        token, method: "POST",
        body: JSON.stringify({ trades: selected }),
      });
      setShowKIS(false);
      setKisTrades([]);
      await load();
    } catch (err) {
      setKisError(err instanceof Error ? err.message : "등록 실패");
    } finally {
      setKisImporting(false);
    }
  };

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const d = await apiFetch<JournalEntry[]>("/api/journal", { token });
      setEntries(d);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setSubmitting(true);
    setSubmitError("");

    const buy = parseFloat(form.buy_price);
    const sell = parseFloat(form.sell_price);
    let profitRate: number | null = null;
    if (buy > 0 && sell > 0) {
      profitRate = parseFloat(((sell - buy) / buy * 100).toFixed(2));
    }

    const payload = {
      trade_date: form.trade_date,
      ticker: form.ticker,
      ticker_name: form.ticker_name || null,
      buy_price: buy || null,
      sell_price: sell || null,
      quantity: parseInt(form.quantity, 10) || null,
      profit_rate: profitRate,
      buy_reason: form.buy_reason || null,
      tags: form.tags ? form.tags.split(",").map((t) => t.trim()).filter(Boolean) : null,
    };

    try {
      await apiFetch("/api/journal", { token, method: "POST", body: JSON.stringify(payload) });
      setForm(EMPTY_FORM);
      setShowForm(false);
      await load();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "등록 실패");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!token || !confirm("삭제하시겠습니까?")) return;
    try {
      await apiFetch(`/api/journal/${id}`, { token, method: "DELETE" });
      setDetail(null);
      await load();
    } catch { /* ignore */ }
  };

  if (!checked || !token) return null;

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-gray-200">매매일지</h1>
        <div className="flex gap-2">
          <button
            onClick={() => { setShowKIS(!showKIS); setShowForm(false); }}
            className="rounded-lg border border-emerald-700 px-4 py-2 text-sm font-medium text-emerald-400 hover:bg-emerald-900/20 transition-colors"
          >
            {showKIS ? "닫기" : "KIS 체결 가져오기"}
          </button>
          <button
            onClick={() => {
              setShowForm(!showForm);
              setShowKIS(false);
              if (!showForm) { setStockQuery(""); setStockResults([]); setShowStockDropdown(false); }
            }}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
          >
            {showForm ? "취소" : "+ 수동 작성"}
          </button>
        </div>
      </div>

      {/* ── KIS 체결내역 가져오기 ── */}
      {showKIS && (
        <div className="rounded-xl border border-emerald-900/40 bg-emerald-950/10 p-5 space-y-4">
          <h2 className="text-sm font-semibold text-emerald-300">KIS 계좌 체결내역 가져오기</h2>

          <div className="flex items-end gap-3">
            <div>
              <label className="mb-1 block text-xs text-gray-500">시작일</label>
              <input type="date" value={kisStart} onChange={(e) => setKisStart(e.target.value)}
                className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 outline-none focus:border-emerald-500" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">종료일</label>
              <input type="date" value={kisEnd} onChange={(e) => setKisEnd(e.target.value)}
                className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 outline-none focus:border-emerald-500" />
            </div>
            <button onClick={fetchKIS} disabled={kisLoading}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40 transition-colors">
              {kisLoading ? "조회 중..." : "체결내역 조회"}
            </button>
          </div>

          {kisError && <p className="text-xs text-red-400">{kisError}</p>}

          {kisTrades.length > 0 && (
            <>
              <div className="overflow-auto rounded-lg border border-gray-800">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800 bg-gray-900/60 text-left text-xs text-gray-500">
                      <th className="px-3 py-2">
                        <input type="checkbox"
                          checked={kisTrades.every((t) => t.selected)}
                          onChange={() => {
                            const allSelected = kisTrades.every((t) => t.selected);
                            setKisTrades((prev) => prev.map((t) => ({ ...t, selected: !allSelected })));
                          }}
                          className="rounded" />
                      </th>
                      <th className="px-3 py-2">일자</th>
                      <th className="px-3 py-2">종목</th>
                      <th className="px-3 py-2">매매</th>
                      <th className="px-3 py-2 text-right">수량</th>
                      <th className="px-3 py-2 text-right">단가</th>
                      <th className="px-3 py-2 text-right">금액</th>
                    </tr>
                  </thead>
                  <tbody>
                    {kisTrades.map((t, i) => (
                      <tr key={`${t.order_id}-${i}`} className="border-b border-gray-800/50 hover:bg-gray-900/40">
                        <td className="px-3 py-2">
                          <input type="checkbox" checked={t.selected ?? false} onChange={() => toggleKISTrade(i)} className="rounded" />
                        </td>
                        <td className="px-3 py-2 text-gray-400">
                          {t.order_date ? `${t.order_date.slice(0,4)}-${t.order_date.slice(4,6)}-${t.order_date.slice(6,8)}` : "―"}
                        </td>
                        <td className="px-3 py-2">
                          <span className="text-gray-200">{t.ticker_name}</span>
                          <span className="ml-1 text-[10px] text-gray-600">{t.ticker}</span>
                        </td>
                        <td className={`px-3 py-2 font-medium ${t.side === "BUY" ? "text-up" : "text-down"}`}>
                          {t.side === "BUY" ? "매수" : "매도"}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-gray-300">{t.quantity.toLocaleString()}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-gray-300">{Math.round(t.price).toLocaleString()}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-gray-300">{t.total_amount.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">
                  {kisTrades.filter((t) => t.selected).length}/{kisTrades.length}건 선택
                </span>
                <button onClick={importKIS} disabled={kisImporting || kisTrades.filter((t) => t.selected).length === 0}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40 transition-colors">
                  {kisImporting ? "등록 중..." : `선택 항목 매매일지 등록 (${kisTrades.filter((t) => t.selected).length}건)`}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── 등록 폼 ── */}
      {showForm && (
        <form onSubmit={handleSubmit} className="rounded-xl border border-gray-800 bg-gray-900/60 p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-300">매매일지 작성</h2>

          {/* 날짜 */}
          <div>
            <label className="mb-1 block text-xs text-gray-500">매매 일자</label>
            <input type="date" name="trade_date" value={form.trade_date} onChange={handleChange} required
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 outline-none focus:border-blue-500" />
          </div>

          {/* 종목 검색 */}
          <div className="relative" ref={searchBoxRef}>
            <label className="mb-1 block text-xs text-gray-500">종목 검색 (코드 또는 이름)</label>
            <input
              type="text"
              value={stockQuery}
              onChange={handleStockQueryChange}
              onFocus={() => { if (stockResults.length > 0) setShowStockDropdown(true); }}
              placeholder="종목코드(005930) 또는 종목명(삼성전자) 입력"
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500"
            />
            {stockSearching && (
              <div className="absolute right-3 top-[30px] text-xs text-gray-500">검색중...</div>
            )}
            {showStockDropdown && stockResults.length > 0 && (
              <div className="absolute z-20 mt-1 w-full max-h-60 overflow-auto rounded-lg border border-gray-700 bg-gray-800 shadow-xl">
                {stockResults.map((item) => (
                  <button
                    key={item.ticker}
                    type="button"
                    onClick={() => selectStock(item)}
                    className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm hover:bg-gray-700/60 transition-colors"
                  >
                    <div>
                      <span className="font-medium text-gray-200">{item.ticker_name}</span>
                      <span className="ml-2 text-xs text-gray-500">{item.ticker}</span>
                    </div>
                    {item.market && (
                      <span className="rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-400">{item.market}</span>
                    )}
                  </button>
                ))}
              </div>
            )}
            {form.ticker && (
              <div className="mt-1.5 flex items-center gap-2">
                <span className="rounded-lg bg-blue-900/30 px-2 py-1 text-xs text-blue-300">
                  {form.ticker_name || form.ticker} ({form.ticker})
                </span>
                <button type="button" onClick={() => {
                  setForm((prev) => ({ ...prev, ticker: "", ticker_name: "" }));
                  setStockQuery("");
                }} className="text-xs text-gray-500 hover:text-gray-300">초기화</button>
              </div>
            )}
          </div>

          {/* 매수가 / 매도가 / 수량 */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-xs text-gray-500">매수 단가</label>
              <input type="number" name="buy_price" value={form.buy_price} onChange={handleChange} placeholder="0"
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">매도 단가</label>
              <input type="number" name="sell_price" value={form.sell_price} onChange={handleChange} placeholder="미매도 시 공란"
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">수량</label>
              <input type="number" name="quantity" value={form.quantity} onChange={handleChange} placeholder="0"
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500" />
            </div>
          </div>

          {/* 수익률 미리보기 */}
          {form.buy_price && form.sell_price && (
            <div className="text-xs text-gray-500">
              예상 수익률:{" "}
              <span className={parseFloat(form.sell_price) >= parseFloat(form.buy_price) ? "text-up font-bold" : "text-down font-bold"}>
                {(((parseFloat(form.sell_price) - parseFloat(form.buy_price)) / parseFloat(form.buy_price)) * 100).toFixed(2)}%
              </span>
            </div>
          )}

          {/* 매수 이유 */}
          <div>
            <label className="mb-1 block text-xs text-gray-500">매수 이유 및 복기</label>
            <textarea name="buy_reason" value={form.buy_reason} onChange={handleChange} rows={4}
              placeholder="어떤 재료나 패턴을 보고 들어갔는지, 시장 분위기는 어땠는지 구체적으로 적어보자."
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 resize-y" />
          </div>

          {/* 태그 */}
          <div>
            <label className="mb-1 block text-xs text-gray-500">태그 (쉼표 구분)</label>
            <input type="text" name="tags" value={form.tags} onChange={handleChange} placeholder="돌파매매, 단기과열, 반도체"
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500" />
          </div>

          {submitError && <p className="text-xs text-red-400">{submitError}</p>}

          <button type="submit" disabled={submitting || !form.ticker}
            className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-40 transition-colors">
            {submitting ? "등록 중..." : "매매일지 등록"}
          </button>
        </form>
      )}

      {/* ── 목록 ── */}
      {loading ? (
        <p className="text-sm text-gray-600">로딩 중...</p>
      ) : entries.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-gray-600">
          <p>매매일지가 비어있습니다</p>
          <p className="mt-1 text-xs text-gray-700">&quot;새 일지 작성&quot; 버튼으로 첫 매매일지를 등록하세요</p>
        </div>
      ) : (
        <div className="overflow-auto rounded-xl border border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-900/60 text-left text-xs text-gray-500">
                <th className="px-4 py-2.5">날짜</th>
                <th className="px-4 py-2.5">종목</th>
                <th className="px-4 py-2.5 text-right">매수가</th>
                <th className="px-4 py-2.5 text-right">매도가</th>
                <th className="px-4 py-2.5 text-right">수량</th>
                <th className="px-4 py-2.5 text-right">수익률</th>
                <th className="px-4 py-2.5">태그</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const rate = e.profit_rate ?? 0;
                const rateColor = rate > 0 ? "text-up" : rate < 0 ? "text-down" : "text-flat";
                return (
                  <tr key={e.id}
                    className="border-b border-gray-800/50 hover:bg-gray-900/40 transition-colors cursor-pointer"
                    onClick={() => setDetail(e)}>
                    <td className="px-4 py-2.5 text-gray-400">{e.trade_date}</td>
                    <td className="px-4 py-2.5">
                      <span className="text-gray-200">{e.ticker_name || e.ticker}</span>
                      {e.ticker_name && <span className="ml-1 text-[10px] text-gray-600">{e.ticker}</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-gray-300">
                      {e.buy_price != null ? e.buy_price.toLocaleString() : "―"}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-gray-300">
                      {e.sell_price != null ? e.sell_price.toLocaleString() : "―"}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-gray-300">
                      {e.quantity != null ? e.quantity.toLocaleString() : "―"}
                    </td>
                    <td className={`px-4 py-2.5 text-right tabular-nums font-medium ${rateColor}`}>
                      {e.profit_rate != null ? `${rate >= 0 ? "+" : ""}${rate.toFixed(2)}%` : "―"}
                    </td>
                    <td className="px-4 py-2.5">
                      {e.tags && e.tags.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {e.tags.map((t) => (
                            <span key={t} className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-400">{t}</span>
                          ))}
                        </div>
                      ) : "―"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── 상세 모달 ── */}
      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setDetail(null)}>
          <div className="mx-4 w-full max-w-lg rounded-2xl border border-gray-700 bg-gray-900 p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-start justify-between">
              <div>
                <h3 className="text-lg font-bold text-gray-200">
                  {detail.ticker_name || detail.ticker}
                  {detail.ticker_name && <span className="ml-2 text-sm text-gray-500">{detail.ticker}</span>}
                </h3>
                <p className="text-xs text-gray-500">{detail.trade_date}</p>
              </div>
              <button onClick={() => setDetail(null)} className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-800 hover:text-gray-300">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-4">
              <div>
                <p className="text-[10px] text-gray-500">매수가</p>
                <p className="text-sm font-bold text-gray-200">{detail.buy_price != null ? detail.buy_price.toLocaleString() : "―"}</p>
              </div>
              <div>
                <p className="text-[10px] text-gray-500">매도가</p>
                <p className="text-sm font-bold text-gray-200">{detail.sell_price != null ? detail.sell_price.toLocaleString() : "―"}</p>
              </div>
              <div>
                <p className="text-[10px] text-gray-500">수량</p>
                <p className="text-sm font-bold text-gray-200">{detail.quantity != null ? detail.quantity.toLocaleString() : "―"}</p>
              </div>
            </div>

            {detail.profit_rate != null && (
              <div className="mb-4">
                <p className="text-[10px] text-gray-500">수익률</p>
                <p className={`text-xl font-bold ${detail.profit_rate >= 0 ? "text-up" : "text-down"}`}>
                  {detail.profit_rate >= 0 ? "+" : ""}{detail.profit_rate.toFixed(2)}%
                </p>
              </div>
            )}

            {detail.buy_reason && (
              <div className="mb-4">
                <p className="mb-1 text-[10px] text-gray-500">매수 이유 / 복기</p>
                <p className="whitespace-pre-wrap rounded-lg border border-gray-800 bg-gray-950 p-3 text-sm text-gray-300">{detail.buy_reason}</p>
              </div>
            )}

            {detail.ai_feedback && (
              <div className="mb-4">
                <p className="mb-1 text-[10px] text-gray-500">AI 피드백</p>
                <p className="whitespace-pre-wrap rounded-lg border border-blue-900/30 bg-blue-950/20 p-3 text-sm text-blue-300">{detail.ai_feedback}</p>
              </div>
            )}

            {detail.tags && detail.tags.length > 0 && (
              <div className="mb-4 flex flex-wrap gap-1.5">
                {detail.tags.map((t) => (
                  <span key={t} className="rounded-lg bg-gray-800 px-2 py-1 text-xs text-gray-400">{t}</span>
                ))}
              </div>
            )}

            <button onClick={() => handleDelete(detail.id)}
              className="w-full rounded-lg border border-red-900/30 py-2 text-sm text-red-400 hover:bg-red-900/20 transition-colors">
              삭제
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
