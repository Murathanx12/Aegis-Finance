# Published news sentiment: descriptive illustrations only

**Metadata-only freeze before CSV access.** Existing C05/C09 context; no new hypothesis, registry trial, backtest, crash-timing test, LLM historical picks, model, returns, exposure or activation. Canon sections 6/7/9/11 and NEGATIVE_RESULTS section 19 remain binding. The coordinator must commit the reviewed protocol and proposed knowledge row before data; independent protocol review precedes values.

## Sources and vintage

Official source: https://www.frbsf.org/research-and-insights/data-and-indicators/daily-news-sentiment-index/

The page displays Updated 10/19/2026 and describes an economics-news index from 24 US newspapers, available since 1980, with trailing geometric weighting and weekly updates. It cites Buckman et al. (2020) and Shapiro, Sudhof and Wilson (2020). The published Chart 1 measure already includes the publisher's aggregation; “raw published” means no additional transformation by us, not raw articles or unsmoothed sentiment.

Exact historical Chart 1 link, extracted from the official HTML without opening:
https://www.frbsf.org/wp-content/uploads/news-sentiment-chart-1.csv?2026-10-23

The query suffix is a URL tag, not a certified observation cutoff or historical vintage. CSV headers, units, values, actual endpoints, completeness, revisions and redistribution terms remain unexamined. This is latest-published descriptive context, not PIT or ex-ante evidence. No Factiva articles, workbook or replication ZIP will be acquired.

NBER requested source: https://www.nber.org/research/business-cycle-dating/business-cycle-dating-committee-announcements-and-historical-business-cycle-dates

The requested page was inaccessible; direct dates/FAQ opens returned 403. Official-domain indexed/cached text corroborated the four protocol-specified peak months at https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions . This limitation is retained, without bypass. NBER peak months are retrospective; its recession-duration convention starts the following month.

## Fixed panels, chosen before values

| Caption | Peak-month day-1 plotting anchor |
|---|---|
| Oil/Gulf-era downturn | 1990-07-01 |
| Dotcom-era recession | 2001-03-01 |
| Global financial crisis era | 2007-12-01 |
| COVID-era downturn | 2020-02-01 |

Day 1 is solely a plotting convention, not a shock, market-peak, exact recession-onset or known-ex-ante date. The 1990 panel does not replace the 1973 oil crisis; 1973 lacks index coverage and stays an explicit gap. March 2001 is not the 2000 Nasdaq peak; December 2007 is not Lehman's failure date.

## Deterministic display rules

Use each anchor plus/minus 365 calendar days, inclusive; x-axis is relative calendar day. Plot the single unambiguous published sentiment series unchanged, with missing dates/nonfinite values shown as gaps, never zero or interpolated. Refuse ambiguous headers/dates, duplicate dates or multiple plausible series; do not choose after inspecting values. No extra smoothing, z-scores, normalization, fit, thresholds, lead/lag calculations, regressions, correlations, averaging across episodes or parameter search.

All four panels share one vertical range: pooled finite minimum/maximum across the fixed windows, with fixed 5% range padding. Constant/absent data or incomplete windows must be disclosed; no substitution or silent omission. No favorable-axis rescaling. These selected historical illustrations cannot establish independent-N, false-alarm performance, direction, causation, novelty, profit or predictive power.

After review/commit, at most one bounded public Chart 1 CSV (1 MiB cap) may be frozen with URL, fetch clock, bytes/hash and coverage checks. A later separate two-page supplement may contain four actual curves plus methods/papers/caveats. No PDF is authored now; no marker exists for that supplement. Accepted 298e and morning R2 remain unchanged.


---

# Phase 2 results: published news-sentiment context

This follows historical pre-data protocol commit `cad483091630aca3a7c415099eba711ad94fd39a`; the four frozen windows and conventions are unchanged. It is a descriptive follow-up, not a new hypothesis or trial.

One public GET occurred post-commit at 21:38 UTC on 25 October 2026: 278,352 bytes, CSV SHA-256 `29a2bbcfd574d48307a2ba2dc8ad3acf420be43ebbea61c7a516aaff28fae6a5`. Pinned coverage records 17,074 unique observations, uniquely month/day/year, spanning 1980-01-01 through 2026-10-18. Nineteen dates are missing globally. Each fixed inclusive +/-365-day window has 731 finite observations and zero gaps. All four share [-0.72, 0.38], using pooled extrema plus 5% padding; no additional transformation of the publisher measure.

The separate two-page PDF is `b17a01fe7301e02c7d60036442ad805f29709113df6779754ab61fec71a76683` (308,155 bytes). Source freeze: `0250945286fa13de3e4c6ef559795e9464ef0c2ffa4840c4ee2cdcd02af24f6a`; final pins: `9d301d04880ae03b0c1bd15d06f7f21915a68b6014e4c58607cec9932f993ddc`. Dewey's full numeric/visual PASS was recorded at 21:50:05 UTC; its path-bound metadata is `e4b85faf0e9eabe9c660b55bf2a5d2d834701272e956444e8b5fde21980cc881`.

1973 remains uncovered; 1990 is not its replacement. March 2001 is not the 2000 market peak. NBER peak-month anchors are retrospective; day 1 is a plotting convention. This is economic-news sentiment, not a direct political-tone or investor-fear measure. No predictive, causal, early-warning, alpha, PIT or novelty claim follows.

Still unmined: historical vintages, original source/availability clocks, forward power and costs. The proposed phase-2 Canon 11 row is for one coordinator-owned local append preserving every old byte. Raw CSV/graphs remain private E-only, outside Git; redistribution terms remain unqualified. No Factiva text or code import. This annotation used metadata only, with no reparse, GET, test, native/model/Git/PDF/Downloads action. Main17 `ad2ced` remains untouched.
