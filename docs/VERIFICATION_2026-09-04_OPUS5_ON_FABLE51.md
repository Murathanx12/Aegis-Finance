# VERIFICATION — Opus 5 re-derives Fable 5.1's S38 review — 2026-09-04

**Who:** Opus 5 as builder, five independent verification agents on
non-overlapping surfaces, plus two hand-checks by the lead session.
**What this answers:** *before building on it, does Fable 5.1's review
(`REVIEW_2026-09-04_FABLE51_VERDICTS.md`) hold?*
**Method:** every load-bearing number was re-derived from the underlying data or
code by an agent that was told the claim and told to attack it. Nothing here is
taken from the review's own working files.
**Licence:** RESEARCH_CLAIM standard for the negatives; nothing here is an alpha
claim.

---

## 0. THE HEADLINE

**The review holds. Its direction is right, its two program-defining findings
are confirmed to the digit, and the plan built on it is sound.** Eleven numbers
reproduced exactly, three reproduced approximately, and **six specific claims
were overstated or mis-attributed**. None of the six changes the roadmap; three
of them change what a builder must do, and one of them changes a conclusion that
was about to be carried forward as a signal.

The single most important correction is §4 below: **the corrected "toxic band is
a long at +37.4%/yr" must not be carried forward.** It is a sub-$5 cell that
flips sign at a $5 price floor.

---

## 1. WHAT REPRODUCED EXACTLY

| claim | Fable | re-derived | note |
|---|---|---|---|
| AAPL 2013-06-20 `ptgsum` vs `ptgsumu` | 19.323 / 541.04 | **19.323 / 541.04** | hand-checked by the lead session; ratio is exactly 28.0 = AAPL's 7:1 (2014) × 4:1 (2020) |
| future reverse split in original `toxic_ge_5` | 74.4% | **74.35%** (n 26,199) | `lt_1_5` 0.09% (270/296,107); `b_3_5` 11.05% |
| original `toxic_ge_5` 1m EW excess vs VW | −35.2%/yr, t −5.79, 172/mo | **−35.18, t −5.79, 172/mo** | 24,450 name-months, 143 months |
| corrected `toxic_ge_5` (PIT) | +37.4%/yr, t +1.94, 7/mo | **+37.44, t 1.94, 7/mo** | 2,093 name-months, 133 months |
| original `b_3_5` | +13.4, t 1.28, 27/mo | **+13.37, t 1.28, 27/mo** | |
| corrected `b_3_5` | −7.0, t −0.67, 46/mo | **−7.01, t −0.67, 46/mo** | |
| original toxic split by `cfacpr` | −13.3 t −1.66 vs −48.9 t −7.15 | **−13.38 t −1.65 vs −48.88 t −7.14** | the lookahead IS the effect |
| re-bucketing census of 26,199 toxic rows | 2,965 / 11,072 / 3,339 / 8,823 | **identical, cell for cell** | full transition matrix reproduced |
| performance-coded delistings 2013-24 | 866, mean `dlret` −24.6% | **866, mean −24.63%** | but see §3 on the code range |
| VW market total return 2020-01-02→2025-05-30 | +96.7% | **+96.67%** | pinned FF vintage, `Mkt-RF + RF` |
| states persistent null p at k=3/4/5 | 1.000 / 1.000 / 1.000 | **1.0000 / 1.0000 / 1.0000** | 368,613 matured rows, 200 draws, 75 s; `lt_1_5` 0.95; observed spread below **all** draws |
| `family_max_p` never called in the v2 driver | asserted | **confirmed** | and the v1 call is degenerate: `null_max` is `json.dumps`-identical to the single-arm null |
| 64 model-null draws ≈ 16 independent | asserted | **confirmed** | 16 seeds × 2 arms × 2 heads; the heads share one trunk, and both arms draw the **same** permutation from `default_rng(seed)` |
| p = 0.0154 is the 1/65 add-one floor | asserted | **confirmed** | observed t 2.639 > null max 2.561 ⇒ zero exceedances ⇒ the floor. A censored bound, not a measurement |

Two hand-checks of the defect's mechanism also reproduced: `ratio_used ×
cfacpr(t)` equals the true PIT ratio to 4 decimal places on AAPL, and lands
within 1% on **92.99%** of all panel rows.

---

## 2. WHAT DID NOT REPRODUCE, AND BY HOW MUCH

| claim | Fable | re-derived | verdict |
|---|---|---|---|
| 66 overlapping windows compounded | +932% | **+949.0%** | approximate; not reproducible under any of four natural anchor/forward conventions (range +914.2% to +949.0%) |
| every-3rd non-overlapping chain | +107% | **+112.2%** | approximate; +106.9% *is* the plain buy-and-hold over the chain's own span, which is likely what was quoted |
| "84% of identifiable round trips closed within one session" | 84% | **60.0%** (hack3/4/6), **54.5%** (all six roles) | **not reproducible from any persisted artefact.** The 84% comes from a 29-row hand-assembled scratchpad file with a `confidence` column (15 `medium`, 1 `low`), several holding-period cells reading `">=1"`, `"0 then 1"`, `"0-1"`, and **two rows that are whole baskets**. Reaching 84% requires expanding those baskets name-by-name — and those were `aat-stop-` protective-stop exits, the one path the re-entry guard **can** see. Folding them into a statistic about the `close_position` blind spot mixes two mechanisms. |
| "median hold 0 sessions on hack3/hack4/hack6" | 0 | pooled **0**, but **hack3's own median is 1.0** | pooled claim true, per-role claim false for hack3 |
| "3 of 64 nulls beat 18.28× (p 0.046)" | 3 draws | **2 draws** | p 0.0462 = 3/65 ⇒ 2 exceedances. Inherited verbatim from `LEARNER_V2_2026-09-03.md:22` |
| Deflated-Sharpe expected max of 44 trials ≈ 0.85 | 0.85 | **not reconstructible** | observed SR ≈ 0.884 checks out, but model-null draws exist for only 2 of 16 arms and their null sds differ (lgbm 0.89 vs encoder 2–3). A Gumbel expected-max from the stored 1m null gives **0.71**. The qualitative conclusion (champion sits at the noise maximum) is solid; the specific 0.85 is not checkable |

**None of these changes a verdict.** The +740% forensic survives its own
imprecision: the log-inflation ratio is **3.123**, so "roughly triples" is right,
and the anchor number is exact. The churn finding survives at 60% instead of
84%; a book that closes 60% of its round trips the same session it opens them is
not testing a 21-session thesis either.

---

## 3. WHAT WAS MIS-ATTRIBUTED (three items a builder would have got wrong)

1. **The delisting code range in the review is wrong.** The verified 866 / −24.63%
   comes from `dlstcd ∈ {500} ∪ [520, 584]`. The review's stated **"400-591"**
   gives n = 1,114 and mean −19.57%, because code 450 (liquidations, n = 216,
   mean −0.7%) dilutes it. A builder following the review's range would have
   produced the right count with the wrong provenance, or the wrong count.

2. **One comment the review calls false is the one that gets it right.**
   `scripts/tracker_ibes_backtest.py:278` — *"Total-return index: dividends in,
   splits out, delisting return included"* — **is** flatly false. But
   `learner/dataset.py:55-57` is the **honest caveat** already: *"CRSP `dsf.ret`
   carries a delisting return only where one is on the daily file… mildly
   generous to dead names."* The review cited it as a place that gets it wrong.
   Verified independently: 1,103 of 1,114 performance delistings have a `dsf`
   bar on `dlstdt` and only **4** have `ret == dlret` (mean `dsf.ret` −9.2% vs
   `dlret` −19.6%), so the substance — `dsf.ret` is not delisting-inclusive — is
   correct; only the citation is misplaced.

3. **The universe claim is REFUTED as characterised, and a re-pull is not
   warranted.** The CRSP daily pull holds **6,894** distinct permnos 2013-24; a
   full `shrcd ∈ {10,11}` ∧ `exchcd ∈ {1,2,3}` screen over the same window gives
   **6,909**. Zero pull permnos fall outside the screen, and 15 screen permnos
   (**0.22%**) are missing. It is a 99.78%-complete **subset**, not a "screened
   superset", and not materially non-common-stock. The word "superset" in the
   pull's own metadata is relative to the 4,796 ever-eligible formation subset.
   B1's "verify or re-pull" reduces to documenting 15 permnos.

Two further internal inconsistencies, noted for the record: claim 9's header
says *REFUTED (void under its own bar)* while its body says *CANNOT DETERMINE* —
the body is right, and p = 1.000 with the observed value below **every**
persistence-preserving draw means the two nulls bracket a confound neither
controls. And "the family correction has never been computed" is true but too
weak: it is **not computable** from any stored draws, because no per-arm null
exists for 11 of the 16 arms at any horizon.

---

## 4. THE ONE CONCLUSION THAT MUST NOT BE CARRIED FORWARD

The corrected `toxic_ge_5` cell reproduces exactly at **+37.44%/yr, t 1.94, 7
names/month** — and it is not a signal:

- **84.1%** of its 2,093 name-months trade under **$5** (median close **$3.08**).
  Restrict to close ≥ $5 and the sign **flips**: **−31.6%/yr, t −1.41**, on 3.6
  names/month. The entire result is earned below $5, where a 10 bps round-trip
  is fiction — a realistic spread on a $3 microcap is 50–200 bps.
- **7 names/month is not a portfolio.** 10 of 143 months are empty, 17 hold ≤ 2
  names, 50 hold ≤ 5. The **median** monthly excess is **−0.86%** against a mean
  of +2.69% — a right-tail cell, not a location shift. Dropping the single best
  month (2020-06, +76% on 7 names) takes it to +28.7%/yr, t 1.66.
- **No era clears t = 2**: +38.3 (t 1.56) / +113.3 (t 1.41) / **+0.7 (t 0.03)
  for 2022-24**.
- **It still carries lookahead, now in the opposite direction.** 27.6% of the
  PIT toxic cell still has a future reverse split, and dropping those rows
  **raises** the estimate to +93.5%/yr, t 2.46. A point estimate that moves 56pp
  on a lookahead filter has an unclean composition.
- **Merging `dlret` will make it worse, not better.** The original toxic band had
  the *lowest* 1m delisting incidence of any band (0.26%) precisely because its
  members were future reverse-*splitters*, i.e. survivors. Under the PIT band,
  toxic delisting incidence rises to **1.79%**, the highest of any band.

So the review's §2 table is arithmetically correct and its natural reading —
"the corrected toxic band is a long" — is wrong. The defensible statement is:
**under a point-in-time ratio, no band premium survives.** That is B1 task 5's
conditional outcome, and the condition is met: `BAND_PRIOR` becomes **hygiene
only** (price floor, coverage floor, unreadable-across-split), and the live
thresholds in the terminal's `alpha/tracker.py` are hygiene-only or re-derived
from the live object. Attended.

A second methodological finding from the same work: **`ratio × cfacpr(t)` is not
a fix.** It agrees with the true PIT ratio on only 93% of rows and, used as a
band, leaves toxic at −20.3%/yr t −2.70 — because `cfacpr(t)` is itself a future
quantity. Any rebuild must read `ibes__ptgsumu`.

---

## 5. WHAT WAS BUILT ON THE VERIFIED FINDINGS (this commit)

- **`learner/benchmark.py`** — the canonical benchmark module. Six benchmarks
  (`vw_market_tr_pinned`, `cash_rf_pinned`, `spy_tr_yf_adjclose`,
  `qqq_tr_yf_adjclose`, `ew_crsp_common_main` / `vw_crsp_common_main`,
  `beta_matched`, `matched`), a closed-vocabulary `resolve()`, provenance stamps
  hashed over the construction, and `compound()` which **refuses** an
  overlapping series with no `force` escape hatch. Reproduces +96.67% exactly.
- **`backend/tests/test_benchmark_canonical.py`** — 18 tests. The gate: any
  receipt in `tracker_backtest/` dated 2026-09-04 or later that quotes a
  market-relative return must carry a valid stamp. The 17 pre-existing receipts
  are exempted by an explicit **named** dict with a per-file reason (a
  date-based exemption would have been a permanently red line), and that list
  may only shrink.
- **`backend/services/backtest.py`** — `^GSPC` retired for SPY with
  `auto_adjust=True`; the previously-dead `tickers=["SPY"]` default is now live;
  the market leg is stamped through `learner.benchmark.declare()`.
- **`backend/BACKTEST_RESULTS.md`** regenerated: **+28.3% net vs +114.8%
  buy-and-hold**, Sharpe 0.432 vs 0.837, sell hit rate **0.0% of 5**. Receipt:
  `signal_engine_backtest_20260904.json`.
- The void pair is now corrected **at the point of use** in all nine documents
  that carried it: `README.md`, `NEGATIVE_RESULTS.md §1`, `docs/CANON.md §7`,
  `docs/KNOWLEDGE/findings.jsonl` (F-001), `docs/KNOWLEDGE/quant-investor-lessons.md`,
  `docs/AEGIS_FINANCE_DOSSIER_2026-08-02.md` (×2),
  `docs/REVIEW_VALIDATION_2026-06-14.md`,
  `docs/postmortems/2026-06-14-consolidation-ship.md`,
  `docs/research/EXTERNAL_BRIEFING_2026-07-30.md`. The review's own withdrawal
  had struck the file *header* while leaving the `+740.0%` **table cell**
  unstruck — a withdrawal by header is invisible to a reader who jumps to the
  table.

### A defect this session created and fixed, worth keeping

The receipt gate returned a **false negative on its own first receipt**.
`signal_engine_backtest_20260904.json` quotes `buy_hold_total_return` and
`buy_hold_sharpe` — market legs whose names contain no market word — and the
first detector regex reported **zero** market fields. The tempting repair was to
widen `validate_stamp` to accept several producer modules; that would have ended
the gate's usefulness. Instead `declare()` keeps **one producer, one validator**
and records `declared_only: True`, so the weaker path is visible rather than
hidden. Pinned by two regression tests. A gate that misses the thing it guards
is worse than no gate, because it is believed.

The exclusion list also caught a genuine false friend: **`screen_BH_FDR` is
Benjamini-Hochberg, not buy-and-hold.**

---

## 6. NEW FINDINGS THE REVIEW DID NOT HAVE

1. **The fleet's entry pass has no deadline gate, so the six books were churning
   post-expiry while the review said they were flat.** The handoff states *"six
   paper accounts liquidate 10:45 ET today; after judging, nothing re-enters
   until B2 §1-3 ship."* The first half is true — plain-UUID venue closes landed
   10:46–10:48 ET. The second half is enforced nowhere: `alpha/exits.py:114`
   gates **exits** on `LIQUIDATE_BY_ET`, and `scripts/run_pass.py` has no
   equivalent gate on **entries**. hack2 opened a PANW short at **11:03:18 ET**
   and the guard liquidated it at **11:03:42 ET** — 24 seconds. hack1 had an
   unfilled `aat-` PANW short (51 shares, ~$16.9k notional) working at 11:15 ET
   in a **SAFE**-tier account whose written mandate says the loop only manages
   exits. `fleet.loop_args()` never emits the `--manage-only` flag that would
   enforce it. The same pattern cost hack1 −$475 on 09-03.
2. **`alpha/exits.py`'s un-profiled 3% stop silently pre-empts a correctly
   profiled venue stop.** `equity.STOP_FRACTION_BY_PROFILE` gives hack3
   (`basket`) 8% and hack4 (`maximum`) 6%, and `protect.ensure` rests those at
   the venue — then `exits.stop_hit` closes at a flat 3% on every 5-minute pass.
   Two stop widths coexist in one book and the tighter, undeclared one always
   wins. The graded receipt says it outright for TNXP: *"venue stop at 8% never
   reached."*
3. **The same 3% is the risk *charge*, in the opposite direction.**
   `equity.stress_charge` and `MAX_LOSS_FRACTION` are un-profiled too, so
   `runner.py:735` sizes hack3 against a 3% worst case while its real stop is
   8% — the per-name worst case is **understated ~2.5×**. The exit defect makes
   positions close too early; the sizing defect makes them too large. Same
   constant, opposite errors.
4. **The re-entry guard fails OPEN.** `runner.py:1136-1138`: any exception in
   `protect.stopped_today` logs a warning and sets `stopped = set()`, so the
   guard is off for that pass even for genuine `aat-stop-` fills.
5. **The +2.5% PEAD take-profit also governs the PAIR**, whose measured edge is
   +0.35% per three sessions — a target roughly **7×** the mechanism it was
   measured on.
6. **Two of five LLM families are unreachable on the authority that trades.**
   `fleet.SECRETS` omits `AAT_FEATHERLESS_API_KEY` **and**
   `AAT_OPENAI_API_KEY`, so Featherless (the documented `BULK_ORDER[0]`
   workhorse, 394 calls locally) and gpt-5-nano relevance extraction both
   silently degrade on Railway. `fleet.env_template()` prints the Featherless
   line for the laptop, which is why it reads as configured.
7. **The torch diagnosis is right and the version is wrong, in a way that
   matters.** Installed is **`torch 2.2.0+cpu`**, not 2.11.0. The RTX 5060 is
   Blackwell **sm_120**, which needs torch ≥ 2.7 / cu128 — so 2.2.0 could not
   drive the GPU even in a CUDA build, and it additionally fails its NumPy 2.x
   array bridge. "Install the CUDA wheel" would not have fixed it.
8. **The churn is not established as a loss.** The only fill-level attribution
   on disk says the opposite for the one book that made money:
   `benchmark_regret_20260903.json` — *"hack4 is the only book with POSITIVE
   realized P&L (+$2,027: NVDA put spread +$1,368, **ABAT churn +$798**, RZLV
   +$296)."* The mechanism defect is real; "the churn lost money" is not
   evidence yet, and B2's regret decomposition is what would settle it.
9. **`state/corpus/` confirmed to the row**: 230,661 observation rows / 292 MB,
   gitignored, and absent from `docs/seed/` which is what the Dockerfile copies
   into `/app/state`. Corpus-dependent brains on Railway read an empty store.
   The `d_catalyst` chain is confirmed by code; the "×810" refusal count could
   not be verified locally (6 occurrences on the laptop) and lives in Railway
   logs.

---

## 7. WHAT REMAINS CANNOT DETERMINE, AND WHAT WOULD DETERMINE IT

| question | why undetermined | what would settle it |
|---|---|---|
| Per-role round-trip statistics before 2026-09-02 | the fleet ledger lives only on the Railway volume; `state/decision_outcomes/` is empty locally | sync the volume, or B2 §5's nightly regret receipt |
| The 2026-08-28 basket cascade (11 of 12 hack3 names stopped 09:36–09:48) | no per-name fill record on the laptop | same |
| The `d_catalyst` ×810 refusal count | Railway logs | `railway logs --service aat-loop-hack4` |
| Whether the states result is real | two nulls bracket it: p = 0.000 on the random-partition null, p = 1.000 on the persistence-preserving null | a null that controls the name path without destroying persistence — B4 |
| Family-adjusted inference over the ~48 learner cells | not computable: no per-arm null exists for 11 of 16 arms | B4 (CPCV / DSR / SPA), then re-run the learner |
| Whether the revision mechanism survives | the pool it was measured in was contaminated; forward power is ~990 months for t = 2 | `rev_top50` over the full PIT hygiene universe with `net_rev_1m` as a second definition — B1 task 4, not paper |

---

## 8. VERDICT ON THE PLAN

`ROADMAP_2026-09-04_PROFIT_ENGINE.md` and its block ordering are **adopted
unchanged**. B1-before-everything is the right call and the verification
strengthens it: the panel defect is real, the ruler defect is real, and both are
upstream of every strategy number the program holds.

Three amendments to B1's task list, all narrowing:

- **B1 §3** "verify the dsf pull covers all shrcd 10/11 … (or re-pull)" →
  **document the 15 missing permnos (0.22%) and move on.** No re-pull.
- **B1 §4** the delisting range is `{500} ∪ [520,584]`, not 400-591; and
  `learner/dataset.py:55-57` is to be *extended*, not corrected.
- **B1 §5** the condition is already met: no band premium survives a
  point-in-time ratio, so `BAND_PRIOR` goes hygiene-only. Do not re-derive
  constants from the corrected toxic cell.

One addition, promoted out of B2 on evidence: **the entry-side deadline gate and
the `--manage-only` enforcement are not "fix train" items (B2 §8), they are
live-money-shaped defects that are firing today.** They belong at the top of B2.
