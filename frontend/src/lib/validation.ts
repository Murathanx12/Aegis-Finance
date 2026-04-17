/**
 * Lightweight client-side validation helpers.
 *
 * We deliberately avoid zod to keep the bundle small and stay in sync with
 * the regex the backend routers use (see backend/routers/stock.py _TICKER_RE).
 */

// Matches backend's `^[A-Z0-9.\-]{1,10}$`
const TICKER_RE = /^[A-Z0-9.\-]{1,10}$/;

export function isValidTicker(raw: string): boolean {
  return TICKER_RE.test(raw.trim().toUpperCase());
}

export function normalizeTicker(raw: string): string {
  return raw.trim().toUpperCase();
}

export function validateTicker(raw: string): { ok: true; ticker: string } | { ok: false; error: string } {
  const t = normalizeTicker(raw);
  if (!t) return { ok: false, error: "Ticker is required" };
  if (!TICKER_RE.test(t)) return { ok: false, error: "Use 1–10 characters: letters, digits, dot, dash" };
  return { ok: true, ticker: t };
}

export function validatePositiveNumber(raw: string | number, field: string): { ok: true; value: number } | { ok: false; error: string } {
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n)) return { ok: false, error: `${field} must be a number` };
  if (n <= 0) return { ok: false, error: `${field} must be greater than zero` };
  return { ok: true, value: n };
}

export function validateAge(current: number, retirement: number): string | null {
  if (!Number.isFinite(current) || current < 0 || current > 120) return "Current age must be 0–120";
  if (!Number.isFinite(retirement) || retirement < current) return "Retirement age must be ≥ current age";
  if (retirement > 120) return "Retirement age must be ≤ 120";
  return null;
}
