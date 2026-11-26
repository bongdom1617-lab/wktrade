import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GOLD AI — Real-Time XAUUSD Trading Analyzer",
  description:
    "Institutional-grade real-time XAUUSD (Gold) multi-timeframe technical analysis, AI trading signals, smart SL/TP risk management, and live TradingView candlestick terminal.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#06090f] font-sans text-slate-100 antialiased selection:bg-amber-500/30 selection:text-amber-200">
        {children}
      </body>
    </html>
  );
}
