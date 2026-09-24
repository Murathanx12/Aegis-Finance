"""Give an LLM everything we know about 3,000 stocks and let it build a book.

    python -m scripts.llm_portfolio brief          # write the briefing
    python -m scripts.llm_portfolio freeze <file>  # commit a returned portfolio
    python -m scripts.llm_portfolio grade          # NAV every frozen book

WHAT THIS IS FOR (Murat, 2026-09-24)
====================================
> feed an LLM preferably Fable 5.1 ... it skims everything and makes portfolios,
> few of them very aggressive focused at maximizing ROI ... others still make
> portfolios based on beating sp500 ... full freedom, 1m for each paper account,
> no cap on how many stocks and how much to allocate ... timeline day-week-
> month-6months to see how the LLM performs and how the timing works.

The programme has spent five months asking "can I prove this factor works" and
the demonstrated edge is 0%. This asks a different question and it is a fair
one: **given everything we know, can a large model allocate better than the
machinery we built?** It is cheap to ask, it is graded by reality rather than by
a backtest, and a negative answer is as useful as a positive one because it
tells us the bottleneck is the INFORMATION, not the allocator.

THE THREE RULES THAT MAKE IT EVIDENCE INSTEAD OF A DEMO
=======================================================
1. **The briefing is point-in-time.** Every field is computable from data that
   existed at `asof`. If the model can see the future, the exercise measures
   nothing, and it will find the leak faster than we will.
2. **The portfolio is FROZEN before any outcome exists**, content-hashed, with
   the briefing's own hash recorded inside it. A book that gets edited after the
   first week is not a forecast. This is the same discipline the three licences
   impose on a `PRODUCT_EXPERIMENT` contract.
3. **It is graded against SPY and against our own machinery**, at every horizon
   it declared. "Beat the market" is the only claim that matters, and a book
   that returns +8% while SPY returns +11% has lost.

WHAT IS HONESTLY IN THE BRIEFING, AND WHAT IS NOT
=================================================
Murat's description assumed "analyst reviews, price targets and fair price
data". **Those are largely NOT available**: the price-target endpoint is 403 on
the free Finnhub tier (observed again on 2026-09-24 when the funnel rebuilt --
`stock/price-target` returned 403 for every one of 40 tickers), and no
fair-value vendor is provisioned. Saying otherwise inside a prompt would invite
the model to hallucinate the field, which is the failure mode this module is
most exposed to.

What IS real, and it is a lot:

* 24 price/volume features per name (`xs_ranker.FEATURES`) -- momentum at four
  horizons, realised vol, liquidity, Amihud illiquidity, distance from the
  52-week high and the 200-day, residual momentum, beta, drawdown, skew.
* Quarterly revenue growth, gross margin and margin CHANGE per name, from SEC
  filings dated by `filed` (`inflection`), including the fourth quarter that
  XBRL never tags and that nothing in this repo could see before 2026-09-24.
* The liquidity band and its empirical round-trip cost, so the model can be
  told what its own turnover will cost rather than discovering it later.
* Whether the name is currently flagged by the inflection detector, with the
  standing caveat that §63 found that detector has no dose-response.

THE COST MODEL IS NOT OPTIONAL AND IS NOT THE MODEL'S CHOICE
============================================================
`grade()` charges `xs_ranker.round_trip_bps` by liquidity band on entry. A book
of 200 microcaps that looks brilliant gross is a different object once it pays
35 bps a side, and letting the allocator ignore that would reproduce the exact
error that made the fleet lose $46,401 realised.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from backend import config as _config

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "llm_portfolio/1"

#: Every book starts here. Declared, not negotiable -- a model that sizes in
#: dollars needs to know the denominator, and comparing books at different
#: capital is comparing two things.
START_CAPITAL = 1_000_000.0

#: The horizons Murat named. Graded at each; a book does not have to "end" at
#: any of them, they are read-outs of the same running NAV.
HORIZON_DAYS = (1, 5, 21, 126)

#: A weight this small is a rounding error wearing a thesis. Not refused --
#: the brief promises "no cap on how many stocks" -- but reported, because a
#: 300-name book at 0.3% each is an index fund with extra steps and the receipt
#: should say so rather than leaving it to be discovered.
TINY_WEIGHT = 0.002


def ledger_dir() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "llm_portfolio"


def briefing_path(day: str | None = None) -> Path:
    return ledger_dir() / f"briefing_{day or date.today()}.json"


def books_path() -> Path:
    return ledger_dir() / "books.jsonl"


def _hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ────────────────────────────── the briefing ────────────────────────────────

def build_briefing(*, asof: Optional[Any] = None, max_names: int = 4000,
                   bars: Optional[pd.DataFrame] = None) -> dict:
    """Everything knowable at `asof`, one compact row per name.

    Rounded hard on purpose. A model reading 3,000 rows does not benefit from
    the ninth decimal of a z-score, and the token budget is better spent on
    coverage than on precision nobody can act on.
    """
    from backend.services import xs_ranker as XR

    asof_ts = pd.Timestamp(asof) if asof is not None else None
    if bars is None:
        bars = XR.load_bars(XR.survivorship_free_paths())
    if asof_ts is not None:
        bars = bars[bars["date"] <= asof_ts]
    panel = XR.build_panel(bars)
    # The LAST row per symbol is the only one an allocator can act on.
    live = (panel[panel["eligible"]].sort_values("date")
            .drop_duplicates("symbol", keep="last"))
    asof_real = str(live["date"].max())[:10]

    # Fundamentals, joined on `filed` so nothing arrives before it was public.
    fund: dict[str, dict] = {}
    try:
        from backend.services import inflection as INF
        q = INF.add_features(INF.quarterly_panel())
        if asof_ts is not None:
            q = q[q["filed"] <= asof_ts]
        q = q[q["sequential_ok"]].sort_values("filed").drop_duplicates(
            "ticker", keep="last")
        fires = set(INF.detect(q, min_acceleration=-9.99)["ticker"])
        for r in q.itertuples():
            fund[r.ticker] = {
                "rev_qoq": _r(r.rev_qoq), "rev_yoy": _r(r.rev_yoy),
                "gross_margin": _r(r.gm), "gross_margin_chg": _r(r.gm_chg),
                "last_filed": str(r.filed)[:10],
                "inflection_flag": r.ticker in fires,
            }
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("briefing: fundamentals unavailable (%s)", exc)

    rows = []
    for r in live.head(max_names).itertuples():
        row = {
            "t": r.symbol,
            "px": _r(r.close, 2),
            "band": XR.liquidity_band(r.median_dollar_vol),
            "cost_bps": round(XR.round_trip_bps(r.median_dollar_vol), 1),
            "dollar_vol_m": _r(r.median_dollar_vol / 1e6, 1),
            "mom_21": _r(r.mom_21), "mom_63": _r(r.mom_63),
            "mom_252_21": _r(r.mom_252_21),
            "vol_63": _r(r.vol_63), "beta_63": _r(r.beta_63),
            "vs_52w_high": _r(r.px_vs_52w_high), "vs_ma200": _r(r.px_vs_ma200),
            "drawdown_63": _r(r.max_drawdown_63), "skew_63": _r(r.skew_63),
            "amihud": _r(r.amihud, 6),
        }
        row.update(fund.get(r.symbol, {}))
        rows.append(row)

    brief = {
        "schema": SCHEMA_VERSION, "kind": "briefing",
        "asof": asof_real,
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "start_capital_usd": START_CAPITAL,
        "n_names": len(rows),
        "field_notes": {
            "mom_21/63/252_21": "trailing total return over that many sessions; 252_21 skips the last month",
            "vol_63": "annualised realised volatility over 63 sessions",
            "vs_52w_high": "fraction below the 52-week high (0 = at the high)",
            "cost_bps": "EMPIRICAL round-trip cost for this name's liquidity band. You pay it.",
            "rev_qoq / gross_margin_chg": "latest SEC quarter, dated by FILING date; Q4 is derived (annual minus Q1-Q3)",
            "inflection_flag": "revenue growing >15% sequentially WITH gross margin up >2pp",
        },
        "what_is_NOT_here": [
            "analyst price targets and consensus estimates -- the vendor endpoint "
            "is 403 on this tier, verified again 2026-09-24. Do not infer them.",
            "fair-value / DCF estimates -- no vendor is provisioned.",
            "news, filings text, transcripts, insider transactions, options data.",
            "sector and industry labels for the full universe.",
        ],
        "standing_findings_you_should_know": [
            "NEGATIVE_RESULTS §59: price/volume alone does not rank this cross-section at 21 sessions; the apparent edge lives in illiquidity and is smaller than the cost of trading it.",
            "§60: a six-ratio fundamental model came LAST of six and was negative at every book size.",
            "§61: extending the holding period to 126 sessions looked positive and was entirely 2025; drop that year and it is +0.12%.",
            "§62: eleven exit rules -- stops, trailing stops, take-profits -- ALL lost to simply holding. A -2% stop is 0.93 daily sigma for the median name and fires on 89% of positions.",
            "§63: the inflection detector above has NO dose-response; a bigger signal does not produce a bigger return. Treat inflection_flag as a description, not a prediction.",
        ],
        "rows": rows,
    }
    brief["briefing_hash"] = _hash(brief["rows"])
    return brief


def _r(v, nd: int = 4):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(f) else round(f, nd)


# ───────────────────────────── freezing a book ──────────────────────────────

@dataclass
class Refusal(Exception):
    why: str

    def __str__(self) -> str:                                      # pragma: no cover
        return self.why


def freeze(book: dict, *, briefing: Optional[dict] = None,
           today: Optional[Any] = None) -> dict:
    """Validate and commit a portfolio. After this it is evidence, not a draft.

    Refuses rather than repairs. A book that does not say what it holds, or
    whose weights do not add up, is not a forecast that can be graded, and
    silently normalising it would make the grade meaningless.
    """
    name = str(book.get("name") or "").strip()
    if not name:
        raise Refusal("REFUSED: the book has no `name`. Books are compared to "
                      "each other and an unnamed one cannot be.")
    objective = str(book.get("objective") or "").strip()
    if not objective:
        raise Refusal("REFUSED: no `objective`. 'Maximise ROI' and 'beat SPY' "
                      "are different books and are graded differently.")
    pos = book.get("positions") or []
    if not pos:
        raise Refusal("REFUSED: no positions. An empty book is a decision to "
                      "hold cash and must say so explicitly as CASH 1.0.")

    clean, seen = [], set()
    total = 0.0
    for p in pos:
        t = str(p.get("ticker") or "").strip().upper()
        if not t:
            raise Refusal(f"REFUSED: a position has no ticker: {p!r}")
        if t in seen:
            raise Refusal(f"REFUSED: {t} appears twice. Merge it or the weights "
                          f"do not mean what they say.")
        seen.add(t)
        try:
            w = float(p.get("weight"))
        except (TypeError, ValueError):
            raise Refusal(f"REFUSED: {t} has a non-numeric weight {p.get('weight')!r}")
        if not np.isfinite(w) or w < 0:
            raise Refusal(f"REFUSED: {t} weight {w} -- long-only for now; a short "
                          f"needs a borrow model this does not have.")
        total += w
        clean.append({"ticker": t, "weight": w,
                      "thesis": str(p.get("thesis") or "")[:600]})
    if not (0.98 <= total <= 1.02):
        raise Refusal(f"REFUSED: weights sum to {total:.4f}, not 1.0. This is "
                      f"not a rounding fix I am willing to make for you -- a "
                      f"book that is 40% cash by accident and 40% by intent are "
                      f"different books.")
    # Normalise the residual only inside the tolerance already accepted.
    for c in clean:
        c["weight"] = c["weight"] / total

    rec = {
        "schema": SCHEMA_VERSION, "kind": "book",
        "name": name, "objective": objective,
        "model": str(book.get("model") or "unknown"),
        "strategy": str(book.get("strategy") or "")[:2000],
        "horizon_days": book.get("horizon_days") or list(HORIZON_DAYS),
        "frozen_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asof": str(today or date.today()),
        "start_capital_usd": START_CAPITAL,
        "n_positions": len(clean),
        "n_tiny_positions": sum(1 for c in clean if c["weight"] < TINY_WEIGHT),
        "max_weight": max(c["weight"] for c in clean),
        "briefing_hash": (briefing or {}).get("briefing_hash"),
        "briefing_asof": (briefing or {}).get("asof"),
        "positions": clean,
    }
    rec["book_id"] = _hash({k: rec[k] for k in ("name", "positions", "asof")})
    return rec


def append_book(rec: dict) -> Path:
    p = books_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")
    return p


def read_books(path: Optional[Path] = None) -> list[dict]:
    p = Path(path) if path else books_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


# ──────────────────────────────── grading ───────────────────────────────────

def grade(rec: dict, bars: pd.DataFrame, *, today: Optional[Any] = None) -> dict:
    """NAV the book forward from its own as-of date, net of entry cost.

    Entry is the OPEN of the session after `asof`, which is the first price the
    book could actually have been filled at. A book priced at the close of its
    own decision date has already been given the day it was deciding on.
    """
    from backend.services import xs_ranker as XR

    start = pd.Timestamp(rec["asof"])
    dates = np.sort(bars["date"].unique()).astype("datetime64[ns]")
    i0 = int(np.searchsorted(dates, np.datetime64(start, "ns"), side="right"))
    if i0 >= len(dates):
        return {"book_id": rec["book_id"], "name": rec["name"],
                "status": "PENDING", "why": "no session has opened since it was frozen"}

    px = {s: g.sort_values("date") for s, g in bars.groupby("symbol", sort=False)}
    held, missing, cost_bps = [], [], 0.0
    for p in rec["positions"]:
        t = p["ticker"]
        if t == "CASH":
            held.append((t, p["weight"], None, None))
            continue
        g = px.get(t)
        if g is None:
            missing.append(t)
            continue
        d = g["date"].values.astype("datetime64[ns]")
        j = int(np.searchsorted(d, dates[i0], side="left"))
        if j >= len(d):
            missing.append(t)
            continue
        o = float(g["open"].iloc[j])
        if not np.isfinite(o) or o <= 0:
            missing.append(t)
            continue
        mdv = float(g["median_dollar_vol"].iloc[j]) if "median_dollar_vol" in g else None
        cost_bps += p["weight"] * XR.round_trip_bps(mdv)
        held.append((t, p["weight"], g, j))

    if not held:
        return {"book_id": rec["book_id"], "name": rec["name"],
                "status": "REFUSED", "why": f"no position could be priced; "
                                            f"missing {missing[:10]}"}

    # A book whose names we cannot price is NOT silently re-weighted onto the
    # ones we can. That would grade a different book than the one frozen.
    priced_w = sum(w for _t, w, _g, _j in held)
    out = {"book_id": rec["book_id"], "name": rec["name"],
           "objective": rec["objective"], "model": rec.get("model"),
           "asof": rec["asof"], "status": "OK",
           "n_positions": rec["n_positions"],
           "n_unpriceable": len(missing), "unpriceable": missing[:20],
           "weight_priced": round(priced_w, 4),
           # Charged ONCE, on entry, at the empirical band cost. Half of a round
           # trip, because the book has not sold yet.
           "entry_cost_bps": round(cost_bps / 2.0, 1),
           "horizons": {}}

    spy = px.get("SPY")
    for h in (rec.get("horizon_days") or HORIZON_DAYS):
        h = int(h)
        i1 = i0 + h - 1
        if i1 > len(dates) - 1:
            out["horizons"][h] = {"status": "PENDING",
                                  "why": f"needs {h} sessions, has {len(dates)-i0}"}
            continue
        asof_d = dates[i1]
        tot = 0.0
        for t, w, g, j in held:
            if g is None:                       # CASH earns nothing here
                tot += w
                continue
            d = g["date"].values.astype("datetime64[ns]")
            k = int(np.searchsorted(d, asof_d, side="right")) - 1
            if k < j:
                tot += w                        # no price yet: held flat, not dropped
                continue
            tot += w * float(g["close"].iloc[k]) / float(g["open"].iloc[j])
        gross = tot / priced_w - 1.0 if priced_w else None
        net = gross - (cost_bps / 2.0) / 10_000.0 if gross is not None else None
        bench = None
        if spy is not None:
            sd = spy["date"].values.astype("datetime64[ns]")
            a = int(np.searchsorted(sd, dates[i0], side="left"))
            b = int(np.searchsorted(sd, asof_d, side="right")) - 1
            if 0 <= a < len(sd) and a <= b:
                bench = float(spy["close"].iloc[b]) / float(spy["open"].iloc[a]) - 1.0
        out["horizons"][h] = {
            "status": "OK", "gross": gross, "net": net,
            "nav_usd": round(START_CAPITAL * (1.0 + (net or 0.0)), 2),
            "spy": bench,
            "vs_spy": (net - bench) if (net is not None and bench is not None) else None,
            "as_of": str(pd.Timestamp(asof_d))[:10],
        }
    return out
