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
    <html lang="ko">
      <body>
        <nav className="top-nav">
          <div className="nav-inner">
            <a href="/dashboard" className="nav-brand">
              Riverflow
            </a>
            <div className="nav-links">
              <a href="/dashboard">대시보드</a>
              <a href="/journal">매매일지</a>
              <a href="/dashboard" className="nav-api-link" id="api-docs-link">
                API Docs
              </a>
            </div>
          </div>
        </nav>
        <div className="page-body">{children}</div>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                var link = document.getElementById('api-docs-link');
                if (link) link.href = window.location.origin + '/api/docs';
              })();
            `,
          }}
        />
      </body>
    </html>
  );
}
