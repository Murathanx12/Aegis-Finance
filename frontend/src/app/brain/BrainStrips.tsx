"use client";

/** Scenario strip, regime-row strip and "what changed since the last cycle" -- the three
 * secondary panels of the Brain v2 spec (§2.3). Each number names its receipt field in its
 * own caption line (no separate hover state needed here: these are already short enough to
 * read directly, unlike the dense board). */

import React from "react";
import type { BeliefUpdateRow, BrainResponse, ScenarioRow } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

function fmtPct(v: number | null, digits = 0): string {
  return v == null ? "n/a" : `${(v * 100).toFixed(digits)}%`;
}
function fmtHours(h: number | null): string {
  if (h == null) return "n/a";
  return h < 48 ? `${h.toFixed(1)} h ago` : `${(h / 24).toFixed(1)} d ago`;
}

function ScenarioBar({ s }: { s: ScenarioRow }) {
  const pct = s.probability_display == null ? null : Math.max(0, Math.min(1, s.probability_display));
  return (
    <li className="py-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium truncate">{s.name ?? s.scenario_id}</span>
        <span className="text-xs tabular-nums font-semibold" title="probability_display (world_state.scenario_probability(s, 'display'))">
          {fmtPct(s.probability_display)}
        </span>
      </div>
      <div className="mt-1 h-2 w-full rounded-full bg-muted overflow-hidden">
        <div className="h-full bg-violet-500/70 dark:bg-violet-400/70" style={{ width: `${(pct ?? 0) * 100}%` }} />
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        prior v{s.prior_version ?? "?"} declared by {s.prior_author ?? "unrecorded"}
        {s.prior_declared_at ? ` on ${s.prior_declared_at}` : ""} · {s.probability_source ?? "no source recorded"}
      </p>
      {s.drivers.length > 0 && (
        <p className="text-[11px] text-muted-foreground line-clamp-1" title={s.drivers.join("; ")}>
          drivers: {s.drivers.join(", ")}
        </p>
      )}
      {s.falsifiers.length > 0 && (
        <p className="text-[11px] text-muted-foreground line-clamp-1" title={s.falsifiers.join("; ")}>
          falsifiers: {s.falsifiers.join(", ")}
        </p>
      )}
    </li>
  );
}

export function ScenarioStrip({ data }: { data: BrainResponse }) {
  if (!data.scenarios.length) {
    return <p className="text-xs text-muted-foreground">
      {data.missing_because.scenarios ?? "no scenarios on this receipt"}
    </p>;
  }
  return <ul className="divide-y divide-border/40">{data.scenarios.map((s) => <ScenarioBar key={s.scenario_id} s={s} />)}</ul>;
}

/** Three small marks per regime variable: the model's own Brier beside its two null Briers
 * (lower is better). This is the GRADE on resolved rows, not the raw P(event) of today's
 * open row -- labelled as such, because that number is not threaded through this receipt
 * yet (see the research note's "what is null today"). */
export function RegimeStrip({ data }: { data: BrainResponse }) {
  const r = data.regime;
  if (!r) {
    return <p className="text-xs text-muted-foreground">{data.missing_because.regime ?? "no regime receipt"}</p>;
  }
  return (
    <div className="space-y-2 text-xs">
      <p className="text-muted-foreground">{r.note ?? "no note on the regime grade"}</p>
      <div className="flex gap-4">
        <span>vs persistence trust <b className="tabular-nums">{r.vs_persistence?.trust ?? "n/a"}</b></span>
        <span>vs base rate trust <b className="tabular-nums">{r.vs_base_rate?.trust ?? "n/a"}</b></span>
      </div>
      {r.fields.length === 0 ? (
        <p className="text-muted-foreground">
          no per-variable field has graded entry sessions yet (regime.fields is empty on this receipt --
          not a finding before the first h5 grades).
        </p>
      ) : (
        <ul className="space-y-1.5">
          {r.fields.map((f) => (
            <li key={f.field} className="flex items-center gap-2" title={`regime.fields[${f.field}]`}>
              <span className="font-mono w-32 truncate">{f.variable}{f.horizon ? ` h${f.horizon}` : ""}</span>
              <span className="flex items-center gap-1" title="brier_model_raw (lower is better)">
                <i className="inline-block h-2 w-2 rounded-full bg-sky-500" /> {f.brier_model_raw ?? "n/a"}
              </span>
              <span className="flex items-center gap-1 text-muted-foreground" title="brier_persistence (null)">
                <i className="inline-block h-2 w-2 rounded-full bg-zinc-400" /> {f.brier_persistence ?? "n/a"}
              </span>
              <span className="flex items-center gap-1 text-muted-foreground" title="brier_base_rate (null)">
                <i className="inline-block h-2 w-2 rounded-full bg-zinc-300" /> {f.brier_base_rate ?? "n/a"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function UpdateRow({ u }: { u: BeliefUpdateRow }) {
  return (
    <li className="flex items-baseline gap-2 py-1 text-xs">
      <Badge variant={u.flipped ? "default" : "outline"} className="shrink-0">
        {u.flipped ? "flip" : "update"}
      </Badge>
      <span className="font-mono font-medium">{u.topic}</span>
      <span className="text-muted-foreground">{u.prior_direction ?? "?"} → {u.direction}</span>
      <span className="tabular-nums text-muted-foreground" title="belief_change">
        (Δ{u.belief_change == null ? "n/a" : u.belief_change.toFixed(3)})
      </span>
      <span className="ml-auto text-muted-foreground shrink-0" title="hours_since_prior">
        {fmtHours(u.hours_since_prior)}
      </span>
    </li>
  );
}

export function WhatChanged({ data }: { data: BrainResponse }) {
  if (!data.belief_updates.length) {
    return <p className="text-xs text-muted-foreground">
      {data.missing_because.belief_updates ?? "no belief_updates rows on this receipt"}
    </p>;
  }
  return <ul className="divide-y divide-border/30">{data.belief_updates.map((u, i) => <UpdateRow key={i} u={u} />)}</ul>;
}
