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

from backend.services.strategy_library import Strategy, col, combo, gated, sector_rel, within_top

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
DERIVED_COLUMNS: tuple[str, ...] = ("sharpe_252", "mkt_not_stress", "low_vs_high_252")


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


#: chunk C's eight rules (pinned by test_pit_features) and the discovery rules.
CHUNK_C_STRATEGIES: list = _rules()
DISCOVERY_STRATEGIES: list = _discovery_rules()
EXTRA_STRATEGIES: list = CHUNK_C_STRATEGIES + DISCOVERY_STRATEGIES

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
    try:
        out, info = _attach_pit(panel, W)
    except Exception as e:                           # noqa: BLE001 -- named in info
        return panel, {**info0, "pit_refused": f"{type(e).__name__}: {e}"}
    return out, {**info0, **info}


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
