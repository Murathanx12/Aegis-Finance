"use client";

/**
 * The Brain state board (v2, 2026-10-06 spec in
 * docs/design/OPTIMUS_CREATIVE_TOOL_LIBRARY_2026-10-07.md §2 -- "Option A": plain SVG/CSS
 * in React, zero new dependency, state-driven rings, every pixel traces to a receipt field).
 *
 * WHY NOT A FORCE GRAPH (spec §2.1, §4): `beliefs.json` has no "distance" between two
 * beliefs -- it has a signed, lagged, SUPPORTED edge (`co_mention_edges`). A force layout
 * throws the sign and lag away and invents a settling position nobody asked for, and
 * because that position has no fixed point, the whole canvas drifts forever -- which is
 * exactly the owner's complaint ("constantly moving because nodes push each other"). This
 * board is the opposite: THREE FIXED RINGS (macro / sector-theme / geopolitical-regulatory,
 * declared in `TOPIC_RINGS` below, the same pattern as `brain/page.tsx`'s old `GROUPS`
 * table) and a STABLE HASH of the topic id for the angle within its ring. Nothing moves
 * unless the data changes; the canvas is deterministic from `beliefs.json` alone.
 *
 * MOTION THAT MEANS SOMETHING: the one-shot pulse (`.aegis-brain-pulse`, gated OFF entirely
 * under `prefers-reduced-motion: reduce` via a plain CSS media query -- no JS feature
 * detection needed) fires only on an element whose server-computed `recent_change` is true:
 * updated within `pulse_window_hours` OR the direction flipped this cycle
 * (`legibility.brain_payload` / `_belief_row`). It plays once per mount and then stops --
 * never a continuous "breathing" loop, because an idle loop IS the complaint restated
 * (spec §2.3 "Movement"). The SAME fact survives motion off: a static amber ring badge is
 * drawn whenever `recent_change` is true, with or without the animation.
 *
 * EVERY PIXEL TRACES TO A FIELD (spec §4): hovering (or focusing, via keyboard) any orb,
 * edge, scenario bar or regime mark opens a tooltip naming the exact `BrainResponse` field
 * the pixel was drawn from. A belief with no evidence (`has_evidence: false`) is drawn as a
 * HOLLOW outline, never a placeholder dot invented to fill the ring.
 */

import React, { useId, useMemo, useState } from "react";
import type { BeliefRow, BrainResponse, CoMentionEdge } from "@/lib/api";

// ───────────────────────────────────────────────────────────── layout: rings, not physics

/** Declared taxonomy (spec §2.2): a belief's RING is a fixed classification of its topic,
 * never derived from `affected_entities.sectors` at render time (a belief can carry several
 * sectors at once, so sectors cannot drive a single ring position -- they instead become
 * the small chip list in the tooltip). A topic not in this table lands on the outer ring,
 * labelled "other", so a new topic never crashes the board; it is also the honest answer
 * ("not yet classified"), never a silent drop. */
const TOPIC_RINGS: { key: string; label: string; topics: string[] }[] = [
  { key: "macro", label: "Macro", topics: ["rates", "inflation", "credit", "dollar", "liquidity",
    "prediction_market_state"] },
  { key: "sector_theme", label: "Sector / theme", topics: ["ai_demand", "semiconductor_capex",
    "grid_power_demand", "commodity_shortages", "consumer_conditions", "energy_security"] },
  { key: "geopolitical", label: "Geopolitical / regulatory", topics: ["china_policy", "geopolitical_risk",
    "defense_procurement", "biotech_regulatory"] },
];
const RING_INDEX: Record<string, number> = Object.fromEntries(
  TOPIC_RINGS.flatMap((r, i) => r.topics.map((t) => [t, i])),
);
const OTHER_RING = TOPIC_RINGS.length; // an unclassified topic: one ring further out, never dropped

const CENTER = 230;
const RING_R = [72, 132, 192, 230]; // last = OTHER_RING, pinned to the canvas edge
const MIN_ORB_R = 5;
const MAX_ORB_R = 22;
const VIEW = 460;

/** A stable hash of the topic id -> an angle in degrees. Deterministic: the same topic is
 * always at the same angle, every render, every day (spec §2.2) -- nothing here is a layout
 * pass or a "settle" animation. djb2-ish; good enough spread for <= a few dozen topics. */
function hashAngleDeg(topic: string): number {
  let h = 5381;
  for (let i = 0; i < topic.length; i++) h = (h * 33 + topic.charCodeAt(i)) | 0;
  return ((h % 360) + 360) % 360;
}

function ringOf(topic: string): number {
  return RING_INDEX[topic] ?? OTHER_RING;
}

function polar(ring: number, angleDeg: number): { x: number; y: number } {
  const rad = (angleDeg * Math.PI) / 180;
  const r = RING_R[Math.min(ring, RING_R.length - 1)];
  return { x: CENTER + r * Math.cos(rad), y: CENTER + r * Math.sin(rad) };
}

// ───────────────────────────────────────────────────────────── visual channels -> fields

/** direction -> colour-blind-safe Tailwind text-color classes (fill="currentColor" on the
 * orb). `none` (literally no signal, confidence 0) is grey; `mixed` is its OWN hue, never
 * grey, so "no data" and "low-confidence mixed" never look the same (spec §2.3). */
const DIRECTION_TONE: Record<string, string> = {
  up: "text-amber-600 dark:text-amber-400",
  down: "text-sky-700 dark:text-sky-400",
  mixed: "text-violet-600 dark:text-violet-400",
  none: "text-zinc-400 dark:text-zinc-500",
};
const DIRECTION_LABEL: Record<string, string> = {
  up: "up (strengthening)", down: "down (weakening)", mixed: "mixed", none: "none (no signal)",
};

function toneFor(direction: string): string {
  return DIRECTION_TONE[direction] ?? DIRECTION_TONE.none;
}

/** confidence (0..1, `beliefs[].confidence`) -> orb radius, with a floor so a 0-confidence
 * belief is still clickable (spec §2.3 "Size = confidence"). */
function orbRadius(confidence: number | null): number {
  const c = Math.max(0, Math.min(1, confidence ?? 0));
  return MIN_ORB_R + c * (MAX_ORB_R - MIN_ORB_R);
}

/** evidence mass (`mass_up + mass_down`) -> opacity, log-scaled so a handful of early votes
 * already reads as "something", not invisible (spec §2.3 "Brightness = evidence strength"). */
function brightnessOpacity(massUp: number | null, massDown: number | null): number {
  const mass = (massUp ?? 0) + (massDown ?? 0);
  if (mass <= 0) return 0.3;
  const scaled = Math.log1p(mass) / Math.log1p(6);
  return Math.max(0.35, Math.min(1, 0.35 + 0.65 * scaled));
}

function edgeWidth(support: number | null): number {
  return Math.max(1, Math.min(7, 1 + (support ?? 0) * 1.4));
}

// ───────────────────────────────────────────────────────────── tooltip

interface TipState { x: number; y: number; title: string; lines: { field: string; value: string }[] }

function Tooltip({ tip }: { tip: TipState | null }) {
  if (!tip) return null;
  const left = Math.min(Math.max(tip.x, 8), (typeof window !== "undefined" ? window.innerWidth : 1200) - 280);
  return (
    <div
      role="tooltip"
      className="pointer-events-none fixed z-50 max-w-[280px] rounded-lg border border-border bg-popover
        p-2.5 text-xs text-popover-foreground shadow-lg"
      style={{ left, top: tip.y + 14 }}
    >
      <p className="font-semibold mb-1">{tip.title}</p>
      <dl className="space-y-0.5">
        {tip.lines.map((l, i) => (
          <div key={i} className="flex justify-between gap-3">
            <dt className="font-mono text-[10px] text-muted-foreground">{l.field}</dt>
            <dd className="tabular-nums text-right">{l.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function num(v: number | null, digits = 3): string {
  return v == null ? "n/a" : v.toFixed(digits);
}

// ───────────────────────────────────────────────────────────── the board

function BeliefOrb({ b, pos, onTip, onLeave }: {
  b: BeliefRow; pos: { x: number; y: number };
  onTip: (e: React.SyntheticEvent, tip: TipState) => void; onLeave: () => void;
}) {
  const tone = toneFor(b.direction);
  const r = orbRadius(b.confidence);
  const hollow = !b.has_evidence;
  const op = hollow ? 1 : brightnessOpacity(b.mass_up, b.mass_down);
  const show = (e: React.SyntheticEvent) => onTip(e, {
    x: (e as unknown as React.MouseEvent).clientX ?? pos.x, y: (e as unknown as React.MouseEvent).clientY ?? pos.y,
    title: `${b.topic} -- ${b.meaning ?? "no gloss recorded"}`,
    lines: [
      { field: "direction (prior)", value: `${DIRECTION_LABEL[b.direction] ?? b.direction} (was ${b.prior_direction ?? "n/a"})` },
      { field: "confidence", value: num(b.confidence, 4) },
      { field: "mass_up / mass_down", value: `${num(b.mass_up, 3)} / ${num(b.mass_down, 3)}` },
      { field: "half_life_days", value: b.half_life_days == null ? "n/a" : `${b.half_life_days}` },
      { field: "hours_since_update", value: b.hours_since_update == null ? "n/a" : `${b.hours_since_update} h` },
      { field: "n_contradictions", value: `${b.n_contradictions}` },
      { field: "evidence_basis", value: b.evidence_basis ?? (hollow ? "no evidence" : "n/a") },
      { field: "sectors", value: b.sectors.length ? b.sectors.join(", ") : "none listed" },
    ],
  });
  return (
    <g
      tabIndex={0} role="img"
      aria-label={`${b.topic}: ${DIRECTION_LABEL[b.direction] ?? b.direction}, confidence ${num(b.confidence, 2)}${hollow ? ", no evidence" : ""}`}
      onMouseMove={show} onFocus={show} onMouseLeave={onLeave} onBlur={onLeave}
      className={`${tone} cursor-pointer outline-none`}
      style={{ transformBox: "fill-box", transformOrigin: "center" } as React.CSSProperties}
    >
      {b.contradicted && (
        <circle cx={pos.x} cy={pos.y} r={r + 4} fill="none" stroke="currentColor"
          className="text-red-500 dark:text-red-400" strokeWidth={1.3} strokeDasharray="3 2.5" opacity={0.85} />
      )}
      <circle
        cx={pos.x} cy={pos.y} r={r}
        fill={hollow ? "none" : "currentColor"} stroke="currentColor" strokeWidth={hollow ? 1.6 : 0.5}
        opacity={op}
        className={b.recent_change ? "aegis-brain-pulse" : undefined}
      />
      {b.recent_change && (
        <circle cx={pos.x + r * 0.62} cy={pos.y - r * 0.62} r={3.1} className="text-amber-500 dark:text-amber-400"
          fill="currentColor" stroke="var(--background)" strokeWidth={1} aria-hidden />
      )}
      <text x={pos.x} y={pos.y + r + 11} textAnchor="middle" className="fill-muted-foreground"
        style={{ fontSize: 8.5, pointerEvents: "none" }}>
        {b.topic.length > 14 ? `${b.topic.slice(0, 13)}…` : b.topic}
      </text>
    </g>
  );
}

export default function StateBoard({ data }: { data: BrainResponse }) {
  const uid = useId();
  const [tip, setTip] = useState<TipState | null>(null);
  const onTip = (e: React.SyntheticEvent, t: TipState) => setTip(t);
  const onLeave = () => setTip(null);

  const positions = useMemo(() => {
    const out: Record<string, { x: number; y: number; ring: number }> = {};
    for (const b of data.beliefs) {
      const ring = ringOf(b.topic);
      out[b.topic] = { ...polar(ring, hashAngleDeg(b.topic)), ring };
    }
    return out;
  }, [data.beliefs]);

  const edges: { from: string; e: CoMentionEdge }[] = useMemo(
    () => data.beliefs.flatMap((b) => b.co_mention_edges
      .filter((e) => positions[e.to])                 // an edge to an unlisted topic is dropped, not invented
      .map((e) => ({ from: b.topic, e }))),
    [data.beliefs, positions],
  );

  const ringsPresent = TOPIC_RINGS.map((r, i) => ({
    ...r, n: data.beliefs.filter((b) => ringOf(b.topic) === i).length,
  })).filter((r) => r.n > 0);
  const nOther = data.beliefs.filter((b) => ringOf(b.topic) === OTHER_RING).length;

  const statesPresent = new Set(data.beliefs.map((b) => b.direction));
  const anyContradiction = data.beliefs.some((b) => b.contradicted);
  const anyHollow = data.beliefs.some((b) => !b.has_evidence);
  const anyNegativeEdge = edges.some(({ e }) => e.sign === "-");

  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_240px]" onMouseLeave={onLeave}>
      {/* the board */}
      <div className="rounded-xl border border-border bg-card p-2">
        <svg viewBox={`0 0 ${VIEW} ${VIEW}`} className="w-full h-auto" role="group"
          aria-label="Belief state board: fixed rings by topic cluster; orb size is confidence, colour is direction">
          <defs>
            <radialGradient id={`${uid}-bg`} cx="50%" cy="50%" r="75%">
              <stop offset="0%" stopColor="currentColor" stopOpacity={0.05} />
              <stop offset="100%" stopColor="currentColor" stopOpacity={0} />
            </radialGradient>
          </defs>
          <circle cx={CENTER} cy={CENTER} r={RING_R[2] + 20} className="text-foreground" fill={`url(#${uid}-bg)`} />
          {/* fixed rings -- never animated, never re-laid-out */}
          {TOPIC_RINGS.map((r, i) => (
            <circle key={r.key} cx={CENTER} cy={CENTER} r={RING_R[i]} fill="none"
              className="text-foreground/10" stroke="currentColor" strokeWidth={1} />
          ))}
          {/* edges = co_mention_edges; thickness = support; dashed = sign "-" */}
          <g className="text-foreground/35">
            {edges.map(({ from, e }, i) => {
              const a = positions[from], z = positions[e.to];
              if (!a || !z) return null;
              return (
                <line key={`${from}-${e.to}-${i}`} x1={a.x} y1={a.y} x2={z.x} y2={z.y}
                  stroke="currentColor" strokeWidth={edgeWidth(e.support)}
                  strokeDasharray={e.sign === "-" ? "5 4" : undefined}
                  opacity={0.55}
                  onMouseMove={(ev) => onTip(ev, {
                    x: ev.clientX, y: ev.clientY, title: `${from} → ${e.to}`,
                    lines: [
                      { field: "sign", value: e.sign === "-" ? "negative (dashed)" : "positive" },
                      { field: "co_mention_edges[].support", value: `${e.support ?? "n/a"} (NOT marginal contribution)` },
                      { field: "lag_sessions", value: e.lag_sessions == null ? "n/a" : `${e.lag_sessions}` },
                      { field: "example_theme", value: e.example_theme ?? "n/a" },
                    ],
                  })}
                  onMouseLeave={onLeave}
                  className="cursor-pointer hover:opacity-90"
                />
              );
            })}
          </g>
          {data.beliefs.map((b) => {
            const p = positions[b.topic];
            if (!p) return null;
            return <BeliefOrb key={b.topic} b={b} pos={p} onTip={onTip} onLeave={onLeave} />;
          })}
        </svg>
        <p className="mt-1 text-center text-[11px] text-muted-foreground">
          {data.as_of ? `belief table as of ${data.as_of.slice(0, 16).replace("T", " ")} UTC` : "no as_of on the belief table"}
          {" · "}pulse window {data.pulse_window_hours} h
        </p>
      </div>

      {/* legend -- its own column on wide screens, below on phones; never overlaid; state-driven */}
      <aside className="rounded-xl border border-border bg-card p-3 text-xs space-y-3 self-start">
        <div>
          <p className="font-semibold mb-1">Rings (fixed, declared)</p>
          <ul className="space-y-0.5 text-muted-foreground">
            {ringsPresent.map((r) => <li key={r.key}>{r.label}: {r.n}</li>)}
            {nOther > 0 && <li>Other (unclassified topic): {nOther}</li>}
          </ul>
        </div>
        <div>
          <p className="font-semibold mb-1">Colour = direction</p>
          <ul className="space-y-1">
            {(["up", "down", "mixed", "none"] as const).filter((d) => statesPresent.has(d)).map((d) => (
              <li key={d} className="flex items-center gap-1.5">
                <span className={`inline-block h-2.5 w-2.5 rounded-full ${toneFor(d)}`} style={{ background: "currentColor" }} />
                <span>{DIRECTION_LABEL[d]}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="text-muted-foreground space-y-1">
          <p>Size = confidence (floor so 0 stays clickable). Brightness = evidence mass.</p>
          {anyHollow && <p>Hollow outline = no evidence yet.</p>}
          {anyContradiction && <p>Dashed red ring = a logged contradiction.</p>}
          {anyNegativeEdge && <p>Dashed edge = negative co-mention sign.</p>}
          <p>Edge thickness = {data.co_mention_label}.</p>
          <p className="pt-1 border-t border-border/50">Amber dot = changed in the last {data.pulse_window_hours} h or flipped this cycle (same fact with motion off).</p>
        </div>
      </aside>

      <Tooltip tip={tip} />
      {/* the one-shot pulse. Gated OFF under reduced motion by a plain media query -- no JS
          detection, so "no animation" is a CSS fact, not a runtime guess. */}
      <style>{`
        @media (prefers-reduced-motion: no-preference) {
          .aegis-brain-pulse { animation: aegis-brain-pulse-kf 1.6s ease-out 1; }
        }
        @keyframes aegis-brain-pulse-kf {
          0% { transform: scale(1); }
          35% { transform: scale(1.4); }
          100% { transform: scale(1); }
        }
      `}</style>
    </div>
  );
}
