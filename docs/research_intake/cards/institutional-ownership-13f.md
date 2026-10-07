# CARD: institutional-ownership-13f

## Index fields
- topic: Institutional ownership (13F)
- mechanism_class: information_asymmetry, limits_to_arbitrage, structural_friction
- dataset_status: DOCUMENTED_NOT_TRACKED

## Citation
Xuemin Yan and Zhe Zhang (2009), "Institutional Investors and Equity Returns: Are Short-term
Institutions Better Informed?," Review of Financial Studies, 22(2): 893-924. DOI
10.1093/revfin/hhl046. Verified by fetching
`https://ideas.repec.org/a/oup/rfinst/v22y2009i2p893-924.html` on 2026-10-07 (title, authors, volume,
issue, pages, DOI and abstract agree; RePEc prints the first author as "Xuemin (Sterling) Yan") and
`https://api.crossref.org/works/10.1093/revfin/hhl046` (Crossref registry; it dates the record 2007, the
advance-access date printed in the PDF, while RePEc and the PDF footer give 2009 for volume 22, issue
2). The authors' own PDF
`https://www.lehigh.edu/~xuy219/research/horizon_RFS.pdf` was also fetched and its text extracted;
the construction and every number attributed to this paper below come from that text (the data and
construction sections, Table 6 and the earnings-announcement section).

Amil Dasgupta, Andrea Prat and Michela Verardo (2011), "The Price Impact of Institutional Herding,"
Review of Financial Studies, 24(3): 892-925. DOI 10.1093/rfs/hhq137. Verified by fetching
`https://ideas.repec.org/a/oup/rfinst/v24y2011i3p892-925.html` and
`https://api.crossref.org/works/10.1093/rfs/hhq137` on 2026-10-07 (title, authors, volume, issue,
pages, DOI, abstract). The doi.org link redirected to academic.oup.com, whose page returned only
navigation text, so it is not counted as a verification.

Hsiu-Lang Chen, Narasimhan Jegadeesh and Russ Wermers (2000), "The Value of Active Mutual Fund
Management: An Examination of the Stockholdings and Trades of Fund Managers," Journal of Financial
and Quantitative Analysis, 35(3): 343-368. DOI 10.2307/2676208. Verified by fetching
`https://ideas.repec.org/a/cup/jfinqa/v35y2000i03p343-368_00.html` (RePEc printed no DOI) and
`https://api.crossref.org/works/10.2307/2676208` (Crossref supplied it) on 2026-10-07. The doi.org
link redirects to JSTOR, which was not fetched.

Miguel Antón, Randolph B. Cohen and Christopher Polk (2021), "Best Ideas," unpublished working paper
(April 2021 draft, which thanks Bernhard Silli for an earlier version; this repo's older notes cite
the paper as "Cohen, Polk and Silli"). SSRN 1364827, DOI 10.2139/ssrn.1364827. Verified by fetching
the authors' LSE-hosted PDF `https://personal.lse.ac.uk/polk/research/BestIdeas.pdf` on 2026-10-07
(text extracted; abstract, data section and footnotes read) and
`https://api.crossref.org/works/10.2139/ssrn.1364827` (Crossref lists the SSRN record under Antón,
Cohen and Polk). The SSRN abstract page returned 403 and the EconBiz record returned an
access-denied page, so neither is counted.

Paul A. Gompers and Andrew Metrick (2001), "Institutional Investors and Equity Prices," Quarterly
Journal of Economics, 116(1): 229-259. DOI 10.1162/003355301556392. Verified by fetching
`https://ideas.repec.org/a/oup/qjecon/v116y2001i1p229-259..html` and
`https://api.crossref.org/works/10.1162/003355301556392` on 2026-10-07.

## The claim, in one sentence
Yan and Zhang (2009): the positive relation between institutional ownership and future stock returns
comes from short-horizon (high-turnover) institutions, whose trading forecasts returns without a
long-run reversal and forecasts earnings surprises, while long-horizon institutions' trading
forecasts neither.

## Mechanism: why the inefficiency could exist, and who is on the other side
Three accounts sit in the fetched sources, and they disagree on sign at long horizons; that
disagreement is the main design fact for this card.

1. **Information.** If some institutions hold superior information and regularly identify mispriced
   stocks, they should trade often to exploit it; infrequent traders hold less (Yan and Zhang's
   argument, which they also test against the opposite story, that active institutions are
   overconfident noise traders). The paper does not name the counterparty; the contrast it draws is
   with long-horizon institutions, whose trading forecasts nothing, and whoever trades against the
   short-horizon group is by implication uninformed relative to it. The same account sits behind Chen,
   Jegadeesh and Wermers (stocks funds buy outperform stocks they sell, per the abstract) and Antón,
   Cohen and Polk (a manager's highest-conviction positions carry the outperformance; the manager's
   other holdings do not).
2. **Demand shocks.** Gompers and Metrick's abstract attributes about half of large stocks' relative
   price appreciation in 1980 to 1996 to a shift in investor composition toward institutions that
   prefer large stocks; Yan and Zhang report that Gompers and Metrick attribute the ownership/returns
   relation to "temporal demand shocks rather than institutions' informational advantage" (Yan and
   Zhang's wording, from the extracted full text). On that account there is no lasting information,
   only price pressure.
3. **Herding with reversal.** Dasgupta, Prat and Verardo model career-concerned managers who imitate
   earlier trades and dealers with market power who exploit it; per the abstract, herding positively
   predicts short-term returns and negatively predicts long-term returns. The abstract names the
   dealers as the exploiters and does not name the losing side; the natural reading (mine, not the
   paper's) is the herding managers and their clients, who pay for the imitation.

Structurally, a 13F is a quarter-end snapshot of long positions only, public up to 45 days later, so
whatever information the trade carried has had up to a quarter and a half to be priced before anyone
outside the filer can see it.

## Assumptions
- A filer's quarter-end position change reflects its trading in the quarter; intra-quarter round
  trips are invisible.
- A filer's trailing four-quarter churn describes its next-quarter behaviour well enough to sort on
  (Yan and Zhang re-sort every quarter from the filer's own history).
- Index and passive complexes land in the low-churn bucket, so the high-churn bucket is active by
  construction. This is an assumption, not a fact: the Thomson s34 extract carries no active/passive
  flag (`backend/data/optimus/tracker_backtest/holder_h2_h3.json`, `grain` field: "NOT observable in
  entitled WRDS") and its only manager-type column is `typecode`.
- The public date is no earlier than quarter end plus 45 days, and later for confidential-treatment
  positions (SEC FAQ, below).
- CUSIP-to-PERMNO links are valid as of the report date (the repo's bridge matches 89.7% through CRSP
  `dsenames`, per `docs/research_notes/2026-09-30/bridges_and_conditionals_2026-09-30.md` section 1).
- 13F adds something Form 4 insider trades and analyst revisions do not already carry. Both are
  closer to the event and both are in the repo: card `analyst-revision-momentum` records the revision
  closures, and `backend/data/optimus/hyp_lab/LEDGER.md` records a FAILED_VARIANT (H-aca81f5b8f, insider
  buy with no sale by the buyers within 90 days) and a CANNOT_DISTINGUISH (H-ca95f10775, insider
  cluster buys) for the insider family.

## Measurable variables: the precursor observable BEFORE the move
The source's variable, from Yan and Zhang's text: a filer's churn rate for quarter t is
min(purchases, sales) divided by the average of its portfolio value at t-1 and t (their equation 3),
averaged over its own four trailing quarters (equation 4); each quarter the filers are sorted into
tertiles, the top tertile is "short-term", and the stock-level precursor is the quarterly change in
short-term institutional ownership (shares held by that tertile over shares outstanding). Every input
is computed from the filer's own filings through quarter t.

Timing, and what is and is not point-in-time:
- **Public date.** The SEC's Form 13F FAQ, fetched at
  `https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f`
  on 2026-10-07 (paraphrased here from the fetch tool's page extraction): each quarterly filing is
  due within 45 days after the end of the calendar quarter (the page lists the 2026 due dates as May
  15, August 14 and November 16, and February 16, 2027); filers are managers with discretion over
  $100 million or more in Section 13(f) securities; short positions are not reported and are not
  netted against longs; and positions under a confidential-treatment request are withheld until
  denial or expiry forces an amendment. So rdate plus 45 days is the earliest knowability for ordinary
  positions, never a guarantee, and a reported "sale" is ambiguous (rotated, redeemed or hedged are
  indistinguishable from a view).
- **No filing timestamp in the data.** `scripts/holders_13f.py` measured `fdate` minus `rdate` over 24
  quarters as median 0, min 0, max 0: in `tr_13f.s34` the vintage date equals the quarter end, so using
  it as the knowledge date would grant 45 days of look-ahead. The tracked per-year meta files
  (for example `backend/data/optimus/wrds/tr13f_s34_2013.meta.json`) nonetheless label `fdate`
  "vintage = when holdings became public", which is wrong as a knowledge date. The repo's rule, in
  `backend/services/crsp_pit_bridges.py` and the H2/H3 receipt, is rdate plus 45 calendar days plus one
  business day, counting only rows with `fdate` equal to `rdate`.
- **The published start convention.** Yan and Zhang form portfolios at quarter end and report returns
  from quarter t+1 (Table 6); a search of the extracted text for lag, delay, public and filing found
  no filing-lag adjustment, so on my reading the first part of each published holding period precedes
  the date a real-time investor could see the filing. Antón, Cohen and Polk state (footnote 4 and
  Figure 4) that strategies using only holdings information as of the public date also earn
  significant abnormal returns.

## Sample period and markets
- Yan and Zhang: US stocks, 1980:Q3 to 2003:Q4, Thomson (CDA/Spectrum) 13F holdings, CRSP returns.
- Antón, Cohen and Polk: US domestic active equity mutual funds, January 1983 to December 2018 (the
  holdings data begin in 1980), plus a hedge-fund sample of 1,662 pure-play 13F filers.
- Gompers and Metrick: 1980 to 1996, US equities.
- Chen, Jegadeesh and Wermers; Dasgupta, Prat and Verardo: only the abstracts were extracted, so
  their sample periods are not stated here. The Dasgupta, Prat and Verardo abstract describes a
  theoretical model with testable predictions.

## Effect size as published
All from Yan and Zhang's Table 6 (value-weighted quintile portfolios sorted on the quarterly change in
ownership by short-term or long-term institutions; Q5 minus Q1 is a zero-investment spread):
- Short-term institutions: +0.53% per quarter raw (t 3.16) and +0.41% per quarter after DGTW
  benchmark adjustment (t 3.34); cumulative over four quarters +2.16% raw (t 2.77) and +1.62% DGTW
  (t 2.82).
- Long-term institutions: -0.19% per quarter raw (t -1.20) and -0.03% DGTW (t -0.29).
- Earnings announcements: Q5 minus Q1 abnormal return in the [-1, +1] window 94 basis points higher in
  the first following quarter (t 17.38); about 53 basis points annualised after controlling for
  earnings momentum.

Antón, Cohen and Polk (abstract): best ideas outperform the market and the managers' other holdings
"by approximately 2.8 to 4.5 percent per year, depending on the benchmark employed", with a six-factor
alpha of 37 basis points per month (t 3.45) from 1983 (their footnote 1). Gompers and Metrick (per
the abstract as returned by the fetch tool): the compositional shift could explain about half of the
relative price appreciation of large over small shares in 1980 to 1996 (a price-level result, not a
return-predictability one). Chen, Jegadeesh and Wermers and Dasgupta, Prat and Verardo: direction
only in the abstracts; no headline number was extracted.

## Known failure modes and post-publication decay
The standing references for whether published predictors survive publication, McLean and Pontiff
(2016) and Harvey, Liu and Zhu (2016), are carried (authors, year, venue, volume and pages, and the
McLean and Pontiff DOI) in cards `post-earnings-announcement-drift` and
`markowitz-1952-portfolio-selection`; both were re-checked against Crossref on 2026-10-07 (authors,
venue, volume and pages agree with those cards) and are not re-derived here. Neither is specific to
institutional ownership.

Mechanism-specific failure modes, from the fetched and tracked material:
- Yan and Zhang's sample ends in 2003. Post-2003 behaviour is what this repo's own data measures, and
  in aggregate form it is weak or opposite-signed (corpse section below).
- The published spread is long-short and gross; this repo's bar is a long-only, cost-charged book.
  NEGATIVE_RESULTS section 28 measured that 99.9% of one ownership signal's equal-weighted decile
  spread sits in the leg a long-only mandate cannot hold, and ruled that any comparison of a local
  rejection with a published effect must state the construction class.
- The literature disagrees on sign. Yan and Zhang's own introduction cites prior work finding that
  aggregate institutional trading has negative predictive ability for next-quarter returns and that
  the evidence is sensitive to how trading is measured, and Dasgupta, Prat and Verardo's abstract has
  herding negatively predicting long-term returns.
- Index complexes confound any holding-duration split: the longest-duration filers in the H2/H3
  receipt are Vanguard, Geode, Northern Trust and State Street, so a new position by a long-duration
  filer is disproportionately an index addition.
- A sign flip is a new candidate, never a free retry (NEGATIVE_RESULTS section 27, stated for the
  option-to-stock volume arm and applied here).

## What AEGIS has on disk to test it
- **Holdings.** 29 Thomson s34 per-year extracts. The tracked meta files
  `backend/data/optimus/wrds/tr13f_s34_1996.meta.json` through
  `backend/data/optimus/wrds/tr13f_s34_2024.meta.json` carry a `rows` field each, and those sum to
  76,896,818; `docs/DATA_MANIFEST.md` (line 141) independently lists the parquet files at 76,896,818
  rows, fdate 1996-03-31 to 2024-12-31, pulled 2026-08-19 by `scripts/wrds_training_pull.py`, columns
  fdate, rdate, mgrno, typecode, cusip, shares, change. The parquet bytes are gitignored
  (`.gitignore` line 74 ignores `*.parquet`), so this checkout cannot confirm that they are present
  on any machine or re-count them. `docs/DATA_CATALOG.md` has no 13F row (a search for 13f, s34,
  holders and tr13f returns nothing), which settles the QUEUE's "not confirmed in the catalog"
  lead: the manifest and meta files document the pull, the catalog is silent.
- **Related bulk tables.** `docs/DATA_MANIFEST.md` (line 165): three `tr_13f` tables in the bulk
  folder, 2,513,784 rows, 1978-12-31 to 2025-12-31.
- **Bridge and link.** `backend/services/crsp_pit_bridges.py` (`f13_fresh`, `f13_quarter_stats`,
  `f13_breadth`) and `backend/data/optimus/wrds/tr13f_permno_link.json` (tracked).
- **Tracked receipts.** `backend/data/optimus/wrds/holders_13f.json` (receipt HOLDERS-13F-3) and
  `backend/data/optimus/tracker_backtest/holder_h2_h3.json` (23,317,112 events), built by
  `scripts/holders_13f.py` and `scripts/holder_h2_h3_test.py`.
- **Not on disk, per the tracked receipts and docs:** an active/passive flag, SEC filing timestamps,
  and 13D/13G holdings (the H2/H3 receipt places 13D/13G outside entitled WRDS).

## The falsifiable question and the declared primary metric, with costs
*For US common stocks on the CRSP/13F bridge, does net buying by high-churn filers (top tertile of
the filer's own trailing four-quarter churn, the Yan and Zhang construction) predict a higher
63-session return than net selling by the same filers, measured from the first close after rdate
plus 45 days, while the same split for low-churn filers shows no effect (the published placebo)?*
Primary metric: the Q5-minus-Q1 spread in 63-session return relative to the size by volatility by
12-1-momentum matched twin, net of cost, with the 252-session horizon, the long-only side and a
by-year and leave-one-year-out print reported alongside (CLAUDE.md protocol 11). Cost model: each
traded weight charged half of max(Corwin-Schultz spread, flat band) and scaled by realised quarterly
turnover, as in `docs/research_notes/2026-09-30/bridges_and_conditionals_2026-09-30.md` section 3.
This is a draft for a future pre-registration. Registered as it stands it would be a RESURRECTION of
H3 in the BLOCKED/DUPLICATE/RESURRECTION/PASS vocabulary of `.claude/skills/pre-register-trial/SKILL.md`
and would have to name its changed instrument (churn tertile instead of duration tercile, buy versus
sell inside the tertile, point-in-time public date, by-year print), not "trying again".

## Whether a corpse already exists here
Yes, extensively. The Optimus brain (`brain_query`, `aegis_postmortems`) and Exa were not available in
this session, so this check rests on the file searches below.
- `NEGATIVE_RESULTS.md` section 26 (TRIAL-ABIO-KIRK, 2026-08-01): level, flow and abnormal-ownership
  arms all REJECTED on the 2004-2018 explore window; the flow arm `io_chg` came out contrarian
  (pooled rank-IC t -2.37, -3.34 in large/mid; net -46.2 bps/month, t -3.50, large/mid at flat 25 bps),
  and the section calls this "the eighth 13F variant to show real rank information and a dead book
  (after best_ideas, breadth_chg, inst_persist x2, own_dur_t10)" and the family "closed at level,
  flow AND residual resolution".
- Section 28 (INSTR-RANK-DEAD, 2026-08-02): the small-cap `io_level` equal-weighted top-minus-bottom
  decile spread is +145.8 bps/month gross (t 5.92), and in the section's own decomposition 150.6 of
  150.8 bps (99.9%) of the equal-weighted spread sits in the leg a long-only book cannot hold.
- Section 58 (B_exclusion_screen, 2026-09-19): exclusion screens built on the ownership ranks, run once
  on one host book and one floor: FAILED_VARIANT (`io_level` low end -0.024% per month versus unscreened,
  t -0.52; +0.006% versus random exclusion, t +0.15).
- `docs/research_notes/2026-09-30/bridges_and_conditionals_2026-09-30.md`: 13F breadth rules, 2
  FAILED_VARIANT; cell C04 "new position by a concentrated 13F manager" CANNOT_DISTINGUISH (validate
  +0.14% per month, t 0.60 against an MDE of 0.65; 590 names).
- `backend/data/optimus/tracker_backtest/holder_h2_h3.json` (63-session excess returns, point-in-time
  from rdate plus 45 days): 13F events as a class carry no value-weighted relative return (+0.06%,
  t +0.16, 23,317,112 events); manager identity is worth about 5 bp per standard deviation of the
  filer's own score; in the extreme holding-duration split, size-neutral, new positions by
  long-duration filers trail those by short-duration filers by about 0.96% (t -4.16), confounded by
  index additions as above.
- **An unadjudicated positive.** `docs/FINDING_2026-08-31_INSTITUTIONS_SELLING_IS_THE_SIGNAL.md`
  reports that names institutions sold by more than 10% returned +26.00% on average over 12 months
  against +8.35% for names they bought by more than 10% (2013-2024), but the same table gives medians
  of -0.29% and -4.37%, so it is a tail result; the note prints no t-statistic, no by-year breakdown and
  no overlap correction for quarterly formation with a 12-month return. Its headline count (152,668
  name-quarters) does not equal the sum of its own table (138,668), and neither equals the tracked
  receipt (`backend/data/optimus/wrds/holders_13f.json`, 124,101 observations; the
  sold-more-than-10% cell has n 7,539, mean 29.95%, median 1.21%). The sign agrees with section 26's
  contrarian flow arm. No trial is registered for it: `backend/services/lab_themes.py` lists
  `holders_13f_v1` with `trial: None` and readiness "observing".

## hyp_lab family
`family_unmapped` - nearest is `insider_event` (Form 4 trades by disclosed holders), but the filing, cadence (quarterly, 45-day lag), horizon and data source differ and no 13F cell was ever generated under it; `official_disclosure` is in the tuple with zero cells and I found no definition for it in tracked code or docs, so whether it was meant to hold 13F is a question for whoever owns the taxonomy.

## Verdict
**ALREADY_CLOSED.** Aggregate 13F ownership level, flow, breadth, residual, concentrated-initiation and exclusion-screen constructions each carry a recorded REJECTED, FAILED_VARIANT or CANNOT_DISTINGUISH (NEGATIVE_RESULTS sections 26, 28 and 58; the 2026-09-30 bridges note).

One thread is named rather than assumed away: the churn-split buy-versus-sell asymmetry under rdate plus 45 days timing, which the H3 duration split could not isolate from index additions, and the 12-month sold-versus-bought gap in the 2026-08-31 finding, which has never been through a by-year or non-overlapping print. A RESURRECTION that names those instrument changes is the only legitimate way back.

## needs_evidence
- Does the 2026-08-31 sold-versus-bought gap (mean +26.00% against +8.35%, median -0.29% against -4.37%) survive a by-year and leave-one-year-out print and a non-overlapping design (dropping each formation year in turn is the standard way a mean-over-median result like this dies), and which of its three cell counts is right?
- Is the Yan and Zhang effect visible at all when churn is computed only from filings public at the time, returns start after rdate plus 45 days, and index complexes are excluded by construction, and does the low-churn placebo come out null (the H3 receipt could not answer this because its duration split puts index complexes on the long side)?
- Can `typecode` or another entitled column serve as an active-versus-passive proxy good enough to separate informed trading from index reconstitution, or does the question need the 13D/13G ingest that the H2/H3 receipt places outside entitled WRDS?
