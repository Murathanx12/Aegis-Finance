# REVIEW 2026-10-06 — C3 `book_dna` (adversarial, Opus)

Reviewed: `backend/services/book_dna.py`, `backend/tests/test_book_dna.py`, the C3 hunks in
`scripts/paper_accounts_roi.py`, `scripts/daily_pass.py`, `backend/services/model_routing.py`,
`scripts/daily_learning_report.py`, `backend/config.py` (`BOOK_DNA_*`), the receipts
`paper_accounts/book_dna_2026-10-06T160824Z.json` + `roi_2026-10-06T160824Z.json`, the build note
and the R4 research note. Read-only; nothing re-run that writes.

## VERDICT: MERGE WITH FIXES

The plumbing is right: the count can no longer be printed without a line next to it, a failure becomes
a REFUSED line instead of silence, receipts are never overwritten, every threshold is printed, and the
tests are green. **The headline number is wrong, though.** "19 independent clusters" is a holdings
overlap count at one Jaccard cutoff. The return-correlation edge that was supposed to catch
same-exposure books with different names never fires for 34 of the 39 books. Measured on ex-ante
returns, the 36 winners with holdings come to about **2.6 effective bets** (4.5 after removing SPY),
not 19. The "largest cluster" is a tie, and row order decides which basket wins it. That tie-break hides
the memory/semis basket R4 found. Fixes F1–F5 must land before the line goes to the top of
PAPER_ACCOUNTS.md. F6–F9 can follow.

Must fix before merge: **F1, F2, F3, F4, F5**. Fix next: F6, F7, F8, F9.

---

## Findings

### F1 — HIGH — "independent clusters" is not independence; the corr edge is dead for 34 of 39 books

`cluster()` adds a return-correlation edge only when two books share >= `BOOK_DNA_MIN_CORR_OBS = 15`
common periods. 34 of the 39 non-twin winners were incepted 2026-09-28/29 and carry **5–6 periods**.
The night books carry 6 and hack2 carries 6. So the only edge that ever fires is holdings Jaccard,
plus one "identical returns" edge between two night books. The module cannot see two books that hold
different names with the same exposure, and that is the exact case axis 1 asks about.

Evidence. I took each winner's frozen weights and priced them as a buy-and-hold over 150 sessions
*before* inception (2026-03-02 → 2026-09-25, bars panel + global panel). Results for the 36 books
with holdings:

| measure | raw daily returns | SPY-residual returns |
|---|---:|---:|
| median pairwise corr (all pairs) | 0.57 | 0.24 |
| median corr **between** the receipt's "independent" clusters | 0.54 | 0.21 |
| effective bets (eigenvalue participation ratio) | **2.64** | **4.48** |
| top eigenvalue share | 58% | 40% |
| single-linkage clusters at corr >= 0.70 | **1** | 11 |
| single-linkage clusters at corr >= 0.80 | 7 | — |

The ex-ante betas of the lib momentum books run **1.8–3.0** (resid_mom 2.87, qc395 3.01, low_dtc
2.59, margin_mom 2.51). On raw returns, "cluster 1" (MU/LITE/SNDK) and "cluster 3" (AMD/DELL) are one
high-beta momentum book. An investor would accept **"about 3 bets, roughly 5 net of the market"**,
not 19 and not 8. The 19 is a fair count of *distinct name lists*. Call it that.

Fix: rename the field and line to `n_holdings_clusters_ahead`. Add `effective_bets_exante` (the
participation ratio of the frozen-weight ex-ante return correlation, with its window printed) and the
same number on SPY-residual returns. When fewer than `min_corr_obs` periods exist, use ex-ante
holdings returns for the correlation edge, not the realised series. Today the realised-series edge
is a check that cannot fire, so it behaves as if it had passed.

### F2 — HIGH — the "largest cluster" is a tie broken by row order; it hides the MU basket

At 0.30 the two largest components both have **n = 6**:

* cluster 0: hack2, revision_flow_v0, pers_revision_flow_leaders, lib_net_raises,
  lib_net_raises_ivw_lead, lib_skill_raises__control → SNOW/OKTA/ABNB/CRWD/CRM
* cluster 1: lib_resid_mom_12_1_large_sealed, lib_qc395…, both qc470…__control,
  mom_12_1_q_trend_lead, disp_short_avoid → **MU/LITE/SNDK/AXTI/TWST**

`sorted(comps, key=(-len, c[0]))` breaks the tie by the first member's position in the ROI rows.
hack2 is listed first, so SNOW wins. The basket in the headline is an artefact of row order.

Across the 36 winners with holdings, MU sits in **19 (53%)**, AMD in 14, SNDK in 13. That is R4's
finding, and it holds. Re-running the module's own `cluster()` on the receipt's books:

| Jaccard | clusters | largest | largest basket | MU in largest |
|---|---:|---:|---|---:|
| 0.15 | 9* | **19 (49%)** | MU 63%, SNDK 58%, STX 47%, TXG 42% | 12 of 19 |
| 0.20 | 15 | 7 | MU, SNDK, AXTI 100% | 7 of 7 |
| 0.30 | 20* | 6 (tie) | SNOW … (row order) | 0 of 6 |

(*The receipt prints 8 and 19. Mine differ by one because the public rows drop `_series`, which loses
the identical-returns edge between the two night books.)

Fix: the headline basket is the most frequent names across **all** non-twin winners (MU 53%, AMD
39%, SNDK 36%), plus the largest component at the *loosest* sensitivity threshold. Where component
sizes tie, print every tied component. Do not let row order choose. The 0.15 → 19-book component is
the one an investor needs to see.

### F3 — HIGH — loser `error_type` on the fleet reads open-position P&L as if it were the loss

For alpaca_fleet the TAIL basis is `unrealized_pl` of **open** positions. The rule treats that number
as the loss:

| book | dollar shortfall since inception | open-position P&L | rule says |
|---|---:|---:|---|
| hack4 | −$19,424 | **−$181** | "RZLV carries 334% of the loss" → sizing_concentration |
| hack6 | −$18,440 | **+$224** | "loss not concentrated" → selection |

The open book explains about 1% of hack4's loss and has the wrong sign for hack6. Neither label rests
on evidence. The loss sits in closed positions and in turnover, which `book_dna` does not read. R4's
operational reading for hack6 (41 odd-lot positions, negative cash on 09-22) is better supported
than "selection". The honest label for both books, from this module, is `not_determinable`.

Fix: a P&L-share rule may fire only when `|tail.total| >= 0.5 x |dollar shortfall|`. Otherwise it
returns `not_determinable` with the coverage ratio printed. `selection` must require positive
evidence, not "no other rule fired while some holdings existed". Today it is the fall-through bucket,
and it is printed as if it were a diagnosis.

### F4 — MEDIUM-HIGH — `timing_exit` divides by the NET; mirror/conviction should be decomposed, not labelled

conviction's thirds: −7.72 / **+4.17** / −8.89 pp. The rule computes −8.89 / −12.44 = 71% ≥ 70% and
returns `timing_exit`. The first third alone is 62% of the net, and the share is only above 70%
because the positive middle third shrinks the denominator. As a share of gross negative it is
8.89 / 16.61 = **54%**. That is not timing.

conviction misses the sizing fallback by 1.2 pp: ABSI is 18.8% against the 20% threshold, on today's
weights.

Neither label answers the question the receipt already has the data for. `lanes.identity_statements`
says mirror and conviction hold the **same 12 names** (Jaccard 1.00). So:

* the **common** shortfall (both behind SPY on the same names) is **selection**;
* the **difference** (mirror −28.3 vs conviction −12.9 = −15.4 pp) is **treatment/sizing**: HRP, the
  cap and the 06-16 → 08-02 two-name state.

R4's "sizing" is right for the mirror − conviction gap, and selection is right for the part they
share. Fix: compute `timing_share` against the gross negative. For any loser inside an identity
group, output a `decomposition` (common vs differential) in place of a single type.

The rule order *is* declared on the receipt (`classify_loser` docstring, and `params` prints every
threshold). It is not printed as an ordered list, though. Add `params.loser_rule_order`.

### F5 — MEDIUM — `kind == "control"` books are counted as strategy bets

Twin detection reads only `books.jsonl kind == "twin"`. `books.jsonl` has 5 `kind: "control"` books,
and 3 of them are among the 39 "non-twin" winners: `lib_qc470…__control`,
`lib_qc470…_lead…__control` and `lib_skill_raises_2026-09-30__control`. Two of these sit inside the
MU cluster and one inside the SNOW cluster. A control counts as evidence about the control, not as a
bet. The correct count is **36 strategy books + 3 controls**. Fix: treat `kind in {"twin",
"control"}` as non-strategy and print the controls on their own line.

### F6 — MEDIUM — `one_name_dependence = true` on 129 books is mostly noise; proposed exact rule

Of the 129, **97 are twins**, 4 are fleet books on the open-P&L basis (F3) and 1 is PC-PAPER. 27 have
|excess| < 0.25 pp (e.g. `lib_disp_short_avoid` at +0.028 pp → WOLF "share 7.735"). 53 have a top-1
"share" above 100%, because the denominator is the net, so the shares explode as the net nears zero.

A single 10%-weight name with ~3% daily vol moves about ±0.7 pp over 6 sessions by chance. The rule
I would ship:

> `one_name_dependence` is computed only when **(a)** `basis == "active_contribution"` (the excess,
> not open P&L), **(b)** `|excess_pp| >= 1.0`, **(c)** `|reconstructed_excess_pp − excess_pp| <= 0.25`.
> The share is **top-1 / Σ same-sign contributions** (bounded 0–1), and the flag is `share > 0.5`.
> Otherwise it is `NOT_COMPUTABLE` with the failing condition named.

Checked on this receipt: (a)+(b) leave **38 books (10 non-twin, 28 twins)** of the 129. The 10
non-twin books: SHADOW_BAYES_v0 (TS), pers_ai_power_global (TER), cards_supports (6857.T),
reviewer_opus (6857.T), lib_frog_in_pan (LITE), lib_qc470…__control (WOLF), lib_margin_mom (AZTA),
lib_book_f_seasonality (WLFC), lib_low_asset_growth (KDK), lib_illiquid (ITG). The reconstruction gap
is small everywhere (median 0.05 pp, p90 0.11 pp), so (c) removes almost nothing today. It is there
to guard tomorrow. The gross-denominator change would also take some of the 8 remaining >100% cases
below the flag. Twins should not print the flag at all.

### F7 — MEDIUM — the EARLY_EVIDENCE gate cannot be reached by any book that is ahead, and the line does not say so

Sub-windows come **from the series** (`np.array_split` over the period index), not from a calendar,
which is correct. `sessions_graded` counts SPY bars between inception and the last mark (a re-served
session is one session, which is also correct). But the only winner with ≥ 21 sessions, **hack2**
(26 sessions, +0.95 pp), has **6** grade rows, so its sub-windows are `NOT_COMPUTABLE`. The night
books have 6 NAV points in 16 sessions. Every other winner has ≤ 6 sessions. "All 362 OBSERVED(n)" is
therefore a property of the data feed, not a verdict, and it will stay that way until the fleet
grader and the night-book NAV are dense. Separately, REPLICATED is reachable through
`fair_twin_excess > 0` by any positive margin, and through a same-rule sibling that need not pass its
own sub-windows. That bar is too low for the rung's name. Fix: say "no winner has a dense ≥ 21-session
series" in the collapse line, and require the sibling to be EARLY_EVIDENCE itself.

### F8 — LOW-MEDIUM — `collapse_factor = 147 / 19` mixes two collapses

The 7.74 multiplies the twin collapse (147 → 39) by the overlap collapse (39 → 19). Print the two
factors separately: 147 → 39 is ×3.8 and 39 → 19 is ×2.05. With F1 it becomes 39 → ~3 effective
(×13). A reader cannot act on the product.

### F9 — LOW-MEDIUM — lane `beta_vs_spy` is printed without a lag check, and it fails one

The lane series in the ROI receipt correlate with SPY at 0.05–0.40 same-day. For balanced-ew-control
the lag-1 correlation is higher (**0.59 vs 0.26**). The same holds for tsmom-overlay (0.58 vs 0.40),
tsmom-6040-control (0.48 vs 0.27), mirror (0.31 vs 0.21) and conviction (0.33 vs 0.25). The
aggressive/balanced/conservative lanes print betas of **0.07 / 0.04 / 0.03**, which is not credible
for equity-bearing lanes. The cause is upstream, in the stamping of `lane_nav_series` (not C3's
code), but C3 prints the beta. Fix: compute corr at lags −1/0/+1 and print `NOT_COMPUTABLE: series
appears lagged` when lag-1 wins. The lane *family* clustering (lane vs lane, same stamping) is
unaffected.

### F10 — INFO — twin count 108 vs R4's 105, and 147 vs 148

108 = 105 `llm_portfolio:twin` + 3 `night_books_twin`. R4 counted only the llm twins. The 148 → 147
change is **PC-PAPER flipping from +0.018 pp to −0.648 pp** between `roi_…T045934Z` and
`roi_…T160824Z`. No other row changed side. Twin identity comes from the registry (`books.jsonl
kind/parent_book_id`) for llm books and from the family suffix plus `graded_against` text for night
books. The night-book parent match is a 40-character name-prefix match, which is fragile but is
correct on this receipt. Apart from F5, no non-twin was counted as a twin or the reverse.

### F11 — INFO — shared-file collateral: clean

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_book_dna.py \
  backend/tests/test_paper_accounts_roi.py backend/tests/test_model_routing.py \
  backend/tests/test_daily_learning_report.py -q
82 passed, 1 warning in 5.00s          (exit 0)

... backend/tests/test_daily_pass.py -q
57 passed in 3.58s                     (exit 0)
```

The C3 hunks in `config.py` are one contiguous `BOOK_DNA_*` block. The other new blocks in the same
diff (Telegram cockpit C6, hyp-lab, query planner C7, PC mandate/sim owner C2) belong to other
builders and are not C3 defects. `test_daily_pass` is green, so no undeclared step from another
builder is breaking it tonight. The `model_routing` and `daily_learning_report` edits are 4–8 lines
each and fall back to a NOT COMPUTED line on a pre-C3 receipt. One gap: no test covers a tie in
cluster size (F2) or a `kind: "control"` book (F5).

### F12 — HIGH (pre-existing, not C3) — the mirror cap hole is real, and there is a second one

Reproduced with `portfolio_intelligence/rules.enforce_position_limits`, cap 0.25 / sector 0.60:

```
{'DKNG':0.5,'SLDP':0.5}             -> {'DKNG':0.5,'SLDP':0.5}        # n x cap = 0.5 < 1: returned unchanged
{'DKNG':0.7,'SLDP':0.3}             -> {'DKNG':0.5,'SLDP':0.5}        # clipped, then refilled past the cap
{'A':.4,'B':.3,'C':.2,'D':.1}, A,B,C='Tech', D='Fin'
                                    -> {'A':.2,'B':.2,'C':.2,'D':.40} # SECOND HOLE: the sector pass
                                                                      # pushes D to 40% > 25% name cap
```

The docstring states "Invariant: output weights sum to 1.0" and "converges when n * cap >= 1.0". It
neither refuses nor warns when that condition fails. The sector pass then redistributes to unfrozen
names *without re-applying the name cap*, so a name outside a capped sector can end up at
`1 − max_sector` = 40%. I did not re-fetch the live positions route. The function reproduces the
builder's 06-16 / 07-14 DKNG 50% / SLDP 50% claim exactly.

**Registered or new?** `book_lanes.yaml` declares `mirror.max_single_name: 0.25`, so a 25% ceiling
is the **registered construction**, and the 50% weights were a deviation from it. The YAML does not
say what happens when the cap cannot be met. Holding the remainder in cash is the reading that
honours the declared number without inventing a new parameter. Refusing the rebalance and keeping
the old weights also honours it, but leaves the lane on stale weights. Either way the config hash
does not move. The change lives in shared code (`rules.py` serves all four reference lanes and
`exit_lane`), so it is `lane-integrity-check` work. conviction declares no cap, so any cap there is
an owner decision.

**Worst case in dollars, mirror today** (NAV $75,525, long-only, Σ|notional|/equity ≈ 1.0):

| state | single-name weight | one name → 0 | one name −50% |
|---|---:|---:|---:|
| now, DKNG | 22.0% | $16,600 | $8,300 |
| declared cap | 25% | $18,900 | $9,400 |
| sector-pass hole (one name outside a 60% sector) | 40% | **$30,200** | $15,100 |
| n × cap < 1 (two priced names) | 50% | **$37,800** | $18,900 |

Not fixed, as instructed.

---

## Investor's question — does this change tomorrow morning?

As shipped, **no.** "19 independent clusters" reads as diversification and nudges the owner toward
comfort. The actionable facts are elsewhere:

1. **Only one book with ≥ 21 sessions is ahead of SPY: hack2, +0.95 pp over 26 sessions.** Every
   website lane, the other four fleet accounts, PC-PAPER and murat_live trail SPY.
2. The 39 short-window winners are ~3 ex-ante bets. The largest is a β ≈ 2–3 memory/semis/momentum
   tilt (MU in 19 of 36) over **6 sessions**. Beta at the ex-ante estimate explains about 40% of the
   median excess (1.63 → 0.97 pp). 33 of 36 stay positive after the beta adjustment, which is still
   OBSERVED(6).
3. The two concrete actions are on the loser side: the mirror cap hole (F12), and hack4/hack6 as an
   operational audit (F3). The receipt cannot diagnose either.

The line I would put at the top of PAPER_ACCOUNTS.md, in place of the current one:

> **1 book with ≥ 21 sessions is ahead of SPY (hack2, +0.95 pp / 26 sessions). The other 146
> "ahead" are 108 control twins, 3 controls and 36 six-session books ≈ 3 ex-ante bets, the largest a
> β≈2–3 memory/semis tilt (MU in 19 of 36). Nothing here is evidence yet.**

## Three things I would have done instead

1. **Count bets by ex-ante return covariance, not name overlap.** Price every book's frozen weights
   over the 120–150 sessions before inception. Report the eigenvalue participation ratio (raw and
   SPY-residual) and cluster on that correlation. Jaccard becomes a *label* for a cluster's basket,
   not the edge that defines it. This needs no new data and works on day 1 of a book, when
   realised-series correlation is impossible.
2. **Lead with the evidence-weighted count.** Stratify "ahead" by sessions graded (≥ 21 / 6–20 / < 6)
   before any clustering. The sharpest single fact in this receipt is that the ≥ 21-session stratum
   has one winner. Clustering six-session books spends precision on the stratum that matters least.
3. **Make loser diagnosis decomposition-first.** Where an identity group exists (mirror/conviction,
   the four-lane risk dial), split each member's shortfall into the group-common part (selection)
   and the member-specific part (treatment). Where a book's dollar loss is not covered by the P&L the
   module can see (fleet closed positions), print `not_determinable` with the coverage ratio. Do not
   fall through to `selection`.

## Score: 64 / 100

Engineering discipline 9/10: refuse-not-absent, receipts never overwritten, thresholds printed,
tests green, shared-file edits small and fallback-safe. The statistical substance is weaker. The
headline cluster count overstates independence by about 6× against ex-ante returns. The headline
basket is a row-order tie-break. Two of the three non-twin loser labels rest on a P&L basis covering
about 1% of the loss. Controls are counted as bets. Fix F1–F5 and this becomes the line the owner
should read first.
