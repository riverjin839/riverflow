import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Trading System",
  description: "K8s 기반 트레이딩 시스템",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
