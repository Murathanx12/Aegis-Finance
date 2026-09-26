"""Chunk C's rules over the six `pit_features` columns -- for the D builder to import.

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

from backend.services.strategy_library import Strategy, col, combo, gated

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


EXTRA_STRATEGIES: list = _rules()

#: Keys every entry exposes through `.meta()`; pinned by the test.
REQUIRED_KEYS: tuple[str, ...] = ("id", "family", "economic_reason", "source",
                                  "first_registered_utc", "forward_only", "requires")


# ── the factory hook: put the six columns on the panel ──────────────────────

def _bars_from_wide(W: dict) -> "pd.DataFrame":
    import numpy as np
    import pandas as pd
    C = np.asarray(W["close"], dtype=float)
    ti, si = np.nonzero(np.isfinite(C))
    return pd.DataFrame({"symbol": np.asarray(W["symbols"])[si],
                         "date": pd.DatetimeIndex(W["dates"])[ti],
                         "close": C[ti, si]})


def attach(panel, W: dict | None = None):
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
