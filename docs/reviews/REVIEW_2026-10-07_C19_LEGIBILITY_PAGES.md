# REVIEW 2026-10-07 — C19 legibility pages (Arena, Forecast Lab, Theory Lab, Health)

Reviewer: Opus 5.5, adversarial (investor reading for five minutes + security-minded operator).
Scope: `backend/services/legibility.py`, `backend/routers/arena_v1.py`, `backend/routers/legibility_v1.py`,
the four pages under `frontend/src/app/{arena,forecast-lab,theory-lab,health}`, `components/legibility/receipts.tsx`,
`backend/tests/test_legibility_routers.py`. Read-only. Payloads were built in-process from the real receipts
on disk (no server) and grepped.

## VERDICT

**SHIP TO THE PRIVATE SITE AFTER FOUR FIXES; DO NOT PUBLISH TO THE PUBLIC SITE AS IS.**
The receipt discipline is real (own-stamp ages, UNKNOWN for undateable, verbatim C3 lines, PC-PAPER shown
behind SPY, `missing_because` everywhere). But the builder's sanitisation claim — "cash/equity NOT served" — is
false on the Arena payload, the Theory Lab serves two twin-board rows the research note says are superseded,
the Forecast Lab mixes two different walk-forward runs under one heading, and "WEAKENING" relabels an
uninformative result as directional evidence.

## Evidence run

| check | result |
|---|---|
| `AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_legibility_routers.py -q` | **12 passed**, exit 0 (the builder's "21" includes reachability tests elsewhere) |
| `cd frontend && npx tsc --noEmit` | exit 0 |
| payload size, real receipts | arena **0.67 MB** · theory-lab **1.05 MB** (twin boards 0.92 MB of it) · forecast-lab 0.08 MB · system-health 0.05 MB · stories 404 (no `decision_story/` folder) |
| build time per request (warm) | arena 0.01 s · theory 0.07 s · forecast 0.01 s · health <0.01 s |
| receipts served today | ROI `roi_2026-10-06T163850Z` + its named book_dna (6.4 h, FRESH) · health `20261006T175305Z` (5.2 h) · reputation / report / grade_forecasts / nn nightly / world_state / analyst all FRESH · twin boards `STK_2026-10-07_2`, `FT_2026-10-07_1` |

## Findings

### F1 — HIGH — Equity IS served: `by_family.sum_equity` / `sum_start_capital` / `pnl`, exact for one-account families

`arena_payload` passes `agg["by_family"]` through whole. On the real receipt it carries `sum_equity`,
`sum_start_capital` and `pnl` for every family. Three families have `n = 1`, so the family sum IS the
account's equity:

- `pc_paper` gives PC-PAPER's broker equity to the cent.
- `murat_book` gives the owner's **personal** book value (start ≈ 33k, now ≈ 31.9k) and its P&L.
- Every other family gets a dollar total.

The `_ROW_DROP` tuple is declared and **never used**. Row safety comes only from `_book_row`'s whitelist, and
the aggregate blocks (`by_family`, `top`, `numbers.tilt`, `status_counts`) bypass it. The arena page does not
render `by_family`, but the public JSON endpoint serves it, and `api.ts` types it.

The share counts in `backend/data/murat_book.yaml` are already tracked in a public repo. That limits the harm;
it does not make the builder's stated contract true. The arena also lists `murat_live` as a `strategy` book
(OBSERVED(38), −4.64 pp) beside the paper books. Whether a personal account belongs in a public league table
is the owner's decision; it should not be the default.

**Fix:**
- Whitelist `by_family` to `{n, n_priced, roi_pct}`.
- After assembly, apply a recursive key filter to the whole payload (`equity|cash|start_capital|pnl|account_number|buying_power`).
- Gate the `murat_*` families behind personal mode.

### F2 — HIGH — Theory Lab serves two rows its own research note says are superseded

`_twin_board` picks "the board with most rules" (`STK_2026-10-07_2`, `FT_2026-10-07_1`). It lists the 2-rule
reruns only as `other_boards_not_served`.

`docs/research_notes/2026-10-06/sticky_twin_2026-10-06.md` §F4 says those reruns matter.
`mom_12_1_liqw` and `qc623_mom63_liquidity_weighted` were still equal-weighted in both full boards (a missing
`amihud` column was filled silently). They "were re-scored in the supplements `FT_2026-10-07_2` and
`STK_2026-10-07_3`, **which supersede those two rows**."

Validate fair-twin net t, served board vs supplement:

| board | rule | served t | supplement t |
|---|---|---|---|
| sticky | `mom_12_1_liqw` | **−2.56** | −1.05 |
| basket | `mom_12_1_liqw` | **−2.84** | −0.86 |
| sticky | `qc623` | −0.35 | +0.12 |

"Most rules wins" correctly avoids showing a 2-rule run as *the board*, but it serves known-wrong rows.

The supplements' own metadata cannot repair this mechanically:
- `STK_2026-10-07_3.supersedes_for_twin_reads = "nothing: a sticky-twin board BESIDE the basket board"`.
- `FT_2026-10-07_2` claims to supersede `FT_2026-10-06_1`.

The writer has to record row-level supersession.

**Fix:**
- The board writer stamps `supersedes_rows: {run_id: [rules]}` on a supplement.
- The reader overlays it row by row and marks each overlaid row with its source run.
- Until then, flag those two rules as `SUPERSEDED — see <run>` instead of printing their t.

### F3 — MEDIUM — The Forecast Lab mixes two walk-forward runs under one tournament card

The tournament card takes its tables from two different walk-forward runs:

- `tournament.nightly_table` comes from the nightly's `wf_20260929_post_review.json` (written 09-28, 8.3 d old).
- `walkforward_models` and `walkforward_magnitude` come from `wf_20261007T_c5_review.json`. These feed the
  **house finding** (trailing-vol IC 0.34, t 72).
- `NN_WF_RE` picked the second file because its name sorts newest. It is a reviewer's rerun, not the canonical
  walk-forward.

The page shows both and never says their provenance differs. The nightly table's age is not in the `receipts`
strip, so it never reaches `status`.

**Fix:**
- Serve the walk-forward the nightly cites (`tw.receipt`) as the tournament.
- Show any newer `wf_*` as a separate block labelled "review rerun".
- Put both in `receipts`.

### F4 — MEDIUM — "WEAKENING" is the wrong word for an unpowered negative

The rule "unpowered FAILED_VARIANT → WEAKENING, not FALSIFIED" fixes half the error. WEAKENING claims a
trajectory: evidence moving against the theory. An unpowered negative carries no directional information.

Two examples served today, neither of which tells the reader anything:
- `H-3b254e9abc` is WEAKENING with **no confirm stats at all**.
- `H-3471279117` has mean −0.48%/mo, t −1.11, MDE 1.20%/mo.

Meanwhile 11 CANNOT_DISTINGUISH rows sit in HYPOTHESIS beside 48 never-run PROPOSED / NEEDS_CELL rows. That
hides the fact that they *were* tested.

Proposed exact map:

| hyp_lab input | state |
|---|---|
| PROPOSED / NEEDS_CELL / DECLARED, no verdict | `HYPOTHESIS` (untested) |
| CANNOT_DISTINGUISH | `UNINFORMATIVE` (tested; MDE printed) |
| FAILED_VARIANT, powered is False **or None** | `UNINFORMATIVE` (sign and MDE printed, "negative, unpowered") |
| FAILED_VARIANT, powered True | `FALSIFIED_VARIANT` (this variant; the family stays open, per EXPLORE DIRTY) |
| MECHANISM_REJECTED | `FALSIFIED` |
| history positive → latest non-positive, **latest powered** | `WEAKENING` |
| history positive → latest non-positive, latest unpowered | `UNINFORMATIVE` (+ "after a positive") |
| non-positive → CANDIDATE / CONDITIONAL_POSITIVE | `STRENGTHENING` (unchanged) |
| CANDIDATE, a split mean ≤ 0 | `REGIME_SPECIFIC` (unchanged) |
| CONDITIONAL_POSITIVE | `CONDITIONAL_SUPPORT` (unchanged) |
| CANDIDATE | `EARLY_SUPPORT` (unchanged) |
| REFUSED / DISCARDED_NO_REFUTATION | `INVALID_EXPERIMENT` (unchanged) |
| DUPLICATE_* / RETIRED_FROM_CURRENT_SEARCH | `RETIRED` (unchanged) |

Under this map today's counts become roughly:

| state | count |
|---|---|
| HYPOTHESIS | 49 |
| UNINFORMATIVE | 33 |
| CONDITIONAL_SUPPORT | 3 |
| FALSIFIED_VARIANT | 2 |
| RETIRED | 16 |
| WEAKENING | 0 |

The honest headline is "zero theories weakening; 33 tested without power". Also stop listing UNINFORMATIVE
rows among the page's "negatives".

### F5 — MEDIUM — The Arena's Winners panel undoes the top line

The top line says only one book with ≥ 21 sessions is ahead of SPY (hack2, +1.14 pp), and that "Nothing here
is evidence yet". The Winners card directly under it says otherwise:

- It lists ten strategy books at +4.4 to +8.1 pp.
- All ten are 6–16 sessions old, and hack2 is not among them.
- Two of the ten show the identical +7.139: a Book D strategy and its "primary comparator".

The table and tiles below repeat the problem:

- The default table sort is by vs-SPY descending with twins included, so **9 of the top 20 rows are TWINS**.
- Twins carry only a small sky-coloured TWIN badge. The row is not dimmed, and nothing sorts it below strategy
  rows.
- The first stat tile is "Ahead of SPY (raw count) = 147".

**Fix:**
- Winners = strategy books with sessions ≥ 21, ranked by vs SPY.
- Move the 6–16-session books to a collapsed "too young to rank" list.
- Make "strategy" the default category filter, and dim twin and control rows.
- Lead the tiles with the ≥21-session count, not the raw 147.

### F6 — MEDIUM — Skill numbers on one page use two different baselines

The two skill numbers are measured against different climatologies:

- **Reputation skill** (the MAGNITUDE vs DIRECTION table and the arm rows): its `split` says "climatology =
  base rate of the **scored** rows". That is the held-out half's own realised rate, a hindsight baseline.
- **Sigma-prior skill** (+0.091 h1 / +0.049 h5): its `split` says "climatology = **training-half** base rate".

The house-finding list prints both side by side under the same unit, "Brier skill vs climatology (held out)".
For example, the prior's +0.091 sits beside pooled arm magnitude h1 +0.105.

Two smaller problems on the same page:
- `_kind_horizon_table` pools per-arm skill scores, weighted by n. That is a new statistic, which the module
  docstring says the reader never computes. A weighted mean of skill scores is also not the pooled skill.
- The trailing-vol IC (t 72) is the same mechanism as the sigma prior. Listing it as separate evidence counts
  one fact twice.

The page does define skill in one line ("1 − Brier / climatology on each arm's later half …"). It does not say
which climatology.

**Fix:**
- Name the baseline in each row's unit string.
- Have the writer compute the pooled skill; the reader should only display it.
- Label the vol-IC row "sanity check of the prior", not evidence.

### F7 — MEDIUM — The calibration chart has no uncertainty and counts overlapping rows as independent

h1 and h5 are separate panels, which is right. But each bucket's `n` is a plain row count:

- h5 rows are per-name daily forecasts whose 5-day outcome windows overlap and share dates.
- Buckets with n = 11–29 are drawn as solid points beside buckets with n = 300.
- No bucket has an interval or a date-block count (§58: n_effective counts DATE BLOCKS).

The visible story is that the investigator over-predicts h5 |move| (predicts 0.68, realises 0.39). It is
probably real, but a reader cannot tell which points are noise.

**Fix:**
- The reputation writer emits `n_dates` and a Wilson or block-bootstrap interval per bin.
- The chart draws whiskers and greys out bins with < 30 rows or < 5 dates.

### F8 — MEDIUM — Machine detail and raw error text still reach the browser

The real health payload leaks:
- live **process ids** in `proof` fields, with "cmdline contains <script>";
- a local **port** in one `evidence` string;
- a credential env-var name (`…_KEYS_ABSENT`);
- the name of a paywalled publisher's reader and its page throughput, on the gateway row. On a public page that
  is a reputational and terms-of-service exposure.

Scrubbing is applied field by field and misses some fields:
- `task_owners[].detail` is passed through **unscrubbed**, although the same `detail` is scrubbed in `rows`.
- `where`, `source` and `read_me_first` are never scrubbed.

Error responses and URLs leak or break too:
- Both routers return `detail=f"{what}: {type(e).__name__}: {e}"` on 500. The message of a `JSONDecodeError`,
  `PermissionError` or `FileNotFoundError` contains the absolute user-home path and bypasses `scrub`.
- `scrub`'s Windows regex also eats URLs. `https://…/v2/account` becomes `GET httpaccount + /v2/positions` on
  the served PC-PAPER and hack2 rows. That hides the host by accident and garbles the text.

Task owners show names and receipt patterns, not command lines. That part is right.

**Fix:**
- Scrub the whole payload once at the router boundary, not field by field.
- Drop `pid \d+` and `:\d{2,5}` port forms.
- Return only the exception TYPE on a 500, and log the message.
- Handle URLs explicitly: keep the path, drop the host.

### F9 — LOW-MEDIUM — Freshness edge cases

Three cases need a fix:

- **(a) A failed broker read hides the newer receipt.** `newest_roi` prefers any broker-read receipt over a
  **newer** `.nobroker` one. If tomorrow's broker read fails, the page serves yesterday's receipt as FRESH for
  up to 48 h and never names the newer one.
- **(b) Date-named receipts are overwritten in place.** `reputation_<date>`, `report_<date>`,
  `grade_forecasts_<date>` and `reputation_weights_<month>` are rewritten by a second run on the same day. The
  page cites a path whose content can change under it (the 09-26 leaderboard lesson). Fix: serve the `sha256`
  of the bytes read with every receipt ref.
- **(d) Per-row staleness shows only in the drawer.** Inside a fresh receipt, 7 marks are STALE and 1 is
  BROKER_ERROR. Fix: add a mark-status column to the table.

Two cases are already right:

- **(c)** Arena pairing uses the book_dna the ROI receipt names, not the newest book_dna.
- **(e)** The stories 404 reads correctly as an absence.

### F10 — LOW — Tests are narrow where it matters

What the tests do:
- They mock `OPTIMUS_LEDGER_DIR` → `tmp_path` and stub `daily_pass.run_health_probes`.
- All fixtures are synthetic, and `NOW` is derived from today (protocol 5 kept).

The sanitisation assertions are weaker than they look:
- They use a fixture with a fake account number (`PA00SECRET`) and a fake user-home path. But the whitelist
  never copies `account_number`, so that assertion is vacuous.
- The fixture's `.env` hint sits inside parentheses, the one form `_ENV_NOTE` catches.

No test puts any of these into a payload:
- `sum_equity` / `pnl` in `by_family`;
- a PID in `proof`;
- an unscrubbed `task_owners.detail`;
- an exception message in a 500;
- a URL through `scrub`.

One fixture that runs the WHOLE serialized payload through a deny-list regex would have caught F1 and F8.
No test covers a supplement board superseding rows (F2).

### F11 — LOW — Performance is fine; payload weight is not

No endpoint re-reads a large ledger. The heaviest per-request read is the Theory Lab: about 4.8 MB uncached
(two 2.3 MB board JSONLs plus the hyp_lab ledger, parsed twice), taking about 70 ms.

The 1.05 MB theory payload is 92% twin-board rows (2 boards × 301 rules × 4 columns × 4 windows), for a page
that shows one board at a time.

**Fix:**
- Serve board rows on demand (`?board=sticky`).
- Cache the parsed JSONL by (path, size, mtime), as `read_json` already does.

### F12 — INFO — Deploy reality

Most receipts these pages read are not in git: the ROI receipt, the reputation receipt and the learning report
are untracked, and the health receipt is gitignored. On Railway every page except the Theory Lab will 404.

The planned `publish_receipts` step is the right shape. It must apply the F1/F8 whole-payload deny-list **at
copy time**: a tracked folder in a public repo is a second publication channel that bypasses the router
entirely.

## What is right (keep it)

- Ages come from each receipt's own stamp, never the file mtime.
- An undateable receipt is UNKNOWN, and the STALE banner is never hidden.
- The C3 top line and collapse line are copied verbatim from `aggregate`.
- PC-PAPER is shown at **−0.598 pp** (the run-stamped receipt), not the earlier +0.19.
- The undated `roi_<date>.json` copy is skipped, and SMOKE boards are excluded.
- The CRSP sentence is quoted from the handoff, with its source.
- "No model has earned forward weight" is derived from trust = 0, not written by hand.
- Every null carries `missing_because`.
- A test pins the health headline to the daily pass's line.
- The 404 / 422 / 500 semantics are right.

## Investor's question

**The page that would change what the owner does tomorrow is the Arena, specifically the PC-PAPER row.** It is
the only book trading the live mandate, and it reads −0.60 pp vs SPY after 10 sessions.

**The missing number is the error bar on `vs_spy_pp`.** That means the book's daily tracking error against SPY,
and from it the MDE: how many sessions until this gap can be told apart from zero. Without it the reader cannot
tell "behind" from "noise". Every row in the 367-row table has the same gap. That one number would tell the
owner not to change the PC-PAPER policy on this reading.

## Three things I would have done instead

1. **One sanitiser at the boundary, deny-by-default.**
   - Every payload passes through one function before it leaves the router.
   - That function applies a recursive key deny-list plus value regexes: paths, PIDs, ports, hosts, env-var
     names and account-like ids.
   - One test serializes each REAL-shaped fixture and asserts nothing matches.
   - Field-by-field `scrub()` calls are how `by_family` and `task_owners.detail` slipped through.
2. **Writers own the semantics; the reader only displays.**
   - Four things belong in the receipts their writers produce, with a content hash: row supersession (F2), the
     baseline name (F6), the per-bin date counts and intervals (F7), and the theory state (F4).
   - The reader then truly computes nothing, and the page cannot disagree with the research note.
3. **Lead each page with the one decision-relevant number and its uncertainty.** Put the full tables behind a
   click.
   - Arena: ≥21-session books vs SPY with tracking-error bands; twins and controls hidden by default.
   - Forecast Lab: the sigma prior vs the best arm on the SAME baseline, with block counts.
   - Theory Lab: counts of tested with power / tested without power / untested.

## Score: **66 / 100**

The receipt hygiene is strong and the top lines are honest. Points are lost for:
- a stated sanitisation contract that is false on real data (F1, F8);
- known-superseded rows served as current (F2);
- mixed provenance and mixed baselines on the Forecast Lab (F3, F6);
- a state label that turns silence into a direction (F4);
- a Winners panel that contradicts the page's own top line (F5).
