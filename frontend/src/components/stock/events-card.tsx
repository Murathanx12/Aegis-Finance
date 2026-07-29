"use client";

import { useQuery } from "@tanstack/react-query";
import { getTickerEvents, EventIntelEvent } from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/info-tooltip";
import { CalendarClock } from "lucide-react";

// Direction chips describe what the SOURCE said about the company — the UI
// never renders advice, forecasts, or outcome probabilities (D4 ruling).
const DIRECTION_STYLE: Record<string, string> = {
  positive: "text-emerald-500",
  negative: "text-red-500",
  neutral: "text-muted-foreground",
  unknown: "text-muted-foreground",
};

const DIRECTION_LABEL: Record<string, string> = {
  positive: "positive",
  negative: "negative",
  neutral: "neutral",
  unknown: "unclear",
};

function BaseRateLine({ ev }: { ev: EventIntelEvent }) {
  const br = ev.context?.base_rate;
  if (!br) return null;
  if (br.status === "measured") {
    return (
      <p className="text-xs text-muted-foreground">
        Measured: {br.stat.replace(/_/g, " ")}{" "}
        <span className="tabular-nums font-medium">
          {(br.value * 100).toFixed(0)}%
        </span>{" "}
        over {br.window} (N={br.n}). Historical description, not a forecast.
      </p>
    );
  }
  return (
    <p className="text-xs text-muted-foreground/70">No measured base rate for this event type.</p>
  );
}

function EventRow({ ev }: { ev: EventIntelEvent }) {
  const dir = DIRECTION_STYLE[ev.direction] ?? "text-muted-foreground";
  const when = ev.timestamp ? ev.timestamp.slice(0, 10) : null;
  return (
    <div className="border-b border-border/40 pb-2 last:border-b-0 last:pb-0 space-y-1">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="uppercase tracking-wide">{ev.event_type.replace(/_/g, " ")}</span>
        <span className={`font-semibold ${dir}`}>
          {DIRECTION_LABEL[ev.direction] ?? ev.direction}
          {ev.direction !== "neutral" && ev.direction !== "unknown" && (
            <span className="font-normal text-muted-foreground">
              {" "}({ev.direction_basis.toLowerCase()} in source)
            </span>
          )}
        </span>
        {when && <span className="ml-auto tabular-nums">{when}</span>}
      </div>
      <p className="text-sm leading-snug">
        {ev.source.url ? (
          <a href={ev.source.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
            {ev.title}
          </a>
        ) : (
          ev.title
        )}
        {ev.source.publisher && (
          <span className="text-xs text-muted-foreground"> — {ev.source.publisher}</span>
        )}
      </p>
      <BaseRateLine ev={ev} />
    </div>
  );
}

export function EventsCard({ ticker }: { ticker: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.events.ticker(ticker),
    queryFn: () => getTickerEvents(ticker),
    staleTime: staleTimes.news,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-medium text-muted-foreground flex items-center gap-2">
            <CalendarClock className="h-4 w-4" /> Events
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    );
  }
  if (error || !data) return null; // additive card — never block the page

  return (
    <Card className="animate-fade-in">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-medium text-muted-foreground flex items-center">
          <CalendarClock className="h-4 w-4 mr-2" />
          Events
          <InfoTooltip
            text="Structured events extracted from filings, earnings data, and news. Direction is what the source stated or implied about this company — descriptive, never a forecast or signal. Extraction tier reflects parse quality only."
            beginnerText="A log of things that happened to this company — filings, earnings, news — with an honest note about what each source said. Not buy/sell advice."
          />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {data.unavailable_feeds.length > 0 && (
          <p className="text-xs text-amber-500">
            Some event feeds are unavailable right now: {data.unavailable_feeds.join(", ")}.
            Missing feeds are disclosed, never assumed quiet.
          </p>
        )}
        {data.events.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No structured events in the recent window
            {data.unavailable_feeds.length > 0 ? " from the available feeds" : ""}.
          </p>
        ) : (
          <div className="space-y-2">
            {data.events.slice(0, 8).map((ev, i) => (
              <EventRow key={`${ev.source.feed}-${i}`} ev={ev} />
            ))}
          </div>
        )}
        <p className="text-[11px] text-muted-foreground/70">{data.disclaimer}</p>
      </CardContent>
    </Card>
  );
}
