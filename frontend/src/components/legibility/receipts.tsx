"use client";

/**
 * Shared pieces of the C19 legibility pages (Paper Arena, Forecast Lab, Theory Lab,
 * System Health). Every page prints the receipts it read with their ages, a STALE
 * banner when any is past its limit, and the reason beside every missing value.
 */

import React from "react";
import { AlertTriangle, FileText, Info } from "lucide-react";
import type { LegReceipt } from "@/lib/api";

export function fmtAgeHours(h: number | null | undefined): string {
  if (h == null) return "age n/a";
  if (h < 1) return `${Math.round(h * 60)} min old`;
  if (h < 48) return `${h.toFixed(1)} h old`;
  return `${(h / 24).toFixed(1)} d old`;
}

export function fmtAgeSeconds(s: number | null | undefined): string {
  if (s == null) return "n/a";
  return fmtAgeHours(s / 3600).replace(" old", "");
}

export function num(v: number | null | undefined, digits = 2, signed = false): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${signed && v > 0 ? "+" : ""}${v.toFixed(digits)}`;
}

export function pctFrac(v: number | null | undefined, digits = 1, signed = false): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${signed && v > 0 ? "+" : ""}${(100 * v).toFixed(digits)}%`;
}

export function signTone(v: number | null | undefined): string {
  if (v == null) return "text-muted-foreground";
  if (v > 0) return "text-emerald-700 dark:text-emerald-400";
  if (v < 0) return "text-red-700 dark:text-red-400";
  return "";
}

const STATUS_TONE: Record<string, string> = {
  FRESH: "text-emerald-700 dark:text-emerald-400 border-emerald-600/30",
  STALE: "text-red-700 dark:text-red-400 border-red-600/40",
  UNKNOWN: "text-amber-700 dark:text-amber-400 border-amber-600/40",
  MISSING: "text-zinc-600 dark:text-zinc-400 border-zinc-500/40",
};

/** The receipts strip: one chip per receipt, file path + age + status. */
export function ReceiptStrip({ receipts }: { receipts: LegReceipt[] }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-3">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        <FileText className="h-3.5 w-3.5" /> Receipts this page read
      </div>
      <ul className="grid gap-1.5 sm:grid-cols-2">
        {receipts.map((r, i) => (
          <li key={`${r.kind}-${i}`} className={`min-w-0 rounded border px-2 py-1 text-xs ${STATUS_TONE[r.status] ?? ""}`}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-mono font-semibold truncate">{r.kind}</span>
              <span className="whitespace-nowrap">{r.status} · {fmtAgeHours(r.age_hours)}</span>
            </div>
            <div className="font-mono text-[11px] text-muted-foreground break-all">
              {r.file ?? `none: ${r.missing_because ?? "no receipt"}`}
            </div>
            {r.role && <div className="text-[11px] text-muted-foreground">used for: {r.role}</div>}
            {r.stamp_utc && (
              <div className="text-[11px] text-muted-foreground">
                stamp {r.stamp_utc} · STALE after {fmtAgeHours(r.stale_after_hours).replace(" old", "")}
              </div>
            )}
            {r.sha256 && <div className="font-mono text-[10px] text-muted-foreground" title={r.sha256}>sha256 {r.sha256.slice(0, 16)}…</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A red banner when any receipt is STALE, amber when one is undateable. Never hidden. */
export function StaleBanner({ receipts }: { receipts: LegReceipt[] }) {
  const stale = receipts.filter((r) => r.status === "STALE");
  // MISSING receipts are listed in the strip and the "null today" box, not as a banner.
  const unknown = receipts.filter((r) => r.status === "UNKNOWN");
  if (!stale.length && !unknown.length) return null;
  const bad = stale.length ? stale : unknown;
  return (
    <div
      role="alert"
      className={`flex items-start gap-2 rounded-lg border p-3 text-sm ${
        stale.length
          ? "border-red-600/40 bg-red-500/10 text-red-800 dark:text-red-300"
          : "border-amber-600/40 bg-amber-500/10 text-amber-800 dark:text-amber-300"
      }`}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <b>{stale.length ? "STALE" : "UNKNOWN AGE"}:</b>{" "}
        {bad.map((r) => r.line).join(" · ")}. The numbers below are as of those receipts, not today.
      </div>
    </div>
  );
}

/** A null value printed with its reason, never as zero. */
export function Missing({ why }: { why?: string | null }) {
  return (
    <span className="text-muted-foreground italic" title={why ?? undefined}>
      n/a{why ? <span className="not-italic text-[11px]"> ({why})</span> : null}
    </span>
  );
}

export function MissingList({ missing }: { missing: Record<string, string> }) {
  const entries = Object.entries(missing ?? {});
  if (!entries.length) return null;
  return (
    <div className="rounded-lg border border-border p-3 text-xs text-muted-foreground">
      <div className="mb-1 flex items-center gap-1 font-medium"><Info className="h-3.5 w-3.5" /> What is null today, and why</div>
      <ul className="space-y-0.5">
        {entries.map(([k, v]) => (
          <li key={k}><span className="font-mono">{k}</span>: {v}</li>
        ))}
      </ul>
    </div>
  );
}

const RUNG_TONE: Record<string, string> = {
  OBSERVED: "bg-zinc-500/15 text-zinc-700 dark:text-zinc-300 border-zinc-500/30",
  EARLY_EVIDENCE: "bg-sky-500/15 text-sky-800 dark:text-sky-300 border-sky-500/30",
  REPLICATED: "bg-violet-500/15 text-violet-800 dark:text-violet-300 border-violet-500/30",
  VALIDATED_EDGE: "bg-emerald-500/15 text-emerald-800 dark:text-emerald-300 border-emerald-500/30",
};

/** The evidence label exactly as the receipt wrote it. */
export function EvidenceBadge({ label, rung, why }: { label: string | null; rung: string | null; why?: string | null }) {
  if (!label) return <Missing why={why ?? "no evidence label"} />;
  return (
    <span
      className={`inline-block whitespace-nowrap rounded border px-1.5 py-0.5 font-mono text-[11px] ${RUNG_TONE[rung ?? ""] ?? RUNG_TONE.OBSERVED}`}
      title={why ?? undefined}
    >
      {label}
    </span>
  );
}

/** The evidence ladder legend (roadmap 2026-10-06 section 7). */
export function EvidenceLadder({ ladder }: { ladder: string[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
      <span>Evidence ladder:</span>
      {ladder.map((l, i) => (
        <React.Fragment key={l}>
          <span className={`rounded border px-1.5 py-0.5 font-mono ${RUNG_TONE[l.replace("(n)", "")] ?? ""}`}>{l}</span>
          {i < ladder.length - 1 && <span aria-hidden>→</span>}
        </React.Fragment>
      ))}
      <span>· a label is never upgraded on this page</span>
    </div>
  );
}

/** A query error: 404 is "none written yet", anything else is red. */
export function LoadError({ what, err }: { what: string; err: unknown }) {
  const msg = err instanceof Error ? err.message : String(err);
  const absent = /\b404\b/.test(msg);
  return (
    <div className={`rounded-lg border p-4 text-sm ${absent ? "border-border text-muted-foreground" : "border-red-600/40 text-red-700 dark:text-red-400"}`}>
      {absent ? `${what}: no receipt written yet.` : `${what} could not be read.`}
      <div className="mt-1 text-xs text-muted-foreground break-words">{msg}</div>
    </div>
  );
}

export function SourceNote({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] text-muted-foreground font-mono break-all">source: {children}</p>;
}
