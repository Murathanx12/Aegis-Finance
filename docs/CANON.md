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

**Scoped by data grade (amended 2026-08-10 after external review).** The rule
above is about **free-data** universes and stands unchanged for anything running
on yfinance/EODHD in production. It is **not** a blanket ban on historical
inference, and reading it as one made NIGHT-7's CRSP work look unlicensed under
our own canon. Two grades, stated separately:

- **`data_grade: free`** (production, yfinance/EODHD) — direction-checks only.
  1-of-20 delisted-name recovery means absolute alpha is not measurable there,
  and no selection-signal claim may rest on it.
- **`data_grade: crsp`** (offline research module, CRSP/Compustat via WRDS,
  28,913 real delisting returns, survivorship-free) — historical *inference* is
  permitted, and remains bounded by everything else: pre-registration, power
  check, placebo, trial-count deflation, era-appropriate costs, G7 for
  turnover-sensitive claims, and the holdout. NIGHT-4 measured the delisting
  correction on this spine at **−0.01%/yr**, which is what survivorship-free
  buys.

A CRSP-grade backtest is still **not a skill claim** — the forward-record rule
governs that — but it is admissible evidence, and the grade must appear on every
scorecard.

### 3. The LLM-lane firewall — no backtest "experience" for the brain
An LLM knows history; a backtested LLM strategy is hindsight wearing a lab
coat. Measured basis (canon A2): lookahead inflates apparent LLM predictive
power by ~37% of the standalone effect (Llama-3.3) and genuinely
out-of-sample the edge is insignificant (p=0.033, Llama-2) — arXiv
2512.23847 (Gao-Jiang-Yan); the "profit mirage" phenomenon label is arXiv
2510.07920 (Li et al.). *(Attribution split corrected 2026-07-30 during
paper verification — this line previously cited both IDs jointly for the
37%, blurring which paper measured it.)* KTD-Fin
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

### 11. Every examination leaves a ledger entry
External projects/tools/data sources examined in a session get an entry in
`docs/KNOWLEDGE/projects.jsonl` **in the same commit** as the work that
examined them — verdict (absorbed / partially-absorbed / rejected / unmined),
what was taken (with file pointers), what was rejected and WHY. Same
discipline as findings.jsonl. The rejects are the most valuable entries:
they are what makes the search terminate instead of re-running
(`docs/PROJECT_LANDSCAPE.md` is the human-readable view; the lab loop
injects the ledger into every cycle). Projects whose pitch is
price/crash/return prediction are rejected-by-category without testing —
that class is refuted (F-001/F-002/F-006/F-009, LPPLS ×2).

### 12. Protected characteristics are never features
Inferred ethnicity, race, religion, national origin, gender or any other
protected characteristic — of a CEO, a board, a workforce or a company — is
**excluded as a feature, permanently and without exception**. This is not a
tuning choice and does not get revisited when a backtest looks interesting.

The mechanisms people reach for it to proxy are real, and every one of them
is directly observable and already legal to use: board connections (BoardEx),
prior employment and appointments, lobbying spend, campaign contributions,
government contracts, disclosed ownership, geographic revenue, supplier and
customer relationships. Those are the features. An inferred demographic is a
worse proxy for each of them than the thing itself, so the rule costs nothing
even before the ethics.

### 13. Masking the name is not masking the date
Entity anonymisation hides *which company* a text is about; it does **not**
hide *when*. Outcome memory keyed on the date survives it (Lookahead
Propensity, arXiv:2512.23847; FinCAD, arXiv:2605.24564 — suppressing it cuts
in-sample backtest returns by up to −67.1% on memorised dates). NIGHT-1's
0/240 identification result measured entity masking only.

Therefore: **masked historical replay is a reasoning laboratory, not an
alpha-certification laboratory.** Any masked-replay result claiming an edge
must additionally either date-shift/synthesise the timeline, or report an
in-sample-vs-post-cutoff contrast. Enforced in code:
`aegis_brain.firewall.ExtractionRequest.alpha_certifiable` is False unless
date or era leakage was controlled.

### 14. P&L never writes beliefs; the LLM never learns from outcomes
An LLM that reads a result and writes a prose "lesson" into memory has not
learned — no weights moved. It has fitted an unregularised prior to the test
set and expressed it in fluent English, which makes it unfalsifiable and more
persuasive the more overfitted it is. The licensed architecture is the one-way
firewall (`aegis_brain/firewall/`): LLM extracts numbers from anonymised text
and never sees outcomes → a small regularised model learns under purged CV →
the LLM adjudicates read-only, scored on Brier, never on P&L.

Memory updates by class: **procedural** (leakage patterns, bad controls, bugs)
updates freely from history; **mechanism** updates with retrospective tags and
shrinkage; **calibration** updates only from scored extractions; **return
beliefs** update only from forward evidence. No self-improving memory loop runs
until Layer 1 has a measured calibration curve.

### 15. Turnover-sensitive claims route through the daily simulator
The monthly panel understates the cost of frequent trading by ≈2.4 percentage
points per year at a ~0.8 one-way-turnover increment — measured twice
independently (NIGHT-6 clock compare; NIGHT-7 trailing stop, where the panel
ranked the arm *first* and daily execution put it 3.08%/yr *behind*, having
paid 74% of starting capital in extra costs over 23 years).

**Scoped precisely (amended 2026-08-10 after external review):** the trigger is
**path-dependence, not trading frequency**. Any strategy that can change
positions *between* scheduled portfolio snapshots — stops, intra-period exits,
delayed entries, replacement-on-event — must be scored from the actual
**trade/event ledger**, never inferred from periodic holdings snapshots. Monthly
simulation remains valid for a strategy whose only permitted transactions occur
on those month-end dates and whose position changes reconcile exactly.

Hard invariants for the daily simulator, from the two bugs this rule has already
caught: every position delta creates a trade; replaying the trade ledger
reconstructs holdings exactly; a zero-cost run reconciles against the gross
research path; an exit without a rebalance still generates turnover; and a
measured turnover that contradicts the panel's turnover is a **construction
artifact until proven otherwise** (NIGHT-7B: an ensemble measured at 1.51× the
panel's turnover was a monthly re-targeting artifact, not a real cost).

So: any candidate whose one-way annual turnover differs from its baseline by
more than 0.10 may **not** have its net number quoted until G7 has measured it.
A turnover-increasing arm's monthly-panel net is an **upper bound**; a
turnover-decreasing arm's is a **lower bound**. Corollary: every high-turnover
corpse in the graveyard was judged on a panel that flattered it, so those are
*more* dead, not candidates for resurrection.

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
| LLM picking stocks directly | REJECT: t 0.04 / 0.93, 204 months, 16,320 graded decisions | NIGHT-3 verdict |
| Trailing stops on the small-cap book | −3.08%/yr under measured daily execution; +$743,599 of cost per $1m over 23yr | NIGHT-7 T2b |
| "Big funds hold it so it can't fail" | Index ownership is mechanical cap-weight tracking — zero information, no backstop | NIGHT-7 brief §2.4 |
| ">1% of the S&P means it has peaked" | Cap weight is an output of value, not a ceiling on returns | NIGHT-7 brief §2.4 |
| Rebalancing premium as a source of edge | Maeso-Martellini's >100bps is vs **buy-and-hold**, not vs a rebalanced benchmark — withdrawn | NIGHT-7 T1 item 18 |
