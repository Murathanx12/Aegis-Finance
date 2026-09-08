# DECISIONS — 2026-09-08 — Fable on the re-arm, the three open calls, and the one constantly-active book

**For Murat, then the Opus builder.** Follows `BUILD_2026-09-08_FLEET_REARM_AND_PREMARKET_OFF.md`
and the nine lane docs (`BUILD_2026-09-07b_*`, `BUILD_2026-09-08_R*`). Pushed:
finance `6c04baf`, terminal `1281486`. Terminal suite re-run by me on 09-08:
ALL PASS. Finance suite: CI verdict on `6c04baf` is recorded at the bottom.

## 1. Are we beating the S&P 500?

**On the backtests: no, not by any honest ruler.** The best historical net
line is `ensemble_ew|k=100|ew|hold=200|10bps` (terminal wealth 62.87 vs the
market's 13.18 over 1999-2024, β 1.195, β-matched +5.65%/yr t 2.42), and its
edge is 1999-2007; on the months when it is genuinely a multi-arm ensemble it
is +2.1%/yr t 0.7. Family-corrected: NOISE. The revision family at equal cost
goes 3.66 → 18.14 (25 bps) against a market of 13.18; Holm 0.49. The growth
champion, sealed once on 2016-2024: 3.6684 vs SPY 3.6707. Every raw-wealth
line above the market carries β above one; nothing survives the alpha ruler.

**On the paper accounts: no, and until 2026-09-08 they could not have.** All
six books held zero positions from 2026-09-04 (four independent disarms in the
deployed environment plus a crash on every role-less pass). The only readable
forward lanes are older: conservative-atr +0.14pp at β 0.04 (it sat out a
rising window), mirror −22pp and conviction −7.7pp at real β. The books re-armed
today hold about 25 positions on $157k of ~$575k, under the OLDER seal's terms
(horizon 21 / min hold 10; the corrected 63/21 and 42/21 contracts apply from
the next seal). The first readable number is 20 sessions away, and under the
product ruler it will be printed with β first.

**What is true and worth money:** holding (hysteresis, turnover 0.90 → 0.53)
and breadth (transfer coefficient 0.13 → 0.49) recover a measured amount of
the information the old construction threw away, era-stable. That is a
mechanism, not alpha. And one event signal held across all three eras with a
placebo that flips sign (§4 below).

## 2. The three decisions

1. **hack1 / SPY: correct not to duplicate.** The benchmark is the seventh
   account (`market`, contract `PASSIVE_BETA_v1`, seeded 2026-08-27). hack1 stays
   the survival layer, manage-only. Add the `market` account's keys to `.env`
   (names only in any doc) so `scripts.fleet --check-all` and `crossbook` can
   read the benchmark; the roadmap's F table is corrected below.
2. **hack4's $99k: the gate is broken, not strict.** `requires_catalyst: true`
   tests a clause `murat_rule` itself lists under `clauses_not_measured`, against
   a calendar that was empty until 2026-08-30. A gate that cannot go green is
   a broken gate (CLAUDE.md). The frozen contract is not edited; **a v2 contract
   is frozen** with `requires_catalyst: false` and the catalyst carried as an
   `UNVALIDATED_INDICATOR` on the row, the v1 retired with this reason in the
   supersession log, worst case printed (5 × 8% at a 15% stop = −6.00%), and
   Murat flips it. Until then hack4's capital sits in the `market` account's
   shadow, not in cash without a thesis.
3. **The MMC prereg stays blocked at R13.** The missing measurement is named;
   a prereg that proceeds without its measurement is the thing the prereg
   exists to prevent.

## 3. The session's real result, and where it goes

Two lanes independently found that **there is no joined text-and-return
panel**: 21,841 of 993,005 event rows carry both a headline and a permno,
9,457 labelled cells across 135 names. That is why a from-scratch encoder on
528k headlines loses to TF-IDF and why every archetype inherits one
corpus-level effect. R4 adds the mirror image: 2015-2024 has prices and ~1%
news; 2025-2026 has 44-46% news and no CRSP prices. **No year has both.**

Decision: **E0 — the joined panel — is the first item in block E**, ahead of
any new mechanism. It is two things: (a) the permno link for the news rows
that exist (ticker→permno through CRSP `dsenames` by date, not today's
mapping); (b) a 2025-2026 price panel from Alpaca daily bars so the years with
news can be graded. The E3 gate is rewritten as R4 §14 proposes: it names its
reading, and the earnings family (95-98% coverage every year 1999-2024) is
not blocked by the news family's number.

## 4. The one constantly-active book (Murat: "day trading or one system that is constantly active, to test and learn")

**Decision: hack2 becomes the EARNINGS-REACTION book.** Not intraday day
trading, for one reason: nothing in this repo has evidence for an intraday
edge (the 5-session small-cap reversal died at the $100k floor; the opening
range has never been tested), and an always-active book that loses on costs
teaches nothing except costs. The earnings-reaction book is active every
session of the year (something reports every day; 8-K item events fill the
off-season), and it is the one signal R4 found that **did not decay**:

| ranked on, at the announcement | 21-session spread | 1999-2007 | 2008-2015 | 2016-2024 | placebo +40 sessions |
|---|---|---|---|---|---|
| the surprise (SUE) | +1.54% t 5.77 | t 4.01 | t 4.65 | t 1.47 | t 1.28 |
| **the announcement reaction** | **+1.80% t 7.37** | t 6.13 | t 2.97 | **t 3.67** | **t −2.04 (sign flips)** |

Pre-event drift difference +0.68% (not repackaged momentum); breakeven 39-45
bps a side; the placebo reverses (ordinary short-horizon reversal away from an
event, continuation at one). It is a screen result under PRODUCT_EXPERIMENT.
Through a *monthly* cross-sectional construction it fails (+2.98%/yr t 0.77 at
`k=50|vw`), because a monthly rank book is not a faithful test of a 21-session
event clock. So:

1. **First, the faithful backtest** (R4 §12 item 1, one lane, hours): enter at
   session +1 after each announcement, long the top reaction decile among names
   above the `$3m/day` floor, hold 21 sessions, 25 bps a side, β printed
   first, three eras, the placebo re-run on the same book. Add the
   announcement timestamp (free) so `e1/e2` collapses to a number.
2. **Then the contract, v2 for hack2:** horizon 21 / min hold 5 / stop at 1.3
   daily σ of the name (not a constant) / n × notional 8 × 6% / gross ≤ 48% /
   exits `THESIS_INVALIDATED` (a reversal of the announcement move beyond the
   name's σ), `DEADLINE` at 21; **loss budget: judged at 40 events, 24 expected
   to lose**; worst case printed at seal. PRODUCT_EXPERIMENT; no significance
   gate; frozen before the first decision. Murat flips.
3. **Learning from it, from session one:** nightly four-counterfactual regret
   (held to 21, held to review, engine pick, SPY), recall of the day's
   reporters it did not buy, exit attribution by typed reason. Judge the
   process for a quarter; judge P&L after.
4. **If Murat still wants an intraday arm**, it runs as a zero-capital shadow
   book beside hack2 under the same contract discipline (opening-range or
   first-hour reaction), and graduates to capital only on its own scoreboard.

## 5. What this changes in the roadmap amendment

- F table: hack1 is the survival layer, not the SPY control; the `market`
  account is the benchmark; hack2 is the EARNINGS-REACTION book (v2 contract);
  hack4 v2 without `requires_catalyst`.
- E block: E0 joined panel first; E3 gate reworded per R4 §14.
- Handoff session two gains lane **D** (the faithful reaction backtest → hack2
  v2 contract → shadow intraday arm) and lane **E0**.

## 6. Verification of the nine-lane session

`VERIFICATION_2026-09-08_OPUS_NINE_LANES.md` (an independent Opus agent, from
receipts) verifies most of the session; five corrections to what Murat was
told, in order of consequence:

1. **The loops hold the OLDER 09-08 seal** (`f2099277…`, sealed 05:07Z:
   horizon 21 / min hold 10 / `stop_frac` null), not `dc6b580d` (06:35Z, the
   63/21/12% and 42/21/10% terms). The build doc's own §12 says the loops
   synced the older one and will not re-fetch. **The corrected contracts are
   tomorrow's book, not today's.** Both 09-08 receipts name `f209…` as basis.
2. **Deployed capital is $157,089, not ~$165k** (hack3 $75,003 + hack6
   $82,086 per `RECEIPT_2026-09-08_LIVE_TRANSFER.json`); the ~$575k total is
   right ($575,579).
3. **Arming is by declaration only; there is no deploy receipt.** Whether the
   six live `AAT_LOOP_ARGS` lack `--manage-only` is unknowable from the repo.
   Murat's own Railway variables are the evidence; a deploy receipt (variables
   per service, redacted) belongs in `state/` after every flip.
4. **"DeepSeek untouched at $9.28" was asserted, not measured.** My snapshot
   at 11:43Z on 09-08 reads **$9.11**: $0.17 left the balance between the
   09-06 and 09-08 reads, and no lane's ledger accounts for it (the loops'
   pre-market digest, on the same key, is the likely spender and is now off).
5. **"0 UNCLASSIFIED drivers" is true of the code, not of the seal**, which
   still stamps `driver_exposure: {"UNCLASSIFIED": 0.83}`; the sector map is
   applied downstream in `alpha/drivers.py`. An auditor opening the JSON
   would conclude the fix did not land.

Also: the `taskkill` hook (X11) is NOT done and `.claude/settings.local.json`
still *allows* `Bash(taskkill:*)`; only 3 of the 4 Sunday suites got the venue
fixture (`tests_smoke.py` never imports it); the news backfill is alive (PID
50240, 12 of 18 months). Everything else in the report — the 11,522,229 Form 4
rows with a real PIT red-test, the clock-skew guard in `alpha/runner.py`, E1,
H1, S1 with executed tests, hack4's gate, the joined-panel numbers — verified.

Terminal suite: ALL PASS on 09-08 (my run). **CI on `6c04baf`: RED**, three
Linux-only causes fixed forward over two commits, **green on `397bd4d`**
(backend and frontend jobs both success, 2026-09-08):

1. `test_journal_router` walked `app.routes` for the write surface; FastAPI
   0.141 on CI (dev venv 0.135) wraps an included router in `_IncludedRouter`
   with no `path`/`methods`, so the test read **zero** routes and would have
   passed vacuously the other way. It now reads `app.openapi()["paths"]`.
2. `test_r4_event_families` indexed an empty glob of local-only WRDS parquet;
   it now asserts the function's own refusal branch on a fresh checkout.
3. My balance snapshot appended two readings seven seconds apart; the
   price-derivation reproduction test read every reading on disk and the
   solver correctly refused the zero-token window. The test now reproduces
   the receipt's own readings. Reproduced first in a `python:3.12` container
   on a depth-1 clone, per the 09-06 lesson; the dev venv is not a reproduction.
