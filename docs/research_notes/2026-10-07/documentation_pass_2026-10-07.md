# Documentation pass, chunk C23 (2026-10-07)

**RESULT IMPROVEMENT: NONE** (documentation only; no code, no git). Files written:
`docs/AEGIS_V1_BETA_2026-10-07.md` (new), `docs/FUNDING_EVIDENCE_PACK_2026-10-07.md` (promoted from the
Sonnet draft, which is left in place), `README.md` (refreshed), `docs/INDEX.md` (two lines added). One
data row was appended by the command the brief asked for: `python -m scripts.llm_cost_audit --snapshot`
added a `cost_audit` balance row to `backend/data/optimus/deepseek_balance.jsonl` ($17.87 at
2026-10-06T22:44:42Z).

## Removed from the README (each read as a return claim, or was stale against the current receipt)

1. "**Paper accounts, 2026-09-26:** 229 tracked; 39 priced — $4,679,959 on $4,733,154 (**-1.12%**); 7 ahead of SPY …" — 11 days stale; replaced by the V1 Beta scoreboard on `roi_2026-10-06T163850Z.json`.
2. "Sorted by net return vs SPY in that window …" and its top-10 table (`mom_12_1_liqw` +89.4% CAGR, +68.4% vs SPY, and nine more rows) — measured on the vendor panel that was selected on 2026 liquidity (`HANDOFF_2026-09-29_THE_DAY_THE_BACKTESTS_DIED.md`); superseded by CRSP.
3. "**The one out-of-sample number the backtest holds:** choosing the top 10 rules by dev … gave **+8.8 pp/yr** mean vs SPY …" — same panel; a return figure that the CRSP re-run did not reproduce.
4. "**110 of 288 rules beat SPY in the 2024-26 window**" and "**69 of 288 rules beat SPY in both windows** …" — same panel; counts of SPY-beaters on a survivor-selected sample.
5. The 2026-09-26 track-record table (e.g. "Cash/index by default … +10.10% … +8.64 pp", "conservative-atr … +1.53 pp") — stale; on the 10-06 receipt all ten website lanes are behind SPY.

The rest of that section (the pooled-family paragraph, the frozen-leads paragraph, the vectorbt
replication line) went with it; the run stays citable at `strategy_library/leaderboard_2026-09-27T082553Z.json`
(commit `6b70c553`), and the section now reports the CRSP results instead.

## Weakened in the README

- "The ordering is real." → "The ordering clears its null." (an IC against a shuffled null, not a fact about money).
- "The money is not — yet." → "The money is not demonstrated." ("yet" promises a result).
- "Paper portfolios will eventually say whether any of it makes money." → "… are the test …; so far none has shown that it does."
- "No alpha claims … *we don't know yet*" → "Alpha: not demonstrated … *no evidence that it does*".
- "Not a trading bot. No execution, no live orders" → "No real money. Orders go to paper accounts only" (the PC-PAPER loop does submit paper orders; the old line was inaccurate).
- Licence table "this is alpha" and the BACKTEST badge's "Never an alpha claim" → "a public skill claim" / "Never a skill claim" (the brief allows "alpha" only as "not demonstrated").
- "no backtested alpha claim here is trustworthy" → "a backtest on the free vendor panel cannot carry a skill claim; the survivorship-free re-runs use CRSP".
- Test badge "3,800+ passing" → "12,496 passed on main (2026-09-29)"; the fast-suite comment likewise. The work branch is not green-gated (handoff §0), so no count is claimed for it.
- Rung 4 pointed at `ROADMAP_2026-08-31_…` (superseded); now the 10-06 roadmap and the V1 Beta doc.
- `mirror`'s "−22%" → "−24.5%" (current receipt).

## Corrected or weakened in the funding pack (against the Sonnet draft)

- "can **prove** which information changed a decision" → "records which information changed a decision".
- "The **reader** was DEAD 6.7 days" → it was the **live decision loop** (no sim session since 09-29); the reader ran.
- "Pages/claims per week: NOT MEASURED" → measured: 9,368 pages → 238 claims → 3,587 forecast rows over 7 days (`openclaw_open_web_and_model_audit_2026-10-06.md`).
- Paper-estate figures 148 / 159, PC-PAPER +0.19%, fleet −9.81% came from the morning receipt `roi_2026-10-06T045934Z.json`; `roi_2026-10-06.json` was **overwritten** at 00:39 HKT by the later run (147 / 160, +0.27%, −9.17%). The pack now cites the run-stamped `roi_2026-10-06T163850Z.json`. (Same defect family as the 09-26 lesson "a date-named receipt a second run can overwrite is not a receipt".)
- PC-PAPER "ahead of SPY because it sat in cash while SPY fell" → on the current receipt it is **behind** SPY (+0.27% vs +0.86%, −0.60 pp); with 80% cash the sign follows SPY.
- Website lanes were quoted as raw returns; on the current receipt **all ten are behind SPY** over their own windows. Alpaca fleet figures were the 09-26 README's; replaced by 10-06 rows.
- NVDA Decision Story figures were labelled "outcome"; they are **position weights under each alternative**, frozen before any outcome.
- "Every current licence that permits trading does so in paper only" → `CAPITAL_CANDIDATE` would permit real-money candidacy; nothing holds it.
- "D7/D9 are this boundary" → D9 is battery operation; the browsing boundary is D7 and D15.
- Railway "$48.05 over one audited month (Aug 26 – Sep 26)" → $48.05 covers **Aug 26 → Sep 20** (~25 days), quoted from the owner's bill via a memory note in `REVIEW_2026-09-26_RAILWAY_COST.md`; not a repo receipt.
- Desktop "bundles a local model … works fully offline with no key" → "can run a local model at $0 marginal cost"; offline-without-keys is C24's acceptance, not yet receipted. Tokens-per-second and VRAM figures dropped (machine details).
- "392,201–393,000 revisions … (memory S55)" and other memory-only citations → repo documents only.
- The owner's local path to the March CUPP deck removed (no user-home paths in public docs).
- Added: every book is `OBSERVED(n)`; hack2 cannot reach `EARLY_EVIDENCE` because its series covers 6 of 26 sessions.

## A defect found while running the cost audit (not fixed: no code edits in this chunk)

`scripts/llm_cost_audit.py` picks `since` = the day of the last snapshot, then takes the **last** snapshot
on that day as the starting balance. Run late in a day, it compares telemetry since 00:00 with a balance
read minutes earlier, prints `DISAGREE`, and attributes the gap to a top-up that did not happen (this
run: provider $0.05 vs telemetry $3.4973; the balance series has no top-up since 2026-09-27). A fair
comparison needs the last snapshot strictly before `since`. Separately, on 10-06 telemetry ($3.50 from
00:00 UTC) exceeds the provider's own drop from the 10-05 17:18 UTC snapshot ($2.05), so telemetry may
over-count (1,540 amendment rows in the October ledger are a candidate). Both belong to whoever owns the
cost audit next.

## Numbers that could not be sourced

- The owner's "~$1,500 over six months": no reconciling receipt.
- The current Railway monthly bill: the last figure in the repo covers 08-26 → 09-20.
- Market sizing, pricing or outreach for customer hypothesis 3.
- The ROT5_DIR event replay (28.1% of top-5 slots dropped): in a review, not a receipt.
- No standalone review file exists for C8 (progress-aware health); C14, C16, C17, C18 have no review yet.

## Visuals still owed

1. **Opportunity Explorer** (`/opportunities`): a real screenshot on the filing date.
2. **Paper Arena** (`/arena`, chunk C19): not in `frontend/src/app` at the time of writing; until it is,
   the fallback is the `book_dna` top line and cluster table.
3. **Decision Story chain**: event → evidence → forecast → decision → order or abstention → outcome →
   attribution, with the frozen-alternative table beside it; from the dry NVDA example until a live story
   exists.
4. **Health board**: ALIVE / STALE / DEGRADED / DEAD across sensors, graders, the live loop and nn_lab,
   from `health_probe`'s receipt (`/health`, chunk C19, not yet in the app).
