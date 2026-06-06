// Null-safe formatters for backend-sourced fields.
// Backend often returns null/undefined when data is missing — never call
// .toFixed / .toLocaleString directly on those values.

export const fmtPct = (n: number | null | undefined, digits = 1): string =>
  n != null && Number.isFinite(n) ? `${n.toFixed(digits)}%` : "—";

export const fmtNum = (n: number | null | undefined, digits = 2): string =>
  n != null && Number.isFinite(n) ? n.toFixed(digits) : "—";

export const fmtMoney = (n: number | null | undefined, digits = 0): string =>
  n != null && Number.isFinite(n)
    ? `$${n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
    : "—";

export const fmtInt = (n: number | null | undefined): string =>
  n != null && Number.isFinite(n) ? Math.round(n).toLocaleString() : "—";

export const fmtStr = (s: string | null | undefined, fallback = "—"): string =>
  s ?? fallback;

export const fmtSigned = (n: number | null | undefined, digits = 2): string => {
  if (n == null || !Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}`;
};

export const fmtSignedPct = (n: number | null | undefined, digits = 1): string => {
  if (n == null || !Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}%`;
};
