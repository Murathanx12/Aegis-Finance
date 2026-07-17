"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import {
  piGetLaneStatsCI,
  piLaneTearsheetUrl,
  type PILaneStatCI,
} from "@/lib/api";
import { queryKeys, staleTimes } from "@/lib/query-keys";

function fmt(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function StatLine({
  label,
  stat,
  asPct = false,
}: {
  label: string;
  stat: PILaneStatCI | undefined;
  asPct?: boolean;
}) {
  if (!stat || stat.value == null) {
    return (
      <p>
        {label} — <span className="opacity-70">(undefined at this history)</span>
      </p>
    );
  }
  const f = asPct ? fmtPct : fmt;
  return (
    <p>
      {label} <span className="font-medium text-foreground">{f(stat.value)}</span>{" "}
      <span className="opacity-80">
        [95% CI {f(stat.ci_lo)}, {f(stat.ci_hi)}]
      </span>
    </p>
  );
}

/**
 * Bootstrap-CI stat pack for one lane's forward paper record.
 * Wide intervals at a young record are the honest display, not a bug.
 */
export function LaneStatsCI({ laneId }: { laneId: string }) {
  const { data } = useQuery({
    queryKey: queryKeys.pi.laneStatsCI(laneId),
    queryFn: () => piGetLaneStatsCI(laneId),
    staleTime: staleTimes.pi,
    retry: 1,
  });

  if (!data) return null;

  if (data.status !== "ok" || !data.stats) {
    return (
      <p className="text-[11px] text-muted-foreground mt-2">
        Risk stats: too little history for honest error bars ({data.n_obs}{" "}
        daily obs; needs {data.min_obs ?? 20}).
      </p>
    );
  }

  return (
    <div className="mt-2 space-y-0.5 text-[11px] text-muted-foreground tabular-nums">
      <StatLine label="Sharpe" stat={data.stats.sharpe} />
      <StatLine label="Sortino" stat={data.stats.sortino} />
      <StatLine label="Max DD" stat={data.stats.max_drawdown} asPct />
      <a
        href={piLaneTearsheetUrl(laneId)}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-primary hover:underline"
      >
        Full tearsheet <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}
