# Aegis — Full Project Report & Self-Review (2026-07-26)

Written for external review. Covers: what exists, what this session did, what
the whole arc has produced, an honest self-review of the research and the
product, what production needs, where the pivot is, and the concrete queue.

---

## 1. What this project is

Two coupled repos, one owner (Murat, HKU freshman; goals: portfolio piece +
research paper + genuinely learning whether the market can be beaten):

- **Aegis Finance** (`aegis-finance`, deployed): free open-source market
  intelligence platform. FastAPI backend (~100 services, 19 routers, 130+
  endpoints) + Next.js frontend. ML crash model, Monte Carlo, portfolio
  construction (BL/HRP/CVaR), macro dashboard, options/earnings/insider
  intelligence, SHAP explainability, ~2,500 fast tests. Live on Railway +
  Vercel with an unbroken **forward paper track record since 2026-06-08**:
  8 live lanes ($100k each) marked to market hourly, NAV integrity
  hash-guarded, plus forward-IC clocks for insider, revisions, multi-factor,
  congress, ARK, and Murat's own conviction picks.
- **Aegis Investor Brain** (`Aegis module`, research): the offline research
  lab. Point-in-time WRDS data (CRSP, Compustat incl. fundq/rdq, IBES,
  BoardEx starters, openFDA, SEC Form 4), a **Strategy Factory** with a
  hard explore/confirm wall (explore 2004-2018, confirm 2019-2024 held out),
  pre-registration of every hypothesis before any data touch, honest costs,
  DSR deflation by cumulative candidate count, and a public graveyard
  (`NEGATIVE_RESULTS.md`, 16 sections).

The governing discipline (CANON): pre-register → one shot → held-out
confirm → forward paper verification → never re-litigate. If it isn't
pre-registered, it didn't happen.

---

## 2. This session (round 7, 2026-07-26)

1. **INSTR-ANOMALY-TIME executed — the factory's first UPGRADE-class
   verdict (candidate #153).** Re-timed the confirmed survivor's (gp-small)
   fundamental availability from the academic `datadate+6mo` convention to
   the actual Q4 earnings announcement date (`rdq`): 90.2% of 136,546
   firm-years re-timed, median **4.0 months of information reclaimed**.
   Held-out confirm: +24.1 → +33.5 bps/mo net (t 0.89 → 1.24, IC t 4.35).
   All frozen bars cleared → EAD availability **adopted for the entire
   fundamentals stack**. Both hands disclosed: the paired book-level gain
   is only +2.7–3.3 bps/mo; ~70% of the headline is benchmark-composition.
   Adoption rests on PIT-correctness + costless weak-positive, not the
   headline.
2. **Two external reviews adjudicated** (`AI_PANEL_2026-07-26.md`): EAD
   upgrade adopted+executed; Chen-Velikov cost model queued; cash-flow
   volatility and idiosyncratic-skewness proposals refused as closed-family
   re-litigations (earn_stab, skew_low/max_low receipts); inventory-EAD
   retry now admissible; stale premises corrected again.
3. **prior_check gate hardened after a disclosed near-miss**: whole quoted
   phrases searched as single literals returned "no priors" on families
   that WERE in the graveyard. Fixed (word-split + stems) and recorded —
   a safety gate that fails open on bad input is silent fragility.
4. **Sector-fund receipt** for Murat's question: XLV beats SPY in 74% of
   rolling 10-year windows yet loses full-period 1999–2026 (8.2% vs 8.5%
   CAGR); XLK's full-period win is one regime bought with an −82% drawdown.
   Bank sector funds = concentrated sector beta + survivorship, not
   stock-picking skill. Replicable by holding the ETF; it is an ALLOCATOR
   bet, not alpha.

---

## 3. The whole arc, compressed

- **Mar–Apr 2026 (V1–V13):** full-stack platform built out to ~45 features
  (crash model, MC engine, portfolio optimizers, factor models, stress
  testing, TA, attribution, retirement MC, …) + autonomous overnight R&D lab.
- **Jun 2026 (V2/V3):** the epistemics turn. Overfitting guards (PSR/DSR/
  PBO/CPCV) wired into a gate; paper-trading lanes + forward NAV; trial
  registry; the finding that **free data cannot certify alpha** (yfinance
  survivorship — T7), so all selection claims validate FORWARD only.
- **Jul 2026 (V4/V5 + Brain):** WRDS point-in-time layer; Strategy Factory;
  seven AI-panel adjudication rounds; **153 pre-registered candidates**
  through the wall. Survivors: **BRAIN-003** (opportunistic insider buys,
  weak-positive, forward clock to 2027-07), **BRAIN-008** (small-cap gross
  profitability, confirm PASS, DSR 0.098 disclosed), **BRAIN-007** (insider
  + quality fusion, live SMQ lane), **INSTR-TSMOM-XA** (cross-asset trend,
  the first macro survivor — crisis alpha 2008/2020/2022, return drag
  disclosed → defensive, not beat-SPY). Everything else: killed, with
  receipts, including five published-anomaly sign reversals, the
  channel-stuffing/supplier theses both directions, FDA drift at both
  resolutions, and the "virtue of complexity" (INSTR-VOC: not supported;
  complexity class barred).
- **Methodology instruments** (the lab studying itself): INSTR-OVERFIT-
  CEILING (measured our own zero-skill E[max t] ≈ 3.6–4.0 and calibrated
  the mining alarm), INSTR-HOLD-HORIZON, prior-check gate, 4-tag signal
  taxonomy, OSAP SignalDoc calibration benchmark banked.

**The headline result of five months:** long-only cross-sectional
stock-picking on public data, at honest costs, in large/mid caps, is dead —
measured, not assumed, across 153 candidates. What survives is small,
slow, and information-based (small-cap quality, insider filings), plus
defensive allocation overlays. Our own scans independently reproduce the
published factor-decay landscape (McLean-Pontiff), which is evidence the
harness measures what it claims.

---

## 4. Self-review — as RESEARCH

**Strengths (genuinely rare, at any level):**
- Pre-registration with frozen decision rules and tamper-evident commits,
  a held-out confirm wall that has killed its own first graduate
  (conc_low), one-shot runs, a deflation ledger, and a public
  negative-results file. This is closer to registered-report standards
  than most published factor research.
- Falsification instruments aimed at ourselves (overfit ceiling, VOC,
  prior-check) — the lab measures its own capacity for self-deception.
- Full PIT data discipline end to end, now upgraded to true announcement
  dates (this session).
- Honest reporting culture: every PASS ships with its caveats (DSR 0.098,
  NW t 0.77, benchmark-composition decomposition).

**Weaknesses (a referee would say):**
- **One sample.** Effectively a single 21-year US window; confirm is 72
  months (power ~1.2t at realistic effect sizes — acknowledged in the
  registrations, but it means survivors are "weak-positive priors," not
  established effects). The 1963-2001 extension helps but shares the
  regime problem.
- **Cost model is blunt.** Flat 25/50 bps; small-cap effective spreads are
  time-varying. Chen-Velikov port is queued — until then, small-cap
  results carry a cost-model asterisk.
- **Single researcher, single pipeline.** No independent replication of
  the harness (INSTR-HARNESS-VALID vs Tidy Finance/Ken French is queued
  precisely to close this).
- **Survivors have factor-tilt risk** (gp-small FF6 alpha is negative) —
  the premium may be compensated exposure, not mispricing.
- Forward clocks are young: no skill claims before 24 months by our own
  rule; earliest decision 2027-07.

**What the research is worth:** the *negative* result is the contribution.
"A pre-registered, cost-honest factory of 153 candidates run by a retail
researcher on institutional PIT data: what survives?" is a publishable
paper (SSRN preprint + HKU venue), with the overfit-ceiling instrument as
a methods contribution. Almost nobody publishes the graveyard; we have
receipts for ours.

---

## 5. Self-review — as PRODUCT

**What Aegis Finance is today:** a Bloomberg-lite breadth product with an
unusual spine — epistemic honesty (two-sided signal cards, drift-aware
predictions, conformal intervals, a public track record, a public
graveyard). Feature count rivals OpenBB; nothing else in the free tier
shows its own forward NAV and negative results.

**Honest product criticisms:**
- **Breadth > depth.** ~45 features, few with daily users. No user
  feedback loop; the only user is the builder.
- **Data fragility.** yfinance/free APIs are the weakest link (silent
  fragility incidents are the house failure mode — SEC 403s, FMP 402s,
  GDELT storms; all fixed, but the class persists). A product promise
  requires paid/redundant data or a narrower promise.
- **No identity for the visitor.** A stranger cannot tell in 10 seconds
  what this is FOR. The differentiator (honesty + forward receipts) is
  buried under feature count.
- No auth/accounts/persistence beyond localStorage (by design), no
  mobile-first pass, no onboarding, no analytics on real usage.

**The product's crown jewel is not a feature** — it is the unbroken,
hash-guarded, forward paper track record + the graveyard. A 24-month
unbroken honest NAV with pre-registered trials is something almost no
retail tool on earth can show. That is the thing to sell (as credibility,
not as revenue).

---

## 6. As PRODUCTION — what it needs

- **Reliability:** uptime/alerting on the collectors (silent-fragility
  audits are manual today); a dead-man switch on NAV freshness (partially
  exists via canary); dependency redundancy for prices (Polygon fallback).
- **Cost control:** API budget ledgers exist (FMP incident); needs a
  single dashboard of quota state.
- **Security/ops:** key rotation cadence (two past incidents handled),
  env-gated attended seeds (good), DEV_ACCESS_KEY on /dev (done).
- **Legal:** disclaimers exist; if it ever markets itself, a proper
  educational-use ToS pass.
- **Observability gaps on file:** SMQ lane missing from /api/health/full;
  NAV hash stamping design note; insider_cmp observability. Small, known,
  queued.

---

## 7. WHERE THE PIVOT IS

The research phase has *converged*. After 153 candidates the marginal new
signal has negative expected value (the overfit ceiling says our best
full-sample t's are indistinguishable from zero-skill mining; the next
ceiling re-registration is due at ~196). Continuing to widen the search is
now the least valuable thing this project can do.

**The pivot: from searching for edge to compounding proof.** Three legs:

1. **Research leg — write the paper.** The asset is the protocol + the
   graveyard + the receipts. Freeze the factory after Build 3 + the two
   calibration instruments (CZ-CALIB, HARNESS-VALID — they make the paper
   defensible), then write: methods (factory + wall + deflation), results
   (153 candidates, survivors, sign reversals, ceiling), and the honest
   conclusion (markets are ~efficient net of costs at retail scale; what
   survives is slow information). Target: SSRN + HKU undergraduate
   research programme. This is Murat's differentiation for internships —
   nobody else's CV has a pre-registered negative-results factory.
2. **Verification leg — let the clocks run.** The forward lanes and IC
   clocks are the only evidence that survives all criticism. Protect them
   (lane integrity, attended seeds only), add the TSMOM-XA defensive lane
   (framed Goal-B: protect capital, vs a 60/40 control), log conviction
   decisions, score the PDUFA ledger as calls mature. Do NOT touch the
   track record's write path for any feature.
3. **Product leg — narrow the story.** Reposition the site from "45
   features" to one sentence: *"The only free research platform that
   shows you its own forward track record — including everything that
   failed."* Lead with the track record page + brain showcase +
   graveyard; demote the feature zoo to a toolbox. That is a product a
   reviewer, a recruiter, or a retail learner immediately understands.

What the pivot is NOT: a fund, a signal-selling service, or a beat-SPY
claim. The honest posture — weak edges, strong process, forward proof —
is the only defensible one and happens to also be the rarest.

---

## 8. Concrete next steps (ordered)

**Research queue (finite, then freeze):**
1. Build 3 — target-price rebuild (ibes_adj + ptgdet, PSZ
   dispersion-conditioned; capitulation long-leg as phase 2).
2. INSTR-CZ-CALIB + INSTR-HARNESS-VALID (calibration pair → paper
   defensibility) → Chen-Velikov effective-spread cost model port
   (retro-check the small-cap survivors under realistic spreads).
3. Batch 10 (zombie/rate-cut long-side exclusion; insider role-weights) +
   INSTR-REGIME-JM2 (post-hoc-repair provenance declared). Optional
   pre-registered combiner from the shelf (issuance + quality ICs).
4. Overfit-ceiling re-registration at ~196 cumulative. Then **factory
   freeze** and paper writing.

**Forward/production (Murat-attended where flagged):**
- Seed TSMOM-XA defensive lane (attended, env-gated, lane-integrity both
  sides).
- Score PDUFA ledger (SCPH matured 2026-07-26; scoreable ~late Aug).
- Keep conviction-lane decisions flowing (the only forward test of
  Murat's own picking).
- Quarterly duties: CMP artifact + SMQ book refresh (~Oct), Monday GPR
  snapshots.
- Close the three observability gaps (SMQ health, NAV hash stamping,
  insider_cmp).

**Product (after research freeze):**
- Homepage re-narrative around track record + graveyard + brain showcase.
- One reliability pass: collector alerting + price-source redundancy.
- Then, and only then, consider users beyond n=1.

---

*Prepared by the session agent, 2026-07-26. Sources: TRIALS/registry.jsonl
(module), docs/STRATEGY_FACTORY.md, docs/SIGNAL_TAXONOMY.md,
NEGATIVE_RESULTS.md §1–16, AI_PANEL_2026-07-24/25/25B/25C/26.md,
RESEARCH_SWEEP_2026-07-26.md, STATE_OF_THE_REPO.md.*
