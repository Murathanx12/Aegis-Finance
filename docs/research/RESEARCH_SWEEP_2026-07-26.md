# Self-directed research sweep — 2026-07-26

Not an AI-panel round: my own two-agent sweep (publications 2023-26 +
open-source projects), citations verified at source. Every adoption below
went through the prior-check gate (first procedural use — it killed two of
my own candidates) and the literature gate (killed a third pre-registration).

## What the sweep changed TODAY

1. **Batch 9 registered & run** (`f7f743d`): conn_mom (Ali-Hirshleifer
   shared-analyst momentum — the strongest IBES-native signal we had never
   tested, alpha 1.68%/mo t 9.67 in-sample, subsumes industry/customer
   momentum; computable from ibes_ptgdet pairs), industry_mom (LOW prior —
   flat since ~2000 per Linnainmaa — kept as the subsumption baseline),
   comp_issue_5y (Daniel-Titman; ~40% absorbed by investment factor,
   low-turnover survivor class). Cumulative 152.
2. **Pre-registration kills (the gates working):** low-beta long-only
   (closed low-vol family in new clothing — prior-check); NOA level (closed
   inverted accruals family — prior-check); **ea_prem** (Frazzini-Lamont
   announcement premium — literature gate: Heitz et al. show the US premium
   DISAPPEARED post-2004 via 8-K migration, exactly our window). Three
   candidates killed before burning DSR slots.
3. **INSTR-VOC registered & run**: falsification of Kelly-Malamud-Zhou
   "virtue of complexity" (JF 2024) on our own market series, with the
   Nagel (2025) mechanical twin (vol-timed linear momentum through an
   IDENTICAL position pipeline — the Buncic no-handicapping fix) as the
   decisive benchmark. Three critique groups say the claim is an artifact;
   the receipt decides whether complexity methods ever enter this factory.
4. **OSAP SignalDoc banked**: Chen-Zimmermann's 331-signal replication
   metadata (in-sample t-stats, sample windows, construction specs) →
   `data/reference/osap_SignalDoc_snap20260726.csv`. The calibration
   benchmark for our factory's scans.

## Borrow list (from the open-source sweep, priority order)

1. **OSAP `openassetpricing` pip package** — monthly returns for 212
   replicated predictors. Future instrument: INSTR-CZ-CALIB (correlate our
   explore t's with their replicated t's + post-publication windows — a
   quantitative version of the decay-landscape receipt batch 2 found
   qualitatively). Data free w/ citation; code GPL-2.
2. **Tidy Finance Python** (actively maintained, MIT) — full CRSP/Compustat
   FF-factor replication validated against Ken French. Future instrument:
   INSTR-HARNESS-VALID — require our plumbing to reproduce French-factor
   correlations. One-day validation of the whole data layer.
3. **Novy-Marx-Velikov AssayingAnomalies + Chen-Velikov** — the published
   effective-spread cost model (low-frequency combination estimates). Port
   to Python → our net-t gates become citable instead of flat-25/50bps.
   (Their receipt: average anomaly nets ~4 bps/mo — our 146-candidate
   ledger found the same class-level answer independently.)
4. **JKP Global Factor Data** (free, CC BY-NC; code MIT, pushed this week)
   — second calibration set with a different construction philosophy;
   the jkp-data repo doubles as a reference implementation to diff our
   Compustat feature code against.
5. **skfolio** (WATCH) — combinatorial-purged-CV over allocators if the
   allocation layer ever needs model selection.

## Refused

- **AlphaGen / gplearn genetic alpha mining** — no license (AlphaGen) and,
  decisively, RL-mined formulaic alphas are anti-pre-registration by
  construction. Only admissible use ever: a mass-mined NULL distribution to
  calibrate multiplicity corrections (noted, not planned).
- **zipline/bt/ffn/ghostfolio** — duplicate the house harness/lanes.
- **Hudson & Thames libs** — abandoned or license-encumbered.
- **Factor momentum (Ehsani-Linnainmaa)** — real, but Falck-Rej-Thesmar
  show the distinct-from-stock-momentum component lives at the 1-MONTH
  horizon = the turnover class our ledger says cannot pay costs; and our
  signals are long-only legs (factor TSMOM evidence is long-short).
  Refused for the factory; noted for the allocation layer someday.
- **IPCA** — identification critiques (Zhang 2024-25) + semi-maintained
  package; "characteristics are covariances" headline not deploy-relevant
  for us. Watch.
- **Cash-flow duration** — subsumed by value/profitability/duration overlap
  (Gormsen-Lazarus); we hold the ingredients already.
- **Institutional trade dispersion (JBF 2024)** — one venue, no independent
  replication, short-leg-heavy. Too green.

## Queued with requirements (next sessions)

- **INSTR-ANOMALY-TIME** (Bowles-Reed-Ringgenberg-Thornock JF 2024 —
  the sweep's most actionable finding): anomaly returns concentrate in the
  first month after information RELEASE; our FundStore uses datadate+6mo.
  One pre-registered variant: gp-small with rdq-based availability instead
  of the +6mo convention. If it improves the confirmed survivor, every
  fundamentals signal inherits the fix; if not, receipt recorded. HIGH
  priority — it upgrades the one thing we know works.
- INSTR-CZ-CALIB + INSTR-HARNESS-VALID + Chen-Velikov cost-model port (the
  three calibration instruments above).
- conn_mom follow-ups only if batch 9 shows IC: the Ali-Hirshleifer
  low-turnover variant (12m connected return) as a separate registration.

Scoreboard: cumulative explore candidates **152**.
