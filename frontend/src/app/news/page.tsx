"use client";

import { useQuery } from "@tanstack/react-query";
import { getMarketNews, getMarketSignal } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/info-tooltip";
import { ErrorCard } from "@/components/error-card";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";

function EventScoreGauge({ score, interpretation }: { score: number; interpretation: string }) {
  const pct = Math.round(score * 100);
  const color = score > 0.75 ? "text-red-400" : score > 0.50 ? "text-amber-400" : score > 0.30 ? "text-yellow-400" : "text-emerald-400";
  const bgColor = score > 0.75 ? "bg-red-500" : score > 0.50 ? "bg-amber-500" : score > 0.30 ? "bg-yellow-500" : "bg-emerald-500";

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative w-32 h-32">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90" role="img" aria-label={`Event risk score: ${pct}%`}>
          <circle cx="50" cy="50" r="40" fill="none" stroke="currentColor" strokeWidth="8" className="text-muted/30" />
          <circle
            cx="50" cy="50" r="40" fill="none" stroke="currentColor" strokeWidth="8"
            strokeDasharray={`${pct * 2.51} 251`}
            className={color}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`text-2xl font-bold ${color}`}>{pct}%</span>
          <span className="text-xs text-muted-foreground">Event Risk</span>
        </div>
      </div>
      <Badge variant="outline" className={`${bgColor}/20 border-current ${color}`}>
        {interpretation}
      </Badge>
    </div>
  );
}

function ScoreCard({ label, value, description }: { label: string; value: number; description: string }) {
  const pct = Math.round(value * 100);
  return (
    <div className="rounded-lg bg-muted/30 p-4">
      <p className="text-xs text-muted-foreground uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold tabular-nums">{pct}%</p>
      <p className="text-xs text-muted-foreground mt-1">{description}</p>
    </div>
  );
}

function ToneChart({ data }: { data: number[] }) {
  const chartData = data.map((v, i) => ({ day: i + 1, tone: v }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="day" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} label={{ value: "Days Ago", position: "insideBottom", offset: -5, fill: "var(--muted-foreground)", fontSize: 11 }} />
        <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
        <Tooltip
          contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--foreground)" }}
          formatter={(v) => [Number(v).toFixed(2), "Tone"]}
        />
        <Area type="monotone" dataKey="tone" stroke="#63b4ff" fill="#63b4ff" fillOpacity={0.15} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export default function NewsPage() {
  const { data, isLoading: loading, error, refetch } = useQuery({
    queryKey: queryKeys.news.market,
    queryFn: getMarketNews,
    staleTime: staleTimes.news,
  });
  const signal = useQuery({
    queryKey: queryKeys.market.signal,
    queryFn: getMarketSignal,
    staleTime: staleTimes.market,
  });

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">News & Intelligence</h1>
        <p className="text-sm text-muted-foreground">
          GDELT-powered market sentiment analysis with AI insights
        </p>
      </div>

      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-2.5 flex items-center gap-2 text-xs text-amber-400/80">
        <span>Educational tool only. Not financial advice. Sentiment scores are algorithmic estimates, not recommendations.</span>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      ) : error ? (
        <ErrorCard message={(error as Error).message} onRetry={() => refetch()} />
      ) : data ? (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
                  Event Risk Score
                  <InfoTooltip text="Composite score from GDELT data combining news tone, volume spikes, and geopolitical risk signals. 0% = calm, 100% = extreme event risk." />
                </CardTitle>
              </CardHeader>
              <CardContent className="flex justify-center">
                <EventScoreGauge
                  score={data.event_score.event_score}
                  interpretation={data.event_score.interpretation}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base font-medium text-muted-foreground">
                  Risk Components
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <ScoreCard label="News Tone" value={data.event_score.components.tone_score} description="Negative sentiment in financial news" />
                <ScoreCard label="Volume Spike" value={data.event_score.components.volume_score} description="Unusual news volume activity" />
                <ScoreCard label="Geopolitical Risk" value={data.event_score.components.gpr_score} description="Conflict and geopolitical signals" />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base font-medium text-muted-foreground">
                  GDELT Signals
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg bg-muted/30 p-3">
                    <p className="text-xs text-muted-foreground uppercase">Avg Tone</p>
                    <p className={`text-lg font-bold ${data.gdelt.avg_tone < -1 ? "text-red-400" : data.gdelt.avg_tone > 1 ? "text-emerald-400" : ""}`}>
                      {data.gdelt.avg_tone.toFixed(2)}
                    </p>
                  </div>
                  <div className="rounded-lg bg-muted/30 p-3">
                    <p className="text-xs text-muted-foreground uppercase">Tone Trend</p>
                    <p className={`text-lg font-bold ${data.gdelt.tone_trend < -0.5 ? "text-red-400" : data.gdelt.tone_trend > 0.5 ? "text-emerald-400" : ""}`}>
                      {data.gdelt.tone_trend >= 0 ? "+" : ""}{data.gdelt.tone_trend.toFixed(2)}
                    </p>
                  </div>
                  <div className="rounded-lg bg-muted/30 p-3">
                    <p className="text-xs text-muted-foreground uppercase">Volume Z-Score</p>
                    <p className={`text-lg font-bold ${data.gdelt.volume_zscore > 2 ? "text-amber-400" : ""}`}>
                      {data.gdelt.volume_zscore.toFixed(1)}&sigma;
                    </p>
                  </div>
                  <div className="rounded-lg bg-muted/30 p-3">
                    <p className="text-xs text-muted-foreground uppercase">Conflict</p>
                    <p className={`text-lg font-bold ${data.gdelt.conflict_score > 0.5 ? "text-red-400" : ""}`}>
                      {(data.gdelt.conflict_score * 100).toFixed(0)}%
                    </p>
                  </div>
                </div>
                {!data.gdelt.success && (
                  <p className="text-xs text-amber-400" role="alert">GDELT data unavailable: {data.gdelt.error}</p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Market Signal Context */}
          {signal.data && (
            <Card className={`border-2 ${
              signal.data.action.includes("Buy") ? "border-emerald-500/30" :
              signal.data.action.includes("Sell") ? "border-red-500/30" : "border-amber-500/30"
            }`}>
              <CardContent className="p-4 flex flex-wrap items-center gap-4">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Signal Engine Says</p>
                  <span className={`inline-block text-lg font-bold px-3 py-1.5 rounded ${
                    signal.data.action.includes("Buy") ? "bg-emerald-500/15 text-emerald-400" :
                    signal.data.action.includes("Sell") ? "bg-red-500/15 text-red-400" : "bg-amber-500/15 text-amber-400"
                  }`}>{signal.data.action}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-muted-foreground">
                    Composite: {signal.data.composite_score > 0 ? "+" : ""}{signal.data.composite_score.toFixed(3)} · Confidence: {signal.data.confidence}%
                    {signal.data.regime && <> · Regime: {signal.data.regime}</>}
                    {signal.data.vix != null && <> · VIX: {signal.data.vix}</>}
                  </p>
                  <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
                    {signal.data.reasons.map((r, i) => (
                      <span key={i} className="text-xs text-muted-foreground">&bull; {r}</span>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {data.gdelt.raw_data.tone.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base font-medium text-muted-foreground">
                  30-Day News Tone Trend
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ToneChart data={data.gdelt.raw_data.tone} />
              </CardContent>
            </Card>
          )}

          {/* Sector Impact */}
          {data.sector_impact && Object.keys(data.sector_impact).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
                  Sector Impact
                  <InfoTooltip text="Sectors mentioned in current market headlines, ranked by relevance. Higher relevance means more headlines are affecting that sector." />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                  {Object.entries(data.sector_impact).map(([sector, info]) => (
                    <div key={sector} className="rounded-lg border border-border/50 p-3">
                      <p className="text-sm font-medium truncate">{sector}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <div className="flex-1 h-1.5 bg-muted rounded-full">
                          <div
                            className="h-full bg-blue-500 rounded-full"
                            style={{ width: `${Math.min(info.relevance * 100 * 3, 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-muted-foreground tabular-nums">{info.headline_count}</span>
                      </div>
                      {info.sample_headlines[0] && (
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-1">{info.sample_headlines[0]}</p>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {data.llm_summary ? (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base font-medium text-muted-foreground">
                    AI Market Summary
                  </CardTitle>
                  <Badge variant="outline" className={
                    data.llm_summary.sentiment === "bullish" ? "text-emerald-400 border-emerald-400/30" :
                    data.llm_summary.sentiment === "bearish" ? "text-red-400 border-red-400/30" :
                    data.llm_summary.sentiment === "mixed" ? "text-amber-400 border-amber-400/30" :
                    "text-muted-foreground"
                  }>
                    {data.llm_summary.sentiment}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-relaxed">{data.llm_summary.summary}</p>
              </CardContent>
            </Card>
          ) : !data.llm_available ? (
            <Card>
              <CardContent className="p-4 text-sm text-muted-foreground text-center">
                AI analysis unavailable — set DEEPSEEK_API_KEY for market summaries
              </CardContent>
            </Card>
          ) : null}

          {data.news.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base font-medium text-muted-foreground">
                  Recent Market Headlines
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {data.news.map((item, i) => (
                  <div key={i} className="flex items-start gap-3 py-2 border-b border-border/30 last:border-0">
                    <div className="flex-1 min-w-0">
                      {item.link ? (
                        <a href={item.link} target="_blank" rel="noopener noreferrer" className="text-sm font-medium hover:text-primary transition-colors line-clamp-2">
                          {item.title}
                        </a>
                      ) : (
                        <p className="text-sm font-medium line-clamp-2">{item.title}</p>
                      )}
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {item.publisher}
                      </p>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </>
      ) : null}
    </div>
  );
}
