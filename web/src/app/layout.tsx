import type { Metadata } from "next";
import { Providers, Shell } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Veridata — verifiable data for AI training",
  description: "Demand-driven marketplace for hardware-verified real-world data. Capture, verify, monetize, train, export.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* loaded at runtime (non-blocking); system fonts are used if offline */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" />
      </head>
      <body className="font-sans">
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  );
}
