"use client";

import { useEffect, useState } from "react";

interface AutoTradeStatus {
  enabled: boolean;
  is_virtual: boolean;
  daily_order_count: number;
  daily_order_amount: number;
  max_daily_orders: number;
  max_daily_amount: number;
}

export default function DashboardPage() {
  const [status, setStatus] = useState<AutoTradeStatus | null>(null);

  useEffect(() => {
    // TODO: fetch from /api/auto-trade/status with auth
  }, []);

  return (
    <main style={{ padding: "2rem", fontFamily: "monospace" }}>
      <h1>대시보드</h1>

      <section>
        <h2>자동매매 현황</h2>
        {status ? (
          <div>
            <p>상태: {status.is_virtual ? "모의투자" : "실전"}</p>
            <p>오늘 주문: {status.daily_order_count}/{status.max_daily_orders}회</p>
            <p>
              금액: {status.daily_order_amount.toLocaleString()}/
              {status.max_daily_amount.toLocaleString()}원
            </p>
          </div>
        ) : (
          <p>로그인이 필요합니다.</p>
        )}
      </section>

      <section>
        <h2>시황 브리핑</h2>
        <p>TODO: 최신 브리핑 표시</p>
      </section>

      <section>
        <h2>조건 검색</h2>
        <p>TODO: 조건식 목록 + 검색 결과</p>
      </section>
    </main>
  );
}
