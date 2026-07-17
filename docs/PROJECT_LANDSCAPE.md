# PROJECT LANDSCAPE — what we've mined, rejected, and what's left

> Written 2026-07-17 (V5 session 1). Human-readable companion to
> `docs/KNOWLEDGE/projects.jsonl` (104 entries — the machine-readable ledger
> injected into every lab cycle). Answers two questions in one read:
> **"what have we looked at?"** and **"is our approach still the right one?"**
>
> Framing (non-negotiable): public projects give us **infrastructure, method,
> and data access — NOT alpha**. Anything genuinely predictive isn't public.
> This ledger exists to make the search TERMINATE, not to justify an endless
> sweep. Rule going forward (CANON §11): every project examined gets a
> projects.jsonl entry in the same commit as the work that examined it.

---

## 1. The approach audit — is our stack outdated?

Verdict per layer, checked against everything in the ledger (2026-07-17):

| Layer | What we run | Verdict |
|---|---|---|
| **Validation spine** | Purged CV + embargo, PSR/DSR/PBO/CPCV, pre-registered forward trials, NEGATIVE_RESULTS, 24-mo skill gate | **AHEAD of every OSS peer surveyed.** Vibe-Trading (21.5k★), qlib, FinRL, TradingAgents — none has purged CV + DSR/PBO + a forward record. FinRL's own authors and QuantConnect's Alpha Streams shutdown independently validate the discipline. Keep. One gap: iid bootstrap on Sharpe CIs should become block bootstrap. |
| **ML stack** | LightGBM + LogisticRegression + SHAP, conformal intervals | **Not outdated — the binding constraint is labels/data, not model tech** (F-006, TRIAL-CRASH-2: retrains "work" and prove nothing; label sparsity). Fancier models (NN/GKX) stay gated on the survivorship-free panel (TRIAL-NN-1). Do not upgrade model tech before data. |
| **Regime/vol** | GJR-GARCH, 3-state HMM, BOCPD, Isolation Forest | Sound but the HMM inference path shares the causal-leakage trap; **jumpmodels (Apache-2.0) is the identified successor** — label-stable, explicitly online. Queued, not urgent. |
| **Portfolio** | riskfolio-lib, PyPortfolioOpt, hand-rolled Marchenko-Pastur | Fine. **skfolio (BSD-3)** is the modern consolidation target — migrate opportunistically (its tested Denoise/Detone could replace our hand-rolled RMT), never big-bang. |
| **Data layer** | yfinance primary + FRED + EDGAR + FMP/Finnhub/Polygon fallbacks, PIT SQLite store | **The weakest layer, and the audit's main finding.** yfinance is a chronic operational liability (401 crumb storms, index-ticker rate limits, T7 survivorship verdict) — every new yfinance dependency is a future incident. FRED has literally never failed in prod. Direction: shrink yfinance surface (this session: treasury yields now fall back to FRED DGS10/DGS3MO/DGS30; next: Alpaca IEX bars as equity_history fallback). FMP quota is now METERED (fmp_budget.py). EODHD $19.99 stays the cheapest validation unblock. |
| **NLP/LLM** | FinBERT + DeepSeek (spend-guarded, firewalled from trade paths) | Right-sized. FinGPT/persona-agents examined and rejected — live arenas (DeepFund, Alpha Arena, LiveTradeBench) show frontier LLMs losing money trading. FPB/FiQA benchmark validation of FinBERT remains a cheap open item. |
| **Lab loop** | rd_loop + hypotheses ratchet + findings.jsonl + (now) projects.jsonl | Sound architecture, independently converged on by RD-Agent. Two identified upgrades from the sweep: **AIDE's solution-tree memory** (branch-from-best, never revisit pruned) and **RD-Agent's admit-only-on-beating-incumbent ratchet**. |
| **Product/UX** | Casual default + tour, tearsheets, two-sided card | The researched-but-unbuilt absorbs (F-017 robo onboarding, F-018 factor lens, F-019 uncertainty display, Kitces reframe, quantile dotplots) are **the highest product leverage available** — mostly presentation work on data we already compute. |

**Bottom line: the approach is not outdated — it is ahead on method and behind
on data breadth + presentation.** The correct moves are data-layer hardening
and UX absorption, not framework adoption. No surveyed framework (qlib,
OpenBB, LEAN, vectorbt, …) would improve validity; several would silently
degrade it (license, PIT control, lookahead ease).

## 2. Where Aegis is genuinely ahead vs behind

**Ahead (the moat — nothing surveyed has ANY of these):**
1. A live pre-registered forward record (7 lanes, day 39, controls included).
2. An experiment registry counting rejects, deflating DSR/PBO against total trials.
3. Published NEGATIVE_RESULTS (§1–§7) + closed-rabbit-hole list.
4. The PIT store (as_of + observed_at, never overwritten) feeding forward IC.
5. The brain/postmortem loop (process memory across sessions).
6. Honest-failure infrastructure: stale-serve disclosure, fail-loud collectors,
   spend/budget guards, verified-state endpoint.

**Behind:**
1. **Data breadth**: no survivorship-free panel (EODHD/WRDS pending), no
   options chains depth, no intl equities. This blocks the entire
   backtest-certification program (T7).
2. **Product polish**: PV-grade factor lens, robo-grade goal framing,
   uncertainty display — all researched (F-017/18/19), none shipped.
3. **Distribution**: zero users, no SEO, no public artifact besides the app.
   (Out of scope for the engine; noted for honesty.)

## 3. The ranked unmined shortlist (from the 2026-07-17 bounded sweep)

Capped at 10. Rank = leverage × free-data buildability × license compatibility.
Everything below it in the sweep was examined-and-passed (entries in the ledger).

| # | Project | What it buys us | Cost |
|---|---|---|---|
| 1 | **Open Source Asset Pricing** (Chen-Zimmermann, GPL code / free data) | 212 cited predictors = a menu of pre-registerable forward-IC trials with published priors; `pit_score_collector` already generalizes | $0 |
| 2 | **JKP Global Factor Data** (MIT code / CC BY-NC data) | Benchmark factor returns — "does our composite add anything?" + citable methodology for the paper | $0 |
| 3 | **WRDS student account** (HKU subscribes; undergrad accounts free) | CRSP delisting returns = the only $0 survivorship-free universe; offline certification only | $0 + Murat's library-portal check |
| 4 | **Kitces probability-of-adjustment framing** | Research-backed reframe of retirement MC away from binary success/failure; pure frontend | $0 |
| 5 | **AIDE solution-tree memory** (MIT) | Upgrades lab hypothesis memory from linear log to pruned tree with ratchet | $0 |
| 6 | **fja05680/sp500 PIT constituents** (MIT) | Free point-in-time S&P membership 1996+ — kills the universe-selection half of survivorship bias | $0 |
| 7 | **Hou-Xue-Zhang q-factors** (free CSVs) | Second independent factor benchmark for the paper | $0 |
| 8 | **Quantile dotplots** (CHI 2018, BSD-3 example) | Lab-validated frequency-framed uncertainty display for casual users | $0 |
| 9 | **Tiingo** (re-examined; $30/mo, personal-use license) | Delisted-coverage fallback ONLY if EODHD phase 2 fails; verify empirically first | $0–300/yr |
| 10 | **Agent Laboratory / AgentRxiv** (MIT) | Cross-run "preprint ledger" pattern for lab cycles | $0 |

**Sweep is closed.** New sweeps require a new gap statement, not curiosity.

## 3b. Sweep #2 (2026-07-18) — investor/firm decision history + long-horizon returns

Gap statement: "historical investing decisions of other people and firms" +
"50-100yr asset-class returns for mandate direction-checks". All verified by
fetching the actual pages; full entries in the ledger. Top finds, in order:

| # | Source | What it buys us | Depth |
|---|---|---|---|
| 1 | **CFTC Commitments of Traders** | 40 years of institutional futures positioning, dual-dated (PIT-gold), free CSVs — drops straight into `pit_score_collector` | 1986+ |
| 2 | **Shiller monthly data** | The only free MONTHLY 150-year series — extends the mandate replay to 1871 (captures 1929) | 1871+ |
| 3 | **Damodaran annual returns** | 7 asset classes, one xls, independent cross-check of our replay | 1928+ |
| 4 | **SEC N-PORT bulk datasets** | Structured monthly fund holdings beyond 13F (bonds/derivatives included), no XML parsing | 2019q4+ |
| 5 | **13D/13G activist stakes** | >5% stake events on EXISTING `_sec_get` plumbing — just a form-type filter | decades |
| 6 | **FINRA short interest** | Bi-monthly short-interest history (2021 regime break flagged) | 2014+ |
| 7 | **SEC fails-to-deliver** | 20+ yrs of squeeze/stress microstructure for the fragility composite | 2009+ (2004 via FOIA) |
| 8 | **CBOE put/call archives** | 24-yr free P/C backfill + forward-scrape path (free daily archive ends 2019-10) | 1995–2019 + fwd |
| 9 | **JST macrohistory** | 150-yr, 18-country return panel — cross-country mandate robustness (CC BY-NC-SA, attribute) | 1870+ |
| 10 | **EDGAR full-text search API** | Keyless filing-text search verified to 2001 — the backbone for the 8-K/guidance text program | 2001+ |

Passed: WhaleWisdom ($300/yr for repackaged 13F), Dataroma (no API, derived
data), ApeWisdom (no history), Motley Fool transcripts (no rights), ICI flows
(terms unverified), MeasuringWorth/BoE (cite-only/superseded), hedge-fund
letter aggregators (link lists), Robintrack (unique but frozen 2018-2020 —
research-only). **Sweep #2 is closed.**

Also produced 2026-07-18: the 73-year mandate direction-check
(`docs/research/LONG_HORIZON_MANDATES_2026-07-18.md`) — mandates behave as
designed in equity crashes; the conservative lane's worst drawdown in 73
years was the 2022 rate shock (duration risk, candidate NEW
short-duration lane); Sharpe flat across the ladder (allocation ≠ alpha);
every mandate spent 3-6 years underwater at least once (the day-39
"too early" calibration now shown on the track-record page).

## 4. Rejected-by-category (never re-test)

- **"Predicts prices/crashes/returns" pitches** — refuted three separate times
  (F-001 timing, F-002/F-006 crash horizons, LPPLS twice). Any project whose
  headline is prediction goes in the ledger as rejected-by-category, untested.
- **LLM-as-trader** — every controlled live arena shows losses (F-009).
- **Backtest-framework adoption as validity upgrade** — T7 makes universe bias
  the binding error; no engine fixes that (vectorbt/backtrader/bt/LEAN class).
- **Copy-trading / follower products** — followers don't profit (Apesteguia
  2020; wikifolio; congress-follower ETFs are beta + story).
- **AGPL / Commons-Clause / no-license code** — never enters this MIT repo
  (OpenBB, Ghostfolio, Fincept, Qbot, pypbo, vectorbt, fatcrash): patterns
  re-implemented, never vendored.

## 5. Session 2026-07-17 operational deltas (recorded here, details in commits)

- **GDELT 429 storm killed at the root**: 1h result cache + failure cooldown in
  `fetch_gdelt_signals` (the warm loop was refetching 3×/hr, 24/7) + retry and
  stale-serve logs demoted to INFO. WARNING now = genuinely no data.
- **^TNX boot failure fixed**: treasury columns backfill from FRED
  DGS10/DGS3MO/DGS30 when yfinance drops them.
- **FMP metered**: `fmp_budget.py` — 240/day ceiling, 40 reserved for the
  congress-IC collector; fallback/ESG callers stop at 200; live 402 fast-fails
  everyone until UTC rollover. Exposed at `/api/health/full` → `fmp_budget`.
  (The 07:30 ET slot died on 402 this morning — scheduling alone provably
  cannot protect an unmetered shared quota.)
- **Close-only MTM lever confirmed fully done**: the cron trigger itself is now
  16:30–19:30 ET weekdays (`pi_hourly_mtm` no longer wakes hourly; skip-checks
  also precede any fetch). RAM plateau check remains a Railway-dashboard glance.
- **Alpaca keys validated live**: paper account ACTIVE ($100k, zero positions,
  created 07-16) and the free IEX daily-bar feed works — seed remains blocked
  on Railway env vars (Murat), keys need rotation after passing through chat.
