"""Rules contributed to the strategy library from outside `strategy_library.py`.

Two blocks: chunk C's rules over the six `pit_features` columns, and (2026-09-26,
the discovery builder, who now owns this file) the OpenClaw discovery candidates
with their sources' claimed numbers -- see the block comment above `DiscoveryStrategy`.

CHUNK C -- for the D builder to import.

`strategy_library.py` is owned by chunk D; this file does not edit it. It builds
`EXTRA_STRATEGIES`, a list of `strategy_library.Strategy` objects in exactly the
library's rule shape, each over a column that `backend/services/pit_features.py`
computes. The factory joins those columns onto its monthly panel and scores the
rules like any other; `register()` still refuses a signature twin.

WHY THESE ARE DIFFERENT MECHANISMS FROM THE BASE LIBRARY
========================================================
The base library already carries neighbours, and each rule here is built to be
a different economic claim, not a relabelling:

* base `analyst_skill` weights a firm by whether its PAST raises beat SPY
  (skill measured on the same yfinance flow it then scores). Here the weight is
  the broker's held-out RECOMMENDATION reliability from IBES (a different
  corpus, sector-benchmarked, direction-mix-adjusted, walk-forward).
* base `first_mover_raises` counts raises that were first in 30 days. Here the
  score is WHO moved first -- the first mover's measured leadership (how many
  firms historically followed it), Cooper-Day-Lewis's timeliness ranking.
* base `low_max` is the unconditional MAX effect. Here MAX is taken net of
  volatility (the lottery component Bali-Cakici-Whitelaw show survives a vol
  control) -- the part of MAX that low-vol rules cannot already buy.
* attention (news counts by first_seen_utc), FOMO reversal and pricing power
  under cost pressure have no base-library neighbour at all.

HISTORY, DECLARED ON EACH RULE
==============================
`attention_z` and everything built on it are `forward_only`: the corpus stamps
`first_seen_utc` at PULL time and began 2026-09-11, so it has no past to
backtest. The analyst rules have history from 2013 (actor corpus claims) and
the revisions parquet from 2011; before 2013-04 every broker carries the prior
weight, which the caveat states.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.services.strategy_library import (Strategy, col, combo, gated, rank_band, rank_of,
                                               sector_rel, within_top)

#: When chunk C registered these rules (before any of them was scored).
REGISTERED_CHUNK_C = "2026-09-26T09:00:00+00:00"

_PIT = ("pit_features: every input row dated STRICTLY before the decision date "
        "(one session more conservative than xs_ranker)")
_REV = ("revisions: yfinance upgrade/downgrade parquet pulled 2026-09, survivor-"
        "selected (64 of 1,784 dead symbols carry history)")
_SKILL = (_REV + "; broker reliability from the IBES actor corpus (2013-2024 recs), "
          "walk-forward on claims resolved before the date; yfinance firm -> IBES "
          "estimid by measured co-occurrence, unmapped firms at the prior weight 1.0; "
          "history from 2013 -- before 2013-04 this is plain net raises")
_ATT = ("news corpus: first_seen_utc is PULL time and the corpus began 2026-09-11; "
        "no history exists, forward book only")
_PP = ("SEC annual revenue/cogs at FIRST filing, filed+2d; cost pressure is an "
       "IN-HOUSE proxy (market-wide median COGS growth vs its 3y median), NOT the "
       "note's NAICS PPI, which is not on disk")

BCW = "Bali, Cakici & Whitelaw 2011, JFE (Stocks as Lotteries)"
CDL = "Cooper, Day & Lewis 2001, JFE (Following the Leader)"
DEG = "Da, Engelberg & Gao 2011, JF (In Search of Attention); Barber & Odean 2008, RFS"
LEH = "Lehmann 1990, QJE; Da, Liu & Schaumburg 2014, MS (short-term reversal)"
NM = "Novy-Marx 2013, JFE (gross profitability); research note 2026-09-26 #11"
MWW = "Mikhail, Walther & Willis 2004, JFE; FINDING 2026-08-23 ANALYST_RELIABILITY"

EXTRA_FAMILIES: dict[str, str] = {
    "ibes_skill_weighted": ("a broker whose recommendations were right before is right again "
                            "(held-out reliability persists, corr 0.25-0.51); its revisions carry "
                            "more information than a plain count admits"),
    "lottery_net_vol": ("lottery-seeking investors overpay for the chance of a jackpot day; "
                        "the part of MAX that volatility does not explain is the mispricing"),
    "attention_shock": ("attention-constrained investors buy what grabs attention; the spike "
                        "pulls price forward and the premium reverses"),
    "attention_reversal": ("a move made WITH an attention spike is the most likely to be "
                           "uninformed demand, so it is the move most likely to reverse"),
    "analyst_leadership": ("lead analysts move prices and followers herd; a revision by a "
                           "historically-followed firm is information the herd has not priced"),
    "pricing_power": ("a firm that holds margin while input costs rise has pricing power the "
                      "market under-weights because margins usually compress in that regime"),
}


def _rules() -> list:
    S = Strategy
    R = REGISTERED_CHUNK_C

    def E(*a, **kw):
        kw.setdefault("first_registered_utc", R)
        kw.setdefault("economic_reason", EXTRA_FAMILIES[a[1]])
        return S(*a, **kw)

    return [
        # 1. analyst-skill persistence weight (#22)
        E("ibes_skill_net_raises", "ibes_skill_weighted",
          "90-day net target raises, each weighted by its broker's held-out IBES reliability",
          col("analyst_skill_weight"), source=f"literature:#22 {MWW}",
          caveat=_PIT + "; " + _SKILL, forward_only=False),
        # 2. MAX lottery (#19), as the vol-orthogonal component
        E("lottery_max_net_vol", "lottery_net_vol",
          "rank-avg: LOW max daily return over 21 sessions, HIGH 21-session volatility "
          "(the lottery part of MAX, not its volatility part)",
          combo(("max_21", -1), ("vol_21", 1)), source=f"literature:LOT-01 {BCW}",
          literature_reported="high-MAX decile underperforms ~1%/mo; survives a volatility control",
          caveat=_PIT, forward_only=False),
        # 3. attention shock (#16)
        E("attention_shock_fade", "attention_shock",
          "LOWEST 5-session news-count z-score vs the name's own 126-session baseline "
          "(avoid the spiked names)",
          col("attention_z", -1), source=f"literature:ATT-05 {DEG}",
          literature_reported="attention-grabbing stocks see net retail buying and subsequent underperformance",
          caveat=_ATT, forward_only=True),
        # 4. FOMO / reversal (#21): REV-02 conditioned on the spike
        E("fomo_reversal_5d", "attention_reversal",
          "5-session losers, scored only where the move came with an attention spike (z > 2)",
          col("fomo_reversal", -1), source=f"literature:REV-02 x ATT-01 {LEH}",
          caveat=_ATT + "; " + _PIT, forward_only=True),
        # 5. analyst first-mover (#23)
        E("first_mover_leadership", "analyst_leadership",
          "latest revision cluster's direction x its first mover's historical leadership percentile",
          col("first_mover_rank"), source=f"literature:#23 {CDL}",
          caveat=_PIT + "; " + _REV + "; leadership from clusters whose 7-day follow window closed "
          "before the date", forward_only=False),
        # 6. pricing power under cost pressure (#11)
        E("pricing_power_under_cost_pressure", "pricing_power",
          "annual gross-margin change x market-wide cost-pressure excess (scored only while "
          "cost pressure is ON)",
          col("pricing_power_cost_pressure"), source=f"literature:#11 {NM}",
          caveat=_PP, forward_only=False),
        # interaction A (the note's §3.4 conditions the REV family on the spike):
        # the classic 1-month reversal, scored only among spiked names
        E("fomo_reversal_21d", "attention_reversal",
          "1-month losers among names with an attention spike (z > 2)",
          gated(col("mom_21", -1), "attention_z", lo=2.0),
          source=f"literature:REV-01 x ATT-01 {LEH}; Jegadeesh 1990, JF",
          caveat=_ATT + "; mom_21 is the factory panel's (includes the decision day's close)",
          forward_only=True),
        # interaction B (the note's §5 trio): a skilled broker who is also a leader
        E("skilled_leader", "analyst_leadership",
          "rank-avg: IBES-reliability-weighted net raises, first-mover leadership",
          combo(("analyst_skill_weight", 1), ("first_mover_rank", 1)),
          source=f"literature:#22 x #23 {MWW}; {CDL}",
          caveat=_PIT + "; " + _SKILL, forward_only=False),
    ]


# ── the OpenClaw discovery candidates (2026-09-26) ───────────────────────────
#
# Source: `docs/research_notes/2026-09-26/research_openclaw_strategy_discovery.md`
# table (a), rows from the QuantConnect leaderboard, Quantpedia, GitHub,
# Composer, Reddit and one newsletter, plus the seven QuantConnect leaderboard
# items the note left in `openclaw_logs/q1_quantconnect_strategies.json`
# (EXT-QC-14a..g). Every row lands in exactly ONE of three places:
#
#   * `EXTRA_STRATEGIES` -- replicable on the panel as a DIFFERENT signature
#     from every base rule; carries `claimed_number` (the source's own number,
#     verbatim, NEVER ours) so a board can print "claimed X, we measure Y";
#   * `EXT_COVERED_BY` -- replicable, but the faithful construction differs
#     from a registered rule only by k, a lookback or a threshold, i.e. it IS
#     that rule (`register()` would refuse it as a ThresholdVariant). The claim
#     is kept beside the base rule it should be read against;
#   * `EXT_NOT_REACHABLE` -- needs a column the panel does not have (named).
#
# Licence: PRODUCT_EXPERIMENT. Every claimed number is a CLAIM from a source
# that selected itself onto a leaderboard; the note rates most of them high
# overfit risk. None of these rules is a replication of the source's full
# strategy -- where only one sleeve is reachable, the caveat says which.

#: When the discovery rules were written down, before any of them was scored.
REGISTERED_DISCOVERY = "2026-09-26T08:55:00+00:00"

_NOTE = "research_openclaw_strategy_discovery.md 2026-09-26"
_QC = "https://www.quantconnect.com/strategies/"
_QP = "https://quantpedia.com/screener"
_MCAP = ("no clean market cap on the panel (VAL-01: split-adjusted bars x as-filed shares), so "
         "'large cap' is the trailing median-dollar-volume band and cap-weighting is not available")
_MONTHLY = "the engine is monthly: a daily/weekly source rule is realised as its month-end analogue"
_SLEEVE = "PARTIAL: only the single-stock sleeve is reachable; the leveraged/inverse-ETF sleeve is not"

EXTRA_FAMILIES["disposition"] = ("holders anchored on an old high sell as the price gets back to it; "
                                 "once that supply is absorbed the name breaks out (Grinblatt-Han)")

#: The multi-horizon momentum blend several QC leaderboard rules use (21..252d).
_MULTI = (("mom_21", 1), ("mom_63", 1), ("mom_126", 1), ("mom_252", 1))

#: Columns `attach` derives from panel columns (all PIT: built from bars <= t).
DERIVED_COLUMNS: tuple[str, ...] = ("sharpe_252", "mkt_not_stress", "low_vs_high_252",
                                    "ear_filed_dow")


@dataclass(frozen=True)
class DiscoveryStrategy(Strategy):
    """A library rule that came from an external source with a claimed number.

    `claimed_number` is the SOURCE's figure and period, verbatim; it is copied
    into `literature_reported` too, so the factory's existing leaderboard row
    (which prints `literature_reported`) carries it beside our measurement.
    """

    claimed_number: str = ""
    discovery_id: str = ""

    def meta(self) -> dict:
        m = super().meta()
        m["claimed_number"] = self.claimed_number
        m["discovery_id"] = self.discovery_id
        return m


def _discovery_rules() -> list:
    def D(did, rid, family, desc, signal, *, url, claimed, reason, caveat="", **kw):
        kw.setdefault("first_registered_utc", REGISTERED_DISCOVERY)
        return DiscoveryStrategy(
            rid, family, desc, signal, source=f"discovery:{did} {url} ({_NOTE})",
            claimed_number=claimed, literature_reported=f"CLAIMED by source: {claimed}",
            discovery_id=did, economic_reason=reason, caveat=caveat, **kw)

    mom_reason = "investors under-react to news that arrives gradually; winners keep winning"
    return [
        D("EXT-QC-01", "qc536_secneutral_multimom_large", "sector_relative",
          "sector-relative rank of a 21/63/126/252-day momentum blend, large band, top 10",
          sector_rel(combo(*_MULTI)), universe_rule="large", k=10,
          url=_QC + "536", claimed="5Y CAGR 156.4%, 1Y Sharpe 1.33, 5Y DD 24.2% (QC leaderboard, "
          "whole 75/25 book incl. leveraged-ETF sleeve, 2026-09-26)",
          reason="within-sector momentum keeps the stock-specific drift and drops the sector bet",
          caveat=_SLEEVE + "; " + _MCAP + "; GICS is the static current map"),
        D("EXT-QC-02", "qc629_multimom_above_trend_gated", "regime_gated",
          "21..252d momentum blend among names above their 200d mean, large band, top 10, "
          "book to cash when SPY < its 200d mean (the momentum-breadth cash hedge)",
          gated(combo(*_MULTI), "px_vs_ma200", lo=0.0), universe_rule="large", k=10,
          regime_gate="mkt_trend_up", url=_QC + "629",
          claimed="5Y CAGR 91.0%, 1Y Sharpe 1.01, 5Y DD 31.9% (QC leaderboard, 3-sleeve book)",
          reason="momentum confirmed by trend, switched off in bear markets where momentum crashes",
          caveat=_SLEEVE + "; ADX filter not on the panel (omitted); " + _MCAP),
        D("EXT-QC-03", "qc623_mom63_liquidity_weighted", "momentum",
          "63-day return (TRIX-90 proxy), large band, top 10, liquidity (inverse-Amihud) weighted",
          col("mom_63"), universe_rule="large", k=10, weight_rule="inv_amihud",
          url=_QC + "623", claimed="5Y CAGR 58.3%, 1Y Sharpe 2.59, 5Y DD 47.2% (QC leaderboard)",
          reason=mom_reason + "; weighting toward the biggest names mimics a cap-weighted book",
          caveat="TRIX is a triple-smoothed EMA rate of change; the raw 63d return is our proxy; "
          + _MCAP + " (inverse-Amihud is the liquidity-weight stand-in)"),
        D("EXT-QC-04", "qc285_secneutral_mom_large_trend", "regime_gated",
          "sector-relative 12-1 momentum, large band, book to cash when SPY < its 200d mean",
          sector_rel(col("mom_252_21")), universe_rule="large", regime_gate="mkt_trend_up",
          url=_QC + "285", claimed="5Y CAGR 53.3%, 1Y Sharpe 0.16, 5Y DD 56.8% (QC leaderboard; "
          "the 5Y/1Y gap is the note's decay finding)",
          reason="sector-neutral momentum with a crash guard: the premium without the momentum crash",
          caveat=_MONTHLY + "; " + _MCAP),
        D("EXT-QC-05", "qc470_mom252_quarterly_riskparity", "weighted",
          "trailing 252-day return, top 20, held a quarter, inverse-volatility weighted (HRP proxy)",
          col("mom_252"), k=20, hold_months=3, weight_rule="inv_vol",
          url=_QC + "470", claimed="5Y CAGR 20.3%, 1Y Sharpe 1.09, 5Y DD 15.8% (QC leaderboard)",
          reason="risk-balanced weights stop the most volatile winners dominating the momentum book",
          caveat="HRP (correlation clustering) is not in the engine; inverse vol is its "
          "diagonal special case; the source's universe also held ETFs, ours is single-stock "
          "(answers TRIAL-001's HRP-vs-EW question only at the diagonal)"),
        D("EXT-QC-08", "qc372_oversold_snapback_mega", "reversal",
          "5-session losers in the mega band, top 5 (RSI(2)<20 snapback, monthly analogue)",
          col("rev_5", -1), universe_rule="mega", k=5,
          url=_QC + "372", claimed="5Y CAGR 14.1%, 1Y Sharpe 1.25, 5Y DD 15.9% (QC leaderboard)",
          reason="liquidity providers are paid to absorb short-horizon overreaction in the most liquid names",
          caveat=_MONTHLY + "; the source's ATR stop/target and 8-day time stop are not modelled; "
          "RSI/TSI replaced by the 5-session return"),
        D("EXT-QC-11", "qc768_golden_cross_mega", "trend",
          "50d-vs-200d moving-average spread (golden cross), mega band, top 30 (DJIA-sized book)",
          col("ma50_vs_ma200"), universe_rule="mega", k=30,
          url=_QC + "768", claimed="5Y CAGR 10.3%, 1Y Sharpe 0.56; full-backtest CAGR 10.27%, "
          "Sharpe 0.29 (same page, 2005-2026)",
          reason="slow-moving capital and herding keep prices trending once the short average crosses",
          caveat="source uses 100d/200d SMA, 1.5x leverage and a 20% stop on the DJIA 30; the "
          "panel has 50d/200d, no leverage, no stop, and the mega band stands in for the DJIA"),
        D("EXT-QC-14a", "qc395_sharpe252_above_trend_large", "momentum",
          "trailing 252-day Sharpe (return / vol) among names above their 200d mean, large, top 10",
          gated(col("sharpe_252"), "px_vs_ma200", lo=0.0), universe_rule="large", k=10,
          url=_QC + "395", claimed="5Y CAGR 48.3%, 1Y Sharpe 1.74, 5Y DD 44.6% (QC leaderboard)",
          reason="risk-adjusted momentum picks winners that got there smoothly, which persist longer",
          caveat="sharpe_252 = mom_252 / vol_252, derived in strategy_library_ext.attach from panel "
          "columns (PIT); the source's minimum-Sharpe floor is a threshold and is not modelled"),
        D("EXT-QC-14d", "qc597_secneutral_multimom_calm", "regime_gated",
          "sector-relative 21..252d momentum blend, large band, book to cash in market stress "
          "(SPY 21d vol in its top tercile)",
          sector_rel(combo(*_MULTI)), universe_rule="large", k=10, regime_gate="mkt_not_stress",
          url=_QC + "597", claimed="5Y CAGR 44.3%, 1Y Sharpe 0.50, 5Y DD 43.8% (QC leaderboard)",
          reason="momentum crashes cluster in high-volatility markets; stepping out of stress avoids them",
          caveat="source de-risks into safe-haven bonds (cash earns 0 here) and re-weights lookbacks by "
          "regime (not modelled); mkt_not_stress = 1 - mkt_stress, derived in attach; " + _MCAP),
        D("EXT-QP-04", "qp0025_small_annual", "size_liquidity",
          "smallest trailing dollar volume, top 50, held twelve months (yearly small-cap tilt)",
          col("dollar_vol_log", -1), k=50, hold_months=12,
          url=_QP + " #0025", claimed="OOS 6.10%/yr, vol 25.60% (Quantpedia screener)",
          reason="holders of small, neglected names demand a premium for the cost of exiting",
          caveat="dollar volume, not market cap (" + _MCAP + "); annual holding cuts turnover, "
          "so this is the size premium at its cheapest cost"),
        D("EXT-GH-01", "gh01_pullback_in_uptrend_mega", "reversal",
          "5-session losers among mega names in the top half by distance above the 200d mean",
          within_top(col("rev_5", -1), "px_vs_ma200", 0.5), universe_rule="mega", k=10,
          url="https://github.com/You07abd/ApexQuant",
          claimed="OOS Sharpe ~0.9-1.2, ann. return ~4-7%, max DD -8%, ~45 trades/yr (README, June 2026)",
          reason="a dip inside an established uptrend is liquidity demand, not news, and mean-reverts",
          caveat="PARTIAL: the ETF-sleeve rotation is not reachable; the megacap satellite's "
          "trend + mean-reversion engine is realised as a monthly pullback-in-uptrend; " + _MONTHLY),
        D("EXT-GH-02", "gh02_five_price_factors_ivw", "combination",
          "rank-avg: 12-1 momentum, 52-week-high proximity, short reversal, up-day persistence, "
          "vol contraction; top 12, inverse-volatility weighted",
          combo(("mom_252_21", 1), ("px_vs_52w_high", 1), ("rev_5", -1), ("up_days_12_1", 1),
                ("vol_ratio", -1)), k=12, weight_rule="inv_vol",
          url="https://github.com/yingwang/trade",
          claimed="5Y (2021-2026) CAGR 16.1%, Sharpe 0.71 vs SPY +80.3% cum.; 1Y CAGR 39.5%, "
          "Sharpe 1.45 (after the repo's own impact-cost bugfix)",
          reason="five price signals with different failure modes average out each other's noise",
          caveat="the 22% vol target and 3-week rebalance are realised as inverse-vol weights and a "
          "monthly rebalance; Almgren-Chriss impact is replaced by the band toll"),
        D("EXT-GH-04", "gh04_rps_20_60_120", "momentum",
          "rank-avg relative price strength over 21, 63 and 126 sessions (no skip month)",
          combo(("mom_21", 1), ("mom_63", 1), ("mom_126", 1)), k=20,
          url="https://github.com/Donvink/quant-trade",
          claimed="2Y (2024-2026) CAGR 93.9%, Sharpe 1.97, max DD -34.2% (single simulated run)",
          reason=mom_reason + "; blending horizons diversifies the lookback choice",
          caveat="volume/fundamental filters and the layered stop system are not modelled; the note "
          "rates the claim VERY HIGH overfit risk"),
        D("EXT-GH-11", "gh11_skip_month_composite_q", "momentum",
          "rank-avg of 12-1, 6-1 and 3-1 momentum (skip-month composite), top 50 (~top quintile)",
          combo(("mom_252_21", 1), ("mom_126_21", 1), ("mom_63_21", 1)), k=50,
          url="https://github.com/husaam-atq/systematic-equity-factor-backtester",
          claimed="CAGR 32.4%, Sharpe 1.33, max DD -31.3% vs SPY 13.0%/0.78 (long-only, 5bps one-way)",
          reason=mom_reason + "; the composite is less exposed to one lookback's crash",
          caveat="the repo's 'momentum-weighted composite' is read as a skip-month horizon blend "
          "(the note does not quote its exact construction); 5bps costs there, band toll here"),
        D("EXT-BLOG-01", "blog01_roe_adv_annual_large", "combination",
          "rank-avg: return on equity, trailing dollar volume; large band, held twelve months",
          combo(("ni_be", 1), ("dollar_vol_log", 1)), universe_rule="large", k=20, hold_months=12,
          url="https://quanta72.substack.com/p/the-factor-model-i-tested-8021-stocks",
          claimed="2013-2024: ROE+ADV 21.1%/yr (SPY 13.2%), Sharpe 1.08 (1.17 with the proprietary "
          "BetaMap overlay), max DD 35.8% (promotional newsletter)",
          reason="profitable firms that the market also trades heavily: quality with institutional sponsorship",
          caveat="source takes the UNION of two top-10 lists in January; the engine rank-averages; "
          "the BetaMap overlay is proprietary and not modelled; ni_be is SEC facts at filed+2d"),
        D("EXT-CO-03", "co03_reversal_in_high_margin", "combination",
          "5-session losers among names in the top 30% by gross margin (quality-filtered dip)",
          within_top(col("rev_5", -1), "gross_margin", 0.3), k=20,
          url="https://www.composer.trade/trading-strategies",
          claimed="3Y backtest AR 26.1%, Sharpe 0.82, SD 36.1%, max DD 37.9% (Composer, semis only)",
          reason="a quality franchise that dips on flow, not news, is the dip most likely to recover",
          caveat="the source is concentrated in semiconductors; ours is the whole eligible universe; "
          "RSI replaced by the 5-session return; " + _MONTHLY),
        D("EXT-RD-01", "rd01_roic_growth_mom_insider", "combination",
          "rank-avg: operating profitability, revenue growth, 12-1 momentum, insider buyers",
          combo(("ope_be", 1), ("rev_gr", 1), ("mom_252_21", 1), ("ins_buyers_90", 1)), k=20,
          url="https://www.reddit.com/r/quant/comments/1s8g7l3/feedback_on_a_ranking_model_roic_earnings/",
          claimed="~30% excess return vs QQQ over a ~4-year backtest (single unaudited Reddit post, 2026-03-31)",
          reason="four signals from four data sources (fundamentals, growth, price, insiders) fail at different times",
          caveat="ROIC -> ope_be and earnings growth -> revenue growth are proxies; institutional flows "
          "(13F) are not on the panel and the leg is dropped; SEC facts at filed+2d; Form 4 by observed_at"),
        # the chunk-D note's FOMO-07, left to this module by name in NOTE_BACKLOG
        DiscoveryStrategy(
            "recovery_anchoring", "disposition",
            "nearness to the 52-week high, only where the 52-week low was >= 30% below that high",
            gated(col("px_vs_52w_high"), "low_vs_high_252", hi=-0.30), k=20,
            source="literature:FOMO-07 Grinblatt & Han 2005, JFE (research_library_expansion_and_lean.md)",
            first_registered_utc=REGISTERED_DISCOVERY, discovery_id="FOMO-07",
            economic_reason=EXTRA_FAMILIES["disposition"],
            caveat="low_vs_high_252 = 52w low / 52w high - 1, derived in attach; it does not know "
            "whether the low came before or after the high (a rally from a low also qualifies)"),
    ]


# ── the paper rules (2026-09-26 evening) ─────────────────────────────────────
#
# Source: `docs/research_notes/2026-09-26/research_ssrn_arxiv_signals_and_oss_comparison.md`
# §4 (five "tonight-registrable" rules) and §2 row 5 (13F is ON DISK, so
# `NOT_REACHABLE["RET-10"] = "no 13F feed"` is stale -- see `EXT_CORRECTS_BASE`).
# Every rule carries its FALSIFIER and its CONTROL, written down before the
# first score. The Friday rule and its Monday control are registered in the
# same commit on purpose: a control chosen after seeing the result is not one.
#
# Deviations from the note's literal one-liners, each forced by the codebase
# and stated here rather than discovered later:
# * Friday is `dayofweek == 4` in pandas (Monday = 0). The note's `lo=5.0`
#   would have selected SATURDAY filings, i.e. almost nothing.
# * `quality_momentum_gate` as literally written (12-1 momentum in the top
#   gross-margin tercile, monthly) IS the registered `mom_in_high_margin`
#   (INT-05) with `gated` in place of `within_top` -- a relabel `register()`
#   would NOT have caught (different shape string, same economics). It is
#   registered at the QUARTERLY hold of `mom_12_1_q` instead, so the note's
#   comparison -- the crash tail against the unconditional twin at the same
#   holding -- is one row against one row.
# * `disp_short_avoid` reads the HISTORICAL `target_cv_180` (cross-firm price
#   target CV from the revisions parquet), not the forward-only
#   `target_dispersion` snapshots, so it can be scored tonight; it is
#   `mom_12_1_q` minus the top dispersion decile (`excluding_top`), so a name
#   with no dispersion reading STAYS in the book -- a `within_top` gate would
#   have silently turned the screen into a coverage filter.
# * `Strategy.control` is a BOOLEAN (this row IS a control, printed, never
#   ranked). The NAMED control(s) of a rule therefore live in `controls`.

_FUND_EXT = "SEC facts joined on filed + 2 days, never on the period end"

#: When the paper rules were written down, before any of them was scored.
REGISTERED_PAPER = "2026-09-26T15:05:00+00:00"

_SSA = "research_ssrn_arxiv_signals_and_oss_comparison.md 2026-09-26"
_LIT = ("[LIT: paper not re-read tonight; DOI resolved via doi.org + Crossref title match 2026-09-26]")
DP09 = ("DellaVigna & Pollet 2009, JF 64(2) 'Investor Inattention and Friday Earnings "
        "Announcements' https://doi.org/10.1111/j.1540-6261.2009.01447.x")
AFIM = ("Asness, Frazzini, Israel & Moskowitz 2014, JPM 40(5) 'Fact, Fiction and Momentum "
        "Investing' https://doi.org/10.3905/jpm.2014.40.5.075; " + NM)
GL03 = ("Gleason & Lee 2003, The Accounting Review 78(1) 'Analyst Forecast Revisions and "
        "Market Price Discovery' https://doi.org/10.2308/accr.2003.78.1.193")
DMS02 = ("Diether, Malloy & Scherbina 2002, JF 57(5) 'Differences of Opinion and the Cross "
         "Section of Stock Returns' https://doi.org/10.1111/0022-1082.00490")
CHS02 = ("Chen, Hong & Stein 2002, JFE 66 'Breadth of Ownership and Stock Returns' "
         "https://doi.org/10.1016/S0304-405X(02)00223-4")
CLS01 = ("Chan, Lakonishok & Sougiannis 2001, JF 56(6) 'The Stock Market Valuation of "
         "Research and Development Expenditures' https://doi.org/10.1111/0022-1082.00411")
EP13 = ("Eisfeldt & Papanikolaou 2013, JF 68(4) 'Organization Capital and the Cross-Section "
        "of Expected Returns' https://doi.org/10.1111/jofi.12034")

EXTRA_FAMILIES["institutional_breadth"] = (
    "with short-sale constraints, pessimists who cannot short simply leave; a FALL in the "
    "number of institutions holding a name means negative views are unpriced (Chen-Hong-Stein)")
EXTRA_FAMILIES["intangibles"] = (
    "GAAP expenses R&D and organisation capital immediately, so book numbers understate "
    "the asset and investors under-price the firms that build it")

_DOW_CAVEAT = ("ear_filed_dow = weekday (Mon=0 .. Fri=4) of the 8-K 2.02 ACCEPTANCE day in "
               "New York, derived in strategy_library_ext.derive_columns as date - "
               "days_since_earn from two panel columns attach_8k built strictly before the "
               "decision date (NaN unless days_since_earn >= 1); an after-close Friday filing "
               "counts as Friday (the paper's announcement day); the 8-K can trail the press "
               "release by a day")
_CLUSTER_CAVEAT = ("cluster_age_days: target RAISES only, chained while consecutive raises on "
                   "the name are <= 30 days apart; the cluster is ACTIVE when its latest raise "
                   "is <= 30 days before the decision date; age = decision date - the chain's "
                   "first raise; every raise dated strictly before the decision date "
                   "(merge_asof, exact matches excluded). " + _REV)
_13F_CAVEAT = ("13F: wrds/tr13f_quarterly.json (tr_13f.s34 aggregated server-side per "
               "(rdate, cusip8), n_managers >= 3, 2013Q1-2025Q4). s34's `fdate` EQUALS "
               "`rdate` (measured: median/min/max 0 days on 4.84M 2024 rows), so it is NOT a "
               "knowledge date; a quarter is usable only when rdate + 45 days (the SEC "
               "deadline) is strictly before the decision date. cusip8 -> permno by "
               "tr13f_permno_link.json, permno -> the permno's LAST CRSP ticker "
               "(crsp_pit_monthly_v1, ends 2024-11: permnos first listed later are unmapped); "
               "a reused ticker goes to the permno alive at that rdate. Change = log(n "
               "managers / n managers the previous quarter), consecutive quarters only; the "
               "n >= 3 floor means a name rising from 2 holders has no prior and is NaN. "
               "Longs-only, 45 days stale by construction")
_INTANG_CAVEAT = ("from sec_facts_history facts 'rd' (us-gaap ResearchAndDevelopmentExpense) and "
                  "'sga' (SellingGeneralAndAdministrativeExpense), ANNUAL periods (350-380 days) "
                  "at their FIRST filing, available filed + 2d; scaled by assets at the same "
                  "period end because market value is refused (VAL-01); org capital by "
                  "perpetual inventory (delta 15%, g 10%, NOT CPI-deflated)")


@dataclass(frozen=True)
class PaperStrategy(DiscoveryStrategy):
    """A rule from a paper, with its falsifier and its named control(s).

    `falsifier` is the observation that would kill the rule's mechanism, stated
    before the first score; `controls` names the registered rule(s) it must be
    read against (`Strategy.control` is the boolean "this row IS a control").
    """

    falsifier: str = ""
    controls: tuple = ()

    def meta(self) -> dict:
        m = super().meta()
        m["falsifier"] = self.falsifier
        m["controls"] = list(self.controls)
        return m


#: Keys a paper rule exposes through `.meta()` on top of REQUIRED_KEYS.
PAPER_KEYS: tuple[str, ...] = ("claimed_number", "discovery_id", "falsifier", "controls")


def excluding_top(base, drop_col: str, frac: float, sign: float = 1.0):
    """`base` everywhere EXCEPT the top `frac` of drop_col per date.

    A name with no drop_col value stays in: an exclusion screen that dropped
    the uncovered names would be a coverage filter wearing a screen's name.
    """
    def f(p):
        r = rank_of(p, drop_col, sign)
        return base(p).where(~(r > 1.0 - frac))
    f.requires = tuple(getattr(base, "requires", ())) + (drop_col,)
    f.shape = (f"excluding_top({getattr(base, 'shape', '?')},"
               f"{drop_col}{'+' if sign >= 0 else '-'})")
    return f


def _paper(did, rid, family, desc, signal, *, cite, claimed, reason, falsifier, controls,
           caveat="", **kw):
    kw.setdefault("first_registered_utc", REGISTERED_PAPER)
    return PaperStrategy(
        rid, family, desc, signal, source=f"literature:{did} {cite} {_LIT} ({_SSA})",
        claimed_number=claimed, literature_reported=f"CLAIMED by source: {claimed}",
        discovery_id=did, economic_reason=reason, caveat=caveat, falsifier=falsifier,
        controls=tuple(controls), **kw)


def _paper_rules() -> list:
    MOM = "mom_252_21"
    fri_claim = ("Friday announcers: ~15% lower immediate response and ~70% higher delayed "
                 "response than other weekdays for the same surprise (paper's abstract; "
                 "not re-derived here)")
    return [
        _paper("SSA-01", "friday_ear_drift", "earnings_event",
               "3-day announcement return of the latest 8-K 2.02, scored only where that 8-K "
               "was filed on a FRIDAY",
               gated(col("ear_last"), "ear_filed_dow", lo=4.0, hi=4.0), cite=DP09,
               claimed=fri_claim,
               reason="investors are less attentive on Fridays; the unpriced reaction becomes drift",
               falsifier=("(a) if monday_ear_drift's excess vs SPY is EQUAL OR LARGER than this "
                          "row's in BOTH the dev window and 2024-26, the day-specific (Friday "
                          "inattention) mechanism is falsified even if this row is profitable; "
                          "(b) if this row's dev excess is not above ear_drift's (the "
                          "unconditional rule), the weekday conditioning adds nothing -> "
                          "DEPRIORITIZED (this row, not the earnings_event family)"),
               controls=("monday_ear_drift", "ear_drift"),
               caveat=_DOW_CAVEAT),
        _paper("SSA-01-CTL", "monday_ear_drift", "earnings_event",
               "3-day announcement return of the latest 8-K 2.02, scored only where that 8-K "
               "was filed on a MONDAY (the pre-declared control for friday_ear_drift)",
               gated(col("ear_last"), "ear_filed_dow", lo=0.0, hi=0.0), cite=DP09,
               claimed="none: the pre-declared control; the source's claim is Friday-specific",
               reason=("control: DellaVigna-Pollet's mechanism is Friday inattention, so Monday "
                       "filers should show the smaller drift"),
               falsifier=("this row IS friday_ear_drift's falsifier: read it BEFORE the Friday "
                          "row; equal-or-larger Monday drift kills the day-specific story"),
               controls=("friday_ear_drift",), control=True, caveat=_DOW_CAVEAT),
        _paper("SSA-18", "quality_momentum_gate", "combination",
               "12-1 momentum among the top third by gross margin, rebalanced QUARTERLY "
               "(mom_12_1_q with a quality gate)",
               within_top(col(MOM), "gross_margin", 1 / 3), hold_months=3, cite=AFIM,
               claimed=("no single number: the claim is that momentum's crash risk concentrates "
                        "in junk / high-volatility names, so a quality-gated book keeps the mean "
                        "and shrinks the tail"),
               reason=("momentum survives in profitable names; the crash risk concentrates in "
                       "the unprofitable tail"),
               falsifier=("against mom_12_1_q (same score, same quarterly hold, no gate): the "
                          "crash-tail claim is falsified unless max_dd is >= 5 percentage points "
                          "shallower OR loo_worst_mean_active is >= 0.10%/month less negative; "
                          "a better mean alone does not rescue it (the claim is about the tail)"),
               controls=("mom_12_1_q", "mom_in_high_margin"),
               caveat=("the literal note spec (monthly, gated on a p66 threshold) is "
                       "mom_in_high_margin (INT-05) relabelled; registered at the quarterly "
                       "hold to compare against mom_12_1_q; " + _FUND_EXT)),
        _paper("SSA-03", "cascade_entry_timing", "revision_flow",
               "names in an ACTIVE target-raise cluster, youngest cluster first (days since "
               "the cluster's first raise, ascending)",
               col("cluster_age_days", -1), cite=GL03,
               claimed=("first-mover revisions carry significantly more of the eventual price "
                        "move than later revisions into the same cluster (no number carried in "
                        "the note)"),
               reason=("the first mover into a revision cluster carries the most unpriced "
                       "information; later revisers are chasing"),
               falsifier=("if its excess vs SPY is not above first_mover_raises' (the 'was "
                          "first' construction) in BOTH the dev window and 2024-26, cascade "
                          "position adds nothing beyond the registered first-mover rule -> "
                          "DEPRIORITIZED"),
               controls=("first_mover_raises", "net_raises"), caveat=_CLUSTER_CAVEAT),
        _paper("SSA-04", "disp_short_avoid", "analyst_dispersion",
               "12-1 momentum, rebalanced quarterly, EXCLUDING the top decile of cross-firm "
               "price-target dispersion (mom_12_1_q with a disagreement screen)",
               excluding_top(col(MOM), "target_cv_180", 0.10), hold_months=3, cite=DMS02,
               claimed=("high-dispersion quintile underperforms low-dispersion significantly in "
                        "the original sample (no number carried in the note)"),
               reason=("with short-sale constraints the optimists set the price when opinions "
                       "differ widely, so high-disagreement names are overpriced"),
               falsifier=("against mom_12_1_q unmodified: if NEITHER the mean (dev and 2024-26 "
                          "excess vs SPY) NOR loo_worst_mean_active improves, dispersion-as-a-"
                          "risk-filter is falsified on this panel"),
               controls=("mom_12_1_q",),
               caveat=("target_cv_180 (attach_ratings: std/mean of each firm's latest target in "
                       "180 days, >= 3 firms) is PRICE-TARGET dispersion, not the paper's "
                       "EPS-forecast dispersion; names without it are kept; " + _REV)),
        _paper("RET-10", "inst_breadth_up", "institutional_breadth",
               "largest quarterly rise in the NUMBER of 13F institutions holding the name "
               "(log change), held a quarter",
               col("inst_breadth_chg"), hold_months=3, cite=CHS02,
               claimed=("increases in ownership breadth predict higher, decreases lower "
                        "subsequent returns (no number carried in the note; none invented)"),
               reason=EXTRA_FAMILIES["institutional_breadth"],
               falsifier=("if inst_breadth_up_21_40 (its own ranks 21-40) earns as much as the "
                          "top 20, the ordering is uninformative; if its dev excess vs SPY is "
                          "not above the random-k controls', breadth change carries nothing here"),
               controls=("inst_breadth_up_21_40", "random_1", "random_2", "random_3"),
               caveat=_13F_CAVEAT),
        _paper("RET-10-CTL", "inst_breadth_up_21_40", "institutional_breadth",
               "inst_breadth_up's own ranks 21-40 (the k+1..2k twin)",
               rank_band(col("inst_breadth_chg"), 21, 40), hold_months=3, cite=CHS02,
               claimed="none: the k+1..2k control for inst_breadth_up",
               reason="control: is the ORDERING inside the breadth ranking informative",
               falsifier="this row IS inst_breadth_up's ordering falsifier",
               controls=("inst_breadth_up",), control=True, caveat=_13F_CAVEAT),
    ]


def _intangible_rules() -> list:
    """CLS R&D and EP organisation capital -- columns exist only after the re-extraction."""
    return [
        _paper("SSA-15", "rd_intensity", "intangibles",
               "annual R&D expense / total assets, highest first, held twelve months",
               col("rd_intensity"), hold_months=12, cite=CLS01,
               claimed=("high R&D-intensity firms subsequently outperform, especially among "
                        "low market-to-book / poor past return names (no number carried)"),
               reason=EXTRA_FAMILIES["intangibles"],
               falsifier=("if its dev excess vs SPY is not above gross_margin's (the registered "
                          "profitability level) and the random-k controls', R&D intensity adds "
                          "nothing on this panel"),
               controls=("gross_margin", "random_1"), caveat=_INTANG_CAVEAT),
        _paper("SSA-16", "org_capital", "intangibles",
               "perpetual-inventory SG&A stock / total assets, highest first, held twelve months",
               col("org_capital"), hold_months=12, cite=EP13,
               claimed=("high organisation-capital firms earn a significant premium over low "
                        "(no number carried)"),
               reason=EXTRA_FAMILIES["intangibles"],
               falsifier=("if its dev excess vs SPY is not above rd_intensity's and the random-k "
                          "controls', capitalised SG&A adds nothing beyond R&D"),
               controls=("rd_intensity", "random_1"), caveat=_INTANG_CAVEAT),
    ]


#: The facts the intangible rules need and the panel column each one yields.
INTANGIBLE_FACTS: dict[str, str] = {"rd": "rd_intensity", "sga": "org_capital"}


def _extraction_has(facts=tuple(INTANGIBLE_FACTS)) -> bool:
    """Does the on-disk sec_facts_history carry these facts yet? (False on any doubt.)"""
    try:
        import pyarrow.parquet as pq

        from backend import config as _cfg
        from pathlib import Path
        path = Path(_cfg.OPTIMUS_LEDGER_DIR) / "fundamentals_sec" / "sec_facts_history.parquet"
        if not path.exists():
            return False
        got = set(pq.read_table(path, columns=["fact"]).column("fact").to_pandas().unique())
        return set(facts) <= got
    except Exception:                                  # noqa: BLE001 -- unknown = not yet
        return False


#: True once `scripts/pull_sec_fundamentals.py` has re-run with the rd/sga tags.
INTANGIBLES_EXTRACTED: bool = _extraction_has()

#: Base-library NOT_REACHABLE lines this module shows to be stale. The base
#: file is chunk D's; the correction is recorded here, next to the rule that
#: makes it stale, and printed in the handoff.
EXT_CORRECTS_BASE: dict = {
    "RET-10": ("STALE: 'no 13F feed' is false -- wrds/tr_13f.s34 is on disk (tr13f_s34_1996..2024 "
               "parquets, 72.7M holdings rows since 2013) and aggregated per quarter in "
               "wrds/tr13f_quarterly.json through 2025Q4; RET-10 is reachable as "
               "`inst_breadth_up` (ownership BREADTH, rdate + 45d). The base line should read: "
               "'reachable via strategy_library_ext.inst_breadth_up'"),
    "MISC-01": "same: the 13F join exists (inst_breadth_up); 'no 13F join' is stale",
    "MISC-08": "built: `cascade_entry_timing` (Gleason & Lee 2003); 'cascade timing not built' is stale",
}


#: chunk C's eight rules (pinned by test_pit_features) and the discovery rules.
CHUNK_C_STRATEGIES: list = _rules()
DISCOVERY_STRATEGIES: list = _discovery_rules()
#: the paper rules (+ the intangible pair once the re-extraction has landed).
PAPER_STRATEGIES: list = _paper_rules() + (_intangible_rules() if INTANGIBLES_EXTRACTED else [])
EXTRA_STRATEGIES: list = CHUNK_C_STRATEGIES + DISCOVERY_STRATEGIES + PAPER_STRATEGIES

#: Keys every entry exposes through `.meta()`; pinned by the test.
REQUIRED_KEYS: tuple[str, ...] = ("id", "family", "economic_reason", "source",
                                  "first_registered_utc", "forward_only", "requires")
#: ...and a discovery row (source starts "discovery:") also carries these.
DISCOVERY_KEYS: tuple[str, ...] = ("claimed_number", "discovery_id")

#: Discovery rows whose faithful construction IS a registered rule (same
#: `signature()`; only k, a lookback or a threshold differ). Registering them
#: would be refused as a ThresholdVariant; read the claim against `base_rule`.
EXT_COVERED_BY: list = [
    {"id": "EXT-QC-12", "base_rule": "lowvol_252_large", "source": _QC + "310",
     "claimed_number": "5Y CAGR 9.8%, 1Y Sharpe 0.91, 5Y DD 16.4% (QC leaderboard)",
     "why": "5 lowest 252d-vol large caps monthly = lowvol_252_large at k=5 (k is not a mechanism)"},
    {"id": "EXT-QC-14b", "base_rule": "qc536_secneutral_multimom_large", "source": _QC + "537",
     "claimed_number": "5Y CAGR 45.5%, 1Y Sharpe 0.36, 5Y DD 52.1% (QC leaderboard)",
     "why": "sector-neutral multi-horizon large-cap momentum = EXT-QC-01's rule; the ADX filter is a threshold"},
    {"id": "EXT-QC-14c", "base_rule": "qc536_secneutral_multimom_large", "source": _QC + "592",
     "claimed_number": "5Y CAGR 45.5%, 1Y Sharpe 0.35, 5Y DD 52.1% (QC leaderboard)",
     "why": "1/3/6/9/12-month blend, sector-neutral, large = EXT-QC-01's rule (lookback set + ADX ceiling)"},
    {"id": "EXT-QP-01", "base_rule": "industry_mom", "source": _QP + " #0003",
     "claimed_number": "OOS 13.94%/yr, vol 18.38% (Quantpedia)",
     "why": "rotate into the best sector monthly = industry_mom (GICS sector momentum)"},
    {"id": "EXT-QP-07", "base_rule": "industry_mom", "source": _QP + " #0067",
     "claimed_number": "OOS 18.00%/yr (Quantpedia)",
     "why": "buy the best-performing industry monthly = industry_mom at the GICS-sector level"},
    {"id": "EXT-QP-02", "base_rule": "rev_5d", "source": _QP + " #0013",
     "claimed_number": "OOS 16.25%/yr, vol 14.94% (Quantpedia)",
     "why": "weekly stock reversal = rev_5d (the engine is monthly; a weekly hold is not a new signature)"},
    {"id": "EXT-QP-03", "base_rule": "mom_12_1", "source": _QP + " #0014",
     "claimed_number": "OOS 8.30%/yr, vol 16.60% (Quantpedia)", "why": "textbook 12-1 momentum"},
    {"id": "EXT-QP-08", "base_rule": "lowbeta", "source": _QP + " #0077",
     "claimed_number": "OOS 8.86%/yr, vol 11.50% (Quantpedia)",
     "why": "long-only betting-against-beta = lowbeta (the leveraged beta-neutral L/S needs a short leg)"},
    {"id": "EXT-GH-08", "base_rule": "resid_mom_12_1",
     "source": "https://github.com/aengusmartindonaire/statistical-arbitrage-strat",
     "claimed_number": "SPY-hedged residual momentum: IC 0.0168, Sharpe 0.48, cum. +721.8%, DD -39.1% "
     "(2016-2025); both reversal legs Sharpe -1.01/-0.88",
     "why": "residual 12-1 momentum = resid_mom_12_1; the SPY hedge needs a short leg"},
]

#: Discovery rows that need an input the panel does not have, with the column named.
EXT_NOT_REACHABLE: list = [
    {"id": "EXT-QC-06", "missing_column": "sue (consensus EPS estimate at announcement)",
     "source": _QC + "254", "claimed_number": "5Y CAGR 19.3%, 1Y Sharpe 0.72, 5Y DD 24.0%",
     "why": "same PEAD-01 dependency; ear_last (price reaction) is PEAD-02, already registered"},
    {"id": "EXT-QC-07", "missing_column": "ETF returns (SPY/IEF/GLD/UUP/DBC) as tradable rows",
     "source": _QC + "410", "claimed_number": "5Y CAGR 18.7%, 1Y Sharpe 1.33, 5Y DD 8.3%",
     "why": "cross-asset allocation; ETFs are excluded from the single-stock panel"},
    {"id": "EXT-QC-09", "missing_column": "div_yield (dividend yield)", "source": _QC + "211",
     "claimed_number": "5Y CAGR 13.9%, 1Y Sharpe 1.64, 5Y DD 22.9%",
     "why": "Dogs/Puppies of the Dow ranks on dividend yield; no dividend fact on the panel"},
    {"id": "EXT-QC-10", "missing_column": "book_to_market / earnings_yield / ev_ebit (clean market cap)",
     "source": _QC + "241", "claimed_number": "5Y CAGR 13.6%, 1Y Sharpe 0.11",
     "why": "value needs a market cap; VAL-01's split-contamination defect refuses it"},
    {"id": "EXT-QC-13", "missing_column": "ev_ebit, ebit_invested_capital", "source": _QC + "761",
     "claimed_number": "5Y CAGR 5.2%, 1Y Sharpe -0.16, 5Y DD 20.6%",
     "why": "no EV (VAL-01) and no invested capital"},
    {"id": "EXT-QC-14e", "missing_column": "theme membership (curated AI-compute basket)",
     "source": _QC + "213", "claimed_number": "5Y CAGR 43.3%, 1Y Sharpe 1.29, 5Y DD 50.8%",
     "why": "a hand-curated theme list chosen in hindsight; no PIT theme membership exists"},
    {"id": "EXT-QC-14f", "missing_column": "ETF rows (UVXY and style/sector/leveraged ETFs)",
     "source": _QC + "299", "claimed_number": "5Y CAGR 38.3%, 1Y Sharpe 0.69, 5Y DD 24.1%",
     "why": "single-position daily ETF rotation"},
    {"id": "EXT-QC-14g", "missing_column": "book_to_market (price-to-book)", "source": _QC + "409",
     "claimed_number": "5Y CAGR 8.7%, 1Y Sharpe 0.56, 5Y DD 16.4%", "why": "VAL-01 defect"},
    {"id": "EXT-QP-05", "missing_column": "net_payout_yield (buybacks + dividends - issuance)",
     "source": _QP + " #0036", "claimed_number": "OOS 22.13%/yr (no vol reported)",
     "why": "no buyback/dividend facts; issuance from as-filed shares is split-contaminated (INV-02)"},
    {"id": "EXT-QP-06", "missing_column": "country-ETF pair spreads", "source": _QP + " #0055",
     "claimed_number": "OOS 20.60%/yr, vol 10.00%", "why": "pairs construction, not k-of-N"},
    {"id": "EXT-QP-09", "missing_column": "style_regime (a style-rotation router)", "source": _QP + " #0091",
     "claimed_number": "OOS 9.25%/yr, vol 16.01%", "why": "a router comes after independent selectors (COMB-07)"},
    {"id": "EXT-QP-10", "missing_column": "wti_ret (crude oil series)", "source": _QP + " #0096",
     "claimed_number": "OOS 11.90%/yr, vol 9.80%", "why": "market timing on an oil series not joined"},
    {"id": "EXT-QP-11", "missing_column": "listed soccer-club stocks + match results", "source": _QP + " #0108",
     "claimed_number": "OOS 42.00%/yr, vol 50.00%", "why": "non-US niche universe"},
    {"id": "EXT-QP-12", "missing_column": "asset-class ETF rows", "source": _QP + " #0002",
     "claimed_number": "OOS 14.49%/yr, vol 11.00%", "why": "asset allocation"},
    {"id": "EXT-GH-03", "missing_column": "cointegrated pair spreads",
     "source": "https://github.com/ava-28/statistical-arbitrage-backtest",
     "claimed_number": "OOS mean Sharpe 0.517, ann. 0.4-5.5% (2024-2025) vs SPY 1.307", "why": "pairs"},
    {"id": "EXT-GH-05", "missing_column": "alfred_macro_vintage + sector-ETF rows",
     "source": "https://github.com/brianbeals/sector-rotation-screener",
     "claimed_number": "15-year backtest since 2011; no net number quoted", "why": "sector-ETF rotation"},
    {"id": "EXT-GH-06", "missing_column": "SPY option chain (ATM straddle, IV regime)",
     "source": "https://github.com/Weculp/Trading-Strategies",
     "claimed_number": "Sharpe 3.38 net, 12y OOS (2013-07 -> 2025-08)", "why": "options"},
    {"id": "EXT-GH-07", "missing_column": "the private conviction score",
     "source": "https://github.com/renee-jia/trading-bot",
     "claimed_number": "beats SPY/QQQ every year 2023-2026 (2025 +24.2% vs SPY +18.0%)",
     "why": "the scoring core is marked private; nothing to replicate"},
    {"id": "EXT-GH-09", "missing_column": "PatchTST forecast",
     "source": "https://github.com/vzeman/trading-autoresearch",
     "claimed_number": "walk-forward 2023 +24.1% / 2024 +25.6% / 2025 +23.0% vs SPY +23.7/+25.2/+17.2%",
     "why": "a trained transformer, not a one-line rule"},
    {"id": "EXT-GH-10", "missing_column": "sector-ETF rows + path-dependent exits",
     "source": "https://github.com/ChiefStarKid/roaring-trade-portfolio-rotation",
     "claimed_number": "none quoted (36,966 combinations swept)", "why": "sector-ETF rotation"},
    {"id": "EXT-GH-12", "missing_column": "a fitted HistGradientBoosting score",
     "source": "https://github.com/Jeremy-Xiang/alpha-factor-pipeline",
     "claimed_number": "L/S net Sharpe 0.93 (EW benchmark Sharpe 4.27 beats it)", "why": "ML pipeline"},
    {"id": "EXT-GH-13", "missing_column": "12-ETF asset-class rows",
     "source": "https://github.com/swaraaaa/FactorPortfolio",
     "claimed_number": "IR-opt cum. 828.8% vs SPY 535.6% (2007-2025), Sharpe 0.66", "why": "asset allocation"},
    {"id": "EXT-CO-01", "missing_column": "congress_net_buys (STOCK-Act disclosures)",
     "source": "https://www.composer.trade/trading-strategies",
     "claimed_number": "since 2024-04-26 cum. 57.08%, Sharpe 0.98, max DD 20.66%",
     "why": "no disclosure feed joined (check TRIAL-CONGRESS-IC first)"},
    {"id": "EXT-LIT-01", "missing_column": "congress_net_buys (STOCK-Act disclosures)",
     "source": "Ziobrowski 2004 JFQA; Belmont et al. 2022 JPubE",
     "claimed_number": "pre-2012 Senate +85bps/mo, House +55bps/mo; post-2012 none (House -26bps/6mo)",
     "why": "same feed; register as EXPECT DEAD post-2012 once joined"},
    {"id": "EXT-CO-02", "missing_column": "US/Europe index rows",
     "source": "https://www.composer.trade/trading-strategies",
     "claimed_number": "since 2024-10-24 cum. 52.42%, Sharpe 1.51, max DD 14.25%", "why": "country allocation"},
    {"id": "EXT-RD-02", "missing_column": "neural attention-factor loadings",
     "source": "https://www.reddit.com/r/quant/comments/1w8otws/tried_to_replicate_the_attention_factors_statarb/",
     "claimed_number": "paper Sharpe +2.30; independent replication -0.64 (2016-2026)",
     "why": "a trained model; the replication already failed"},
    {"id": "EXT-RD-03", "missing_column": "ibs (internal bar strength of the decision day) + ETF rows",
     "source": "https://www.reddit.com/r/algotrading/comments/1rjvxjy/found_a_simple_mean_reversion_setup_with_70_win/",
     "claimed_number": "70% win rate, no CAGR/Sharpe (SPY/QQQ 2011-2026)",
     "why": "a daily SPY/QQQ timing rule; ETFs are not on the panel"},
    {"id": "EXT-QC-01/02-regime-sleeve", "missing_column": "leveraged/inverse ETF rows (TQQQ/SOXL/UVXY/SQQQ)",
     "source": _QC + "536 / 629", "claimed_number": "(the regime sleeves of EXT-QC-01/02)",
     "why": "only the equity momentum sleeves are registered (qc536_*, qc629_*)"},
    {"id": "EXT-GH-01-etf-sleeve", "missing_column": "ETF rows (SPY/QQQ/IWM/DIA/GLD/TLT)",
     "source": "https://github.com/You07abd/ApexQuant", "claimed_number": "(the ETF sleeve of EXT-GH-01)",
     "why": "only the megacap satellite is registered (gh01_*)"},
]

#: The intangible pair waits on the re-extraction (scripts/pull_sec_fundamentals.py
#: FACTS gained "rd"/"sga" on 2026-09-26; the parquet on disk predates that). Once
#: sec_facts_history carries both facts, INTANGIBLES_EXTRACTED flips at import,
#: the rules join PAPER_STRATEGIES, `attach` builds the columns, and these rows go.
if not INTANGIBLES_EXTRACTED:
    EXT_NOT_REACHABLE += [
        {"id": r.discovery_id, "rule_id": r.id,
         "missing_column": (f"{INTANGIBLE_FACTS[f]} (built by strategy_library_ext.attach from "
                            f"sec_facts_history fact '{f}' = us-gaap:{tag})"),
         "source": r.source, "claimed_number": r.claimed_number,
         "why": ("the 9-tag extraction on disk has no R&D/SG&A; the tag is now in "
                 "pull_sec_fundamentals.FACTS and lands on the next extraction run")}
        for r, f, tag in zip(_intangible_rules(), ("rd", "sga"),
                             ("ResearchAndDevelopmentExpense",
                              "SellingGeneralAndAdministrativeExpense"))]


# ── the factory hook: put the six columns on the panel ──────────────────────

def _bars_from_wide(W: dict) -> "pd.DataFrame":
    import numpy as np
    import pandas as pd
    C = np.asarray(W["close"], dtype=float)
    ti, si = np.nonzero(np.isfinite(C))
    return pd.DataFrame({"symbol": np.asarray(W["symbols"])[si],
                         "date": pd.DatetimeIndex(W["dates"])[ti],
                         "close": C[ti, si]})


def derive_columns(panel):
    """The three columns the discovery rules read, from panel columns only.

    Every input is a price/regime column `build_panel` computed from bars dated
    on or before the row's date, so these are as point-in-time as their inputs.
    NaN stays NaN (a NaN regime is "unknown", which the engine treats as ON).
    """
    import numpy as np
    out = panel.copy()
    if {"mom_252", "vol_252"} <= set(out.columns):
        v = out["vol_252"].astype(float)
        out["sharpe_252"] = out["mom_252"].astype(float) / v.where(v > 0)
    if "mkt_stress" in out.columns:
        out["mkt_not_stress"] = 1.0 - out["mkt_stress"].astype(float)
    if {"px_vs_52w_high", "px_vs_52w_low"} <= set(out.columns):
        lo = (1.0 + out["px_vs_52w_low"].astype(float))
        out["low_vs_high_252"] = (1.0 + out["px_vs_52w_high"].astype(float)) / lo.where(lo > 0) - 1.0
    if {"days_since_earn", "date"} <= set(out.columns):
        # the latest KNOWN 8-K 2.02 is `days_since_earn` days before the row's
        # date (attach_8k: filed strictly before the date, its 3-day window
        # closed). A non-positive age would be an event on/after the decision
        # date and is refused (NaN), never turned into a weekday.
        import pandas as pd
        age = pd.to_numeric(out["days_since_earn"], errors="coerce")
        ok = age.notna() & (age >= 1)
        day = pd.to_datetime(out["date"]) - pd.to_timedelta(age.where(ok, 0.0), unit="D")
        out["ear_filed_dow"] = day.dt.dayofweek.astype(float).where(ok)
    for c in DERIVED_COLUMNS:
        if c in out.columns:
            out[c] = out[c].replace([np.inf, -np.inf], np.nan)
    return out


def attach(panel, W: dict | None = None):
    """(panel + the derived discovery columns + chunk C's pit_features, info).

    The derived columns come first and survive a pit_features failure (named in
    `info["pit_refused"]`), so a missing corpus cannot take the discovery rules
    down with it.
    """
    panel = derive_columns(panel)
    info0 = {"derived": {c: int(panel[c].notna().sum()) for c in DERIVED_COLUMNS if c in panel.columns}}
    panel, info0["paper"] = attach_paper_columns(panel)
    try:
        out, info = _attach_pit(panel, W)
    except Exception as e:                           # noqa: BLE001 -- named in info
        return panel, {**info0, "pit_refused": f"{type(e).__name__}: {e}"}
    return out, {**info0, **info}


# ── the paper rules' columns: revision clusters, 13F breadth, intangibles ────

#: 13F: the SEC deadline. s34's `fdate` equals `rdate`, so it cannot be used.
FILING_LAG_13F_DAYS = 45
#: a 13F reading older than this at the decision date is stale (a missed quarter).
MAX_13F_AGE_DAYS = 200
CLUSTER_GAP_DAYS = 30
CLUSTER_ACTIVE_DAYS = 30
OC_DEPRECIATION = 0.15
OC_GROWTH = 0.10


def _day(s):
    import pandas as pd
    t = pd.to_datetime(s, errors="coerce", utc=True)
    return t.dt.tz_convert(None).dt.normalize()


def _asof_join(panel, feats, value_cols, *, on_right: str, exact: bool, max_age_days=None,
               age_from: str | None = None):
    """Backward as-of join of per-symbol rows onto the panel (row order kept)."""
    import numpy as np
    import pandas as pd
    left = pd.DataFrame({"_i": np.arange(len(panel)), "symbol": panel["symbol"].astype(str).to_numpy(),
                         "date": pd.to_datetime(panel["date"]).dt.normalize().to_numpy()})
    left = left.sort_values("date", kind="mergesort")
    right = feats.sort_values(on_right, kind="mergesort")
    m = pd.merge_asof(left, right, left_on="date", right_on=on_right, by="symbol",
                      direction="backward", allow_exact_matches=exact)
    if max_age_days is not None and age_from:
        stale = (m["date"] - m[age_from]).dt.days > max_age_days
        m.loc[stale, value_cols] = np.nan
    m = m.sort_values("_i")
    return {c: m[c].to_numpy(dtype=float) for c in value_cols}


def cluster_age_frame(rev):
    """(symbol, day, cluster_start) per raise day: the chain a raise belongs to.

    Raises chain while consecutive raises on a name are <= CLUSTER_GAP_DAYS
    apart. A chain's START is its first raise, which depends only on earlier
    raises, so no later event can move it.
    """
    import pandas as pd
    ta = rev["target_action"].fillna("").astype(str).str.lower()
    r = pd.DataFrame({"symbol": rev["ticker"].astype(str).str.upper(), "day": _day(rev["event_date"])})
    r = r[(ta == "raises").to_numpy() & r["day"].notna().to_numpy()]
    r = r.sort_values(["symbol", "day"], kind="mergesort").drop_duplicates()
    gap = r.groupby("symbol")["day"].diff().dt.days
    r["cid"] = (gap.isna() | (gap > CLUSTER_GAP_DAYS)).cumsum()
    r["cluster_start"] = r.groupby("cid")["day"].transform("min")
    return r[["symbol", "day", "cluster_start"]]


def cluster_age_days(panel, rev):
    """Days since the ACTIVE raise cluster began, from raises strictly before the date."""
    import numpy as np
    import pandas as pd
    f = cluster_age_frame(rev)
    left = pd.DataFrame({"_i": np.arange(len(panel)), "symbol": panel["symbol"].astype(str).to_numpy(),
                         "date": pd.to_datetime(panel["date"]).dt.normalize().to_numpy()})
    m = pd.merge_asof(left.sort_values("date", kind="mergesort"), f.sort_values("day", kind="mergesort"),
                      left_on="date", right_on="day", by="symbol", direction="backward",
                      allow_exact_matches=False).sort_values("_i")
    since_last = (m["date"] - m["day"]).dt.days
    age = (m["date"] - m["cluster_start"]).dt.days.astype(float)
    return age.where(since_last <= CLUSTER_ACTIVE_DAYS).to_numpy(dtype=float)


def inst_breadth_frame(q_rows, link: dict, crsp, *, lag_days: int = FILING_LAG_13F_DAYS):
    """(symbol, rdate, available, inst_breadth_chg) from the aggregated 13F quarters.

    `q_rows`: [rdate, cusip8, inst_shares, n_managers, top_shares] (tr13f_quarterly.json).
    `crsp`: permno, date, ticker (crsp_pit_monthly_v1). A quarter is AVAILABLE at
    rdate + lag_days; callers join it only on dates strictly after that.
    """
    import numpy as np
    import pandas as pd
    q = pd.DataFrame(list(q_rows), columns=["rdate", "cusip8", "inst_shares", "n_managers", "top_shares"])
    q["rdate"] = pd.to_datetime(q["rdate"])
    q["permno"] = q["cusip8"].astype(str).map({str(k): int(v) for k, v in link.items()})
    q = q.dropna(subset=["permno"])
    q["permno"] = q["permno"].astype("int64")
    q = q.groupby(["permno", "rdate"], as_index=False)["n_managers"].max()
    q = q.sort_values(["permno", "rdate"], kind="mergesort")
    g = q.groupby("permno")
    prev_n, prev_d = g["n_managers"].shift(1), g["rdate"].shift(1)
    gap = (q["rdate"] - prev_d).dt.days
    consecutive = gap.between(80, 100)
    with np.errstate(divide="ignore", invalid="ignore"):
        q["inst_breadth_chg"] = np.log(q["n_managers"].astype(float) / prev_n.astype(float)).where(consecutive)
    c = crsp[["permno", "date", "ticker"]].dropna().copy()
    c["date"] = pd.to_datetime(c["date"])
    c = c.sort_values("date", kind="mergesort")
    life = c.groupby("permno").agg(first=("date", "min"), last=("date", "max"), ticker=("ticker", "last"))
    crsp_end = c["date"].max()
    q = q.join(life, on="permno", how="inner")
    slack = pd.Timedelta(days=92)
    alive = (q["rdate"] >= q["first"] - slack) & (
        (q["rdate"] <= q["last"] + slack) | (q["last"] >= crsp_end - pd.Timedelta(days=35)))
    q = q[alive & q["inst_breadth_chg"].notna()]
    q = q.sort_values("n_managers", kind="mergesort").drop_duplicates(["ticker", "rdate"], keep="last")
    q["symbol"] = q["ticker"].astype(str).str.upper()
    q["available"] = q["rdate"] + pd.Timedelta(days=lag_days)
    return q[["symbol", "rdate", "available", "inst_breadth_chg"]].reset_index(drop=True)


def intangibles_frame(facts):
    """(symbol, filed, available, rd_intensity, org_capital) from ANNUAL first filings."""
    import numpy as np
    import pandas as pd
    lo, hi = 350, 380
    f = facts.copy()
    f["filed"] = pd.to_datetime(f["filed"])
    f = f.sort_values("filed", kind="mergesort")
    flows = f[f["fact"].isin(tuple(INTANGIBLE_FACTS)) & pd.to_numeric(f["period_days"], errors="coerce").between(lo, hi)]
    flows = flows.drop_duplicates(["ticker", "fact", "end"], keep="first")
    assets = f[f["fact"] == "assets"].drop_duplicates(["ticker", "end"], keep="first")
    w = flows.pivot_table(index=["ticker", "end"], columns="fact", values="val", aggfunc="first")
    filed = flows.groupby(["ticker", "end"])["filed"].max()
    w = w.join(filed).join(assets.set_index(["ticker", "end"])["val"].rename("assets")).reset_index()
    for c in INTANGIBLE_FACTS:
        if c not in w.columns:
            w[c] = np.nan
    a = w["assets"].where(w["assets"] > 0)
    w["rd_intensity"] = w["rd"] / a
    w["end_d"] = pd.to_datetime(w["end"])
    w = w.sort_values(["ticker", "end_d"], kind="mergesort")
    oc = np.full(len(w), np.nan)
    prev_t, prev_end, prev_oc = None, None, np.nan
    for i, (t, e, s) in enumerate(zip(w["ticker"].to_numpy(), w["end_d"], w["sga"].to_numpy(dtype=float))):
        if not np.isfinite(s):
            prev_t, prev_oc = t, np.nan
            continue
        chained = (t == prev_t and np.isfinite(prev_oc) and prev_end is not None
                   and (e - prev_end).days <= 400)
        oc[i] = ((1 - OC_DEPRECIATION) * prev_oc + s) if chained else s / (OC_GROWTH + OC_DEPRECIATION)
        prev_t, prev_end, prev_oc = t, e, oc[i]
    w["org_capital"] = oc / a.to_numpy(dtype=float)
    w["symbol"] = w["ticker"].astype(str).str.upper()
    w["available"] = w["filed"] + pd.Timedelta(days=2)
    return w[["symbol", "filed", "available", "rd_intensity", "org_capital"]]


def attach_paper_columns(panel):
    """(panel + cluster_age_days / inst_breadth_chg / rd_intensity / org_capital, info).

    Each source is read under its own try: a missing file is a named refusal in
    `info` and the rules over that column are refused by name by the factory.
    """
    import json

    import pandas as pd

    from backend.services import pit_features as pf
    opt = pf._optimus()
    out = panel.copy()
    info: dict = {}
    try:
        p = opt / "analyst" / "target_revisions.parquet"
        if not p.exists():
            info["cluster_age_days"] = f"REFUSED: no {p.name}"
        else:
            rev = pd.read_parquet(p, columns=["ticker", "event_date", "target_action"])
            out["cluster_age_days"] = cluster_age_days(out, rev)
            info["cluster_age_days"] = {"non_nan": int(out["cluster_age_days"].notna().sum()),
                                        "pit": "raises strictly before the date"}
    except Exception as e:                          # noqa: BLE001 -- named
        info["cluster_age_days"] = f"REFUSED: {type(e).__name__}: {e}"
    try:
        wr = opt / "wrds"
        qp, lp = wr / "tr13f_quarterly.json", wr / "tr13f_permno_link.json"
        cp = opt / "crsp_pit" / "crsp_pit_monthly_v1.parquet"
        missing = [x.name for x in (qp, lp, cp) if not x.exists()]
        if missing:
            info["inst_breadth_chg"] = f"REFUSED: missing {missing}"
        else:
            fr = inst_breadth_frame(json.loads(qp.read_text(encoding="utf-8")),
                                    json.loads(lp.read_text(encoding="utf-8")),
                                    pd.read_parquet(cp, columns=["permno", "date", "ticker"]))
            got = _asof_join(out, fr, ["inst_breadth_chg"], on_right="available", exact=False,
                             max_age_days=MAX_13F_AGE_DAYS, age_from="rdate")
            out["inst_breadth_chg"] = got["inst_breadth_chg"]
            info["inst_breadth_chg"] = {
                "non_nan": int(out["inst_breadth_chg"].notna().sum()),
                "quarters": [str(fr["rdate"].min().date()), str(fr["rdate"].max().date())],
                "pit": f"rdate + {FILING_LAG_13F_DAYS}d strictly before the date (fdate == rdate)"}
    except Exception as e:                          # noqa: BLE001 -- named
        info["inst_breadth_chg"] = f"REFUSED: {type(e).__name__}: {e}"
    try:
        fp = opt / "fundamentals_sec" / "sec_facts_history.parquet"
        facts = pd.read_parquet(fp) if fp.exists() else None
        if facts is None or not set(INTANGIBLE_FACTS) <= set(facts["fact"].unique()):
            info["intangibles"] = ("AWAITING EXTRACTION: sec_facts_history has no rd/sga facts "
                                   "(re-run scripts/pull_sec_fundamentals.py --universe-from-bars)")
        else:
            fr = intangibles_frame(facts)
            cols = list(INTANGIBLE_FACTS.values())
            got = _asof_join(out, fr, cols, on_right="available", exact=True,
                             max_age_days=460, age_from="filed")
            for c in cols:
                out[c] = got[c]
            info["intangibles"] = {c: int(out[c].notna().sum()) for c in cols}
    except Exception as e:                          # noqa: BLE001 -- named
        info["intangibles"] = f"REFUSED: {type(e).__name__}: {e}"
    return out, info


def _attach_pit(panel, W: dict | None = None):
    """(panel + the six pit_features columns and supports, info dict).

    The factory scores rules at month-end rows (`is_month_end`) on that day's
    close and enters at the next open. The features are therefore computed for
    decision date `t + 1 day`, i.e. from input rows dated on or before `t` --
    news first seen by the end of `t` (UTC), revisions with `event_date` on `t`
    or earlier, filings with `filed + 2d` before `t + 1` -- and mapped back to
    the row dated `t`. Nothing dated after `t` can enter.
    """
    import json

    import pandas as pd

    from backend.services import pit_features as pf
    opt = pf._optimus()
    p = panel
    rows = p["is_month_end"] if "is_month_end" in p.columns else pd.Series(True, index=p.index)
    me = pd.DatetimeIndex(sorted(pd.to_datetime(p.loc[rows, "date"]).unique()))
    if not len(me):
        return panel, {"status": "NO_DATES"}
    dec = me + pd.Timedelta(days=1)
    bars = _bars_from_wide(W) if W is not None else None
    info: dict = {"pit": "features at t+1d from rows dated <= t, mapped back to t"}

    def _read(path, **kw):
        try:
            return pd.read_parquet(path, **kw) if path.exists() else None
        except Exception as e:                      # noqa: BLE001 -- named in info
            info[f"refused:{path.name}"] = f"{type(e).__name__}: {e}"
            return None

    rev = _read(opt / "analyst" / "target_revisions.parquet")
    actor = _read(opt / "actor_corpus" / "ibes_graded.parquet",
                  columns=["estimid", "direction", "outcome", "public_at"])
    facts = _read(opt / "fundamentals_sec" / "sec_facts_history.parquet")
    mp = opt / "pit_features" / "firm_estimid_map.json"
    fmap = json.loads(mp.read_text()) if mp.exists() else {}
    info["firm_map"] = (f"{len(fmap)} firms from {mp.name}" if fmap else
                        "ABSENT: every broker at the prior weight (run python -m "
                        "backend.services.pit_features to measure the map)")
    news = pf.load_news_corpus() if (opt / "news_corpus").exists() else None
    sess = (pd.DatetimeIndex(W["dates"]) if W is not None else None)
    frame = pf.compute(dec, bars=bars, revisions=rev, news_rows=news, actor_corpus=actor,
                       fundamentals=facts, firm_map=fmap, sessions=sess,
                       tickers=p["symbol"].astype(str).unique())
    f = frame.reset_index().rename(columns={"ticker": "symbol"})
    f["date"] = f["date"] - pd.Timedelta(days=1)
    cols = [c for c in f.columns if c not in ("symbol", "date")]
    base = panel.drop(columns=[c for c in cols if c in panel.columns])
    base = base.assign(_d=pd.to_datetime(base["date"]).dt.normalize(),
                       _s=base["symbol"].astype(str))
    out = base.merge(f.rename(columns={"symbol": "_s", "date": "_d"}), on=["_s", "_d"],
                     how="left").drop(columns=["_s", "_d"])
    out.index = panel.index
    info["support_non_nan"] = {c: int(out[c].notna().sum()) for c in pf.FEATURE_COLUMNS}
    return out, info
