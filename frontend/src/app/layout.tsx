import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Riverflow Trading",
  description: "K8s 기반 한국 증시 자동매매 시스템",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko" className="dark">
      <body>
        <nav className="sticky top-0 z-50 border-b border-gray-800 bg-gray-950/80 backdrop-blur-md">
          <div className="mx-auto flex h-12 max-w-7xl items-center justify-between px-4">
            <a
              href="/dashboard"
              className="text-lg font-bold tracking-tight text-blue-400 hover:text-blue-300 transition-colors"
            >
              Riverflow
            </a>
            <div className="flex items-center gap-6 text-sm">
              <a href="/dashboard" className="text-gray-400 hover:text-white transition-colors">
                대시보드
              </a>
              <a href="/market" className="text-gray-400 hover:text-white transition-colors">
                시황
              </a>
              <a href="/journal" className="text-gray-400 hover:text-white transition-colors">
                매매일지
              </a>
            </div>
          </div>
        </nav>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
