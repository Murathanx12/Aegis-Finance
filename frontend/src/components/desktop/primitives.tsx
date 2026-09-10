"use client";

import { Badge } from "@/components/ui/badge";
import {
  ControlError,
  errorText,
  isForbidden,
  isNotBuilt,
  isUnreachable,
  pickNumber,
} from "@/lib/control-api";

/** Nothing measured. One glyph, used everywhere, never a zero or a guess. */
export const DASH = "—";

export function fmtBytes(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return DASH;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

export function fmtUtc(s: string | null | undefined): string {
  if (!s) return DASH;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString();
}

export function ageLabel(s: string | null | undefined): string {
  if (!s) return DASH;
  const t = new Date(s).getTime();
  if (Number.isNaN(t)) return DASH;
  const secs = Math.max(0, (Date.now() - t) / 1000);
  if (secs < 90) return `${Math.round(secs)}s ago`;
  if (secs < 5400) return `${Math.round(secs / 60)}m ago`;
  return `${(secs / 3600).toFixed(1)}h ago`;
}

/** A label / value row. `value === null` prints the em dash, not an empty cell. */
export function Field({
  label,
  value,
  mono = false,
  title,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  title?: string;
}) {
  const empty = value == null || value === "";
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span
        title={title}
        className={`text-xs text-right break-all ${mono ? "font-mono" : ""} ${
          empty ? "text-muted-foreground" : "text-foreground"
        }`}
      >
        {empty ? DASH : value}
      </span>
    </div>
  );
}

/**
 * The one place an API failure is turned into words.
 *
 * A 404 on an endpoint that is still being written is a STATE of this build, not
 * an error the user caused — it says so, and the page keeps rendering everything
 * else. A 403 names the flag that would fix it.
 */
export function ApiState({ error, what }: { error: unknown; what: string }) {
  if (!error) return null;
  let headline: string;
  let tone = "text-muted-foreground";
  if (isNotBuilt(error)) {
    headline = `${what}: endpoint not built yet (404). Nothing is shown rather than something invented.`;
  } else if (isForbidden(error)) {
    headline = `${what}: the control plane is read-only here. Mutating routes need AEGIS_CONTROL_ENABLED=1, which the desktop shell sets on its own environment.`;
  } else if (isUnreachable(error)) {
    headline = `${what}: the backend did not answer. Is it running?`;
    tone = "text-destructive";
  } else {
    headline = `${what}: ${errorText(error)}`;
    tone = "text-destructive";
  }
  return (
    <p className={`text-xs ${tone}`}>
      {headline}
      {error instanceof ControlError && error.status > 0 && !isNotBuilt(error) ? (
        <span className="font-mono opacity-70"> [{error.status}]</span>
      ) : null}
    </p>
  );
}

/**
 * The raw payload, collapsed.
 *
 * Every one of these pages reads endpoints whose field names are not frozen. If
 * a key exists that the UI does not know how to name, it must still be visible —
 * otherwise the page silently drops a measurement (the house failure mode).
 */
export function RawPayload({ data, label = "raw payload" }: { data: unknown; label?: string }) {
  if (data == null) return null;
  return (
    <details className="mt-3">
      <summary className="cursor-pointer text-[11px] text-muted-foreground hover:text-foreground">
        {label}
      </summary>
      <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-muted/40 p-2 text-[11px] leading-relaxed font-mono">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}

export function YesNo({ v, yes, no }: { v: boolean | null; yes: string; no: string }) {
  if (v == null) return <Badge variant="outline">unknown</Badge>;
  return <Badge variant={v ? "default" : "destructive"}>{v ? yes : no}</Badge>;
}

// ------------------------------------------------------------- estimates

export interface ReadEstimate {
  value: number | null;
  se: number | null;
  ciLo: number | null;
  ciHi: number | null;
  n: number | null;
}

/**
 * Read one estimate out of a payload node, in whatever shape it arrived.
 *
 * A bare number is accepted as a value with NO uncertainty — and the renderer
 * below then refuses to print it as an estimate. That is the point: "β 0.18 ±
 * 2.21 is not a beta", and β 0.18 with no error bar at all is less than that.
 */
export function readEstimate(node: unknown): ReadEstimate {
  if (typeof node === "number" && Number.isFinite(node)) {
    return { value: node, se: null, ciLo: null, ciHi: null, n: null };
  }
  return {
    value: pickNumber(node, ["value", "estimate", "point", "point_estimate", "mean", "beta", "coef"]),
    se: pickNumber(node, ["se", "std_err", "std_error", "stderr", "standard_error", "sigma"]),
    ciLo: pickNumber(node, ["ci_lo", "ci_low", "ci_lower", "lo", "lower", "ci95_lo"]),
    ciHi: pickNumber(node, ["ci_hi", "ci_high", "ci_upper", "hi", "upper", "ci95_hi"]),
    n: pickNumber(node, ["n", "n_obs", "nobs", "n_effective", "sessions", "n_blocks"]),
  };
}

/**
 * Render an estimate WITH its uncertainty, or refuse.
 *
 * Handoff 09-10 §4.5: uncertainty travels with the estimate. If the payload
 * carries no standard error and no interval, this prints "not estimable" and
 * shows the bare value only as struck-through context — a number without an
 * error bar must not read as a result.
 */
export function EstimateValue({
  est,
  digits = 2,
  suffix = "",
}: {
  est: ReadEstimate;
  digits?: number;
  suffix?: string;
}) {
  const f = (v: number) => `${v.toFixed(digits)}${suffix}`;
  if (est.value == null) {
    return <span className="text-muted-foreground">{DASH}</span>;
  }
  if (est.se != null) {
    return (
      <span className="tabular-nums">
        <span className="font-medium">{f(est.value)}</span>
        <span className="text-muted-foreground"> ± {f(est.se)}</span>
        {est.n != null ? (
          <span className="text-muted-foreground"> (n={est.n})</span>
        ) : null}
      </span>
    );
  }
  if (est.ciLo != null && est.ciHi != null) {
    return (
      <span className="tabular-nums">
        <span className="font-medium">{f(est.value)}</span>
        <span className="text-muted-foreground">
          {" "}
          [{f(est.ciLo)}, {f(est.ciHi)}]
        </span>
        {est.n != null ? (
          <span className="text-muted-foreground"> (n={est.n})</span>
        ) : null}
      </span>
    );
  }
  return (
    <span className="tabular-nums">
      <Badge variant="outline">not estimable</Badge>
      <span className="ml-2 text-[11px] text-muted-foreground">
        payload carries {f(est.value)} with no standard error or interval
      </span>
    </span>
  );
}
