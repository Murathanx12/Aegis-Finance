"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const POPULAR = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "JNJ", "V", "UNH", "XOM"];

export default function StockPage() {
  const [ticker, setTicker] = useState("");
  const router = useRouter();

  const go = (t: string) => router.push(`/stock/${t.toUpperCase()}`);

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Stock Analysis</h1>
        <p className="text-sm text-muted-foreground">
          Per-ticker Monte Carlo projections with fundamental awareness
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Search Ticker</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={(e) => { e.preventDefault(); if (ticker.trim()) go(ticker); }} className="flex gap-2">
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="Enter ticker symbol (e.g. AAPL)"
              className="flex-1 rounded-md border border-border bg-background px-4 py-3 text-base placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <Button type="submit" disabled={!ticker.trim()}>Analyze</Button>
          </form>

          <div>
            <p className="text-xs text-muted-foreground mb-2">Popular tickers</p>
            <div className="flex flex-wrap gap-2">
              {POPULAR.map((t) => (
                <button
                  key={t}
                  onClick={() => go(t)}
                  className="rounded-md bg-muted/50 px-3 py-1.5 text-xs font-medium hover:bg-muted transition-colors"
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
