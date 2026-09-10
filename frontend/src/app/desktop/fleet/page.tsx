"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Ruler } from "lucide-react";
import {
  ApiState,
  DASH,
  EstimateValue,
  Field,
  RawPayload,
  fmtUtc,
} from "@/components/desktop/primitives";
import { getFleet, isNotBuilt, type FleetLane } from "@/lib/control-api";

/**
 * Fleet vs SPY.
 *
 * The whole point of this page is the error bar. From the 09-10 handoff: "β 0.18
 * ± 2.21 is not a beta", and must not be printed as one. So the rule here is
 * mechanical rather than tasteful:
 *
 * - the daily excess is rendered ONLY through `EstimateValue`, which refuses to
 *   print a value that arrived without a standard error or an interval;
 * - where the row says `estimable: false`, the t-stat cell prints "not
 *   estimable" and the row's own `why_not_estimable` sentence — never a number,
 *   not even a greyed-out one;
 * - realised quantities (NAV, a since-inception return, a day count) are
 *   OBSERVATIONS, not estimates: they have no sampling error to carry and are
 *   printed as they arrived;
 * - anything the payload holds that this page did not name is still visible in
 *   the raw block, so no measurement is silently dropped.
 *
 * Four sessions of paper trading cannot separate a beta from zero. "Not
 * estimable" is the honest reading of that, and it is the reading this page
 * prints.
 */

function pct(v: number | undefined, digits = 2): string {
  return typeof v === "number" && Number.isFinite(v) ? `${v.toFixed(digits)}%` : DASH;
}
function num(v: number | undefined, digits = 4): string {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : DASH;
}

/** The daily excess with its own standard error, or a refusal to print it. */
function DailyExcess({ lane }: { lane: FleetLane }) {
  return (
    <EstimateValue
      est={{
        value: typeof lane.mean_daily_excess_pct === "number" ? lane.mean_daily_excess_pct : null,
        se: typeof lane.se_daily_excess_pct === "number" ? lane.se_daily_excess_pct : null,
        ciLo: null,
        ciHi: null,
        n: typeof lane.n_days === "number" ? lane.n_days : null,
      }}
      digits={4}
      suffix="%"
    />
  );
}

/**
 * The t-stat cell. `estimable === false` is a REFUSAL with a reason attached,
 * and the reason is the useful part — a bare "—" would read as a missing field
 * rather than as "four sessions cannot answer this".
 */
function TStat({ lane }: { lane: FleetLane }) {
  if (lane.estimable === false) {
    return (
      <span>
        <Badge variant="outline">not estimable</Badge>
        {lane.why_not_estimable ? (
          <span className="ml-2 text-[11px] text-muted-foreground">
            {lane.why_not_estimable}
          </span>
        ) : null}
      </span>
    );
  }
  if (typeof lane.t_stat !== "number" || !Number.isFinite(lane.t_stat)) {
    return <span className="text-muted-foreground">{DASH}</span>;
  }
  if (typeof lane.se_daily_excess_pct !== "number") {
    // A t without the standard error it was built from is not readable as one.
    return (
      <span>
        <Badge variant="outline">not estimable</Badge>
        <span className="ml-2 text-[11px] text-muted-foreground">
          payload carries t {lane.t_stat.toFixed(2)} with no standard error beside it
        </span>
      </span>
    );
  }
  return <span className="tabular-nums font-medium">{lane.t_stat.toFixed(2)}</span>;
}

function LaneRow({ lane, emphasis }: { lane: FleetLane; emphasis?: boolean }) {
  return (
    <tr
      className={`border-b border-border/30 last:border-0 ${
        emphasis ? "bg-muted/40 font-medium" : ""
      }`}
    >
      <td className="py-1.5 pr-3 font-mono">{lane.lane || DASH}</td>
      <td className="py-1.5 pr-3 text-right tabular-nums">{num(lane.nav, 2)}</td>
      <td className="py-1.5 pr-3 text-right tabular-nums">{pct(lane.since_inception_pct)}</td>
      <td className="py-1.5 pr-3 text-right tabular-nums">
        {pct(lane.excess_vs_benchmark_pct)}
      </td>
      <td className="py-1.5 pr-3 text-right">
        <DailyExcess lane={lane} />
      </td>
      <td className="py-1.5 pr-3">
        <TStat lane={lane} />
      </td>
      <td className="py-1.5 text-right tabular-nums text-muted-foreground">
        {typeof lane.n_days === "number" ? lane.n_days : DASH}
      </td>
    </tr>
  );
}

function LanesTable({ lanes, aggregate }: { lanes: FleetLane[]; aggregate?: FleetLane }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-muted-foreground">
          <tr className="border-b border-border/60">
            <th className="py-1.5 pr-3 text-left font-medium">Lane</th>
            <th className="py-1.5 pr-3 text-right font-medium">NAV</th>
            <th className="py-1.5 pr-3 text-right font-medium">Since inception</th>
            <th className="py-1.5 pr-3 text-right font-medium">Excess vs benchmark</th>
            <th className="py-1.5 pr-3 text-right font-medium">
              Mean daily excess ± se
            </th>
            <th className="py-1.5 pr-3 text-left font-medium">t</th>
            <th className="py-1.5 text-right font-medium">Days</th>
          </tr>
        </thead>
        <tbody>
          {lanes.map((l, i) => (
            <LaneRow key={l.lane ?? i} lane={l} />
          ))}
          {aggregate ? (
            <LaneRow
              lane={{ ...aggregate, lane: aggregate.lane ?? "aggregate" }}
              emphasis
            />
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

export default function FleetVsSpyPage() {
  const fleet = useQuery({
    queryKey: ["desktop", "fleet"],
    queryFn: getFleet,
    refetchInterval: 60_000,
    retry: false,
  });

  const d = fleet.data;
  const lanes = Array.isArray(d?.lanes) ? d.lanes : null;
  const bench = d?.benchmark;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
            <Ruler className="size-4" /> Fleet vs {bench?.symbol ?? "benchmark"}
            {typeof d?.age_days === "number" ? (
              <Badge variant="outline">{d.age_days} days since inception</Badge>
            ) : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Uncertainty travels with the estimate. A mean daily excess is printed here
            only with its standard error; where a lane reports{" "}
            <span className="font-mono">estimable: false</span> this page prints{" "}
            <Badge variant="outline">not estimable</Badge> and the reason, never a
            number. At a handful of sessions that is the honest answer, not a bug — β
            0.18 ± 2.21 is not a beta.
          </p>

          {fleet.isLoading ? <Skeleton className="h-32" /> : null}
          <ApiState error={fleet.error} what="Fleet" />
          {isNotBuilt(fleet.error) ? (
            <p className="text-xs text-muted-foreground">
              <span className="font-mono">GET /api/control/fleet</span> is not in the
              control router yet. When it lands, this page renders the lane table it
              declares — each excess beside its own standard error. It shows nothing at
              all before then.
            </p>
          ) : null}

          {d ? (
            <div className="space-y-1">
              <Field label="As of (UTC)" value={d.utc ? fmtUtc(d.utc) : null} />
              <Field label="Inception" value={d.inception_date ?? null} />
              <Field label="Age (days)" value={d.age_days ?? null} />
              <Field label="Benchmark" value={bench?.symbol ?? null} mono />
              <Field
                label="Benchmark total return"
                value={
                  typeof bench?.total_return_pct === "number"
                    ? pct(bench.total_return_pct)
                    : null
                }
              />
              <Field label="Benchmark days" value={bench?.n_days ?? null} />
            </div>
          ) : null}

          {d?.note ? (
            <p className="rounded-md bg-muted/40 px-2 py-1.5 text-[11px] text-muted-foreground">
              {d.note}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {lanes ? (
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
              Per lane
              <Badge variant="outline">{lanes.length} lanes</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {lanes.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                The endpoint answered with no lanes. Nothing is shown in their place.
              </p>
            ) : (
              <LanesTable lanes={lanes} aggregate={d?.aggregate} />
            )}
            <p className="mt-3 text-[11px] text-muted-foreground">
              NAV, since-inception and excess are realised OBSERVATIONS and carry no
              sampling error. The daily excess is an ESTIMATE and is shown only with
              one.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {d ? (
        <Card>
          <CardContent>
            <RawPayload
              data={d}
              label="raw fleet payload (every field, including the ones this page did not name)"
            />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
