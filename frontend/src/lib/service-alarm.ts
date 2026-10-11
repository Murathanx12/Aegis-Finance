import type { ServiceAlarm } from "./api";

type Row = {
  alarm?: ServiceAlarm;
  evidence_utc?: string | null;
  evidence_mode?: string | null;
  valid_until_utc?: string | null;
};

function stamp(value: string | null | undefined): number {
  return value && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? Date.parse(value) : NaN;
}

/** Requalify a cached light at the local clock; never clear a recorded fault. */
export function currentServiceLight(row: Row, current: boolean, now: number): ServiceAlarm["light"] {
  const light = row.alarm?.light;
  if (light === "RED") return "RED";
  if (!current || !Number.isFinite(now) || !light || !["RED", "AMBER", "BLUE", "GREEN"].includes(light)) return "AMBER";
  if (light !== "GREEN") return light;
  if (row.evidence_utc != null) {
    const evidence = stamp(row.evidence_utc);
    if (!Number.isFinite(evidence) || evidence > now) return "AMBER";
  }
  const mode = row.alarm?.evidence_mode ?? row.evidence_mode;
  const deadlineText = row.alarm?.valid_until_utc ?? row.valid_until_utc;
  if (deadlineText != null) {
    const deadline = stamp(deadlineText);
    if (!Number.isFinite(deadline)) return "AMBER";
    if (now > deadline) return "RED";
  } else if (mode === "DYNAMIC") return "AMBER";
  // Calendar/static/declared idle were qualified by the server. Their snapshot
  // must still be current; sim/task idle windows supply their own deadline.
  return ["DYNAMIC", "STATIC_PROOF", "SESSION_DATA", "DECLARED_IDLE"].includes(mode ?? "") ? "GREEN" : "AMBER";
}

export function currentPanelLight(rows: Row[], recorded: ServiceAlarm | undefined,
  current: boolean, now: number): ServiceAlarm["light"] {
  const lights = rows.map((r) => currentServiceLight(r, current, now));
  if (recorded?.light === "RED" || lights.includes("RED")) return "RED";
  if (!current || !rows.length || !recorded || recorded.light === "AMBER" || lights.includes("AMBER")) return "AMBER";
  if (recorded.light === "BLUE" || lights.includes("BLUE")) return "BLUE";
  return recorded.light === "GREEN" ? "GREEN" : "AMBER";
}
