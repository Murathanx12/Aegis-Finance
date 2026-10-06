# book_dna — build note (chunk C3, 2026-10-06)

**Licence: PRODUCT_EXPERIMENT. Nothing here is a claim.** Spec:
`winner_loser_dna_2026-10-06.md` (R4) and `ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md`
§5 row C3 / §7.

## RESULT

> **147 ahead of SPY = 39 non-twin = 19 independent clusters; largest cluster = SNOW, OKTA, ABNB, CRWD, CRM (15%)** [Jaccard 0.30; clusters 8 at 0.15, 19 at 0.30, 26 at 0.50]

From the first scheduled-path run: `backend/data/optimus/paper_accounts/roi_2026-10-06T160824Z.json`,
with `aggregate.collapse_line` and the fields below, and its companion
`backend/data/optimus/paper_accounts/book_dna_2026-10-06T160824Z.json`.
Collapse factor **7.74**. 108 of the 147 are control twins. **0 of 362 priced books
have more than `OBSERVED(n)`**: nothing reaches EARLY_EVIDENCE, because that needs
≥ 21 sessions, excess > 0, and a full-window series positive in 2 of 3 sub-windows.
The winners are 6–10 sessions old. The books old enough (lanes, the fleet) are
either behind SPY or have only 6 graded sessions of daily series.

R4 counted the 04:59Z receipt (148 / 40); this 16:08Z re-read counts 147 / 39.

## What was built

| file | what |
|---|---|
| `backend/services/book_dna.py` (new) | loads holdings + series, builds per-book DNA, clusters, lanes, losers; writes `paper_accounts/book_dna_<run_id>.json`; never labels above REPLICATED (`LABEL_CEILING`, asserted) |
| `scripts/paper_accounts_roi.py` | `attach_book_dna()` runs before the receipt is written (the caller is the daily pass's `paper_accounts` step); the summary goes INTO `aggregate` (`n_ahead_raw`, `n_ahead_non_twin`, `n_independent_clusters_ahead`, `collapse_factor`, `largest_cluster_share`, `largest_cluster_basket`, `collapse_line`, `book_dna_receipt`); `honest_sentence` now ENDS with the collapse line (the count-only text is kept as `honest_sentence_counts`); PAPER_ACCOUNTS.md prints the collapse line directly under the count; the chart title carries it; a failure is a REFUSED summary whose line says the count "is NOT a count of independent bets", never silence |
| `backend/config.py` | `BOOK_DNA_*` thresholds (Jaccard 0.30 + sensitivity, corr 0.80 / 15 obs, beta ≥ 20 obs, EARLY ≥ 21 sessions, fair-twin kinds, one-name 50%, loser rules) |
| `scripts/daily_pass.py` | the `paper_accounts` row carries `collapse_line` and `book_dna_receipt` |
| `backend/services/model_routing.py`, `scripts/daily_learning_report.py` | they printed `n_ahead_of_spy` bare; they now print the collapse line, or "NOT COMPUTED" for a pre-C3 receipt |
| `backend/tests/test_book_dna.py` (new) | 7 tests, every date derived from today |

`signal_reachability`: `book_dna` classifies itself as `tooling_only` (reached from
`scripts/`); no registry edit needed.

## Cluster table (non-twin books ahead, Jaccard ≥ 0.30 or return corr ≥ 0.80 / identical series)

| id | n | shared basket (top 5) | excess pp mean / median | members |
|---|---:|---|---|---|
| 0 | 6 | SNOW, OKTA, ABNB, CRWD, CRM | +3.73 / +5.06 | hack2, revision_flow_v0, pers_revision_flow_leaders, lib_net_raises, lib_net_raises_ivw_lead, lib_skill_raises__control |
| 1 | 6 | MU, LITE, SNDK, AXTI, TWST | +2.98 / +2.03 | lib_resid_mom_12_1_large_sealed, lib_qc395_sharpe252_above_trend_large, lib_qc470 ×2, lib_mom_12_1_q_trend_lead, lib_disp_short_avoid |
| 2 | 4 | MRK, TSM, ASML, VRTX, MU | +0.97 / +1.06 | pers_ai_power_global, pers_quality_momentum, pers_ensemble, pers_catalyst_calendar |
| 3 | 4 | AMD, CLYM, DELL, DFTX, GH | +2.38 / +2.35 | lib_skill_mom_sealed, lib_skill_mom, lib_mom_flow, lib_mom_flow_ivw |
| 4 | 3 | META, JAZZ, AVPT, AMZN, AAPL | +0.72 / +0.72 | probe_bigmove_tilt, probe_equal, probe_inverse_vol (the PC-PAPER names; PC-PAPER itself is behind SPY on this read) |
| 5 | 2 | — (no holdings read) | +7.14 / +7.14 | night book "Cash/index by default" and "Always invested — Book D" (**identical daily returns**) |
| 6 | 2 | 000660.KS, GEV, 6857.T, ARGX, HOOD | +1.35 / +1.35 | cards_supports, reviewer_opus |
| 7–18 | 1 each | — | +1.0 to +8.1 | 12 singletons (12-1 momentum night book, pers_asia_supply_chain, SHADOW_BAYES_v0, CRSP_BLEND_v0, murat_core_satellite, eight `lib_*`) |

On the threshold: R4's "~6 clusters" used Jaccard 0.15 on 35 lib/personal books;
this receipt reads 39 non-twin books (including night books, hack2 and probes)
and finds **8 at 0.15**. The declared value is 0.30 ("largely the same book"),
and the line prints all three counts so the choice is visible. A looser threshold
chains: at 0.15 the semiconductor basket absorbs most of the momentum books, which is
R4's finding.

**Lanes (derived, not hard-coded):** `conservative-atr, aggressive, balanced,
conservative` are one risk-dial family (daily-return corr 0.89–0.98).
`tsmom-overlay, balanced-ew-control, tsmom-6040-control` form a second (0.82–0.91).
Identity statements from holdings: the five reference lanes hold the same names
(76 in the union, pairwise Jaccard 0.92–1.00, declared caps 3% / 5% / 8%), and
**conviction and mirror hold the same 12 names (Jaccard 1.00): declared
max_single_name conviction NONE, mirror 25%; top-1 now conviction ABSI 18.8%,
mirror DKNG 22.0%.**

**Losers (bottom 10 by excess, rule-chosen `error_type`):** mirror
sizing_concentration (by weight: DKNG 22% now) · hack4 sizing_concentration (RZLV
carries 334% of the open-position loss) · hack6 selection · conviction timing_exit
(71% of the shortfall 08-26..10-05; ABSI 18.8% is under the 20% weight fallback) ·
hack1 selection · smallmid-quality not_determinable · balanced-ew-control
timing_exit (78% in 06-11..07-15) · three night-book twins control_artifact. By
the declared rule order this differs from R4 in two places, hack6 (R4: sizing/
operational drift) and conviction (R4: sizing). The rule cannot see hack6's
negative cash or odd-lot count, and conviction's top weight is just under the
fallback.

## Position cap — declared vs new (INVESTIGATED, NOT SHIPPED)

**R4 said mirror/conviction's cap was "diagnosed 2026-08-02 and never enforced
(`book_management.py:221`)". That is half wrong.** Line 221 is conviction's
decision-apply path. The two lanes differ:

* **mirror: DECLARED and ENFORCED, with one hole.** `backend/data/book_lanes.yaml`
  `mirror.max_single_name: 0.25` (`max_sector: 0.60`). `book_management._mirror_target_weights`
  applies `rules.enforce_position_limits` at every mirror rebalance. The hole: the
  live positions route (`GET /api/pi/lane/mirror/positions`) shows the **2026-06-16
  drift and 2026-07-14 monthly rebalances wrote DKNG 50% / SLDP 50%**. HRP had
  dropped 10 of 12 names ("dropped [AARD, ABSI, …]" in the event text), and the
  waterfill cannot hold a 25% cap over two names: n × cap = 0.5 < 1, and its own
  docstring says it "converges when n * cap >= 1.0". It returns over-cap weights
  and does not refuse. That state ran through mirror's −14.3% July. Since 2026-08-02
  all 12 names are priced and post-rebalance maxima are 19.8% / 22.2% / 21.8%.
  Enforcing the registered construction here means **refusing (or holding the
  remainder in cash) when n_priced × cap < 1**. That fix sits in
  `rules.enforce_position_limits`, which all four reference lanes and `exit_lane`
  share, or in the mirror path before it. Either way it is upstream of a lane's
  rebalance write and is `lane-integrity-check` work. I did not ship it.
* **conviction: NO cap declared — a new cap is an OWNER DECISION.** `book_lanes.yaml`
  `conviction:` has no `max_single_name`, on purpose: the lane is defined as
  Murat's real book at current-MV weights, changing only via logged decisions.
  A cap changes what the lane measures, and editing the YAML moves
  `get_book_config_hash` (a segment boundary). Not built.

**Worst case in dollars** (long-only, Σ|notional|/equity ≈ 1.0 for both; NAVs from
`roi_2026-10-06T160824Z.json`: mirror $75,525, conviction $90,928):

| book / cap | single-name weight | one name → 0 | one name −50% |
|---|---:|---:|---:|
| mirror, now | DKNG 22.0% | $16,600 | $8,300 |
| mirror, declared cap (max at a rebalance) | 25% | $18,900 | $9,400 |
| mirror, the 06-16 → 08-02 state (n × cap < 1) | 50% | $37,800 | $18,900 |
| conviction, now | ABSI 18.8% (AARD unpriced) | $17,100 | $8,500 |
| conviction, no cap (largest admissible) | 100% | $90,900 | $45,500 |
| conviction, owner option 25% | 25% | $22,700 | $11,400 |
| conviction, owner option 15% | 15% | $13,600 | $6,800 |
| conviction, owner option 10% | 10% | $9,100 | $4,500 |

Between rebalances drift can carry any name past its cap: the cap binds only at
rebalance, as the 08-02 dossier noted.

## Not finished / caveats (each is visible in the receipt, not hidden)

* **BRIDGE.md** prints no "N ahead of SPY" count. It already prints its own
  collapse ("32 books under test = 18 distinct bets"), so `bridge_report.py`
  (C1-adjacent) is untouched.
* **Still printing `n_ahead_of_spy` bare:** `backend/services/alerts_replies.py`,
  `backend/services/telegram_cockpit.py` (C6's files) and
  `scripts/stock_lists_v3_build.py`. Owed: each should print
  `aggregate.collapse_line` beside it.
* **`one_name_dependence` is true on 129 books**, many with an excess near zero. A
  share of a small excess is large by construction. I suggest a minimum |excess|
  (e.g. 0.25 pp) before apportioning. Not changed tonight, so code and receipt stay consistent.
* ETFs are absent from the bars panel, so most reference lanes have PARTIAL
  concentration and NOT_COMPUTABLE cash. Foreign tickers leave
  `pers_asia_supply_chain`'s tail NOT_COMPUTABLE (34% of weight unpriced).
  Night-book holdings are not read by v1. Lane P&L share is NOT_COMPUTABLE because
  lots reopen at each rebalance.
* The fleet series (`grades.jsonl`) starts 2026-09-29: 6 of 26 sessions. So hack2
  cannot earn EARLY_EVIDENCE yet, and nothing has a beta except the lanes (lanes:
  mirror 0.59, conservative-atr 0.12, tsmom-overlay 0.24).
* The two ROI receipts this run wrote had an absolute local path in
  `aggregate.book_dna_receipt`. I rewrote that one field to the repo-relative path
  before any commit, and the code now writes it repo-relative.

## After the adversarial review (`docs/reviews/REVIEW_2026-10-06_C3_BOOK_DNA.md`, F1–F8 applied)

The headline "19 independent clusters" above is **superseded**. New receipt:
`backend/data/optimus/paper_accounts/roi_2026-10-06T163850Z.json` + `book_dna_2026-10-06T163850Z.json`.

Top line of PAPER_ACCOUNTS.md:

> **1 book with >= 21 sessions is ahead of SPY (hack2, +1.14 pp / 26 sessions). The other 146 "ahead" are 108 control twins, 3 controls and 35 5-16-session books ~ 2.6 ex-ante bets (4.6 net of SPY), the most common name MU (17 of 33 books, Semiconductors; its books' ex-ante beta ~ 2.1). Nothing here is evidence yet.**

* F1: `n_independent_clusters_ahead` is renamed `n_holdings_clusters_ahead` (20 at Jaccard 0.30). New: `effective_bets_exante` 2.6 (raw) / 4.6 (SPY-residual). These are participation ratios of the return correlation of 32 books' frozen weights, priced over the 150 sessions before the earliest inception (2026-02-23 → 2026-09-25). Top eigenvalue share 59%; 7 clusters at raw corr ≥ 0.80.
* F2: clusters sort by size, then total excess, then name. Every cluster of 3 or more books prints with its basket. The largest component at the loosest threshold prints too: Jaccard 0.15 → MU, SNDK, STX, RVMD, INTC, 17 books. MU is in 17 of 33 strategy winners with holdings.
* F3: P&L rules fire only when the visible P&L covers ≥ 80% of the shortfall. hack4, hack6 and hack1 are now `not_determinable` (open-position P&L covers 1% / 1% / 6%). `selection` requires a covered loss spread across names.
* F4: timing uses the gross negative sub-window loss. Lanes in an identity group are `decomposed`. For mirror: −12.86 pp common = selection, and −15.40 pp is the treatment/sizing gap to conviction. For balanced-ew-control: −1.76 common, −5.40 differential. The rule order prints as `params.loser_rule_order`.
* F5: `kind: control` books are their own count (3).
* F6: `one_name_dependence` is computed only on the excess basis, with |excess| ≥ 1 pp and a reconstruction gap ≤ 0.25 pp. The share is bounded to same-direction contributions, and twins are not flagged. 2 books are flagged (SHADOW_BAYES_v0, reviewer_opus); 35 are computable.
* F7: `evidence_density_line`: only 1 of 147 books ahead has ≥ 21 sessions. A REPLICATED sibling must now itself be EARLY_EVIDENCE.
* F8: the collapse factors print separately: twins+controls ×4.08, holdings overlap ×1.8, ex-ante ×13.5.
* Not done (fix-next): F9, the lane beta lag check. Also cosmetic: the collapse line prints the ex-ante window as a Python list.
