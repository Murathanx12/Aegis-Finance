# Deep Research — Decision Document (2026-06-14)

> Two adversarially-verified `deep-research` runs commissioned 2026-06-14 to answer:
> *which crash/market-top signals, forward-testing guards, Optimus designs,
> competitive moves, and smart-money signals should Aegis build next* — handed off
> for implementation. **This file separates VERIFIED findings (adversarial 2-of-3
> vote, primary sources) from UNVERIFIED context (four LLM drafts in
> `~/Downloads/reseach.txt`, useful framing, NOT load-bearing).** Nothing here is a
> skill claim; it is a literature/architecture map with honest confidence levels.
>
> Provenance: Run 1 (Sections 1 + DSR) — 24 sources, 105 claims, 12 confirmed / 13
> killed (≈half the kills were API-rate-limit *abstentions*, not genuine refutations
> — recorded as "unverified," not "false"). Run 2 (Sections 3–5) — 23 sources, 98
> claims, **24 confirmed / 1 refuted**, clean. The project's identity is honest
> measurement, so the research is reported the same way: what verified, what didn't,
> and what was refuted.

---

## How to read confidence

- **VERIFIED (high)** — primary source, 3-0 or 2-1 adversarial vote. Safe to build on.
- **VERIFIED-with-caveat** — confirmed but the source flags an in-sample / single-source / time-sensitivity limit. Build, but measure forward before claiming.
- **REFUTED** — adversarially killed. **Do not cite or build as if true.**
- **UNVERIFIED** — fetched but rate-limited out, or only in the LLM drafts. Open; needs a follow-up pass before assertion.

---

# SECTION 1 — Crash / Bubble / Market-Top Detection (VERIFIED CORE)

## 1.1 LPPLS — a descriptive bubble flag, NOT a forecaster

**VERIFIED (high, 3-0).** The Log-Periodic Power Law Singularity model captures two
empirical signatures of a speculative regime: (1) transient *faster-than-exponential*
(super-exponential) price growth toward a finite critical crash-time, and (2)
*accelerating log-periodic oscillations*. Standard form
`ln p(t) = A + B(t_c−t)^m + C(t_c−t)^m·cos(ω ln(t_c−t)+φ)`.
*Sources: Shu & Song 2024 (WIREs Comp. Stats) https://wires.onlinelibrary.wiley.com/doi/abs/10.1002/wics.1649 ; Zhang/Zhang/Sornette PLOS One https://pmc.ncbi.nlm.nih.gov/articles/PMC5091919/*

**VERIFIED (high, 3-0).** Documented honest limitations (Sornette is a co-author of the
source): (a) OLS/MLE calibration is outlier-vulnerable → Sornette et al. adopt
**quantile regression** for robustness; (b) aggregating many fluctuating, often
*conflicting* LPPLS signals into a single actionable bubble-burst decision "remains a
challenge" (unsolved).

**VERIFIED (high, 2-1).** Replicable case study: positive LPPLS confidence clusters
formed Aug 2020–Jan 2022 on the S&P 500, peaking at **26.4% on Nov 30, 2021** —
essentially *coincident* with the early-Jan-2022 top (almost no lead time).

**🚩 REFUTED (0-3).** The claim that quantile-regression LPPLS provides **measurable
predictive ability** around actual burst/rally times was *unanimously refuted* — even by
the Sornette-favorable source. **Build directive: LPPLS ships as a descriptive
bubble/regime flag gated against a measured baseline, NEVER as an early-warning
forecaster, and never wired to arm a lane, until a leakage-safe walk-forward OOS number
(Brier + calibration by horizon) says it has skill.**

## 1.2 Macro / recession lane — labor-market indicators beat Sahm

**VERIFIED (high, 3-0).** The Richmond Fed **SOS indicator** (26-week MA of the insured
unemployment rate rising >0.2pp above its prior-52-week minimum) caught **all 7
recessions since 1971 with ZERO false positives (1971–2024)**, vs the Sahm rule's **two
false positives (2003, 2024)**. It leads Sahm: signals **2.3 months** after NBER onset
vs Sahm's 3.4; reaches 100% signaling probability at **5 months vs Sahm's 8**. Data
(insured unemployment, FRED `IURSA`) is free.
*Source: Richmond Fed EB 25-07 https://www.richmondfed.org/publications/research/economic_brief/2025/eb_25-07*

**VERIFIED (high, 3-0).** Sahm's mixed record: a 2024 paper finds it only becomes useful
~4 months *after* a recession starts; ≥4 false alarms since 1950.

**VERIFIED-with-caveat (2-1 / 2-0, IN-SAMPLE only).** Michaillat's
anticipation-precision-frontier ensemble detected all 15 US recessions 1929–2021, zero
false positives, 2.1 months after onset (std 1.8). **These are training-period results,
not forward skill** — validate walk-forward before adopting.
*Source: arXiv 2506.09664*

**The honest through-line:** even the best macro recession flags are
**coincident-to-lagging, not leading.** Measure and display them by *lag-to-onset*, never
as foresight.

---

# SECTION 2 — Forward-Testing Rigor (overfitting sub-topic VERIFIED)

**VERIFIED (high, 3-0).** The **Deflated Sharpe Ratio** (Bailey & López de Prado) tests
whether an observed Sharpe is significant after correcting for (a) selection bias across
many trials and (b) non-normal returns — using trial count N, variance of trial Sharpes,
sample length, skewness, kurtosis.
*Source: SSRN 2460551 https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551*

**VERIFIED (high, 2-0).** The **False Strategy Theorem**: the expected *maximum* Sharpe
under the null of zero skill grows with the number of independent trials N (closed form
using Euler-Mascheroni γ≈0.5772 and the inverse-normal CDF). More lanes/backtests
automatically inflate the best observed Sharpe even at zero true skill.

> **The effective-N gap (load-bearing for Aegis).** DSR's N assumes *independent* trials.
> Aegis's lanes (conservative/balanced/aggressive/ew-control) are *correlated*, so raw
> trial count overstates independence and makes DSR too lenient. → **Ticket 2.**

**UNVERIFIED (rate-limited abstentions in Run 1, NOT refuted):** slippage definitions,
LEAN's `NullSlippageModel` default, CSCV/PBO mechanics, the "billions of strategies"
multiple-testing framing. Real and worth a follow-up pass; do not assert as confirmed.

---

# SECTION 3 — Optimus Brain / Hindsight Firewall (VERIFIED, Run 2)

## 3.1 Agent-memory architectures (citable patterns)

**VERIFIED (high, 3-0).** **Hindsight** (arXiv 2512.12818, Latimer et al., Dec 2025)
organizes agent memory into **four logical networks** — world facts, agent experiences,
synthesized entity summaries, evolving beliefs — governed by **three operations**:
*retain* (add), *recall* (access), *reflect* (update traceably / produce answers). It
explicitly **separates evidence from inference** with traceable, explainable updates.
The fact-vs-belief split + traceable Reflect map directly onto a provenance-gated
firewall. *(Note: FOUR networks, THREE operations — do not conflate.)*

**VERIFIED (high, 3-0).** **FinMem** (arXiv 2311.13743) = three modules (Profiling,
layered/hierarchical Memory, Decision-making) with an "adjustable cognitive span." A
layered postmortem/rationale/registry corpus with differentiated retention timescales is
an established pattern.

**VERIFIED (high, 3-0).** **TradingAgents** (arXiv 2412.20138) = multi-agent LLM debate
(analyst roles, Bull/Bear researchers, risk team) simulating a trading firm. **Caution:**
its headline Sharpes (8.21 AAPL, 6.39 GOOGL, 5.60 AMZN) come from a **<3-month window
(Jan 1–Mar 29 2024)** the authors themselves flag as overfitting-prone. **REFUTED (1-2):**
the separate ~23–27% cumulative-return figure — **do not cite it.** Architecture real;
performance numbers are a hindsight cautionary tale.

## 3.2 The hindsight firewall is empirically necessary (the core Section 3 finding)

**VERIFIED (high, 3-0).** LLM financial agents exhibit a **"profit mirage"**: dazzling
backtested returns evaporate once the test period passes the model's knowledge cutoff,
because an LLM that already knows market history leaks realized outcomes into
"forecasts." Quantified across four dimensions; FinLake-Bench released.
*Source: Profit Mirage, arXiv 2510.07920 (Li et al., Oct 2025).*

**VERIFIED (high, 3-0).** Lookahead bias is **measured and removable**: with Llama-3.3,
memorization amplifies apparent predictive power by **~37%** of the standalone effect;
run genuinely out-of-sample (Llama-2, Sep 2023–Dec 2024) the leakage interaction becomes
statistically insignificant (one-sided bootstrap **p=0.033**). Forecasting widely-reported
variables (like stock returns) with off-the-shelf LLMs is "effectively in-sample" unless
leakage is controlled. *Source: arXiv 2512.23847 (Gao, Jiang, Yan, Dec 2025); corroborated
in direction by Glasserman & Lin 2023, arXiv 2309.17322.*

**This is the empirical justification for Optimus's firewall:** forbid backtest P&L from
reaching the model; gate retrieval to point-in-time / as-of; trust only an OOS/post-cutoff
measured number. Aegis already states this as a guardrail — the literature now backs it
quantitatively.

**Caveat:** the Section 3 sources are recent (Oct–Dec 2025) arXiv preprints, not yet
peer-reviewed; descriptive/empirical claims verbatim-verified, methodology not
independently audited.

## 3.3 What Optimus likely lacks → next (synthesis, not a citable claim)

The verified architectures point to candidate gaps (no single source prescribes Optimus's
exact next step — this is judgment):
- **Point-in-time / as-of retrieval gating** keyed on timestamp + git-SHA provenance (the firewall's mechanism, validated by 3.2).
- **A fact-vs-belief separation** in the corpus (Hindsight's split) so rationales (belief) never masquerade as outcomes (fact).
- **An OOS-only gate** before any insight Optimus surfaces is allowed to influence a live decision — the same "measured number first" discipline Aegis already runs on signals.

---

# SECTION 4 — Competitive Landscape & Data Legality (PARTIALLY VERIFIED)

**VERIFIED (high, 3-0).** **SEC EDGAR** fair-access limit is **≤10 requests/second**
(IP-level throttling, ~10-min block on exceedance); SEC expects a **User-Agent declaring
a contact** (`Sample Company Name AdminContact@domain.com`); generic clients get HTTP 403.
**Build directive: any EDGAR/Form-4/13F ingestion throttles to ≤10 req/s with a contact
User-Agent.** *Source: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data*

**VERIFIED (high, 3-0).** **OpenBB is AGPLv3** (copyleft + network-use / Section 13 SaaS
clause requiring source disclosure for modified network services); positioned as a
data-aggregation layer (Python/REST/Excel/MCP). **Build directive: study its architecture,
never copy its code into the MIT Aegis repo** (already in roadmap §6).
*Source: https://github.com/OpenBB-finance/OpenBB*

**UNVERIFIED (did not survive this run — needs a follow-up pass before assertion):**
yfinance/Yahoo ToS for non-commercial use, FRED API terms specifics, GDELT terms,
Financial Modeling Prep / Alpha Vantage free-tier limits, and large-scale-scraping
legality (Cloudflare/AI-blockers). The LLM drafts assert these (≤10 req/s EDGAR, FMP
250/day, "scrape-everything is infeasible") and they are *probably* right, but they are
**not adversarially verified** — treat as open.

**Differentiation (consensus across both runs + drafts, judgment):** Aegis's genuine moat
is the **honest forward track record (uncopyable — needs elapsed time), published negative
results, and the experiment registry.** Where it's behind: **data breadth** (yfinance+FRED
vs OpenBB's many connectors) and **community**.

---

# SECTION 5 — Smart Money & News-as-Measured-Flag (VERIFIED, Run 2)

## 5.1 Insider (Form 4) — durable edge ONLY when filtered

**VERIFIED (high, 3-0).** Over **half** of insider trades are "routine" with ~zero
predictive value; stripping them leaves "opportunistic" trades carrying *all* the
predictive power — a value-weighted opportunistic strategy earns **~82 bps/month
(~10%/yr)** abnormal returns, routine ~zero.
*Source: Cohen, Malloy & Pomorski, "Decoding Inside Information," JF 2012 / NBER w16454.
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1692517*
**Caveat:** gross-of-cost, 1986–2007 sample; subject to alpha decay — describes what the
literature found, not a guaranteed live edge. **Refines the Form-4 idea beyond
cluster-buying: also separate routine vs opportunistic filers.**

## 5.2 13F — the alpha lives PRE-disclosure and erodes after the 45-day lag

**VERIFIED (high, 3-0).** 13F disclosure imposes a real proprietary cost: hedge-fund
performance drops **~2.7pp/yr** after a fund begins filing (not explained by scale or mean
reversion), concentrated in high-proprietary-cost / illiquid-holding funds; **confidential
(delayed-disclosure) positions earn positive significant abnormal returns over the
non-disclosure window.** → The alpha is in the *pre-disclosure* period and erodes once
positions are public (lagged).
*Sources: Shi 2017, JFE 126(1) https://www.sciencedirect.com/science/article/abs/pii/S0304405X17301186 ;
Agarwal, Jiang, Tang & Yang 2013, JF 68(2) https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1787171 .*
**Provenance note for the coding agent:** the "confidential positions" result is Agarwal
et al. 2013; cite both papers.

**Honest verdict (validates the brief's thesis):** cloning ordinary **45-day-lagged 13F is
weak/negative after costs** because the information-sensitive alpha has already eroded;
**long-horizon value cloning (e.g., Berkshire) survives only because holding periods dwarf
the lag.** Congressional/political trackers carry similar reporting-window lag — treat as
low-weight thematic context, not a signal.

## 5.3 Real-time news/social signals — UNVERIFIED here

**No claims survived verification** for political/executive-order/tariff market impact or
social sentiment in this run. The LLM-draft consensus (unverified) is consistent and
plausible: signal decay in **minutes–hours**, extreme misinformation risk, negligible
durable retail edge → **use news as a *measured risk-off gate* (eligibility=False on a
flagged binary event), never a buy signal, gated against a no-news Brier baseline.** This
matches Goal 5 already. Needs a dedicated verification pass before any assertion.

---

# Cross-cutting risks the builder may be under-weighting

(From both runs + draft consensus; all judgment-level, worth holding.)

- **Survivorship & look-ahead bias** — replay must use as-of constituents and as-of features (Aegis already flags this; the leakage literature in 3.2 raises the stakes).
- **Overfitting to a single bull market** — 2020–2025 is one regime; validate signals on older crises as OOS proxies.
- **Data-snooping across lanes** — exactly what effective-N (Ticket 2) defends; raw trial count under-deflates correlated lanes.
- **Acting on a paper record too early** — the 24-month skill threshold is the firewall against a young track record; both runs reinforce it.
- **Reflexivity / regime change** — the SOS zero-false-positive record is 2024-vintage; immigration-driven 2024 unemployment may not generalize. Measure forward.
- **Liability of public guidance** — keep disclaimers; ship signals as "descriptive" unless a measured OOS number clears the gate.

---

# What's VERIFIED vs what's still OPEN (one-glance)

| Topic | Status |
|---|---|
| LPPLS structure + limitations + "not a forecaster" | ✅ VERIFIED (predictive skill **refuted**) |
| SOS > Sahm recession indicator (free FRED `IURSA`) | ✅ VERIFIED |
| Michaillat ensemble | ✅ VERIFIED **in-sample only** |
| DSR + False Strategy Theorem (effective-N gap) | ✅ VERIFIED |
| Hindsight / FinMem / TradingAgents architectures | ✅ VERIFIED (TA returns figure refuted) |
| Hindsight firewall empirically necessary (profit mirage, ~37% leakage, p=0.033) | ✅ VERIFIED |
| SEC EDGAR ≤10 req/s + User-Agent; OpenBB AGPLv3 | ✅ VERIFIED |
| Insider opportunistic-vs-routine (82 bps/mo); 13F pre-disclosure alpha erosion | ✅ VERIFIED |
| Slippage/CSCV/PBO mechanics; LEAN defaults | ⚠️ UNVERIFIED (rate-limited, not refuted) |
| yfinance/FRED/GDELT/FMP/AlphaVantage ToS; scraping legality | ⚠️ UNVERIFIED (drafts only) |
| Real-time political/tariff/social signals | ⚠️ UNVERIFIED (no claims survived) |
| FinLake-Bench's 4 leakage dimensions (identities) | ❓ OPEN |

---

# Open questions for a future pass

1. The four specific "dimensions" of LLM leakage in FinLake-Bench (arXiv 2510.07920) — would sharpen the firewall threat model.
2. Section 4 data-legality items (above) — verify before asserting in any public doc.
3. Section 5 real-time signals — documented decay + legality per signal; can any clear a no-news Brier baseline as a risk-off gate?
4. How to estimate DSR's effective-N when lanes are correlated rather than independent (→ Ticket 2's design question).

*Unverified context: `~/Downloads/reseach.txt` (Gemini, BigData, DeepSeek, ChatGPT drafts). Directionally consistent with the verified core; retained as framing, not evidence.*
