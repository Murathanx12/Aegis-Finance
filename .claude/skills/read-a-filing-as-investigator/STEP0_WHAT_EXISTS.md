# Step 0 — what Aegis already collects, already tested, and the lab's intake schema

Read 2026-11-19 from the release clone `C:\Users\mrthn\aegis-runtime-20261115b` (code, docs) and, read-only, from the
live data under `C:\Users\mrthn\aegis-finance\backend\data\optimus\`. Counts were taken today from the files named.

## 1. SEC data on disk, by form

| Form | Where | Rows | Newest | Read by a decision path? |
|---|---|---|---|---|
| 8-K item codes | `edgar_8k/eightk_items.parquet` | 293,619 filings, 2,594 CIKs, 2013-01-02 on | **2026-09-03** (built once) | `hyp_cells` event read-through; survivor caveat in its manifest |
| 8-K "current" feed | `news_corpus/sec_edgar_8k_current_atom/` | 9,639 rows, 47 day files | 2026-11-19 | news corpus |
| 8-K EX-99 body | `news_corpus/sec_edgar_8k_ex99_body/` | 5,275 rows, 43 day files from 2026-09-19 | 2026-11-19 | news corpus. **4,761 of 5,275 bodies are exactly 4,000 characters** |
| Form 4 (bulk) | `sec_insider/insider_events_v1.parquet` | 3,127,624 events, 2006q1–2026q2 | built 2026-09-08 | insider cells (verdict CANNOT_DISTINGUISH) |
| Forms 3/4/5 daily | `teacher_library/events.jsonl` | 1,589 rows (Form 4: 1,460; Form 3: 108) | **2026-08-13** (one day collected) | COPY-LAB lanes, which have no scheduler job |
| 13D / 13G | same file | **9 rows**, all 13G-type (`SC 13G/A` PASSIVE_STAKE) | filed **2024-03-11** | `ACTIVIST_13D` lane: 0 events ever |
| 13F | `wrds/holder_events/` + `holder_transitions/` (WRDS Thomson s34) | 115 quarters, q119 = 335,524 event rows; `manager_actions_quarterly_v1` 249,424 rows, 11,313 managers | **2024Q4** | holder H2/H3, popularity corpse. No EDGAR 13F reader exists |
| 10-Q / 10-K text | — | **none** | — | — |
| XBRL company facts | `fundamentals_sec/sec_fundamentals_*.json` | 3,000-name table | 2026-09-27 | fundamentals rankers |
| DEF 14A, DFAN14A, SC TO-I, 10-12B, 13D XML | — | **none** | — | — |

The scheduled task `AegisRawSecCollection` collects one thing: the 8-K EX-99 body feed. Its wrapper
(`aegis-recovery-evidence\oct15-clean-recovery-20261015\oct15-sec-cursor-runtime-r6\`) has written
**no OK receipt since 2026-11-16 14:15 UTC: REFUSED / SOURCE_PIN_DRIFT from 2026-11-17 01:53 UTC, `consecutive_failures: 49` in today's receipt, the rest SKIPPED / BACKOFF**,
while Task Scheduler shows `Last Result: 0`. Rows still arrive in the folder because the news writer covers the same
source (`CORPUS_WRITER_ACTIVE` in the receipts), so nothing downstream looks empty.

## 2. What is already tested (do not re-run under a new name)

| Idea | Verdict here | Receipt / doc |
|---|---|---|
| Copy 13F popularity | corpse; the mandatory control for any 13F work | `scripts/holders_13f.py`, `docs/IDEA_2026-08-31_HOLDER_PROVENANCE_TO_THE_ROOTS.md` §2 |
| Institutions selling predicted HIGHER returns | reported (return level), $10–50m/day band | `tracker_backtest/` |
| Manager identity / holding-period fingerprint (H2, H3) | PRODUCT_EXPERIMENT run, filer grain, active/passive UNKNOWN | `tracker_backtest/holder_h2_h3.json` |
| Insider buys, clusters, CMP opportunistic | CANNOT_DISTINGUISH from the market | `hyp_insider_events`, `TRIAL-INSIDER-IC`, `TRIAL-CMP-INSIDER-IC` |
| Analyst target implied upside | CLOSED / PERVERSE | `signal_registry` (`analyst_target_upside_xs`) |
| Hedged analyst-revision flow | gross t 2.67 vs twins, net unpowered | S71 |
| Personas vs process (14,703 forecasts) | `investigator` +8.97% held out; nine personas −27.98%; skill at h=1, gone by h=5 | canon §64 |
| Restatement (8-K 4.02) | declared cell exists | `scripts/hyp_restatement.py` |
| COPY-LAB lanes (insider cluster, activist 13D) | seeded 2026-08-14; 1 ineligible signal, 0 activist events | `docs/TEACHER_LIBRARY_COPY_LAB.md` |

## 3. The investigator process as it runs today

`backend/services/investigator_agent.py` (trial INTERNET-INVESTIGATOR-FWD-1): five small contracts —
**gather** (tools) → **event** (what changed, novelty, expectedness) → **expectations** (already priced?) →
**forecast** (prior, posterior per cell) → **critic** (objection, falsifying check). Cells: `abs_move_exceeds` 5d/5%,
`abs_move_exceeds` 1d/3%, `return_sign` 5d. Names come from `investigator_triggers.py` (abnormal move, volume,
earnings within 5 days, fresh filing; no model output in the trigger). Grading: `iif1_grader.py`, paired Brier
across arms, outcomes stripped in power mode. Tools (`investigator_tools.py`): news search, `read_filings`
(**returns form, date and 8-K item codes only — never filing text**), revisions, options IV, earnings summary, prices.

## 4. The schema a hypothesis needs to enter `hyp_lab`

`backend/services/hyp_lab.make_hypothesis(...)`, appended to `backend/data/optimus/hyp_lab/ledger.jsonl`
(489 log rows today: 114 PROPOSED, 56 NEEDS_CELL, 73 + 12 duplicates; verdicts 60 CANNOT_DISTINGUISH,
47 FAILED_VARIANT, 8 CONDITIONAL_POSITIVE, 1 REFUSED).

- Required (`REQUIRED`): `title`, `mechanism`, `precursor`, `separation_from_beta`, `refutation`, `target`.
- `target` ∈ `size | direction | return | co_movement | llm_capability | data`.
- Also set: `family`, `source`, `source_ref`, `data_needed[]`, `cell_type`, `params{}`, `split{}`,
  `negative_informative`, `cost_usd`, `cpu_min`, `gpu_min`, `expected_power`, `notes`.
- Derived: `hyp_id = "H-" + sha1(norm(mechanism)|norm(precursor)|params)[:10]`, `sha256`, `created_utc`, `status`.
- A `precursor` or `refutation` shorter than 12 normalised characters → `DISCARDED_NO_REFUTATION`.
  `cell_type = None` → `NEEDS_CELL`. Runnable cells today: `macro_lead_lag`, `event_readthrough`,
  `size_feature_increment` only. **No cell takes a filing field as its precursor**, so every row in
  `precursor_hypotheses.jsonl` enters as NEEDS_CELL.
- Dedup: cosine ≥ 0.09 against `docs/NEGATIVE_RESULTS.md` / `WHAT_WE_ALREADY_KNOW_LLM.md`, ≥ 0.70 against the ledger.
- The schema has no field for the matched control, the event count, the licence or the closest corpse; the rows here
  carry them as extra keys.
