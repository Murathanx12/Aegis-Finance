# V3 Research Synthesis — Strategy & Architecture

**Date:** 2026-06-20
**Method:** Deep-research workflow (109 agents, 27 sources fetched, 119 claims extracted,
25 adversarially verified 3-vote, 0 refuted) + targeted fetch fill-in for valuation/signal
angles + reconciliation against live `aegis_verified_state` (deploy `0e329e2`).
**Inputs reconciled:** Claude / DeepSeek / Bigdata / ChatGPT research docs pasted by Murat.

---

## 0. TL;DR — what survived verification, what didn't

The four pasted AI docs converge on a roadmap that is **methodologically half-right and
factually half-stale.** The single most important correction is one all four under-weight:

> **A backtest can only KILL a strategy. It can never prove one works.** This is not opinion —
> it is the verified, peer-reviewed consensus (Bailey & Lopez de Prado; Harvey-Liu-Zhu). The
> "compress 25 years of learning into a weekend" framing that DeepSeek and ChatGPT lead with is
> the *exact* trap the literature names: after enough trials a profitable backtest is
> **guaranteed by chance**, and under crowding/mean-reversion an over-optimized backtest predicts
> **negative** out-of-sample returns. Our 24-month forward rule is the only clean evidence we will
> ever get. The deep backtester is worth building — **as a guillotine, not a teacher.**

Aegis is **already past** the gaps DeepSeek/ChatGPT diagnosed: we run 7 individual-name forward
lanes (not sector ETFs), and we already wire PSR/DSR/PBO/CPCV — the precise guards the literature
prescribes. The genuine open gaps are: (a) **data integrity** for single-stock backtests, (b) a
**cross-sectional ranker**, and (c) the **broken crash model** blocking the crisis overlay.

---

## 1. ANGLE 4 — Crisis/valuation fact-check (the numbers the docs asserted)

The Bigdata doc's specific figures were the most quotable and the most wrong. Verified against
primary sources (multpl.com, currentmarketvaluation.com), mid-June 2026:

| Metric | Doc claimed | **Verified actual** | Verdict |
|---|---|---|---|
| Shiller CAPE today | ~42–45x | **41.71** (Jun 18 2026, multpl.com) | ✅ "~42x" right; 44–45x was the *Dec-1999 peak* (44.19), not today |
| Buffett Indicator today | **233%**, 2.1 SD above trend | **219%** ($69.15T/$31.57T, Mar 31 2026); **2.1 SD** / +64.8% above trend | ⚠️ **233% is STALE/overstated by ~14pts**; the 2.1 SD figure is **correct** |
| S&P trailing P/E today | (n/a) | **32.23** (Jun 18 2026) | High but nowhere near the scary numbers |
| 2008 "P/E ~140x" | ~140x | **123.73** (May 2009) — an *earnings-collapse* artifact, not valuation | ⚠️ conflated; directionally real, number wrong |
| 2000 "P/E ~45x" | ~45x | That's **CAPE** (44.19), not trailing P/E | ⚠️ CAPE/P-E conflated |

**Net:** the *qualitative* read is TRUE — by CAPE the market sits a hair below its dot-com record
and the Buffett Indicator is ~2.1 SD rich ("Strongly Overvalued"). But **every precise number in
the docs should be recomputed in-engine, not trusted.** The 233% figure is exactly the kind of
stale stat that discredits a crisis dashboard. **Compute these live from FRED + index data.**

**The n≈2 problem (decisive for the crash project):** there are only ~**2 genuinely endogenous**
modern US equity crashes — **2000 (valuation/tech) and 2008 (credit/leverage)**. 2020 was
**exogenous** (COVID), a different reference class. You **cannot validate a crash *predictor* on
n=2.** Therefore the crisis engine must be a **descriptive distance-to-stress gauge that outputs a
continuous exposure multiplier**, never a binary "crash coming" call. This matches our existing
LPPLS/fragility "descriptive, never-arm" discipline. The IPO-supply thesis belongs here as a
*mechanism* (IPO supply absorbs liquidity + signals euphoria + coincides with insider distribution
→ marginal-buyer exhaustion) feeding the multiplier — not as a trigger.

---

## 2. ANGLE 1 — Backtesting methodology (verified, high-confidence)

All claims below verified 3-0 against primary papers.

- **Backtest = falsifier only.** "A backtest is not an experiment... it does not prove anything"
  (Lopez de Prado). One that doesn't report **N (number of trials)** is "worthless regardless of
  reported performance" (Bailey & LdP). → The 2000-present engine must **log N** for every
  candidate it searches.
- **Tuning on the backtest = manufacturing overfitting.** "The purpose of a backtest is to discard
  bad models, not improve them." → **`lab/rd_loop` must not iterate parameters against the
  historical record.** That converts history into a tuning set and produces false discoveries.
- **Overfit ⇒ negative OOS, not zero.** Under memory/crowding, "good backtest performance is an
  indicator of negative future results" (AMS Notices 2014). Stronger than the usual warning.
- **DSR** deflates an observed Sharpe by 5 inputs: skew, kurtosis, sample length T, variance of
  SRs tested, and **N**. Residual challenge: estimating *effective* N under correlated configs
  (LdP uses ONC/hierarchical clustering) — we already track effective-N.
- **MinBTL:** with ~5y of data, >~45 independent configs almost guarantees a skill-less strategy
  showing in-sample Sharpe ~1, OOS Sharpe 0. Even ~26 years caps legitimate independent configs
  far below an unconstrained ML search.
- **t > 3.0, not 2.0.** Harvey-Liu-Zhu: with **316+ cataloged factors**, p<0.05 is hopelessly
  inadequate; a new factor needs **t > ~3.0**. → Any new thematic/selection signal must clear
  t>3.0 forward, not t>2.0.
- **PBO via CSCV/CPCV** is the right overfitting metric — **but it is blind to lookahead, data
  leakage, and regime shift.** Those need PIT discipline + purged/embargoed CV separately.

**Implication:** our methodology stack is *already correct*. The risk is not the framework — it's
**feeding it dirty data** (next section).

---

## 3. The actual gate: DATA INTEGRITY (under-weighted by 3 of 4 docs)

Going ETF→single-stock, the backtest is only as honest as its data, and **free yfinance is poison
for sizing-grade single-stock backtests**:

1. **Survivorship bias** — yfinance has no delisted tickers. Our own **T7 audit already proved
   this** (1/20 delisted names usable → no survivorship-free universe buildable on free data).
2. **Restated, not point-in-time, fundamentals** — yfinance serves *today's* restated financials,
   not what was knowable on the date. This manufactures gorgeous fake alpha (the Compustat trap).

**Verdict:** until clean data exists, **every single-stock backtest is directional-only, never
sizing-grade.** This is the real gate on the whole plan. Options:
- **Free/directional:** yfinance — fine for falsification *direction* only, flagged loudly.
- **Affordable clean (recommended if we go sizing-grade):** **Sharadar (Nasdaq Data Link)** —
  delisted-inclusive prices + PIT as-reported fundamentals + PIT index membership, ~$ low-hundreds.
  Tiingo and Norgate are alternatives. CRSP/Compustat are institutional-priced; skip.
- **Qlib's built-in PIT DB** (released Mar 2022) is the best *open-source reference design* for how
  to store PIT data leak-free — borrow the schema, not the framework.

---

## 4. ANGLE 2 — Open-source tooling verdicts (adopt / learn / skip)

Star counts verified mid-June 2026 where a primary repo was fetched.

| Tool | Stars / status | Verdict for Aegis | Why |
|---|---|---|---|
| **Microsoft Qlib** | ~44.8k, MIT, v0.9.7 (Aug 2025) | **LEARN-FROM (high value)** | Copy Alpha158/Alpha360 **factor formulas** as a feature menu; borrow the **PIT DB schema**. *Skip the framework* — A-share origin, `.bin` format, adopting it means rebuilding our pipeline around its abstractions. US data needs user feeds anyway. |
| **NautilusTrader** | ~24k, LGPL-3, Rust core, bi-weekly | **LEARN-FROM (later bridge)** | Research-to-live *code/semantic* parity is the gold standard if we ever go live. NOTE: parity is code-level, **not** a guarantee backtest results = live results. We're paper-only → reference, not adopt now. |
| **zipline-reloaded** | maintained (Stefan Jansen) | **BORROW THE CONCEPT** | The **Pipeline API** (rank a universe → top-N) is exactly our missing cross-sectional ranker. Reimplement the *pattern* inside our own loop; don't take the bundle system. Pairs with the ML4T/alphalens/pyfolio lineage we already use. |
| **OpenBB** | data platform, MIT | **OPTIONAL DATA ADAPTER** | "Connect once, consume everywhere" data layer — **not** a backtester or optimizer. Fine for ad-hoc exploratory pulls. **Never backtest through its live calls** (no PIT control; most "40+ providers" need their own, often paid, keys). |
| **Tauric TradingAgents / paperclip** | TradingAgents primary repo verified | **SKIP as allocator** | An LLM deciding trades on historical data **has read the news archive** — its "beat buy-and-hold on AAPL" chart is a lookahead tell. Our LLM-firewall is correct. Usable only as an *analysis-memo generator a human reads*, never as an allocator. Agent orchestration is not our bottleneck. |
| **Riskfolio-Lib** | active | **ADOPT (incremental)** | Stronger than PyPortfolioOpt for **cross-asset** CVaR / risk-parity / hierarchical budgeting. We already have riskfolio-lib installed — lean on it for the regime rotator. |
| **alphalens-reloaded** | maintained | **ADOPT (the bench)** | Information-coefficient analysis — the bench every signal must pass *before* it earns a lane. This is the gate for the whole "psychohistory" thesis. (We already compute forward-IC; alphalens formalizes it.) |
| **mlfinlab** | reference | **LEARN-FROM** | Triple-barrier, meta-labeling, frac-diff, CPCV. We half-use it; the CPCV lineage backs our guard. Reference-only (license/maintenance). |
| **quantstats / pyfolio-reloaded** | maintained | **ADOPT (reporting)** | Tearsheets for the lanes. Cheap win. |
| **edgartools** | active | **ADOPT (alt-data)** | Cleanest EDGAR lib; expand past 13F into 8-K/10-K full text, risk-factor diffs, guidance-language mining. (Note: our `edgartools` path has hung before — keep the hang-safe wrapper.) |
| **hmmlearn** | maintained | **ALREADY HAVE** | HMM regime classification (bull/bear/volatile/crisis) conditioning the rotator. |
| LEAN / vectorbt / backtrader / bt | — | **SKIP as source-of-truth** | LEAN: C#, cloud-coupled. vectorbt: vectorized = easy lookahead (param-sweep only). backtrader/bt: fine references but our own PIT-safe event loop **stays the source of truth** — that discipline *is* the moat. `bt` is acceptable for quick multi-asset monthly-rebalance prototyping. |

**One-line doctrine:** *Keep our own event loop. Borrow factor formulas (Qlib), the ranking
pattern (zipline Pipeline), the IC bench (alphalens), and cross-asset optimization (Riskfolio).
Firewall LLMs out of allocation. Pay for clean data if and when we go sizing-grade.*

---

## 5. ANGLE 3 — Which signals actually predict (ranked by verified evidence)

The unifying truth (McLean & Pontiff 2016, *Journal of Finance*): signals don't fail because
they're fake — they **shrink because they get crowded**. Anomaly returns decay **~58%
post-publication** (~26% even out-of-sample pre-publication). Almost nothing public goes to zero,
but the edge erodes. **Track crowding as a variable.**

| Signal | Evidence | Aegis status |
|---|---|---|
| **Analyst REVISIONS (not levels)** | **STRONG.** Mill Street 19y global: top-vs-bottom decile **+7.6%/yr**, monthly **IC 0.23, t=4.9 (p<0.001)**, 83% directional persistence. **Levels/ratings are near-useless** (sell-side ~95% non-sell — already priced). | ✅ **T10 already built revisions momentum** — validated as the right choice. |
| **Credit spreads (HY OAS)** | **STRONG macro.** Widening leads equity drawdowns more reliably than most equity-internal signals. Free from FRED (we already load `hy_oas`, `ig_oas`). | Core input to rotator + crisis multiplier. |
| **Capex guidance / supply-chain / backlog lead-lag** | **STRONG & causal — this is Murat's demonstrated edge.** Capex/backlog lead supplier revenue 1–3 quarters (the Micron/Marvell HBM read). Defensible because structural, not a correlation that arbitrages away on publication. | Build: 2–3 *first-principles* causal chains (semis→tech, credit→equity, copper/oil→industrials), not a 500-node graph. |
| **Insider transactions** | Moderate; cluster-buys carry signal. | ✅ **T9 wired** (now SEC-rate-limited after the prod-403 fix). IC clock accrues forward. |
| **13F flows** | **WEAK/SLOW.** 45-day lag, quarterly, decaying. | Confirmer only — never a fast signal. |
| **Options put/call & dealer gamma** | Real concept; best feeds paid. | Crisis-engine input, later. |
| **CFTC COT positioning** | Positioning *extremes* for contrarian/regime. Free. | Optional regime input. |
| **Geopolitical (GPR index)** | **WEAK for returns** (reactions counterintuitive — the Iran example). | Crisis-engine **volatility** input only, never alpha. |
| **Google/social attention (LunarCrush)** | Real for retail-driven/crypto names, noisy for large caps. | We're connected; niche use. |

**Multi-factor (T8)** = z-score(momentum + insider + revisions) — already snapshotted forward.
Add quality (Piotroski) **once a hang-safe fundamentals path exists**.

---

## 6. ANGLE 5 — Small-account realism (the hard truth)

- **"50% annual on $10k" is retail-blowup framing, not a target.** The only way to reach it is
  concentration, and on a small account with no income buffer a single −50% name ends the
  experiment. **Replace the goal with: measurable edge over the correct benchmark, with drawdowns
  you survive.**
- **What credible factor strategies actually deliver:** Piotroski F-Score showed ~**13.4%/yr**
  outperformance for high-score names (1976–96), best in small-caps — but that's largely in-sample
  and subject to the ~58% post-publication decay above. Realistic *sustainable* factor edge is
  **mid-single to low-double-digit excess**, not 35–50%. Your 100% year was a **concentrated
  discretionary thematic bet — n=1, statistically indistinguishable from luck until measured
  forward.** That's precisely what the **conviction lane** exists to test.
- **The benchmark must be right:** not just SPY, but **Fama-French factors + our equal-weight
  control** (`balanced-ew-control`, already live), so we separate beta from alpha. DSR + effective-N
  is what tells us whether any number is real or a multiple-testing artifact.
- **Cross-asset / bonds (Murat's bonds ask, reframed):** don't hunt a bond strategy that beats SPY
  outright — equities win long-run; **bonds win *regimes*** (TLT +~33% in 2008 while SPY −37%;
  *both* crushed in 2022's rate shock). The robust small-account play is a **cross-asset regime
  rotator** (equities / long-duration / credit / gold / cash) where bonds supply convexity exactly
  in the regimes the fragility engine flags. Risk-parity/all-weather logic, more survivable than
  equity-only stock-picking. Build with **Riskfolio-Lib + FRED curve + ETF proxies
  (TLT/IEF/SHY/LQD/HYG/TIP/AGG)** — no exotic bond data needed for a paper lane.

---

## 7. V3 architecture (the whole loop)

```
                    PIT DATA LAYER
   prices (delisted-incl) · PIT fundamentals · macro/FRED
            · 13F flows · IPO supply · insider txns
                          │
          ┌───────────────┴────────────────┐
          ▼                                 ▼
  FALSIFICATION (offline)          FORWARD EVIDENCE (online)
  backtest 2000 → now              7 paper lanes, real-time
   → candidate rules                 ├ conservative / balanced / aggressive
   → DSR + effective-N + t>3.0       ├ balanced-ew-control   = CONTROL
   → 2000 / 2008 / 2022 guillotine   ├ conservative-atr      = exit overlay
          │                          ├ mirror (your book)
   survivors ONLY ──────────────►    └ conviction (your theses)  ← LOG DECISIONS
   may graduate                              │
                          ┌───────────────────┘
                          ▼
            FORWARD-IC / Deflated Sharpe  (24-mo window)
            ← the ONLY thing that may claim "skill"
                          ▲
          CRISIS / FRAGILITY OVERLAY (continuous multiplier)
        valuation·breadth·credit·liquidity·IPO/insider·sentiment
                          │
  firewall:  backtest can only KILL  ·  forward can only PROVE
             LLM never touches the allocation decision
```

---

## 8. Roadmap — sequenced for Claude Code (2–3 tasks/session, schema-first)

**Session A — Repo audit (in-IDE).** One `AUDIT.md`: real test coverage, current lane configs,
every place ETF-level assumptions are baked in, every path where lookahead could enter the
single-stock flow. (Done in-IDE where it reads all files — not from any AI's recollection.)

**Session B — Data integrity (THE GATE).** Decide clean-vs-free (recommendation: **Sharadar** if
going sizing-grade; else yfinance flagged directional-only). Implement delisted-inclusive prices +
PIT fundamentals into the PIT store with a **survivorship test that FAILS LOUDLY.** Schema before
ingestion. Borrow Qlib's PIT DB design.

**Session C — Cross-sectional ranker.** Implement the zipline-Pipeline pattern
(universe → rank → top-N) inside our own loop, feeding the existing portfolio constructor +
Riskfolio. Register as a **backtest candidate only**; run through DSR + effective-N + the
2008/2022 guillotine before it touches any forward lane. Wire alphalens forward-IC as the gate.

**Session D — Crisis/fragility engine (descriptive).** Recompute CAPE / Buffett / HY-OAS / breadth
**in-engine from FRED** (never trust pasted numbers). Output a **continuous exposure multiplier**
into all forward lanes. Encode IPO-supply as a mechanism input. Never a binary call (n≈2).
Unblock prerequisite: **retrain `crash_model.pkl`** (feature mismatch 67 vs 30 — backlog M3) so the
overlay leaves `model_not_deployed`.

**Session E — Cross-asset regime rotator (new lane).** Riskfolio-Lib + FRED curve + ETF proxies +
hmmlearn regime. Register as candidate → guillotine → forward lane.

**Steady state:** every idea enters as a backtest candidate → guillotine + DSR/t>3.0 → survivors
graduate to a forward lane → forward-IC is the *only* thing that promotes to real conviction. The
crisis overlay scales exposure continuously across all lanes.

**Highest-leverage immediate move (Murat's standing call):** **log conviction decisions into the
empty conviction lane** — it's the only forward test of the stock-picking edge, and it accrues
nothing until decisions are logged.

---

## 9. Caveats / provenance

- Angle-1 & Angle-2 claims: 3-0 adversarially verified against primary papers (Bailey, Lopez de
  Prado, Harvey-Liu-Zhu) and primary GitHub repos.
- Angle-4 numbers: directly fetched from multpl.com / currentmarketvaluation.com mid-June 2026 —
  **time-sensitive, recompute in-engine.**
- Angle-3 revisions / Angle-5 Piotroski: single-source primary/blog fetches — directionally
  reliable, not triple-verified. McLean-Pontiff decay figure is canonical (JF 2016) cited from
  knowledge (PDF was binary-unreadable).
- GitHub stars drift; "actively maintained" for Qlib rests on release recency, not commit-log.
