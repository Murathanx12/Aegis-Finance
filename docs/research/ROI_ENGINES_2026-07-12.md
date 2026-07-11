# Max-ROI Engines & Real-Investor Following — what actually works (2026-07-12)

> Research deliverable only (no code changes). Context read first: `REFERENCES.md`
> (15 OSS verdicts stand, not re-litigated), `docs/research/CRASH_AND_OSS_RESEARCH_2026-07-11.md`,
> `docs/research/ENGINE_GAPS_2026_07_09.md` (PEAD/vol-managed verdicts reused, not re-argued),
> the 13 TRIALS docs. Method: 3-angle web fan-out (OSS bots / copy-trading evidence /
> academic strategy menu), synthesized against the live trial inventory.
> Owner's directive: "learn from the highest-ROI bots and real investors; don't play
> very safe." This doc takes the directive seriously — and prices it honestly.

---

## 1. OSS "max ROI" bots: nobody publishes an honest live record

**Blunt meta-finding: no flagship open-source retail bot publishes a dated,
out-of-sample, live track record with drawdowns.** The space is backtest-marketing
plus disclaimers. The only honest *forward* evidence comes from academic live
benchmarks of these agents — and it is mostly negative.

| Project | What it actually runs | Live/forward evidence | Grade |
|---|---|---|---|
| [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (virattt, ~43k★) | LLM investor-persona stock-picking (Buffett/Burry/Wood agents → PM agent) | **None** from the repo (educational, no execution). One independent test ([Vietnamese stocks](https://www.researchgate.net/publication/390835988)) found short-horizon Sharpe **−1.43**. No fork found with a dated equity curve. | nothing / weak-negative |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) (~80k★) | Bull-vs-bear debate multi-agent | Backtest on ~3 months of mega-cap tech **inside the LLM training cutoff** — parametric look-ahead is unresolvable ([arXiv 2605.24564](https://arxiv.org/abs/2605.24564)). Independent live eval found these agents **degrade under live conditions** ([Agent Market Arena, arXiv 2510.11695](https://arxiv.org/abs/2510.11695)). | backtest-only, contaminated |
| FinRL / FinGPT (AI4Finance) | Deep-RL allocation; FinGPT sentiment backtests | No live record. The authors themselves document endemic backtest overfitting (FinRL-Meta, NeurIPS 2022) and propose **rejecting agents with >10% estimated overfit probability** ([arXiv 2209.05559](https://arxiv.org/abs/2209.05559)). | backtest-only, self-criticized |
| Lumibot / QuantConnect | Frameworks, not strategies | Lumibot: no audited community results found. QuantConnect **shut down Alpha Streams v1**, admitting its selection process "results in strong overfitting" ([forum postmortem](https://www.quantconnect.com/forum/discussion/13441/alpha-streams-refactoring-2-0/)). | the platform's own postmortem confirms live degradation |
| [freqtrade](https://www.freqtrade.io/en/stable/) (crypto) | Harness, not strategy | Publishes **no performance claims at all**; docs actively warn public strategies underperform and [hyperopt overfits](https://www.freqtrade.io/en/stable/hyperopt/). Community "2,509%" posts = unaudited backtests. | honest-by-abstention |
| [Composer.trade](https://composer.trade/symphony) | No-code ETF momentum/vol-switch "symphonies" | Partial credit: public symphonies show **out-of-sample stats accrued after creation date** (simulated forward, not real money). | weak-moderate; best UI pattern in the space |
| LiveTradeBench ([arXiv 2511.03628](https://arxiv.org/abs/2511.03628)) | Academic: 21 LLMs traded live 50 days (Aug–Oct 2025) | **The real live evidence:** LMArena rank does *not* predict trading outcome; framework matters more than model. | strong (dated, live, multi-model) |
| NexusTrade | Closed-source LLM platform | Founder put [$25k real money public](https://nexustrade.io/blog/im-giving-an-ai-access-to-my-public-trading-account-heres-how-you-can-watch-it-destroy-25000-20260228) (Feb 2026) — a transparency commitment, results not matured. | weak-but-honest (prospective) |

**Patterns worth borrowing (none require adopting a framework):**
1. **Composer's creation-date-stamped OOS accounting** — performance before vs
   after publication displayed separately. Directly applicable to the
   track-record page: every lane/trial already has an inception commit; surface
   "since pre-registration" as the only headline number.
2. **FinRL's overfit-probability rejection gate** — statistically reject a
   candidate before deployment. Aegis already has this (DSR/PBO in
   `evaluate_candidate`); the borrow is confidence that the discipline is the
   industrial direction, not paranoia.
3. **freqtrade's warnings-at-the-point-of-temptation** — overfitting warnings
   live inside the hyperopt docs page, not a separate ethics doc. Same idea as
   the discipline skills; worth applying to any future lane-config surface.
4. QuantConnect's Alpha Streams postmortem and the two live LLM-agent benchmarks
   are **external validation of the house doctrine**: backtest selection ≈
   overfitting selection; live degradation is the norm. The forward-NAV +
   pre-registration spine remains the moat — confirmed again, third scan in a row.

---

## 2. Following real investors: what the evidence actually supports

### Social copy-trading (eToro): followers don't reliably profit
- Copy-trading availability causes **excessive risk-taking** in controlled
  experiments — rankings select lucky high-variance traders ([Apesteguia,
  Oechssler & Weidenholzer, *Management Science* 2020](https://pubsonline.informs.org/doi/10.1287/mnsc.2019.3508)).
- Being copied makes leaders *worse*: more risk, more trading, stronger
  disposition effect ([Pelster & Breitmayer, *JEBO* 2019](https://www.sciencedirect.com/science/article/abs/pii/S0167268119300812); Pelster & Hofmann, *JBF* 2018).
- Wikifolio-type platforms: **no alpha on average** across ~1,084 portfolios
  ([summary](https://www.evidenceinvestor.com/post/social-trading-platforms-are-bad-for-your-wealth)).
  No peer-reviewed "% of copiers profitable" number exists; eToro's own CFD
  disclosure (51–76% of retail accounts lose money) is the nearest hard datum.
  The oft-quoted MIT +6–10% ([Pan/Altshuler/Pentland 2012](https://dspace.mit.edu/handle/1721.1/80764))
  is *relative to other platform users*, partly eToro-funded, and not
  market-beating evidence.

### 13F superinvestor cloning: the ONE follower approach with real support
- **Berkshire clone bought the month after public disclosure: ~+10.75%/yr over
  the S&P (1976–2006)** ([Martin & Puthenpurackal, SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=806246) —
  caveat: working paper, apparently never journal-published, sample ends 2006).
- What made Buffett copyable is **quality + low-beta held long with leverage**,
  not secret timing ([Frazzini, Kabiller & Pedersen, "Buffett's Alpha," *FAJ* 2018](https://www.tandfonline.com/doi/abs/10.2469/faj.v74.n4.3)).
- Copycats of disclosed mutual-fund holdings **marginally beat the originals net
  of costs** — free-riding saves the fees ([Verbeek & Wang, *JBF* 2013](https://www.sciencedirect.com/science/article/abs/pii/S0378426613002070)).
- Managers' **biggest-conviction positions outperform by ~2.8–4.5%/yr; the rest
  of their books don't** ([Antón, Cohen & Polk "Best Ideas," SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1364827)).
- The condition that decides everything: **the 45-day lag is irrelevant for
  low-turnover managers and fatal for fast ones** — and the time-sensitive
  positions get confidential treatment anyway ([Aragon, Hertzel & Shi, *JFQA* 2013](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1569736)).

### Congressional trading: the edge is dead in the data; the products are beta + story
- Pre-2012: real — Senate ~85bp/mo ([Ziobrowski et al., *JFQA* 2004](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/abnormal-returns-from-the-common-stock-investments-of-the-us-senate/A39406479940758D59E09FDCB8EE9BEC)), House ~55bp/mo (2011).
- Post-STOCK Act 2012–2020: **"random stock picking," no informed trading**
  ([Belmont, Sacerdote, Sehgal & Van Hoek, *J. Public Economics* 2022](https://www.sciencedirect.com/science/article/abs/pii/S0047272722000044); [NBER w26975](https://www.nber.org/system/files/working_papers/w26975/w26975.pdf)).
- The cleanest live test: **NANC vs SPY since Feb-2023 ≈ +93% vs +79%** — but
  [Baulkaran & Jain, *Economics Letters* 2025](https://www.sciencedirect.com/science/article/abs/pii/S0165176525001004)
  find **no risk-adjusted outperformance**: NANC is a 0.75%-fee large-growth/tech
  fund. KRUZ lags badly. [Unusual Whales' own 2025 report](https://unusualwhales.com/congress-trading-report-2025):
  only 32.2% of Congress beat SPY, rankings driven by *unrealized* stale
  holdings. Autopilot's "Pelosi +54% in 2024" is self-reported, unaudited,
  dominated by leveraged NVDA calls — marketing.
- Matches the frozen TRIAL-CONGRESS-IC prior exactly (weak-to-null); nothing
  found justifies amending it.

### ARK copying: reliably wealth-destroying
- ARKK dollar-weighted investor return ~**9.9%/yr vs 41.3% time-weighted** over
  the hot 5 years — money arrived at the top ([Morningstar/Arnott 2022](https://www.morningstar.com/markets/arkk-an-object-lesson-how-not-invest));
  ARK family = **~$14.3B destroyed**, the decade's worst ([Morningstar 2024](https://www.morningstar.com/funds/15-funds-that-have-destroyed-most-wealth-over-past-decade)).
- No peer-reviewed study of mimicking ARK's *daily* disclosures exists; nearest
  rigorous result: thematic ETFs lose **~−6%/yr risk-adjusted over their first
  5 years** because they launch at peak hype ([Ben-David et al., *RFS* 2023](https://academic.oup.com/rfs/article-abstract/36/3/987/6655702)).
  TRIAL-ARK-IC's "possibly negative IC" prior stands; a robust negative read
  would be genuinely useful (crowding gauge).

**What separates evidence from marketing in follower products:** (1) low-turnover
targets that survive the disclosure lag; (2) conviction/cluster filters (copy the
biggest active bets only); (3) long holding periods — what is actually harvested
is durable factor exposure (quality/low-beta), which doesn't decay in 45 days;
(4) avoiding crowded high-flow themes (the ARK tax); (5) audited/risk-adjusted
reporting instead of raw-return storytelling (NANC vs its Sharpe).

---

## 3. The honest "high ROI without fund-hugging" menu

All numbers below net of the [McLean & Pontiff](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623)
haircut logic (published predictors: **−26% out-of-sample, −58% post-publication**).

| Family | Published gross | Live / post-publication reality | Drawdown reality |
|---|---|---|---|
| **Cross-sectional momentum** ([JT 1993](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1993.tb04702.x) ~12%/yr L-S) | Survives costs at scale ([Frazzini-Israel-Moskowitz](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2294498)) **if** traded with buy/hold bands ([Novy-Marx & Velikov, *RFS* 2016](https://academic.oup.com/rfs/article-abstract/29/1/104/1844518)) | **MTUM live since 2013: ≈ +1%/yr vs SPY. AQR AMOMX live since 2009: ≈ −0.7%/yr net** (fund being merged away). Concentration to top-10 plausibly adds 1–3%/yr gross ([Piras, SSRN — grade C](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3695892)) | WML crashes −74% (1932), −46% (2009) ([Daniel & Moskowitz](https://www.kentdaniel.net/papers/published/jfe_16.pdf)); long-only inherits market DD + winner pain, not the full short-leg blowup |
| **Analyst revisions** ([CJL 1996](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1996.tb05222.x) ~7.5%/6mo gross) | Drift lives in **low-coverage** names ([Gleason & Lee 2003](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=370425)) — weakest exactly in a yfinance large-cap universe; recommendation alpha **not reliably >0 net** ([Barber et al. 2001](https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00336)). Zacks' 24%/yr = hypothetical equal-weight frictionless churn, [their own disclosure concedes it](https://www.zacks.com/performance_disclosure/) | ~0–2%/yr net in large caps, heavily overlapping momentum | momentum-like |
| **PEAD** | (prior doc; not re-litigated) | **"Rest in Peace PEAD"** ([Martineau, *CFR* 2022](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3111607)): gone in non-micro stocks since ~2006 | — |
| **Quality (GP/A, F-score, QMJ)** | GP/A works **in the largest, most liquid names** (~4%/yr gross L-S, [Novy-Marx 2013](https://www.sciencedirect.com/science/article/abs/pii/S0304405X13000044)); [QMJ](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2312432) alpha in 23/24 countries | Piotroski's 23%/yr is dead post-publication ([replication](https://blog.portfolio123.com/why-piotroskis-f-score-no-longer-works/)); large-cap quality tilt ≈ 2–4%/yr gross, ~half captured long-only | **Quality pays off in downturns** — the natural crash-hedge for a momentum book |
| **Retail base rate** | — | Average household **−1.1 to −1.5%/yr**; most-active quintile **−6.5%/yr** ([Barber & Odean 2000](https://faculty.haas.berkeley.edu/odean/papers/returns/individual_investor_performance_final.pdf)) | — |

**The blunt priors for a 10–20 name, retail-data, long-only engine:**
- Realistic net excess over SPY: **+0 to +3%/yr, centered +1–2%**. Live factor
  funds cluster at −1 to +1.5%/yr ([factor-fund live records](https://www.evidenceinvestor.com/post/factor-based-strategies)); anything projecting >5%/yr
  sustained contradicts every audited live record and the decay math.
- Tracking error **6–10%** → at a true +1–2% edge, any given year is ~40% likely
  to lag SPY, and 3–5 year droughts are near-certain per decade. Even a
  perfect-foresight portfolio (29.4%/yr) endured a **76% drawdown** and repeated
  multi-year lags ([Alpha Architect](https://alphaarchitect.com/even-god-would-get-fired-as-an-active-investor/)).
- Concentration cuts both ways: 4% of stocks made all net wealth since 1926
  ([Bessembinder 2018](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2900447));
  a 15-name book that misses the skewed winners structurally lags. Momentum +
  quality screens raise the odds of *holding* them; nothing guarantees it.
- The retail edges that actually exist: tiny-position capacity (no market
  impact), zero fee drag, and **behavioral discipline** (not being the
  Barber-Odean active quintile). Not signal superiority.
- On the owner's 2025–26 tech returns: a great year in a tech bull market is
  exactly what beta + 8% TE produces at high frequency (see NANC's raw-vs-Sharpe
  decomposition). It is a reason to *log the convictions forward* (the seeded,
  empty conviction lane), not a reason to raise the prior. One year ≈ zero
  statistical evidence; the house 24-month rule is the correct instrument.

---

## 4. Synthesis for Aegis: three concentrated-lane candidates, ranked by expected value

Everything below is a **proposal for pre-registration** (`pre-register-trial`
skill), not a claim. All would be new lanes (new trials — TRIAL-MULTIFACTOR v1
and TRIAL-QUALITY explicitly forbid folding into the frozen composite), seeded
attended and env-gated (`seed-a-lane`), validated forward only (T7), descriptive
until proven. Risk controls reuse the **existing frozen machinery**: ATR
Chandelier exits + vol-target cap at `config["exit_engine"]` defaults
(TRIAL-EXIT pattern — no new knobs to tune), same cost model as existing lanes.

### Candidate A — Concentrated Composite v2 ("top-15 multifactor") — highest EV, seedable soon
- **Selection rule (frozen at registration):** z-score composite, equal-weighted
  (no tuned weights), of **momentum + quality (GP/A) + revisions + insider** —
  the four accruing signals with surviving literature support. PEAD excluded
  (Martineau), congress/ARK excluded (dead/negative priors, own trials pending).
  Long-only **top 15** of the tracked universe; tech tilt allowed via a 40%
  sector cap + 10% position cap; no leverage.
- **Rebalance:** monthly, with **rank bands** — enter at rank ≤15, hold until
  rank >30 (the Novy-Marx–Velikov band structure is what lets momentum survive
  costs; it also keeps turnover measurable against the cost model).
- **Benchmarks (both required):** SPY *and* equal-weight tracked universe — to
  separate stock-selection skill from the universe/tech tilt (the NANC lesson).
- **Honest prior:** +0 to +3%/yr net vs SPY, center +1–2%; TE 6–10%; deeper
  drawdowns than SPY in momentum unwinds, partially offset by the quality
  sleeve; ~40% chance of lagging in any year. Primary metric: net Sharpe vs
  both benchmarks + forward return spread CI; no decision before month 12,
  skill claims at 24.
- **Dependency:** quality + insider snapshots must have a few weeks of clean
  accrual first (insider had a false-zero history). Nothing else blocks it.

### Candidate B — 13F "Best Ideas" clone lane — strongest published follower prior, needs one build step
- **Basis:** the only follower evidence that is real: post-disclosure Berkshire
  cloning (+10.75%/yr, old-sample working paper), copycats-net-beat-originals
  (Verbeek & Wang), best-ideas +2.8–4.5%/yr (Antón-Cohen-Polk), lag harmless for
  low-turnover managers (Aragon et al.).
- **Selection rule (to freeze):** fixed panel (frozen at registration) of ~8–12
  **low-turnover, concentrated** superinvestors (Dataroma-class: Berkshire,
  Ainslie/Marks-style long books — panel chosen by turnover stats, not vibes);
  clone only **top-conviction holdings** (top-5 by weight or new positions ≥3%
  of the filer's book); equal-weight 10–20 names; rebalance quarterly, 1–3 days
  after each 13F window closes. Same exit overlay + caps as A.
- **Honest prior:** the best in the follower space but inflated by an old
  sample: call it **+0 to +3%/yr net**, with the specific falsifiable mechanism
  "conviction + low turnover survives the 45-day lag." A null here is a clean
  publishable negative.
- **Dependency:** the EDGAR 13F collector exists but is **unscheduled**; needs
  scheduling + a frozen panel/conviction definition + its own IC-style trial
  before any lane. That build step is why this ranks second despite the prior.

### Candidate C — Insider-cluster conviction lane — conditional; wait for the IC read
- Cluster insider buying (≥2 distinct officers/directors, 90d) intersected with
  positive momentum, 10–20 names. Literature support is decent
  (opportunistic-cluster purchases), and it is the most "real investor
  conviction"-flavored signal in the stack — but the free Form4 cross-section is
  **sparse** (the prod false-zero episode showed how thin), and TRIAL-INSIDER-IC
  already measures exactly this signal's forward IC.
- **Recommendation: do not seed yet.** Gate on TRIAL-INSIDER-IC's first matured
  read (earliest ~Dec 2026 / Jan 2027). Seeding a lane on a signal whose own IC
  trial is mid-flight would pay the multiple-testing tax twice for no
  information gain.

### What NOT to build (explicit negative recommendations)
- **No congress/ARK follower lane.** The evidence (Belmont 2022; Baulkaran &
  Jain 2025; Morningstar ARK) is null-to-negative; the IC trials already accrue
  the answer. Revisit only on a CI-excluding-zero read.
- **No LLM stock-picker lane.** ai-hedge-fund/TradingAgents-class agents have
  zero honest live evidence and negative independent live evals; the one
  borrowable piece (bull/bear debate for conviction-decision logging) is already
  in REFERENCES.md.
- **No new vol-timing alpha machinery** (re-affirmed; ENGINE_GAPS refutation
  stands — the overlay is drawdown control, honestly labeled).

### The cheapest high-value action of all
The **conviction lane is seeded and empty**. The owner's real edge claim ("I made
great returns picking tech") is testable for free by logging his actual picks
into it — that is a forward record of *his* convictions with zero research risk,
and it is what every follower product in section 2 fails to provide about the
people it follows.

---

## Evidence-quality note

Live/audited (strong): MTUM/AMOMX records, NANC/KRUZ, Morningstar ARK,
LiveTradeBench/Agent Market Arena, QuantConnect postmortem, peer-reviewed papers
cited by venue. Working-paper grade: Martin & Puthenpurackal (never
journal-published as far as verifiable), Antón-Cohen-Polk, Piras concentration
result, Angelini 13F-clone alphas. Marketing grade (cited only to debunk):
Zacks Rank claims, Autopilot Pelosi tracker, freqtrade community return posts,
Unusual Whales rankings. Unverifiable: any "% of copiers profitable" figure;
Composer aggregate live-vs-backtest stats; Lumibot community live results.
