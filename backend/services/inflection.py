"""The SanDisk archetype: find a business whose ECONOMICS just changed shape.

    from backend.services import inflection as INF
    panel = INF.quarterly_panel()
    fires = INF.detect(panel)

WHY THIS MODULE EXISTS, AND WHY IT IS NOT ANOTHER RANKER
========================================================
`NEGATIVE_RESULTS.md` §59, §60 and §61 closed three attempts at the same
question -- *how do I order the whole cross-section?* -- and all three failed.
This asks a different question:

    Which businesses just underwent a NONLINEAR transition in their own
    economics, and is that observable before the market re-rates them?

That is a DETECTOR, not a ranker. It is allowed to be silent for months and fire
on nine names. A cross-sectional ranker must have an opinion about every name on
every date, which is exactly why it ends up ranking noise.

THE ARCHETYPE, AND THE ONE IDEA THAT MAKES IT WORK
==================================================
SanDisk, from its own filings, dated by when they were FILED:

    filed        rev      QoQ     gross margin
    2025-05-12   $1.70B   -9.7%   22.5%     <- the trough
    2025-11-07   $2.31B  +36.2%   29.8%     <- FIRES
    2026-01-30   $3.02B  +31.1%   50.9%
    2026-05-01   $5.95B  +96.7%   78.4%

The price on 2025-11-07 was $239.48. It is $1,766 now.

Western Digital -- the same industry, the same customers, the same AI demand --
over the identical window: **+8.2%, +7.1%, +10.6% QoQ with gross margin crawling
43.5% -> 50.2%.** It went up 176%; SanDisk went up 638%.

So the discriminator cannot be "revenue is growing". Both were growing. It is:

    REVENUE ACCELERATION ALONE is volume OR price.
    REVENUE ACCELERATION *WITH* MARGIN EXPANSION is PRICING POWER.

Sandisk's own release attributed roughly two thirds of its sequential growth to
**higher pricing** and one third to volume. Price lands in gross margin; volume
does not. That conjunction is the whole detector, and it is the reason this is
not a momentum factor wearing a new hat: a company can win share, grow volume
and post 40% sequential growth at a constant margin, and that is a good business
without a changed one.

The economic story the conjunction is standing in for:

    commodity -> structural bottleneck -> supply tightness -> pricing power
    -> mix shift to the scarce use -> earnings explosion -> revisions -> re-rating

We can observe the fourth arrow in a filing. The market prices the seventh.

WHAT THIS MODULE REFUSES TO DO
==============================
* It does not produce an expected return. The rank->return calibration that
  would license one does not exist for this signal, and §61 is what happens when
  a number gets quoted before it has one.
* It does not rank. `detect()` returns the rows that FIRE and says why.
* It never reads `end` as if it were knowable. Every feature is keyed on
  `filed`, the date the fact became public, and a row filed after the as-of date
  does not exist. The panel carries restatements of the same `end` filed a year
  later -- Western Digital's 2024-09-27 quarter was refiled in 2025 at $2.21B
  against its original $4.09B, because SanDisk had been spun out of it -- and
  reading the restated figure as of 2024 would be a 46% collapse that nobody
  could have seen.

THE HAZARD THIS SHARES WITH EVERY CORPORATE-ACTION SIGNAL
=========================================================
A spin-off, a large acquisition or a divestiture moves sequential revenue by
tens of percent for reasons that have nothing to do with pricing power, and this
detector cannot tell that apart from the real thing. Western Digital's spin-off
of SanDisk is in this very panel. Two partial defences, both declared rather
than hidden: the margin condition kills most of them (a divestiture rarely lifts
gross margin by 2 points in the same quarter it cuts revenue), and
`corporate_action_suspect` flags the shape so the base rate can be measured with
those rows both in and out.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from backend import config as _config

logger = logging.getLogger(__name__)

#: A calendar quarter, loosely. XBRL period lengths wander with fiscal calendars
#: and 52/53-week years, so this is deliberately wide; anything outside it is a
#: half-year, a nine-month YTD figure or an annual, and mixing those into a
#: sequential series manufactures growth that never happened. That exact defect
#: -- annual 10-K revenue compared against quarterly 10-Q revenue -- produced
#: NVDA `gp_at` readings of 0.742/0.236/0.225 on 2026-09-23.
QUARTER_DAYS = (80, 100)

#: Facts the detector needs. `revenue` and `cogs` carry the whole signal;
#: `operating_income` is read for context on the receipt and never gated on.
FACTS = ("revenue", "cogs", "operating_income")

#: THE ARCHETYPE, in three conditions that must hold TOGETHER.
#:
#: These are declared here, above the function, so a reader can see they were
#: not tuned after looking at the base rate. They came from ONE case (SanDisk)
#: and its matched control (Western Digital), which makes them a hypothesis to
#: be measured on the other 2,378 tickers -- not a finding. `A PRIOR CHOSEN
#: AFTER THE DIAGNOSTIC IS NOT A PRIOR` (2026-09-22): the honest description of
#: these numbers is that they are read off one example, and the base-rate test
#: is what they have to survive.
MIN_REV_QOQ = 0.15          #: this quarter's sequential revenue growth
MIN_GM_EXPANSION = 0.02     #: gross margin up 2 points on the prior quarter
MIN_ACCELERATION = 0.10     #: and growing FASTER than it was growing

#: Below this, sequential percentages are arithmetic noise on a rounding error.
MIN_REVENUE_USD = 50e6


def facts_path() -> Path:
    """The SEC history, through config so the frozen build resolves it."""
    return (Path(_config.OPTIMUS_LEDGER_DIR) / "fundamentals_sec"
            / "sec_facts_history.parquet")


def load_facts(path: Optional[Path] = None) -> pd.DataFrame:
    p = Path(path) if path else facts_path()
    if not p.exists():
        raise FileNotFoundError(
            f"no SEC fact history at {p}. Build it with "
            f"`python -m scripts.pull_sec_fundamentals`.")
    d = pd.read_parquet(p)
    d["filed"] = pd.to_datetime(d["filed"])
    d["end"] = pd.to_datetime(d["end"])
    return d


#: An annual period, for deriving the fourth quarter. Same width as
#: `fundamental_features.ANNUAL_DAYS`.
ANNUAL_DAYS = (350, 380)


def derive_q4(facts: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct the fourth quarter, which XBRL never tags as a quarter.

    THE DEFECT THIS FIXES, MEASURED 2026-09-24
    ------------------------------------------
    17% of quarter-rows in the raw panel follow a gap, and the gap's median is
    **182 days with a p90 of 184** -- exactly two quarters, every time. That is
    not patchy vendor data. A filer reports Q1-Q3 on 10-Qs as ~90-day periods,
    and then reports Q4 inside the 10-K *as part of the annual figure*. There is
    no 90-day fact for it, so a puller that keeps only 80-100 day periods drops
    one quarter in four for essentially every company on the exchange.

    It cost the archetype its best signal. SanDisk's June-2025 quarter is
    missing for this reason, which made the next comparison span 189 days, which
    the gap guard correctly refused -- so the detector stayed silent on
    2025-11-07 at $239 and only fired on 2026-05-01 at $1,187. The data hole, not
    the hypothesis, ate 590 points of that move.

    Q4 = annual - (Q1 + Q2 + Q3) of the same fiscal year, for FLOW facts only.
    Stock facts (assets, cash, debt, equity, shares) are balances at an instant
    and summing them is meaningless -- the same distinction that produced NVDA
    `gp_at` readings of 0.742/0.236/0.225 on 2026-09-23.

    PIT: the derived quarter's `filed` is the ANNUAL filing's `filed`, because
    that is when the arithmetic first became possible. Dating it to the fiscal
    period end would hand a decision three months of hindsight.
    """
    flows = facts[facts["fact"].isin(FACTS)].copy()
    ann = flows[flows["period_days"].between(*ANNUAL_DAYS)]
    qtr = flows[flows["period_days"].between(*QUARTER_DAYS)]
    if ann.empty or qtr.empty:
        return pd.DataFrame(columns=facts.columns)

    ann = ann.sort_values("filed").drop_duplicates(["ticker", "end", "fact"], keep="first")
    qtr = qtr.sort_values("filed").drop_duplicates(["ticker", "end", "fact"], keep="first")

    # Index the quarters ONCE. The first version re-filtered the whole 116k-row
    # quarterly frame inside the loop, ~7,000 times, which cost about two
    # minutes on every script that built a panel.
    qidx = {key: g for key, g in qtr.groupby(["ticker", "fact"], sort=False)}

    out = []
    for (tkr, fact), a in ann.groupby(["ticker", "fact"], sort=False):
        qs = qidx.get((tkr, fact))
        if qs is None or qs.empty:
            continue
        ends = qs["end"].values
        for r in a.itertuples():
            # The three quarters strictly INSIDE this fiscal year. `end` must
            # fall in (year_start, year_end): a quarter ending on the annual end
            # date is the very Q4 we are deriving, not an input to it.
            lo = r.end - pd.Timedelta(days=int(r.period_days or 365))
            m = (ends > np.datetime64(lo)) & (ends < np.datetime64(r.end))
            got = qs[m]
            if len(got) != 3:
                continue        # a REFUSAL: 2 or 4 quarters cannot be subtracted
            val = float(r.val) - float(got["val"].sum())
            if not np.isfinite(val):
                continue
            q3_end = got["end"].max()
            days = (r.end - q3_end).days
            if not (QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1]):
                continue        # the residual is not a quarter's worth of time
            out.append({
                "ticker": tkr, "cik": r.cik, "fact": fact,
                # The annual filing's date. This is the PIT claim.
                "filed": r.filed, "end": r.end, "start": q3_end,
                "period_days": float(days), "val": val,
                "form": str(r.form) + "+derivedQ4"})
    return pd.DataFrame(out)


def quarterly_panel(facts: Optional[pd.DataFrame] = None,
                    *, tickers: Optional[Iterable[str]] = None,
                    with_q4: bool = True) -> pd.DataFrame:
    """One row per (ticker, fiscal quarter) at its FIRST public disclosure.

    First disclosure, not latest restatement: the earliest `filed` for a given
    `end` is the earnings release that the market actually reacted to, and it is
    the only version that existed at the time. Taking the latest would let a
    2025 restatement of a 2024 quarter into a 2024 decision.
    """
    d = load_facts() if facts is None else facts
    if tickers is not None:
        d = d[d["ticker"].isin(set(tickers))]
    q = d[d["fact"].isin(FACTS) & d["period_days"].between(*QUARTER_DAYS)].copy()
    if with_q4:
        q4 = derive_q4(d)
        if not q4.empty:
            # A real 90-day fact beats a derived one wherever both exist.
            q = pd.concat([q, q4], ignore_index=True)
            q = q.sort_values("form").drop_duplicates(
                ["ticker", "end", "fact"], keep="first")
    if q.empty:
        return pd.DataFrame(columns=["ticker", "end", "filed", "revenue", "cogs"])

    # Earliest filing wins per (ticker, end, fact).
    q = q.sort_values("filed").drop_duplicates(["ticker", "end", "fact"], keep="first")
    wide = q.pivot_table(index=["ticker", "end"], columns="fact", values="val",
                         aggfunc="last")
    # The disclosure DATE is the earliest filing across the facts of that
    # quarter: revenue and cogs arrive in the same release.
    filed = q.groupby(["ticker", "end"])["filed"].min()
    form = q.sort_values("filed").groupby(["ticker", "end"])["form"].first()
    out = wide.join(filed).join(form).reset_index()
    for c in FACTS:
        if c not in out.columns:
            out[c] = np.nan
    return out.sort_values(["ticker", "end"]).reset_index(drop=True)


def add_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Sequential growth, margin and acceleration, per ticker, in fiscal order.

    Every feature is a function of THIS quarter and earlier quarters only, so a
    row is fully computable on its own `filed` date.
    """
    d = panel.sort_values(["ticker", "end"]).copy()
    g = d.groupby("ticker", sort=False)

    d["rev_prev"] = g["revenue"].shift(1)
    d["rev_qoq"] = d["revenue"] / d["rev_prev"] - 1.0
    d["rev_qoq_prev"] = g["rev_qoq"].shift(1)
    d["accel"] = d["rev_qoq"] - d["rev_qoq_prev"]
    d["rev_yoy"] = d["revenue"] / g["revenue"].shift(4) - 1.0

    # Gross margin. This is the half that separates pricing power from volume.
    d["gm"] = 1.0 - d["cogs"] / d["revenue"]
    d.loc[~np.isfinite(d["gm"]) | (d["gm"] < -1) | (d["gm"] > 1), "gm"] = np.nan
    d["gm_prev"] = g["gm"].shift(1)
    d["gm_chg"] = d["gm"] - d["gm_prev"]
    d["gm_chg_4q"] = d["gm"] - g["gm"].shift(4)

    d["op_margin"] = d["operating_income"] / d["revenue"]

    # A fiscal quarter that follows a GAP is not a sequential comparison. SNDK's
    # own series is missing 2025-06, and dividing across that hole would invent
    # a two-quarter jump and report it as one quarter's acceleration.
    gap = g["end"].diff().dt.days
    d["prior_gap_days"] = gap
    d["sequential_ok"] = gap.between(60, 130)

    # The corporate-action tell: revenue moving by more than half in either
    # direction is far more often a spin-off, an acquisition or a change of
    # reporting entity than an organic move. Flagged, never silently dropped --
    # the base rate is measured with these rows in AND out.
    d["corporate_action_suspect"] = d["rev_qoq"].abs() > 0.50
    return d


def detect(panel: pd.DataFrame, *,
           min_rev_qoq: float = MIN_REV_QOQ,
           min_gm_expansion: float = MIN_GM_EXPANSION,
           min_acceleration: float = MIN_ACCELERATION,
           min_revenue: float = MIN_REVENUE_USD) -> pd.DataFrame:
    """Rows where all three archetype conditions hold at once.

    The conjunction is the point. Each condition alone is common and cheap:
    plenty of companies grow 15% sequentially, plenty expand margin 2 points,
    plenty accelerate. Requiring all three in the same quarter is the claim that
    the BUSINESS changed rather than the weather.
    """
    d = panel if "rev_qoq" in panel.columns else add_features(panel)
    fires = (
        d["sequential_ok"]
        & (d["revenue"] >= min_revenue)
        & (d["rev_qoq"] >= min_rev_qoq)
        & (d["gm_chg"] >= min_gm_expansion)
        & (d["accel"] >= min_acceleration)
    )
    out = d[fires.fillna(False)].copy()
    out["why"] = [
        f"revenue +{r.rev_qoq*100:.0f}% sequentially (was "
        f"{(r.rev_qoq_prev or 0)*100:+.0f}%, so accelerating by "
        f"{r.accel*100:.0f} points) WHILE gross margin went "
        f"{r.gm_prev*100:.1f}% -> {r.gm*100:.1f}% (+{r.gm_chg*100:.1f}pp). "
        f"Growth with expanding margin is PRICING POWER; growth at a flat "
        f"margin is volume."
        + (" NOTE: revenue moved >50%, which is more often a spin-off or "
           "acquisition than an organic move -- verify the entity."
           if r.corporate_action_suspect else "")
        for r in out.itertuples()]
    return out.sort_values("filed").reset_index(drop=True)


def asof(panel: pd.DataFrame, when: Any) -> pd.DataFrame:
    """Only what had been FILED by `when`. The PIT gate for any live use."""
    d = panel if "rev_qoq" in panel.columns else add_features(panel)
    return d[d["filed"] <= pd.Timestamp(when)]


def latest_per_ticker(d: pd.DataFrame) -> pd.DataFrame:
    """The most recently disclosed quarter for each ticker."""
    return (d.sort_values("filed").drop_duplicates("ticker", keep="last")
            .reset_index(drop=True))
