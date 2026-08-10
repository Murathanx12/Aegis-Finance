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
- **`data_grade: crsp`** (offline research module) — the **CRSP security
  universe with real delisting returns** (28,913 of them), and **Compustat
  fundamentals subject to point-in-time reporting-lag and CCM linkage controls**.
  Historical *inference* is permitted, bounded by everything else:
  pre-registration, power check, placebo, trial-count deflation, era-appropriate
  costs, G7 for turnover-sensitive claims, and the holdout.

  The two halves of that grade are not equally strong and must not be quoted as
  one word. Delisting returns close a **survivorship** hole. They say nothing
  about whether a linked accounting field was *available on the formation date* —
  that is a separate control, and it is the reporting-lag one. A run that has the
  first and not the second is survivorship-free and still leaks.

  **The delisting correction measured on this spine was −0.01%/yr *for this
  strategy over this window*** (NIGHT-4). That is one measurement of one book,
  not a general finding that survivorship bias is economically negligible — the
  same audit on free data found 1-of-20 recovery, and the gap between those two
  numbers is the whole reason the grades are separate.

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

### 16. A cost comparison needs a denominator, and it must not be the winner's
Two arms that start at the same NAV do not end at the same NAV. The one that
compounds less trades fewer dollars for the same turnover *rate*, so **totalling
cost in dollars silently rewards whichever arm made less money.**

This rule exists because the same claim was made three times in three nights and
was wrong twice, in opposite directions, purely from the denominator:

| night | instrument | verdict on the clock ensemble |
|---|---|---|
| NIGHT-7 | monthly-panel turnover rate | "free" — violated §15 |
| NIGHT-7B | total cost **dollars** | "cheaper by $19,390" |
| NIGHT-8 | cost / (average NAV × years) | **indistinguishable**; at $1m the ensemble is 3.54 bps/traded and 0.011 pt/yr *worse* |

So: **a cost comparison between arms is quoted as cost drag per year against
average NAV, and as bps of traded notional.** Dollar totals may appear beside
those, never instead of them. Two corollaries the same run produced:

- **Capital rungs are re-simulated, never scaled.** Participation caps are
  nonlinear in size: at $50m the single clock executed only 47.7× the turnover
  of the $1m run against 50× the capital, because it could not fill. *(Amended
  the same night: the original wording said "participation caps **and impact**",
  and the simulator that produced the number has no impact term at all. See §17
  — that omission is a second, larger reason a rung cannot be scaled.)*
- **Counters summed across sleeves are not comparable to a single book's.**
  `days_with_capped_orders` summed over twelve sleeves counts one bad day twelve
  times. Report the fraction of desired notional that failed to execute instead.

### 17. An execution number carries the model that produced it
Two simulators now exist and they answer different questions. A capacity or cost
figure that does not name which one produced it is not quotable.

| grade | what it prices | what it cannot see |
|---|---|---|
| **G7** | explicit costs, Corwin-Schultz half-spread, participation caps, execution delay, carried unfilled orders | **price impact.** NIGHT-8 measured 31.00 bps per dollar traded at ADV multiples of 1e6, 100, 5 and 1 — identical across a million-fold liquidity range |
| **G8** | everything G7 prices, plus a metaorder square-root impact term charged on the whole order against ADV | execution urgency/horizon, permanent-vs-temporary decomposition, cross-impact, and the coefficient itself |

Three consequences, all binding:

- **Every capacity number produced before G8 is a delay-only lower bound** and
  must be labelled as one. That includes NIGHT-5's "$100m → $500m" and NIGHT-7's
  $50m rung.
- **A G8 number is quoted with its coefficient and its scenario band**, never as
  a point estimate, until real execution data replaces the assumption. The
  published square-root prefactor ranges roughly 0.25–1.0 and we have no TCA of
  our own.
- **G7 is not modified to become G8.** `impact_coef = 0.0` skips the arithmetic
  entirely and reproduces G7 exactly, so historical outputs stay comparable and
  the receipt records which model ran.

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
