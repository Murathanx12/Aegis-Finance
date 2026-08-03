# AEGIS — TOMORROW'S LIST
*Written 2026-08-02. Companion to `AEGIS_FINANCE_DOSSIER_2026-08-02.md`.*

---

## TONIGHT (30 min, if you have it)

**Run `WRDS_RECON_TONIGHT.py`.** `pip install wrds` then `python WRDS_RECON_TONIGHT.py`. Say YES when it offers to create `~/.pgpass` — that's what makes tomorrow unattended.

It pulls **no data**. It answers three questions we're currently guessing at:
1. True row counts of the three BoardEx tables (we only know our local copies are `LIMIT`-truncated at 500k/1M/1M).
2. Whether you're entitled to **IBES** (analyst coverage counts = the neglect proxy), **OptionMetrics**, **RavenPack**, **Audit Analytics**.
3. The real table names, so tomorrow's pull script doesn't fail on a typo.

Leaves `wrds_recon_report.txt` in Downloads. **That file is the input to everything below.**

If you don't get to it, tomorrow starts with it instead — costs ~20 min.

---

## MURAT'S LIST (things only you can do)

| # | Task | Time | Why it's yours |
|---|---|---|---|
| **M1** | Run the WRDS recon above | 20 min | Needs your credentials + 2FA |
| **M2** | Decide: does the BoardEx re-pull get a time budget tomorrow, or do we defer it? | 2 min | It may be a multi-hour job — see D1 |
| **M3** | Confirm whether HKU's WRDS licence includes **RavenPack** | — | Falls out of M1. If yes, it's the news-novelty filter from Part VIII.5 (Sharpe 1.03→1.43 as a pure filter) |
| **M4** | **Attended decision still open #1:** mirror/conviction concentration control | — | Mandate call, not a code change. The conviction lane currently has *no position cap at all* |
| **M5** | **Attended decision still open #2:** un-park the paper | — | Search closed 08-02. Nothing is blocking drafting now |
| **M6** | Verify TSMOM's first real rebalance fired after the `451ad98` cache fix | 5 min | Open verification item from the last session; was due ~08-03 after 16:30 ET |

---

## CLAUDE'S LIST (I can do these unattended)

### Tier 0 — Confirmed defects, no WRDS needed. Start here.

| # | Task | Est. | Detail |
|---|---|---|---|
| **C1** | **Patch `quantile_return_spread`** | 20 min | `engine/validation/factor_ic.py:135`. `qcut` on an all-tied factor breaks ties **alphabetically** and manufactures a +9.6 bp "spread" out of a constant, reporting `status: "scored"`. Fix: skip dates where `nunique() < n_quantiles`, return `available: False, reason: "degenerate cross-section"`. Then gate `score_forward_ic` on `ic["n_periods"]`, not raw row count, and stop overwriting `n_dates`. **Then re-read every factor result the bench has produced on a sparse signal.** |
| **C2** | **Fix the insider collector + stop fabricating zeros** | 1–2 h | Confirmed: `insider_opp` = 72 obs, 1 distinct value, all 0.0. `insider_cmp` live leg all zero with `degraded: false`. (a) `pit_score_collector` must **not write** when the fetch returns nothing — write an absent marker or skip. (b) `degraded` must include `live_fetch_ok`. (c) add a cross-sectional canary: N consecutive all-identical cross-sections → alarm. |
| **C3** | **Same fix for `smartgrowth_pick`** | 30 min | 40 obs, 1 distinct value (0.1), every date. TRIAL-SMARTGROWTH has accrued zero information since 2026-07-12. Same class as C2. |
| **C4** | **FRED publication-lag map + re-run walk-forward** | 2–3 h | `engine/training/features.py:286` reindexes on the **reference date**, not release date — ~56 leaky features. Add `publication_lag_days` per series in `config.py`, shift before `reindex`. **Then re-run walk-forward.** Expect AUC/Brier to move materially. Worst offender: `RECPROUSM156N` (Chauvet-Piger smoothed recession prob) is **two-sided by construction — a soft label, not a feature**. Cheapest first cut: drop it alone and re-measure. |
| **C5** | **Replace the tautological leak assertions** | 30 min | `market_data_wrapper.py:54-60`. `.loc[:ts]` cannot return an index > ts — the assertion **can never fire**. Replace with one that can: assert the series' *release date* ≤ ts. |
| **C6** | **Fix `multifactor.py` absent-vs-zero** | 30 min | Missing → `0.0` is indistinguishable from a real 0.0, so the dead insider leg still consumes its 1/3 weight. Confirmed live: every payload is `{"insider": 0.0, ...}` — a **2-factor model reported as 3-factor**. Return `None` for absent; drop from the denominator; record per-component `n_live`. |

### Tier 1 — Needs the recon report (M1)

| # | Task | Est. | Blocked on |
|---|---|---|---|
| **D1** | **Write the BoardEx re-pull script**, scoped US-listed + date-bounded, **no row limit**, with row counts logged so truncation stays detectable | 1 h to write; **pull time unknown until M1** | Needs true row counts + real table names |
| **D2** | **BoardEx → CRSP PIT linkage** — `cikcode` → `permno`, or ticker **through `crsp_stocknames` with `namedt`/`nameenddt`**, never a raw current ticker | 2 h | D1 |
| **D3** | **IBES coverage counts** → build the neglect proxy for the quality × neglect interaction | 2 h | IBES entitlement from M1 |
| **D4** | **First check whether neglect×quality already exists** in Chen-Zimmermann's 212 predictors — the SignalDoc snapshot is already on disk at `Aegis module/data/reference/osap_SignalDoc_snap20260726.csv` | 30 min | Nothing — **can start now** |

### Tier 2 — Research protocol (no data needed)

| # | Task | Est. | Why |
|---|---|---|---|
| **E1** | **Compute `std()` of the 179 candidate Sharpes** | 30 min | **The single most valuable number in the archive.** Bailey-LdP's deflation uses the *empirical* cross-sectional σ_SR, not the null. At σ_SR 0.4 the hurdle is Sharpe 1.09; at 0.5 it's 1.37. Determines whether any survivor clears the bar |
| **E2** | **Make the 179 counter a machine artifact** | 2 h | Registry reads **18**, shows **18 adoptions / 0 rejections** — violating CANON §6 in the project's own database. One append-only row per candidate arm; back-fill from NEGATIVE_RESULTS |
| **E3** | **Run `evaluate_candidate` on all four survivors at n=179** | 1 h | Blocked on E2. The paper's central claim ("we deflate against the cumulative count") is currently *described but not executed* |
| **E4** | **Add `P(fire \| H0)` + MDE to every registered decision rule** | 2 h | **TRIAL-001 fires on noise 13–34% of the time and decides 2027-06-10.** Urgent because the date is fixed |
| **E5** | Per-lane inception + `n_obs` on every track-record surface; **suppress annualisation below 126 obs** | 1 h | `comparator.py:108` currently takes a 6.8th-power extrapolation of 37 days — mirror's −22% annualises to −83% |

---

## WHAT I GOT WRONG TODAY — don't act on the earlier version

**F1 (the 13D placebo gate) does NOT reopen the search phase.** I verified the per-seed values from `trial_13dg_harvest.json` and re-ran it:

| Trial | mean | mean×√5 | reported | **seed-level t** |
|---|---:|---:|---:|---:|
| §30 | −1.478 | −3.305 | −3.17 | **−4.06** |
| §31 | −1.332 | −2.978 | −3.02 | **−2.43** |

The √5 mechanism is real — the pooled statistic *is* the per-seed mean scaled by √5. But the audit agent read the *median* seed and stopped. The natural test — "is the mean placebo effect across seeds ≠ 0?" — gives **t = −4.06 for §30, more extreme than the statistic it was meant to correct**, because the seeds *agree* with each other.

**Corrected finding:** the pooling was misspecified and was never pre-registered, so the search closed on an arbitrary choice among three readings that disagree. Worth a line in the paper. **Not grounds to reopen the 13D family.**

---

## THE ONE-LINE SUMMARY

Two live forward clocks (insider, smartgrowth) are measuring nothing and no health surface caught it; the crash model's headline numbers are probably leak-driven; and BoardEx — the data your whole context thesis needs — is on disk but truncated. **C1–C6 are all confirmed defects with known fixes. Start there; the WRDS work is gated on 20 minutes of recon.**
