import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/app-shell";

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
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
