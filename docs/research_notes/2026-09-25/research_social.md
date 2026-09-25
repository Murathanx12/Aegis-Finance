# DKNG / QUBT social + fundamental check, and a retail-crowding scan

Compiled 2026-09-25. Tools used: OpenClaw (browser-agent, profile `muratclaw`, 6 quests, logs below),
LunarCrush MCP (topic snapshots for DKNG/QUBT before the session's LunarCrush auth expired),
Exa web search/fetch, and public data (SEC filings, AGA tracker, MarketBeat/TipRanks/Zacks/StockAnalysis).
No repo source file was read or modified; a live edit to `backend/services/openclaw_client.py` by
another concurrent process (caught mid-syntax-error, see "Notes on tooling" at the end) was routed
around by shelling out to the `openclaw` CLI directly from a scratchpad script instead of importing
that module.

---

## 1. DKNG — DraftKings

### 1a. Retail social read (last ~30 days)

**OpenClaw quest log** (all 6 quests ran; logs at
`.../scratchpad/log_*.json`, elapsed times below):

| # | Quest | URL | Elapsed | Result |
|---|---|---|---|---|
| 1 | `dkng_reddit` | old.reddit.com/search?q=DKNG (relevance/all-time, not scoped to month — a Windows `cmd.exe` shell quoting issue in the CLI's subprocess call ate the `&sort=new&t=month` params; the agent caught and reported this itself) | 336s | OK, rich reply |
| 2 | `dkng_sportsbook` | old.reddit.com/r/sportsbook/search?q=DKNG | 410s | OK — zero results |
| 3 | `dkng_x` | x.com/search?q=%24DKNG | 54s | OK — login wall, no data |
| 4 | `qubt_reddit` | old.reddit.com/search?q=QUBT | 96s | OK — search-noise, no real QUBT posts |
| 5 | `wsb_hot` | old.reddit.com/r/wallstreetbets/hot | 82s | OK, rich reply |
| 6 | `qubt_subreddit` | old.reddit.com/r/QUBT/hot | 56s | OK — dead subreddit |

**X/Twitter is not reachable for reads**: it is not on OpenClaw's `DENIED_DOMAINS` list (only
payment/brokerage domains are blocked), but the `muratclaw` browser profile has no logged-in X
session — the setup doc only ever had Murat sign into a dedicated **Google** account. X search
redirected straight to a login/onboarding wall for both `$DKNG` and (untested, but certain to repeat)
`$QUBT`. **Recommendation: sign the `muratclaw` profile into a burner X account once, read-only, if
X reads matter going forward.** LunarCrush's own per-network breakdown (below) is the only X signal
this report has.

**Reddit (r/wallstreetbets, r/DKNG, r/stocks) — what's actually there:**
The OpenClaw agent found a live, small (dozens of upvotes, not thousands) but **consistently bullish**
r/DKNG micro-community, plus a couple of related WSB threads:
- "DKNG dropped from +6% to red today after Robins' Wells Fargo comments. Full breakdown of what he
  actually said, and why I think the market got this wrong." (r/DKNG, 2 days old) — retail pushing back
  on a bearish read of management commentary.
- "Today's news is extremely bullish for DKNG" (r/DKNG, 26 days old) — thesis: Kalshi/prediction-market
  regulatory crackdown is a moat for DKNG.
- "DRAFTKINGS is Mispriced" (r/DKNG) — thesis: prediction-market volume already ≈25% of market cap.
- "DKNG is seriously underrated. I'm predicting $50 by end of year." / "one of the most misunderstood
  stocks in the market... worth $100+" — price-target bull posts.
- A large historical WSB gain-post ("Turns out my dumbass might be a genius", 16.1k upvotes, 11 months
  old) inflates any raw "top posts" ranking; it is not current.

**Dominant narrative:** DKNG is "mispriced/underrated," Predictions is the wedge, and regulatory heat
on Kalshi/Polymarket is a tailwind. The one bearish note in the live window is retail explicitly arguing
*against* a bearish analyst take, not conceding it. **r/sportsbook has zero DKNG-tagged threads** in
the past month (bettor chatter there is funneled into daily/promo threads, not standalone posts), so
there is no direct bettor read on odds/limits/hold from this quest.

**LunarCrush `topic("dkng")` snapshot** (tool: LunarCrush `topic`, pulled 2026-09-25 ~05:29 UTC, before
the account hit its rate limit and then needed re-auth mid-session — see caveats):
- Sentiment **55%** now vs a 77% daily average; trending down across every window (Week −20%, Month
  −28%, 3M −28%, Year −36% relative to baseline) — i.e., **sentiment is eroding even though the loudest
  visible posts are bullish.** 1-year high was 98% on 2026-07-26; 1-year low 27% on 2026-09-04 (right
  around the Q2 earnings/CEO commentary window).
- Engagements: Month +179% (a real spike, plausibly the Sept 22–24 CBS investigation + Wells Fargo/CEO
  news cluster below) but 3M −12%, Year −22% — the base rate of chatter has been falling all year.
- Mentions: Week −40%, Month +19%, 3M −38%, Year −33%.
- Network split (24h): X > YouTube > Reddit ≈ TikTok — most DKNG chatter volume is on X/YouTube, not
  Reddit, which is exactly where this report has no direct read (login wall).
- **This is a free/"limited data mode" account** — `topic_posts` (which would give the actual top-5
  posts with links/engagement Murat asked for) returned empty both times it was called. I could not
  retrieve linkable top-5 posts by engagement for DKNG or QUBT from LunarCrush this session.

**Top-5 posts by engagement, with links:** **Not obtainable this session.** LunarCrush's post-level
endpoint needs a paid tier; OpenClaw could not read X (login wall) and old.reddit's own upvote/comment
counts (from quest 1) are the closest substitute — see the bullet list above, none over ~150 points,
which itself is informative (no viral DKNG post in the live window).

### 1b. The facts

**Q2 2026 (reported Aug 6, 2026 — source: DraftKings IR press release, ir.aboutdraftkings.com; SEC
8-K/10-Q, sec.gov/Archives/edgar/data/1883685/):**
- Revenue **$1,443.2M**, down 4.6% YoY ($1,512.5M in Q2'25) — miss vs. consensus.
- Adjusted EBITDA **$114.6M**, down from $300.6M YoY.
- Net loss **$(67.6)M** vs. net income $157.9M YoY.
- Sports Consumer Volume **$13.1B**, +15% YoY. Sportsbook handle +11% YoY. Sports Net Revenue Margin
  fell to 6.8% from 8.7% ("customer-friendly" outcomes + Predictions promo reinvestment).
- Monthly Unique Payers **3.6M**, +9% YoY; ARPMUP **$132**, −$19 YoY.
- Cash + restricted + user-reserved cash: **$1.39B**.
- **FY2026 guidance reaffirmed**: revenue $6.5–6.9B, Adjusted EBITDA $700–900M. CFO: core business
  "on track to generate approximately $1 billion of Adjusted EBITDA this year."
- Earnings call, per Jason Robins: revenue miss was ~$80M from sport outcomes, the rest from customer
  acquisition spend; core (ex-Predictions) revenue was actually **+10% YoY normalized**.

**"Predictions" product:**
- Launched Dec 19, 2025 as a standalone CFTC-regulated app (Introducing Broker subsidiary), 38 states,
  17 with sports contracts (source: bidcanvas.com; defirate.com).
- Acquired Railbird Technologies (closed Oct 21, 2025) for its own Designated Contract Market license;
  launched proprietary exchange **DKeX** June 26, 2026, moving off third-party CME/Crypto.com rails
  (igamingnews.io, news.bitcoin.com).
- Volume trajectory: ~$1.3B annualized consumer volume in May 2026 (+24% MoM) → ~$3.4B annualized
  consumer volume / $11.3B annualized total volume for the week ended June 21, 2026 (World Cup-boosted)
  → per the Sept 23, 2026 Wells Fargo conference remarks, volume is now **~2.5x its July level and
  still rising weekly**, with DraftKings "approaching a double-digit share" of sports prediction-market
  consumer volume (baseballnewssource.com, 2026-09-23).
- Company's own stated internal analysis (Q2 call, Aug 2026): **only ~1% customer overlap** between its
  sportsbook base and the largest prediction-market operator's users in sportsbook states, and it
  estimates 80–90% of prediction-market volume in those states is professional/syndicate flow, not
  organic sportsbook cannibalization.
- Planned FY2026 Predictions investment: **$200–300M**, mostly marketing.
- **Market reaction (Sept 23, 2026, 247wallst.com):** DKNG fell 4% the day after the CEO's comments
  because the market read "we're pulling forward more marketing spend into Predictions" as a near-term
  margin hit — while Robinhood (which owns prediction-market *customers* already, vs. DraftKings which
  has to buy them) rose 0.8% on the *same* news. That's a real, dated (Sept 23) market signal that the
  Street is pricing DKNG's Predictions bet as a cost center for now, not a proven profit engine.

**Guidance:** FY26 revenue $6.5–6.9B / Adj. EBITDA $700–900M, reaffirmed twice (May 7 and Aug 6, 2026).
No change as of the Sept 23 Wells Fargo remarks.

**Analyst target cluster (firm / date / target):**

| Date | Firm | Rating | Target |
|---|---|---|---|
| 2026-09-18 | UBS Group | Buy | $49 → $48 |
| 2026-09-18 | Needham | Buy | reiterate $35 |
| 2026-09-08 | Citizens JMP | Market Outperform | $36 → $37 (cut again 09-24 to **$35**) |
| 2026-09-03 | Bernstein | Outperform | $27 → $29 |
| 2026-09-02 | Wolfe Research | Init. Outperform | $40 |
| 2026-08-11 | Citigroup | Buy | $30 → $32 |
| 2026-08-11 | Macquarie | Outperform | $38 |
| 2026-08-10 | JPMorgan | Overweight | $34 → $33 |
| 2026-07-22 | Morgan Stanley | Overweight | $39 → ~$36 |
| 2026-07-10 | TD Cowen | Buy | $30 → $35 |
| 2026-07-09 | Deutsche Bank | Hold | $26 → $28 |

(Source: MarketBeat forecast page, TipRanks, stocknewsroom.com — all dated Sept 2026.)

Consensus (41 analysts, MarketBeat, as of 2026-09-24): **"Moderate Buy," average target $34.29–$34.36**,
high $50, low $20. TipRanks (27 analysts, trailing 3mo): avg $35.57, high $50, low $27. StockAnalysis:
avg $35.2. MarketScreener (35 analysts, wider trailing window): avg $34.71–$34.88, **high outlier $74**
(a stale pre-guidance-cut estimate still in the average), low $20.

**Is the "60% consensus upside" real?** **Yes, directionally — it's a live, primary-source number, not
an invented one.** As of the most recent snapshots (prices in the low-to-mid $20s in Sept 2026 after
the Q2 miss and the Sept 23 sell-off):
- StockAnalysis.com: price target $35.20 = **+61.47%** upside.
- Stocknewsroom.com: mean target $34.88 vs. $21.82 = **+59.9%**.
- Citizens JMP's own Sept 24 note states its $35 target implies **+64.71%** from the prior close.
- MarketBeat's Sept 3–24 snapshots run **+42–45%** off a somewhat higher reference price (~$24).

So "~60% upside" is a fair read of the current consensus-target-vs-current-price gap **specifically
when DKNG trades in the low $20s** — it moves a lot with the stock (it was 23–43% a month earlier when
the stock was higher, per MarketBeat's own trailing table). It is a real number computed from a primary
consensus source (MarketBeat/TipRanks/StockAnalysis, all first-party aggregators of individual analyst
notes), not a fabricated one — but it is a moving target that compressed and re-expanded as the stock
sold off around the Q2 miss and the Sept 23 Predictions-spend news.

### 1c. Murat's thesis, addressed directly

- **Is legal sportsbook handle growing or flat?** **Mixed and decelerating, not simply "growing."**
  AGA Commercial Gaming Revenue Tracker (americangaming.org, 2026 releases): Q1 2026 handle **−0.8%
  YoY** — "the first quarter YoY handle decline since June 2020." April 2026: handle **+1.5%** YoY
  (barely positive; **−slightly negative excluding new-market Missouri**). Q2 2026: handle **+7.8%**
  YoY to $38.84B, boosted by the World Cup and NBA Finals. DraftKings' own Sports Consumer Volume
  (handle + Predictions volume) was +15% YoY in Q2 — DKNG is growing faster than the market, but the
  market itself (ex-Missouri, ex-World Cup) has been flat to down for three of the last four reported
  periods in 2026.
- **Is hold rate rising?** **Yes, on a multi-quarter basis, but Q2 2026 was actually a rare
  contraction.** Q1 2026 hold **9.8%**, +85bps YoY. April 2026 hold **11.1%**, up from 9.3% YoY. But
  **Q2 2026 hold fell 81bps YoY to 10.1%** — AGA's own release calls this "the first quarterly
  [sportsbook revenue] contraction... outside pandemic-affected periods," and June specifically (World
  Cup month) saw hold crash to 8.1% from 12.5% a year earlier as handle jumped 26%. **Net: hold has
  trended up across 2026 but is volatile and event-driven (a customer-friendly outcome quarter can wipe
  out a full year of hold gains in one print)** — this is the mechanism behind DKNG's own Q2 revenue
  miss (management explicitly blamed "customer-friendly sport outcomes").
- **Is CAC falling?** **Yes, by the company's own reporting, materially.** Q1 2026 call: Predictions
  CAC fell **>80%** after integration into the flagship app (April 2026). Q2 2026 call: "best
  enterprise-wide customer acquisition cost since Q1 2025," ~25% better than plan even while spending
  ~10% more in absolute dollars (i.e., cost-per-customer fell while volume of customers acquired rose
  ~75% YoY / ~30% above plan). This is the strongest piece of evidence for Murat's "little cost, more
  profit" thesis — but note the company is **choosing to reinvest the CAC savings into faster
  acquisition (pulling 2027 marketing spend into 2026)** rather than letting it drop to the bottom
  line, which is exactly what spooked the stock on Sept 23.
- **Where's the "fast money" going (Kalshi/Polymarket/Robinhood event contracts)?** Overwhelmingly
  still to the two private incumbents: Kalshi ($17.1B 2025 notional volume, reportedly raising at a
  ~$40B valuation vs. $22B in May) and Polymarket ($21.5B 2025 notional), together ~97.5% of global
  prediction-market volume (bidcanvas.com, alcapitaladvisory.com). Among *public* names, **Robinhood is
  the current leader in disclosed dollars**: $156M event-contract revenue in Q2 2026 (13.6B contracts,
  >10x YoY), now Robinhood's **second-largest disclosed transaction-revenue category after options**,
  ahead of stock trading ($129M) and crypto ($100M). DraftKings Predictions is smaller in disclosed
  consumer-dollar terms (~$3.4B annualized *volume*, not revenue, as of late June) but growing fast and
  is the only sportsbook-native entrant building its own exchange (DKeX) rather than renting one.
  Coinbase's PM revenue is scaling fastest in percentage terms (+106% QoQ, $100M annualized within 2
  months of full launch). Interactive Brokers is the "boring" exchange-owner (ForecastEx, CFTC DCM)
  play with a much smaller retail base (~3M active accounts vs. HOOD's 27–28M).

### 1d. Verdict — DKNG: **HOLD, lean toward small add on further weakness, not chase here**

The bull case Murat is running (gambling addiction as durable secular demand, "little incremental
cost") is real and shows up directly in the numbers: CAC per customer is falling, MUPs are growing,
and Predictions volume is compounding fast with a documented ~1% cannibalization overlap. The Reddit
read, thin as it is, is genuinely bullish and unforced (retail is defending the stock against bearish
analyst commentary, not capitulating). The ~60% consensus-target upside is a real, current, primary-
source number.

Against that: **the stock just missed Q2 revenue and guided nothing higher**, hold rate — the actual
lever behind "little incremental cost, more profit" — just had its worst quarter of the year (Q2 down
YoY, driven by a bad-for-the-house sports calendar that DraftKings cannot control), and management is
explicitly telling the market it will spend the CAC savings rather than bank them, which is why the
stock sold off 4% on Sept 23 even on objectively good operating commentary. LunarCrush's own sentiment
series is in a *year-long downtrend* even though the vocal Reddit minority is bullish — a sign the loud
posts are not representative of broader retail mood. Handle growth ex-World-Cup/ex-Missouri has been
flat-to-negative for most of 2026 at the industry level.

**What would change this to ADD:** a Q3 print (reported November) showing hold normalizing back toward
Q1's 9.8%+ *and* Predictions volume continuing to compound *without* a further guidance-eroding step-up
in promotional spend — i.e., evidence the CAC gains are starting to convert to EBITDA rather than being
reinvested indefinitely. **What would change this to TRIM:** a second consecutive quarter of hold
compression, or a state-level ruling (several are pending, e.g. Nevada, Michigan, Connecticut orders
already hit Robinhood/Kalshi on sports event contracts) that forces DraftKings to unwind Predictions in
states where it's currently the growth driver.

---

## 2. QUBT — Quantum Computing Inc.

### 2a. Retail social read (last ~30 days)

**Reddit: there is essentially no live discussion.** Two separate OpenClaw quests confirm this from
different angles:
- A cross-subreddit search for "QUBT" (old.reddit.com/search?q=QUBT) returned almost entirely
  **false-positive substring matches** (r/BudgetBlades, r/latin, r/Epson, r/tomhiddleston, etc.) — no
  genuine r/wallstreetbets, r/pennystocks, or r/stocks thread about Quantum Computing Inc surfaced in
  that result set at all.
- The dedicated **r/QUBT subreddit is dead**: 3 total posts on its "hot" page, all ~1 year old, all 0
  upvotes/0 comments. Its own sidebar rules (cite StackExchange sources, 100-karma posting minimum)
  read as an academic Q&A project, not a ticker board — it appears to have strangled its own retail
  traffic rather than hosting one.
- QUBT also did **not** appear anywhere in the r/wallstreetbets "hot" listing snapshot (25 posts, none
  mentioning QUBT, DKNG, or any name in the gambling basket).

**X/Twitter:** blocked by the same login wall as DKNG (untested directly for QUBT this session, but
there is no reason to expect a different result from the same unauthenticated profile).

**LunarCrush `topic("qubt")`** (same pull, ~05:29 UTC): this is where QUBT's actual social activity
is — **sentiment 90%** (vs 80% daily avg), and every headline metric is rising week-over-week:
mentions +52.8%, engagements +20.2%, creators posting +39.3%, posts created +47.0%. But the *level* is
small — QUBT's 1-year engagement high was back on 2025-10-23, and the current reading is still 6.3%
below the trailing-year average and 58% below the 3-month peak. Network mix (24h) shows engagement
spread across Reddit/TikTok/YouTube/X fairly evenly, with the most-engaged creators being YouTube/X
accounts (`@realpaulthomas`, `@AIStockSavvy`, `@willrichyt`), not Reddit posters — consistent with
Reddit search finding nothing: **QUBT's retail conversation lives on X/YouTube, which this session
could not read directly.**

**Top-5 posts by engagement, with links:** **Not obtainable** — same LunarCrush "limited data mode"
and X login-wall constraints as DKNG.

**Read:** QUBT is a *quiet but improving* social story, not a currently-loud one. It is not on any
retail attention tracker's radar right now (see the crowding list, §3 — QUBT does not appear in
ApeWisdom, AltIndex, or feargreedmeter's current top rankings), which cuts against treating any near-
term price action as retail-driven.

### 2b. The facts

**Q2 2026 (reported Aug 10, 2026 — source: quantumcomputinginc.com press release; SEC 8-K/10-Q,
sec.gov/Archives/edgar/data/1758009/):**
- Revenue **$5.6M**, up from **$61K** in Q2 2025 and from $3.7M in Q1 2026 — a real sequential and YoY
  increase, but the base was essentially zero; six-month 2026 revenue is $9.24M.
- Net loss **$11.8M** ($0.05/share), improved from $36.5M ($0.26/share) YoY — but the prior-year loss
  was inflated by a one-time $28M non-cash warrant mark-to-market charge; the current-quarter mark was
  only $1.7M. **The improvement is mostly a non-cash accounting comparison, not an operating-margin
  story** (operating expenses actually rose 114% YoY, from $10.2M to $21.8M, driven by
  headcount/R&D/M&A transaction costs).
- **Cash, cash equivalents and investments: ~$1.3B** (down from $1.5B at YE2025 after ~$180M cash used
  for the Luminar Semiconductor, NuCrypt, and NHanced Semiconductors acquisitions).
- Contract backlog: **~$42.5M**.
- Stockholders' equity: **$1.6B**; total liabilities only $47.2M.

**Dilution:** Basic/diluted weighted-average share count went from **141.4M (Q2'25) to 224.7M (Q2'26)
— a ~59% YoY increase**, and shares issued/outstanding rose further intra-2026 (224.2M at 2025-12-31 →
226.3M at 2026-06-30). Most of the massive YoY dilution happened before this reporting window (QUBT
raised the $1.3–1.5B cash pile largely via at-the-market equity issuance through 2025); the Q2-to-Q2
sequential dilution (224.2M → 226.3M, ~1%) is modest by comparison. **The headline fact: QUBT is
functionally a $1.3B cash-and-acquisitions vehicle wrapped around a ~$20M-run-rate photonics/quantum
products business** — the cash war chest, not organic revenue, is what's funding the recent M&A
(Luminar, NuCrypt, NHanced/"Fab 2").

**Contracts:** Q2 revenue "generated across QCi's integrated portfolio... serving a diverse range of
government, educational, and commercial customers," primarily photonics products supporting the
quantum roadmap plus existing aerospace/industrial applications. $42.5M backlog is the only forward
number disclosed; no single named large contract stands out in the Q2 materials reviewed.

**Analyst price targets — the $10 vs $32 dispersion is real and current:**

| Date | Firm | Rating | Target |
|---|---|---|---|
| 2026-08-26 | Ascendiant Capital | Buy | $30 → **$32** |
| 2026-08-11 | Cantor Fitzgerald | Neutral | **$10** |
| 2026-08-03 | Wedbush | Neutral (assumed) | $12 |
| 2026-06-29 | Rosenblatt | Buy | $22 |
| 2026-04-20 | Northland Capital Markets | Outperform (init.) | $20 |

(Source: tickernerd.com, benzinga.com, tickergate.com, wallstreetzen.com, alphaspread.com — all citing
the same ~5–6 sell-side analysts.) Consensus across sources: median/average **$17.33–$19.20**, high
**$30–32**, low **$10**. That's a >3x spread between the most bearish and most bullish live target —
an unusually wide dispersion that signals genuine disagreement about whether QUBT is a real operating
business or a cash shell trading on quantum-computing sentiment. One independent read worth flagging:
**tickernerd.com's own systematic factor model ranks QUBT 23rd out of 100 in its ~4,600-stock universe
— "the weakest quartile"** — i.e., a quant factor screen disagrees with the Street's bullish median
target even as it reports that same median honestly.

### 2c. Verdict — QUBT: **HOLD, do not add on the current setup**

There is a real, improving revenue trend (from a near-zero base) and a genuinely reassuring balance
sheet ($1.3B cash vs. a market cap that likely does not fully reflect it — worth Murat checking current
market cap against this cash figure directly). But the bull case here is not "little incremental cost,
more profit" the way DKNG's is — QUBT's operating losses are *widening* on a cash basis (opex +114%
YoY) and the "improvement" in headline net loss is a non-cash derivative accounting artifact, not
margin expansion. Retail attention is real but quiet and not currently reachable via the channels this
report could check (Reddit is empty; X is blocked). The $10–$32 analyst dispersion and the weak
independent factor-model rank both say: **this is a name where the target you get depends entirely on
which analyst you ask, and a systematic screen disagrees with the median bull.** Nothing here argues
for urgency in either direction — it argues for waiting for the next print (revenue trend continuation,
opex trajectory, and whether the M&A spree starts producing disclosed contract wins beyond the $42.5M
backlog) before sizing up.

**What would change this to ADD:** two more quarters of accelerating revenue (ideally toward/above the
Q1→Q2 $3.7M→$5.6M sequential pace) *combined with* opex growth decelerating below revenue growth — i.e.
early operating leverage. **What would change this to TRIM:** another large ATM equity raise (further
dilution beyond the ~1% seen this quarter) without a matching jump in backlog or named contracts.

---

## 3. Additional stocks retail is crowding into NOW (last ~14 days)

Source: **ApeWisdom** (apewisdom.io/wallstreetbets, live WSB mention tracker), **AltIndex**
(altindex.com/wallstreetbets and its Sept 21 weekly recap), **FearGreedMeter** (feargreedmeter.com,
updated Sept 24, 2026), and the OpenClaw `wsb_hot` quest (§1a). *LunarCrush's `stocks` endpoint — the
tool this task specified for a social_dominance/posts_active/galaxy_score sort — hit a per-minute rate
limit and then required interactive re-authentication mid-session ("needs you to sign in again"), so
this list is built from the alternative trackers instead; it is not a LunarCrush-sourced ranking.*

| # | Ticker | Mentions/signal | Sentiment | Why | Dated catalyst? |
|---|---|---|---|---|---|
| 1 | **GME** | 2,311 wk mentions (AltIndex, #1, though −20% WoW); unusual options Sept 24 (+72% call volume) | Bullish | Ryan Cohen $26.4M insider buy; eBay-deal speculation | **Yes** — insider buy + options surge, both dated Sept 24 |
| 2 | **MU** | 119 ApeWisdom / 51 AltIndex (+15.9%) | Bullish | AI memory/HBM shortage supercycle | Yes — recent earnings beat/guide (early Sept) |
| 3 | **ORCL** | 32 mentions but **+3,100%** surge | Mixed | "Oracle calls" YOLO despite bad news | **Yes** — force-majeure notice on a data-center project, dated Sept 24 (negative, but retail bought the dip) |
| 4 | **GOOGL/GOOG** | 54/43 ApeWisdom | Bullish | AI model cycle | Yes — Gemini 4 flagship model release imminent |
| 5 | **NVDA** | 30 ApeWisdom, 24 AltIndex | Neutral/Bullish | AI capex | Weak — Huang comment about doubling chip sales, no new dated print this window |
| 6 | **SPCX** (SpaceX, synthetic/pre-IPO exposure) | 23 AltIndex (+23.3%) | Bullish | Space/AI halo | Yes — confirmed Nasdaq-100 rebalance weight |
| 7 | **BYND** | not on trackers' top list but +95% single session (Sept 17) | Bullish/mania | "2021 throwback" meme rally | Dated but **pump-shaped**: no fundamental news cited by any source found |
| 8 | **DNUT** | same cluster, +20% (Sept 17–19) | Bullish/mania | Rode BYND's coattails | **Pump-shaped**, no company-specific news |
| 9 | **GPRO** | same cluster, +14% (Sept 17–19) | Bullish/mania | Same meme cluster | Real underlying catalyst exists (Starman Optical take-private/relist deal) but the spike pre-dated clean news flow — **partly pump-shaped** |
| 10 | **RKLB** | AltIndex #1 by WoW change, **+550%** mentions | Bullish | Space-sector momentum | **No identified dated catalyst — flag as pump-shaped** (mention surge with no news hook found) |
| 11 | **NBIS** (Nebius) | 52 ApeWisdom, **+160%** | Bullish | AI cloud/GPU-neocloud narrative | **No dated catalyst found this window — flag as pump-shaped** |
| 12 | **BB** (BlackBerry) | 44 ApeWisdom, **+83%** | Bullish | QNX auto-software revival narrative | **No dated catalyst found — flag as pump-shaped** |
| 13 | **SNDK** (SanDisk) | 43/24 on trackers | Neutral | Flash/HBM memory shortage | Narrative-only in this window — **Murat's own repo (Aegis-Finance) already built and then refuted a "SanDisk archetype" by dose-response** (per session memory, S55, 2026-09-24): a promising-looking cell died once tested properly. Treat fresh SNDK enthusiasm with that specific prior in mind. |
| 14 | **AMD** | 52 ApeWisdom (−38% off a prior spike) | Neutral | AI-chip beta to NVDA | Narrative-only, no new dated print this window |
| 15 | **PLTR** | 27/19 on trackers | Neutral | Recurring gov't/AI narrative | Narrative-only, no new dated print this window |

**Read across the list:** the *actual* current WSB/Reddit crowd (per the live `wsb_hot` snapshot and
ApeWisdom) is dominated by **mega-cap AI/tech and macro** (META, SPY, MU, GOOGL, NVDA, ORCL), not by
small speculative names — the small/illiquid "pump-shaped" tickers (RKLB, NBIS, BB) show up as mention
*surges* without accompanying news, which is the closer thing to Murat's "additional stocks to find"
ask, but they are momentum/attention trades, not fundamentally-anchored ones. The BYND/DNUT/GPRO
cluster (Sept 17–19) is the clearest "2021 throwback" mania of the last two weeks and is explicitly
described that way by two independent sources (Sherwood News, Juniorstocks) as well as a third
(newsserp.com) that frames 2026 meme rallies as shorter, more ticker-specific, and increasingly
touching even profitable/dividend-paying names (their example: Wendy's, mid-2026). **Neither DKNG nor
QUBT nor any name in the gambling basket (§4) appears anywhere in these live trackers right now** —
that is itself the headline finding for those two names: whatever is happening with them is not
currently a retail-crowd-driven move.

---

## 4. Gambling / fast-money basket beyond DKNG

One line each, plus the fact that most separates it from the theme. Social-attention column reflects
what the trackers in §3 and the `wsb_hot` OpenClaw quest actually showed (all of these were **absent**
from WSB-hot, ApeWisdom's visible top ranks, and AltIndex's top-20 as of Sept 20–25, 2026) — the
exception is HOOD, which does have a dated, sourced mention-momentum data point.

| Ticker | Social data | Separating fact |
|---|---|---|
| **FLUT** (Flutter/FanDuel) | Not on any current retail tracker; institutional/analyst-driven story instead | Stock is near a 52-week low, **down ~69% from a year-ago peak**, after **four guidance cuts in 2026**; Rothschild downgraded to Neutral on Sept 21 ($169→$119 PT). Its own execs reportedly *hope prediction markets get shut down* (JPMorgan meeting note, Sept 24) — the opposite posture of DKNG. |
| **MGM** | Not on retail trackers; pure M&A-arb story | Stock fell **9–10% on Sept 24** after Barry Diller's People Inc. **withdrew an $18B buyout bid** — a collapsed-deal story, not an operating one. |
| **CZR** (Caesars) | Not on retail trackers | Per Truist (Sept 21), a separate M&A/consolidation process ("Caesars' deal is progressing") is the live catalyst, distinct from Q4 operating trends which Truist calls a "seesaw." |
| **PENN** | Not found in this session's data — flag as a genuine gap, not "quiet by inference" | No fresh (last-30-day) fact retrieved this session; needs a follow-up look before using this basket entry. |
| **RSI** (Rush Street Interactive) | Not found in this session's data — same flag | Same as above. |
| **GENI** (Genius Sports) | Not found in this session's data — same flag | Same as above. |
| **SRAD** (Sportradar) | Not found in this session's data — same flag | Same as above. |
| **HOOD** | **The one name with real, dated social momentum**: AltIndex's Sept 21 weekly recap shows Reddit mentions **+19% WoW**, driven by a viral "found an old account with big gains" nostalgia post plus headline risk from former-employee insider-trading charges | Event-contract revenue **$156M in Q2 2026** — now HOOD's **second-largest disclosed transaction-revenue line, ahead of stock trading ($129M)** — up >10x YoY on 13.6B contracts traded; stock +79.8% over 6 months. Regulatory pushback is real and dated (Connecticut cease-and-desist + ~30 subpoenas, Michigan court order to close sports positions by Oct 9, Nevada case at the Ninth Circuit/on appeal to SCOTUS). |
| **IBKR** | Not on retail trackers (small ~3M-account retail base is itself the point) | Only public name that **owns the exchange outright** (ForecastEx, a CFTC-regulated DCM) rather than distributing someone else's contracts — captures exchange-level (listing/data/clearing) economics, plus a 3.14% APY on open forecast-contract positions that specifically attracts institutional treasurers, not retail gamblers. |
| **COIN** | Not on retail trackers as a PM-specific mention, but scaling fastest of the group | Prediction-market revenue **+106% sequentially** in Q2 2026, crossed **$100M annualized within two months** of full 50-state Kalshi-embedded launch — the fastest product ramp cited in Coinbase's history; leverages a 110M-registered-user crypto-native base. |

**Reading the basket as a whole against Murat's "gambling addiction = durable profit" thesis:** the
public-market winners right now are the **distribution owners with an existing captive user base**
(HOOD, COIN) or the **exchange owner capturing fee economics** (IBKR) — not the two traditional
sportsbooks (FLUT down on repeated guidance cuts and reportedly hoping the whole prediction-market
category gets banned; MGM/CZR trading on M&A headlines unrelated to gambling demand). DraftKings sits
in between: it is the one traditional operator building its *own* exchange (DKeX) rather than either
fighting prediction markets (FLUT) or distributing someone else's (HOOD/IBKR/COIN), which is a
genuinely differentiated strategic bet, but it is also the one paying full customer-acquisition cost
for a customer base HOOD/COIN already had.

---

## 5. What social data can and cannot tell us

Retail attention data (Reddit mention counts, LunarCrush social-volume scores, WSB "hot" rankings) is a
real and measurable **attention** signal, and a large academic literature — starting with Barber and
Odean's finding that individual investors disproportionately buy stocks that have just grabbed their
attention (heavy news coverage, extreme returns, high volume) rather than searching broadly among the
thousands of stocks they could buy — shows that attention reliably drives retail *order flow*. The
WallStreetBets-specific literature confirms the same mechanism in a more extreme setting: Warkulat &
Pelster (2024, *International Review of Financial Analysis*) find WSB attention spurs uninformed,
riskier trading, and that **positions opened when WSB attention on a name is at its peak realize an
average −8.5% holding-period return**, against a positive average return across all positions in their
sample — i.e., the crowd is a contrarian tell more often than a leading indicator. The GameStop-specific
studies (Long, Lucey, Xie & Yarovaya 2023; the Financial Markets & Portfolio Management GameStop paper)
find Reddit posting volume predicts *trading volume* in the following 30 minutes robustly, but find
**no reliable evidence that Reddit sentiment predicts subsequent *returns*** — attention moves activity,
not necessarily price direction, and where price effects are found (e.g., Semenova & Winkler 2025's
Granular-Instrumental-Variable study: roughly +1% average weekly log-return following a doubling of the
odds a very popular WSB post is bullish) the effect is small, concentrated in already-bubble-like
setups, and explicitly framed by the authors as evidence social media can *destabilize* prices rather
than reveal fundamental information. The honest summary: **elevated retail mentions tell you a stock is
about to see more retail order flow and more volatility, not that it is about to go up — and the single
best-replicated finding in this literature is that buying into peak attention is, on average, a below-
average trade.** That is the frame this report used throughout: mention counts and sentiment scores are
reported as a description of what the crowd is doing, never as a reason by themselves to hold, add, or
trim DKNG or QUBT.

---

## Notes on tooling (for the record)

- **OpenClaw**: `health()` returned `READY` at session start (gateway probe ok, profile `muratclaw`
  pinned, `evaluate` disallowed, 0 messaging channels). All 6 quests produced non-empty logs (paths:
  `log_dkng_reddit.json`, `log_dkng_sportsbook.json`, `log_dkng_x.json`, `log_qubt_reddit.json`,
  `log_wsb_hot.json`, `log_qubt_subreddit.json`, all in this scratchpad directory). X/Twitter reads
  failed on an authentication wall (not a domain-policy denial) both times attempted. A Windows
  `cmd.exe` shell-quoting issue (the CLI wrapper runs with `shell=True` on Windows) caused `&`-joined
  query-string parameters to be split and dropped on the first quest; later quests avoided multi-param
  URLs. Mid-session, `backend/services/openclaw_client.py` was found with a live syntax error (another
  process was actively editing it — its mtime was seconds old), so remaining quests were run through a
  small self-contained scratchpad script (`openclaw_quest.py`, same directory) that shells out to the
  `openclaw` CLI directly instead of importing that module. No repo file was read for this beyond the
  initial reference read, and none was modified.
- **LunarCrush**: `topic()` worked for both DKNG and QUBT. `topic_posts()` (needed for linkable top-5
  posts) returned "Limited data mode" both times — this account is not on a paid tier. The `stocks()`
  sort endpoint (specified in the task for the crowding list) hit a per-minute rate limit (4/min) after
  3 calls, then the server reported "needs you to sign in again" on every subsequent call including
  `auth()` — this is an interactive re-authentication this agent cannot perform, so §3's crowding list
  uses ApeWisdom/AltIndex/FearGreedMeter (via Exa) instead, as flagged in that section.
- **Exa** (`web_search_exa`): used for all fundamental/analyst-target/AGA/academic-literature research;
  no issues.
- **Bigdata.com**: tool was loaded but not ultimately needed — Exa's results for SEC filings/earnings
  transcripts were sufficient and came with clean source URLs and dates.
