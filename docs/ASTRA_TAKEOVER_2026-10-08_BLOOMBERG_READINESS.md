# Astra takeover brief — Bloomberg readiness

**Date:** 2026-10-08 HKT/SGT  
**Repository:** `Murathanx12/Aegis-Finance`  
**Branch for this handoff:** `astra/2026-10-08-bloomberg-readiness`  
**Verified GitHub main at takeover:** `6bc11c4060d26abb324c6e7a91c8cd40fa096bdf`  
**Primary objective:** arrive at the Bloomberg Global Trading Challenge start with a rehearsed, current, fail-closed contest desk and the best explicitly declared contest policy we can justify from the available evidence.  
**Secondary objective:** preserve AEGIS V1 Beta progress without distracting the contest path.

> This file is a pickup brief and execution order, not permission to silently rewrite production/capital code. Use branches, tests, receipts and adversarial review for any behavioral change.

---

## 1. Owner intent

The owner has granted broad autonomy to continue AEGIS from Claude/Fable's work and wants the system optimized for the Bloomberg competition. The owner explicitly prefers action, fast learning, paper/live-shadow evidence, causal reasoning and profitability over accumulating research that never reaches decisions.

The standing V1 Beta principle remains:

**observe -> decide -> act/paper -> grade -> attribute -> learn**

For the contest, however, optimize the separate utility:

**contest relative return / right-tail rank under the official rules**, not long-horizon institutional portfolio utility.

Do not confuse these two utilities.

---

## 2. What was already completed — do not rebuild

### Main / V1 Beta

PR #11 and PR #12 are merged.

Main is now `6bc11c4` ("Merge PR #12: results voice, PC off cash (SPY core + revision_flow sleeve 30%), contest REGISTERED, reviews").

Already merged:

- V1 Beta night-one measurement/health/decision-story work.
- fair/sticky twin corrections and review work;
- results voice;
- PC-PAPER benchmark core + `revision_flow` sleeve;
- revision-flow sleeve reduced to **30%** after the deeper historical 21-session loss bound;
- SPY core clipped to post-fill gross and SELLs sent before BUYs;
- sleeve/core decisions written as labelled DECIDED rows;
- contest registration marker;
- query/research/health work;
- public visual language and evidence pages;
- forecast-ledger split implementation and review fixes.

Do not re-implement any of the above unless a current receipt or failing test proves it is broken.

### Forecast ledger

The ledger split is **built, reviewed, merged and rehearsed on a copy**, but the real local ledger migration was deliberately **not applied**. It requires an attended PC operation after old writer processes are restarted.

This is not a reason to design a new storage layer. It is a deferred operator step.

Unless the legacy ledger blocks contest operation, prioritize contest readiness first and migrate only in an attended maintenance window.

### Public assets

PR #13 is open: `Public assets refresh: --bump-pin, weekly task_keeper job, staleness health row`.

Head: `fb60f2d5fe6be2c9c8c6930aaae921645f25c7db`. CI is green.

It is useful product hygiene but is **not on the Bloomberg critical path**. Do not let it displace Terminal/rules/rehearsal work.

---

## 3. Production truth verified on 2026-10-08

### Railway AEGIS production

Project: `selfless-courage`  
Service: `Aegis-Finance`

Verified:

- source repo: `Murathanx12/Aegis-Finance`
- branch: `main`
- latest deployed commit: `6bc11c4060d26abb324c6e7a91c8cd40fa096bdf`
- latest deployment status: **SUCCESS**
- production domain exists
- healthcheck: `/api/health`
- persistent volume: `/data`, 5 GB
- no staged service changes

Do not redeploy merely to "make sure". Only redeploy if a specific tested fix is merged or production evidence requires it.

### Legacy Alpaca Railway estate

The separate `loving-elegance` project still contains `aat-loop-hack1` through `hack6`. Their latest deployments are old FAILED deployments from Aug/Sep 2026. `hack3` is already considered retired/replaced by PC-PAPER.

Treat these as legacy estate, not proof of a healthy current execution fleet. Do not spend Bloomberg-prep time reviving them unless a current contest dependency is discovered.

---

## 4. Bloomberg registration and dates

Repository registration marker:

`backend/data/optimus/contest/REGISTERED`

records the owner's 2026-10-07 statement: **"bloomberg is registered"**.

The connected Gmail search performed during takeover found no Bloomberg competition confirmation email. This does **not** disprove registration; it only means this session cannot independently corroborate the repository marker from Gmail. Do not delete or weaken the marker.

Current published HKU/Bloomberg-facing dates:

- registration closed: **Oct 4, 2026 23:59 New York**
- challenge starts: **Oct 12, 2026 09:00 New York**
- starting positions due: **Oct 16, 2026 23:59 New York**
- challenge ends: **Nov 13, 2026 17:00 New York**
- winners announced: **Nov 20, 2026**

Public reference:
- https://ug.hkubs.hku.hk/competition/bloomberg-global-trading-challenge-2026

Public challenge descriptions also repeat the core security constraints:

- $1M virtual USD / notional
- stocks in the Bloomberg WLS Index
- single-name equities, no ETFs
- long only
- no leverage
- no single position above 20% of the notional amount

Useful public reference:
- https://www.fa.mgt.tum.de/fm/teaching/project-studies/list-of-open-project-studies/bloomberg-global-trading-challenge-2026/

The public wording "20% of the notional amount" supports a fixed $200k ceiling on the original $1M notional. The existing code's `min(20% NAV, $200k)` is conservative. Do not loosen it without the current Terminal T&C.

---

## 5. Current contest architecture

Primary runbook:

`docs/CONTEST_RUNBOOK_2026-10.md`

The contest code remains **decision support + immutable order-sheet generation + verification**. It does not send Bloomberg orders. The owner manually enters tickets into TMSG.

That boundary should remain for this challenge unless the current Bloomberg rules explicitly authorize an API path and the owner separately chooses to automate entry.

### Live gate

CONTEST mode deliberately refuses an order sheet unless BOTH exist:

1. `backend/data/optimus/contest/REGISTERED`
2. a valid WLS MEMB export in `backend/data/optimus/contest/wls/`

The WLS export checker requires:

- CSV/XLS/XLSX;
- filename or header identifies WLS;
- loader finds membership tickers;
- at least 1,000 rows.

**Never bypass this gate with a guessed/public constituent list.**

The WLS export is the most concrete external blocker currently visible from GitHub.

---

## 6. Critical readiness discrepancy: rehearsal receipts are stale in tracked GitHub

The runbook says rehearsal should produce a daily sheet through Oct 9.

But the tracked main receipts currently show:

- `contest/rehearsal/runs.jsonl`: last daily run **2026-10-06**
- `contest/rehearsal/SCOREBOARD.md`: last grade **2026-10-06**
- `contest/rehearsal/freeze_log.jsonl`: last daily frozen sheet **2026-10-06** (strategy-contract records were added later)

Last tracked scoreboard:

- book NAV: approximately **$1,023,073**
- relative vs ACWI: about **+2.20 pp gross** over the then-graded window
- 10 positions total, 6 closed, 4 open

This is descriptive rehearsal evidence, not a validated edge.

### Interpretation

GitHub receipts being stale does not prove the local scheduler stopped, because newer local/uncommitted receipts may exist on the owner's PC.

Therefore the **first local-PC task is not coding**:

1. inspect Task Scheduler ownership for `AegisContestRehearsal` / `AegisContestDesk`;
2. inspect the local `contest/rehearsal/` receipts for Oct 7 and Oct 8;
3. run the contest status command;
4. verify calendar/prices are fresh;
5. if local also stops at Oct 6, classify the rehearsal **RED / STALE**, find the root cause and restore it immediately;
6. only then produce today's rehearsal/grade.

Do not backfill a missed live observation and call it forward evidence. Mark missed windows honestly.

---

## 7. Current contest strategy decision

### Current runbook recommendation: ROT5_TRAIL

Each day:

- rank eligible upcoming reporters by magnitude of past earnings reactions;
- hold the top 5 WLS names, 20% each;
- buy at the open before the print;
- sell at the open after the reaction window.

The existing strategy lab treats it as a **right-tail variance strategy**, not demonstrated directional alpha.

Runbook estimates at 10 bps/side:

- ROT5_TRAIL October-null P(relative return > +40%): roughly **3.6–4.2%**
- MAXTAIL_BH: roughly **3.3–3.8%**
- MAXTAIL_EVT: roughly **2.2–2.6%**

At 25 bps/side, turnover hurts ROT5_TRAIL enough that MAXTAIL_BH becomes more attractive in the runbook.

### Fallback: MAXTAIL_BH v2

- 5 highest raw-`sigma63` liquid operating names;
- refuse x2 one-day jump / obvious split-stitch data defects;
- buy once;
- hold through the contest.

Lower operational turnover and more robust to transaction-cost assumptions.

### ROT5_DIR result

Do not assume the analyst direction filter solved direction.

Current replay receipt:

`backend/data/optimus/contest/strategy_lab/direction_replay_DRR_2026-10-07_1.json`

Top-5 historical replay:

- 6,860 events
- analyst filter drops 34.5%
- dropped minus kept mean return: about **-0.48 pp/event**
- day-clustered t: **-1.69**
- after 63-session momentum control: about **-0.44 pp**, t **-1.51**
- P(> +20%): dropped **3.5%**, kept **3.5%**
- P(< -20%): dropped **4.4%**, kept **2.8%**

Interpretation: the analyst-negative filter appears to reduce left-tail exposure, but the current top-5 replay does not establish a reliable directional edge and does not clearly increase the right tail. Keep it shadow unless new evidence changes the declared choice.

---

## 8. Terminal-only blockers to resolve before Oct 11/12

These require Bloomberg Terminal / current TMSG Help / current challenge T&C. Do not guess them from old documents.

Highest priority:

1. exact fill-price convention;
2. actual challenge commissions/fees;
3. whether the 20% cap is checked only at entry or continuously;
4. whether sale proceeds can fund same-session buys;
5. whether full investment is required only by the Oct 16 deadline or continuously;
6. non-US execution/FX treatment;
7. dividends/corporate-action treatment;
8. exact Relative P&L calculation;
9. minimum trades / re-entry / daily order limits;
10. available order types;
11. board-lot handling by market;
12. export the actual WLS membership via `MEMB <GO>`.

Then encode answers as a dated receipt/source note. If any answer changes the book-selection decision, rerun only the affected contest lab with the new rule. Do not reopen unrelated V1 Beta research.

---

## 9. Agent-routing protocol for this takeover

The controller should allocate effort by risk and difficulty, not spawn agents for trivial work.

### LOW effort / deterministic operator

Use one lightweight worker for:

- status/receipt inventory;
- WLS export parser validation after the owner provides the file;
- stale-file checks;
- CI/status checks;
- document updates;
- exact command/result capture.

No debate agent needed.

### MEDIUM effort / integration builder + reviewer

Use one builder plus one independent reviewer for:

- fixing the rehearsal scheduler/task ownership if it is stale;
- contest health/progress contracts;
- Terminal export ingestion;
- rule-receipt plumbing;
- order-sheet verification bugs;
- calendar/holiday/FX/board-lot fixes.

Requirements:

- reproduce bug first;
- patch on branch;
- targeted tests;
- reviewer attacks failure modes;
- rerun affected drills;
- do not merge behavior changes solely because unit tests pass.

### HIGH effort / strategy or capital-sensitive research

Use at least:

1. **researcher** — builds the best case and runs declared experiment;
2. **skeptic** — tries to falsify / identify leakage, survivorship, cost or operational mismatch;
3. **integrator** — decides whether evidence changes the contest policy;
4. **test/replay worker** — independently reproduces decisive result when feasible.

Use this for:

- changing ROT5_TRAIL vs MAXTAIL_BH;
- adding a news/LLM/direction overlay to the live contest book;
- changing sizing;
- changing holding period;
- using non-US markets;
- any strategy selected after seeing recent results.

A new idea can run in SHADOW quickly. It should not replace the frozen live policy without a clear declared reason and receipt.

### LLM use during contest prep

LLM agents may:

- research current public news;
- generate causal theses;
- identify catalysts/falsifiers;
- summarize Terminal exports;
- propose alternative names/policies;
- compare evidence.

They should **not** silently own final order sizing/execution mechanics. Deterministic code remains the capital/rule authority.

---

## 10. Ordered execution queue

### P0 — today: recover live contest readiness

1. Verify local PC receipts after Oct 6.
2. Verify scheduled contest tasks are alive and progressing.
3. Run current rehearsal status/grade; produce a dated receipt.
4. Export WLS membership from Bloomberg and make `contest_rehearsal gate --mode contest` pass.
5. Record exact Terminal/TMSG challenge-rule answers.
6. Rerun 13 contest drills.
7. Produce one dry contest-mode Oct 12 preview after the WLS/rule inputs are present.
8. Verify PC timezone/clock, Task Scheduler wake behavior and AC-power behavior.
9. Test the manual blotter -> `verify` workflow end to end.

**Exit:** live gate OPEN, drills green, current receipts, no silently stale input, one frozen/dry preview reproducible.

### P1 — before first live sheet: choose the book under actual rules

Once actual cost/fill/settlement mechanics are known:

- recompute ROT5_TRAIL vs MAXTAIL_BH under those exact assumptions;
- keep ROT5_DIR and any news/LLM overlay in shadow unless their incremental right-tail utility is clear;
- write `contest/live/BOOK` explicitly rather than relying on an implicit default;
- produce a short decision receipt explaining why.

**Exit:** one named live book, one fallback and explicit switch conditions.

### P2 — Oct 11/12 operations

- first live sheet freeze at the prescribed schedule;
- owner checks `EVTS <GO>`, `MEMB <GO>`, `CACS <GO>`;
- owner enters SELLs then BUYs manually;
- run `verify` against entered blotter before the relevant open;
- record actual fills and compare against assumed convention;
- update NAV from Terminal;
- immediately revise the book only if the observed execution mechanism invalidates the declared assumption.

### P3 — parallel but non-blocking

- leave PR #13 until P0/P1 are green;
- ledger migration only in an attended maintenance window;
- V1 Beta world graph/NN/RL/product work resumes after contest safety/readiness gates are closed for the day.

---

## 11. What not to do this week

- Do not rewrite the contest engine because a new model is available.
- Do not bypass the WLS gate.
- Do not revive dead legacy Alpaca loops for optics.
- Do not change the live book after reading a favorable historical result without recording the selection.
- Do not feed every news item directly into order sizing.
- Do not use magnitude as direction.
- Do not migrate the real forecast ledger during a contest-critical window unless needed.
- Do not merge PR #13 before a competition-critical failure just because its CI is green.
- Do not report an old Oct 6 rehearsal receipt as current.
- Do not call a process healthy because it exists; its outputs must advance.

---

## 12. Commands the PC operator should run first

From repo root on the owner PC, on current main:

```powershell
git fetch origin
git status --short --branch
git rev-parse HEAD
python -m scripts.contest_rehearsal status --mode rehearsal
python -m scripts.contest_rehearsal gate --mode contest
python -m scripts.contest_drills
```

Then inspect the newest local files under:

```text
backend/data/optimus/contest/rehearsal/
backend/data/optimus/contest/live/
backend/data/optimus/contest/wls/
backend/data/optimus/contest/logs/
```

If the rehearsal is stale locally, diagnose before manually fabricating a new receipt.

After WLS is exported:

```powershell
python -m scripts.contest_rehearsal gate --mode contest
python -m scripts.contest_rehearsal dry --mode contest --date 2026-10-12
```

Use the repository's current CLI help if argument shape differs; do not alter commands merely to force a green result.

---

## 13. Takeover definition of done

The Bloomberg prep phase is ready when:

- registration marker exists;
- WLS export passes the live gate;
- challenge rules that affect execution are sourced from current Terminal/T&C and recorded;
- rehearsal has current Oct 8/9 receipts or an honest incident record for any missed day;
- 13/13 drills pass on current main;
- Oct 12 dry contest sheet is reproducible;
- one live book and one fallback are explicitly named;
- actual execution assumptions are compatible with the chosen book;
- all input freshness checks are green;
- the owner can type a blotter and `verify` it without ambiguity;
- AEGIS production remains healthy;
- no capital-sensitive change bypassed review.

Only then return to lower-priority V1 Beta enhancements.

---

## 14. Sources to read before changing behavior

Internal:

- `docs/CONTEST_RUNBOOK_2026-10.md`
- `docs/HANDOFF_2026-10-07_V1_BETA_NIGHT_ONE.md`
- `docs/ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md`
- `docs/reviews/REVIEW_2026-10-07_PC_CORE_AND_REVISION_FLOW_SLEEVE.md`
- `docs/reviews/REVIEW_2026-10-07_PR11_CLOUD_LEDGER_SPLIT.md`
- `docs/research_notes/2026-10-07/contest_direction_replay_2026-10-07.md`
- `backend/data/optimus/contest/strategy_lab/direction_replay_DRR_2026-10-07_1.json`

Owner source pack:

- `AEGIS Version 1 Beta — Fable Handoff, Owner Review, Research Pack, Design Options and Guiding Roadmap`
- owner's pre-beta review / brainstorming notes

External:

- HKU 2026 page: https://ug.hkubs.hku.hk/competition/bloomberg-global-trading-challenge-2026
- official portal: https://portal.bloombergforeducation.com/trading_challenges
- Bloomberg API library: https://professional.bloomberg.com/support/api-library/
- public challenge-rule description: https://www.fa.mgt.tum.de/fm/teaching/project-studies/list-of-open-project-studies/bloomberg-global-trading-challenge-2026/

---

## Final controller instruction

Do not optimize this week for the largest number of modules or commits.

Optimize for the shortest path to:

**fresh inputs -> valid WLS universe -> named contest policy -> immutable sheet -> correctly entered ticket -> verified fill -> relative P&L -> grade -> next decision.**

If a task does not materially improve that chain before Oct 12, park it unless it repairs a critical AEGIS integrity failure.
