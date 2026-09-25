# Bloomberg Global Trading Challenge — Research Report (as of 2026-09-25)

## PART 1 — OFFICIAL RULES: what's CONFIRMED vs UNCONFIRMED

### Dates, Fall 2026 edition

CONFIRMED, primary source (Bloomberg for Education portal, fetched directly 2026-09-25 at
https://portal.bloombergforeducation.com/trading_challenges):
- Registration window: **Aug 31, 2026 – Oct 5, 2026**
- Challenge period: **Oct 12, 2026 – Nov 13, 2026**
- Winners announced: **Nov 20, 2026**

UNCONFIRMED / minor discrepancy: secondary AI-aggregated sources (quantchallenges.com,
last-verified banner "2026-09-23") give the registration deadline as **"Oct 4, 2026, 23:59 EDT"**
rather than Oct 5. Given the pattern in prior years (registration always closes a few days before
a Monday challenge-start, at either 5pm or in one case noon ET), the true deadline is most likely
**Oct 4 or Oct 5, 2026, evening ET** — pin down the exact hour from the confirmation email/portal
banner directly, don't trust either secondary figure to the hour.
Source: https://portal.bloombergforeducation.com/trading_challenges ;
https://quantchallenges.com/challenges/2026-bloomberg-global-trading-challenge-qc-2899

The user's prompt guess ("~Oct 12–Nov 13, registration ~Oct 4") is **CONFIRMED essentially
correct** on the challenge window and directionally correct on registration.

Important caveat found in passing: at least one school (St. John Fisher University) ran Bloomberg
Global Trading Challenge teams in **"Spring 2026"** as well
(https://www.sjf.edu/news-and-events/news-archive/spring-2026/fisher-teams-compete-bloomberg-trading-challenge) —
Bloomberg appears to run this as a roughly twice-yearly (spring + fall) programme, not a single
annual event. Not confirmed from Bloomberg's own materials which of the two (if either) is called
the "Fall 2026" edition officially, but the Oct–Nov window matches the historical "fall" slot every
year 2021-2025.

### Structural rules — CONFIRMED, primary source, and STABLE 2021→2025

I fetched the actual Terms & Conditions text via the Bloomberg for Education portal (both the
official page and its PDF equivalents for 2021, 2022, 2024, and the live 2025 edition — the portal
had not yet rolled over to 2026 text as of 2026-09-25, so the current live terms are still the 2025
ones, verbatim identical in substance to 2021-2024). This is about as close to "read the actual
current T&C" as is possible before Bloomberg republishes for 2026; treat the 2026 numeric rules
below as **INFERRED with very high confidence** (5 straight years unchanged) rather than
literally re-confirmed for 2026 specifically.

- **Notional amount:** US$1,000,000 virtual, must be invested in FULL within the first business
  week of the Challenge Period (2025 wording: "no later than 9:00am ET on October 17, 2025" —
  i.e., ~4 trading days after the Oct 13 start). CONFIRMED for 2025; pattern present since 2021
  ("starting positions entered no later than" a date ~4-7 days after start).
- **Universe:** "All stocks that are members of the Bloomberg World Large, Mid and Small Cap
  Price Return Index (WLS <Index><GO>)" — CONFIRMED, exact official name. This is NOT "World
  Large & Mid Cap" as guessed in the prompt — it is **Large, Mid, AND Small** cap (all three), price
  return (not total return) index, ticker WLS. ETFs are explicitly excluded ("single name equities —
  no ETFs"). CONFIRMED across every year 2021-2025.
- **Long only, no shorts:** CONFIRMED, verbatim every year: "The Challenge is limited to long-only
  trades; no short positions are allowed."
- **No leverage:** CONFIRMED, verbatim every year: "No leverage is permitted."
- **Max position size:** CONFIRMED, verbatim every year: "No single position held by a Team may
  be greater than twenty percent (20%) of the notional amount."
- **Scoring / benchmark — this is where the prompt's guess and secondary sources DIVERGE from
  the primary source:**
  - The **official Terms & Conditions** (fetched directly, 2025 live text) say the winner has **"the
    highest Relative P&L over the Challenge Period"** relative to the WLS Index, with "Relative P&L"
    itself defined inside the Terminal's own help menu (`TMSG<GO>` Help page) — not spelled out
    on the public web. Tiebreaker (to the thousandths of a percent) is **highest Absolute Return**.
    This "Relative P&L" language is IDENTICAL going back to the 2021 PDF.
  - Multiple **secondary/press sources** (RIT's own news article on its 2024 win, the
    quantchallenges.com aggregator, and Bloomberg's own 2025 "embraces AI" insights framing as
    paraphrased in search snippets) instead describe the metric as **"highest time-weighted
    relative return"**. This may be a looser paraphrase of the same TMSG-defined "Relative P&L"
    concept (time-weighting is a natural component of P&L attribution when positions are added
    mid-week), or it may reflect a genuine methodology refinement not yet reflected in the public
    T&C page. **UNCONFIRMED which of the two phrasings is technically precise** — the primary
    document's own text is the safer one to rely on and cite: "Relative P&L," and it explicitly says
    the operative definition lives inside `TMSG<GO>` Help on the Terminal itself, which a
    participant should read directly once they have terminal access.
  - So: the benchmark is **CONFIRMED as WLS itself** (not MSCI World — no source anywhere
    mentions MSCI as the challenge benchmark; that part of a possible LLM-summary error is
    corrected here). The score is explicitly **relative** to WLS, not absolute return.

- **Team size / eligibility:** CONFIRMED, stable since 2021: 3-5 students + 1 faculty advisor
  (advisor does not trade, except for legal reasons with under-18 teams); all same institution; ≥16
  years old (2024 wording; 2021-2022 wording didn't specify an age floor beyond "full-time
  student"). One login (Team Captain's) submits trades via `TMSG<GO>`.
- **Number of teams per school:** since 2024, 2 teams per Bloomberg terminal in the school's
  teaching/research fleet (uncapped for schools with enough terminals); pre-2024 the cap was
  looser/keyed to "ELP" partner status. HKU almost certainly qualifies for multiple teams given it
  runs the Challenge as a named undergraduate competition every year.

### Terminal functions and data-export rules

- **Data export (BQL/BDH to Excel) is NEITHER explicitly permitted NOR explicitly forbidden** in
  any Terms & Conditions, FAQ, or trader's-handbook text I could retrieve. The official documents
  are silent on it — they describe trade submission via `TMSG<GO>` but never restrict *research*
  tool use to any particular function set. **UNCONFIRMED** whether a stricter internal rule exists;
  given the challenge explicitly encourages using "the Terminal to define market assumptions,
  develop a return-generating strategy" with no restriction language anywhere, the reasonable
  working assumption is that BQL/BDH/Excel research use is allowed (it's just Terminal-native
  data access, same as looking at a screen), but **you should not rely on my inference alone — ask
  Bloomberg via the challenge's own support channel (`bbgtradecomp@bloomberg.net`, confirmed
  live in the 2021/2022 PDFs) or your HKU Bloomberg lab administrator before building an
  Excel/BQL pipeline for the challenge.**
- Regarding the student Terminal licence more generally (separate from challenge-specific rules):
  no source found addressing whether a *student* login has BQL/Excel add-in entitlements
  distinct from a full professional licence. **UNCONFIRMED** — check with HKU's Bloomberg lab.

### Bloomberg Terminal functions relevant to analyst-revision / catalyst work

Verified to exist (CONFIRMED via multiple independent Bloomberg/library-guide sources) and what
each actually does — several differ from the guesses in the prompt:

| Function | Exists? | What it actually is |
|---|---|---|
| `ANR<GO>` | CONFIRMED | Analyst Recommendations — consensus buy/hold/sell rating (1-5 scale) + price targets, list of contributing analysts and their individual calls. One of the most-used functions on the Terminal. |
| `ANRP` | **UNCONFIRMED / likely not a distinct function** | Could not find any documentation of a function literally named ANRP; all hits resolve back to `ANR`. Treat this as probably not a real, separate command — verify on-Terminal with `HELP ANRP<GO>` rather than building anything around it. |
| `EE<GO>` | CONFIRMED | Earnings & Estimates — consensus estimates, estimate history/revisions, individual analyst forecasts, earnings history and price reaction. This is the main "analyst revisions" screen, not `EM`/`EEG` individually. |
| `EM` | CONFIRMED but narrower than implied | "Earnings Trends," a sub-view reached from `EE`, not a standalone top-level revisions function. |
| `EEG<GO>` | CONFIRMED | Earnings Estimates Graph — plots how consensus sell-side estimates for a metric/period have moved over time; this is closer to what you actually want for "analyst-revision momentum" than ANR. |
| `ERN<GO>` | CONFIRMED | Earnings & estimates entry screen (ticker + `EQUITY` + `ERN` + `GO`); overlaps heavily with `EE`. |
| `SURP` | CONFIRMED (as "Surprise Analysis") | Historical earnings-surprise data — actual vs. consensus, and the stock's price reaction to each past surprise. This is the right function for a documented "earnings surprise" precursor test. |
| `SPLC<GO>` | CONFIRMED | Supply Chain — maps a company's disclosed suppliers/customers with modeled cost%/revenue% exposure; covers 200,000+ quantified supply-chain links, sourced from filings/transcripts. Directly useful for a "catalyst propagates along the supply chain" hypothesis. |
| `PHDC` | **UNCONFIRMED / could not verify this exists** | No documentation found anywhere under this exact mnemonic. Likely conflated with `BI PHRM RX` (Bloomberg Intelligence prescription-drug data) or with the BI biotech/pharma catalyst calendar (see below). Do not assume `PHDC` is real without checking `HELP PHDC<GO>` on-Terminal. |
| `BI` (Bloomberg Intelligence) biotech-pharma catalyst calendar | CONFIRMED | A BI product tracking 300+ mostly US/EU biotech-pharma names' regulatory milestone timelines: PDUFA (FDA action) dates, FDA/EMA filing dates, advisory-committee meeting dates. This is the actual "PDUFA calendar" function the prompt was reaching for — access it via `BI<GO>` and the pharma/biotech catalyst calendar inside Bloomberg Intelligence, not a bare `DRUG<GO>` command (no evidence `DRUG` is a standalone ticker-agnostic function; it's more likely shorthand people use informally). |
| `ECO<GO>` | CONFIRMED | Economic-release calendar (macro data, not company events). |
| `EVTS<GO>` (and `EVT`) | CONFIRMED | Company/index events & earnings-announcement calendar — filterable by single security or index (e.g. SPX), daily/weekly/monthly views. This is your general catalyst calendar for a name or the WLS universe subset you can screen down to. |
| `ECDR` / `ECOD` / `ECMX` / `ECFC` | Partially confirmed | `ECOD` (economic release details) and `ECFC` (economic forecasts) turned up in searches; `ECDR` specifically did not resolve to independent documentation — likely a garbled mnemonic (possibly meant `ECOD`). **UNCONFIRMED as written.** |
| `CACS<GO>` | CONFIRMED | Single-security corporate-actions calendar (buybacks, splits, dividends, capital changes). |
| `CACT<GO>` | CONFIRMED (related) | Cross-security corporate-actions search/menu — broader than `CACS`. |

Bottom line for catalyst/analyst-revision work: the functions that are solid and real are `ANR`,
`EE` (with `EM`/`EEG` as sub-views), `ERN`, `SURP`, `SPLC`, `ECO`, `EVTS`/`EVT`, `CACS`/`CACT`, and
the BI pharma-biotech catalyst calendar. `ANRP`, `PHDC`, `DRUG`, and `ECDR` as literally-named
functions could not be confirmed to exist — verify each with on-Terminal `HELP` before designing
a pipeline around it.

---

## PART 2 — PAST WINNERS AND STRONG FINISHERS (2021-2025): what they actually published

Overall pattern across every write-up found: **university PR / student-newspaper pieces almost
never disclose position count, exact holding periods, or turnover.** Only a handful of teams (USF
2025, RIT 2024, Iona 2024, SCSU 2024) gave any texture on *how* they traded; most (HKU 2023,
Lehman 2025, CUHK 2025) gave only the headline return and vague "we worked hard as a team"
framing. I've marked confidence per claim.

### CUHK "Bear Bull" — 2025 Grand Prize (global winner)
- Return: **>400%**, portfolio to **US$4.1M** from $1M. CONFIRMED (Bloomberg press coverage +
  CUHK's own GLEF news page). Team: captain Shierina Sayogo, with Gracia Aubrey Perdana,
  Marvelia Claresa Tjen, Cherish Anastasia Nicolaus; advisor Prof. Haynes Yung. All-women team.
- **No methodology detail published** in the source I could reach (CUHK GLEF news page) — it is a
  marketing blurb (headline return + team photo + congratulatory quotes), not a strategy write-up.
  A fuller CUHK article was referenced but not independently fetched/verified here — treat any
  method details you may have seen elsewhere about this team as UNCONFIRMED until sourced.
- Source: https://www.glef.cuhk.edu.hk/news-events/grand-prize-winner-bloomberg-global-trading-challenge-2025/

### RIT "Tiger Traders" — 2024 Global Grand Prize winner
- Beat 2,453 teams / 396 universities / 46 countries. Relative profit **+$1,676,618** on $1M
  (i.e. ~+168% relative P&L). CONFIRMED, RIT's own news article (detailed write-up, not just a
  blurb).
- Strategy, in the team's own words: **"betting on volatility"** — concentrated heavily in **foreign
  stocks, particularly Asian equities**. Captain Carter Ptak: *"try to make as much money as
  possible without being concerned about the risks of losing... it worked for this competition"*
  (explicitly framed by the team as NOT a real-world-appropriate risk approach).
  This is a genuine, detailed disclosure — CONFIRMED as the team's own account, not marketing
  copy.
- Traded during **Asian market hours overnight** (US time), which the team believed gave them a
  timing edge over competitors asleep during those hours.
  Led the leaderboard **5 of the 6 weeks**.
- No disclosed position count, explicit holding periods, or turnover numbers.
- Source: https://www.rit.edu/news/rit-trio-triumphs-global-trading-challenge

### Iona University — 2024, top 3% (~2,400 teams)
- Final profit **$204,564** on $1M (~+20.5%). CONFIRMED, Iona's own news article.
- Strategy, in the team's words (club president Paul Romano): an **earnings-based** approach —
  **"We focused on smaller market cap companies scheduled to report earnings during the
  week."** This is a genuine (if brief) disclosure of the mechanism: small-cap + pre-earnings
  positioning, i.e. betting on earnings-day volatility in less-covered names.
- Source: https://www.iona.edu/news/iona-university-students-place-top-3-percent-bloomberg-global-trading-challenge

### USF — 2025, top 3% (No. 69 of 2,700 teams, 400 universities, 50 countries)
- Relative return **$53,194** on $1M (~+5.3%). CONFIRMED, USF's own detailed news article — this
  is the **most methodologically detailed write-up found** among all sources.
- Explicitly **rejected standard momentum** on their advisor's advice ("standard momentum
  strategies were unreliable in the current economy") and instead built an **earnings-volatility**
  strategy across tech, healthcare, energy, and rare-earth-materials sectors: buying "stocks that
  had appropriate volatility on their earnings day," sized to risk appetite.
- Named trades: **NVIDIA** (+10% on a single trade around CEO commentary on AI demand),
  **Seagate Technology** (+7%, anticipatory AI-storage-demand trade ahead of earnings) — i.e.
  **catalyst/pre-earnings positioning, not pure post-hoc momentum**.
- Risk rule described: **"a balanced risk strategy"** that "held strong" through a two-day, >200bp
  S&P 500 drawdown late in the competition — no specific stop-loss percentage or sizing rule
  given, but a qualitative claim of resilience through a real drawdown episode.
- Trading cadence: described as fitting research "in between classes" plus "rapid, high-pressure
  analyses late in the evenings" — i.e., not continuous/systematic, bursty around news/earnings.
- Source: https://www.usf.edu/business/news/2025/12-10-bloomberg-trading-challenge-usf.aspx

### SCSU (Southern Connecticut State University) — 2024, 38th of 2,169 teams (top 1.75%)
- CONFIRMED rank and framing (SCSU's own news article): beat all six Ivy League teams and all
  six Columbia teams that year.
- Strategy: **concentrated primarily in cryptocurrency-linked equities** — described as a "bold"
  concentrated bet, not diversified. No numeric return, position count, or holding-period detail
  disclosed.
- Source: https://news.southernct.edu/2024/12/11/scsu-team-excels-in-bloomberg-global-trading-challenge/

### HKU — 2023, Global Grand Prize + Asia/Oceania Regional winner
- Return: **+67.7%** over six weeks, **+$637,399** relative profit on $1M. CONFIRMED via a
  secondary aggregator (FinanceFeeds); HKU's own competition pages exist
  (ug.hkubs.hku.hk/competition/2023-bloomberg-global-trading-challenge) but detailed content
  was not independently re-verified line-by-line here — treat the return figure as CONFIRMED (it
  is consistent and specific, not a rounded marketing number) but the **method is essentially
  undisclosed**: only vague quotes about the Terminal being useful for "analyzing companies and
  trends" and "key stats and analyst reports." **This is a marketing-blurb-level disclosure, not a
  strategy write-up** — worth reading HKU's own competition page directly (linked above) before
  relying on any secondhand description of their 2023 method.
- Context stat for that year overall: >48,000 trades submitted competition-wide; AI stocks were
  the most commonly held theme across ALL teams that year (i.e., a crowded trade, not HKU's
  differentiator specifically).

### Lehman College (CUNY) — 2025, top 5% of ~2,400 teams
- CONFIRMED rank (first among CUNY/SUNY schools). **No return %, no strategy detail** published
  — the article is pedagogy-framed ("students learned to work as a team... evaluate information
  under pressure"), a pure marketing/PR piece with zero trading-method content.
- Source: https://www.lehman.cuny.edu/news/2025/Lehman-Students-Among-Top-5-in-Bloomberg-Global-Trading-Challenge.php

### Newcastle University Business School — 2023 and 2025
- 2023: 4 teams in the global top 10%. 2025: best team ranked **18th of 2,393 teams** globally,
  plus 2 more teams inside the top 10%. CONFIRMED ranks; no strategy detail found in the search
  snippets (would need to fetch ncl.ac.uk articles directly for method detail — not done here, flag
  as an open follow-up if useful).

### Pattern across all of the above (my synthesis, not any single source's claim)
- Every disclosed high-performing strategy either (a) **concentrated** hard in a theme/region
  (RIT: Asian equities + volatility; SCSU: crypto-linked names; USF: earnings-day volatility across
  a handful of sectors) rather than diversifying across the ~10,000-name WLS universe, or (b)
  explicitly **timed positions around a known catalyst** (Iona: pre-earnings small caps; USF:
  earnings-day trades in NVDA/STX). Nobody who published detail described a diversified,
  low-turnover, buy-and-hold approach.
- Nobody disclosed a number of positions held or a precise holding-period distribution. This is a
  genuine gap in the public record — you will not find a "typical winning portfolio held N names for
  M days" figure anywhere; if you want that, you'd need direct outreach to a past captain (e.g. via
  LinkedIn) rather than published sources.
- Risk-management disclosures are uniformly qualitative ("balanced risk strategy," "stop losing
  trades" per the official FAQ language) — no team published a quantitative stop-loss or
  position-sizing rule.

---

## PART 3 — THE RANK-TOURNAMENT MATH: what return was needed for top 1% / 5% / 10%

**No official Bloomberg-published distribution or leaderboard-cutoff table was found anywhere** —
Bloomberg does not publish the full return distribution, only headline winners and each school's
own self-reported rank. Everything below is reconstructed from scattered self-reports, so treat
the implied cutoffs as **UNCONFIRMED, order-of-magnitude estimates**, not real percentile
statistics:

| Year | N teams (participants) | Team | Rank | Return / relative P&L |
|---|---|---|---|---|
| 2023 | ~2,900+ (context: 48,000+ trades that year) | HKU | Global winner (#1) | +67.7% (+$637,399) |
| 2024 | 2,453 teams / 396 universities / 46 countries | RIT | #1 | +$1,676,618 (~+168%) |
| 2024 | 2,169 teams / 396 universities / 46 countries | SCSU | #38 (top 1.75%) | not disclosed |
| 2024 | ~2,400 teams | Iona | top 3% | +$204,564 (~+20.5%) |
| 2025 | 2,700 teams / 400 universities / 50 countries | USF | #69 (top 3%, "No. 69") | +$53,194 (~+5.3%) |
| 2025 | ~2,400 teams | Lehman | top 5% | not disclosed |
| 2025 | 2,393 teams | Newcastle (best team) | #18 (top 0.75%) | not disclosed |
| 2025 | ~2,600+ teams / 11,000+ students / 50 countries | CUHK "Bear Bull" | Global winner (#1) | +400%+ (to $4.1M) |

Reading this as a **very rough** implied cutoff curve (illustrative only — different years, different
market regimes, not a clean single distribution):
- **#1 (top ~0.04%):** anywhere from **+68% to +400%+** depending on the year — huge
  year-to-year variance, consistent with a short (5-7 week), long-only, single-name-concentration,
  20%-max-position tournament where a few teams get lucky/aggressive on a handful of volatile
  names (crypto-linked equities, single-stock earnings pops, AI-theme concentration).
- **Top 1-2% (rank ~20-40 of ~2,200-2,700):** SCSU's rank-38-of-2,169 is the only clean data point
  and it came with **no disclosed return** — so no basis exists to say "top 1% needs X%."
- **Top 3%:** USF's own return at rank 69/2,700 was **only ~+5.3%** relative to WLS — this is the
  single most useful real data point, and it is much smaller than intuition would suggest for
  "top 3% of a stock-picking tournament." It implies the return distribution across ~2,700 teams is
  **extremely right-skewed**: a small number of concentrated/lucky/aggressive teams post
  triple-digit relative returns, while a "very good, competent" team at the 97th percentile posts a
  single-digit relative return over 5 weeks.
- **Top 5%:** Lehman, no return disclosed.
- **Top 10%:** Newcastle, 2 teams, no returns disclosed.

**Conclusion on the tournament shape:** the evidence (thin as it is) supports treating this as a
**high-variance, fat-right-tailed rank tournament** where the winning number is dominated by a
small number of extremely concentrated, extremely lucky teams (consistent with RIT's own
explicit "make as much money as possible without being concerned about risk" framing, and
CUHK's 400%+ in 5 weeks on a long-only, 20%-max-position, no-leverage $1M book — which is only
mathematically reachable through a handful of huge concentrated winners, likely small/micro-cap
WLS-index members with extreme single-name moves, not diversified stock-picking skill). A team
aiming for "respectable top-quartile" should expect single-digit-to-low-double-digit relative
returns (USF's ~+5.3% at top-3% is the best real anchor); a team aiming for the **Grand Prize**
should recognize that recent winners (RIT +168%, CUHK +400%+) reflect concentrated,
high-variance bets, not diversified alpha — winning outright appears to require deliberately
maximizing variance (consistent with RIT's own stated approach), not minimizing risk.

**This whole section is a reconstruction from self-reported news snippets, not a Bloomberg
statistic — flagged UNCONFIRMED as a distribution, though each individual rank/return pair cited
is CONFIRMED from its own named source.**

---

## PART 4 — Sources list (all URLs cited above)

- Bloomberg for Education portal (2026 dates, live): https://portal.bloombergforeducation.com/trading_challenges
- Bloomberg for Education Terms & Conditions (live = 2025 text as of fetch date 2026-09-25): https://portal.bloombergforeducation.com/trading_challenges/terms
- Bloomberg for Education FAQ: https://portal.bloombergforeducation.com/trading_challenges/faqs
- Official Bloomberg PDF, 2021 edition: https://assets.bbhub.io/professional/sites/10/Trading-Challenge_Info.pdf
- Official Bloomberg PDF, 2022 edition (FAQ): https://assets.bbhub.io/professional/sites/10/2022-Bloomberg-Global-Trading-Challenge-FAQ.pdf
- Official Bloomberg PDF, 2024 edition (via HKU mirror): https://ug.hkubs.hku.hk/f/competition/254985/262466/2024_GTC_Introduction.pdf
- quantchallenges.com aggregator (2026, secondary, last verified 2026-09-23): https://quantchallenges.com/challenges/2026-bloomberg-global-trading-challenge-qc-2899
- St. John Fisher spring 2026 mention: https://www.sjf.edu/news-and-events/news-archive/spring-2026/fisher-teams-compete-bloomberg-trading-challenge
- CUHK "Bear Bull" 2025 Grand Prize: https://www.glef.cuhk.edu.hk/news-events/grand-prize-winner-bloomberg-global-trading-challenge-2025/
- RIT "Tiger Traders" 2024: https://www.rit.edu/news/rit-trio-triumphs-global-trading-challenge
- Iona University 2024: https://www.iona.edu/news/iona-university-students-place-top-3-percent-bloomberg-global-trading-challenge
- USF 2025: https://www.usf.edu/business/news/2025/12-10-bloomberg-trading-challenge-usf.aspx
- SCSU 2024: https://news.southernct.edu/2024/12/11/scsu-team-excels-in-bloomberg-global-trading-challenge/
- HKU 2023 (via FinanceFeeds secondary summary): https://financefeeds.com/hong-kong-university-wins-bloombergs-trading-challenge/
- HKU's own 2023 competition page (not independently re-verified in full): https://ug.hkubs.hku.hk/competition/2023-bloomberg-global-trading-challenge
- Lehman College 2025: https://www.lehman.cuny.edu/news/2025/Lehman-Students-Among-Top-5-in-Bloomberg-Global-Trading-Challenge.php
- Newcastle University 2023/2025 mentions (via search snippets, not independently fetched): ncl.ac.uk business news pages
- Bloomberg participation-record press release (existence confirmed, 403'd on direct fetch — cited via search snippet only): https://www.bloomberg.com/company/press/bloombergs-global-trading-challenge-sets-participation-record/
- Bloomberg Terminal function documentation: various library guides (USD, NYPL, CBS, UTSA, Emory, UTD) and Bloomberg's own professional.bloomberg.com/insights pages, individually cited inline above.
