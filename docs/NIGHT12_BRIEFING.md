# NIGHT-12 — SESSION BRIEFING FOR OPUS

**8-hour autonomous campaign. 2026-08-11. Written by the brain session from
Murat's disclosure of his own investing record + two external reviews he
endorsed, filtered through canon.**

Work the whole window. A null triggers diagnosis and the next distinct task,
never a stop. Never say "blocked" until the endpoint was called and the
status printed.

---

## 0. What changed tonight

Murat disclosed his actual record and process: **+73.7%/1yr brokerage**
(his sheet header says "2025 +115%" — unreconciled), built on thematic
future-facing selection (semis, batteries, rare metals, quantum, 40-year
petrol thesis), analyst targets + big-bank endorsement as confirmation, and
high-positive-skew names (clinical biotech, SOC, QUBT). His self-diagnosed
failures, in his own words: **exit discipline** (SOC bought $5, hit ~$20,
never sold; ALMS sold at 10, later 21+; sold FSLR "so early"), **anchoring**
(holding NTLA "waiting for 26 again"), **regime exposure** (rode the
pre-Iran-war drawdown down; "could have sold and bought the dip").

His sheets are in the repo, and they are better than anecdotes: **dated
point-in-time snapshots** (2025-11-07 and 2026-01-13 columns, sold-at
annotations) of both his SELECTIONS and the WATCHLIST they were drawn from:
`docs/conviction_replay/murat_sheet_2025-11-07.pdf`,
`docs/conviction_replay/murat_sheet_and_report_2026-01-13.pdf`.

**Rulings now in force:**
1. **QUBT = 300 shares, AUTHORITATIVE.** The 200-vs-300 fork is resolved.
   Update the lane config (attended-safe: config value only, no trade).
2. **DeepSeek is sufficient. Do not wait for the Anthropic key.** Provider
   must be swappable; every model+version+prompt gets its own forward
   calibration record. The $30/night budget stands; near-$0 spend is a
   defect.
3. **The LLM-centric self-learning brain is the project direction.** His
   process is the CANDIDATE architecture — to be decomposed and mechanized
   where it measures well, not copied on faith.

**The frame (keep it exact):** Aegis did not become "too conservative" — it
became excellent at a narrower question (statistically defensible average
alpha) than the one his process exploited (positively skewed, future-facing
bets with catalyst selection). Do not lower the evidence bar. Widen what
the evidence machinery can evaluate.

---

## 1. PHASE 1 — CONVICTION-REPLAY-1 (the night's centerpiece)

Pre-register as **EXPLORE / OBSERVATIONAL** (rules designed after seeing his
history can never be confirmation). Corpse-lint first. Then reconstruct and
decompose his record:

- **NAV first.** Reconcile +73.7% vs "115%": time-weighted vs money-weighted
  return, deposits/withdrawals, window, realized/unrealized. Sources: the
  two PDFs, book_lanes, the conviction decision log, the January PDF already
  in repo. Cash figure still unknown — carry it as a labelled gap. **Train
  nothing on either headline number until the NAV series exists.**
- **Decompose** into: selection, sizing, entry timing, exit timing,
  market/regime exposure, cash drag. Per position: MFE/MAE, % of available
  move captured, what happened after each sale (TVTX sold 34.4 → 22.8 =
  good exit; ALMS sold 10 → 21+ = bad exit — measure, don't assume the
  story), profit concentration in top winners.
- **The identified test — selection vs candidate pool:** his portfolio picks
  vs his own watchlist non-picks, both PIT from the same sheets, against:
  target-upside-only ranking, consensus-only ranking, sector subsets, equal
  weight, SPY, and Aegis licensed signals. This answers whether his
  qualitative thematic judgment added information beyond the analyst
  spreadsheet — **the single most decision-relevant number of the night**,
  with its own MDE printed beside it (§19; n is small, the MDE will be
  large — print it and say what the design can and cannot see).
- **Up/down capture, measured separately**, for his book, every lane, and
  SPY — his claim "Aegis wins in bear, loses in bull" becomes a number.

## 2. PHASE 2 — Counterfactual Replay Engine v0 (leakage-immune)

Mechanical branching, no LLM required, so no temporal-leakage problem:
at every decision date in his record (and lane histories), branch
hold-100% / sell-100% / trim-25/50 / take-original-capital-out /
rotate-to-best-alternative / rotate-to-SPY / cash / hedge-half-beta, and
roll every branch forward on real prices. Output: the dataset for **"what
observable at the moment of a big run-up separates winners to hold from
winners to harvest"** — the exit-policy question a generic stop can't
answer (the trailing stop is a corpse, CANON §15; its trigger-information
finding is the prior). Same for drawdown states (the NTLA question:
expected utility of hold vs sell-to-best-alternative vs add, at each date,
on then-known information).

## 3. PHASE 3 — Freeze the spine: BeliefState + PredictionRecord

NIGHT-11 named this the prerequisite for everything two-way. Freeze the
schemas and START THE CLOCK — forward calibration only accrues from the
first written record:

- `OptimusBeliefState` per security: fundamentals, expectations,
  market-implied belief, Optimus belief, dislocation, + Murat-style fields:
  `theme`, `causal_chain`, `adoption_stage`, `catalyst_timeline`,
  `scenario_valuation` (probability tree for binary-catalyst names),
  `payoff_skew`, `thesis_breakers`, `replacement_edge`, `next_observable`.
- `PredictionRecord`: frozen input snapshot hash, model+version+prompt hash,
  horizon (5/20/60/120/252d), probability, magnitude, thesis,
  counter-thesis, next observable, resolution date. Auto-resolution scores
  Brier/calibration by specialist × category × horizon × regime.
- **DeepSeek specialists tonight** (biotech/pharma; semis/compute/quantum;
  energy/batteries/materials; software/consumer + one skeptic), each
  writing structured PredictionRecords for the current candidate set + the
  MIRROR names. They propose and forecast; they never size. Batch checked
  by `lint_batch()` (§20). Spend real budget; ledger every call.

## 4. PHASE 4 — Regime/Exposure Controller v0

Not crash prediction — **exposure control**: risk-on / neutral / risk-off /
crisis with beta/cash budgets, built from validated state variables (trend,
breadth, vol term structure, credit, revisions) + a low-frequency LLM macro
read (narration, not trigger). **Every reduction ships with its re-entry
protocol, specified at the same time** — a detector that sells and misses
the rebound destroys compounding. Judge on avoided drawdown AND missed
upside (both captures), on the lanes' history and on his replayed book
(would it have helped his pre-Iran-war drawdown AND kept his bull years?).

## 5. PHASE 5 — Short-leg decomposition of REVINFO-1 (carried, cheap, gating)

Round 16: 88–99.9% of a comparable spread lives in the short leg a
long-only book can't hold. Decompose the REVINFO-1 small-cap revision
spreads into long-leg-vs-market and short-leg contributions. **This can
kill the family for the product** — run it before anything builds on
revisions.

## 6. Time permitting

- **Analyst-reliability prereg** (his Oppenheimer/JPM/GS heuristic, made
  testable): per point-in-time recommendation, score analyst × firm ×
  sector × horizon on target error, revision direction, herding,
  calibration — IBES has the fields on disk. `revision × analyst-skill ×
  independence` is the candidate signal; raw upside stays a
  market-expectation sensor.
- **Positive-skew evaluation object**: probability-tree valuation for
  binary-catalyst names (the MIRROR category-mismatch fix). The bridge,
  stated once and enforced: research reports what it knows; the portfolio
  layer MAY take small, capped, evidence-labelled allocations on credible
  asymmetric payoffs — in shadow books only tonight.

## 7. Deferred, with reasons (do not build tonight)

- **Market Episode Store / Portfolio Gym / historical LLM simulation**: the
  LLM's training memory contains 2012–2026 outcomes; entity masking is
  necessary-not-sufficient (NIGHT-1) and masking the name ≠ masking the date
  (§13). Historical-LLM results can test ARCHITECTURE, never count as alpha
  evidence — and the store is a multi-week build. Design doc only if time.
- **Evolution Engine (500–5,000 genomes)**: the extreme-value bar scales
  with pool size; a bigger pool over the same information is a bigger null.
  The pool improves when the information set does — that's Phases 1–5.
- **Teacher library**: 13F-copy is a corpse and stays closed;
  imitation-learning (hindsight style inference) vs tradable-following
  (post-disclosure only) must never mix. Prereg the design, don't run it.
- **No protected-characteristic signals, ever.** The testable form of
  Murat's "social" instinct is adoption/attention/behavior: developer
  activity, hiring, specialist clustering, narrative diffusion vs price.

## 8. Do not

- Copy his portfolio style into production because it made 70% — that
  number is one draw from a high-variance process; the replay measures it.
- Lower the evidence bar anywhere; widen the objects it can evaluate.
- Let the LLM size anything, see post-freeze data, or grade its own tests.
- Quote a half-life, a skill claim, or a money claim the design can't see
  (print the MDE beside every number, §19).
- Touch paper_nav, seed a lane, or trade. QUBT config edit is the sole
  attended-adjacent change, and it is config-only.
- Read the holdout.

## 9. Outputs

`docs/NIGHT12_CONVICTION_REPLAY.md` (the decomposition + the selection-vs-
watchlist verdict with MDE), `docs/NIGHT12_COUNTERFACTUAL_EXITS.md`,
frozen schemas + first live PredictionRecords + LLM ledger,
`docs/NIGHT12_EXPOSURE_CONTROLLER.md` (with both captures for every book),
REVINFO-1 short-leg receipt, updated roadmap. End-of-night answers, in
order: (1) did his selection beat his own watchlist, and by a number the
design can see? (2) which of his three self-diagnosed failures does the
counterfactual data confirm, and what observable would have fixed each?
(3) what did the specialists predict today that is now on the record?
(4) does the revision family survive its short leg? (5) what would the
exposure controller have done to his book and to the lanes?

## 10. Closeout

Fast suites both repos → `silent-fragility-audit` → manifests → commit →
push → verify clean → `python tools/refresh_aegis.py` → handoff + memory.
Still owed by Murat (carry, don't block): **cash**, kill-condition rulings
(ABSI/AMSC/HUBS/KYTX/SLDP), `confirmed: true`, graceful-degradation ruling.
