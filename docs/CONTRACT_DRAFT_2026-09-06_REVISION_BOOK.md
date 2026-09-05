# CONTRACT DRAFT — hack2 revision book (`net_rev_4w`, six overlapping cohorts)

> **DRAFT. NOTHING IS SEALED, ORDERED OR DEPLOYED BY THIS DOCUMENT.**
> **Murat freezes or declines.** No policy hash and no `frozen at` timestamp is
> stamped below — a hash stamped before the final text is a forgery of a
> commitment. No env flag is flipped here; seeding stays attended via the
> `seed-a-lane` discipline. This file changes no code and no fleet mandate.

## SCOREBOARD FIRST

| what | value | receipt |
|---|---|---|
| licence requested | `PRODUCT_EXPERIMENT` | CLAUDE.md 2026-08-23 three-licence table |
| selector | top-50 by `net_rev_4w`, monthly, value-weighted | this doc §2 |
| **`net_rev_4w` book, 10 bps, UNFLOORED** | TW **22.859** vs market **13.182**, excess **+2.53%/yr**, **t 1.038**, 309 months | `backend/data/optimus/weekend_lab_2026-09-06/W9_survivor_books_run40_v0.json` → `cells["net_rev_4w\|high\|10bps"]` |
| same book at 25 bps | TW **9.316**, excess **−0.98%/yr**, **t −0.402** | same receipt, `cells["net_rev_4w\|high\|25bps"]` |
| same book under the tradable floor ($3m/day, ≥$5) | **NOT IN A RECEIPT** | `tradable_floor_usd: null` on every `cells` row |
| cross-section shape | effect **lives in the TOP decile** (d10 +0.562%/mo, d1 −0.232%, d10 does not turn over) | same receipt, `cross_section_shape["net_rev_4w"]` |
| screen strength (matched-loser, not a book) | block t **3.83**, Holm **0.0047** | `docs/BUILD_WEEKEND_LAB_2026-09-06.md` FINDING 3 table |
| family verdict W9 | **CANNOT DETERMINE (underpowered; MDE 8.00%/yr)**, DSR **0.1239** over **307** trials | same receipt, `verdict`, `inference.deflated_sharpe` |

**Read the second and fourth rows together: the entire result is the cost
assumption.** +2.53%/yr at 10 bps becomes −0.98%/yr at 25 bps on 0.975
monthly turnover. This book is a bet that we execute at 10 bps.

## THE HONEST POWER LINE

**The tape says this needs ~36 years of monthly observations to reach t = 2 at
its own Sharpe. We hold 25.7. Forward paper cannot adjudicate the alpha claim —
not this year, not next, not in this decade. This book exists to test holding
discipline and regret, not alpha.**

The receipted `years_needed_for_t2` is **36.27** against **25.67 years
observed**, with `t_observed 1.6824` and `mde_annual_excess_at_t_target
0.08001` — 8.00%/yr is the *smallest* effect the arm could have shown at t = 2
(`W9_survivor_books_run40_v0.json` → `inference.power`). Those figures are
computed on W9's **champion** arm (`target_rev_1m__xs|high|10bps`) restricted
to the tradable universe, per that receipt's `grading_note`; the arm this
contract selects, `net_rev_4w`, is **weaker** (t 1.038 unfloored vs the
champion's 1.682 floored). Its own years-to-t2 is **DERIVED, not in a receipt**:
25.75 yrs × (2 / 1.038)² ≈ **96 years**. The 36-year figure is therefore the
*optimistic* end of the range, quoted for the family this arm belongs to.

**Tail concentration (W9, carried forward).** 54.28% of the excess sits in
**five months** — 2020-01, 1999-11, 2000-05, 1999-12, 2020-11. Remove them and
the book is **+3.128%/yr at t 0.844** (`tail_concentration` block). Era t's are
**2.233 (1999-2007) / 0.705 (2008-2015) / 0.037 (2016-2024)**
(`era_sign_table`) — the last nine years are flat. And **57.97% of the
champion's headline is unbuyable** under the execution floor
(`execution_floor_check.share_of_the_headline_that_is_unbuyable`;
`survives_the_floor: false`).

Nothing above licences the word "edge". A reader who finishes this document
believing this book is an alpha claim has misread it.

## 1. Objective

Maximise terminal wealth net of costs versus **SPY TR**, sourced only from
`learner/benchmark.py` id **`spy_tr_yf_adjclose`** (the one ruler; it REFUSES
offline rather than substituting the pinned market). Personality: balanced.
No leverage, no shorting, no options.

## 2. Selection (exact)

At each monthly formation vintage, over the **tradable universe** —
`learner.evaluate.TRADABLE_DOLLAR_VOL` = **$3,000,000/day** AND **close ≥
$5.00** — rank descending by **`net_rev_4w`** and take the **top 50**,
value-weighted. Both floors are applied to the *selection* universe, not only
at grading (the correction that turned 561× into 36×, build doc claim 4).

*Constant hygiene:* the $5 floor has **no named constant** — it is a literal
at `scripts/weekend_lab_jobs.py:2436` and `:3018`. If this contract freezes,
that literal must become a named constant beside `TRADABLE_DOLLAR_VOL` or the
two will drift apart silently.

## 3. Cohorts, horizon, hold

- **Six overlapping monthly cohorts** (Jegadeesh–Titman calendar time). Each
  month ~1/6 of sleeve capital reforms into that month's top-50.
- **`expected_horizon_sessions` = 126** (≈ 6 months), buy-and-hold within the
  cohort — no intra-cohort rebalancing.
- **`min_normal_hold_sessions` = 42** (≈ 2 months). Before session 42 a close
  needs a typed emergency reason (§4). This is the field the whole experiment
  is actually testing: 60% of the fleet's round trips have finished in the
  session they opened (`alpha/contract.py` header, S39 verification).
- A name may sit in several cohorts at once; that overlap is the signal's own
  persistence and is not deduplicated.
- Proceeds from an early exit **park in SPY**, never idle cash (cash requires a
  thesis), and recycle at the next monthly reform.

## 4. Typed exits — the real vocabulary, quoted

From `alpha/contract.py`, `EMERGENCY_EXIT_REASONS` (legal before the minimum
hold, checked in this order): **`DEADLINE`**, **`EXECUTION_CORRECTION`**,
**`HARD_RISK_LIMIT`**, **`DATA_ERROR`**, **`THESIS_INVALIDATED`**,
**`EXPLICIT_EVENT_STRATEGY_EXIT`**. `NORMAL_EXIT_REASONS` (legal only at or
after session 42): **`HORIZON_SPENT`**, **`PROFIT_TARGET`**,
**`THESIS_EXPIRED`**; plus **`HELD`**. This book declares **no profit target**
(`profit_target_frac = None`), so `PROFIT_TARGET` can never fire on it, and
`EXPLICIT_EVENT_STRATEGY_EXIT` is not applicable — it is an event-book code and
its presence on a hack2 row after a freeze is a bug, not a decision.

## 5. Costs and fill

**10 bps per side on measured traded notional** (headline; 25 bps carried as
the adverse arm, and at 25 bps this book loses — §Scoreboard). Turnover 0.975
monthly, measured, not assumed. Paper: shares-only, DAY limit-or-market at the
regular-session open after the vintage; never `tif=cls` (S32 partial fills),
never `opg` (S36: the paper venue does not fill opg, 13/15).

## 6. The six contract fields, filled

`alpha/contract.py` `REQUIRED_FIELDS` — every one is expressible:

| field | value |
|---|---|
| `expected_horizon_sessions` | **126** |
| `min_normal_hold_sessions` | **42** |
| `thesis_expiry` | per cohort: `contract.sessions_ahead(formation_date, 126)` — derived, never a literal date (fixtures rule) |
| `hard_falsifiers` | (1) the name leaves the top-50 `net_rev_4w` set for two consecutive vintages; (2) the 4-week net revision that admitted it turns negative; (3) a delisting, halt or split makes the sealed price basis unreadable |
| `risk_budget_usd` | notional × stop width, computed by the caller that knows equity. At 6 cohorts × 50 names on a $100k sleeve: ~0.33%/name = **$333 notional**, at the `basket` 8% width = **≈ $27 per name**; worst case at the 100% gross cap is the sleeve, ~**−$44k over a cycle** on the parent drawdown of **−43.6%** (`docs/CONTRACT_DRAFT_2026-09-04_REVISION_6M.md` §6, parent receipt `risk_bounds_at_100pct_gross`) |
| `emergency_exit_reasons` | the six above, verbatim from `EMERGENCY_EXIT_REASONS` |

**The field that is missing is not in `Contract` — it is in `defaults_for`.**
`alpha/contract.defaults_for` branches on `TRACKER_BOOKS = ("hack3","hack4","hack6")`
and falls through to the **event defaults** for everything else: horizon **3**,
min hold **0**, `profit_target_frac` **0.025**. hack2 today takes that branch.
A 126/42 book sealed without adding hack2 to an explicit branch gets a
3-session contract with a +2.5% profit target and holds nothing. Related:
hack2's mandate profile in `alpha/fleet.py:104` is **`aggressive`** = a
**3%** stop (`alpha/engine/equity.STOP_FRACTION_BY_PROFILE`); a 3% stop on a
126-session thesis is the "stop inside the noise is a fee" failure named in
`alpha/contract.py`'s own header. Freezing requires `profile="basket"` (8%) or
an explicit `stop_frac`. **Both are code changes Murat must approve; neither is
made here.**

There is also no **cohort id** field on `Contract`. Six overlapping cohorts of
one book are six different `thesis_expiry` values on positions that share a
`book`. That is expressible (expiry is per-position) but the ledger cannot
`group by` cohort without one; recommend a cohort tag before freeze.

## 7. Licence — what it permits and what it does not

**Requested: `PRODUCT_EXPERIMENT`.** It permits internal simulation and
external **paper** brokerage on a frozen strategy contract stamped before the
first decision. It requires no significance gate, no 24-month floor, no
pre-registration, and it explicitly does **not** relax PIT discipline, cost
realism, immutable policy versions, or the ban on LLM authority over real
capital.

It does **not** permit: any claim that this is alpha; any move toward
`CAPITAL_CANDIDATE` (which needs matured forward evidence, calibration, and
drawdown/ruin bounds); any `RESEARCH_CLAIM` (pre-registration, MDE,
multiplicity control, holdout — and W9's own DSR is **0.1239** over **307**
trials, `WITHIN_SELECTION_NOISE`). Roadmap B9 conditions hack2 on "the best
B1-surviving admission family (**revision only if it survives**)"
(`docs/ROADMAP_2026-09-04_PROFIT_ENGINE.md:330`). **It did not survive as a
market-beater.** This draft therefore asks for hack2 on the discipline
question, not on the surviving-family clause.

## 8. Where this contradicts the 2026-09-04 draft — stated, not slipped

`docs/CONTRACT_DRAFT_2026-09-04_REVISION_6M.md` is the prior draft. It already
carries a DO-NOT-FREEZE box (its arm was refuted on the rebuilt tape). Four
deliberate differences:

1. **Selector.** 09-04 selects on `target_rev_1m`; this draft selects on
   **`net_rev_4w`**. Reason: `net_rev_4w`'s effect **lives in the top decile**
   (`cross_section_shape`), which is the only shape a long top-50 book can
   reach; six of W9's fifteen survivors have their effect in the bottom decile
   and were correctly excluded from a long book.
2. **Admission.** 09-04 admits via **band prior v2** (ratio ∈ [1.5, 5.0),
   close ≥ $2, coverage ≥ 2). This draft admits the **tradable universe only**
   ($3m/day, ≥ $5) with **no band gate**. Reason: the band is an EXCLUSION rule
   on a 21-session clock, dead 2022-24, and stacking it on a 126-session
   revision book mixes two clocks. Consequence stated plainly: the $5 floor is
   *stricter* than the band's $2 hygiene floor, so this book is a smaller,
   more liquid universe than the 09-04 draft's.
3. **Cost headline.** 09-04 headlines **25 bps**; this draft headlines
   **10 bps** because that is the tier at which the receipted `net_rev_4w` cell
   is positive at all. This is the weakest point in the document and is said
   here rather than buried.
4. **Minimum hold.** 09-04 has no minimum-hold floor (only typed falsifiers
   inside a 6-month buy-and-hold); this draft adds **42 sessions** and the
   typed-reason gate, because the discipline question *is* the experiment.

Not contradicted, and carried forward unchanged: SPY parking over cash; no
per-name stop tighter than the profile width; delisted names keep their
delisting return; `upside`/ratio unit discipline; sub-$3m names are marked
unbuyable, never deleted.

## 9. What a freeze would require (checklist — none of it done here)

- [ ] Murat's decision to remap hack2 at all (its live mandate is
      `post_event_drift`, `alpha/fleet.py:104`).
- [ ] `defaults_for` branch for hack2 (126 / 42 / no profit target) + profile
      or `stop_frac` fixed at ≥ 8%.
- [ ] `net_rev_4w` re-run **under the tradable floor** with the era table, DSR,
      MDE and tail concentration on its own series — the row this document had
      to mark NOT IN A RECEIPT.
- [ ] Cohort tag on the ledger row.
- [ ] Policy hash = SHA256 of the frozen text + the admission code paths,
      stamped with a timestamp.
- [ ] `seed-a-lane` run; env flag flipped by Murat; first decision recorded
      before any order.
- [ ] New Alpaca keys minted (S36: finance mirror/arena keys revoked).
