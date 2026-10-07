# CARD: short-interest

## Index fields
- topic: Short interest
- mechanism_class: information_asymmetry, limits_to_arbitrage
- dataset_status: DOCUMENTED_NOT_TRACKED

## Citation
Ekkehart Boehmer, Zsuzsa R. Huszar, Bradford D. Jordan (2010), "The good news in short interest," Journal of Financial Economics, 96(1): 80-97. DOI 10.1016/j.jfineco.2009.12.002.
Verified by fetching https://ideas.repec.org/a/eee/jfinec/v96y2010i1p80-97.html on 2026-10-07 (authors, title, journal, volume, issue, pages and abstract read; RePEc prints no DOI). The DOI comes from a Crossref title query fetched the same day, https://api.crossref.org/works?query.bibliographic=The+good+news+in+short+interest+Boehmer+Huszar+Jordan&rows=3 (third record returned: JFE 96(1), pages 80-97, 2010). The publisher page could not be read: doi.org resolves the DOI (HTTP 302) to an Elsevier linking-hub page that returned only a "Redirecting" stub, the SMU repository copy returned 503 and SSRN returned 403. The paper's tables, sample period and alpha magnitudes were therefore NOT read in this pass.

Paul Asquith, Parag A. Pathak, Jay R. Ritter (2005), "Short interest, institutional ownership, and stock returns," Journal of Financial Economics, 78(2): 243-276. DOI 10.1016/j.jfineco.2005.01.001.
Verified by fetching https://ideas.repec.org/a/eee/jfinec/v78y2005i2p243-276.html on 2026-10-07 (bibliographic fields only; RePEc prints no abstract or DOI), https://api.crossref.org/works/10.1016/j.jfineco.2005.01.001 (title, authors, journal, volume, issue, pages, year and DOI agree) and the in-press journal PDF hosted by the University of Florida, https://site.warrington.ufl.edu/ritter/files/2015/04/Short-interest-institutional-ownership-and-stock-returns-2005-08.pdf, read as text (abstract, sample, DOI line and the running head "Journal of Financial Economics 78 (2005) 243-276"). The NBER working paper https://www.nber.org/papers/w10434 (fetched) carries the earlier title "Short Interest and Stock Returns".

Ekkehart Boehmer, Charles M. Jones, Xiaoyan Zhang (2008), "Which Shorts Are Informed?," Journal of Finance, 63(2): 491-527. DOI 10.1111/j.1540-6261.2008.01324.x.
Verified by fetching https://ideas.repec.org/a/bla/jfinan/v63y2008i2p491-527.html on 2026-10-07 (authors, title, journal, volume, issue, pages, DOI and abstract read) and https://api.crossref.org/works/10.1111/j.1540-6261.2008.01324.x (agrees).

David E. Rapach, Matthew C. Ringgenberg, Guofu Zhou (2016), "Short interest and aggregate stock returns," Journal of Financial Economics, 121(1): 46-65. DOI 10.1016/j.jfineco.2016.03.004.
Verified by fetching https://ideas.repec.org/a/eee/jfinec/v121y2016i1p46-65.html on 2026-10-07 (authors, title, journal, volume, issue, pages, DOI and abstract read) and https://api.crossref.org/works/10.1016/j.jfineco.2016.03.004 (agrees). The Elsevier link from doi.org returned only a redirect stub, so the sample period and index construction used below come from the secondary summary at https://cxoadvisory.com/short-selling/aggregate-short-interest-and-future-stock-market-returns (fetched 2026-10-07), not from the paper's text.

Joseph E. Engelberg, Adam V. Reed, Matthew C. Ringgenberg (2018), "Short-Selling Risk," Journal of Finance, 73(2): 755-786. DOI 10.1111/jofi.12601.
Verified by fetching https://ideas.repec.org/a/bla/jfinan/v73y2018i2p755-786.html on 2026-10-07 (authors, title, journal, volume, issue, pages, DOI and abstract read), https://api.crossref.org/works/10.1111/jofi.12601 (agrees) and the working-paper version dated 15 October 2014 (WFA Center for Finance and Accounting Research Working Paper 13/004), https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2014/03/riggenberg.pdf, read as text for the data description. A 2026-09-26 house note (`docs/research_notes/2026-09-26/research_ssrn_arxiv_signals_and_oss_comparison.md`, row 8) lists this paper as JFE; the DOI registry and RePEc both say Journal of Finance.

## The claim, in one sentence
Relatively heavily traded stocks with low short interest earn statistically and economically significant positive abnormal returns, often larger in absolute value than the negative returns of heavily shorted stocks, because the public information in a quiet short book is incorporated into price only slowly (Boehmer, Huszar and Jordan 2010).

## Mechanism: why the inefficiency could exist, and who is on the other side
Source says (the counterparty identifications are my reading, not the sources' wording). Two stories
compete and the sources do not settle between them. The constraint story
(Miller 1977, as framed by Asquith, Pathak and Ritter 2005): when demand to short is high and
lendable supply is low, pessimists cannot trade on their view, price reflects only the optimists, and
the stock stays overvalued until the constraint relaxes. The authors proxy demand with short interest
and supply with institutional ownership and call a stock constrained when both bind. The counterparty
is the marginal optimistic holder, and the arbitrageur who would correct the price cannot borrow the
stock. The information story (Boehmer, Jones and Zhang 2008): short sellers are informed,
institutional non-program short sales most of all, so heavy shorting is informed pessimism (their
measure is daily short SALES from proprietary order data, not reported short interest). Boehmer, Huszar and
Jordan (2010) add that the informative side of PUBLIC short interest is the quiet side, and say their
results cast doubt on existing theories of the impact of short sale constraints; the counterparty to
the low-short-interest outperformance is the long investor who treats an absence of informed shorting
as uninformative. Two extensions: Rapach, Ringgenberg and Zhou (2016) read the aggregate level as
short sellers anticipating aggregate cash flows (their abstract names a cash-flow channel), and
Engelberg, Reed and Ringgenberg (2018) argue that fee and recall risk limit the arbitrageur, so stocks
with more short-selling risk keep lower returns; the counterparty there is the risk-averse short
seller who has to be paid a premium for bearing it.

## Assumptions
- A short-interest print is public before anyone trades on it. It is a position at a settlement
  date, published more than a week later, so any series keyed on the settlement date is a look-ahead.
- Borrow exists for a short leg at a known cost. The house bar is a long-only, cost-charged book under
  a mandate that forbids shorting (NEGATIVE_RESULTS.md section 28), and Muravyev, Pearson and Pollet
  (2025, below) report that short-leg anomaly returns do not survive borrow fees, which is why this
  card concerns long-only and avoid-side constructions.
- For the low-short-interest long-leg claim: a quiet short book is information and not a proxy for
  size, quality or index membership, and turnover is comparable across venues (the house panel
  carries an unresolved Nasdaq volume double-counting flag).
- For the constraint story: lendable supply is thin for only a minority of names. Asquith, Pathak and
  Ritter's abstract says that for the overwhelming majority of stocks short interest and
  institutional ownership make constraints unlikely, which is consistent with the effect living in a
  small, small-cap corner (their equal-weighted 215 against value-weighted 39 basis points).
- No closer substitute: institutional ownership and option skew carry overlapping negative-conviction
  information (NEGATIVE_RESULTS.md sections 26 to 28 measured both).

## Measurable variables: the precursor observable BEFORE the move
Source variables: the short interest ratio (shares sold short over shares outstanding; Asquith,
Pathak and Ritter), a low-short-interest by high-turnover double sort (Boehmer, Huszar and Jordan),
an aggregate index built from the equal-weighted short interest ratio, detrended and standardised
(Rapach, Ringgenberg and Zhou, per the secondary summary), and loan fee, utilization and recall risk
from Markit (Engelberg, Reed and Ringgenberg). House variants: days to cover (short interest over
the 21-session average daily share volume), a 3-month log change in short interest, and Asquith's
conjunction of high short interest AND low institutional ownership, whose supply side would come from
13F holdings under the house's 45-day filing-lag convention (`backend/services/crsp_pit_bridges.py`,
`F13_LAG_DAYS = 45`).

Point-in-time is the whole point. The observable before the move is the LAST PUBLISHED print as of
the decision date. FINRA's own page (https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest,
fetched 2026-10-07) says firms report short interest twice a month, due by 6 p.m. Eastern on the
second business day after the settlement date, and its schedule rows publish a 14 November 2025
settlement on 25 November and a 15 December 2025 settlement on 24 December (seven business days after
settlement by my count of those rows). The house uses three different lags for the same data:
`observed_at = datadate + 14` calendar days in Book A (the measured median of a 10 to 26 day range,
`docs/research_notes/2026-09-12/probe_short_interest.md`), `SI_LAG_DAYS = 26` in
`backend/services/crsp_pit_bridges.py` (the conservative end), and settlement plus 8 business days in
`backend/services/official_sources.py`. A cell must declare one. This card's deciding arm would be 26
days with 14 as the sensitivity, because the 14-day stamp is optimistic for roughly half of the prints
by construction (`backend/data/optimus/short_interest/comp_sec_shortint_receipt.json`, field `pit_rule`).

Do not conflate the variables. FINRA's daily short-sale VOLUME files count executions flagged short on
a day. FINRA's information notice (https://www.finra.org/rules-guidance/notices/information-notice-051019,
fetched 2026-10-07) states that short sale volume data does not, and is not intended to, equate to
reported bi-monthly short interest information, and that the volume data is published separately for
each FINRA reporting facility and each exchange rather than consolidated. The house service documents
that most of that volume is market makers shorting to fill customer buys
(`backend/services/finra_short_volume.py`). It is a different variable with its own corpse (below).

## Sample period and markets
- Boehmer, Huszar and Jordan (2010): the abstract gives no sample. The house documents
  (`docs/TRIALS/TRIAL-DRAFT-A-si-low-turnover-high-v1.md` section 1 and
  `docs/research_notes/2026-09-11/ideas_round2/angle3_evidence.md` item d2) carry US stocks, 1988-2005,
  taken from a practitioner write-up of the tables. This pass could not read the tables, so that span
  is the house's claim and not a verified fact.
- Asquith, Pathak and Ritter (2005), in-press journal text read: NYSE-Amex stocks 1980-2002 and
  Nasdaq stocks from June 1988 to December 2002; the headline result is for 1988-2002.
- Boehmer, Jones and Zhang (2008), abstract: proprietary NYSE order data, 2000 to 2004. This is short
  SALES by account type, not reported short interest.
- Rapach, Ringgenberg and Zhou (2016), secondary summary: monthly mid-month short interest and S&P 500
  excess returns, January 1973 to December 2012; the out-of-sample window it reports is 1990-2012.
- Engelberg, Reed and Ringgenberg (2018), working-paper text: Markit equity lending data, about 6.7
  million firm-day observations for over 4,500 US equities from 1 July 2006 to 31 December 2011, a
  5.5-year sample.

## Effect size as published
- Asquith, Pathak and Ritter (abstract, verified): constrained stocks (high short interest, low
  institutional ownership) underperform over 1988-2002 by 215 basis points per month equally weighted
  and by an insignificant 39 basis points per month value weighted.
- Boehmer, Jones and Zhang (abstract, verified): heavily shorted stocks underperform lightly shorted
  stocks by a risk-adjusted 1.16% over the following 20 trading days (15.6% annualized); stocks heavily
  shorted by institutional non-program accounts underperform by 1.43% the next month (19.6% annualized).
- Boehmer, Huszar and Jordan (abstract, verified): qualitative only. Heavily traded stocks with low
  short interest earn positive abnormal returns "often larger (in absolute value) than the negative
  returns observed for heavily shorted stocks", and the high-short-interest effect "can be transient
  and of debatable economic significance". The magnitudes the house design leans on (about 1% a month
  alpha for the low-short-interest leg, about 1.3% a month for a long-only portfolio, holding for up to
  six months) come from a practitioner write-up that the house itself flagged as unverified against
  the JFE tables; they are not restated here as the paper's numbers.
- Rapach, Ringgenberg and Zhou (abstract, verified): annual R-squared of 12.89% in sample and 13.24%
  out of sample, and utility gains of over 300 basis points per annum for a mean-variance investor. The
  secondary summary adds that a one standard deviation rise in the index goes with a 6% fall in
  annualized future excess market return.
- Engelberg, Reed and Ringgenberg (working-paper text): a long-short portfolio on fee risk earns a 9.7%
  annual three-factor alpha and one on recall risk 8.6%. The published abstract states the direction
  (more short-selling risk, lower returns, less price efficiency, less short selling) without numbers.

## Known failure modes and post-publication decay
The two standing references, McLean & Pontiff (2016) and Harvey, Liu & Zhu (2016), are carried with
their numbers in the card `post-earnings-announcement-drift` and are not re-derived here.
Mechanism-specific evidence:
- The source papers warn about themselves. The NBER abstract of Asquith, Pathak and Ritter says many
  documented short-interest patterns are not robust and that inferences from short sub-periods can
  mislead (high short interest stocks underperformed strongly in 1988-1994, while Nasdaq ones did not in
  1995-2002). Their equal-weighted against value-weighted gap (215 against 39 basis points) says the
  effect lives in small names. Boehmer, Huszar and Jordan call the high-short-interest effect
  transient. The secondary summary of Rapach, Ringgenberg and Zhou says the out-of-sample gain was
  concentrated in the late 1990s and 2008-2009 and weak in 1990-1995 and 2000-2007, which is the
  house's "which part of the sample is it" question (CLAUDE.md protocol 11) already visible in the
  source.
- The short leg is expensive. Muravyev, Pearson and Pollet (2025), "Anomalies and Their Short-Sale
  Costs," Journal of Finance 80(6): 3639-3694, DOI 10.1111/jofi.13501 (Crossref record fetched
  2026-10-07), report that the average of 162 long-short anomalies earns 0.14% a month before
  short-sale costs and -0.01% after, and remains unprofitable when high-fee observations are excluded.
  The same authors (2022), "Is There a Risk Premium in the Stock Lending Market? Evidence from Equity
  Options," Journal of Finance 77(3): 1787-1828, DOI 10.1111/jofi.13129 (Crossref record fetched
  2026-10-07), find only a minimal premium for borrow-fee risk, which bears on whether Engelberg, Reed
  and Ringgenberg's short-selling-risk result is a tradeable premium.
- The house's own readings in the post-publication era are negative on the long side (see the corpse
  section).
- Panel defects the house already flagged in the build receipt: Nasdaq volume double-counting is
  unresolved, so turnover and days to cover are not comparable across venues; the CCM link keeps only
  59% of rows (match rate 0.5914; per-year join rates 0.62 to 0.82); and `observed_at` uses one fixed
  median lag rather than each print's release date.

## What AEGIS has on disk to test it
Tracked in git (bytes you can open in this checkout):
- `backend/data/optimus/short_interest/comp_sec_shortint_receipt.json`: the build receipt of the
  Compustat-based panel, built 2026-09-12. Current table 5,279,203 rows and legacy table 4,770,658 rows,
  6,776,917 after de-duplication, 3,707,730 linked to CRSP permnos, 2,211,042 panel rows across 1990-2024
  in 35 yearly files (per-year permnos from 1,772 in 1990 to a peak of 5,109 in 2004, and 3,793 to 4,613
  across 2011-2024), stamped `observed_at = datadate + 14`. The receipt describes the panel; it is not
  the panel.
- `backend/data/optimus/finra_short_volume/manifest.json` and two `pull_receipt_*.json` files:
  19,645,674 rows of FINRA short-sale VOLUME over 2,049 dates, 2018-08-01 to 2026-09-25, with per-year
  sha256. Receipts only.
- Receipts of runs that consumed the panel:
  `backend/data/optimus/first_books/replay/si_low_turnover_high_v1_2026-09-21T173526Z.json` (and two
  earlier files), `backend/data/optimus/night_factory_2026-09-13/A_corner_run01.json`,
  `backend/data/optimus/night_factory_2026-09-13/LEADERBOARD.md`, and the CRSP-era board
  `backend/data/optimus/crsp_rebuild/bridges_board_BR_FLAT_2026-09-29T1535Z__FT_2026-10-07_1__2026-10-06T182820Z.json`.
- `backend/data/optimus/official/receipts/run_20260929T134706Z.json`: the forward FINRA short-interest
  collector landed two settlements, 2026-08-31 (22,569 rows) and 2026-09-15 (22,595 rows). Two
  settlements are a trickle, not a research panel.
- Code: `scripts/short_interest_panel.py`, `backend/services/crsp_pit_bridges.py`,
  `backend/services/official_sources.py`, `backend/services/finra_short_volume.py`, and
  `backend/services/short_interest.py` (a live yfinance snapshot with no history).

Documented but not tracked (the bytes are gitignored, `.gitignore` lines 74, 368 and 402, so presence
and row counts cannot be confirmed from this checkout):
- `backend/data/optimus/short_interest/comp_sec_shortint/` yearly parquet files, 1990-2024. The tracked
  receipts dated 2026-09-12 to 2026-10-06 were produced from them, so the panel existed on the data
  machine on those dates; that is an inference from receipts, not an observation.
- `backend/data/optimus/wrds/bulk/comp__sec_shortint.parquet` (5,279,203 rows, settlement dates
  2006-07-14 to 2026-08-14) and `comp__sec_shortint_legacy.parquet` (4,770,658 rows, 1973-01-15 to
  2024-12-31), per `docs/research_notes/2026-09-12/probe_short_interest.md`.
- The `backend/data/optimus/finra_short_volume/` year parquets: `docs/DATA_CATALOG.md`, generated
  2026-10-07T01:00:01Z on the data machine, lists the directory at 16 files and 276.0 MB.
- `backend/data/optimus/wrds/tr13f_s34_1996.parquet` through `tr13f_s34_2024.parquet`: the tracked meta
  files give the columns and per-year rows (1,376,529 for 1996; 4,839,107 for 2024).

Not found: any securities-lending fee, utilization or recall series. The house notes
(`docs/research_notes/2026-09-11/ideas_round2/angle3_evidence.md` item d4 and
`docs/research_notes/2026-09-26/research_ssrn_arxiv_signals_and_oss_comparison.md` section 2) record it
as paid (Markit/IHS, S3, Ortex) and not on disk. The QUEUE row's statement that short interest is "not
confirmed on disk" is superseded: the panel is documented and was used.

## The falsifiable question and the declared primary metric, with costs
The question the house already asked and closed (Book A, `si_low_turnover_high_v1`): do names in the
low-short-interest by high-turnover double-sort cell of the $3M-dollar-volume-eligible CRSP
cross-section, entered on the publication-lagged print and held one month, beat a random-universe,
turnover-matched twin by more than the 0.685%-a-month minimum detectable effect over monthly date
blocks 2011-2024? The deciding metric used was net monthly excess return versus the random twin with a
Newey-West lag-2 t on the date blocks, priced at a flat 25 bps a side (an interim ruler,
`flat_25bps_pending_5c`) where the unsigned draft had declared 5 plus 1 bps a side. The only variant
this card would pass to a future registration is the one never asked, drafted in needs_evidence 1:
Asquith, Pathak and Ritter's constrained-name conjunction used as an exclusion screen on a host book.
It would be declared as a RESURRECTION-shaped cell naming a new instrument, priced by the bridges-board
convention (`backend/services/matched_twins.py`, `round_trip_spread`: the larger of Corwin-Schultz
capped at 20% and the 6/10/18/35 bps band, charged on traded weight) with the 26-day lag as the
deciding arm. This is a draft for a future pre-registration, not a registration.

## Whether a corpse already exists here
Yes, on the long side. In the order the intake README prescribes (NEGATIVE_RESULTS.md at the repo root,
`docs/TRIALS/`, dated research notes, then the Optimus brain, which was not reachable in this session,
so the check rests on the files named):
- **Book A, the cell this card's main source supports.** Receipts:
  `backend/data/optimus/night_factory_2026-09-13/A_corner_run01.json`,
  `backend/data/optimus/first_books/replay/si_low_turnover_high_v1_2026-09-21T173526Z.json`, draft
  `docs/TRIALS/TRIAL-DRAFT-A-si-low-turnover-high-v1.md`. On the 2011-2024 confirm slice (168 blocks)
  the book trails its twin by 0.937% a month at the $3M floor (Newey-West lag-2 t -2.09) and by 0.253%
  at the $10M floor (t -0.64); pooled over 1990-2024 (417 blocks) it trails by 0.541% (t -2.26, two-sided
  p 0.0238, which does not clear the Holm threshold of 0.0125 for the declared family of four books);
  the sign is negative in all four eras (1990-99 -0.30%, 2000-09 -0.19%, 2010-16 -0.99%, 2017-24
  -0.87%). Status FAILED_VARIANT under PRODUCT_EXPERIMENT; the draft was never signed.
- **The CRSP-era library board** (`backend/data/optimus/crsp_rebuild/bridges_board_BR_FLAT_2026-09-29T1535Z__FT_2026-10-07_1__2026-10-06T182820Z.json`,
  85 rules of which 7 are short-interest rules, rule minus fair matched twin, %/month, t on 3-month
  blocks). 1991-2016 pooled and the 2017-2024 holdout: `low_days_to_cover` +0.11 (t 0.74) and -0.44
  (t -0.97); `low_days_to_cover_large` +0.04 (t 0.18) and -0.09; `low_dtc_gp` +0.34 (t 1.85) and +0.22;
  `short_covering` (3-month fall in short interest) +0.21 (t 1.64) and -0.11. All four are
  CANNOT_DISTINGUISH and none is a registration candidate (every one fails "rule-twin t at least 2
  over 1991-2016" and "DSR at least 0.95 at the full count"). `covering_flow`, `low_dtc_mom` and
  `short_squeeze` are FAILED_VARIANT. `short_squeeze` (high days to cover crossed with last month's
  winners) is the one significantly negative rule, -0.68% against its twin over 1991-2016 (t -3.65) and
  -0.94% in 2017-2024; it is consistent with heavily shorted names underperforming, but its second leg
  is one-month momentum, so one-month reversal is a confound and the high-days-to-cover leg alone was
  never run.
- **Short-interest change as a rank signal** (NEGATIVE_RESULTS.md section 24): `si_chg_low` small-cap
  rank-IC t 6.09 at one-way turnover 0.457 a month, printed t_net 2.16; the section's own prose says no
  flow signal above about 0.15 a month of turnover has a positive net t and Draft A calls it net-dead,
  so the printed 2.16 is not reconciled in the ledger. `si_trend` large/mid IC t 2.12, t_net -0.92. The
  level pair `dtc_low`/`dtc_high` is named but its numbers are not printed and its code lives in the
  Aegis module repository (probe note). Reading: the rank information is real and the book is not
  collectible.
- **FINRA short-sale VOLUME rules, a different variable**
  (`docs/research_notes/2026-09-27/finra_short_volume_2026-09-27.md`; receipt
  `backend/data/optimus/strategy_library/finra/finra_short_volume_rules_2026-09-27T142546Z.json`;
  monthly, k=20, 2018-08 to 2026-07): low short-volume ratio -0.84% a month against SPY (t -2.43, alpha
  -0.20% with t -0.83), falling ratio -0.98% (t -2.75, alpha -0.60% with t -1.94), both BETA_EXPLAINS;
  momentum gated by low short volume +0.01% against SPY and worse than ungated momentum,
  CANNOT_DISTINGUISH. This is not evidence about reported short interest.

In the `pre-register-trial` vocabulary (read by hand; the linter was not run): re-submitting Book A would
be BLOCKED, since it was adequately powered against its 0.685% MDE and came back negative; re-submitting a
days-to-cover or short-covering rule would be RESURRECTION-shaped, since CANNOT_DISTINGUISH is an
unanswered question that needs a named change; the constrained-name screen and the aggregate index would
be PASS, which means unmatched, not novel. FAILED_VARIANT closes these constructions, not the mechanism,
and no MECHANISM_REJECTED is claimed. Not found this pass: any construction crossing short interest with
institutional ownership (the library's seven `RET-07` rules use days to cover and a 3-month change, which
are neighbours of Asquith, Pathak and Ritter's construction, not that construction), any aggregate
short-interest series, any exclusion screen on short interest (NEGATIVE_RESULTS.md section 58 ran four
screens, `io_level`, `io_abn`, `skew_25d` and `skew_resid`, all FAILED_VARIANT, none on short interest),
and any borrow-fee series.

## hyp_lab family
`family_unmapped` - the nearest family is `risk_timing` and it fits only the aggregate-index branch (market exposure timing); cross-sectional short interest matches none of the 21 fixed families (`insider_event` is Form-4 event cells, `size_*` target move size, and `official_disclosure` has no ledger rows).

## Verdict
**ALREADY_CLOSED.** The long-only cross-sectional constructions this card's main source supports were run on two house platforms and failed (Book A is FAILED_VARIANT at -0.94% a month on the 2011-2024 confirm slice; the seven library short-interest rules are CANNOT_DISTINGUISH or FAILED_VARIANT on the CRSP-era board), which closes those constructions and not the mechanism: the constrained-name avoid-list, the aggregate index and a borrow-fee proxy were never asked, and each is power- or data-limited (see needs_evidence).

## needs_evidence
- How many names per month are constrained in Asquith, Pathak and Ritter's sense (top-decile short interest over shares outstanding AND bottom-tercile 13F institutional ownership, with the 26-day and 45-day lags) while above the $10M median-dollar-volume floor, and does the improvement an exclusion screen could buy (bounded, by my arithmetic, by the share of host holdings excluded times the 39 bps value-weighted gap, so a few bps a month at most) exceed the minimum detectable effect of the host book's monthly blocks?
- Does the Rapach, Ringgenberg and Zhou aggregate index (equal-weighted short interest over shares outstanding, detrended and standardised; their sample ends December 2012) still predict the market in 2013-2024, and is that test powered at all on about 144 monthly observations, meaning what is the minimum detectable out-of-sample R-squared or certainty-equivalent gain and how much of any gain sits in 2020?
- Can a borrow-fee proxy be built from data the programme already licenses, namely the option-implied fee that Engelberg, Reed and Ringgenberg compare with Markit loan fees (60 bps against 57 bps on average in their sample), which needs OptionMetrics standardized options beyond the single 1996 file named in `docs/DATA_CATALOG.md`, and would it survive Muravyev, Pearson and Pollet (2022), who find only a minimal premium for borrow-fee risk?
