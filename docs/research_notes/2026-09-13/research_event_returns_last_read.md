# Research note: before typing the remaining ~143k headlines, which construction does the literature support, and do we already have it?

Written 2026-09-13. Licence: research input to a `PRODUCT_EXPERIMENT` read, not a
`RESEARCH_CLAIM`. Read first: E1 receipt
`backend/data/optimus/night_factory_2026-09-13/E1_event_head_run04.json`,
`scripts/night_e1_event_head.py`, `learner/event_head.py`,
`docs/research_notes/2026-09-11/research_nn.md`,
`docs/research_notes/2026-09-13/research_registry.md`, `NEGATIVE_RESULTS.md` §19.

## What we have today (verified from the receipt, not re-typed)

- 26,003 rows already typed by L2 (LLM extraction, 43-id vocabulary, `typed_l2`
  source) — `n_typed_rows_on_disk: 26003` in the run04 receipt. These cover
  30,275 of 129,983 (symbol, entry_date) cells = 23.3%. Remaining unique texts
  ≈ 163,284 − 26,003 (typed) ≈ 137,000-143,000, matching the prompt's "last
  ~$10 / 143,000 headlines" figure.
- `learner/event_head.py:build_features` already computes, per cell, `direction`
  (mean, signed), `magnitude` (ordinal, from `magnitude_bucket`), and
  `confidence` (mean) as separate aggregated columns, ALONGSIDE the 42-way
  one-hot `event_type × direction` block. **A scalar direction×confidence(×
  magnitude) feature is a strict subset of columns already produced — it needs
  no new code and no new typing to isolate.**
- E1 (run04) tested only the one-hot-type table, at horizon=5 sessions
  (`x_oc_h5`, open of entry session to close of session+4, SPY-excess).
  Result: GBM EVENT−SHUFFLE IC +0.0046, t 1.13, Holm p 0.96 → NO. Head
  (StockMixer_T1) EVENT−SHUFFLE IC +0.0000 → NO. Every net line negative at 25
  bps/side, ~1.3x daily turnover.
- N3 (frozen sentence embedding, same panel family) tested horizon=1 twice
  (2026-09-10, 09-11): IC −0.0035 and −0.0032, both losing to SHUFFLE.
- `scripts/night_e1_event_head.py` line 57: `HORIZONS = (5, 21)` and the CLI's
  `--horizon` `choices=list(HORIZONS)` — **horizon=1 is not even a legal
  argument for the typed-event table today.** The literature-matched horizon
  was never tried with typed features, only with frozen embeddings.

## The post-2020 literature, construction by construction

**Lopez-Lira & Tang, "Can ChatGPT Forecast Stock Price Movements?"**
arXiv:2304.07619 (v6, Oct 2025); SSRN 4412788.
[arXiv abs](https://arxiv.org/abs/2304.07619) ·
[HTML v6](https://arxiv.org/html/2304.07619v6)
- Score: **discrete −1/0/1** ("YES/NO/UNKNOWN" good/bad/uncertain news),
  temperature 0. Not a 43-way type, not even a continuous score — a signed
  trit.
- Horizon: **one session.** If released before 9am ET: same-day open→close.
  If released after close: next session's open→close. Never accumulated over
  multiple days.
- Rebalance: **daily**, ~190% portfolio turnover at baseline (a 25%-fraction
  reduced-turnover variant preserves pre-cost Sharpe and is more cost-robust).
- Universe: 4,123 names with ≥1 major-media/newswire story, Oct 2021–May 2024,
  NYSE/NASDAQ/AMEX, ~85% of CRSP.
- **Decay, with numbers**: annualized Sharpe **6.54 (2021Q4) → 3.68 (2022) →
  2.33 (2023) → 1.22 (Jan–May 2024)** as LLM adoption rose — "consistent with
  improved price efficiency." Cumulative return >300% at 5bps round-trip,
  >100% at 10bps, **unprofitable at 20bps round-trip.** Our own book charges
  25bps *per side* (≈50bps round-trip) — above the threshold at which even
  the strongest documented instance of this effect failed, and that was on
  2021-2023 data before the 2024 decay to Sharpe 1.22.

**Chen, Kelly & Xiu, "Expected Returns and Large Language Models,"**
SSRN 4416687 (2022, updated through 2026; 2023 GSU-RFS FinTech best paper).
[SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416687)
- Feature: dense LLM **embeddings** of news (GPT/LLaMA family), not typed
  categories, not a scalar score.
- Finding: predictability is **short-horizon "news momentum"** — persists
  several days for **small** stocks, dissipates quickly for **large** stocks
  (limits-to-attention/arbitrage). This is the one paper in the set that
  supports a multi-day horizon at all, and only conditionally (small caps).
  It does not support a 42-way typed-event feature either — it is embeddings
  vs. bag-of-words/Word2Vec, which is the N3/E2 comparison this repo already
  ran and closed (IC −0.0032 to −0.0035 vs SHUFFLE).

**Ke, Kelly & Xiu, "Predicting Returns With Text Data" (SESTM),**
NBER w26186 (2019). [NBER](https://www.nber.org/papers/w26186)
- Construction: supervised **sentiment screening + topic model → one scalar
  sentiment score per article**, fit to predict returns directly (not a fixed
  taxonomy of event types). Reported in bps/day, daily long-short. Scalar,
  same family as Lopez-Lira's trit, not one-hot types.

**Boudoukh, Feldman, Kogan & Richardson, "Information, Trading, and
Volatility: Evidence from Firm-Specific News,"** RFS 32(3), 2019 (note: the
prompt's "Kozhan" is a misspelling of **Kogan**).
[RFS](https://academic.oup.com/rfs/article-abstract/32/3/992/5061375) ·
[SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2193667)
- Central number: **identified (type-tagged) news explains 49.6% of overnight
  idiosyncratic volatility vs. 12.4% intraday** — the effect of "news we can
  categorize" is heavily concentrated in the close→open gap, not the trading
  session. This is the strongest evidence in the set that (a) event
  **identification/typing does add explanatory power** over an undifferentiated
  news flag, for volatility — but (b) the horizon where identified news matters
  is the **overnight gap**, not a multi-session open-to-close window.
- This is a volatility decomposition, not a directional-return trading result
  — it does not itself license a one-hot 42-way type table for RETURN
  prediction, only for explaining WHEN variance concentrates.

**Glasserman & Lin, "Assessing Look-Ahead Bias in Stock Return Predictions
Generated By GPT Sentiment Analysis,"** arXiv:2309.17322 — already cited in
`NEGATIVE_RESULTS.md` §19: GPT headline-sentiment long-short is profitable
**only gross**, daily-rebalanced, short-heavy, and the authors' own words are
"not a feasible strategy." Anonymizing tickers *improved* returns (company
knowledge is a distraction) and the edge concentrates in **large** caps —
the opposite tilt from Chen-Kelly-Xiu's small-cap persistence finding, which
the two papers do not reconcile.

**Jiang, Kelly & Xiu, "(Re-)Imag(in)ing Price Trends,"** JF 78(6), 2023.
[SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3756587) — **NOT
found to be a news/text paper.** It is stock-level **price-chart images**
(candlestick patterns) fed to a CNN; no news or LLM text is used. The task
brief's framing of it as "(image/news)" is not supported by the abstract —
flagging as a correction rather than inventing a news connection that isn't
there.

**"Structured Event Representation and Stock Return Predictability,"**
arXiv:2512.19484 (a Dec-2025 preprint, **not yet independently verified as
peer-reviewed** — flagging status honestly). Abstract claims an LLM-derived
structured event representation "outperforms" text-driven baselines
out-of-sample, but the fetched abstract does not state the predicted horizon
or give a direct structured-vs-scalar head-to-head number, so this is
**not found** as a confirming data point for the 42-way-type construction —
it is a lead, not evidence, and should not be cited as support without
reading the full paper.

## The ONE construction the literature best supports

- **Horizon: one session**, entered at the open immediately following
  publication (same-day open→close if published before the open; next
  session's open→close otherwise) — Lopez-Lira & Tang's exact rule, and
  broadly consistent with Boudoukh et al.'s finding that identified news'
  volatility effect is concentrated in the close→open gap, i.e. the FIRST
  session after the news, not session+4.
- **Feature: a signed, confidence-weighted scalar** (direction ∈ {−1,0,+1} ×
  confidence, magnitude optional) — not a one-hot event-type table. Every
  return-prediction paper in this set (Lopez-Lira, Ke-Kelly-Xiu, and Chen-
  Kelly-Xiu's embeddings collapse to a predicted-return scalar too) uses a
  scalar or embedding, never a fixed categorical taxonomy, for the return
  target. The one paper that DOES reward "identified/typed" news
  (Boudoukh et al.) is a volatility decomposition, not a return-direction
  result, and does not license carrying type identity into the RETURN
  regression beyond what direction/confidence already encode.
- **Rebalance: daily**, high turnover (~190%/day in the strongest documented
  case) — closer to our 1.3x measured turnover than not, but costed at 25bps
  *per side* here vs. the 20bps *round-trip* breakeven Lopez-Lira report for
  2021-23 data, before their own 2024 decay to Sharpe 1.22. A construction
  this thin, on data 2+ years staler than ours, at half our cost tolerance,
  should not be expected to clear costs net even if it clears SHUFFLE gross.
- **Universe: broad** (not mega-cap-only) — both Chen-Kelly-Xiu and
  Lopez-Lira find the (gross) effect concentrates in **small** stocks;
  Glasserman-Lin's feasible-net residue concentrates in **large** stocks. No
  consensus universe emerges; report both size buckets separately if this is
  run again, per the repo's own size-tercile discipline.

## Does the direction × confidence feature already exist in our rows, and can the last read run before typing the rest?

**Yes on both counts.** `direction`, `magnitude`, and `confidence` are already
per-cell columns in `learner/event_head.py:build_features`'s output, computed
from the SAME 26,003 typed rows / 30,275 covered cells E1 already used — no
new typing is needed to isolate them from the 42-way one-hot block. What is
missing is not data but **the horizon**: `night_e1_event_head.py`'s
`HORIZONS = (5, 21)` and its CLI `choices` never included horizon=1, so the
literature-matched construction (scalar direction×confidence, one-session
open-to-close, on the *typed* rows) has never actually been run. N3 tested
horizon=1 but only with frozen embeddings, not typed direction/confidence.

**Recommended next read, at $0 marginal spend:** add `horizon=1` to
`HORIZONS`/`choices` in `night_e1_event_head.py`, and add an arm (or a new
run) that uses ONLY `direction × confidence` (± `magnitude`) as the event
feature — dropping the one-hot type-count block — against the same SHUFFLE/
TFIDF/NOTEXT controls, on the existing 30,275 covered cells. This is the
construction the literature actually supports, it costs nothing (rows already
typed), and it directly separates two live hypotheses E1 conflated: "typed
events don't work here" (E1's actual finding, at the wrong horizon and the
wrong feature shape) vs. "a scalar sentiment score at the literature's own
horizon doesn't work here either" (not yet tested).

## What would make typing the remaining ~143,000 headlines worthwhile

Typing more rows raises COVERAGE (23.3% → toward 100% of cells), which raises
the effective cross-sectional N per date (median 326 names/date, ~23% typed
≈ 75 typed names/date today) and therefore the STATISTICAL POWER of whatever
construction is being tested — it does not change which construction is
correct. Concretely:

1. Run the $0 horizon=1, scalar-direction×confidence read above FIRST on the
   26,003 already-typed rows.
2. If it beats SHUFFLE with a t-stat that looks like it is being capped by
   the 23% coverage rather than by a true-zero effect (e.g. a promising point
   estimate with a wide interval, given only ~75 typed names/date to rank
   against ~250 untyped ones diluting the cross-section) — THEN typing the
   rest is worthwhile: it is a power increase on a construction already shown
   to have signal.
3. If the horizon=1 scalar read ALSO fails to beat SHUFFLE (matching N3's two
   horizon=1 embedding failures and E1's horizon=5 type failure), the null
   has now been shown at the literature's own horizon, with the literature's
   own feature shape, and generalizes across three independent constructions
   (embeddings, one-hot types, scalar score) — typing the remaining 143,000
   headlines would not be testing a fourth hypothesis, it would be re-running
   an already-falsified one with more rows. Per the registry's own §5 rule
   family (`docs/research_notes/2026-09-13/research_registry.md` #23, #26),
   "more data on a closed construction" is not what reopens a family — a
   different mechanism class is.

**Bottom line:** the last ~$10 should not be spent yet. There is a $0,
literature-matched read (horizon=1, scalar direction×confidence, on rows
already on disk) that has not been run and that the whole post-2020
literature this session found points to as the best-supported construction.
Run that first; let its result — not the remaining headline count — decide
whether the $10 buys power on a real signal or buys more evidence for a null
already established twice over.
