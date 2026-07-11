# Aegis Finance — The Full Picture, v2
### Written for Murathan · 2026-07-12 · by Claude (Fable 5)

---

## 1. What this project is, in plain words

Aegis Finance is a **market-intelligence engine that measures itself in
public**. Three jobs:

1. **It watches the market** — prices, credit, filings, insider and
   congressional trades, ARK's daily fund moves, analyst revisions, news —
   and turns them into readings a person can act on.
2. **It runs experiments on itself** — 7 live paper accounts marked daily
   since June 8, and now **9 pre-registered trials** whose predictions are
   graded against reality on fixed clocks. Failures get published
   (NEGATIVE_RESULTS.md has six entries and we're proud of every one).
3. **It guides a real portfolio** — your holdings, your logged convictions,
   per-position stops and behavioral nudges, and now a weekly
   **smart-money growth basket** built from your own thesis.

The moat is unchanged and uncopyable: anyone can fork the code; nobody can
fork a timestamped forward record.

## 2. What exists now (the delta since the last report is large)

**The honesty machine**
- 7 paper lanes, day 33. **Your conviction lane is the best performer
  (+2.6%)** — ahead of every rules lane and ~15 points ahead of the engine
  managing your same book (mirror, −12.2%). 33 days is noise, not proof —
  but the machine that will *prove or refute* your judgment is finally
  running with real decisions in it.
- 9 registry trials: HRP-vs-EW, mirror, conviction, LPPLS, fragility,
  ATR exits, **congressional trades**, **ARK daily flows**, and (new today)
  **TRIAL-SMARTGROWTH** — your "tech + forecast prices + real investors"
  thesis frozen into a falsifiable weekly top-10 basket vs QQQ, decision
  earliest 2027-01-12.
- The PIT store now ingests **five external-investor decision streams**:
  insider Form 4, analyst revisions, 13F filings, congressional disclosures
  (~150 names), and ARK's full holdings **every trading day**.

**The strategy layer (your "highest ROI" push, honestly built)**
- Portfolio builder: revised Aggressive (momentum tilt, ARKK out — 3-year
  Sharpe 1.39 vs SPY 1.31 in the direction-check) and a new **Max Growth**
  tier (26.5% CAGR vs SPY 20.7% over 3y; 17.1% vs 13.5% since 2015; smaller
  max drawdown than SPY in both windows). Caveat printed on the tin: this is
  a growth/momentum tilt that lags if the regime rotates, and a backtest is
  a direction-check, never proof.
- **Smart-money basket** (weekly, forward-only): momentum 35% + analyst
  revisions 25% + smart money (Congress+ARK) 20% + clipped analyst upside
  20% → top-10 equal weight. It renders as *measured candidates*; if it
  beats QQQ over 6+ months it earns a real paper lane.
- Exit discipline (ATR trailing stops, vol targeting) live in its own lane.

**The brain**
- Optimus brain map v2→v3: a 168-node interactive network — pages as
  bubbles, **every verified fact as an orbiting neuron**, retrieval pulses
  animating the links. Public at optimus-brain-alpha.vercel.app; private
  content is anonymized by construction (a leak of private claim-IDs was
  caught by the pre-deploy scan today and fixed — the process works).
- The engine now **writes a daily market digest the brain ingests** — news,
  regime, signal, fragility, each reading with its age disclosed.

**The product**
- Site restructured: grouped navigation, mobile-friendly spacing, previously
  unreachable pages surfaced, duplicate cards removed.
- Performance: the big pages are now near-instant (stale-while-revalidate +
  background warming); measured: sectors 267s→0.3s, screener pre-warmed,
  stock signal 41s→0.3s repeat.
- **/dev** is a private operator dashboard (deploy health, all-lane equity
  curves, registry, warnings, LLM budget) — now gated behind your access key.

## 3. Direct answers to your questions

**"Is merging dev + brain into the main site, private to me, smart?"**
Half of it. **/dev on the main site behind a key: yes, done** — set
`DEV_ACCESS_KEY` in Vercel, then visit `/dev?key=YOURKEY` once per browser.
It keeps the operator view one URL away without a separate deployment.
**The raw brain: no.** Identity, dispositions, and personal projects should
never sit on a public origin behind a homemade gate — one middleware bug and
it's indexed. The split we have is the right one: the *sanitized* showcase is
public (and linked from /dev), the raw brain stays on your machine with its
local read-only UI. That's not a compromise; it's the design.

**Hosting cost.** The Pro upgrade was almost certainly RAM: FinBERT/torch
keeps ~1-2 GB resident. There is now a switch — set `AEGIS_DISABLE_FINBERT=1`
on Railway and sentiment falls back to the keyword lexicon (every response
labels its method, so the downgrade is visible, never silent). That should
let you try dropping back from Pro. Compute is already tuned (~2 CPU-min/hr).
Vercel: a small Next app, Hobby-tier cheap; Pro only matters there if you
want team features or password-protected previews.

**The paper accounts, read honestly (day 33):** every rules lane is slightly
red in a flat-choppy month (−0.2% to −1.1%), the ATR-exit lane is proving its
point (−0.03%, shallowest), the mirror is deeply red because HRP rebalanced
your volatile small-caps mechanically (−12.2%) — and your conviction calls
are +2.6%. If that spread persists for quarters, not weeks, the engine will
say so with receipts; that is precisely the experiment you wanted.

## 3b. What the competition taught us (fresh research, 2026-07-12)

We surveyed every notable "max ROI" bot and copy-trading engine
(`docs/research/ROI_ENGINES_2026-07-12.md`, fully cited). The blunt version:

- **Nobody publishes an honest live record.** Not ai-hedge-fund, not
  TradingAgents, not FinRL, not QuantConnect's marketplace (whose own
  postmortem admits "strong overfitting"). Academic live benchmarks show LLM
  trading agents *degrade* when they go live. Our forward-lane spine remains
  the thing nobody else has.
- **Copy-trading mostly doesn't work.** eToro-style copying shows no alpha;
  ARK-followers destroyed ~$14B; the congressional edge died with the 2012
  STOCK Act — which is exactly the skeptical prior we pre-registered on our
  own congress/ARK trials. The ONE follower strategy with real published
  support: **low-turnover 13F "best ideas" cloning** (e.g. a Berkshire clone
  earned ~+10.75%/yr post-disclosure in the study period). That's proposal B
  in the research doc — our 13F collector already exists.
- **Realistic expectations:** published anomalies decay ~58% after
  publication; live factor funds deliver −1 to +1.5%/yr net. A 10-20 name
  engine on free data should target **+0 to +3%/yr over SPY with brutal
  multi-year droughts** — anyone promising more is selling. Your great 2026
  is consistent with high-beta exposure plus tracking error; the conviction
  lane is the instrument that will distinguish skill from that, with receipts.
- **Borrow-worthy patterns:** Composer's creation-date-stamped out-of-sample
  accounting (a UI idea for our track-record page) and freqtrade's
  warnings-at-the-point-of-temptation.

## 4. What's still missing (the honest list)

1. **Users: still ~one.** The apparatus measures you alone. Going public
   (below) is the fix, and it is now mostly a product problem, not an
   engineering one.
2. **The crash model stays dark** — retrained twice, still no demonstrable
   skill (the ≥20%-crash label has ~7 events in history; NEGATIVE_RESULTS
   §6). The redesign plan exists (severity/exceedance target, stress-index
   benchmarks); the fragility composite carries the crisis read meanwhile.
3. **Signal clocks are young.** Congress started accruing this week, ARK's
   score self-arms ~mid-Aug, smart-growth takes its first snapshot at the
   next daily check. Real readouts start ~January 2027.
4. **First-visit stock pages** on obscure tickers still take ~40s (fix
   spec'd: parallelize the 15 sequential data fetches — backlog U2).
5. **Two page merges pending** (crash + simulation → outlook, backlog U1).
6. **No mobile-native testing** — spacing and tables are responsive, but a
   real device QA pass hasn't happened.

## 5. Going public — the product plan

**Positioning (what makes it sellable):** "The only investing tool that
shows you its own scorecard." Every competitor shows you data; Aegis shows
you *whether its own advice worked, measured in public, with its failures
published*. Lead with the track-record page, the conviction journal, and the
behavioral nudges. The audience is retail investors who have been burned by
confident tools.

**Phase 0 — hardening (1-2 sessions)**
- Legal surface: "educational, not advice" interstitial + footer on every
  page (texts exist; make them unavoidable once, dismissible after).
- Rate limiting on the API (one abusive scraper = your Railway bill).
- Error tracking (Sentry free tier) + uptime alerts (UptimeRobot exists).
- U1/U2 perf+UX items; a real mobile QA pass.

**Phase 1 — soft beta (invite ~20 people)**
- A landing page that explains the honesty machine in 60 seconds, with the
  live track record embedded.
- Conviction accounts: right now decisions land in ONE shared lane — going
  public needs per-user decision journals (schema exists; add user keys —
  browser-local identity first, no accounts/database, consistent with the
  stateless design).
- Feedback loop: a visible "what's broken/missing" link.

**Phase 2 — public launch**
- Show HN / r/investing / X thread centered on NEGATIVE_RESULTS.md — "we
  published everything that didn't work" is the story that travels.
- The GitHub README (rewritten today) is the developer funnel.
- Keep API keys server-side; publish the SDK for read-only access.

**What NOT to do:** no payments, no "signals subscription", no performance
marketing until at least one pre-registered trial reads out positive on its
own clock (mid-2027). Selling confidence before the receipts exist is the
exact thing this project was built against.

## 6. Rating: **8 / 10** (research platform: 9; product: 6, up from 4)

Up from 7.5: the conviction loop is live with real decisions, the
data-acquisition problem has five streams flowing, strategy work now has a
falsifiable growth thesis instead of a wish, the site is fast and navigable,
and the operator has a cockpit. Still short of 9+: no second user, young
clocks, dark crash model. The path from 8 to 9 is Phase 0+1 above — weeks,
not months.

---
*Everything here is verifiable: docs/TRIALS/, NEGATIVE_RESULTS.md,
docs/BACKLOG.md, the live API, and the /dev dashboard.*
