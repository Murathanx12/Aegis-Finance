# Research v3 — crowd reads (Reddit / StockTwits / X) for the demand/CEO/competition note (2026-09-27)

**Licence: PRODUCT_EXPERIMENT.** Nothing here is a claim of alpha and none of it is an order. This note fills
the CROWD column that `docs/research_notes/2026-09-27/research_v3_demand_ceo_competition.md` could mostly not
read — that note's own browser pass collided with a concurrent Aegis session on the shared `muratclaw`
OpenClaw profile and left `crowd: n/a` on all but five of its 68 names (NVEC, PRAX, SLDP, DKNG, QUBT).

**Tooling.** `backend.services.openclaw_client.browser()`/`read_text()` against the `muratclaw` profile,
driven by a purpose-built crawler (`scratchpad/crowd_crawl.py`: open -> wait 5-15s -> `read_text` -> close,
one tab at a time, no LLM in the loop — pure automation, so it does not draw on the `openclaw_client.agent()`
$1.00 budget at all). Reddit reads `old.reddit.com/search/?q=<query>&sort=new&t=month`; StockTwits reads
`stocktwits.com/symbol/<TICKER>`; X reads the company handle's own timeline logged out. Google Trends is out
of scope per the brief.

**A real Windows/CLI defect found and worked around, not fixed in place (out of scope for a research note):**
`openclaw_client._run()` invokes the `openclaw.CMD` npm shim via `subprocess.run(..., shell=True)` on Windows.
A bare `&` in a URL (e.g. `?q=X&sort=new&t=month`) is torn apart as a command separator by TWO nested layers
of `cmd.exe` (the outer shell, then the `.CMD` batch file's own re-invocation) before it reaches the browser.
The 2026-09-26 session hit this and worked around it by dropping the extra query params entirely. This pass
found the actual fix: replacing each literal `&` with `^^^&` survives both escaping layers and lands on the
page as a literal `&` — confirmed against `old.reddit.com/search/?q=NVEC^^^&sort=new^^^&t=month`, which landed
as `sorted by: new links from: past month`, i.e. the sort/window filters actually applied, not just the bare
query. Worth a real fix in `openclaw_client.py` next session; not touched here since this note's job is the
crowd read, not the client.

**A second real defect, found mid-run, partially fixed, and still not fully trustworthy — this is the honest
finding, not a solved problem.** The crawler's first pass counted any page match containing the ticker string
as a "post," which on common-word/name-collision tickers (MAN, RHI, ACI, PEGA, and non-ticker collisions like
PRAX/r-TheExpanse) pulled in job-ad chatter, grocery-store threads and sci-fi spoilers as if they were
investing discussion — the same failure mode the brief itself warned about for PRAX. A revised parser then
required "investing context" (a finance-flavoured subreddit, or an explicit stock/ticker reference) before
counting a hit, and tags `COLLISION` when the raw string match returns mostly off-topic hits.

**Spot-checking the revised parser's own output (this session, on the raw JSON) shows it is still noisy in
both directions:**
- **False positives survive the fix.** MAN's one "relevant" hit is a r/JobSearchAndResumes thread about
  restaurant-industry hiring ("Is Q4 actually going to be better?") — genuine staffing-market chatter, but not
  anyone discussing ManpowerGroup the stock. ACI's top "relevant" hit (score 332) is a r/povertyfinance grocery
  haul post that happens to mention Albertsons as a store, not Albertsons Companies as an equity. Both were
  tagged `relevant: true, name_only: false` — the "investing context" filter accepted a finance-adjacent
  subreddit (personal finance, job search) as sufficient, which is not the same claim as "this is
  ticker-specific investor sentiment."
- **False negatives may also exist.** An ad-hoc manual read of NVEC earlier in this same session (outside the
  crawler, same `old.reddit.com/search` mechanism) surfaced a real, substantive post in the dedicated `r/NVEC`
  subreddit quoting the CEO's own earnings-call language — the same post the demand note already cited. The
  crawler's run on NVEC this pass returned `n_relevant: 0`. Either the post aged out of the "past month" window
  between the two reads, or the parser is also under-counting genuine small-subreddit discussion. Not resolved
  this pass.

**Conclusion: treat every `n_relevant` count below as a noisy, directionally-useful signal — good enough to
say "materially more/less chatter than X" — and not as a clean, audited measure of ticker-specific investor
sentiment.** This is disclosed rather than silently smoothed over, per this repo's own standing rule.

---

## Coverage note (read this before the table)

**This is a preliminary, partial read — 15 of 68 tickers freshly read (Reddit only), plus 5 tickers reused
from the demand note's own five clean crowd reads (4 of them not already in the 15). StockTwits and X were
not reached in this pass.** The task brief
asked for Reddit + StockTwits + X across all 68 names at a mandatory 5-15s pace between pages. At the
observed pace (~90-180s per ticker once profile-check and read overhead are included — see §D), one clean
source across all 68 names is itself a ~2-3 hour job; three sources sequentially is a 3-4+ hour job. That
crawl is real, is still running in the background as of this writing, and is not something this note should
block on indefinitely rather than deliver an honest partial answer — the same trade-off the demand note itself
made (it shipped with `crowd: n/a` on 63 of 68 names, disclosed rather than hidden, rather than waiting out a
multi-hour browser queue). This note follows the same convention.

**What is real data here, and what is not:**
- **15 Tier-1 tickers read live this session, Reddit only** (in crawl order: NVEC, MAN, RHI, ACI, PEGA, IRDM,
  HELE, SMPL, PRGS, AGYS, NOVT, COGT, VKTX, BBIO, RGEN), with the caveats above.
- **5 tickers reused from the demand note** (NVEC — also re-read live above; PRAX, SLDP, DKNG, QUBT) — these
  were the demand note's own clean crowd reads, carried forward rather than re-read.
- **19 of 68 tickers total have any crowd data. The remaining 49 are marked `IN_PROGRESS`** in the table: the
  crawl is queued to reach them (in ticker-list order — see the ordering in `scratchpad/crowd_crawl.py`), but
  had not done so as of this note's writing. This includes most of the demand note's top-15 ROI list (LEU, MP,
  CCJ, AGIO, IONQ, MU, ABSI — PRGS, AGYS, NOVT, COGT, VKTX and BBIO DID complete, and anchor §C below) and
  every Tier-2 mega-cap.
- **UPDATE, same session, after this note was first published — machine-level incident, not just a data
  loss: `C:` is at 100% full (independently confirmed: `Get-PSDrive C` reports 0 bytes free of ~953 GB), and
  the background crawl is dead as a result.** The crawl (PID 19516) eventually attempted all 68 tickers on
  Reddit (43 OK, 19 COLLISION, 6 EMPTY, 0 walled) and reached StockTwits for 14 more (NVEC..VKTX, 13 OK, 1
  refused on BBIO) before a non-atomic write truncated `scratchpad/crowd_results.json` to 0 bytes (`OSError
  28`, no space left on device). Only the per-ticker PASS/FAIL *status* line survives, in
  `scratchpad/crowd_run.log` — the actual post text, scores, top posts etc. for everything past RGEN (index
  14, where this note's own data ends) is gone, not merely unread. **This is not contained to this task**:
  other zero-byte files appeared the same evening under `backend/data/optimus/` (a dowjones plan/queue file,
  a health receipt, `lab_status.json.tmp`, a night-factory `.tmp`) — other jobs are losing writes too, right
  now, on this machine. `openclaw_client.health()` also now reports all three browser profiles
  (`muratclaw`/`user`/`chrome`) as `absent` and a NEW `messaging_channels: 1` (it read `0` at the start of
  this session) — an anomalous OpenClaw state neither agent configured. **This needs Murat's attention before
  anything else runs on this machine.** Nobody in this session deleted anything or freed space, and nobody
  should attempt to without him — freeing the wrong thing on a 100%-full drive, or restarting OpenClaw into an
  unknown state, is exactly the kind of unilateral "fix" this repo's CLAUDE.md warns against. **Do not re-run
  `crowd_crawl.py` assuming `crowd_results.json` has anything in it** — it is empty. The honest scoreboard
  from the surviving log: of the 68 tickers, 68/68 got at least a Reddit status before the crash, but only
  the 19 in this note's table have any retrievable content — the rest is `OK`/`COLLISION`/`EMPTY` labels with
  no substance behind them anymore.

---

## The crowd table

*Columns: ticker · reddit posts (30d, investing-context only) · top post (date, score/comments) · pump flag
Y/N · StockTwits watchers · StockTwits sentiment · X handle · last company X post (date, topic) · read status.*

| Ticker | Tier | Reddit posts (30d, invest-context) | Top post | Pump | StockTwits watchers | StockTwits sentiment | X handle | Last company X post | Status |
|---|---|---|---|---|---|---|---|---|---|
| NVEC | T1 | 0 | none | N | not yet read | not yet read | not yet read | not yet read | COLLISION (reddit only) |
| MAN | T1 | 1 | "Is Q4 actually going to be better? Because summer was just r" (r/JobSearchAndResumes, 5 days ago, score 8/4c) | N | not yet read | not yet read | not yet read | not yet read | OK (reddit only) |
| RHI | T1 | 0 | none | N | not yet read | not yet read | not yet read | not yet read | COLLISION (reddit only) |
| ACI | T1 | 3 | "$9 mini grocery haul from sales, coupons & pointsGrocery Hau" (r/povertyfinance, 1 day ago, score 332/15c) | Y | not yet read | not yet read | not yet read | not yet read | OK (reddit only) |
| PEGA | T1 | 0 | none | N | not yet read | not yet read | not yet read | not yet read | COLLISION (reddit only) |
| IRDM | T1 | 1 | "Weekly Deep Dive #7 -- +3.1% WoW: New ATH on market moves alo" (r/GrowthStockInvesting, 1 day ago, score 6/0c) | N | not yet read | not yet read | not yet read | not yet read | OK (reddit only) |
| HELE | T1 | 0 | none | N | not yet read | not yet read | not yet read | not yet read | COLLISION (reddit only) |
| SMPL | T1 | 0 | none | N | not yet read | not yet read | not yet read | not yet read | COLLISION (reddit only) |
| PRGS | T1 | 2 | "Chipmakers Sizzle While Nike Sweats It OutUpcoming Earnings" (r/EarningsWhisper, 18 hours ago, score 14/2c) | N | not yet read | not yet read | not yet read | not yet read | OK (reddit only) |
| AGYS | T1 | 0 | none | N | not yet read | not yet read | not yet read | not yet read | COLLISION (reddit only) |
| NOVT | T1 | 0 | none | N | not yet read | not yet read | not yet read | not yet read | COLLISION (reddit only) |
| COGT | T1 | 1 | "Cogent Biosciences Announces FDA Acceptance of NDA for Bezuclastinib..." (r/StockTitan, 11 days ago, score 1/0c — an automated news-bot repost, not organic discussion) | N | not yet read | not yet read | not yet read | not yet read | OK (reddit only) |
| VKTX | T1 | 10 | "Viking Therapeutics Raises $500M in Upsized Stock and Convertible Note Offering After Weight-Loss Drug Surge" (r/MarketFluxHub, 2 days ago, score 2/0c) | Y (1 of 10, a "Tickerade trending list" post) | not yet read | not yet read | not yet read | not yet read | OK (reddit only) |
| BBIO | T1 | 3 | "Interesting times" (r/Livimmune, 11 days ago, score 41/11c — the most organically-engaged post found this pass outside VKTX; other 2 hits are r/MerlintraderPub bot reposts) | N | not yet read | not yet read | not yet read | not yet read | OK (reddit only) |
| RGEN | T1 | 0 | none | N | not yet read | not yet read | not yet read | not yet read | COLLISION (reddit only) |
| IONQ | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| MP | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| LEU | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| CCJ | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| WST | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| AGIO | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| PRAX | T1 | n/a (see note) | collision with r/TheExpanse character; no substantive PRAX-stock discussion found (read 2026-09-27, demand note) | N | not read | not read | not read | not read | COLLISION (reused from demand note / 09-25) |
| QUBT | T1 | n/a (see note) | almost no substantive QUBT-specific content in new/past-month search; no pump language, no real conviction either way (read 2026-09-25, reused) | N | not read | not read | not read | not read | OK (reused from demand note / 09-25) |
| AARD | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| BHVN | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| SLDP | T1 | n/a (see note) | real r/SLDP community (5y old); one substantive post 12d old, 16pts/14 comments, on an 8-K pre-commercial production roadmap; no pump language (read 2026-09-27, demand note) | N | not read | not read | not read | not read | OK (reused from demand note / 09-25) |
| ABSI | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| AMSC | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| HUBS | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| KYTX | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| NTLA | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| PRCH | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| SOC | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| AVPT | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| VRTX | T1 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS (missed by the demand note entirely — see its own §-list vs. its Tier1/Tier2 headers) |
| VRT | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| GEV | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| MU | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| TSM | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| HOOD | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| AVGO | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| CLS | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| BE | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| NVT | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| DKNG | T2 | n/a (see note) | bullish retail narrative (targets $50-100+, Kalshi/Polymarket tailwind) but low-engagement r/DKNG posts + older WSB hype, not fresh high-volume conviction (read 2026-09-25, reused) | N | not read | not read | not read | not read | OK (reused from demand note / 09-25) |
| AAPL | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| AMGN | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| BA | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| BSP | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| CRM | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| HWM | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| LNG | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| VG | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| NOW | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| NVO | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| PSNL | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| SNOW | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| TEM | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| WDAY | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| BN | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| AMZN | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| GOOG | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| GOOGL | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| META | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| NVDA | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| INCY | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| JAZZ | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |
| SNDR | T2 | not yet read | not yet read | n/a | not yet read | not yet read | not yet read | not yet read | IN_PROGRESS |

---

## (A) Most crowded / least watched

**Not answerable in full from this pass — 49 of 68 tickers have no reddit read yet, and none of the 19 with a
read have any StockTwits watcher count, which is the more standard "crowdedness" metric.** On what exists:

- **Most crowded by far: VKTX (10 relevant posts, 2 pump-flagged)** — but read the composition before calling
  it "loud": the vast majority of its posts come from automated finance-alert/news-bot subreddits
  (r/MarketFluxHub, r/Tickerade, r/StockOptionsAlerts, r/TheDesperateTrader, r/Biotechplays,
  r/MerlintraderPub) reposting the Sept 24 $500M raise and generic options-flow/trending-list mentions
  alongside a dozen other tickers each time — not organic retail conversation building around VKTX
  specifically. This is a real, useful distinction this note did not have a column for: **volume and organic
  conviction are different things, and VKTX's count is mostly the former.**
- **BBIO is the second-most-engaged name, and closer to genuine organic discussion**: 3 hits, two of them the
  same r/MerlintraderPub bot pattern, but the third — "Interesting times" in r/Livimmune, 41 points / 11
  comments, 11 days old — is real engagement in what reads as a patient/investor community around
  BridgeBio's approved drug, not a bot repost. Modest in absolute terms, but the most credible organic signal
  found outside VKTX.
- **Next most chatter:** ACI (3 relevant posts, one scoring 332 — but see the false-positive caveat above:
  that's a grocery-shopping thread, not stock chatter), then PRGS/COGT (1-2 each, both weak/bot-adjacent
  hits), then MAN and IRDM (1 each, IRDM's the more credible hit — a growth-stock portfolio update).
- **Least watched among the 19 read:** NVEC, RHI, PEGA, HELE, SMPL, AGYS, NOVT, RGEN, PRAX — all at
  effectively zero genuine investing-context posts in the past 30 days by this pass's own (imperfect) parser.
  Notably, NOVT — a name the demand note itself describes as riding a "very hot" humanoid-robotics theme — is
  just as quiet as the boring dress-rehearsal names. Attention has not yet found it either.
- A real top-10/bottom-10 ranking across all 68 needs the crawl to finish; re-run against
  `scratchpad/crowd_results.json` once it does — the script already tags `n_relevant` per ticker for exactly
  this ranking.

## (B) Loud crowd, weak fundamentals (the pump shape)

Cross-referencing the crowd read above against the demand note's own ROI reads and drop list
(`research_v3_demand_ceo_competition.md` §B and its top-15 table).

**No clean, organic pump case in the 19 names read so far — a real (if preliminary) negative result, worth
stating plainly rather than forcing a match.** The two highest raw "post count" boring-Tier-1 names (ACI at 3,
MAN at 1) both trace to false positives on inspection (a grocery-haul thread, a restaurant-hiring thread —
see the parser caveat above), not stock hype. **VKTX is the one borderline case**: it has real volume and one
post from a "trending list" account flagged `pump`, but on inspection that volume is dominated by
automated news-bot/options-flow-alert subreddits reposting the same $500M-raise headline and generic
multi-ticker "trending" lists (VKTX named alongside AAPL, SOFI, AVGO, TLT, and others in the same post) —
that is bot/aggregator noise around a real, dated corporate event, not a grassroots WSB-style pump. The
demand note's own strongest *structural* pump-risk flag in this shortlist — **QUBT**, explicitly vetoed there
for "target dispersion $10 vs $32... promotional history" — came back from its own crowd read (reused,
2026-09-25) as *quiet*: "almost no substantive QUBT-specific content," no r/wallstreetbets or r/pennystocks
threads in that window. That is itself informative and consistent across two independent reads two days
apart: whatever made QUBT's promotional history a red flag, there is no evidence of an active pump happening
in the crowd data right now — the risk flagged in the demand note is a structural/historical one (wide
analyst dispersion), not a live mania this pass can see.

**The names most likely to actually show a genuine organic pump shape have not been read yet** — the crawl
has not yet reached the small/thin-coverage names with retail-favourite characteristics (AARD, BHVN, KYTX,
SOC, PRCH, SLDP's dup-check aside). This section should be re-run once those land; a negative result on 19
mostly biotech/industrial/"boring" Tier-1 names does not answer the question for the names where a genuine
retail pump shape would actually be expected.

## (C) Quiet crowd, strong demand-note rating (the undiscovered shape)

The shape Murat has said he wants found: names the demand note rates as top-15/solid ROI candidates that
carry little to no retail chatter — i.e. the fundamentals thesis has not yet become a crowd story.

**PRGS, AGYS, and NOVT — three real top-15/solid-ROI names from the demand note, not marginal ones, all
essentially undiscovered by the crowd. COGT is a weaker fourth case.**

- **PRGS (Progress Software)** — demand note: "fastest software grower here (+15.5%), 30%+ FCF margin, Strong
  Buy, Oct 21 catalyst... **Solid Tier-1 ROI candidate**," #13 in the top-15 table. Crowd: the ONLY reddit hit
  in the past month is a generic r/EarningsWhisper earnings-calendar roundup post ("Chipmakers Sizzle While
  Nike Sweats It Out") that likely lists PRGS among many names reporting that week — not substantive discussion
  of the company. Effectively zero real retail awareness of the +45.4%-upside, Strong-Buy thesis.
- **AGYS (Agilysys)** — demand note: "accelerating growth, Strong Buy, real upside, clean balance sheet...
  **Solid Tier-1 ROI candidate**," #12 in the top-15 table, with its Oct 26 catalyst landing exactly at the
  rehearsal book's own check date. Crowd: literally zero relevant hits (`COLLISION` status, meaning the raw
  string match itself returned little). No retail conversation found at all.
- **NOVT (Novanta) — the important one, because it directly answers the "is this just the boring names"
  objection.** Demand note: "real robotics-demand story... humanoid-robotics buildout" — riding a genuinely
  "very hot" 2026 theme, #14 in the top-15 table with a servo-drive order for "hundreds of robots in
  testing." Crowd: zero relevant hits, `COLLISION` status — exactly as quiet as PRGS/AGYS or the boring
  dress-rehearsal names. **A name in one of the hottest live themes in the market is not yet a crowd story
  either.** This is the strongest single data point for the "undiscovered" shape in this pass.
- **COGT (Cogent Biosciences)** — #7 in the top-15 table (12-analyst Strong Buy, $792M cash runway). Crowd:
  one hit, and it is an automated r/StockTitan news-bot repost of the FDA NDA-acceptance headline (score 1,
  0 comments) — a wire-service echo, not discussion. Counts as "technically not zero" but functionally still
  undiscovered.

**Read with real caution given the sample size (19 of 68), but the finding held up better than expected on
its own first stress-test:** the open question after the first 10 tickers was whether quiet crowd + strong
fundamentals was just an artefact of reading only "boring" staffing/grocery/consumer names — a hot-theme name
(NOVT) reading exactly as quiet as the boring ones is direct evidence against that objection. **PRGS, AGYS,
NOVT (and, more weakly, COGT) are the names in this pass that best match the shape Murat asked for: a real,
demand-note-validated ROI thesis that the retail crowd has not found yet.** VKTX and BBIO are the interesting
contrast cases: both also top-15 (#3 and #2 respectively), and both show more crowd engagement than the other
four — VKTX heavily (but mostly bot/aggregator volume, §A), BBIO modestly (one real 41-point organic thread).
So within this small sample, the top-15 list already splits three ways: **"bot-loud but not organically
found" (VKTX), "modestly found, organically" (BBIO), and "genuinely not yet found" (PRGS, AGYS, NOVT,
COGT)** — which is a more useful frame than a single quiet/loud label. It is also a plausible size/maturity
story: VKTX and BBIO are the two largest, most analyst-covered names in this batch (20 and 22 analysts
respectively per the demand note); PRGS, AGYS, NOVT and COGT are smaller and thinner-covered. The rest of the
top-15 (LEU, MP, CCJ, AGIO, IONQ, MU, ABSI) still needs reading before this size/discovery relationship can be
trusted as more than a 6-name coincidence.

## (D) Footprint

- **Pages read this pass:** 15 tickers x 1 reddit page = 15 clean, kept reddit reads, plus ~7 reddit reads
  from a first crawl run that was discarded (killed) after its parser turned out to count name-only matches
  as crowd signal — those pages were genuinely fetched but their extracted data was not trustworthy enough to
  keep. Add ~8 ad-hoc manual page opens (this session, debugging the URL-escaping defect and the tab-tracking
  logic: NVEC reddit x2, MAN reddit x2, NVEC StockTwits x1, a wrong X-handle guess for MP Materials that
  404'd x1, plus closes). **Total: roughly 30 page loads**, of which 19 tickers' worth of data made it into
  this note (15 fresh + 4 reused non-overlapping). The crawl continued producing new tickers (BBIO, RGEN)
  while this note was being written, which is itself evidence of the ~90-180s/page pace claimed below.
- **Pages/hour:** slow. Once the browser-profile assert/attach overhead and the mandatory 5-15s pace are
  included, a single reddit page-and-read cycle ran **~90-180 seconds** end to end — roughly **20-25
  pages/hour** sustained. At that rate the full brief (68 tickers x up to 3 sources, ~150-200 pages) is a
  **3-4+ hour job**, confirmed independently by the process actually running it. This is a real constraint on
  what "crowd-check 68 names" can mean inside one session, not a tooling failure — the 5-15s pace itself is
  most of the cost.
- **What walled/blocked this pass, and what did not:**
  - **WebFetch cannot reach any of the three target sites at all** — `old.reddit.com` returned an explicit
    "unable to fetch" refusal, `stocktwits.com` returned HTTP 403, `x.com` returned HTTP 402. This is the
    opposite of the demand note's own finding for financial-data sites (stockanalysis/finviz/investing.com/
    EDGAR, where it "worked cleanly and fast, no pacing needed") — **for social platforms, the OpenClaw
    browser is not a slower alternative to WebFetch, it is the only option that works at all.**
  - **The `muratclaw` browser profile was NOT in concurrent use by another Aegis session this pass** (unlike
    the demand note's own experience four hours earlier) — `browser --json status` showed it `stopped` with
    zero open tabs at the start. The contention this pass hit was a **different, narrower version of the same
    failure mode**: two agents *from the same task* (this note's own author and a fork it spawned for a small
    sub-task) ended up independently driving the same shared profile at the same time, closing each other's
    tabs, before the roles were sorted out. **The lesson generalizes beyond "watch for other sessions" to
    "a single crowd-check task should be executed by exactly one process end to end" — splitting even one
    task's own browser work across cooperating agents recreates the exact contention problem the profile
    ownership rule exists to prevent.**
  - **No genuine login wall or CAPTCHA was hit on any site reached this pass.** `old.reddit.com/search`
    rendered fully logged-out; the one StockTwits page manually checked (NVEC) rendered real content
    logged-out; the one X page manually checked was a 404 (wrong handle guess, not a wall).
  - **WebSearch's 200-call session budget was exhausted before the X-handle-verification sub-task could use
    it** — the same failure the demand note itself hit for CEO bios. The X leg of this crawl (once it gets
    there) will run on unverified handle guesses already baked into `crowd_crawl.py` and simply record `404`
    for wrong guesses rather than spend more pages chasing alternate spellings.
- **The real, reusable fix found this pass:** the `&`-in-URL defect (see the top of this note) — worth
  porting into `openclaw_client.py` itself next session, since every future Reddit/site read with a
  multi-param query string will otherwise silently drop everything after the first `&`.
