# Investigator process — one company, one date, dated public inputs only

Distilled 2026-11-19 from the documents listed in `sources.jsonl` (10 13F tables, 4 Schedule 13D filings,
6 earnings releases, 1 partial 10-Q, 6 fund-letter excerpts). It extends the five existing microtasks in
`backend/services/investigator_agent.py` (gather → event → expectations → forecast → critic); it does not
replace them. Steps 1–9 are a typed **gather** stage that today's `read_filings` tool cannot do, because that tool
returns form, date and item codes and never the filing's text.

Licence: PRODUCT_EXPERIMENT. Output is typed fields and hypotheses. It is never a recommendation, and it gives an
LLM no authority over capital. Three earnings cases and six letters are anecdotes: they ordered the checklist, they
did not validate it.

Source keys: **[NOW] [LRCX] [CMG]** = `raw/8k/earnings_cases_extractions.txt`; **[13D-F]** Fivespan/Stride,
**[13D-S]** Saba/TCPC, **[13D-E]** Elliott/Triple Flag, **[13D-Q]** Starboard/Qorvo = `raw/13d/`;
**[13F]** = `f13_diff.json`; **[L1]..[L6]** = `raw/letters/letters_q3_2026.excerpts.txt`.

Collected today? **Y** = on disk and current, **P** = partly (stale, truncated or not parsed), **N** = not collected.

## Rule 0 — bind every input to the time it became public

Every field carries `knowable_at` = the EDGAR acceptance time of the filing it came from. Period-end dates and
"date of event" are stored beside it and never used as the gate. A later filing by the same filer on the same
issuer outranks an earlier-period one ([13D-Q]: the 13F line for Qorvo was dead 42 days before it was published).

## The checklist, in the order the documents used it

| # | Step | Came from | Data field needed | Collected? | Typed output |
|---|---|---|---|---|---|
| 1 | **What is already in the price?** Before reading the news, measure the run into the date. | [NOW] +60% in 120 sessions then −8.6 sd; [CMG] −15% in 60 then +3.4 sd; [L1] "the index is not where we want our risk" | daily closes; own 60-session sd | **Y** (`prices_2025_26/bars.parquet`) | `runup_z_20/60/120: float`, `reaction_unit_sd: float` |
| 2 | **What did the company say it would do?** Pull the range it published last quarter for this quarter. | [NOW] guide 20.5% / cRPO 19.5%; [LRCX] $8.10bn ± 0.40; [CMG] "low single digit" | prior 8-K EX-99.1 guidance table | **P** — exhibit stored to 4,000 characters; guidance sits after that | `prior_guide: {metric, low, high, filed_at}` |
| 3 | **Where did the actual land against that range?** Inside, above or below — not "beat consensus". | [NOW] printed inside/top of range, headline "beats high end"; [LRCX] inside | step 2 + current EX-99.1 headline numbers | **P** (current headline is inside the first 4,000 characters) | `actual_vs_prior_range: inside \| above \| below`, `headline_claims_beat: bool` |
| 4 | **Second derivative.** New guide for next quarter against the quarter just reported. | [NOW] cRPO 21% → 20.5% → guide 18.5%; [LRCX] $8.22bn → $8.60bn; [L6] "margins near their peak and price increases were slowing" | current EX-99.1 guidance table | **P** (same cut) | `guided_growth_delta_pts: float`, `guide_direction: accel \| flat \| decel` |
| 5 | **How was the growth produced, and where did the cash go?** Acquisitions, debt raised for them, buyback on or off, GAAP vs adjusted margin. | [NOW] $8.8bn deals in H1, goodwill ×2.7, $4.0bn notes, repurchases $0 for two quarters, margin 31% adjusted vs 8–10% GAAP | XBRL: acquisitions cash, goodwill, debt issued, repurchase cash, operating income | **Y** (`fundamentals_sec`, companyfacts; freshness 2026-09-27) | `acq_cash_to_revenue: float`, `buyback_state: on \| off \| restarted`, `gaap_adj_margin_gap_pts: float` |
| 6 | **Balance-sheet tells.** Inventory, deferred revenue, receivables and who owes them. | [LRCX] inventories $4.00 → 4.28 → 4.55bn, deferred revenue $2.22 → 2.43 → 2.66bn; [NOW] one channel partner 20% of receivables vs 11% | XBRL inventory, contract liabilities, concentration percentages | **P** (tags exist in companyfacts; concentration tag not verified as stored) | `inventory_growth_minus_revenue_growth: float`, `ar_concentration_change_pts: float` |
| 7 | **Mix shift.** Which region, customer or driver produced the change. | [LRCX] China 26% → 35%, Taiwan 27% → 18%; [CMG] check +1.3%, transactions +0.8% | segment / geographic tables in EX-99.1 or 10-Q | **N** for text; XBRL segment axis not parsed | `largest_mix_shift: {dimension, member, delta_pts}` |
| 8 | **What is the company doing with its own stock?** Price paid, amount, authorisation raised. | [CMG] $630.7m at $32.55, +$1.3bn authorised, then $110m at $34.05, market $28.73; [LRCX] $1.02bn; [NOW] zero | 10-Q Part II Item 2 table; 8-K 8.01 | **N** (no 10-Q text; repurchase cash only via XBRL) | `avg_repurchase_price_last_q: float`, `price_vs_repurchase_price_pct: float`, `authorization_change: float` |
| 9 | **Who else has acted in public, with a date and a reason?** 13D Item 3 (cost), Item 4 (demand), Item 6 (pledges, swaps); cooperation agreements; proxy-fight notices. A 13F is context only. | [13D-F] cost $79.92, agreement and committee before the 13D; [13D-S] discount to NAV as the lever; [13D-E] 64.8% pledged against $1.3bn | SCHEDULE 13D / 13D-A XML; 8-K item 1.01 exhibits; DFAN14A | **N** (9 rows of 13G from 2024 in `teacher_library`) | `holder_events[]: {filer, form, filed_at, pct, implied_cost, demand_type, standstill_until, pledged_shares, loan_principal}` |
| 10 | **Is there a dated catalyst, and what happens if it does not occur?** | [L2] "identifiable catalyst for a rerating"; [L5] the divestiture that did not happen, position >20%, −40% | 8-K / press text announcing reviews, closings, approvals | **P** (8-K items yes; text cut) | `catalysts[]: {event, expected_by, source_filed_at}`, `no_event_case: str` |
| 11 | **Can the customer break the scarcity it is paying for?** Supplier capacity announced, lead time, contracts that fix volume but not price. | [L6] (low provenance) | competitor capacity announcements typed per product market | **N** | `scarcity_breakable: yes \| no \| unknown`, `capacity_lead_quarters: int` |
| 12 | **Expectations microtask** (existing): what did the market believe, already priced? Now fed by steps 1–4 instead of prose. | existing `SYS_EXPECT` | steps 1–4 | — | existing contract + `expectation_gap: actual_vs_prior_range × runup_z` |
| 13 | **Critic** (existing), with one added question: *in which single scenario do this name and its hedge lose together?* | [L1] shorts "amplifying our AI longs"; [L6] "All three groups would lose together in that case" | book positions, residual correlations | **Y** (book DNA) | `joint_loss_scenario: str`, `hedge_residual_corr_60d: float` |
| 14 | **Forecast** (existing cells, unchanged): `abs_move_exceeds` 1d/3% and 5d/5%, `return_sign` 5d, prior and posterior. | existing | — | — | existing; graded by `iif1_grader` |

## Thesis-broken / sell block

The letters treat selling as part of the process, with stated triggers. Each becomes a boolean computed from a dated
input; none is a stop price.

| Trigger | Came from | Field | Collected? | Output |
|---|---|---|---|---|
| The dated catalyst is cancelled or passes with no event | [L5] | step 10 | P | `catalyst_failed: bool` |
| The company guides growth down a second consecutive time | [NOW] | step 4, two quarters | P | `guide_decel_streak: int` |
| The reason for holding was stated last quarter as provisional and nothing new arrived | [L6] "could not stay in the book by default for another quarter" | prior thesis card with a review date | Y (`thesis_card.py` exists) | `review_due: bool` |
| A holder who gave the thesis exits in a dated filing | [13D-Q]; 164 "ceased to be >5%" documents a year | 13D/A, Form 4 | N / P | `sponsor_exited_at: date` |
| The hedge has become a second position in the same factor | [L1], [L3] | step 13 | Y | `hedge_is_second_long: bool` |
| The buyer of last resort has stopped | [NOW] repurchases $0; [CMG] $631m → $110m | step 8 | P | `buyback_state` change |
| **Not a trigger:** the price moved against us with no new dated fact | [L6] Mettler "a mistake of impatience"; Lumentum sold, then +60% from the low | — | — | `price_only_exit: bool` is logged so the cost of impatience can be measured |

Measured here already: a −2% stop is 0.93 daily sigma on the median name and lost to holding on real bars. Triggers
above are facts, and any price rule is quoted in sigma.

## Sizing block

| Rule observed | Came from | Typed output for Aegis |
|---|---|---|
| Size follows conviction, not benchmark weight; top ten = 64.5% of 29 names | [L4] | `top10_share` reported per book (already in scorecard) |
| A position is larger than usual only when it has a second, independent reason (counter-cyclical as well as cheap) | [L2] | `n_independent_reasons: int`; size tier cannot rise on one reason |
| When two halves of a book are opposite bets on one variable and the sign is unknown, size them equally | [L6] | `shared_driver: str`, `equal_weight_within_driver: bool` |
| The cap is set by the scenario in which everything loses together | [L6] 9% cap; [L1] cut gross and net | worst case in dollars for the largest admissible book (session protocol item 4) |
| An initial position above 20% is a declared exception, and it produced −25% year to date in the one case read | [L5] | `concentration_exception: bool` with its loss case printed |
| A uniform 12–16% trim across the largest lines is fund-level resizing and carries no view on any name | [13F] Akre: Mastercard −11.6%, Visa −16.3%, Moody's −11.9%, KKR −13.5%, Roper −14.8%, Brookfield −13.3% | `pro_rata_trim: bool` — such rows are excluded from any "manager sold X" feature |
| Observed concentration: top-10 share 55.7% (Lone Pine) to 86.1% (Akre); largest line 9.1% to 29.2% (Duquesne, Natera) | [13F] | context only |

## Steps we cannot execute today, and the cheapest free fix

1. **Steps 2–4 (prior guide, landing zone, second derivative).** The EX-99 collector keeps 4,000 characters; 90% of
   stored bodies are cut exactly there and the guidance table comes later. Fix: store the full exhibit (same EDGAR
   URL already in each row; no new source), then a table parser for "Guidance" / "Outlook" blocks.
2. **Step 9 (who acted, with cost and demand).** No Schedule 13D reader; `teacher_library` has nine 13G rows from 2024.
   Fix: the EDGAR daily form index (`sec_daily_index.py` already walks it for Forms 3/4/5) filtered to
   `SCHEDULE 13D` and `SCHEDULE 13D/A`, whose `primary_doc.xml` has been structured XML since December 2024.
3. **Step 8 (repurchase price) and step 7 (mix).** No 10-Q text is stored. Fix: the 10-Q primary document from
   EDGAR for names that trip the trigger, Part II Item 2 table only; or the XBRL `frames` API for
   repurchase and segment facts.
4. **Step 11 (scarcity).** No source exists yet; it is a typing job over 8-K capex and capacity announcements.

One further blocker applies to every fix: EDGAR answered HTTP 403 ("Undeclared Automated Tool") to a User-Agent
without an e-mail address. The project's own collectors send one. A project contact address that is not a personal
mailbox would let a research session read filings directly.
