# Review: chunks D (strategy library, sealed split) and E (backtest to forward bridge), 2026-09-26

Reviewer: read-only, $0, no LLM. Commits `c4f46332` (D) and `5cbef964` (E). Where a
number below differs between commits, the D receipt is quoted **as committed in
`c4f46332`** (`git show c4f46332:backend/data/optimus/strategy_library/leaderboard_2026-09-26.json`),
because the file at that path has since been overwritten (finding 0).

## RESULTS SCOREBOARD
- Best historical net strategy vs the market: `mom_12_1_q` (hindsight, rule written 2026-09-26). Best DSR 0.21 at 762 cells, below 0.95.
- Best forward paper strategy: none. Every forward book is PENDING, with entry at the 2026-09-28 open.
- Terminal wealth moved: **none**. Real capital: none. Paper P&L: none yet.
- Independent selectors: 9 new `lib_*_sealed` books. MU is in 6 of them and SNDK in 5 (see Q7), so the effective count is about 3.
- **RESULT IMPROVEMENT: NONE.** Both chunks improved **gradeability**. D gave a declared split, threshold refusal and multiplicity printed on the board. E gave forward books with twins and an investigation rule. Chunk E also froze a construction that will grade the wrong thing (items 3 and 5).

## Verdict per chunk
- **D: gradeability yes, terminal wealth no.** The sealed constants in code (`strategy_library.py:621-626`), `register()` refusing threshold variants (`:904`), per-row dev/sealed/LOO/top-5 share/max DD and the noise ceiling are real improvements. The board's own header already says "sealed means declared-before-this-run, NOT unseen". But the board then **sorts on the sealed column**, which turns the holdout into the selection sample (item 2).
- **E: gradeability partly; the construction undermines it.** The twins (ew / sector-ETF / SPY / random-same-band) are right, and the investigation rule was declared before any trade. But the books are frozen once and never re-weighted, so after 21 sessions they are no longer the rule. The expectation column uses the window the rows were selected on. One book is 97.5% in two correlated memory names. The replication is a re-implementation, not an independent engine.

## 0. The receipt moved under the README (found while reviewing, highest priority)
`08628087` (17:04, four minutes after E) re-ran the factory and **overwrote `leaderboard_2026-09-26.json`, `LEADERBOARD.md` and `top10_for_replication_2026-09-26.json` in place**: 762 became 834 cells, 254 became 277 rules, 88/254 became 104/277 beating SPY sealed, and 4 `qc*` rows entered the sealed top-10.

README "Historical backtests" and `docs/BRIDGE.md` still quote 762 / 254 / 88 and cite that same path. `replication_vectorbt_2026-09-26.json` verified the *old* top-10 file. The current one holds `qc372`, `qc623`, `qc395` and `qc470`, which were never replicated. The frozen books' notes say "sealed DSR at n=762".

A judge who clicks the receipt sees different numbers from the sentence that cites it. **Fix:** receipts get a run id in the filename (`leaderboard_2026-09-26T0836.json`), and the README cites a commit hash plus path. A date-named receipt that a second run can overwrite is the mtime family of protocol item 7.

## Answers to the seven attacks

**(1) Is "sealed 2024 to now" sealed?**
No. The split was declared before the ranking, but every rule was written in September 2026 by people who lived through 2024-26. The 02:00 board had printed full-sample numbers, and the board ranks on this window.

The honest name is **"2024-26 selection window (split declared, data seen)"**. Its numbers are in-sample for the ranking, and the DSR says so: the sealed noise ceiling at n=762 is an annual IR of 1.98, and 160.6 pure-noise cells would show IR > 0.5. The sealed top-1 has sealed DSR 0.075, and no sealed row exceeds about 0.17.

The one honest out-of-sample number the receipt already contains is **dev-selected, sealed-evaluated**. I computed it from `c4f46332`:
- **Top-10 chosen on dev only:** mean sealed vs SPY **+4.5 pp CAGR, median −1.6 pp, 5 of 10 beat SPY.** Top-20: +1.7 / −1.6. Top-50: +0.0 / −1.5.
- **Dev-to-sealed rank correlation across 254 rules: Spearman 0.16** (p 0.01). Backtest rank carries a little information about the next window, not much.

A real sealed test needs three things:
- (a) Rule text and parameters hashed and timestamped **before** the window's data exist. That is only the forward books from 2026-09-28, and only if they trade the rule (item 5).
- (b) One pre-declared ranking on dev, with the count of rules tried.
- (c) Power. At the library's typical active σ of about 6.5%/month, 21 monthly blocks give SE ≈ 1.4%/month, so the MDE is about **4%/month** at 80% power. The 32 blocks actually available give SE ≈ 1.15%/month. A truly sealed window of that length can kill a rule; it cannot certify a realistic 0.5%/month edge, and certainly not at DSR n=762.

**(2) Should the sealed top-3 have been frozen?**
Not as the headline. `mom_12_1_liqw` (dev +7.0%, dev vs SPY −6.2 pp, max DD −70.6%, top-5-month share 0.91), `rev_5d` (dev +2.8%, DD −66.5%, share 1.08) and `illiquid` (dev −2.0%, DD −80.7%, share 1.44) are rows whose 2024-26 luck is the whole story. `rev_5d`'s sealed excess is +100 pp in 2025 alone, and `mom_12_1_liqw`'s is +104 pp in seven months of 2026.

Freezing them is harmless as a control. Freezing them **as "the sealed top-10" with a README bullet saying "each of these is a $1M forward book"** teaches the reader that a leaderboard is a slot machine whose top rows get a coin.

Applying dev>0 AND sealed>0 AND top-5 share<0.6 AND max DD>−40% to the D receipt leaves 32 rows. **Only 2 of the 9 new sealed books pass** (`skill_mom`, `low_asset_growth`, plus `mom_12_1_q`, which was already frozen). Seven of the nine fail, including all three of the top-3. My rule is in the last section.

**(3) Is a book with 60% MU a strategy test or a coin flip?**
It is a coin flip. The freeze log reads MU 60.3% and **SNDK 37.2%**, so 97.5% of the book is in two names with 63-day return correlation **0.90**. Daily σ is MU 5.6% and SNDK 8.4% (bars as of 09-21), which gives a book daily σ of about **6.4%** and a monthly σ of about 29%. The expected 21-session relative return is +3.8%.

MU prints 09-30, the third session. The first month of this book is one draw of memory-sector beta plus one earnings print. The fault is not today's bad luck: `_weights` uses `inv_amihud = 1/expm1(amihud)`, which is unbounded. Historically this rule's median effective N is **4.5** over all months and **3.3** sealed, with a median top weight of 52%. Its top name each month was SMCI, NVDA (96% on 2023-09-29), MSTR, APP, PLTR (88% on 2025-05-30), SNDK, then MU. It is "the most-traded momentum story of the month", not liquidity-weighted momentum.

**The freeze should refuse:** max name weight > 15%; effective N < 8; more than 40% of the book in names pairwise-correlated > 0.8; any name > 10% with a scheduled earnings date inside the first 5 sessions, unless the book is an event book. The `__ew` twin of the same 20 names is the actual strategy test and should stay.

**(4) Is the vectorbt replication independent?**
It is the same code run twice, with one real exception. The period returns are recomputed from raw bars without importing `strategy_library`. That is worth something: it would catch an index shift or a wrong fill.

Everything else is shared:
- Holdings and weights come from the factory's file, so selection is never re-run.
- The bars parquet is the same.
- The fill convention and the −30% delisting fill are transcribed.
- The intra-period **no-drift / no-cost constant-weight assumption** is copied (`holdings_path`). For the quarterly `mom_12_1_q` this means free monthly rebalancing that no broker gives.
- Costs are in pandas by the same formula.
- vectorbt's role is a Σw·r on a synthetic price index, and it cannot disagree with itself.

A 1e-8 agreement is the signature of shared conventions. It is not evidence of realism.

What would be independent, in rising cost:
- **(a)** A clean-room `mom_12_1` in about 40 lines that re-selects from raw closes, with drifting weights and costs on actual traded notional. $0, one hour. The observation that matters is the **selection overlap and the net-return gap**, not the correlation.
- **(b)** The same ten sealed series priced from a second vendor's bars (Alpaca daily for the held names).
- **(c)** LEAN in Docker for 2-3 rules, with its own fills and fee model.

Expect (a) to disagree by tens of bps/month on the 11.6x-turnover rows. That disagreement is the information.

**(5) What is `skill_mom`?**
It is the rank-average of `skill_net_raises_90` and 12-1 momentum (`strategy_library.py:1347`). `skill_net_raises_90` counts net target raises in the last 90 days by firms whose resolved raises (≥20, each resolved 63 sessions before the date) beat the market on average (`night_backtest_factory.py:535-547`). That part is point-in-time and correct.

Two problems:
- **"Skill" is measured against the market, not against momentum.** Raises chase winners, so in momentum years most active firms look skilled, and skill partly re-labels the momentum loading.
- **Its edge over its own unskilled twin is one year.** `mom_flow` is the same combination with all raises. Excess by year: skill_mom 2024/25/26 = +34/+53/+11 pp against mom_flow +22/+10/+27. In dev, skill_mom is *worse* (dev vs SPY +4.7 against +6.8). Drop 2025 and the two are the same (≈ +45 against +49 pp summed). CLAUDE.md rule 11 applies: this is a 2025 row.

It may still be the analyst-skill feature's only real use. ANALYST-SKILL-1 was ADOPT at a trivial effect standalone (`9d81b697`), and `skill_raises` alone has sealed vs SPY −1.2 pp in 2025. A skill filter can plausibly work only as a **tie-breaker inside a momentum sort**.

**Run tonight, $0, about 3 minutes of factory time:**
- `skill_mom_k21_40`, the same rule's picks ranked 21-40. This tests whether the ordering within the top is informative or the edge is the covered-momentum universe.
- `unskilled_mom`, with raises by firms **not** in the skilled set plus momentum. This is the direct skill test.
- Print the share of firms flagged skilled per date. If it is > 70%, skill ≈ all raises.

Beta-separating observation: `skill_mom − unskilled_mom` by year. If the gap lives only in 2025 it is not skill. The revision parquet's survivorship caveat (64 of 1,784 dead symbols carry history) inflates every flow row in dev. Print it beside the result.

**(6) Can Murat show the README at a hackathon without being caught?**
Mostly. The HINDSIGHT banner, the random controls, "nothing passes the multiplicity bar" and the old +28% vs +115% history are honest. Three catches remain:
- The receipt path now says 834, not 762 (finding 0).
- "Since 2026-09-28" is written in the past tense on 09-26.
- The top two rows invite "what did it hold?" The answers are 60% MU / 37% SNDK, and a dev CAGR of +2.8%.

**The missing sentence:** *"No forward day has been graded yet. The first expectation-vs-result reading is on 2026-10-26 (21 sessions), and one month per book cannot tell a rule from luck. Choosing the top 10 by pre-2024 results alone would have beaten SPY by +4.5 pp/yr on average in 2024-26 (median −1.6 pp; 5 of 10 beat)."* The last clause is the number that survives a quant in the audience. The +68% does not.

**(7) Which numbers first show "we made X and it correlates to paper"?**
On `docs/BRIDGE.md`, it is the column **"expected rel. to date"** against **"forward relative"**, per book. The first reading is **the close of 2026-10-26** (21 sessions after the 09-28 entry), reported 10-27. At that point n = **19 books with a backtest row, one month each**.

That n is much smaller than it looks:
- Per book, the expected monthly relative return divided by its historical monthly active σ is **0.0-0.34** (`skill_mom` 0.34, `mom_12_1_liqw` 0.25, `mom_12_1_q` 0.23). Reaching 2 SE for a single book needs **34 months** (`skill_mom`) to **66** (`liqw`).
- The books are not independent. **MU is in 6 of the 9 new sealed books and SNDK in 5.** Semiconductor and hardware weight runs from 0.98 (`liqw`) through 0.45 (`skill_mom`) to 0.40 (`resid_mom_12_1_large`). That is my hand-classified list, so treat it as indicative. Effective n is about 3.
- The expectation uses the **sealed** CAGR, which is the selected-on window. `liqw`'s dev-based expectation is **−0.47%/month**, against a sealed expectation of +3.8%.

The first honest "correlates" statement is available **today**, from history: dev-to-sealed Spearman 0.16 over 254 rules. For paper, the first meaningful number is the **pooled** Spearman of expected against forward relative, across chained monthly re-freezes, at about 6 months (≈ 100 book-months, effective ~20). Print both the dev-based and sealed-based expectations, and let the forward data say which predicted better. That comparison is the real result the bridge can produce.

## Five places I think you are wrong

1. **"The only rows good in both windows are `mom_12_1_q` and `skill_mom`"** (README, adjudication row 6).
   - *Wrong:* **53 of 254** rules beat SPY in both dev and sealed. 32 also have top-5 share < 0.6 and DD better than −40%. What is true is that they are the only two in *both top-10 lists*.
   - *Alternative:* say that.
   - *Settles it:* `sum(dev_vs_spy>0 & sealed_vs_spy>0)` on the `c4f46332` receipt, which gives 53.

2. **"Sealed net return vs SPY is the objective"** (session order rule 1 as implemented).
   - *Wrong:* maximising a column you rank on makes it in-sample. The top-10 by sealed has a mean dev vs SPY of **−0.1 pp**. The ranking selected 2024-26 luck.
   - *Alternative:* rank on dev (or on dev DSR), and **report** sealed.
   - *Settles it:* dev-selected top-10 sealed = +4.5 pp mean / −1.6 pp median. The next factory run prints that line on the board.

3. **"`mom_12_1_liqw` is a liquidity-weighted momentum rule worth a forward book."**
   - *Wrong:* its median effective N is 3.3 sealed, and its top name was ≥50% in most sealed months (SMCI, MSTR, APP, PLTR, SNDK, MU). Today it is 97.5% in two names at ρ 0.90.
   - *Alternative:* cap inv-Amihud weights at 10% per name.
   - *Settles it:* re-run with the cap. I predict the sealed advantage collapses toward `mom_12_1` equal-weight (+4.8 pp sealed vs SPY).

4. **"Frozen once, never re-weighted" is a forward test of the rule.**
   - *Wrong on three counts:*
     - The rules rebalance monthly (turnover 2.4x-11.6x/yr), so after 21 sessions the book is a stale basket. The 63/126-day horizons grade September's picks held, not the rule.
     - The picks were computed on **bars as of 2026-09-21** for a 09-28 entry, a decision date the rule never uses.
     - `mom_12_1_q` rebalances Jan/Apr/Jul/Oct only (`rebalance_dates`), so its live state is its 07-31 picks, not a 09-21 selection.
   - *Alternative:* chained freezes on the rule's own decision dates (month-end, entry next open), each a new immutable version under one rule fingerprint.
   - *Settles it:* the 10-30 selection of every monthly rule differs from the frozen basket in most names. Print the overlap.

5. **"vectorbt replication 10/10 AGREE" is an independent check** (commit title, README bullet).
   - *Wrong:* it shares holdings, bars, fill convention, the no-drift assumption and the cost formula. It also verified the top-10 file that `08628087` has since replaced.
   - *Alternative:* call it an "accounting re-implementation". Make the independent check a clean-room re-selection with drifting weights (Q4a).
   - *Settles it:* the selection overlap and the net gap between the clean-room `mom_12_1` and the library's.

## One thing to delete
**Void `lib_mom_12_1_liqw_sealed_2026-09-26` before the 09-28 open.** Append a `VOID_BEFORE_ENTRY: concentration (effN 2.0, MU+SNDK 97.5%, ρ 0.90)` row and do not delete the line. Rule 5 protects forward *failures*, and this book has not traded. Keep its `__ew` twin, which is the strategy. Its first month is a bet on MU's 09-30 print, and whichever way that lands, it will be the most-quoted number on the page.

## Three ideas (cost; the observation that separates edge from beta)
1. **Semis and momentum decomposition of the sealed top-10.** $0, about 30 minutes, no LLM. Regress each sealed monthly series (32 blocks) on SPY, an SMH/SOXX monthly series and the library's own `mom_12_1` equal-weight series. *Separating observation:* the intercept's t after SMH and UMD. If `margin_mom`, `low_dtc_mom` and `resid_mom_12_1_large` lose most of their sealed excess to SMH, the sealed window rewarded a sector, not nine mechanisms. The forward bridge should then report each book against its **sector-ETF twin** first and SPY second.
2. **`skill_mom` against `unskilled_mom` and against its own ranks 21-40** (Q5). $0, about 3 minutes of factory time, 2 rows as controls (not trials). *Separating observation:* the `skill_mom − unskilled_mom` gap by year, excluding 2025. If the gap is zero, the skill filter is a 2025 artefact and the analyst-skill branch stays unfunded.
3. **Rebalance-offset test for `mom_12_1_q`**, the best-DSR row on the board. $0, minutes. Run it at the three quarterly offsets (Jan/Apr/Jul/Oct, Feb/May/Aug/Nov, Mar/Jun/Sep/Dec), with drifting intra-quarter weights. *Separating observation:* its excess over monthly `mom_12_1` is +45 pp in 2023 and +42 pp in 2024 from the same signal. If that advantage lives in one offset, the board's best row is calendar-timing luck plus free rebalancing.

## My freeze rule (for any `lib_*` forward book)
Freeze only if **all** of the following hold, and print every boolean on the freeze log.

**Selection**
1. Selected on **dev**: dev vs SPY > 0 and dev DSR is in the top quartile of the library.
2. Confirmed on sealed: sealed vs SPY > 0.
3. Top-5-month share < 0.6.
4. Max DD > −40%.
5. LOO-worst mean active > 0.
6. Worst breadth cell (k = 10/20/50) beats SPY.
7. At most 2 books per family, and pairwise monthly-return correlation < 0.8 with any already-frozen book. Otherwise freeze it as a twin, not a book.

**Construction**

8. Max name weight ≤ 10% (15% for k ≤ 10).
9. Effective N ≥ 8.
10. No correlated cluster (ρ > 0.8) above 40%.
11. No name above 10% with earnings inside the first 5 sessions.
12. Worst case at $1M printed, with the largest name to zero ≤ $150k.

**Timing**

13. Picks computed on the rule's **own decision date**, with bars ≤ 1 session old.
14. Re-frozen as a chained version at every rebalance of the rule.

**Expectation**

15. "Expected rel. to date" printed from dev *and* from sealed, and the investigation rule keyed to the **dev** expectation.

On the D receipt this passes `mom_12_1_q`, `skill_mom`, `low_asset_growth`, `mom_flow`/`mom_flow_ivw` (one of them), `px_vs_ma200_large`, `chase_raises`, `eap_mom` and `inflection_flow_large`, before the correlation dedupe. It fails 7 of the 9 books frozen today.
