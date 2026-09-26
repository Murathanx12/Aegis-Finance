# REVIEW 2026-09-26, chunks H + I: the Railway cost review and the daily learning report, reviewed as money

**Reviewer:** Opus (read-only, investor seat). **Loop:** `research_notes/2026-09-26/SESSION_ORDER_2026-09-26_SURVIVE_AND_PROFIT.md`
("after G+H, after I"). **Standard:** `REVIEW_2026-09-25_CHUNK0_THE_DAYS_BUILD.md` + its adjudication.
**Read:** `docs/REVIEW_2026-09-26_RAILWAY_COST.md`, `scripts/daily_learning_report.py`,
`learning_reports/report_2026-09-26.md`, `research_notes/2026-09-26/audit_forecasts_and_learning_since_august.md` + its
adjudication, `ACCOUNTS_2026-09-22_THE_PAPER_FLEET.md`, `reputation/reputation_2026-09-26.json`,
`strategy_library/leaderboard_2026-09-26.json`, `llm_portfolio/books.jsonl`, `paper_accounts/roi_2026-09-26.json`,
`backend/services/signal_reachability.py`, and in `../aegis-alpha-terminal`: `scripts/market_window.sh`,
`scripts/counterfactual.py`, `alpha/counterfactual.record_marks`, `alpha/ledger.scan_chain`, `scripts/agent_loop.py` L243.
**Ran (read-only):** `railway metrics -s aat-loop-<role> --since 1d/7d/14d --raw --json` for the five roles;
`signal_reachability.audit()`; throw-away pandas over `predictions.jsonl` and `prices_2025_26/bars.parquet`. Nothing in
either repo or on Railway was modified. $0.00 LLM.

**Short version.** Neither chunk moved expected terminal wealth. H is a careful piece of work: its diagnosis is
right, and it would save about $40/month if executed. But it proposes one fix that trades away tamper evidence for
nothing, it misses that the volumes are growing at 1.75 GB per trading day, and it keeps a role that has had no
positions since 09-04. I is a good reader of receipts, but its three closing sentences are wrong in ways that
steer the next session:

1. **Sentence 1 is wrong.** It credits an LLM with skill that a $0 formula has. A trailing-63-day-volatility normal
   CDF beats the investigator's magnitude forecasts on **7 of 8 days at h=1 and 6 of 8 at h=5**.
2. **Sentence 3 is wrong.** Its winner and runner-up are both **already running**.
3. **The orphan line is wrong.** 591 of the 614 "orphans" are test files.

---

## 1. Verdict per chunk

| chunk | moved terminal wealth? | moved gradeability? | why (receipt) |
|---|---|---|---|
| **H: Railway cost** | **no, not yet.** Worth about **+$41/month** of real cash if executed (bill `max($20, usage)`: ≈$61.5 → $20) | no | The diagnosis holds and I re-checked it (§2.4). Fix 1 (persist the cadence stamps) is a real correctness bug, and it also **more than doubled ledger growth**: hack1's disk grew 0.10–0.13 GB/day under the persistent loop (09-12 → 09-19) and **0.29–0.44 GB per trading day** after the 09-20 cadence deploy. hack5 went from 0.17–0.21 to 0.49–0.63 (`railway metrics --since 14d`, `DISK_USAGE_GB`). Fix 2's checkpoint is unnecessary (§2.4). |
| **I: daily learning report** | **no** | **mixed.** The sections and receipt paths are real progress. The closing sentences are **negative value if acted on** | Sentence 1 praises a volatility prior the LLM was handed (§2.1). Sentence 3 ranks two experiments that are both already running, on priors the builder set by hand (§2.2). The orphan count is 96% test files (§2.3). "More compute" reads the wrong signal (§2.2, last bullet). |

**RESULT IMPROVEMENT: NONE** for both. One new measured result came out of this review (§5, sentence 1).

---

## 2. You are wrong: five places

### 2.1 Chunk I, sentence 1: "`investigator:D_all` +6.02% WORKS". What works is a $0 formula, and the LLM subtracts from it.
**What the report says.** `investigator:D_all`, held-out Brier skill +6.02% (n=468), is "what currently works".
**Why that is wrong, in three layers:**
- **The number mixes the observables. The receipt it cites already splits them, and the report ignores the split.**
  `reputation_2026-09-26.json → arms_by_observable` gives D_all:
  - `abs_move_exceeds` h1: **+4.1%** (n 156)
  - `abs_move_exceeds` h5: **+9.0%** (n 156)
  - `return_sign` h5: **−8.1%** (n 156)

  The "+6.02% works" line is a volatility forecaster wearing a stock-picker's number. This is the **third** time
  the same fact has surfaced (reviewer row 2 on 09-25; audit row 2 on 09-26), and the template re-blends it.
- **The skill sits in the LLM's own prior, not in its evidence step.** Every investigator row stores `prior`
  (for example TJX: "Prior from 21% annualized volatility", 0.091) and `probability` (the posterior). On the
  held-out half (later half by `made_at`), the posterior's Brier against the prior's:
  - `abs_move` h1: **−0.3%**, posterior better than prior on 2 of 4 days
  - `abs_move` h5: **−5.3%**, 1 of 4 days
  - `return_sign` h5: **−3.3%**, 1 of 4 days

  Per arm, `A_snapshot` returns posterior = prior exactly, and `B_anon`, `B_tools` and `C` are −2% to −8% at h5.
  Reading the dossier makes the forecast worse.
- **A free formula beats the LLM on the same questions.** Take `p = 2·(1 − Φ(thr / (σ₆₃·√h)))`, where σ₆₃ is the
  63-session std of daily log returns before `made_at`, from `prices_2025_26/bars.parquet`. That covers 3,100 of
  3,120 graded investigator magnitude rows. Held-out half, climatology = the training-half base rate. The
  comparison is row-for-row, so the choice of climatology does not change the ranking.

  | h | rows | LLM posterior | LLM's own prior | **formula σ₆₃ (raw)** | formula σ₆₃, shrink fitted on the train half | days formula beats LLM (all 8) |
  |---|---:|---:|---:|---:|---:|---:|
  | 1 | 775 | +5.7% | +6.3% | **+10.2%** | +10.2% (w = 1.0) | **7 of 8** |
  | 5 | 775 | +2.1% | +7.2% | +5.3% | **+7.9%** (w = 0.5) | **6 of 8** |
  | 1, D_all only | 155 | +7.2% | +5.9% | **+11.0%** | | |

**What I would do.** Sentence 1 reads `arms_by_observable`, and is admitted only when an arm **beats the free
baseline** (σ-formula plus an earnings-date flag), not climatology. Climatology is a bar a spreadsheet clears.
Also retire the "WHAT DOES NOT: `biotech_pharma` −70%" line. That persona has had weight 0 since 09-24 and wrote
its last row on 08-12. The template picks `min(skill)` over arms whether or not the arm is alive, so it reports a
corpse every day.
**What would settle it.** The 09-25/26 investigator magnitude rows resolve 09-29 → 10-05, which is 6 new date
blocks. If the σ₆₃ formula has Brier ≤ the LLM posterior on ≥ 4 of 6 blocks, LLM magnitude forecasting is
retired and the formula replaces it at $0. The LLM is then graded only on the **residual** (idea A, §4).
Caveat, stated: the held-out window is 4 date blocks and 133 tickers. The all-8-days count is the more robust
line.

### 2.2 Chunk I, sentence 3: the "highest-EV experiment" and its runner-up are both already running, and the priors are constants
- **`INVESTIGATOR_DIRECTION_CALIBRATION` (EV $3,993) is not an experiment. It is a clock that is already
  ticking.** `u_forecast` writes the direction rows every day whatever the report says: 194 `evidence_v3`
  `beats_benchmark` h1 + 194 h5 rows made 09-25/26 (`predictions.jsonl`). Choosing it changes no action. Its
  "cost" of $6.63 (21 × today's spend) is spend that happens anyway.
- **"Direction skill UNMEASURED" is false.** It is measured: `return_sign` h5 held out **−8.7% (n 780)**, with a
  training-half shrink weight of **0** (audit §1.3), and D_all is −8.1% in today's receipt. The flag is read from
  a string in `forecasts/day_<date>.json` and not from the reputation receipt, so P is never halved.
- **P = 0.40 is not defensible, because of power.** The new direction rows have **sd(p) = 0.019–0.028**
  around 0.50. Even if they were perfectly calibrated, the most Brier skill they can earn is
  `var(p)/(b(1−b)) ≈ 0.028²/0.25 ≈ 0.3%`. With 2,000 fully *independent* rows that is t ≈ 1.2, and 21 sessions
  of an h=5 question are about 4 non-overlapping date blocks. Power is below 0.1, and the prior (−8.7%, w = 0)
  says the effect is probably absent. **P ≈ 0.03–0.05.** On the value side, a direction signal this flat is worth
  ≤ 1%/yr on the capital it sizes. EV ≈ 0.05 × $1M × 1% ≈ **$500 at the most generous notional.**
- **`LIB_SEALED_TOP1_FORWARD` (runner-up, EV $3,000) was done this morning.** `llm_portfolio/books.jsonl` already
  holds `lib_mom_12_1_q_2026-09-26` plus its `__ew`, `__sector_etf`, `__spy` and `__random_same_band` twins. The
  eligibility check reads the leaderboard and never reads `books.jsonl`. The top-1 also has **DSR 0.293 with
  `dsr_z` −0.54**: below the best-of-336 null, so it is indistinguishable from the luckiest rule. A mom_12_1 k=12
  night book has also run forward since 09-11. Its marginal EV is 0.
- **The values ($20,000 / $10,000 / $8,000) are not tied to any capital.** Murat's real book is "small money"
  (`user_murathan.md`), PC-PAPER is a $1M paper notional, and the WLS challenge is a prize. A value has to be
  `C × Δ(certainty-equivalent return) × T` with C declared, or the ranking is the builder's taste printed as
  arithmetic.

**What I would do.** An experiment is eligible only if (a) it is **not already running** (check `books.jsonl`,
`forecasts/`, `paper_books`), (b) P comes from a written power line (the effect size the prior allows, n in date
blocks), and (c) V = C × Δ × T with C named. My ranking is in §5.
**What would settle it.** Nothing needs to wait. The two facts above are in today's files.

**The compute verdict reads the wrong signal (same file, `s_compute`).** MORE fires when the purpose's graded
rows fall in a *family* whose blended arm-level skill is positive. When the 09-25 `u_forecast` rows grade
(from 09-28), family `investigator` will read positive on **magnitude** credit, and the report will say MORE
for a purpose that writes **direction** (`beats_benchmark`) rows. Meanwhile it says LESS for a purpose that spent
**$0.0000**, and "already due and none graded" → LESS blames a purpose for the *grader's* lateness. The audit
found grading ran only twice in five weeks. The right signal is the purpose's own rows, per `(observable, h)`,
held-out skill **over the free baseline, per dollar**. $0 purposes are exempt, and grader lag is a HOLD plus a
grader alarm.

### 2.3 Chunk I, "614 of 1,041 modules nothing can call": an artefact. The real number is 24, and every one is classified.
`signal_reachability._all_modules` rglobs **every** `.py` under `backend/`, which includes `backend/tests/`.
No entry point imports a test, so every test file lands in `orphans`. Re-running `audit()` today gives:
- `n_modules` 1,042, `n_reachable` 319, `n_tooling_only` 108, `n_orphaned` 615, **`unclassified` 0**.
- By prefix: **`backend.tests` 591**, `backend.services` 19, `backend.vendor` 5.
- The 24 non-test orphans all carry a recorded reason: 5 are VERBATIM cross-repo vendored source, and the rest
  are OK/AWAITS/GAP research modules.

The report prints the first eight orphans alphabetically. `backend.services.*` sorts before `backend.tests.*`, so
the display shows the only real ones and hides that the other 591 are tests. This is the same failure the
module's own docstring warns about ("an audit that cries wolf … gets ignored on the 21st").
**What I would do.** Print `unclassified` (0 today: *green*) and non-test orphans (24, all classified). In
`signal_reachability`, exclude `backend.tests` from `_all_modules` or count it on its own line. That is one line,
in a file chunk I does not own.
**What would settle it.** `audit()["orphans"]` filtered on `".tests" not in module` → 24.

### 2.4 Chunk H, fix 2: the checkpoint trades tamper evidence for nothing, and the review missed the real growth problem
- **Page-cache residency does not scale with the number of reads.** Reading the same 1.1 GB file 55 times or 9
  times caches the same pages. Fix 1 therefore cuts CPU and ledger *growth*, but not resident cache. What
  releases the cache is `posix_fadvise(DONTNEED)` after the walk, and that half of fix 2 needs no checkpoint.
  A full `scan_chain` costs 8.7 s of CPU (the review's own measurement). At about 10 hourly walks a day that is
  roughly 25 CPU-hours a year, which rounds to $0.
- **What the checkpoint breaks.**
  - Detection latency for a prefix rewrite goes from about 10 minutes to up to 24 hours. The 25-Aug breaks in
    this programme were exactly that shape: rows "physically spliced mid-JSON" by a second writer
    (`ledger.scan_chain` docstring).
  - The checkpoint lives **on the same volume** as the ledger, so anything that can rewrite the ledger can
    rewrite the checkpoint. It is a cache, not evidence.
  - `verify_chain` honours `ledger_epochs.json`. A checkpoint that does not bind the epoch list's hash can pass
    a prefix the epoch file later re-describes.
- **The review costed the volumes as static. They are not.** Across the fleet, disk grew **+8.7 GB in the five
  trading days 09-21 → 09-25**:
  - hack1: 2.71 → 4.58
  - hack5: 3.76 → 6.56
  - hack6: 2.92 → 4.72 (7d window)
  - hack2: 2.05 → 3.39
  - hack4: 1.91 → 2.55

  That rate began on the first weekday after the 09-20 cadence deploy. The cause is in the code:
  `counterfactual --record` **appends a mark for every world on every run** (`alpha/counterfactual.record_marks`),
  and the cadence bug runs it every 10 minutes instead of hourly. Consumers dedupe to the last mark
  (`refusal_regret.py` L14), so the extra rows are pure bloat. At about 37 GB/month the volumes and the chain
  walk keep growing even after both fixes. At the pre-cadence rate (0.1–0.2 GB/day per role) the fleet would
  still add about 4 GB/week.
**What I would do.** Fix 1, plus `fadvise(DONTNEED)` after every full walk and every `read_all`. **No
checkpoint.** For growth, **seal the chain into monthly segments**: each segment's head hash becomes the next
segment's genesis and is appended to `ledger_epochs.json`. Per-cycle verification walks only the open segment.
A weekly full walk re-derives every sealed head. Reads are bounded and tamper evidence is intact.
**What would settle it.** A difference-in-differences with free metrics: deploy fix 1 + fadvise on one role and
leave the rest as controls. Over one week the treated role's `DISK_USAGE_GB` slope should fall **≥ 2×**, and its
between-cycle `MEMORY_USAGE_GB` should sit **< 0.3 GB**, while the controls keep today's shape.

### 2.5 Chunk H: "keep five services" optimises the bill and not the fleet. The canary is wrong, and step 0 is gating nothing.
- **At the Pro floor, keeping and retiring cost the same dollars.** The bill is `max($20, usage)`. Website $8.16
  + seal $0.76 + all volumes ≈ $3.8 comes to about $12.7 of usage, so the fleet's marginal dollar cost after the
  fixes is roughly **$0–3/month**. The real cost of the fleet is its **information yield**:
  - −9.8% and **−$39,384 realised** over 358 trips, with a 27.7% hit rate and −418 bps per position
    (`fleet_audit/trade_autopsy_2026-09-24.json`)
  - hack6 on **negative cash (margin)** since 09-22
  - **no terminal-repo commit since 09-20**
  - the hackathon it was built for was judged on **09-04** (`../aegis-alpha-terminal/docs/HANDOFF.md`)

  A book whose output nobody iterates on is a slot machine that writes −418 bps/position rows we already have.
- **hack2 should be retired, not used as the canary.**
  - It has held **0 positions since 09-04** (ACCOUNTS).
  - It pulls the fleet's **largest network ingress (7.9 GB/7d)**, against 2.3–4.4 GB for the roles that trade.
  - Its disk grows 1.34 GB/week, for an account doing nothing.
  - The review's own post-deploy check, "exits still run on every exits-only cycle", **cannot fail on an account
    with no positions**, so hack2 validates the memory line and nothing else.

  Use **hack4** as the canary: 4 positions, the smallest volume (2.55 GB), and the smallest blast radius among
  the accounts that hold positions.
- **A cheaper falsifier than `railway ssh` was already in the data, and it agrees with the review.**
  - Across the five roles, the rank of in-window memory equals the rank of volume size (**Spearman 1.0**:
    hack5 > hack6 > hack1 > hack2 > hack4).
  - Max 7-day memory ≤ end-of-week disk for every role (3.36 ≤ 4.61, 2.09 ≤ 3.39, 1.89 ≤ 2.55, 5.25 ≤ 6.60,
    4.86 ≈ 4.72).
  - On Saturday, hack1 sits **flat at 3.355 GB with CPU 1.1–1.4e−5 vCPU**. That is the same signature as hack5's
    idle `sh` at **0.02 GB**, so no extra process is running on hack1.
  - hack6 steps down 3.408 → 2.837 → 1.967 → 0.371 → 0.242 at constant CPU: host reclaim, not a process freeing
    memory.

  The orphaned-child alternative predicts CPU above the `sh` baseline, or a hung process. The first is falsified;
  the second remains, which is why `ssh` is still worth one look. **But fix 1 is a correctness bug whatever the
  cache/anon split, so step 0 should not gate it.**
**What I would do.**
- (1) `railway down` hack2 attended, keeping the volume and the account.
- (2) Fix 1 + fadvise on hack4 first, then the others.
- (3) A 14-day mandate clock: a role with no terminal-repo commit touching its mandate by 10-10 goes
  exits-only → flat → container retired. Its **Alpaca account is kept** and re-pointed at a PC-driven arm (idea B).
**What would settle it.** Whether anyone commits to the terminal repo's mandates in 14 days. If nobody does, the
fleet's information value was zero and retiring it cost nothing.

---

## 3. The one thing to delete

**Delete the hand-declared `EXPERIMENTS` table (`scripts/daily_learning_report.py` L70–95) and the
sentence-3 ranking built on it, until P and V are derived.** The table's heading says "THE SINGLE HIGHEST-EV
NEXT EXPERIMENT", and on its first day it ranked two things that were already running. P and V are the
builder's constants, and "UNMEASURED" is read from a string that is wrong. Of everything in the two chunks, this
line is the one a tired reader is most likely to act on, and today it points at zero-marginal-value work.
Replace it with "**no derived ranking yet**" plus the power line of §2.2. Sentence 3 comes back when each
candidate carries C, Δ from a receipt, P from a power calculation, and a `not_already_running` check. (Runner-up
for deletion: LLM magnitude forecasting in `u_forecast`, once §2.1's 6-block test agrees.)

---

## 4. Three new ideas (not on the roadmap)

**A. Formula first, and the LLM graded only on the residual.** Write the σ₆₃ formula probability (plus an
earnings-in-window flag from the calendar we already hold) as its own `formula:vol63` arm on every magnitude
question. Then ask the LLM one thing: *does this name's |move| exceed the formula's number, and why?* Grade
the LLM on Brier improvement **over the formula**, not over climatology.
*Beta-separating observation:* the formula absorbs the volatility factor and the earnings-season vol premium, so
anything left is the dossier's contribution. If the residual skill is ≤ 0 on 6 new date blocks, the evidence
step is costing money and should stop.
*Cost:* $0 for the formula; the LLM calls already run (about $0.32/day). Half a builder-day.

**B. Re-point the idle Alpaca accounts at PC-driven sizing twins with real fills.** hack2's account is
PA33ON4NRJAX, $98,820 cash. Retire its container and let the PC loop drive it under its own lease prefix, as
ACCOUNTS already proposes for idle accounts. Same PROBE names as PC-PAPER, three weightings:
- equal weight (the control)
- inverse formula-σ
- tournament tilt toward high predicted |move| (for the grand-prize personality)

Real fills measure slippage for the shapes the competition will actually run.
*Beta-separating observation:* all three arms hold identical names, so they differ only in weights. Regress the
daily return differences on SPY, IWM, MTUM and **USMV**. The inverse-σ arm must beat EW *after* its low-vol
factor loading, and "risk resolves about 30× faster than return" (§59) means realised vol separates within
about 21 sessions.
*Cost:* $0 on Railway (it saves about $4.7/month), one attended lease setup, half a builder-day.

**C. Grade the report's own priors.** Each day's sentence 3 writes one forecast row: *"experiment X changes a
named decision by date D"*, with p = the P it used, observable `decision_changed`, and the settling file named.
After 30 days, the P column has a Brier score and a calibration curve, so the EV priors earn their weight like
every other forecaster.
*Beta-separating observation:* compare against the constant base rate of "decisions changed per experiment".
If the builder's Ps do not beat a constant, the EV ranking is ornamental and should print only the power line.
*Cost:* $0, about 40 lines.

---

## 5. My own three sentences for 2026-09-26

1. **WHAT CURRENTLY WORKS:** a $0 volatility formula forecasting magnitude, `p = 2(1−Φ(thr/σ₆₃√h))`.
   - Held-out Brier skill **+10.2% at h=1 (n 775)** and **+7.9% at h=5 (n 775, shrink fitted on the train
     half)**.
   - It beats the LLM investigator's posterior on **7 of 8 days (h1) and 6 of 8 (h5)**, on the investigator's
     own graded questions (`predictions.jsonl` × `prices_2025_26/bars.parquet`; method in §2.1).
   - Nothing forward works yet: 0 of 38 frozen books are graded (`llm_portfolio/leaderboard_2026-09-26.json`).
     The "+8.64 pp" best forward line rests on **2 NAV marks** and ties its own always-invested twin
     (`paper_accounts/roi_2026-09-26.json`).
2. **WHAT DOES NOT:**
   - **LLM direction.** `investigator:D_all` `return_sign` h5 is **−8.1% (n 156)**, and all arms are **−8.7%
     (n 780, training-half weight 0)** (`reputation_2026-09-26.json → arms_by_observable`; audit §1.3).
   - **The LLM's evidence step on magnitude.** Posterior vs its own prior on the held-out half: **−0.3% (h1),
     −5.3% (h5)**.
   - **The PROBE gate so far.** PROBE−REFUSED is **−0.68%/day, t −0.83, on 3 blocks**
     (`decisions/autopsy_2026-09-25.json`).
   - **The Railway fleet.** −9.8%, **−$39,384 realised, 27.7% hit** (`fleet_audit/trade_autopsy_2026-09-24.json`),
     while it costs ≈ **$52/month** of real money (`REVIEW_2026-09-26_RAILWAY_COST.md` §3).
3. **HIGHEST-EV EXPERIMENT: `VOL_SIZED_TWINS`** (idea B, frozen first as virtual twins in `llm_portfolio`, and as
   real fills on hack2's account once it is PC-driven).
   - EV = P **0.5** × C **$1,000,000** × Δ **3.4%/yr** × T **1 yr** − cost ≈ $0 → **≈ $17,000**. At Murat's own
     smaller C the ratio is unchanged: about **30×** the direction calibration.
   - **P = 0.5:** the magnitude skill is measured on 8 date blocks, and realised vol resolves in about 21
     sessions.
   - **Δ = 3.4%/yr:** the certainty-equivalent gain at γ = 3 if inverse-σ cuts book vol from 25% to 20% at the
     same mean, `½·γ·(σ²_EW − σ²_IV)`. It is an assumption, and the USMV regression tests it.
   - **Runner-up: formula-vs-LLM residual (idea A).** P 0.6 that it retires LLM magnitude; value is the freed
     LLM budget plus the correct attribution of the only positive number, ≈ $1–2k equivalent; cost $0.
   - **Not eligible:** `INVESTIGATOR_DIRECTION_CALIBRATION` (already running; EV ≤ $500 on power grounds) and
     `LIB_SEALED_TOP1_FORWARD` (frozen this morning with 4 twins; DSR 0.293).

---

**What this review did not check, and should be checked:**
- the actual Railway invoice (both reviews use metrics);
- whether a Railway volume mounts on a cron service;
- `AAT_LOOP_EXPIRY` per role, i.e. when each mandate ends on its own. I did not print `railway variables`,
  because it prints secrets;
- the formula comparison on the 09-25/26 rows once they resolve.

The fleet's egress (TX 0.15–0.25 GB/week per role, about $0.05/month) is negligible, so the review was right not
to chase it.
