import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Providers, Shell } from "@/components/shell";
import "./globals.css";

const sans = Inter({ subsets: ["latin"], variable: "--font-sans" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Veridata — verifiable data for AI training",
  description: "Demand-driven marketplace for hardware-verified real-world data. Capture, verify, monetize, train, export.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="font-sans">
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  );
}
