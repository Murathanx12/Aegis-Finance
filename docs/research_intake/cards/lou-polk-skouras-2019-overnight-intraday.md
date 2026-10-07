# CARD: lou-polk-skouras-2019-overnight-intraday

## Index fields
- topic: Overnight vs intraday returns (the tug of war between clienteles)
- mechanism_class: behavioural_bias, structural_friction
- dataset_status: DOCUMENTED_NOT_TRACKED

## Citation
Dong Lou, Christopher Polk, Spyros Skouras (2019), "A Tug of War: Overnight versus Intraday
Expected Returns," *Journal of Financial Economics*, 134(1): 192-213. DOI
10.1016/j.jfineco.2019.03.011. Verified by fetching
`https://econpapers.repec.org/RePEc:eee:jfinec:v:134:y:2019:i:1:p:192-213` (2026-10-07; title,
authors, journal, volume, issue, pages, DOI, and abstract confirmed directly).

## The claim, in one sentence
Firm-level overnight returns and intraday returns each exhibit their own strong positive
autocorrelation (continuation) over periods of years, but overnight and intraday returns are
**negatively** related to each other ("a tug of war"), and many well-known trading-strategy
returns (the paper examines 14) are concentrated almost entirely in one of the two sub-periods —
overnight or intraday — rather than spread across both, which the authors trace to a
composition-of-investor-clientele mechanism (momentum/institutional-style demand pushing one
period, contrarian/retail-style demand pushing the other).

## Mechanism: why the inefficiency could exist, and who is on the other side
The proposed driver is investor heterogeneity by trading venue/time: institutional, momentum-chasing
order flow concentrates near the open (reacting to overnight news, index-fund flows, and
overnight-information absorption), while a different clientele — more contrarian, liquidity-
providing, or retail-dominated — is active intraday and tends to fade the overnight move. The
"other side" of the overnight continuation is whoever supplies liquidity intraday and systematically
takes the opposite side of the overnight crowd's direction; the tug-of-war framing makes this
explicit rather than incidental. This is the same mechanism family as Berkman, Koch, Tuttle &
Zhang/Cooper-Cliff-Gulen and the "overnight-information inflated at the open, reverted once real
liquidity returns" story this programme's own `FINDING_2026-08-23_OVERNIGHT_INTRADAY.md` already
cites and tests directly.

## Assumptions
Requires open/close-level (not necessarily sub-minute) price data to split a day into overnight
(close-to-open) and intraday (open-to-close) legs; assumes the split is economically meaningful,
i.e. that the overnight gap captures genuinely different information/clientele exposure than the
intraday session, not simply microstructure noise (bid-ask bounce) — which is exactly the
confound this programme's own replication tested and rejected (see "already tried" below).

## Measurable variables: the precursor observable BEFORE the move
The paper's own framing treats a stock's **recent history of overnight vs. intraday returns** as
the precursor: a name with a strongly positive trailing overnight-return series predicts a
continuation of positive overnight returns (and, per the tug-of-war, a damped or negative
intraday leg) going forward — both legs are observable in real time as of the decision date
(close-to-open and open-to-close splits of CRSP daily bars with `openprc`), so the precursor is
PIT-clean in principle. What AEGIS's own prior work (`FINDING_2026-08-23_OVERNIGHT_INTRADAY.md`)
established is narrower and more specific: the overnight premium itself (not a continuation
signal built from it) is large, real, strongest in the MOST liquid names, and not microstructure
noise — but it does not beat buy-and-hold net of costs as a standalone timing strategy.

## Sample period and markets
Lou-Polk-Skouras (2019): US common stocks, decades-long sample (CRSP-based; exact start/end dates
not independently re-extracted this pass beyond the abstract — the paper's tug-of-war and
14-strategy decomposition is run across a multi-decade CRSP history per the JFE abstract and
widely-cited summaries). AEGIS's own replication: CRSP daily, common stock, NYSE/AMEX/Nasdaq,
**2013-2024 only** (`openprc` is not carried in the pre-2013 CRSP pull on this machine — a declared,
receipted data limit, not a choice).

## Effect size as published
AEGIS's own measured numbers (not Lou-Polk-Skouras's, which were not independently re-extracted
this pass beyond the abstract) are the directly comparable, already-verified figures: universe-wide
overnight return **10.73 bps/day** (t=8.71, Newey-West), intraday **0.06 bps/day** (t=0.01); in the
most-liquid dollar-volume quintile, overnight **8.25 bps/day** (t=5.94) and intraday **6.30
bps/day** (t=3.88) — i.e. in the names that could actually be traded at scale, the intraday leg is
ALSO strongly positive, which is the specific reason the standalone overnight strategy loses to
buy-and-hold.

## Known failure modes and post-publication decay
No decay was found in AEGIS's own 2013-2024 window: the overnight premium in the most-liquid
quintile **rose** from 2.45 bps/day (2013-2017) to 5.91 bps/day (2018-2024) — the opposite of
McLean-Pontiff-style post-publication decay (McLean & Pontiff 2016, *Journal of Finance* 71(1):
5-32; cited here as the standing decay reference, not independently re-verified for this specific
mechanism). The dominant failure mode AEGIS already found is not decay but **dominance**: the
premium is real and robust to the bid-ask-bounce confound (it is strongest in liquid names, where
bounce should be weakest, not strongest), yet a standalone long-overnight/flat-intraday book loses
to buy-and-hold at every cost level tested, because sitting out the intraday session also sits out
a large, equally real positive intraday return in exactly the liquid names a real book would hold.
Breakeven one-way cost for the standalone strategy was 4.13 bps against a book trading 504
times/year, and even clearing that breakeven only reaches a strategy that loses to holding.

## What AEGIS has on disk to test it
CRSP daily bars with `openprc`, 2013-2024, common stock (`shrcd` 10/11), NYSE/AMEX/Nasdaq
(`exchcd` 1/2/3), eligibility via the `dsenames` interval join — already pulled and used by
`scripts/overnight_intraday_study.py`, receipts at `backend/data/optimus/overnight_study/
{panel_receipt,results}.json`. Compustat `rdq` linked via `ccmxpf_lnkhist` for the
earnings-conditioned slice. No new data pull needed for a cross-sectional momentum re-cut of the
same panel (see falsifiable question below); a cross-sectional panel back to 1990 would need a
separate WRDS pull of `openprc` for the pre-2013 years, which the existing finding already names as
the first thing that would change its scope.

## The falsifiable question and the declared primary metric, with costs
AEGIS's own `FINDING_2026-08-23_OVERNIGHT_INTRADAY.md` already answered the TIMING version of
this mechanism (buy at the close, sell at the open, as a standalone book) and rejected it
(`ANOMALY_CONFIRMED / STRATEGY_REJECTED`). What is **not** yet tested is the Lou-Polk-Skouras
cross-sectional version: *does a stock's trailing overnight-return rank (e.g. 21- or 63-session
cumulative overnight return, cross-sectionally ranked) predict its FUTURE overnight return
better than its trailing TOTAL (close-to-close) return does — i.e. is overnight-return
continuation a sharper momentum signal than ordinary total-return momentum, net of costs, when
used as a cross-sectional RANKING signal rather than a universe-wide timing rule?* Primary metric:
long-short decile spread on forward overnight return (not total return), t-stat blocked by month
(CANON §58), reported against ordinary 12-1 total-return momentum on the same universe as the
named control (since the arena's own composite is already 12-1-momentum-dominated per
`docs/ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md` — this question's value is specifically whether it
is a DIFFERENT error signature than momentum, not an additional restatement of it).

## Whether a corpse already exists here
The TIMING mechanism (buy close / sell open as a book) is `ANOMALY_CONFIRMED / STRATEGY_REJECTED`
— closed, with no licence requested, in `docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md`. The
CROSS-SECTIONAL MOMENTUM version proposed above (overnight-return continuation as a ranking
signal, distinct from the timing question) was **not found** in `NEGATIVE_RESULTS.md`,
`docs/TRIALS/`, or the research notes grepped this pass — it is the specific "what remains
testable" gap this card's own task brief names.

## Needs evidence
- Post-2019 citing literature that extends the tug-of-war framing to a cross-sectional (not
  universe-wide timing) construction, specifically on US common stocks -- the 2026-10-07 probe
  (`docs/research_notes/2026-10-07/research_instruments_2026-10-07.md` §2.4) found two 2025 SSRN
  working papers on the mechanism via CrossRef that neither this card nor OpenAlex's result set
  named; whether either proposes the SAME cross-sectional ranking this card's falsifiable
  question asks, or a different (e.g. intraday-only) cut, was not read this pass.
- Whether any post-2019 paper tests overnight-return continuation as a RANKING signal (decile
  spread) rather than Lou-Polk-Skouras's own long-overnight/flat-intraday TIMING construction --
  the specific gap this card's falsifiable question names as untested.
- Independent (non-AEGIS) replication of the "dominance, not decay" finding (overnight premium
  rising 2013-2024 in liquid names) outside this programme's own CRSP pull.

## hyp_lab family
`family_unmapped` — closest existing family is `price_location` (day-range/52-week price-location
features), but overnight-return continuation is a return-based momentum construction, not a
price-location feature, and does not fit cleanly.

## Verdict
**READY_TO_CELL** for the cross-sectional momentum re-cut (data already on disk, existing script
`scripts/overnight_intraday_study.py` is directly extensible to compute a ranked rather than
universe-wide version, 2013-2024 window only). The TIMING mechanism itself is **ALREADY_CLOSED**
(cite `docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md` — do not re-discover it).

## needs_evidence
- Does a stock's trailing 21- or 63-session cumulative overnight-return rank predict its forward
  overnight return (long-short decile spread, t blocked by month) better than ordinary 12-1
  total-return momentum on the same 2013-2024 CRSP universe, net of costs?
- Does the answer hold before 2013, which needs a separate WRDS pull of `openprc` for the pre-2013
  years?
- What are Lou, Polk & Skouras's (2019) exact sample bounds and per-strategy overnight/intraday
  effect sizes, which this pass did not re-extract beyond the abstract?
