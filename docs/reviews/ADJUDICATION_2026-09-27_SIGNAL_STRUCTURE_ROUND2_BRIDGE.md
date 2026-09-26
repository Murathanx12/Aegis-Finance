# Adjudication — 2026-09-27 03:50 HKT — reviewer on signal structure, round 2, the bridge

Review: `REVIEW_2026-09-27_SIGNAL_STRUCTURE_ROUND2_BRIDGE.md`. Builders' commits: `03376f6a`
(signal structure), `615256bd` (round 2), `d93f6029` (cluster bridge).

| # | finding | verdict → action |
|---|---|---|
| 1 | **"No alpha survives the ETFs" was "no power".** Median alpha SE 0.88%/mo on 32 blocks → MDE 2.46%/mo; a true 12%/yr alpha would clear t ≥ 2 in both windows ~10% of the time; `mom_12_1_q`'s 2024-26 alpha equals its pre-2024 alpha, only the error bar grew. | accepted — the label "MOSTLY SMH/MTUM BETA" and the share column are DELETED; every alpha prints SE + MDE; verdict ∈ {ALPHA_DETECTED, CANNOT_DISTINGUISH, BETA_EXPLAINS}. Memory corrected the same hour. |
| 2 | **The betas are a regime**: MTUM β 1.4 → 0, SMH β 0.4 → 1.0 across windows; hedged with pre-2024 betas, momentum is −1.83%/mo (t −1.0). | accepted — `alpha_after_pre2024_hedge` is the standard decomposition; β stability printed per factor. |
| 3 | **The IWM tilt is the panel's**, not the rules': random controls load 0.7–0.85 on IWM and earn IWM's 7.3%/yr; rules beating the benchmark in both windows: 66 vs SPY, 112 vs IWM, 135 vs the panel's random portfolio. | accepted — `vs_random_panel` and `vs_iwm` beside `vs_spy` on every row; the README says the panel tilts small and "vs SPY" understates every rule by that tilt. |
| 4 | **Clustering on residuals RAISES the bet count** (187 → 212–216) and the count runs 79–216 across ρ cuts. | accepted — the curve over ρ ∈ {0.5…0.9} on active and residual returns is printed; no single "N bets" headline. |
| 5 | **Distance-to-default's "2020" was January 2021**: the factory keys by-year/LOO on the DECISION date, not the hold month; one meme-squeeze month = 77× the rule's lifetime net excess. **This keying touches every LOO verdict printed so far, including the "drop 2025" checks.** | accepted as a DEFECT — re-key on the hold month; recompute the by-year/LOO tables of the receipt of record from the stored series into a `.rekeyed.json` sidecar with the list of verdicts that change; a synthetic test pins the boundary month. |
| 6 | **VAL-01's timing is PIT-safe but its company matching is not** (today's Compustat tickers; 983 dead securities renamed, e.g. `AXTC.1`; the CRSP check matched by ticker and could not see it); value rules return non-cash months after 2026-04-06 where market value is NaN. | accepted — map by the dated CRSP–Compustat link; per-date `n_eligible_names`; a rule REFUSES below k eligible names. |
| 7 | **The bridge's cluster mean hides construction**: within the momentum cluster, members run −18.6% to +37.9% vs SPY; rank persistence 0.82–0.86 by universe size, ≈ 0.06 by filters. | accepted — the two-level read: clusters for "does the mechanism work", paired member − cluster spreads for "does construction matter". |
| 8 | **The strategy** (Murat: "we lack a clear strategy"): Bloomberg book = 10 small/mid names × 10% with a Q3 print inside the window, ranked by predicted move size (the σ63 prior, the one arm with skill) and tilted by the fundamentals ranking, ≤ 2 semis; expected σ ≈ 12% over the contest, expected relative return 0 ± 11%. Murat's money = 80% index + 20% fundamentals sleeve, TE ≈ 4%/yr, stop in σ units. The 2026-10-26 check is the dress rehearsal from 09-28: move-size rank correlation ≥ 0.3, realised factor exposure within ±0.3 of declared, fills vs plan — **the 21-day return is not the test**. | accepted — both frozen tonight as PRODUCT_EXPERIMENT books with twins (`bloomberg_rehearsal_2026-09-27`, `murat_core_satellite_2026-09-27`), entry 09-28; nothing is a claim. |

**Deleted:** the "MOSTLY SMH/MTUM BETA" label. **Deferred:** pooled per-family tests and size/vol/past-return-matched
random twins (ideas 2–3) to the next factory night.

**What this changes for the reader:** tonight's strongest-sounding sentence ("the momentum win is semis
beta") is withdrawn. The defensible sentences are: the 32-block window cannot distinguish a 1%/month
alpha from zero; the panel itself is a small-cap portfolio and the benchmark must say so; and one
month (January 2021) can carry a rule's whole history when the calendar is keyed on the wrong date.
