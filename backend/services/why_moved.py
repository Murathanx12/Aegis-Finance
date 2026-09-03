"""Why the book moved — and the only two things about that we can grade.

WHAT MURAT ASKED FOR
====================
"my portfolio dropped a bit yesterday, lost 1k. why did this happen, llm should
try to reason multiple times and compare itself to reality on why. this is the
learning we want."

The trap in that sentence is the word "why". A single day's move has no
recoverable cause: the counterfactual world where Iran did not sign and the
book still fell is not observable, and no amount of language-model reasoning
creates it. **This module never assigns a cause, and any language here or
downstream that claims it knows why the market moved is a defect.** What it
does instead is split the question into a part that is arithmetic and a part
that is checkable, and refuse to write down the part that is neither.

THE THREE LAYERS, AND WHAT EACH IS WORTH
----------------------------------------
1. **Attribution (arithmetic).** Shares x price change, per position, summed.
   The market leg is book beta x benchmark return; the sector leg is the
   book's sector-ETF exposure net of the market; the residual is what neither
   explains. This is GROUND TRUTH, needs no language model, and is returned
   even when every other layer is dark. An attribution with no hypotheses is a
   valid answer. A fabricated hypothesis is not.

2. **Hypotheses (unproven, preserved plural).** Seven specialists are asked
   SEPARATELY — one prompt asked to do all seven does none of them, and a panel
   that agrees is one forecaster (CANON §20). Competing explanations are kept
   side by side forever. They are never scored against each other, never ranked
   into a winner, and the module has no concept of "the reason".

3. **Grading (the only measurement).** Exactly two mechanical checks exist:

   * **Cross-asset corroboration — the COHERENCE instrument.** A hypothesis
     must state what ELSE should have moved on that same, already-past day —
     oil up, long duration underperforming, VIX up 3%. Those instruments'
     actual moves are fetched and every assertion is scored right now: hit,
     miss, or unavailable. This is the fast clock. A specialist that blames
     geopolitics whenever the tape is red, but whose stated signature is
     repeatedly absent, loses reliability in DAYS rather than months.
   * **The forward claim — the SKILL instrument.** Each hypothesis states one
     thing that has not happened yet, as an `Observable` with a probability and
     a frozen horizon, minted through `belief_state.make_prediction` so the
     existing resolver grades it on schedule with everything else.

   THE TWO ARE NEVER ADDED TOGETHER. A corroboration hit says the stated
   mechanism was COHERENT with the rest of the market that day; an incoherent
   explanation is refuted, which is worth knowing, but coherence about the past
   is not forecasting skill and does not become skill however many days
   accumulate. Only the resolved PredictionRecords speak to skill.

   A hit is also not evidence the hypothesis is TRUE — the signature of a rates
   shock is present on plenty of days that had nothing to do with rates.
   Absence is the informative direction, and it is the direction that accrues
   fastest.

   And the rate is counted ONLY over instruments the prompt did not already
   disclose. The lenses are shown the book's returns, the benchmark's and each
   held sector's, so "XLE up" from a lens just told "Energy +4.66%" is the
   input read back and hits every time. The first live run measured the gap:
   100% on book tickers, 89% on sector ETFs, 84% on everything external. The
   external number is the only one that is ever quoted (`derivable_assets` is
   computed from the prompt payload itself so the split cannot rot).

WHAT IS REFUSED, AND WHY THAT IS THE POINT
------------------------------------------
A hypothesis with no checkable corroboration AND no forward claim is REJECTED
at parse time and the rejection is counted and reported. That single rule is
the entire difference between this module and market commentary: commentary
costs nothing to produce and can never be wrong, so it never teaches anyone
anything. Rejections are reported per specialist because a lens that produces
mostly ungradeable prose is telling you something about itself.

DEGRADED IS NOT FABRICATED
--------------------------
No key, an API that will not answer, JSON that will not parse: the status says
so, the hypothesis list is empty, and the attribution still comes back. There
is no path in this file from "the model did not answer" to "here is what
probably happened".

DESCRIPTIVE ONLY
----------------
Nothing here recommends an action. Hypothesis text that reaches for one is
refused rather than sanitised — the sanitised version was still written by a
forecaster that thought it was allowed to advise.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import pandas as pd

from backend.cache import cached
from backend.config import (WHY_MOVED_BENCHMARK, WHY_MOVED_BETA_LOOKBACK_DAYS,
                            WHY_MOVED_CORROBORATION_UNIVERSE,
                            WHY_MOVED_FORBIDDEN_PATTERN,
                            WHY_MOVED_IDEA_JACCARD, WHY_MOVED_LLM_TIMEOUT_S,
                            WHY_MOVED_MAGNITUDE_MAX_PCT,
                            WHY_MOVED_MAGNITUDE_MIN_PCT_FLOOR,
                            WHY_MOVED_MAX_CORROBORATION_PER_HYPOTHESIS,
                            WHY_MOVED_MAX_HYPOTHESES_PER_SPECIALIST,
                            WHY_MOVED_MAX_TOKENS, WHY_MOVED_MIN_BETA_OBS,
                            WHY_MOVED_MODEL, WHY_MOVED_PRICE_CACHE_TTL,
                            WHY_MOVED_PRICE_PAD_DAYS, WHY_MOVED_SECTOR_ETFS,
                            WHY_MOVED_STOPWORDS, WHY_MOVED_TEMPERATURE,
                            WHY_MOVED_TICKER_SECTOR)
from backend.services.belief_state import (HORIZONS, Observable,
                                           PredictionRecord, make_prediction)

logger = logging.getLogger(__name__)

_FORBIDDEN = re.compile(WHY_MOVED_FORBIDDEN_PATTERN, re.I)
_WORD = re.compile(r"[a-z0-9^=\-\.]+")

MODULE_VERSION = "why_moved/1.0.0"


class PricingError(RuntimeError):
    """The book could not be priced, so there is no attribution.

    Raised rather than returned: a book missing a close is not a book that
    moved zero. The house failure mode is code that runs green and silently
    does nothing, and a plausible $0.00 is exactly what that looks like from
    the outside.
    """


# ── the deterministic layer ─────────────────────────────────────────────────

@dataclass
class PositionMove:
    """One position's arithmetic. No opinion in this object."""
    ticker: str
    shares: float
    price_prev: float
    price_now: float
    value_prev: float
    value_now: float
    pnl_usd: float
    return_pct: float
    weight_prev: float
    contribution_pct: float          # weight x return, in percent of the book
    contribution_bps: float          # the same number in basis points
    beta: float
    beta_source: str                 # "estimated" | "fallback_insufficient_history"
    sector: str | None
    sector_return_pct: float | None


@dataclass
class Attribution:
    """The ground truth a language model is asked to explain.

    `idiosyncratic_pct` is a RESIDUAL, defined as what the market and sector
    legs do not account for. It is not "stock-specific news"; it is the part of
    the arithmetic those two factors leave over, which on a 12-name small-cap
    book is usually most of it.
    """
    as_of: str
    prev_close_date: str
    requested_date: str
    book_value_prev: float
    book_value_now: float
    pnl_usd: float
    pnl_pct: float
    benchmark: str
    benchmark_return_pct: float
    book_beta: float
    market_component_pct: float
    market_component_usd: float
    sector_component_pct: float
    sector_component_usd: float
    idiosyncratic_pct: float
    idiosyncratic_usd: float
    positions: list[PositionMove]
    sector_returns_pct: dict[str, float]
    sector_unmapped: list[str]
    beta_fallbacks: list[str]
    notes: list[str] = field(default_factory=list)


def _closes(panel: pd.DataFrame, ticker: str) -> pd.Series:
    """Numeric closes for one column, NaNs dropped. Empty if absent."""
    if ticker not in panel.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(panel[ticker], errors="coerce").dropna()


def _sessions(panel: pd.DataFrame, benchmark: str) -> pd.DatetimeIndex:
    """The benchmark's own trading calendar.

    The book's own names are the wrong calendar: a halted or thinly traded
    small cap can miss a session the market held, and a book date defined by
    "some position printed" drifts per run.
    """
    s = _closes(panel, benchmark)
    if s.empty:
        raise PricingError(
            f"benchmark {benchmark} has no usable closes in the panel — "
            f"without it there is no trading calendar and no market leg")
    return pd.DatetimeIndex(s.index)


def resolve_session(panel: pd.DataFrame, requested: str | date, *,
                    benchmark: str = WHY_MOVED_BENCHMARK) -> tuple[str, str]:
    """(as_of, previous close) — the last session at or before `requested`.

    Returns the date actually used so every caller can SAY which day it graded.
    A weekend or a holiday walks back; it never silently grades a different day
    than the one it reports.
    """
    idx = _sessions(panel, benchmark)
    want = pd.Timestamp(str(requested)[:10])
    eligible = idx[idx <= want]
    if len(eligible) < 2:
        raise PricingError(
            f"the price panel holds {len(eligible)} session(s) at or before "
            f"{want.date()} — a one-day move needs two closes")
    return str(eligible[-1].date()), str(eligible[-2].date())


def _beta(stock: pd.Series, bench: pd.Series, *, min_obs: int) -> tuple[float, str]:
    """OLS beta on overlapping daily returns, or 1.0 and a reason.

    A beta fitted on a handful of bars is a random number with a t-stat, so
    below `min_obs` the position is carried at 1.0 and the caller NAMES it.
    Pretending to an estimate is worse than declaring a default.
    """
    j = pd.concat([stock.pct_change(), bench.pct_change()], axis=1).dropna()
    if len(j) < min_obs:
        return 1.0, "fallback_insufficient_history"
    var = float(j.iloc[:, 1].var())
    if var <= 0:
        return 1.0, "fallback_zero_benchmark_variance"
    return float(j.cov().iloc[0, 1] / var), "estimated"


def attribute_move(positions: Sequence[tuple[str, float]], panel: pd.DataFrame,
                   requested_date: str | date, *,
                   benchmark: str = WHY_MOVED_BENCHMARK,
                   sector_map: dict[str, str] | None = None,
                   sector_etfs: dict[str, str] | None = None,
                   beta_lookback: int = WHY_MOVED_BETA_LOOKBACK_DAYS,
                   min_beta_obs: int = WHY_MOVED_MIN_BETA_OBS) -> Attribution:
    """Split one day's P&L into market, sector and residual. No model involved.

    Contributions sum to the total by CONSTRUCTION (they are the same dollars
    grouped differently), and the residual is defined as the remainder — so the
    decomposition never fails to add up, and the honest content is in the size
    of the residual, not in its existence.

    Raises PricingError when any held name lacks a close on either side of the
    move. A book that cannot be priced has no P&L, and the alternative — a
    silent zero for the missing name — reports a loss the book did not take.
    """
    sector_map = WHY_MOVED_TICKER_SECTOR if sector_map is None else sector_map
    sector_etfs = WHY_MOVED_SECTOR_ETFS if sector_etfs is None else sector_etfs
    as_of, prev = resolve_session(panel, requested_date, benchmark=benchmark)
    t_now, t_prev = pd.Timestamp(as_of), pd.Timestamp(prev)

    def _pair(tkr: str) -> tuple[float, float] | None:
        s = _closes(panel, tkr)
        if t_now not in s.index or t_prev not in s.index:
            return None
        return float(s.loc[t_prev]), float(s.loc[t_now])

    missing = [t for t, _ in positions if _pair(t) is None]
    if missing:
        raise PricingError(
            f"no usable closes on {prev} -> {as_of} for {sorted(missing)}; "
            f"the book cannot be marked and no attribution is produced (a zero "
            f"contribution for a name we could not price is a lie about the "
            f"book's P&L, not a conservative default)")

    bench_s = _closes(panel, benchmark).loc[:t_now]
    bench_ret = float(bench_s.loc[t_now] / bench_s.loc[t_prev] - 1.0)
    bench_window = bench_s.iloc[-(beta_lookback + 1):]

    sector_ret: dict[str, float] = {}
    unmapped: list[str] = []
    for sec in {sector_map.get(t.upper(), "") for t, _ in positions}:
        etf = sector_etfs.get(sec)
        if not sec or not etf:
            continue
        p = _pair(etf)
        if p is None:
            logger.warning("why_moved: sector proxy %s for %s has no closes on "
                           "%s -> %s — that sector's leg is not computed",
                           etf, sec, prev, as_of)
            continue
        sector_ret[sec] = p[1] / p[0] - 1.0

    rows: list[PositionMove] = []
    beta_fallbacks: list[str] = []
    value_prev_total = 0.0
    for tkr, shares in positions:
        p0, p1 = _pair(tkr)                       # type: ignore[misc]
        value_prev_total += float(shares) * p0
    if value_prev_total <= 0:
        raise PricingError(
            f"the book's value on {prev} is {value_prev_total} — a book with no "
            f"positive value has no weights and no attribution")

    for tkr, shares in positions:
        t = tkr.upper()
        p0, p1 = _pair(tkr)                       # type: ignore[misc]
        v0, v1 = float(shares) * p0, float(shares) * p1
        ret = p1 / p0 - 1.0
        w = v0 / value_prev_total
        b, src = _beta(_closes(panel, tkr).loc[:t_now].iloc[-(beta_lookback + 1):],
                       bench_window, min_obs=min_beta_obs)
        if src != "estimated":
            beta_fallbacks.append(t)
        sec = sector_map.get(t)
        if sec is None:
            unmapped.append(t)
        rows.append(PositionMove(
            ticker=t, shares=float(shares), price_prev=p0, price_now=p1,
            value_prev=v0, value_now=v1, pnl_usd=v1 - v0,
            return_pct=ret * 100.0, weight_prev=w,
            contribution_pct=w * ret * 100.0, contribution_bps=w * ret * 10000.0,
            beta=b, beta_source=src, sector=sec,
            sector_return_pct=(sector_ret[sec] * 100.0
                               if sec in sector_ret else None)))

    pnl = sum(r.pnl_usd for r in rows)
    value_now_total = sum(r.value_now for r in rows)
    book_ret = pnl / value_prev_total
    book_beta = sum(r.weight_prev * r.beta for r in rows)
    market = book_beta * bench_ret
    # The sector leg is deliberately NET of the market: a sector ETF's return
    # is mostly the market's, and counting it whole would attribute the same
    # dollars twice and leave a residual that is an accounting artifact.
    sector_leg = sum(r.weight_prev * ((r.sector_return_pct / 100.0) - bench_ret)
                     for r in rows if r.sector_return_pct is not None)
    resid = book_ret - market - sector_leg

    notes = [
        "market/sector/idiosyncratic is a DECOMPOSITION, not a causal claim: "
        "the residual is what these two factors leave over, and on a "
        "concentrated small-cap book that is normally most of the move.",
    ]
    if unmapped:
        notes.append(f"no sector declared for {sorted(set(unmapped))} — those "
                     f"positions contribute nothing to the sector leg and their "
                     f"move lands wholly in the residual")
    if beta_fallbacks:
        notes.append(f"beta defaulted to 1.0 for {sorted(set(beta_fallbacks))} "
                     f"(< {min_beta_obs} overlapping bars)")

    return Attribution(
        as_of=as_of, prev_close_date=prev, requested_date=str(requested_date)[:10],
        book_value_prev=value_prev_total, book_value_now=value_now_total,
        pnl_usd=pnl, pnl_pct=book_ret * 100.0, benchmark=benchmark,
        benchmark_return_pct=bench_ret * 100.0, book_beta=book_beta,
        market_component_pct=market * 100.0,
        market_component_usd=market * value_prev_total,
        sector_component_pct=sector_leg * 100.0,
        sector_component_usd=sector_leg * value_prev_total,
        idiosyncratic_pct=resid * 100.0,
        idiosyncratic_usd=resid * value_prev_total,
        positions=sorted(rows, key=lambda r: r.pnl_usd),
        sector_returns_pct={k: v * 100.0 for k, v in sorted(sector_ret.items())},
        sector_unmapped=sorted(set(unmapped)), beta_fallbacks=sorted(set(beta_fallbacks)),
        notes=notes)


# ── prices ──────────────────────────────────────────────────────────────────

#: (tickers, start_iso, end_iso) -> wide frame of adjusted closes, one column
#: per ticker. Injectable so the offline suite can hand over a fixture and so a
#: caller can supply a frozen panel; the default reaches the network.
PriceFetch = Callable[[list[str], str, str], pd.DataFrame]


@cached(ttl=WHY_MOVED_PRICE_CACHE_TTL)
def _cached_download(tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(list(tickers), start=start, end=end, auto_adjust=True,
                     progress=False, timeout=30)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(name=tickers[0])
    return df


def default_price_fetch(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Live adjusted closes, same convention as the ledger resolver."""
    return _cached_download(tuple(sorted(tickers)), start, end)


def universe_for(positions: Sequence[tuple[str, float]], *,
                 benchmark: str = WHY_MOVED_BENCHMARK) -> list[str]:
    """Everything one run needs priced: the book, its sector proxies, the
    benchmark, and every instrument a specialist is allowed to point at."""
    book = [t.upper() for t, _ in positions]
    etfs = {WHY_MOVED_SECTOR_ETFS[s] for t in book
            if (s := WHY_MOVED_TICKER_SECTOR.get(t)) in WHY_MOVED_SECTOR_ETFS}
    return sorted(set(WHY_MOVED_CORROBORATION_UNIVERSE) | set(book) | etfs
                  | {benchmark})


def last_priceable_session(positions: Sequence[tuple[str, float]],
                           panel: pd.DataFrame, requested: str | date, *,
                           benchmark: str = WHY_MOVED_BENCHMARK,
                           max_walkback: int = 5) -> tuple[str, list[str]]:
    """The most recent session at or before `requested` where the WHOLE book prints.

    Vendors publish the index before they publish a $2 biotech: on 2026-08-12
    SPY had an 08-11 close and eleven of Murat's twelve names did not. Grading
    the book on a day where most of it is missing would report a P&L the book
    did not take, so the walk-back happens HERE, out loud, and every skipped
    day is returned with the reason. The attribution itself still refuses to
    guess — this only chooses which day to hand it.
    """
    idx = _sessions(panel, benchmark)
    want = pd.Timestamp(str(requested)[:10])
    candidates = [d for d in idx[idx <= want][::-1]][:max_walkback + 1]
    skipped: list[str] = []
    for d in candidates:
        try:
            attribute_move(positions, panel, str(d.date()), benchmark=benchmark)
            return str(d.date()), skipped
        except PricingError as e:
            skipped.append(f"{d.date()}: {e}")
    raise PricingError(
        f"no session in the last {max_walkback + 1} at or before {want.date()} "
        f"prices the whole book:\n  " + "\n  ".join(skipped))


def panel_for(tickers: Iterable[str], as_of: str | date, *,
              price_fetch: PriceFetch | None = None,
              pad_days: int = WHY_MOVED_PRICE_PAD_DAYS) -> pd.DataFrame:
    """One panel covering the beta window and the graded day."""
    end = date.fromisoformat(str(as_of)[:10]) + timedelta(days=1)
    start = end - timedelta(days=pad_days)
    fetch = price_fetch or default_price_fetch
    df = fetch(sorted({t for t in tickers if t}), str(start), str(end))
    return df.sort_index()


# ── the language layer ──────────────────────────────────────────────────────

@dataclass
class LLMReply:
    """What a specialist call returns. `model_version` is recorded on every
    minted PredictionRecord, so a model swap is visible in the calibration
    slices rather than silently mixed into them."""
    text: str
    model_version: str


#: (system, user) -> LLMReply. Injectable; the default reaches DeepSeek.
LLMCall = Callable[[str, str], LLMReply]

#: One lens per way of being wrong about a single day. The skeptic is not
#: decoration: six specialists asked "what happened" will all find something,
#: and the only member of a panel who can lower the batch's confidence is the
#: one whose job is to argue the others are pattern-matching.
LENSES: dict[str, str] = {
    "company_news": (
        "You are an equity analyst who reads primary company disclosures. You "
        "reason about filings, press releases, clinical and regulatory updates, "
        "guidance, financings and dilution, index and share-count events. You "
        "care about WHEN something became public, because a move that preceded "
        "the disclosure was not caused by it."),
    "macro_rates": (
        "You are a rates and macro strategist. You reason about the yield "
        "curve, real rates, inflation prints, central-bank communication, "
        "liquidity and the duration sensitivity of long-dated equity cash "
        "flows. You know that unprofitable growth is a long-duration asset."),
    "geopolitical": (
        "You are a geopolitical risk analyst. You reason about conflict "
        "escalation and de-escalation, sanctions, shipping and chokepoints, "
        "elections and policy shocks, and how each transmits into oil, gold, "
        "defence, the dollar and risk appetite. You are aware that "
        "'geopolitics' is the most over-used explanation for a red day, and "
        "that a real geopolitical shock leaves a specific cross-asset "
        "signature that is either present or absent."),
    "sector_factor": (
        "You are a quantitative factor analyst. You reason about style and "
        "sector rotation, beta, size, value, momentum and crowding, and you "
        "start from the question of whether a name moved with its factor "
        "exposure rather than for any reason of its own."),
    "options_vol": (
        "You are a volatility and market-microstructure analyst. You reason "
        "about implied volatility, skew, dealer gamma, expiries, short "
        "interest, squeezes, liquidity and flows, and you distinguish a move "
        "caused by information from a move caused by positioning."),
    "revisions": (
        "You are an analyst-estimate specialist. You reason about earnings and "
        "revenue revisions, price-target and rating changes, coverage "
        "initiations and drops, and the dispersion of estimates. You know that "
        "a target change is a statement about a forecaster, not about a firm."),
    "skeptic": (
        "You are a professional skeptic. Your job is to argue that the other "
        "specialists have pattern-matched a story onto noise. You default to "
        "the base rate: most single-day moves in small, high-beta, "
        "low-liquidity securities are dominated by idiosyncratic flow and "
        "carry no recoverable cause. Where you do state a mechanism, you state "
        "the cross-asset evidence that would have to be ABSENT for the other "
        "explanations to be wrong."),
}

#: The contract every lens is bound by. Kept separate from the lens text so its
#: hash moves when the RULES change, not when a lens is reworded.
CONTRACT = """
You explain a day that has ALREADY HAPPENED, and every claim you make is
checked mechanically. You are not being asked for the cause; nobody can supply
one from a single day of data. You are being asked for hypotheses that can be
CAUGHT BEING WRONG.

Hard rules:
- You never state a position size, a weight, an action, or a recommendation,
  and you never use the words buy, sell, hold, trim, overweight, underweight.
- Every hypothesis MUST carry at least one cross_asset_corroboration assertion
  about a DIFFERENT instrument on the SAME day, or a next_observable forward
  claim. A hypothesis with neither is discarded unread: it cannot be wrong, so
  it cannot teach anyone anything.
- cross_asset_corroboration assertions are about the SAME day being explained,
  and they will be checked against that day's actual closes immediately. State
  the signature your mechanism REQUIRES, not the one that flatters it.
- confidence is your genuine credence that the mechanism was materially
  present. 0.3 is a good and useful answer. A batch of 0.9s is a batch of one.
- counter_evidence and falsification_condition are mandatory and must be
  specific.
- evidence[].first_public_timestamp is when the information became public. If
  you do not know, write "unknown" — do not invent one. A move that preceded
  the disclosure was not caused by it.

Return ONLY valid JSON, no prose outside it, matching exactly:
{"hypotheses": [{
  "hypothesis_id": short slug,
  "claim": one sentence,
  "causal_chain": [str, ...],
  "affected_assets": [{"ticker": str, "expected_sign": "up"|"down"}],
  "confidence": float 0..1,
  "counter_evidence": str,
  "falsification_condition": str,
  "evidence": [{"what": str, "source": str, "first_public_timestamp": str}],
  "cross_asset_corroboration": [
     {"kind":"direction","asset":"CL=F","expect":"up"}
   | {"kind":"relative","asset":"QQQ","versus":"SPY","expect":"underperforms"}
   | {"kind":"magnitude","asset":"^VIX","expect":"up","min_abs_move_pct":3.0}
  ],
  "next_observable": {"ticker": str, "observable":
     "return_sign"|"beats_benchmark"|"abs_move_exceeds"|"drawdown_exceeds",
     "horizon_days": int, "probability": float 0..1,
     "threshold": decimal fraction or null, "claim": str}
}]}

Units, and this has burned us before: min_abs_move_pct is PERCENT (3.0 means
3%). next_observable.threshold is a DECIMAL FRACTION (0.25 means 25%) and is
required for abs_move_exceeds and drawdown_exceeds, null otherwise.
"""


@dataclass
class Corroboration:
    """One mechanically checkable assertion about another instrument, same day.

    `evidence_class` is the difference between a check and a tautology. The
    prompt hands the specialist the book's own returns, the benchmark's and
    each held sector's, so "XLE up" from a lens that was just told "Energy
    +4.66%" is not a claim about the world — it is the input read back, and it
    hits every time. The first live run scored 100% on book tickers and 89% on
    sector ETFs against 84% on instruments the prompt never mentioned; the
    gap was pure measurement artifact. Only `external` assertions are counted
    in the headline rate.
    """
    kind: str
    asset: str
    expect: str
    versus: str | None = None
    min_abs_move_pct: float | None = None
    status: str = "ungraded"          # hit | miss | unavailable | ungraded
    evidence_class: str = "external"  # external | derivable_from_prompt
    observed: dict = field(default_factory=dict)


@dataclass
class ForwardClaim:
    """The part of a hypothesis that has not happened yet."""
    ticker: str
    observable: str
    horizon_days: int
    probability: float
    threshold: float | None
    claim: str = ""
    prediction_id: str | None = None
    refusal: str | None = None


@dataclass
class Hypothesis:
    lens: str
    hypothesis_id: str
    claim: str
    causal_chain: list[str]
    affected_assets: list[dict]
    confidence: float
    counter_evidence: str
    falsification_condition: str
    evidence: list[dict]
    corroboration: list[Corroboration]
    forward: ForwardClaim | None
    score: dict = field(default_factory=dict)


@dataclass
class LensResult:
    """One specialist's output, including everything thrown away and why."""
    lens: str
    status: str                       # ok | degraded
    degraded_reason: str | None
    model: str
    model_version: str
    hypotheses: list[Hypothesis]
    rejections: list[dict]
    raw_text: str = ""


def build_prompt(lens: str, attribution: Attribution, *,
                 context: dict | None = None) -> tuple[str, str]:
    """System and user prompt. The attribution is what the model may see."""
    if lens not in LENSES:
        raise KeyError(f"unknown lens {lens}")
    system = LENSES[lens] + "\n" + CONTRACT
    facts = lens_input(attribution, context=context)
    user = (
        "Here is the ALREADY-COMPUTED arithmetic of one day's move in a "
        "concentrated book. The arithmetic is not in dispute; explaining it is "
        "your job, and your explanation will be checked against other "
        "instruments' actual closes on the same day.\n\n"
        f"{json.dumps(facts, indent=1, sort_keys=True)}\n\n"
        "Instruments available for cross_asset_corroboration and for "
        "next_observable (nothing outside this list can be checked, and an "
        "assertion about an instrument we cannot price is scored "
        "'unavailable', never a hit):\n"
        f"{', '.join(sorted(set(WHY_MOVED_CORROBORATION_UNIVERSE) | {p.ticker for p in attribution.positions}))}\n\n"
        f"next_observable.horizon_days must be one of {list(HORIZONS)}; the "
        "short horizons exist so a claim about a reaction resolves in days.\n"
        "Vary them, and vary the observable. The first live batch was 23 of 25 "
        "one-day return_sign claims at probability 0.5, which accrues records "
        "fast and says nothing: a coin flip you called a coin flip is not a "
        "forecast. If your mechanism implies something over a week or a "
        "quarter, state THAT horizon; if it implies a magnitude, use "
        "abs_move_exceeds.\n\n"
        f"Return at most {WHY_MOVED_MAX_HYPOTHESES_PER_SPECIALIST} hypotheses, "
        f"each with at most {WHY_MOVED_MAX_CORROBORATION_PER_HYPOTHESIS} "
        "corroboration assertions. Fewer, sharper, more falsifiable is better "
        "than more.")
    return system, user


def lens_input(attribution: Attribution, *, context: dict | None = None) -> dict:
    """Exactly what every lens is shown. One function, because the grading
    depends on it: an assertion is only a CHECK if its answer was not already
    in this payload (see `derivable_assets`)."""
    facts = {
        "date_explained": attribution.as_of,
        "previous_close": attribution.prev_close_date,
        "book_pnl_usd": round(attribution.pnl_usd, 2),
        "book_return_pct": round(attribution.pnl_pct, 3),
        "benchmark": attribution.benchmark,
        "benchmark_return_pct": round(attribution.benchmark_return_pct, 3),
        "book_beta": round(attribution.book_beta, 3),
        "market_component_pct": round(attribution.market_component_pct, 3),
        "sector_component_pct": round(attribution.sector_component_pct, 3),
        "idiosyncratic_component_pct": round(attribution.idiosyncratic_pct, 3),
        "sector_returns_pct": {k: round(v, 3)
                               for k, v in attribution.sector_returns_pct.items()},
        "positions": [{"ticker": p.ticker, "return_pct": round(p.return_pct, 3),
                       "weight": round(p.weight_prev, 4),
                       "contribution_bps": round(p.contribution_bps, 1),
                       "pnl_usd": round(p.pnl_usd, 2), "sector": p.sector}
                      for p in attribution.positions],
    }
    if context:
        facts["context"] = context
    return facts


def derivable_assets(facts: dict) -> set[str]:
    """Instruments whose move on the graded day the prompt ALREADY gave away.

    Derived from the payload itself, never from a hand-kept list: if someone
    later adds a field to `lens_input` — say each position's sector ETF return,
    or a VIX level — the classification follows automatically instead of
    silently rotting into a wrong one. That rot is precisely how a measurement
    artifact survives a code review.
    """
    out: set[str] = set()
    for p in facts.get("positions", []):
        if "return_pct" in p:
            out.add(str(p.get("ticker", "")).upper())
    if "benchmark_return_pct" in facts and facts.get("benchmark"):
        out.add(str(facts["benchmark"]).upper())
    for sec in (facts.get("sector_returns_pct") or {}):
        etf = WHY_MOVED_SECTOR_ETFS.get(sec)
        if etf:
            out.add(etf.upper())
    return {t for t in out if t}


def default_llm_call(system: str, user: str, *, model: str = WHY_MOVED_MODEL,
                     api_key: str | None = None) -> LLMReply:
    """DeepSeek, OpenAI-compatible. Raises when there is no key.

    Failing loudly here is deliberate: the caller converts the failure into an
    explicit degraded status with zero hypotheses. A default that quietly
    returned nothing would be indistinguishable from a night the specialists
    had nothing to say.
    """
    import os

    from openai import OpenAI
    key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is empty — keys are env-only by house rule. The "
            "attribution stands on its own; hypotheses are simply absent.")
    cli = OpenAI(api_key=key,
                 base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                 timeout=WHY_MOVED_LLM_TIMEOUT_S)
    import time

    t0 = time.perf_counter()
    resp = cli.chat.completions.create(
        model=model, temperature=WHY_MOVED_TEMPERATURE,
        max_tokens=WHY_MOVED_MAX_TOKENS,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}])
    text = resp.choices[0].message.content or ""
    model_version = str(getattr(resp, "model", model))

    # Telemetry. This path was the ONE uninstrumented LLM call site the
    # telemetry ledger's own audit named, which made every WHY-MOVED lens call
    # invisible to the accounting built to answer "is the inference buying
    # anything". `usage` is read defensively because it is the vendor's object,
    # not ours, and a missing field must degrade to a zero-token row rather
    # than take a forecast down. record_call never raises, by contract — but
    # the extraction around it has to hold that promise too.
    try:
        from backend.services import llm_telemetry
        usage = getattr(resp, "usage", None)
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = int(getattr(details, "cached_tokens", 0) or 0)
        llm_telemetry.record_call(
            provider="deepseek", model=model, model_version=model_version,
            purpose="why_moved_hypothesis",
            prompt=system + user, context=None,
            tokens_in=int(getattr(usage, "prompt_tokens", 0) or 0),
            tokens_out=int(getattr(usage, "completion_tokens", 0) or 0),
            cached_tokens=cached,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            # Whether the reply PARSES is decided downstream by the lens
            # coordinator, which counts rejections. Claiming schema validity
            # here would rubber-stamp any HTTP 200 — the exact failure the
            # telemetry ledger exists to expose — so the truthful value is
            # "unknown until parsed", and the coordinator links the outcome.
            schema_valid=bool(text.strip()),
            meta={"max_tokens": WHY_MOVED_MAX_TOKENS})
    except Exception as exc:                                  # noqa: BLE001
        logger.warning("why_moved: telemetry not recorded for a lens call "
                       "(%s: %s) — this spend is MISSING from the ledger, but "
                       "the hypothesis itself is unaffected",
                       type(exc).__name__, exc)

    return LLMReply(text=text, model_version=model_version)


def _extract_json(text: str) -> dict:
    """Parse the model's JSON, including when it fences it."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        out = json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            raise
        out = json.loads(m.group(0))
    # THE ANNOTATION IS NOW ENFORCED. `json.loads` returns a str for a JSON
    # string literal, a list for an array, an int for a number — all of which
    # parsed "successfully" and were handed to `parse_hypotheses`, which does
    # `raw.get(...)`. Double-encoded JSON (a string whose content is the
    # object) is a known DeepSeek json_object failure mode, so this was a live
    # route to `'str' object has no attribute 'get'` escaping the lens, the
    # orchestrator and the nightly job. Raising here puts it where the caller
    # already handles a model that produced no object: a counted rejection.
    if not isinstance(out, dict):
        raise ValueError(
            f"model returned a JSON {type(out).__name__}, not an object")
    return out


def _parse_corroboration(raw: Any, allowed: set[str]) -> tuple[Corroboration | None, str | None]:
    """One assertion, or the reason it is not one.

    Every rejection here removes a way the hypothesis could have been caught
    being wrong, which is why each is returned with its reason instead of being
    dropped.
    """
    if not isinstance(raw, dict):
        return None, f"corroboration is not an object: {raw!r}"
    kind = str(raw.get("kind", "")).strip().lower()
    asset = str(raw.get("asset", "")).strip().upper()
    expect = str(raw.get("expect", "")).strip().lower()
    if asset not in allowed:
        return None, (f"{asset or '?'}: outside the checkable instrument "
                      f"universe — an assertion we cannot price is not a check")
    if kind == "direction":
        if expect not in ("up", "down"):
            return None, f"{asset}: direction expects up|down, got {expect!r}"
        return Corroboration(kind=kind, asset=asset, expect=expect), None
    if kind == "relative":
        versus = str(raw.get("versus", "")).strip().upper()
        if versus not in allowed:
            return None, (f"{asset}: relative needs a checkable `versus`, got "
                          f"{versus!r}")
        if expect not in ("outperforms", "underperforms"):
            return None, (f"{asset}: relative expects outperforms|underperforms,"
                          f" got {expect!r}")
        return Corroboration(kind=kind, asset=asset, expect=expect,
                             versus=versus), None
    if kind == "magnitude":
        if expect not in ("up", "down", "either"):
            return None, f"{asset}: magnitude expects up|down|either, got {expect!r}"
        try:
            m = float(raw.get("min_abs_move_pct"))
        except (TypeError, ValueError):
            return None, (f"{asset}: magnitude needs a numeric "
                          f"min_abs_move_pct in PERCENT")
        if not WHY_MOVED_MAGNITUDE_MIN_PCT_FLOOR <= m <= WHY_MOVED_MAGNITUDE_MAX_PCT:
            # Below the floor everything is a hit; above the ceiling the number
            # is a units error, and coercing it would be guessing at what the
            # forecaster meant.
            return None, (f"{asset}: min_abs_move_pct {m} is outside "
                          f"[{WHY_MOVED_MAGNITUDE_MIN_PCT_FLOOR}, "
                          f"{WHY_MOVED_MAGNITUDE_MAX_PCT}] percent")
        return Corroboration(kind=kind, asset=asset, expect=expect,
                             min_abs_move_pct=m), None
    return None, f"unknown corroboration kind {kind!r}"


def _parse_forward(raw: Any, allowed: set[str]) -> tuple[ForwardClaim | None, str | None]:
    """The forward claim, or why it is not one. Nothing is minted here."""
    if not isinstance(raw, dict):
        return None, None if raw is None else f"next_observable is not an object: {raw!r}"
    tkr = str(raw.get("ticker", "")).strip().upper()
    if tkr not in allowed:
        return None, (f"{tkr or '?'}: forward claim about an instrument outside "
                      f"the checkable universe — the resolver could not grade it")
    try:
        obs = Observable(str(raw.get("observable", "")).strip().lower())
    except ValueError:
        return None, (f"{tkr}: {raw.get('observable')!r} is not one of "
                      f"{[o.value for o in Observable]}")
    try:
        h = int(raw.get("horizon_days"))
        p = float(raw.get("probability"))
    except (TypeError, ValueError):
        return None, f"{tkr}: horizon_days/probability are not numbers"
    if h not in HORIZONS:
        return None, f"{tkr}: horizon {h} is not one of the frozen {list(HORIZONS)}"
    thr = raw.get("threshold")
    thr = float(thr) if thr is not None else None
    return ForwardClaim(ticker=tkr, observable=obs.value, horizon_days=h,
                        probability=p, threshold=thr,
                        claim=str(raw.get("claim", "")).strip()), None


def parse_hypotheses(lens: str, raw: dict, *, allowed_assets: set[str],
                     max_hypotheses: int = WHY_MOVED_MAX_HYPOTHESES_PER_SPECIALIST,
                     max_corroboration: int = WHY_MOVED_MAX_CORROBORATION_PER_HYPOTHESIS
                     ) -> tuple[list[Hypothesis], list[dict]]:
    """Hypotheses that could be caught being wrong, and a counted pile of the rest.

    The rejection list is not an error log. It is the measurement of how much
    of a specialist's output was ungradeable, and it is reported beside the
    hypotheses that survived.
    """
    kept: list[Hypothesis] = []
    rejected: list[dict] = []
    # `_extract_json` is `json.loads`, so a reply that is a JSON string literal,
    # array or number PARSES CLEANLY into a non-dict and sails past the
    # JSONDecodeError guard at the call site. Double-encoded JSON (a string
    # whose content is the object) is a known DeepSeek json_object failure
    # mode. Counted as a rejection like any other ungradeable output — the one
    # thing it must not do is raise, because `run_lens` calls this OUTSIDE its
    # parse guard and the exception escapes all the way to the scheduler.
    if not isinstance(raw, dict):
        return [], [{"lens": lens, "hypothesis_id": None,
                     "reason": (f"response parsed to {type(raw).__name__}, "
                                f"not an object")}]
    items = raw.get("hypotheses")
    if not isinstance(items, list):
        return [], [{"lens": lens, "hypothesis_id": None,
                     "reason": "response carried no `hypotheses` list"}]
    for i, h in enumerate(items[:max_hypotheses]):
        hid = str(h.get("hypothesis_id") or f"{lens}_{i}")[:64] if isinstance(h, dict) else f"{lens}_{i}"
        if not isinstance(h, dict):
            rejected.append({"lens": lens, "hypothesis_id": hid,
                             "reason": "hypothesis is not an object"})
            continue
        claim = str(h.get("claim", "")).strip()
        if not claim:
            rejected.append({"lens": lens, "hypothesis_id": hid,
                             "reason": "no claim"})
            continue
        blob = " ".join([claim, str(h.get("counter_evidence", "")),
                         str(h.get("falsification_condition", "")),
                         " ".join(str(x) for x in (h.get("causal_chain") or []))])
        hits = _FORBIDDEN.findall(blob)
        if hits:
            # The offending words and an excerpt are kept: the first live run
            # recorded three of these with no trace of WHAT was refused, which
            # makes a rejection count unauditable — you cannot tell a lens with
            # a tic from a regex that is too greedy.
            rejected.append({"lens": lens, "hypothesis_id": hid,
                             "reason": "contains recommendation language — this "
                                       "surface explains, it does not advise",
                             "matched_terms": sorted({h.lower() for h in hits}),
                             "refused_text_excerpt": claim[:200]})
            continue
        checks: list[Corroboration] = []
        sub: list[str] = []
        for c in (h.get("cross_asset_corroboration") or [])[:max_corroboration]:
            parsed, why = _parse_corroboration(c, allowed_assets)
            if parsed is not None:
                checks.append(parsed)
            elif why:
                sub.append(why)
        fwd, fwd_why = _parse_forward(h.get("next_observable"), allowed_assets)
        if fwd_why:
            sub.append(fwd_why)
        if not checks and fwd is None:
            rejected.append({
                "lens": lens, "hypothesis_id": hid, "claim": claim,
                "reason": "no checkable corroboration and no forward claim — "
                          "ungradeable, and an explanation that cannot be wrong "
                          "is commentary",
                "sub_reasons": sub})
            continue
        try:
            conf = float(h.get("confidence"))
        except (TypeError, ValueError):
            conf = float("nan")
        if not 0.0 <= conf <= 1.0:
            rejected.append({"lens": lens, "hypothesis_id": hid, "claim": claim,
                             "reason": f"confidence {h.get('confidence')!r} is "
                                       f"not a credence in [0,1]"})
            continue
        kept.append(Hypothesis(
            lens=lens, hypothesis_id=hid, claim=claim,
            causal_chain=[str(x) for x in (h.get("causal_chain") or [])],
            affected_assets=[{"ticker": str(a.get("ticker", "")).upper(),
                              "expected_sign": str(a.get("expected_sign", "")).lower()}
                             for a in (h.get("affected_assets") or [])
                             if isinstance(a, dict)],
            confidence=conf,
            counter_evidence=str(h.get("counter_evidence", "")).strip(),
            falsification_condition=str(h.get("falsification_condition", "")).strip(),
            evidence=[e for e in (h.get("evidence") or []) if isinstance(e, dict)],
            corroboration=checks, forward=fwd,
            score={"parse_sub_reasons": sub}))
    if len(items) > max_hypotheses:
        rejected.append({"lens": lens, "hypothesis_id": None,
                         "reason": f"{len(items) - max_hypotheses} hypothesis(es) "
                                   f"past the cap of {max_hypotheses} not read"})
    return kept, rejected


# ── grading the day that already happened ───────────────────────────────────

def _day_return(panel: pd.DataFrame, asset: str, prev: str, now: str) -> float | None:
    s = _closes(panel, asset)
    t0, t1 = pd.Timestamp(prev), pd.Timestamp(now)
    if t0 not in s.index or t1 not in s.index:
        return None
    p0 = float(s.loc[t0])
    if p0 == 0:
        return None
    return float(s.loc[t1]) / p0 - 1.0


def _rate(hits: int, miss: int) -> float | None:
    return hits / (hits + miss) if (hits + miss) else None


def grade_corroboration(hypotheses: Sequence[Hypothesis], panel: pd.DataFrame,
                        *, as_of: str, prev: str,
                        derivable: set[str] | None = None) -> None:
    """Score every assertion against the day it was about. Mutates in place.

    The whole reason the corroboration is stated about a PAST day is that it
    can be graded now — the loop that teaches a forecaster anything is the one
    that closes in hours, not the one that closes in quarters.

    `unavailable` is its own bucket and NEVER counts as a hit. An instrument we
    could not price says nothing about the hypothesis, and folding it into
    either side would let a specialist improve its record by naming obscure
    assets.

    `derivable` is the set of instruments whose move the prompt already stated
    (`derivable_assets`). Those assertions are still graded — a lens that
    contradicts its own input has told you something — but they are scored in a
    separate bucket, because getting them right measures instruction-following,
    not information.

    WHAT A HIT MEANS, PRECISELY: the mechanism the hypothesis required was
    COHERENT with the rest of the market that day. Nothing more. An incoherent
    explanation is refuted, which is genuinely useful, but coherence is not
    predictive skill and never becomes it however many days accumulate. The
    forward PredictionRecords are the skill instrument; these are the coherence
    instrument, and conflating the two would manufacture a track record out of
    arithmetic about the past.
    """
    shown = {t.upper() for t in (derivable or set())}
    for h in hypotheses:
        for c in h.corroboration:
            c.evidence_class = (
                "derivable_from_prompt"
                if c.asset in shown and (c.versus is None or c.versus in shown)
                else "external")
            r = _day_return(panel, c.asset, prev, as_of)
            if r is None:
                c.status = "unavailable"
                c.observed = {"reason": f"no closes for {c.asset} on {prev} -> {as_of}"}
                continue
            if c.kind == "direction":
                c.observed = {"return_pct": r * 100.0}
                c.status = "hit" if ((r > 0) == (c.expect == "up")) else "miss"
            elif c.kind == "relative":
                rv = _day_return(panel, c.versus or "", prev, as_of)
                if rv is None:
                    c.status = "unavailable"
                    c.observed = {"reason": f"no closes for {c.versus}"}
                    continue
                c.observed = {"return_pct": r * 100.0, "versus_return_pct": rv * 100.0,
                              "spread_pct": (r - rv) * 100.0}
                # Ties go to miss: "underperforms" is a claim about a
                # difference, and a difference of exactly zero did not happen.
                c.status = "hit" if ((r > rv) == (c.expect == "outperforms")
                                     and r != rv) else "miss"
            elif c.kind == "magnitude":
                big = abs(r) * 100.0 >= float(c.min_abs_move_pct or 0.0)
                signed = (c.expect == "either") or ((r > 0) == (c.expect == "up"))
                c.observed = {"return_pct": r * 100.0,
                              "abs_move_pct": abs(r) * 100.0,
                              "min_abs_move_pct": c.min_abs_move_pct}
                c.status = "hit" if (big and signed) else "miss"
            else:                                   # pragma: no cover
                c.status = "unavailable"
                c.observed = {"reason": f"unknown kind {c.kind}"}
        h.score.update(score_corroboration(h.corroboration))


def score_corroboration(checks: Sequence[Corroboration]) -> dict:
    """Roll graded assertions up, with the external rate as the headline.

    Every rate here is None rather than 0.0 when its denominator is empty: a
    rate over nothing is no score, and a zero would read as a failed check.
    """
    def n(status: str, cls: str | None = None) -> int:
        return sum(1 for c in checks if c.status == status
                   and (cls is None or c.evidence_class == cls))

    hits, miss, una = n("hit"), n("miss"), n("unavailable")
    eh, em = n("hit", "external"), n("miss", "external")
    dh, dm = n("hit", "derivable_from_prompt"), n("miss", "derivable_from_prompt")
    return {
        # the headline: instruments the prompt never mentioned
        "corroboration_hit_rate_external": _rate(eh, em),
        "corroboration_hits_external": eh,
        "corroboration_misses_external": em,
        # instruction-following, NOT information — the prompt gave these away
        "corroboration_hit_rate_derivable": _rate(dh, dm),
        "corroboration_hits_derivable": dh,
        "corroboration_misses_derivable": dm,
        "corroboration_hits": hits, "corroboration_misses": miss,
        "corroboration_unavailable": una,
        "corroboration_checkable": hits + miss,
        "corroboration_hit_rate_combined": _rate(hits, miss),
    }


def mint_predictions(hypotheses: Sequence[Hypothesis], *, attribution: Attribution,
                     prompts: dict[str, str], model: str, model_version: str,
                     made_at: str | None = None) -> tuple[list[PredictionRecord], list[dict]]:
    """Turn surviving forward claims into ledger records the resolver will grade.

    `make_prediction` is called, never reimplemented, so its refusals apply
    here unchanged — including the one that matters most: a threshold at or
    above 1.0 is a percent/fraction mixup, and a previous run wrote six
    guaranteed-wrong records because that mixup was swallowed. It is surfaced
    here as a COUNTED refusal with the message intact, so the specialist that
    produced it is identifiable.
    """
    records: list[PredictionRecord] = []
    refusals: list[dict] = []
    for h in hypotheses:
        f = h.forward
        if f is None:
            continue
        try:
            rec = make_prediction(
                ticker=f.ticker, specialist=f"why_moved:{h.lens}",
                observable=Observable(f.observable), horizon_days=f.horizon_days,
                probability=f.probability, threshold=f.threshold,
                benchmark=(attribution.benchmark
                           if f.observable == Observable.BEATS_BENCHMARK.value
                           else None),
                thesis=(f.claim or h.claim),
                counter_thesis=(h.counter_evidence or h.falsification_condition),
                next_observable=h.falsification_condition,
                model=model, model_version=model_version,
                prompt=prompts.get(h.lens, ""),
                input_snapshot={"as_of": attribution.as_of,
                                "book_return_pct": attribution.pnl_pct,
                                "benchmark_return_pct": attribution.benchmark_return_pct,
                                "hypothesis": h.claim},
                made_at=made_at,
                # The session this record is ABOUT — the snapshot above is
                # stored only as a hash, so without this stamp the ledger
                # cannot answer "was this session already minted?"
                session_as_of=attribution.as_of)
        except Exception as exc:                     # noqa: BLE001
            f.refusal = f"{type(exc).__name__}: {exc}"
            refusals.append({"lens": h.lens, "hypothesis_id": h.hypothesis_id,
                             "reason": f"forward claim refused by the ledger — "
                                       f"{f.refusal}"})
            logger.warning("why_moved: %s/%s forward claim refused: %s",
                           h.lens, h.hypothesis_id, f.refusal)
            continue
        f.prediction_id = rec.prediction_id
        records.append(rec)
    return records, refusals


# ── CANON §20: the batch checked against itself ─────────────────────────────

def _tokens(text: str) -> set[str]:
    stop = set(WHY_MOVED_STOPWORDS)
    return {w for w in _WORD.findall(text.lower()) if w not in stop and len(w) > 2}


def effective_distinct_ideas(hypotheses: Sequence[Hypothesis], *,
                             jaccard: float = WHY_MOVED_IDEA_JACCARD) -> dict:
    """How many DIFFERENT explanations this batch actually contains.

    NIGHT-10 found ten "independent" LLM hypotheses that were one connected
    component. Seven lenses each producing "risk-off on rates" is one idea with
    seven authors, and treating it as seven manufactures agreement that no
    independent evidence supports. Two hypotheses are joined when they assert
    the same cross-asset signature or when their claims share most of their
    content words; the count reported is the number of CONNECTED COMPONENTS,
    which is the honest denominator for anything said about this batch.
    """
    n = len(hypotheses)
    if not n:
        return {"n_hypotheses": 0, "effective_distinct_ideas": 0, "ratio": None,
                "components": []}
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    sigs = [frozenset((c.kind, c.asset, c.versus or "", c.expect)
                      for c in h.corroboration) for h in hypotheses]
    toks = [_tokens(h.claim) for h in hypotheses]
    for i in range(n):
        for j in range(i + 1, n):
            same_sig = bool(sigs[i]) and sigs[i] == sigs[j]
            u = toks[i] | toks[j]
            overlap = (len(toks[i] & toks[j]) / len(u)) if u else 0.0
            if same_sig or overlap >= jaccard:
                union(i, j)
    comps: dict[int, list[str]] = {}
    for i, h in enumerate(hypotheses):
        comps.setdefault(find(i), []).append(f"{h.lens}:{h.hypothesis_id}")
    return {
        "n_hypotheses": n,
        "effective_distinct_ideas": len(comps),
        "ratio": round(len(comps) / n, 3),
        "distinct_lenses": len({h.lens for h in hypotheses}),
        "components": sorted(comps.values(), key=len, reverse=True),
        "reading": ("the denominator for any claim about this batch is the "
                    "number of components, not the number of rows (CANON §20)"),
    }


# ── orchestration ───────────────────────────────────────────────────────────

def run_lens(lens: str, attribution: Attribution, *, allowed_assets: set[str],
             llm_call: LLMCall | None = None, model: str = WHY_MOVED_MODEL,
             context: dict | None = None) -> tuple[LensResult, str]:
    """One specialist, end to end, degrading explicitly. Returns (result, prompt).

    Independence is the product: the lenses never see each other's output, so
    seven agreeing hypotheses are seven pieces of evidence about the same prior
    rather than a consensus.
    """
    system, user = build_prompt(lens, attribution, context=context)
    call = llm_call or default_llm_call
    try:
        reply = call(system, user)
    except Exception as exc:                          # noqa: BLE001
        logger.warning("why_moved: lens %s produced no answer (%s: %s) — "
                       "recorded as degraded with zero hypotheses",
                       lens, type(exc).__name__, exc)
        return LensResult(lens=lens, status="degraded",
                          degraded_reason=f"{type(exc).__name__}: {exc}",
                          model=model, model_version="", hypotheses=[],
                          rejections=[]), system + user
    try:
        raw = _extract_json(reply.text)
    except Exception as exc:                          # noqa: BLE001
        # Unparseable output is a REJECTION, not a crash and not an empty
        # night: the call was made and spent, and the batch's rejection count
        # is the honest place for it.
        logger.warning("why_moved: lens %s returned unparseable JSON (%s) — "
                       "counted as a rejection", lens, exc)
        return LensResult(
            lens=lens, status="degraded",
            degraded_reason=f"unparseable JSON: {type(exc).__name__}: {exc}",
            model=model, model_version=reply.model_version, hypotheses=[],
            rejections=[{"lens": lens, "hypothesis_id": None,
                         "reason": f"unparseable JSON from the model: {exc}"}],
            raw_text=reply.text[:4000]), system + user
    kept, rejected = parse_hypotheses(lens, raw, allowed_assets=allowed_assets)
    return LensResult(lens=lens, status="ok", degraded_reason=None, model=model,
                      model_version=reply.model_version, hypotheses=kept,
                      rejections=rejected, raw_text=reply.text[:4000]), system + user


def ledger_has_minted(as_of: str, ledger_path: Path | None = None) -> bool:
    """True if the belief ledger already carries why_moved records for `as_of`.

    The catch-up-slot idempotency key (the arena's `already_marked`, for this
    job): a retry firing on a day whose first pass already minted must not ask
    the lenses again — the second answer would be a second set of gradeable
    records for the same session, and the calibration table would count one
    night twice. The check DERIVES from the ledger itself, never from a
    marker file that could drift from what was actually written.

    Matches on `session_as_of` (schema 1.3.0) — the session a record is
    ABOUT. Records written before the stamp existed carry None and never
    match; the worst that buys is one legitimate re-ask of a pre-stamp day,
    never a suppressed first ask.
    """
    from backend.services.belief_state import read_predictions
    return any(
        str(r.get("specialist", "")).startswith("why_moved:")
        and r.get("session_as_of") == as_of
        for r in read_predictions(ledger_path))


def run_why_moved(positions: Sequence[tuple[str, float]], requested_date: str | date,
                  *, price_fetch: PriceFetch | None = None,
                  panel: pd.DataFrame | None = None,
                  llm_call: LLMCall | None = None,
                  lenses: Sequence[str] | None = None,
                  with_hypotheses: bool = True,
                  model: str = WHY_MOVED_MODEL,
                  context: dict | None = None,
                  ledger_path: Path | None = None,
                  write_ledger: bool = False,
                  skip_if_minted: bool = False,
                  benchmark: str = WHY_MOVED_BENCHMARK) -> dict:
    """The whole thing: attribution always, hypotheses when they can be graded.

    Returns a plain dict (JSON-safe) so the router, the script and the artifact
    are literally the same object. `status` is one of:

      "ok"                     — attribution and at least one lens answered
      "degraded_no_hypotheses" — attribution stands, every lens went dark
      "attribution_only"       — hypotheses not requested
      "already_written"        — `skip_if_minted` and the ledger already holds
                                 this session's records (catch-up slots only)

    There is no status in which an explanation is invented, and none in which
    the attribution is skipped because the language layer failed.
    """
    lenses = list(lenses if lenses is not None else LENSES.keys())
    universe = universe_for(positions, benchmark=benchmark)
    if panel is None:
        panel = panel_for(universe, requested_date, price_fetch=price_fetch)

    attribution = attribute_move(positions, panel, requested_date,
                                 benchmark=benchmark)
    # The whitelist is what the panel can actually price, not what config
    # wishes it could: an assertion about a column we never fetched would be
    # graded "unavailable" forever, which reads as a data problem rather than
    # the prompt problem it is.
    allowed = {t for t in universe if not _closes(panel, t).empty}

    out: dict[str, Any] = {
        "module_version": MODULE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": attribution.as_of,
        "prev_close_date": attribution.prev_close_date,
        "requested_date": attribution.requested_date,
        "attribution": asdict(attribution),
        "epistemics": {
            "what_this_grades": [
                "COHERENCE: whether the cross-asset signature a hypothesis "
                "REQUIRED was actually present that day (hit / miss / "
                "unavailable), counted only over instruments the prompt did "
                "not already disclose",
                "SKILL: whether its forward claim resolves, on the ledger's "
                "schedule, scored by Brier against climatology",
            ],
            "what_this_never_claims": [
                "that any hypothesis caused the move. One day of data cannot "
                "identify a cause, competing explanations are preserved rather "
                "than collapsed, and a corroboration hit is evidence a "
                "mechanism was PRESENT, not that it was operative.",
                "that a corroboration hit rate is forecasting skill. It is a "
                "coherence check on the past; the two instruments are reported "
                "separately and are never to be added together.",
            ],
            "descriptive_only": ("this surface explains; it never recommends an "
                                 "action, and hypothesis text that reaches for "
                                 "one is refused"),
        },
    }

    if skip_if_minted and write_ledger and ledger_has_minted(attribution.as_of,
                                                             ledger_path):
        # Cheap by construction: attribution (prices only) has run, no lens
        # has spoken, no LLM call has been spent, nothing will be appended.
        out["status"] = "already_written"
        out["status_detail"] = (
            f"the ledger already holds why_moved records for "
            f"{attribution.as_of} — catch-up slot skipped before any lens "
            f"spent a call")
        out["lenses"] = []
        out["hypotheses"] = []
        out["predictions"] = []
        out["n_predictions_minted"] = 0
        return out

    if not with_hypotheses:
        out["status"] = "attribution_only"
        out["status_detail"] = "hypotheses not requested"
        out["lenses"] = []
        out["hypotheses"] = []
        out["predictions"] = []
        return out

    results: list[LensResult] = []
    prompts: dict[str, str] = {}
    for lens in lenses:
        res, prompt = run_lens(lens, attribution, allowed_assets=allowed,
                               llm_call=llm_call, model=model, context=context)
        prompts[lens] = prompt
        results.append(res)

    kept = [h for r in results for h in r.hypotheses]
    # Computed FROM the payload the lenses were actually shown, so the
    # classification cannot drift away from the prompt it describes.
    derivable = derivable_assets(lens_input(attribution, context=context))
    grade_corroboration(kept, panel, as_of=attribution.as_of,
                        prev=attribution.prev_close_date, derivable=derivable)
    version = next((r.model_version for r in results if r.model_version), model)
    records, mint_refusals = mint_predictions(
        kept, attribution=attribution, prompts=prompts, model=model,
        model_version=version)

    by_lens = {}
    for r in results:
        hs = r.hypotheses
        extra = [x for x in mint_refusals if x["lens"] == r.lens]
        by_lens[r.lens] = {
            "status": r.status, "degraded_reason": r.degraded_reason,
            "n_hypotheses": len(hs),
            "n_rejected": len(r.rejections) + len(extra),
            "rejections": r.rejections + extra,
            **score_corroboration([c for h in hs for c in h.corroboration]),
            "n_predictions_minted": sum(
                1 for h in hs if h.forward and h.forward.prediction_id),
        }

    batch_checks = [c for h in kept for c in h.corroboration]
    rolled = score_corroboration(batch_checks)
    n_ok = sum(1 for r in results if r.status == "ok")

    out.update({
        "status": "ok" if n_ok else "degraded_no_hypotheses",
        "status_detail": ("at least one lens answered" if n_ok else
                          "every lens went dark — the attribution above is "
                          "unaffected, and no explanation was invented to fill "
                          "the gap"),
        "lenses": by_lens,
        "hypotheses": [asdict(h) for h in kept],
        "batch": {
            **effective_distinct_ideas(kept),
            "n_rejected": sum(v["n_rejected"] for v in by_lens.values()),
            "corroboration": {
                **rolled,
                "derivable_assets": sorted(derivable),
                "headline": "corroboration_hit_rate_external",
                "note": ("unavailable is never a hit, and a rate over zero "
                         "checkable assertions is None rather than zero. "
                         "corroboration_hit_rate_external is the only rate to "
                         "quote: an assertion about an instrument whose return "
                         "the prompt already printed measures "
                         "instruction-following, not information. Neither rate "
                         "is forecasting skill — this is a COHERENCE check on "
                         "a day that already happened. Skill lives in the "
                         "forward PredictionRecords and nowhere else."),
            },
        },
        "predictions": [asdict(r) for r in records],
        "n_predictions_minted": len(records),
    })

    if write_ledger and records:
        from backend.services.belief_state import append
        append(records, ledger_path)
        out["ledger_written"] = str(ledger_path) if ledger_path else "default"
    elif write_ledger:
        out["ledger_written"] = None
        logger.warning("why_moved: asked to write the ledger but no record "
                       "survived — nothing was appended")
    return out


def hypothesis_from_dict(d: dict) -> Hypothesis:
    """Rebuild a stored hypothesis. Used only by `regrade`."""
    f = d.get("forward")
    return Hypothesis(
        lens=d["lens"], hypothesis_id=d["hypothesis_id"], claim=d["claim"],
        causal_chain=list(d.get("causal_chain") or []),
        affected_assets=list(d.get("affected_assets") or []),
        confidence=float(d.get("confidence", 0.0)),
        counter_evidence=d.get("counter_evidence", ""),
        falsification_condition=d.get("falsification_condition", ""),
        evidence=list(d.get("evidence") or []),
        corroboration=[Corroboration(**{k: v for k, v in c.items()
                                        if k in Corroboration.__dataclass_fields__})
                       for c in (d.get("corroboration") or [])],
        forward=(ForwardClaim(**{k: v for k, v in f.items()
                                 if k in ForwardClaim.__dataclass_fields__})
                 if f else None),
        score=dict(d.get("score") or {}))


def regrade(artifact: dict, panel: pd.DataFrame) -> dict:
    """Re-score a stored run's assertions under the CURRENT grading rules.

    No model is called and no record is minted: the hypotheses are exactly the
    ones that were written on the night, and only the scoring of them changes.
    This exists because the first live run was scored before the
    derivable/external split existed, and rerunning the model to fix a SCORING
    bug would have written a second batch of forecasts about the same day —
    inflating the ledger's n with correlated records to repair arithmetic.
    Every regrade stamps its provenance so a reader can see the artifact was
    re-scored and by which rule.
    """
    a = artifact["attribution"]
    hyps = [hypothesis_from_dict(h) for h in artifact.get("hypotheses", [])]
    derivable = derivable_assets(artifact.get("lens_input") or _facts_from_stored(a))
    grade_corroboration(hyps, panel, as_of=a["as_of"],
                        prev=a["prev_close_date"], derivable=derivable)
    out = dict(artifact)
    for lens, v in (out.get("lenses") or {}).items():
        checks = [c for h in hyps if h.lens == lens for c in h.corroboration]
        v.update(score_corroboration(checks))
        # Drop the pre-split keys. Leaving a stale `corroboration_hit_rate`
        # (the inflated 89% of the 2026-08-10 run) beside the corrected one
        # under a more inviting name is how the wrong number gets quoted.
        for legacy in ("corroboration_hit_rate", "corroboration_hits_undisclosed",
                       "corroboration_misses_undisclosed",
                       "corroboration_hit_rate_undisclosed"):
            v.pop(legacy, None)
    all_checks = [c for h in hyps for c in h.corroboration]
    out["hypotheses"] = [asdict(h) for h in hyps]
    out.setdefault("batch", {})["corroboration"] = {
        **score_corroboration(all_checks),
        "derivable_assets": sorted(derivable),
        "headline": "corroboration_hit_rate_external",
        "note": ("re-scored: only assertions about instruments the prompt did "
                 "NOT disclose count toward the headline rate"),
    }
    out.setdefault("regrades", []).append({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "module_version": MODULE_VERSION,
        "what_changed": ("corroboration assertions classified external vs "
                         "derivable_from_prompt; the headline rate now counts "
                         "external assertions only"),
        "no_model_calls": True, "no_records_minted": True,
    })
    return out


def _facts_from_stored(a: dict) -> dict:
    """The prompt payload's disclosure surface, reconstructed from a stored
    attribution. Only the fields `derivable_assets` reads are rebuilt."""
    return {"benchmark": a.get("benchmark"),
            "benchmark_return_pct": a.get("benchmark_return_pct"),
            "sector_returns_pct": a.get("sector_returns_pct") or {},
            "positions": [{"ticker": p["ticker"], "return_pct": p["return_pct"]}
                          for p in a.get("positions", [])]}


def book_positions(path: Path | str | None = None) -> list[tuple[str, float]]:
    """(ticker, shares) from the book file, refusing positions without shares.

    A position with no share count cannot be marked to market, and carrying it
    at zero would silently shrink the book — the same class of defect as the
    silent exclusion that moved a measured result by ten points on NIGHT-12.
    """
    from backend.services.pm_engine import load_book
    book = load_book(path)
    out, dark = [], []
    for p in book.positions:
        if p.shares is None or float(p.shares) <= 0:
            dark.append(p.ticker)
            continue
        out.append((str(p.ticker).upper(), float(p.shares)))
    if dark:
        raise PricingError(
            f"positions with no usable share count: {dark} — the book cannot be "
            f"marked and a partial book would report a P&L that is not the "
            f"book's")
    return out
