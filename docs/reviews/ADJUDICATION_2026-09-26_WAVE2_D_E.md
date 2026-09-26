# Adjudication — 2026-09-26 wave 2 (chunks D + E) — Fable, 19:10 HKT

Review: `REVIEW_2026-09-26_CHUNKS_D_E.md`. Builders' commits: D `c4f46332`, E `5cbef964`,
discovery registration `08628087` (the run that overwrote E's receipt).

Verdict accepted as written: **neither chunk moved terminal wealth; both made results
gradeable, and E's construction undermines its own gradeability.** Fixes dispatched to one
builder (files disjoint from PRF2/PRF3); every row below is either code tonight or a named
next-run item.

| # | finding | verdict → action |
|---|---|---|
| 1 | **The receipt moved under the README.** `08628087` ran the factory four minutes after E and overwrote `leaderboard_2026-09-26.json` in place: 762 cells → 834, 254 rules → 277, 88/254 → 104/277 beating SPY. README, BRIDGE and the frozen books' notes quote the old numbers against the same path; the vectorbt check verified a top-10 file that no longer exists (four `qc*` rows never replicated). | accepted — the mtime family (protocol item 7) in a new coat: **a date-named receipt that a second run can overwrite is not a receipt.** Factory receipts get a `T<HHMMSS>Z` run id; the date-named file is a "latest" copy; README/BRIDGE cite the suffixed path + HEAD hash; replication re-run on the current top-10; docs re-rendered. |
| 2 | **"Sealed" is not sealed.** The split was declared before the ranking, but the board *sorts* on the 2024-26 column, and every rule was written in Sept 2026 by people who saw 2024-26. Honest name: "2024-26 selection window (split declared, data seen)". The one held-out number already in the receipt: **top-10 chosen on dev only → mean +4.5 pp/yr vs SPY in 2024-26, median −1.6 pp, 5 of 10**; dev-rank vs 2024-26-rank Spearman **0.16**. | accepted — renamed everywhere; `dev_selected_sealed_evaluated` computed by the factory on every receipt (top-10/20/50, Spearman, MDE); README and BRIDGE carry the sentence. |
| 3 | **Power.** 32 monthly blocks at σ≈6.5%/mo → SE≈1.15%/mo → MDE≈4%/mo at 80% power. A window that length can kill a rule; it cannot certify a 0.5%/mo edge. | accepted — MDE printed on the receipt; no row is "confirmed" by the 2024-26 column, only "not killed". |
| 4 | **Seven of the nine books frozen today fail a sane freeze rule** (dev>0 ∧ 2024-26>0 ∧ top-5 share<0.6 ∧ max DD>−40%): only `skill_mom` and `low_asset_growth` pass; `mom_12_1_q` was already frozen. Freezing the top-3 as "the sealed top-10 with a $1M book each" teaches that a leaderboard is a slot machine. | accepted — the reviewer's 15-point rule becomes `freeze_gate()` in the factory (selection 1–7, construction 8–12, timing 13); a failing row is frozen as a **CONTROL**, never a headline book; every boolean on the freeze log and a gate column in BRIDGE. Item 14 (chained re-freeze at each rule's own rebalance date) is the next run's item — tonight's books are, by construction, the rule for one month only. |
| 5 | **`lib_mom_12_1_liqw_sealed_2026-09-26` is a coin flip on MU's 09-30 print**: MU 60.3% + SNDK 37.2%, ρ 0.90, book daily σ≈6.4%, effN 2.0. Cause: unbounded `inv_amihud` weighting — the rule's median effN is 3.3 in 2024-26 with a >50% top name (SMCI, NVDA 96%, MSTR, APP, PLTR 88%, SNDK, MU). | accepted — **voided before entry** by an appended `llm_portfolio/void` row (books.jsonl is never edited); its `__ew` twin stays as the strategy test. Rule 5 protects forward *failures*; this book has not traded. |
| 6 | **The vectorbt replication is the same code run twice** except the period returns from raw bars (which is worth something: index shifts, wrong fills). Holdings, fills, no-drift and the cost formula are shared. | accepted — renamed "re-implementation of the arithmetic, not an independent engine". Independent = a clean-room re-selection of `mom_12_1` with drifting weights (next factory night), then LEAN. |
| 7 | **`skill_mom`'s edge is 2025** (+53 pp vs `mom_flow` +10 pp; equal without 2025; worse before 2024). | accepted — two $0 controls registered: `skill_mom_ranks_21_40` and `unskilled_mom`; the gap by year with 2025 excluded is the observation. Consistent with ANALYST-SKILL-1's ADOPT_AT_TRIVIAL_EFFECT: the branch stays unfunded. |
| 8 | `mom_12_1_q`'s +45 pp (2023) / +42 pp (2024) over monthly momentum may be calendar luck. | accepted — the three quarterly offsets run as controls. |
| 9 | Semis/UMD decomposition of the 2024-26 top-10 (SPY + SMH + own `mom_12_1` ew, intercept t). | accepted — `bridge_report` table if SMH is in the panel, else `SMH_NOT_IN_PANEL` printed. |
| 10 | Murat's "backtest X correlates to paper": first visible on the **2026-10-26 close**, 19 books × 1 month, but MU sits in 6 of 9 new books and SNDK in 5 — effectively ~3 independent draws; one book needs 34–66 months to reach 2 SE. | accepted — the sentence goes in README/BRIDGE verbatim: no forward day graded yet; first reading 2026-10-26; the correlation is between "expected rel. to date (dev)" and "forward relative", and its n is books-minus-overlap, not books. |
| 11 | "Only 2 rows good in both windows" was wrong (53 on the old receipt). | accepted — recomputed and printed. |

**Not accepted / deferred:** LEAN via Docker tonight (memory; the clean-room re-selection is the
cheaper independent check); voiding the other six gate-failing books (they are controls, and a
control that trades is information).

**What this changes for the reader of the README:** the headline is no longer "the sealed top-10
each got a $1M book" but "ranked on a window we had seen, 5 of the 10 rules chosen blind on
pre-2024 beat SPY afterwards by a median of −1.6 pp; nothing clears multiplicity; the forward books
are the only quotable record and the first one lands 2026-10-26."
