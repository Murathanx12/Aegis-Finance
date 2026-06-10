# Track Record Policy

> Which performance numbers Aegis shows, what each one is, and the exact
> language used. Goal: a visitor can never find two pages telling different
> performance stories. (V2 P0 #4 — the Sharpe-contradiction fix.)

## The one canonical record

**The live forward NAV** is Aegis's only performance track record:

- Source: `paper_nav` table — daily mark-to-market of the three reference
  lanes ($100k notional each), written by the hourly MTM scheduler on
  Railway since **inception 2026-06-08** (config `82be14cb6039bfae`).
- Exposed at `GET /api/pi/reference/{lane}/history` with per-point
  `config_version` so rule changes render as labeled segment boundaries.
- Properties that make it canonical: forward-only (no hindsight), externally
  timestamped (server writes, not retro-computed), survivorship-free
  (decisions recorded before outcomes), and **uncopyable** — it accrues only
  with elapsed time.
- **No skill claims before 24 months of tracked decisions** (config
  `skill_min_months: 24`). Until then the record is shown with its age and
  no performance adjectives.

## Everything else is methodology, not performance

| Surface | What it actually is | Label it must carry |
|---|---|---|
| `/portfolio-intelligence/reference` (walk-forward replay) | Simulation of the current rules over 2021–2025, fixed universe, crash-prob stub | "Methodology backtest — not the track record" |
| `/portfolio-intelligence/compare` (replay curves + period metric packs) | Backtested/static comparison vs SPY/AGG/60-40 | "Methodology comparison (backtested) — not the track record" |
| `docs/replay_report_v1.md` | Generated replay diagnostics | Header already states engine + period |

**Why the two replay-derived Sharpes differ (0.65 vs 0.95 class of
contradiction):** different windows, different cash/rf handling, and the
replay's `crash_prob_override` stub. They are *simulations of methodology*,
useful for understanding the rules' behavior — they are not, and must never
be presented as, what Aegis has actually done. The live forward NAV is what
Aegis has actually done.

## Exact UI language (the shared banner)

Every methodology page renders the shared `MethodologyBanner` component
(`frontend/src/components/methodology-banner.tsx`):

> **Backtest, not the track record.** Numbers on this page are simulated by
> replaying today's rules over 2021–2025 with a fixed universe (survivorship
> caveat: docs/replay_diagnostics_v1.md). Aegis's real performance record is
> the live forward paper-portfolio NAV, marked daily since 2026-06-08 — it
> is young, and we make no skill claims before 24 months of tracked
> decisions. Educational tool, not financial advice.

Rules for any future page:
1. A number derived from `paper_nav` may be called "track record."
2. A number derived from replay/compare/any backtest must carry the banner
   and may not use the words "track record" or "performance" unqualified.
3. New signals shown without a measured out-of-sample number are labeled
   "descriptive."

## Status

- 2026-06-10: policy written; `MethodologyBanner` replaces the three
  duplicated survivorship disclaimers on PI pages. The live equity-curve UI
  (P0 #2) renders the canonical record once the history endpoint deploy is
  verified.
