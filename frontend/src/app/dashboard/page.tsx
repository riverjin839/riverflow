"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

// ================================================================
// Types
// ================================================================

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

interface TopStock {
  ticker: string;
  name: string;
  change_rate: number;
  volume_ratio: number;
  price: number;
}

interface SectorItem {
  sector_name: string;
  market: string;
  stock_count: number;
  top3_avg_change_rate: number;
  sector_volume_ratio: number;
  is_leading: boolean;
  leader_ticker: string;
  leader_name: string;
  leader_change_rate: number;
  top_stocks: TopStock[];
}

interface AutoTradeStatus {
  enabled: boolean;
  is_virtual: boolean;
  daily_order_count: number;
  daily_order_amount: number;
  max_daily_orders: number;
  max_daily_amount: number;
}

// ================================================================
// Helpers
// ================================================================

function trendIcon(trend: string): string {
  if (trend === "rising") return "\u25B2";
  if (trend === "falling") return "\u25BC";
  return "\u25C6";
}

function trendColor(trend: string): string {
  if (trend === "rising") return "#e74c3c";
  if (trend === "falling") return "#3498db";
  return "#95a5a6";
}

function formatNumber(n: number): string {
  if (Math.abs(n) >= 1_0000_0000) return (n / 1_0000_0000).toFixed(1) + "\uC5B5";
  if (Math.abs(n) >= 1_0000) return (n / 1_0000).toFixed(0) + "\uB9CC";
  return n.toLocaleString();
}

// ================================================================
// Component
// ================================================================

export default function DashboardPage() {
  const [token, setToken] = useState<string | null>(null);
  const [supplyTrend, setSupplyTrend] = useState<Record<string, SupplyTrend | null>>({});
  const [highImpactNews, setHighImpactNews] = useState<NewsItem[]>([]);
  const [sectors, setSectors] = useState<SectorItem[]>([]);
  const [autoTradeStatus, setAutoTradeStatus] = useState<AutoTradeStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    setToken(stored);
  }, []);

  const fetchData = useCallback(async () => {
    if (!token) return;
    setLoading(true);

    try {
      const [supply, news, sectorData, tradeStatus] = await Promise.allSettled([
        apiFetch<Record<string, SupplyTrend | null>>("/api/supply/trend", { token }),
        apiFetch<NewsItem[]>("/api/news?impact_min=8&limit=10", { token }),
        apiFetch<SectorItem[]>("/api/sectors/latest?limit=10", { token }),
        apiFetch<AutoTradeStatus>("/api/auto-trade/status", { token }),
      ]);

      if (supply.status === "fulfilled") setSupplyTrend(supply.value);
      if (news.status === "fulfilled") setHighImpactNews(news.value);
      if (sectorData.status === "fulfilled") setSectors(sectorData.value);
      if (tradeStatus.status === "fulfilled") setAutoTradeStatus(tradeStatus.value);
    } catch {
      // allSettled handles individual failures
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (!token) {
    return (
      <main style={styles.container}>
        <h1 style={styles.title}>Trading Dashboard</h1>
        <p style={styles.loginMsg}>\uB85C\uADF8\uC778\uC774 \uD544\uC694\uD569\uB2C8\uB2E4.</p>
      </main>
    );
  }

  return (
    <main style={styles.container}>
      <h1 style={styles.title}>Trading Dashboard</h1>

      {/* ===== \uC0C1\uB2E8: \uC2DC\uC7A5 \uC9C0\uC218 + \uC218\uAE09 \uD604\uD669 ===== */}
      <section style={styles.topBar}>
        {["KOSPI", "KOSDAQ"].map((market) => {
          const data = supplyTrend[market];
          if (!data) {
            return (
              <div key={market} style={styles.indexCard}>
                <strong>{market}</strong>
                <span style={styles.noData}>\uB370\uC774\uD130 \uC5C6\uC74C</span>
              </div>
            );
          }
          const isUp = data.index_change_rate >= 0;
          return (
            <div key={market} style={styles.indexCard}>
              <div style={styles.indexHeader}>
                <strong>{market}</strong>
                <span style={{ color: isUp ? "#e74c3c" : "#3498db", fontWeight: "bold" }}>
                  {data.index_value.toFixed(2)} ({isUp ? "+" : ""}
                  {data.index_change_rate.toFixed(2)}%)
                </span>
              </div>
              <div style={styles.supplyRow}>
                <span>
                  \uC678\uC778{" "}
                  <span style={{ color: trendColor(data.foreign_trend) }}>
                    {trendIcon(data.foreign_trend)}
                  </span>{" "}
                  {formatNumber(data.foreign_net_buy)}
                </span>
                <span>
                  \uAE30\uAD00{" "}
                  <span style={{ color: trendColor(data.institution_trend) }}>
                    {trendIcon(data.institution_trend)}
                  </span>{" "}
                  {formatNumber(data.institution_net_buy)}
                </span>
                <span>\uAC1C\uC778 {formatNumber(data.individual_net_buy)}</span>
              </div>
            </div>
          );
        })}

        {autoTradeStatus && (
          <div style={styles.indexCard}>
            <strong>\uC790\uB3D9\uB9E4\uB9E4</strong>
            <span style={{ color: autoTradeStatus.is_virtual ? "#27ae60" : "#e74c3c" }}>
              {autoTradeStatus.is_virtual ? "\uBAA8\uC758" : "\uC2E4\uC804"}
            </span>
            <span>
              \uC8FC\uBB38 {autoTradeStatus.daily_order_count}/{autoTradeStatus.max_daily_orders}
            </span>
          </div>
        )}
      </section>

      {/* ===== \uBCF8\uBB38: \uC88C\uCE21 \uB274\uC2A4 / \uC6B0\uCE21 \uC139\uD130 ===== */}
      <div style={styles.mainGrid}>
        {/* \uC88C\uCE21: \uACE0\uC601\uD5A5 \uB274\uC2A4 */}
        <section style={styles.panel}>
          <h2 style={styles.panelTitle}>\uD575\uC2EC \uB274\uC2A4 (\uC601\uD5A5\uB3C4 8+)</h2>
          {loading && highImpactNews.length === 0 ? (
            <p style={styles.noData}>\uB85C\uB529 \uC911...</p>
          ) : highImpactNews.length === 0 ? (
            <p style={styles.noData}>\uACE0\uC601\uD5A5 \uB274\uC2A4 \uC5C6\uC74C</p>
          ) : (
            <ul style={styles.newsList}>
              {highImpactNews.map((n) => (
                <li key={n.id} style={styles.newsItem}>
                  <div style={styles.newsHeader}>
                    <span style={styles.impactBadge}>{n.impact_score}</span>
                    {n.theme && <span style={styles.themeBadge}>{n.theme}</span>}
                    {n.is_leading && <span style={styles.leadingBadge}>\uC8FC\uB3C4</span>}
                  </div>
                  <p style={styles.newsTitle}>{n.title}</p>
                  <span style={styles.newsMeta}>
                    {n.source} | {new Date(n.crawled_at).toLocaleString("ko-KR")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* \uC6B0\uCE21: \uC139\uD130 \uB7AD\uD0B9 */}
        <section style={styles.panel}>
          <h2 style={styles.panelTitle}>\uC139\uD130 \uAC15\uC138 \uB7AD\uD0B9</h2>
          {loading && sectors.length === 0 ? (
            <p style={styles.noData}>\uB85C\uB529 \uC911...</p>
          ) : sectors.length === 0 ? (
            <p style={styles.noData}>\uC139\uD130 \uB370\uC774\uD130 \uC5C6\uC74C</p>
          ) : (
            <div>
              {sectors.map((s, i) => (
                <div
                  key={s.sector_name}
                  style={{
                    ...styles.sectorCard,
                    borderLeft: s.is_leading
                      ? "4px solid #e74c3c"
                      : "4px solid #ddd",
                  }}
                >
                  <div style={styles.sectorHeader}>
                    <span style={styles.sectorRank}>#{i + 1}</span>
                    <strong>{s.sector_name}</strong>
                    {s.is_leading && <span style={styles.leadingBadge}>\uC8FC\uB3C4</span>}
                    <span style={styles.sectorMarket}>{s.market}</span>
                  </div>
                  <div style={styles.sectorMetrics}>
                    <span>
                      Top3 \uD3C9\uADE0{" "}
                      <b style={{ color: s.top3_avg_change_rate >= 0 ? "#e74c3c" : "#3498db" }}>
                        {s.top3_avg_change_rate >= 0 ? "+" : ""}
                        {s.top3_avg_change_rate.toFixed(2)}%
                      </b>
                    </span>
                    <span>\uAC70\uB798\uB300\uAE08\uBE44 {s.sector_volume_ratio.toFixed(0)}%</span>
                  </div>
                  <div style={styles.leaderRow}>
                    <span style={styles.leaderLabel}>\uB300\uC7A5\uC8FC</span>
                    <span>
                      {s.leader_name} ({s.leader_ticker}){" "}
                      <b style={{ color: s.leader_change_rate >= 0 ? "#e74c3c" : "#3498db" }}>
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
    </main>
  );
}

// ================================================================
// Inline Styles
// ================================================================

const styles: Record<string, React.CSSProperties> = {
  container: {},
  title: {
    fontSize: "1.3rem",
    marginBottom: "1rem",
    borderBottom: "2px solid #333",
    paddingBottom: "0.5rem",
  },
  loginMsg: { color: "#999", textAlign: "center" as const, marginTop: "3rem" },

  topBar: {
    display: "flex",
    gap: "1rem",
    marginBottom: "1.5rem",
    flexWrap: "wrap" as const,
  },
  indexCard: {
    flex: 1,
    minWidth: 220,
    background: "#fff",
    border: "1px solid #e0e0e0",
    borderRadius: 8,
    padding: "0.8rem 1rem",
    display: "flex",
    flexDirection: "column" as const,
    gap: "0.3rem",
  },
  indexHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  supplyRow: {
    display: "flex",
    gap: "1rem",
    fontSize: "0.85rem",
    color: "#555",
  },
  noData: { color: "#999", fontSize: "0.85rem" },

  mainGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "1.5rem",
  },

  panel: {
    background: "#fff",
    border: "1px solid #e0e0e0",
    borderRadius: 8,
    padding: "1rem",
    maxHeight: 600,
    overflowY: "auto" as const,
  },
  panelTitle: {
    fontSize: "1.1rem",
    marginBottom: "0.8rem",
    paddingBottom: "0.4rem",
    borderBottom: "1px solid #eee",
  },

  newsList: { listStyle: "none", padding: 0, margin: 0 },
  newsItem: {
    padding: "0.6rem 0",
    borderBottom: "1px solid #f0f0f0",
  },
  newsHeader: { display: "flex", gap: "0.4rem", marginBottom: "0.3rem" },
  impactBadge: {
    background: "#e74c3c",
    color: "#fff",
    borderRadius: 4,
    padding: "1px 6px",
    fontSize: "0.75rem",
    fontWeight: "bold",
  },
  themeBadge: {
    background: "#3498db",
    color: "#fff",
    borderRadius: 4,
    padding: "1px 6px",
    fontSize: "0.75rem",
  },
  leadingBadge: {
    background: "#e67e22",
    color: "#fff",
    borderRadius: 4,
    padding: "1px 6px",
    fontSize: "0.75rem",
  },
  newsTitle: { margin: "0.2rem 0", fontSize: "0.9rem" },
  newsMeta: { fontSize: "0.75rem", color: "#999" },

  sectorCard: {
    padding: "0.6rem 0.8rem",
    marginBottom: "0.5rem",
    background: "#fafafa",
    borderRadius: 4,
  },
  sectorHeader: {
    display: "flex",
    gap: "0.5rem",
    alignItems: "center",
    marginBottom: "0.3rem",
  },
  sectorRank: { color: "#999", fontSize: "0.85rem" },
  sectorMarket: { color: "#aaa", fontSize: "0.75rem", marginLeft: "auto" },
  sectorMetrics: {
    display: "flex",
    gap: "1rem",
    fontSize: "0.85rem",
    color: "#555",
  },
  leaderRow: {
    fontSize: "0.8rem",
    color: "#666",
    marginTop: "0.2rem",
  },
  leaderLabel: {
    background: "#eee",
    borderRadius: 3,
    padding: "0 4px",
    marginRight: "0.3rem",
    fontSize: "0.75rem",
  },
};
