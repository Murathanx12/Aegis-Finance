# REVIEW 2026-10-07: C15 (publish receipts and follow-ups) and C20 (v3 contracts and benchmark core)

Adversarial reviewer: Opus 5.5. Read-only. One Python probe of `pc_broker.plan_orders` (pure, no broker). Five targeted test files run. Nothing edited or committed except this file.

**RESULT IMPROVEMENT: NONE.** Both chunks are plumbing and preparation. No book traded and no number moved.

## VERDICTS

- **C15: SHIP THE CODE, BUT THE PAGES ARE NOT PUBLIC.** The sanitiser path is sound, and the leak scan of the six published payloads came back clean. But the "daily commit" that the manifest says makes the pages public has no caller anywhere. The copies sit on a WIP branch, and `origin/main` does not contain `backend/data/public_receipts/`. This is the C10 lesson again: a commit that is only documented is a commit nobody makes.
- **C20: THE CONTRACTS ARE PREPARED CORRECTLY. DO NOT TURN THE BENCHMARK CORE ON AS BUILT.** Seeding is refused all three ways, and the tests prove it. With the flag ON and the EXPLOIT sleeve planned but not acting (today's state), the core cuts the acting PROBE orders by about 42%. The worst-case table and the tests both miss this. Separately, the quant-ensemble contract puts a significance gate on a PRODUCT_EXPERIMENT. That breaks the three-licence rule, and the gate has never gone green.

Scores: **C15 70/100 · C20 60/100.**

## Tests (question 6)

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_publish_receipts_c15.py \
  backend/tests/test_board_supersessions_c15.py backend/tests/test_fleet_v3_contracts.py \
  backend/tests/test_benchmark_core.py backend/tests/test_rules_capfix_proposal.py -q
........................................                                 [100%]
40 passed, 1 warning in 15.46s      (exit 0)
```

Mocks used:
- **publish (10 tests):** `_config.OPTIMUS_LEDGER_DIR` points at a tmp world (x3), and `S.scrub_str` is monkeypatched to identity to prove that a bypassed scrub is refused. The opportunities runner is a fake `_R(rc)`, and the publish job is a lambda.
- **benchmark core (10 tests):** `config.PC_BENCHMARK_CORE` is patched (x3), `FakeBroker().install` stands in for the broker, and `_plan_benchmark_core` is patched once. The fixture builds the ranking with `net=-0.2`, so **no EXPLOIT targets exist in the plan**. That is why H2 is invisible to the suite.
- **The other three files (20 tests):** pure. They use tmp folders and an AST scan.

## HIGH findings

**H1 (C15). The publication step has no caller, so the public site still 404s.**
- `MANIFEST.json.how_public` says "the daily commit of backend/data/public_receipts/ is what makes the pages public". Nothing performs that commit:
  - `task_keeper.run_publish_receipts` writes the files and logs a row. No `git add`, commit or push exists in `task_keeper`, `publish_receipts` or any scheduled task.
- The only commit of the folder is the hand commit `0d6fa492` on `wip/2026-10-06-v1-beta`. `git ls-tree origin/main backend/data/public_receipts` is empty, and Railway builds from main.
- So tomorrow morning Railway serves exactly what it served yesterday.
- Every published copy will age into STALE honestly, because `refresh` recomputes from the stamps. But "public" is a claim about a process that does not exist.
- **Fix:**
  - Either schedule an attended-safe commit of only that folder, gated on the manifest's sha256s and status OK, never `-a`.
  - Or stop calling it "daily" and print the folder's git age on the System Health page: commit time of `public_receipts/MANIFEST.json` vs `published_utc`.

**H2 (C20). Flag ON silently shrinks the acting PROBE sleeve by ~42%, and the 12% core is clipped after the damage.**
- `_plan_benchmark_core` appends the core at its WANTED weight, `1 - active_gross` (0.80 today), after the order-path gate. `pc_broker.plan_orders` then normalises every target by `MAX_INVESTED_FRAC / total_w` **before** it clips any single name at `MAX_NAME_FRAC`.
- `u_plan` keeps the non-acting EXPLOIT targets in `targets`, at `room = 1 - probe_gross` (`scripts/sim_run.py` ~L1520-1540). They are planned but not sent.
- With EXPLOIT planned at 0.72, PROBE at 0.20 and the core at 0.80, `total_w` is about 1.72 and every weight is scaled by about 0.58. The core is then clipped to 12% and the PROBE names shrink.
- Reproduction (pure `plan_orders`, equity $1M, price $100):
  ```
  OFF {'EX1'..'EX6': 1200 each, 'AAA': 1000, 'BBB': 1000}
  ON  {'SPY': 1200, 'EX1'..'EX6': 697 each, 'AAA': 581, 'BBB': 581}
  ```
- So the acting PROBE orders drop from 10% to 5.8% per name, and the account receives a 12% core in exchange.
- The note's row "flag ON as built: -$32,098 (3.20%)" assumes PROBE stays at 20%, so the table is wrong for today's state. `test_flag_on_adds_one_spy_target_clipped_by_max_name_frac` asserts `gross == 0.12 + PROBE_GROSS_CAP` on a fixture with no EXPLOIT targets.
- **Fix:**
  - Send the core into `plan_orders` at its deliverable weight, `min(want, MAX_NAME_FRAC, 1 - sum(other targets))`.
  - Or exclude non-acting targets from the normalisation.
  - Add a test that runs flag ON with EXPLOIT planned but not acting and asserts that the PROBE quantities are identical to flag OFF.

**H3 (C20). The quant-ensemble contract (hack4, `0bb99e6a...`) is a significance gate on a PRODUCT_EXPERIMENT and has never gone green.**
- The eligibility rule requires "pure_selection t >= 2 on both twins AND net_minus_market t >= 2 in the validation window".
- 27 rules pass both twins and 0 pass the market line, so the frozen book is HOLD_CASH. Its twin is "cash while the book is cash", so the account produces no gradeable information.
- CLAUDE.md, THREE LICENCES: "Research rigour determines what Aegis is allowed to CLAIM. It must not determine what Aegis is allowed to TEST in paper."
- The 27 two-twin survivors are exactly what a PRODUCT_EXPERIMENT exists to test forward. Since the 09-29 CRSP run, none of the library has beaten the market, so the gate goes green only if a new rule appears.
- The t >= 2 cut also has no multiplicity control over a ~209-rule library. It is a claim-grade gate with a non-claim-grade threshold.
- **Recommendation:** trade the 27 two-twin survivors equally weighted (or the top-k by twin t), grade them against SPY and the fair twin, and label the book CANNOT_DISTINGUISH vs the market. Keep the market-line t as a CAPITAL_CANDIDATE promotion gate, not as an entry gate.

## MEDIUM findings

**M1 (C15). The fallback precedence counts receipts and ignores their age. Row-level freshness is frozen at publish time.**
- `prefer_published` serves the published copy only when `_n_present(live) < _n_present(pub)`.
- If a Railway checkout carries the same number of old tracked receipts as the published copy names, the live (older) build wins over the fresher published copy. Ties should go to the newer stamps.
- When the published copy is served, `refresh` recomputes ages for the **receipts strip only**. Book rows keep their baked `mark_status: "LIVE"`, `mark_age_days: 0` and `evidence_label`.
- So a 5-day-old arena copy shows STALE at the top and LIVE / 0 days on each row. It is not served as FRESH, but the rows contradict the header.
- **Fix:** compare `max(stamp_utc)` when counts tie. On a published copy, rewrite row ages from `last_mark` against now, or blank them and label the rows "as of <published_utc>".

**M2 (C15). The owner-name scrub covers one kind, is case-sensitive, and is not in the leak scan.**
- `_OWNER_NAME = r"\bMurat(?:han)?\b"` is applied only to `_opportunities()`. It misses upper- and lower-case forms and the GitHub handle (the `\b` after "Murathan" fails on the next letter).
- Arena, forecast, theory and health copies get no name scrub, and `leak_scan` has no owner-name, e-mail or Railway-host pattern.
- **Today's six payloads are clean.** A case-insensitive grep found no owner name, handle, e-mail, drive path, user path, loopback, broker id or Railway host.
- The protection is luck plus the per-page allow-lists. Move the name pattern (case-insensitive, handle included) into `leak_scan`, so that a hit REFUSES instead of being silently scrubbed in one kind only.
- The PC-PAPER book's holdings and `cash_fraction` (0.799) are published. Equity cannot be derived from them because no start capital is served. That is acceptable for a paper account, but it is a policy choice worth stating.

**M3 (C15). The supersession writer trusts `--supersedes <R>` without checking R.**
- It checks for none of the following:
  - that R's summary exists;
  - that R's `twin_kind` equals the supplement's (a basket supplement could supersede sticky rows);
  - that R actually scored the rule;
  - that R is older than the supplement;
  - that two supplements do not claim the same (R, rule).
- A supplement can only supersede rules it re-scored OK, because `ok` rows are the only ones stamped, and that part is right. But it can target the wrong board.
- The backfill table is acceptable, not a hand override the writer should refuse:
  - it is a closed, sourced, two-entry table in code;
  - its rules derive from the supplement's own OK rows, not a hand list;
  - it never edits a written summary.
- Pin it closed: a test should assert `len(BACKFILL_SUPERSEDES) == 2`, so the escape hatch cannot grow quietly. Have `write_supersessions` REFUSE on a missing R, a twin-kind mismatch or a conflicting claim.

**M4 (C15). The nn_lab rotation uses a new, weaker seal instead of C10's `ledger_archive.verify_seal`.**
- `rotate_revisions` writes the parquet and the manifest (with sha256), then **removes the rows from the live file**.
- It never checks that git tracks the parquet. That is condition 3 of C10's `verify_seal`, the one that exists because "a gitignored parquet is one laptop only again".
- `revisions_history` reads the archive without re-hashing it against the manifest.
- Nothing is lost yet: all 10,394 live rows are 2026-10, so the first rotation is 1 November. After that, the "sealed" month is an untracked file on one laptop that nothing verifies.
- **Fix:** reuse `verify_seal`, or at least its tracked and hash checks. Keep rows live until the month verifies as sealed.

**M5 (C15). The 09:00 catalog firing now loads bars while the sim task repeats every 30 minutes.**
- `opportunities_build` has a 45-minute limit and runs in the same window as the sim task. Two final suite runs this week were memory-killed.
- It runs as a child process, so a crash cannot take down the keeper. That helps, but it does not stop the OOM killer from choosing the sim.
- Print available RAM in the catalog row before launching the build. Skip the build (as a refusal, not a raise) below a floor.
- The silent-exit rule is correct: a 0 exit without a final `wrote <receipt>` line is REFUSED, and `opportunities_build` prints that line last.

**M6 (C20). Every "63 sessions, excess <= 0 vs both" kill rule is a sign test with no noise band.**
- These rules are neither a measured gap nor an idiosyncratic-sd line. They are the sign of a point estimate.
- For a 15-20-name small-cap book, the 63-session excess sd is several percent. A real +1%/month edge would read <= 0 against one comparator roughly a third of the time, and against both perhaps a fifth.
- That matches the ~21% false-kill rate found on 10-02 (`docs/research_notes/2026-10-02/review_forecasts_and_books_2026-10-02.md` L102).
- The consequence is softened to DEPRIORITIZED (no new entries), never MECHANISM_REJECTED. But the false-kill rate should be printed on the contract before anyone freezes it.

**M7 (C20). The innovation contract's stop and its 10% three-sigma-day claim both fail on the names it targets.**
1. **The stop quoted in sigma is a percent stop in disguise for this lane.** `clip(3 sigma, 6%, 20%)` turns the pool-max sigma of 13.5% into a **1.48-sigma stop**. That exits on noise within days, which is the 09-24 lesson. For sigma above 6.7%, the 20% clip binds every time.
2. **The binary-gap case breaches the limit the contract claims.** It loses -$10,500 against a 10% (-$10,000) three-sigma-day limit, and the entry scale of 0.82 is not applied to the binary case.
3. **RUNWAY-flagged names have no gap cap.** A name flagged RUNWAY without a dated event keeps 2% with no gap cap, so a -70% gap on 15 such names is -21%. The disclosed "no-stop ceiling" of -$30,000 is the honest line, and it should be the headline.

## LOW findings

- **L1 (C15).** The `system_health` copy publishes the whole scheduled-task inventory with remediation commands. The 00:00 copy still lists `AegisWRDSPullNight` with a "delete it" command after the task was deleted. This is not a secret, but it is the operator's console on a public page. Allow-list the task count and status, not the commands.
- **L2 (C15).** `publish` replaces each `<kind>/latest.json` before it writes the manifest. A crash in between leaves a copy whose sha256 does not match the manifest. Any check would catch it, but nothing checks it at serve time.
- **L3 (C20).** The world_news twin is redrawn per entry day (`hash(role, day)`), not sticky. For a 5-session hold this is defensible, but the contract should say why it differs from the TWIN_STICKY_v1 standard used by three of its siblings.
- **L4 (C20).** The note's reconciliation finding is correct and well pinned (`test_what_the_core_does_and_does_not_reconcile`). PROBE gross counted as 0% is a `decision_contract` bug that exists with or without the core.
- **Positive (C20).** The SPY control is not self-contradictory: `name_cap_overrides: {"SPY": 0.95}` is honoured at `fleet_manager.py:201`.
- **Positive (C20).** The capfix proposal is correctly unwired, and an AST test proves it.

## The two owner decisions on D14 (question 5)

The core never passes the order-path gate: it is added after it. It has its own worst-case shrink, and `pc_broker`'s per-name clip still binds. The order goes out under the lease like any other order, so the lease sees it. The risk gate does not.

As built, the flag is close to useless. It delivers 12% SPY, and today it would cut the acting PROBE orders by ~42% (H2). Grading against SPY already happens in `decision_ledger`, so the core adds no information. It only reduces cash drag.

- **Decision 1: should `decision_contract` count the acting PROBE/EXPLOIT gross?** Yes. This is a correctness fix, not a loosening, and the line stays red without it.
- **Decision 2: should a broad index ETF be exempt from `MAX_NAME_FRAC`?**
  - Yes, but only for `PC_BENCHMARK_CORE_SYMBOL`, under its own `CORE_MAX_FRAC`, and only after H2 is fixed.
  - Until then, keep the flag OFF.
  - Worst case at a full core is -$46,340 (4.62%) at panel sigma and -$58,444 (5.83%) at the stressed sigma. Both are inside the 10% limit, and SPY's own worst day costs -$46,935.

## Question 7: the operator's shortest path

**A live, honest public page tomorrow morning:**
1. Run the frozen-tree suite once. It has been memory-killed twice, so stop the sim and lab first and kill only by PID.
2. Merge `wip/2026-10-06-v1-beta` to main. It already carries `0d6fa492` with the six copies.
3. Push, watch CI with `python -m scripts.ci_watch --wait`, and run `verify-prod-after-deploy` against `/arena`, `/forecast-lab`, `/theory-lab`, `/health` and `/opportunities`.

The pages will be honest because their ages derive from their stamps, so a day-old copy reads STALE with its date. They will go stale again in a few days unless H1 is fixed.

**The one owner action that unlocks the fleet:** none unlocks it safely tomorrow.
- The binding constraints are code (`scripts/fleet_manager_run.py` resolves only v1/v2) and a date (earliest seed 2026-10-26).
- The most dangerous owner action is the obvious one: setting `modes.json` to `v3` today silently runs v1 terms.
- The one owner-only step on the critical path is **regenerating hack3's keys** (it answers 401). That is the only account blocker. Every other blocker is engineering.

## Three things I would have done instead

1. **Make publishing a commit, not a folder.** A keeper step would stage only `backend/data/public_receipts/`, commit it with the manifest sha in the message, and push to a branch that Railway reads, or open a PR to main. The System Health page would show "public copy is N days behind the machine". A public page whose freshness depends on someone remembering a commit is the funnel_night10 failure in a new folder.
2. **Size the core inside `plan_orders` as a first-class sleeve, or not at all.** Give it its own cap and keep it out of the invested-frac normalisation. Test the flag on today's exact state: PROBE acting, EXPLOIT planned but not acting. Then only one owner decision is needed.
3. **Give the quant role the licence it is owed.** Trade the 27 two-twin survivors forward as a PRODUCT_EXPERIMENT and print the false-kill rate of each 63-session kill line on every contract, instead of freezing an account into cash behind a claim-grade gate.
