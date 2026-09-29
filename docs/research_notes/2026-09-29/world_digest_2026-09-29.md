# World digest: reading the news like a human and typing what it implies (2026-09-29)

Licence: PRODUCT_EXPERIMENT. Paper and shadow only. No LLM has authority over capital. Nothing
here changes an order, a size, a cap, a stop or a weight of the live plan.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE yet.** News now has a typed, graded path into a shadow contract, and
the first frozen rows exist. No row is graded yet, so no one can say the digest helps. The one
test that can run today, on past headlines, says **headline-level size buckets carry no
information**.

| item | today |
|---|---|
| best historical net strategy vs market | unchanged (not touched by this work) |
| best forward paper strategy | unchanged; PC-PAPER and the frozen books are not touched |
| independent selector count | +1 SHADOW path (news tilt on SHADOW_BAYES_v0), trust **0** |
| new frozen forecast rows | **95** `news_digest:implication_v0` rows (50 size, 45 direction), 47 tickers, 34 on names **no article mentioned** |
| new actionable finding | (1) **455 of 995** Dow Jones pages the reader "held" in the 36 h window were **archive** pieces, median 65 days old, up to 3.6 years; (2) headline size buckets **lose to the trailing-vol prior** at h=1 (t −2.16 by date) and **tie** at h=5 |
| LLM spend (per-call price, DeepSeek) | digest run 1 **$0.252** (512 calls) + run 2 **$0.077** (48 calls, 1,080 rows from cache) + size test **$0.020** + smoke test $0.002 = **$0.351** |
| provider balance over the runs | $29.22 → $28.75. That $0.47 also includes the other agents running on the same key; this work's own spend is the $0.35 above |
| first grades | 1-session row 2026-10-03; **5-session rows 2026-10-09** (the ledger's generous resolution date); 20-session rows 2026-10-31. Trust can first leave 0 once 3 decision dates are graded (≈ 2026-10-11 if the task runs daily) |

## 1. What existed before this (reused, not rebuilt)

- **The reader's store.** `news_corpus/dowjones/<publisher>/<day>/*.json` (articles, stock pages),
  `news_corpus/media_transcripts/`, `news_corpus/social/`, and 30 headline feeds (yfinance, GDELT,
  Google News in 11 locales, Nikkei Asia, SEC 8-K atom, MarketWatch bulletins).
- **The `source:` claims path** (`dowjones_claims` → `source_registry.write_claims`): one DeepSeek call
  per Dow Jones article, directional claims per named ticker. It grades what a COLUMN said. It does
  not synthesise across articles, carry tone, or name what no article named.
- **`belief_state.make_prediction`** with `ABS_MOVE_EXCEEDS` (a threshold observable), and
  **`forecast_grader`**, which resolves every prefix in `predictions.jsonl` from local bars in the
  daily pass. News-digest rows need no new grader.
- **`llm_analyzer.call_named("deepseek", ..., production_budget=False)`**: the central path with the
  language pin, telemetry and a per-call price from the served model (`deepseek-flash`).
- **`scripts/shadow_bayes_rule.py`** and frozen book `439fd84f869744e0` (SHADOW_BAYES_v0), the base
  the news tilt is applied to. **It is read, never mutated.**
- **`alerts_replies`** (Telegram) and the `AegisAlerts` task pattern (pythonw, STOP file, receipts).
- `expected_return.NOT_READ_BY_DESIGN`: `news_digest:` is now listed there, so the omission is on every
  E[r] receipt.

## 2. What was built

| file | what |
|---|---|
| `backend/services/world_digest.py` | collection (PIT by first-held time, archive filter, dedup), injection guard, stage-1 typed extraction with URL/text-hash cache, stage-2 themes (map over chunks, reduce, link to previous digest) and implications, measured tone, frozen-row writer, grading → trust, SHADOW_NEWS_v0 contract and rule, markdown and short renderers |
| `scripts/world_digest.py` | run / `--dry-run` / `--grade` / `--backtest` / `--schtasks`; run lock; STOP file; CRASHED and REFUSED receipts under pythonw |
| `backend/tests/test_world_digest.py` | 18 offline tests: typing, cache (no second payment), injection (page text never reaches the synthesis prompt), frozen-row writer (threshold = σ√h, vol prior on the row, direction shrunk into [0.45, 0.55], same-day idempotence, named refusals), budget meter, trust = 0 without graded dates, contract immutability, archive filter, Telegram read |
| `backend/config.py` (appended) | `WORLD_DIGEST_*` block; `FORECAST_WRITERS["news_digest"]` (reported, not scheduled-graded) |
| `backend/services/alerts_replies.py` | `news` with no ticker, and bare `digest`, return the latest short digest **read from disk** |
| `backend/services/expected_return.py` | one `NOT_READ_BY_DESIGN` entry |
| scheduled task `AegisWorldDigest` | every 6 h from 12:30 local, `--hours 24`, `$0.90` cap per run, STOP file `news_digest/STOP` |

### How a news item becomes a gradeable number

1. **Collect** everything AEGIS first held in the window. Dated by `first_seen_utc` / `read_utc`, never
   by the article's own date. An item published more than 4 days before AEGIS held it is **ARCHIVE**:
   counted and never a theme.
2. **Extract** (DeepSeek, one call per article or transcript; headlines 20 per call): topic, own-words
   summary, event type (19-value enum), tickers (**kept only if the item names them**; others go to
   `tickers_unverified`), sectors, countries, macro variables, **sentiment, fear/greed of the
   coverage, management confidence, uncertainty**, novelty, and up to 3 forward claims the item itself
   makes. Cached by `sha(url | text | prompt version)`.
3. **Themes**: map over chunks of 260 typed rows, then reduce to ≤10 themes linked to the previous
   digest (new vs continuing). Independent sources are counted per column or host.
4. **Implications** per theme: first-order and second-order paths, including names no article
   mentioned. Each one is typed: subject, direction, size bucket relative to the name's own normal
   move, horizon {1, 5, 20} sessions, confidence, a 2-3 sentence chain, and the observation that would
   contradict it. `mentioned` is computed from the rows, not taken from the model.
5. **Tone** is measured, not asked: mean sentiment (news and social apart), fear/greed, management
   confidence (with its n), agreement between sources (1 − sd/0.5), and how far each named stock
   **already moved** in daily sigma over 1 and 5 sessions, from the bars on disk.
6. **Frozen rows** for each implication on a ticker in the price panel (not a stitched ticker, not
   social-only):
   - a **size row**: `ABS_MOVE_EXCEEDS` at threshold = 63-session daily sd × √h, probability from
     the frozen bucket map (below_normal 0.18, normal 0.3173 = the Gaussian value, above_normal 0.50,
     extreme 0.70). **The vol prior's own probability for the same name, horizon and threshold
     (252-session frequency) is stored on the row as `vol_prior_p`.** This is the control the row
     must beat.
   - a **direction row** (only when up or down): `BEATS_BENCHMARK` vs SPY. The model's number goes
     in `raw_probability` = 0.5 ± 0.25 × confidence. The graded probability is shrunk by 0.2 toward
     0.5, so it stays inside [0.45, 0.55]. The stated reason is on the row.
   - Every row carries price and bar at the moment of writing, sigma, the already-moved sigmas,
     source URLs, the theme, the order, the served model and the prompt hash. Rows are only appended.
     One (day, ticker, observable, horizon, direction) is written once per day.
7. **What to read next** goes to `news_digest/read_next.jsonl` as questions with search queries
   (50 today), state `QUEUED_FOR_READER_NOT_FETCHED`. There is no reader hook to call, so the reader
   agent has to adopt this file.

### Prompt injection

Raw page text reaches exactly one prompt, the extraction, inside `<<<ITEM ... ITEM>>>`. Before that,
lines that address a model ("ignore previous instructions", "system:", role tags) are removed, and so
are the marker tokens. The synthesis only ever sees typed, enum-checked, length-capped fields. A
summary or topic that contains a URL or an instruction pattern is blanked when it is typed. A test
plants a canary sentence in an article and asserts it never appears in any synthesis prompt. On
today's 1,680 items the guard removed 0 lines.

### The shadow path (SHADOW_NEWS_v0, contract `f3b149ea42311760`)

- Base: SHADOW_BAYES_v0 (`439fd84f869744e0`), read only. **Matched twin: the base itself**, i.e. the
  same rule with both trusts pinned at 0. The tilt's own return (Σ (w′ − w) × r) is therefore the
  whole comparison.
- Rule: for a base name with news implications at horizon 5 or 20, w′ = w (1 + trust_dir · d) /
  (1 + trust_size · (s − 1)), where d is the mean of sign × confidence and s the size multiple. A new
  name with d > 0 that is in the panel gets trust_dir · d · 0.05. The result is renormalised to the
  base sleeve's total.
- Trust: size and direction are kept separate. Prior N(0, 0.01²) on the per-date Brier improvement
  over the control (vol prior for size, a 0.25 coin for direction). Trust = clip(posterior / 0.02,
  0, 0.25). With fewer than 3 graded dates it is exactly 0.
- **What the shadow book did differently because of news today: nothing.** Trust is 0, so the tilted
  sleeve equals the base. For illustration only (trust set to one prior sd, which is NOT the rule), it
  would have trimmed JAZZ 0.329 → 0.321 and added about 1% each of AMGN, MU, SMMT, AVGO, BABA, GOOGL,
  AMZN and ASML. Decisions are appended to `news_digest/shadow/decisions.jsonl`.
- `expected_return` and `pc_broker` are untouched. No book was appended to `llm_portfolio`: the roadmap's
  "no new book before 26 Oct" stands. SHADOW_NEWS_v0 is a contract plus a decision log, and the owner
  decides whether it ever becomes a graded paper book.

## 3. The digest itself (run `20260929T030156Z`, items held 2026-09-27 15:01Z → 2026-09-29 03:01Z)

Read **1,680 items** (357 fresh Dow Jones articles, 42 stock pages, 7 transcripts, 1,214 deduplicated
headlines, 60 social pages for tone), after dropping **1,017 archive items** and 336 duplicates.
10 themes, 80 implications. The first run, 3 minutes earlier, lost 600 headlines to truncated JSON
(since fixed). Its 10 themes were the same ones.

| # | theme | news rows / sources | tone (sentiment, fear/greed, agreement) |
|---|---|---|---|
| 1 | US-Iran conflict drives oil surge and a global bond selloff (Brent > $108) | 55 / 26 | −0.24, −0.24, 0.49 |
| 2 | Treasury yields at multi-decade highs (10-y ≈ 5.24%), pressuring markets | 32 / 18 | −0.32, −0.27, 0.58 |
| 3 | AI infrastructure boom: record tech bond issuance and capex | 37 / 19 | +0.26, +0.19, 0.35 |
| 4 | Nvidia's record buyback lifts AI-chip sentiment (NVDA already +0.7σ) | 29 / 18 | +0.52, +0.41, 0.62 |
| 5 | US-China tariff truce; soybeans and rare earths in focus | 18 / 17 | +0.20, +0.13, 0.72 |
| 6 | Meta's enterprise AI platform triggers a software selloff (MDB CEO leaves for Meta, −3.9σ) | 9 / 4 | −0.32, −0.28, 0.18 |
| 7 | OpenAI pauses training; AI safety and regulation debate | 19 / 5 | −0.21, −0.17, 0.39 |
| 8 | AMD buys World Labs for $8.2B in stock | 7 / 7 | +0.34, +0.20, 0.68 |
| 9 | Boeing 737 MAX 10 certification delayed by a software glitch (BA −3.1σ) | 6 / 5 | −0.63, −0.45, 0.78 |
| 10 | Biotech capital markets: AZN-Summit $2B, upsized offerings, trial wins | 28 / 11 | +0.23, +0.17, 0.33 |

**Second-order paths the digest found (names no article in the theme mentioned are marked \*):**

- Oil/Iran → **DAL\*, UAL\*, LUV\*** down (jet fuel 20-30% of cost, hedges partial) and **XOM\*** up.
  Separately, EM importers down ("Indian stocks at a six-month low").
- Yields → **IWM\*** down (floating-rate debt), regional banks and homebuilders down (mortgage rates
  toward 8%), utilities as a bond proxy down, gold down on real yields despite the war. Sector and
  macro claims are typed but **not graded**, because no sector ETF is in the price panel.
- Nvidia's buyback and China possibly allowing ByteDance and Alibaba to buy its chips → **TSM\*** up
  (foundry volume), **BABA** up (cloud capex constraint eases).
- US-China truce → **MOS\*** (fertiliser, from larger soybean plantings) and **MP\*** (unresolved rare
  earths keep a scarcity premium). Also coal exporters, from a 20 Mt purchase commitment.
- Meta enterprise AI → **CRM\*** down (workflow disintermediation). RELX was hit less (−0.6σ).
- OpenAI pause → **AMD\*** down ("a distant second loses first when capex slows"), MSFT down, GOOGL
  up.
- Boeing MAX delay → **GE\*, TDG\*** (content suppliers), **LUV\*, UAL\*** (delivery delays). Safran was
  named but has no bars.
- Biotech → **GMAB** (antibody-platform read-through from AZN-Summit), VKTX dilution
  (refused: social-only in run 2).

The short version is what Telegram `news` now returns; it is in `digest/world_digest_<stamp>.short.txt`.

## 4. The honest test on data already on disk

**Question:** does an LLM size bucket from the news beat the trailing-volatility prior?

**Data:** 600 single-ticker yfinance headlines, 40 per publication date over 15 dates, 2026-09-10 →
09-25. All are after DeepSeek's measured cutoff (2025-12), so the model cannot remember them. Sampled
with the declared seed 20260929. Entry is the OPEN of the first session that opens after publication;
exit is the CLOSE of entry + h − 1. Threshold = 63-session sd × √h. The vol prior is the 252-session
frequency of the same exceedance. Standard errors are by publication date.

| h | n rows / date blocks | Brier model | Brier vol prior | per-date improvement (model − prior) | t by date | dates model better | direction hit vs SPY |
|---|---|---|---|---|---|---|---|
| 1 | 596 / 15 | 0.1445 | **0.1315** | −0.0130 | **−2.16** | 4 / 15 | 50.5% (n 105) |
| 5 | 488 / 13 | 0.1562 | **0.1501** | −0.0034 | −0.51 | 6 / 13 | 53.8% (n 80) |

By year: 2026 only (the one year there is). **There is no discrimination.** At h=1 the realised
exceedance rate is 13.0% for `below_normal`, 16.2% for `normal` and 14.7% for `above_normal`. The
buckets do not rank moves, and the map's higher probabilities for "above normal" are what the Brier
score punishes. Verdict for this variant (headline-only size buckets): **FAILED_VARIANT**, in line with
AMNESIA-2 and X2 (`docs/WHAT_WE_ALREADY_KNOW_LLM.md`). What it does NOT test: the synthesised,
multi-source, second-order implications. Those are the 95 forward rows, first gradeable on
2026-10-09 (5-session) against the vol prior stored on each row.
Receipt: `backend/data/optimus/news_digest/backtest_20260929T030326Z.json`.

## 5. What is weak

- **Direction**: recorded, shrunk, and expected to be worthless. The record says so.
- **The size map is a declared guess.** Today's historical test says the buckets do not rank. If the
  forward rows also fail, the map should be refit (isotonic on graded rows) or the size claim dropped,
  and nothing earned will be lost.
- **Sector and macro claims are ungraded** (no sector ETF or TLT/GLD in the panel). They are about 35%
  of implications. Pulling ~25 ETFs into the bars panel would make them gradeable.
- **Near-duplicate themes** (Iran/oil and yields came out as two themes). Independent-source counts
  count columns and hosts, so two WSJ desks count twice.
- **One run is one date block.** 95 rows written on one morning are one observation of that morning.
- **The archive problem is upstream.** The reader stores months-old articles it reaches from stock
  pages with a fresh `first_seen`. The digest filters them. Other consumers of the store (the `source:`
  claims) should check that they do the same: `dowjones_claims` marks >30-day-old items ARCHIVE, but
  4-30-day-old pieces still write forecasts dated today.
- **The balance delta** is shared with every agent on the key, so the per-call sum is this work's only
  own-spend figure.

## WHAT WORKS / WHAT DOES NOT / HIGHEST-EV EXPERIMENT

**WHAT WORKS:** The pipeline runs for $0.25 over a full 36 h of reading (then ~$0.08 per refresh from
cache). It turns ~1,700 items into typed rows with measured tone, 10 coherent themes and 80 typed
implications, half of them second-order and a third on names no article mentioned. Every
ticker-level implication became a frozen, gradeable row with its own control on the row. Nothing
reached an order.

**WHAT DOES NOT:** Headline-level size buckets do not beat the trailing-volatility prior (h=1 t −2.16;
flat hit rates across buckets). LLM direction stays at a coin (50.5% / 53.8% here, within noise). News
still cannot change a paper order, and by design it will not until graded rows earn trust.

**HIGHEST-EV EXPERIMENT:** Grade the synthesis, not the headline. From 2026-10-09 read the 5-session
size rows against `vol_prior_p` by decision date. Split by `order` (1 vs 2) and `mentioned_in_articles`
(True vs False), because the owner's question, "is there another path they are leading", is exactly
the second-order, not-mentioned slice. It costs $0 to read. The data accrues at about $0.30 a day
from the scheduled task. It answers the owner's question directly, whichever way it comes out.
