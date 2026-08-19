# ROADMAP POSITION — 2026-08-19 (day session, unattended)

> **LATE-DAY DELTA (appended ~15:35 HKT):** the evidence column moved for
> the first time. (1) **CONVEXITY-PRESERVATION-1 resolved** — the
> program's first Holm-surviving registered positive: mechanical
> trims/full exits at +40 destroy 60-day terminal wealth (−1.3/−2.6/−5.2%
> per dollar); the deciding daily-close trailing exit is NOT_ESTABLISHED
> at n (CRSP replication protocol frozen pre-read). §61-capped: adaptive
> historical evidence, not edge. (2) **G1 status refined**: false-kill
> rate measured 0.000, null FP 0.4%, but the z-based MDE label is
> miscalibrated for the full Holm judge (~50% not 80% win rate at nominal
> MDE) — `DECISION_MDE_80` solved by simulation through the complete
> judge: **0.0702 vs STATISTICAL_MDE_80 0.0529 at the tournament's n
> (ratio 1.33×)** — receipt
> `verdict_battery_decision_mde_2026-08-19.json`. G1 flips when both
> error rates are declared AND the power label quotes the decision
> number, not the z number. (3) **WRDS entitlement map**
> (500 usable schemas) + training substrate pulls: the "information over
> architecture" path the NET tournament prescribed is now materially
> unblocked (finratio, JKP chars, IBES, fundq, options surface, iid,
> 13F). (4) Research executor: first end-to-end hypothesis result
> (executed=1/blocked=12-with-reasons).

Written to answer Murat's direct question: *where are we on the roadmap, how
close are we to reaching our goals?* Everything below is grounded in code,
artifacts, or the live deploy as verified this morning — file paths given so
the next session can re-check rather than trust.

## 0. The one-paragraph answer

The **factory is close to complete; the evidence is close to zero — and that
is the designed state, not a failure.** Every gate that can be passed by
building has been built or is one small build away; every gate that can only
be passed by *calendar time under pre-registration* is waiting on its clock.
Demonstrated investment edge remains **0%** (the number the roadmap itself
insists on): zero resolved forward predictions (first 396 resolve **Friday
08-21**), zero licensed reads (IIF-1's first look is at **40 graded nights**),
lanes at **72 days against a 24-month floor**. The distance to goal is now
measured in **signatures and nights, not builds** — which is exactly what the
day-work/night-simulation restructure (`docs/OPERATING_MODEL_DAY_NIGHT.md`)
is for.

## 1. The three deliverables

| Deliverable | Position |
|---|---|
| **Murat's own capital** | No demonstrated edge yet; the honest product shape identified is **RISK-first** (§59: risk resolves ~30× faster than return on identical data; 206 published predictors net out at median −0.12%/yr). 10 paper lanes accruing since 2026-06-08, all fresh through 08-18. No skill claims before 2028-06. |
| **Public open-source tool** | Deployed and healthy (`0.2.0` @ `9be7e4d`, scheduler 7/7, all lanes fresh). The V1 surface (30+ analytics) is live; what it may honestly claim is bounded by the same evidence clocks. |
| **HKU paper** | The defensible novelty so far is **methodological**: the referee machinery itself (instrument floors, §58 k_eff with tests-as-units, §62 execution-boundary verdicts, §63 screen/confirm split, the false-kill catalogue). A "we found alpha" paper has no evidence; a "how a self-learning system avoids learning nonsense, with receipts" paper is largely written in the docs already. |

## 2. Gates (the roadmap's own scoreboard), verified today

| Gate | State 2026-08-19 | Evidence checked today |
|---|---|---|
| G1 referee | **OPERATIONAL, not PASSED** | Downgrade stands (a compiled false kill was found *after* declaration). Flips only when the known-answer battery recovers planted truth at declared false-positive AND false-kill rates. The tournament rehearsal harness (`scripts/net_tournament_run.py --rehearsal`) is the first real piece of that battery — it plants a linear world and the arms recover it correctly (re-ran today: ridge IC +0.059, nonlinear arms less, 9 folds green). |
| G2 unit of analysis | **PASSED for high-frequency event families** | regime→event pivot; 145 monthly date blocks is the §58 unit printed on every new dataset. |
| G3 objective layer | **SUBSTANTIALLY BUILT** | All four personalities exist in `research_gym/utility.py` (`PERSONALITIES` tuple, line ~481); `counterfactual.py` takes an objective and *names* the default on every record instead of silently sorting raw return. Residual: G3 is authoritative in the gym, not yet wired through every consumer. |
| G4 expectation layer | **V1 BUILT** | `backend/services/g4_expectation.py` — `ExpectationRecord` with strict validation + refusal type. Residual: population (feeding it real expectations at scale) is a build item, not a design item. |
| G5 world model | **THREE RECEIPTS, ALL NEGATIVE** | A learned conditional *shape* adds nothing even given an oracle scale; realized vol commoditised (four free forecasters indistinguishable at 0.005 IC). Headroom is in **scale, not shape** — which is why the NET tournament's primary question is framed as "does any complex model beat the simplest admissible baseline by more than its own MDE." |
| G6 sizing learner | **PARTIAL** | Blocked by design on G3-everywhere + the §59 ruling: validate sizing on RISK outcomes (rv20 vol-targeting as baseline product), never on 95-year return statistics. |
| G7 forward certification | **MACHINERY READY, ZERO RESOLVED EVIDENCE** | First 396 h=1 resolutions land Fri 08-21 (mechanics only — the read gate licenses nothing before 40 graded nights, O'Brien-Fleming 4.312/3.295/2.845). 2 IIF nights complete (`ok`, 585 + 600 records, ~$0.92/night). Launcher arming blocked on the schtask `< NUL` fix (attended); the 3/3 acceptance clock restarts from the first clean receipt. |

## 3. The clocks (what "how close" actually means)

Nothing below can be accelerated by building harder — only by keeping the
nights running and the signatures flowing:

- **Fri 2026-08-21** — first forward resolutions ever (396 at h=1). Mechanics only.
- **~40 graded nights** (≈ early October if nights run nightly from arming) — IIF-1's first licensed read. MDE at 40 = 0.0104/0.0153 at measured ρ. This is the earliest date on which the program can say *anything* evidence-backed about its forward forecasts.
- **Signature-gated, ~2 min of compute** — the NET tournament heads (`docs/TRIALS/PREREG_AEGIS_NET_TOURNAMENT_1.md`, refuses unsigned — re-verified today). Honest expectation set by its own power block: the primary contrast is NOT_ANSWERABLE_AT_N at the economic bar unless measured dispersion comes in low; the *ablation ladder* (which feature families carry information) resolves regardless.
- **2026-08-27** — second resolution batch, attended.
- **2028-06-08** — the 24-month lane floor. No skill claims before it, full stop.

## 4. What the last 48h added (validated, not just claimed)

Re-verified today, independently of the session log:
- Tournament rehearsal green; signed path refuses unsigned (both re-run).
- Cross-arm replay reproduces: conviction NAV vs YAML-seed buy-and-hold
  diverges up to **11.23%** in discrete jumps (07-30/07-14/06-24) — the
  14-point mirror gap is **UNRECONCILED** and only the attended positions
  read resolves it.
- Datasets exist at claimed sizes: NET panel 24,911 × 145 blocks;
  convexity episodes 23,011 (13,956/6,198/1,845/1,012 by threshold);
  pair labels 72,495 with 5 cost-sensitive.
- TAQ: 184/185 bands retired, 1 stays (dead PXD); effective spreads
  measured, verdict correctly DEFERRED to conventions.
- Daemon receipt real: 13 declared jobs, priors before data, m-ledger clean.

## 5. What is actually in the way (ranked)

1. **The attended queue** — positions read (resolves the only live
   contradiction), tournament signature, Brier-bar signature, schtask fix,
   Night 3/4 launches. All Murat-only. Nothing unattended can substitute.
2. **Calendar** — the clocks in §3.
3. **G1's known-answer battery** — the one *build* that upgrades the
   referee from OPERATIONAL to PASSED. Specced in the Opus handoff.
4. **G4 population + G3-everywhere** — small builds, specced in the handoff.

Not in the way: compute, ideas, data access (WRDS/TAQ entitled and proven),
test coverage (5,010 fast tests green).
