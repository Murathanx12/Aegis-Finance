# CANON — the non-negotiable guardrails

> Written 2026-07-08, distilled from V2_GOALS.md, TRACK_RECORD_POLICY.md,
> NEGATIVE_RESULTS.md, the experiment registry, and two years' worth of closed
> rabbit holes compressed into one month of sessions. **Read this before
> building anything.** Every rule below was earned by a measured failure or an
> adversarially-verified research finding — none is a style preference. A future
> session that wants to break one of these rules must do it in an attended
> session, with the evidence that overturns the rule written down first.

---

## The prime rule

> **"The engine learns forward — process memory plus forward evidence — never
> by training a stock-picker on historical prices."**

The system improves two ways only: (1) *process memory* — postmortems, rejected
approaches, and decision rationales ingested into the Optimus brain so the next
session starts smarter; (2) *forward evidence* — pre-registered trials whose
clocks accrue on live data (paper-lane NAV, forward IC, forward Brier). It never
improves by fitting, training, or reinforcement on historical returns, because
every historical path we can access is contaminated (survivorship, hindsight,
LLM knowledge-cutoff leakage) in ways no statistical guard can remove.

## The rules

### 1. No skill claims before 24 months
The live forward NAV (`paper_nav`, inception 2026-06-08) is the **only** thing
that may be called a track record (`TRACK_RECORD_POLICY.md`). It is shown with
its age and no performance adjectives until 24 months of tracked decisions
exist (`skill_min_months: 24`). Interim numbers are reported, never acted on.
Every pre-registered trial has its own earliest-decision date (TRIAL-001:
2027-06-10); no peeking decisions before it.

### 2. Backtests on our data are direction-checks only — never alpha claims (T7)
Measured 2026-06-16 (`docs/research/SURVIVORSHIP_AUDIT_2026-06-16.md`,
NEGATIVE_RESULTS §4): yfinance recovers **1 of 20** delisted S&P names — a
survivorship-free universe is not buildable on free data. Therefore **no
backtested absolute-alpha number on our data is trustworthy**, and the DSR/PBO
gate cannot save it (it guards multiple testing, not a biased universe — that
is exactly how vol-managed momentum printed a false PASS). Backtests may check
*direction and mechanics* (does the overlay reduce drawdown, does the rule
behave); selection signals validate **forward only** — PIT-store IC + paper-lane
NAV. Every backtest-derived number carries its `data_grade` stamp and the
methodology banner.

### 3. The LLM-lane firewall — no backtest "experience" for the brain
An LLM knows history; a backtested LLM strategy is hindsight wearing a lab
coat. Measured basis (canon A2): the "profit mirage" — lookahead inflates
apparent LLM predictive power by ~37% of the standalone effect, and genuinely
out-of-sample the edge is insignificant (arXiv 2510.07920, 2512.23847); KTD-Fin
(arXiv 2605.28359): 9/10 models show **negative** selection alpha under blinded
eval. Therefore: the conviction/LLM lanes are **forward-only**; the brain never
"learns" from replayed history; no LLM theme-pick is ever backtested to justify
itself (TRIAL-THEME reject, postmortem 2026-06-15).

### 4. No RL / online learning on P&L
The accounts never train on their own returns. Optimizing on own-P&L learns
noise and dies live (anti-goal since V2; empirically reinforced by TRIAL-THEME:
"every backtest gets better" drove PBO from 0.37 to 0.66). "The paper accounts
train themselves" means: more pre-registered forward hypotheses running in
parallel — never weight updates from outcomes.

### 5. The `paper_nav` write-path is sacred
Nothing touches the NAV write-path or a live lane's strategy outside an
attended session. Concretely: no in-place edits to lane YAMLs (config hashes are
segment identity), no retrofitting an overlay onto an in-flight trial
(TRIAL-001 annotation 2026-06-14), no strategy changes to a tracked lane —
changes ship as **new pre-registered lanes** with their own config hash and
inception. Lane seeding is env-gated and attended (Murat flips the flag).

### 6. Pre-register or it didn't happen
Every hypothesis enters as a registry trial with hypothesis, primary metric,
decision rule, and earliest decision date committed **before** data accrues
(the git timestamp is the tamper-evidence). No metric substitution, no window
cherry-picking, no post-hoc "adjusting for regime." Rejected trials are
recorded and published (NEGATIVE_RESULTS.md) — a project whose registry shows
only adoptions is lying to itself.

### 7. Crash timing is closed; fragility is the surviving form
Short-horizon crash *timing* has ≈0 IC; false-positive de-risking exits
compounding bull runs and costs more than the crashes (canon A5, verified
2026-06-14; our own signal engine: +251% vs buy-and-hold +740%,
NEGATIVE_RESULTS §1). LPPLS predictive skill: refuted twice. The answerable
question is "how fragile is the system, and is fragility rising" — a
descriptive composite that may one day *scale exposure*, never a "crash
imminent" call. The fragility composite stays equal-weighted (fitting weights
to past crashes is the hindsight trap), descriptive-only, and never arms a
lane until a forward Brier earns more. The crash overlay stays DARK until a
*discriminating* model exists (current artifact is provenanced but outputs
~0.066 in every regime) — and arming happens only on a new pre-registered lane.

### 8. Silent fragility is the house failure mode — verify live, fail loud
The recurring bug class is not wrong math; it is code that runs green and does
nothing (insider collector: 12 passing tests, 100% prod fetch failure —
NEGATIVE_RESULTS §5; the crash overlay dark for weeks; the warm-cache test that
was never offline). Rules: every collector/model failure is loud
(`data_quality`, provenance sidecars, fail-loud loaders); deploy claims are
verified against `aegis_verified_state` / `/api/health/full`, never against a
prior session's narration; a green test suite is not a live verification.

### 9. Data discipline: PIT or descriptive
New data enters through the PIT store (`pit_observations`: `as_of` +
`observed_at`, never overwritten) — API-first, scrape-last, failures loud.
Anything not PIT-safe (politician trades on a 30–45-day disclosure lag, 13F,
analyst targets) ships as **labeled descriptive context**, never a timing
signal. FRED latest-vintage caveat applies before any macro series becomes
sizing-grade.

### 10. Consolidation beats expansion
Anti-goals stand: no real-money execution (the human keeps the keys), no
Bloomberg-parity push, no feature-count arms race, no database beyond the
existing SQLite/PIT stores, AGPL code (OpenBB) never enters this MIT repo.
External projects contribute **patterns, re-implemented** — never vendored
code (see REFERENCES.md).

---

## Closed rabbit holes — do not re-run

| Closed | Verdict | Where |
|---|---|---|
| Market-timing strategy vs buy-and-hold | Loses (+251% vs +740%) | NEGATIVE_RESULTS §1 |
| 12-month crash prediction | ≈ base rate, no skill | NEGATIVE_RESULTS §2 |
| LPPLS as a predictor | Refuted twice → descriptive flag | NEGATIVE_RESULTS §3 |
| Thematic-momentum selection (TRIAL-THEME) | REJECT: −0.08 Sharpe vs controls, PBO 0.66 | postmortem 2026-06-15 |
| Backtesting LLM/brain theme-picks | Profit mirage — forward conviction lane is the only honest test | canon A2 |
| Survivorship-free universe on free data (T7) | Not buildable (1/20) | NEGATIVE_RESULTS §4 |
| Day-trading lane | Costs swamp edge; multi-horizon lanes instead | BACKLOG V4 |
| Fitting fragility-composite weights to past crashes | Hindsight overfitting; equal-weight stays | BACKLOG V1 |
| Finnhub-free + edgartools for Form 4 | Missing fields / 50-min hangs | BACKLOG T9 |
| N_eff loosening the adoption gate | Raw trial count stays the strictness floor | postmortem 2026-06-14-t2 |
