"""LANE B — a paper book is a frozen contract, a cadence, an origin and a TWIN.

WHY THIS FILE EXISTS
====================
Murat asked for "thousands of paper accounts". The unit is not an account —
thousands of Alpaca accounts is impossible and thousands of daily NAV rows is
nothing to sqlite. The unit is a **frozen `Strategy` + a cadence + a control
twin + a forecast row** (roadmap §3 lane B), marked from local bars.

The twin is the whole point. `docs/AEGIS_STRATEGIC_INVARIANTS.md` and roadmap
B3: *a book's number is never shown without its twin's*. So the twin is created
WITH the book, before its number exists — `create()` refuses a book that has no
twin, and refuses it at creation rather than at display time, because a twin
constructed after a number is known is a twin chosen to flatter it.

WHAT THIS DOES NOT DO
=====================
No order path, no broker, no real capital, no LLM authority over size. A book
is a declaration and a NAV series. `paper_books.create()` is reachable from the
control plane (`POST /api/control/books/create-from-contract`), and the control
plane's AST test keeps it broker-free.

THE WRITE PATH IS SACRED (CANON §5)
===================================
The four reference lanes' `paper_nav` rows are the track record. A book writes
to a NEW table (`paper_books`, db.py v9) and to `paper_nav` under a NAMESPACED
`portfolio_id` — `book:<fingerprint>` — and never touches an existing lane's
rows. `paper_nav.portfolio_id` carries a foreign key to `paper_portfolios`, so
a book also gets ONE `paper_portfolios` row under the same namespaced id; every
lane enumerator in this repository reads an explicit lane list and is therefore
blind to it, and the one wholesale reader (`/api/control/fleet`) now excludes
the namespace by name.

WHY THE ID IS THE FINGERPRINT
=============================
Two books with the same contract ARE the same book, and giving them two ids
would let the same strategy accrue two independent forward records and be
reported as two pieces of evidence. `contract.Strategy.fingerprint` already
hashes the whole record including the cost flag, so `book:<fingerprint>` is
identity, not a name. A mutation is a new strategy (`Strategy.with_`) and
therefore a new book — which is the property lane B needs to accumulate.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from backend.strategy.contract import (Construction, Licence, Signal, Strategy,
                                       StrategyError, Universe,
                                       loss_budget_worst_case)

logger = logging.getLogger(__name__)

#: The cadences a book may declare.
#:
#: `monthly` was added 2026-09-12 (`docs/research_notes/2026-09-12/
#: spec_first_books.md` §0C): three of the first four `origin=night_job` books
#: are native to a monthly decision cycle — short-interest files are
#: semi-monthly, IBES revisions monthly, R2's digest monthly — and the spec's
#: interim advice was to declare `quarterly` and note the mismatch in
#: `origin_text`. A cadence that has to be explained in prose is a cadence the
#: scheduler cannot act on, so the enum carries it instead.
CADENCES: tuple[str, ...] = ("30m", "daily", "weekly", "monthly", "quarterly")

#: How many TRADING SESSIONS one cadence period is, for the forecast horizon.
#: Every value is a member of `belief_state.HORIZONS` — a horizon invented per
#: book would be a free parameter, which is the thing `HORIZONS` exists to stop.
CADENCE_SESSIONS: dict[str, int] = {
    "30m": 1,          # graded at the next close; minute bars do not exist locally
    "daily": 1,
    "weekly": 5,
    "monthly": 20,
    "quarterly": 60,
}

#: Where a book came from. `twin_of:<book_id>` is the fourth, and it is a
#: PREFIX rather than a member because a twin names its parent.
ORIGINS: tuple[str, ...] = ("human_text", "night_job", "mutation")
TWIN_PREFIX = "twin_of:"

#: The namespace. Nothing outside it is ever written by this module.
BOOK_PREFIX = "book:"

#: Constructions that are long-only by declaration. A beta-matched twin is only
#: meaningful for a book that is long the market; a long-short book's beta is
#: already a design choice rather than an accident of selection.
#:
#: `passthrough` joined them 2026-09-12. It was omitted, and the omission was
#: invisible until lane B's insider-cluster book — the only `passthrough` book
#: in the programme — came out with one twin where its own pre-registration
#: names two. `decide_weights` never produces a negative weight for any rule,
#: so a passthrough book is as long-only as a top-k one; the tuple was a list
#: of the rules that happened to exist when it was written.
LONG_ONLY_RULES = ("top_k", "composite_top_k", "threshold_coverage",
                   "passthrough")

#: The twin constructions, named once so a receipt and a `PredictionRecord`
#: quote the same words (`control_construction`, spec §4).
TWIN_RANDOM = ("same construction, same cadence, same k, same costs; universe "
               "drawn AT RANDOM from the same dollar-volume band, with the seed "
               "derived from the parent's fingerprint and recorded")
TWIN_BETA = ("same construction and cadence; a random draw matched on the "
             "pre-period beta decile of the parent's own universe (OLS of daily "
             "return on the equal-weight market over the 120 sessions ending "
             "strictly before creation, minimum 60 usable sessions)")
TWIN_OVERNIGHT = ("holds through the open and does nothing intraday — the "
                  "construction lane D needs to tell an intraday edge from the "
                  "overnight drift it would otherwise be reading")


class BookError(ValueError):
    """A book that cannot be created as declared."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def book_id_for(strategy: Strategy) -> str:
    return f"{BOOK_PREFIX}{strategy.fingerprint}"


def is_book_id(portfolio_id: str) -> bool:
    """True for the book namespace. Used by every lane reader that would
    otherwise render a book as a lane."""
    return str(portfolio_id).startswith(BOOK_PREFIX)


# --------------------------------------------------------------------------
# the object


@dataclass(frozen=True)
class PaperBook:
    """One book: a frozen contract, a cadence, where it came from, its twins."""

    book_id: str
    strategy: Strategy
    cadence: str
    created_utc: str
    origin: str
    origin_text: str = ""
    control_twin_ids: tuple[str, ...] = ()
    control_construction: str = ""
    ips_hash: str | None = None
    shadow: bool = False
    status: str = "holding"

    def __post_init__(self) -> None:
        if self.cadence not in CADENCES:
            raise BookError(f"cadence {self.cadence!r} is not one of "
                            f"{list(CADENCES)}. A cadence the scheduler cannot "
                            f"act on is a note, not a cadence.")
        if not (self.origin in ORIGINS or self.origin.startswith(TWIN_PREFIX)):
            raise BookError(
                f"origin {self.origin!r} must be one of {list(ORIGINS)} or "
                f"{TWIN_PREFIX}<book_id>. An unattributed book cannot be told "
                f"from one a human held.")
        if self.status not in ("holding", "flipped", "retired"):
            raise BookError(f"status {self.status!r} is not holding/flipped/retired")

    @property
    def is_twin(self) -> bool:
        return self.origin.startswith(TWIN_PREFIX)

    @property
    def parent_id(self) -> str | None:
        return self.origin[len(TWIN_PREFIX):] if self.is_twin else None

    @property
    def horizon_sessions(self) -> int:
        return CADENCE_SESSIONS[self.cadence]

    def as_row(self) -> dict:
        return {
            "book_id": self.book_id,
            "fingerprint": self.strategy.fingerprint,
            "strategy_id": self.strategy.strategy_id,
            "title": self.strategy.title,
            "cadence": self.cadence,
            "origin": self.origin,
            "origin_text": self.origin_text,
            "control_twin_ids": list(self.control_twin_ids),
            "control_construction": self.control_construction,
            "ips_hash": self.ips_hash,
            "shadow": bool(self.shadow),
            "created_utc": self.created_utc,
            "status": self.status,
            "licence": self.strategy.licence.value,
            "is_twin": self.is_twin,
            "parent_id": self.parent_id,
            **self.strategy.costs.as_row(),
        }


# --------------------------------------------------------------------------
# the universe a book actually holds
#
# `Universe` is a DECLARATION (a floor, a price minimum, a cap), not a list, so
# something has to resolve it to symbols. That resolution happens here, from the
# local bars, and it is recorded on the receipt: a universe resolved differently
# on two days is a different book being marked under one id.


def _bars_path() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "prices_2025_26" / "bars.parquet"


_BARS_MEMO: dict[str, Any] = {}


def load_bars(path: Path | None = None):
    """Daily bars as a DataFrame (symbol, date, open, high, low, close, volume).

    Memoised by path+mtime: the file is 32 MB and a cadence pass over several
    books would otherwise read it once per book.
    """
    import pandas as pd

    p = Path(path) if path is not None else _bars_path()
    if not p.is_file():
        raise BookError(
            f"no local bars at {p}. A book marked from a price panel that does "
            f"not exist would be marked from nothing; the pass reports this "
            f"rather than marking.")
    key = f"{p}:{p.stat().st_mtime_ns}"
    hit = _BARS_MEMO.get(key)
    if hit is None:
        hit = pd.read_parquet(p)
        hit["date"] = pd.to_datetime(hit["date"])
        _BARS_MEMO.clear()
        _BARS_MEMO[key] = hit
    return hit


def liquidity_panel(bars, asof: date, *, lookback: int = 21):
    """Median dollar volume and last close per symbol over the trailing window.

    The window ENDS ON `asof` and never contains a bar after it. Everything the
    twin's draw and the universe's floor are computed from comes from this one
    frame, so a book and its twin are selected from the same measured pool
    rather than from two nearly-identical ones.
    """
    import pandas as pd

    ts = pd.Timestamp(asof)
    window = bars[bars["date"] <= ts]
    if window.empty:
        return pd.DataFrame(columns=["symbol", "dollar_vol", "close", "n_bars"])
    dates = sorted(window["date"].unique())[-lookback:]
    window = window[window["date"].isin(dates)]
    window = window.assign(dollar_vol=window["close"] * window["volume"])
    grp = window.groupby("symbol")
    out = pd.DataFrame({
        "dollar_vol": grp["dollar_vol"].median(),
        "close": grp["close"].last(),
        "n_bars": grp["close"].count(),
    }).reset_index()
    return out


def resolve_universe(strategy: Strategy, bars, asof: date) -> list[str]:
    """The symbols a book's declared universe resolves to on `asof`.

    An explicit list in `engine_params["symbols"]` wins — a book seeded from a
    named basket should not be silently re-screened. Otherwise the declaration
    is applied: the dollar-volume floor, the price minimum, and `max_names` by
    descending liquidity.
    """
    explicit = (strategy.engine_params or {}).get("symbols")
    if explicit:
        return sorted({str(s).upper() for s in explicit})
    panel = liquidity_panel(bars, asof)
    if panel.empty:
        return []
    u = strategy.universe
    if u.floor_dollar_vol_usd is not None:
        panel = panel[panel["dollar_vol"] >= float(u.floor_dollar_vol_usd)]
    if u.min_price_usd is not None:
        panel = panel[panel["close"] >= float(u.min_price_usd)]
    panel = panel[panel["n_bars"] >= 5]
    panel = panel.sort_values("dollar_vol", ascending=False)
    if u.max_names is not None:
        panel = panel.head(int(u.max_names))
    return sorted(panel["symbol"].astype(str).tolist())


# --------------------------------------------------------------------------
# beta, for the beta-matched twin
#
# `learner/beta.py` declares this programme's beta estimator and implements it
# on CRSP permnos against the CRSP value-weighted index. A 2025-26 book on
# ticker bars has neither, so this is the SAME estimator on the data that
# exists, and it says so rather than pretending to be that module: OLS of daily
# return on the daily equal-weight market return over the 120 sessions ending on
# the last session strictly BEFORE the decision date, minimum 60 usable
# sessions, and a name with fewer gets no beta and is dropped from BOTH arms.


BETA_WINDOW = 120
BETA_MIN_SESSIONS = 60
BETA_ESTIMATOR = (
    "OLS of daily return on the daily EQUAL-WEIGHT market return of the same "
    "pool over the 120 sessions ending strictly before the decision date, "
    "minimum 60 usable sessions. This is learner/beta.py's declared estimator "
    "applied to ticker bars: that module estimates on CRSP permnos against the "
    "CRSP value-weighted index, neither of which exists for a 2025-26 book.")


def pre_period_beta(bars, symbols: Sequence[str], asof: date) -> dict[str, float]:
    """{symbol: beta} over the window ending strictly before `asof`."""
    import numpy as np
    import pandas as pd

    ts = pd.Timestamp(asof)
    sub = bars[(bars["date"] < ts) & (bars["symbol"].isin(list(symbols)))]
    if sub.empty:
        return {}
    wide = sub.pivot_table(index="date", columns="symbol", values="close",
                           aggfunc="last").sort_index()
    wide = wide.tail(BETA_WINDOW + 1)
    rets = wide.pct_change(fill_method=None).iloc[1:]
    if rets.empty:
        return {}
    mkt = rets.mean(axis=1)
    out: dict[str, float] = {}
    mvar = float(np.nanvar(mkt.to_numpy(dtype=float)))
    if not math.isfinite(mvar) or mvar <= 0:
        return {}
    for sym in rets.columns:
        col = rets[sym]
        ok = col.notna() & mkt.notna()
        if int(ok.sum()) < BETA_MIN_SESSIONS:
            continue
        y = col[ok].to_numpy(dtype=float)
        x = mkt[ok].to_numpy(dtype=float)
        cov = float(np.cov(y, x, ddof=1)[0, 1])
        var = float(np.var(x, ddof=1))
        if var > 0 and math.isfinite(cov):
            out[str(sym)] = cov / var
    return out


def _decile_edges(values: Sequence[float]):
    """The nine interior deciles of `values`, as an array."""
    import numpy as np
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return np.asarray([], dtype=float)
    return np.quantile(arr, [i / 10 for i in range(1, 10)])


def _decile_of(edges, v: float) -> int:
    """Which decile 0-9 `v` falls in, given `edges` from `_decile_edges`."""
    import numpy as np
    if getattr(edges, "size", 0) == 0:
        return 0
    return int(np.searchsorted(edges, float(v), side="right"))


# --------------------------------------------------------------------------
# B3 — the twins


def _twin_seed(strategy: Strategy, kind: str) -> int:
    """Deterministic, derived from the parent's fingerprint, and RECORDED.

    A fixed seed is what reproducibility asks for WITHIN a run and what destroys
    accumulation ACROSS runs (CLAUDE.md rule 9) — but a twin is not a search: it
    is a control that must be reconstructible from the book it controls, which
    is exactly the case where the derived seed is correct. It is written onto
    the twin's `engine_params` so a reader never has to re-derive it.
    """
    import hashlib
    h = hashlib.sha256(f"{strategy.fingerprint}:{kind}".encode()).hexdigest()
    return int(h[:8], 16)


def is_long_only(strategy: Strategy) -> bool:
    return strategy.construction.rule in LONG_ONLY_RULES


def make_twins(strategy: Strategy, *, cadence: str, bars=None,
               asof: date | None = None,
               created_utc: str | None = None) -> list[PaperBook]:
    """Every control this book is owed, built from the book itself (B3).

    (a) the random-universe twin, always;
    (b) the beta-matched twin when the book is long-only;
    (c) the overnight-only twin when the cadence is `30m` (lane D).

    Each twin is itself a `PaperBook` with `origin="twin_of:<parent id>"`, so it
    is marked, decided and graded by exactly the same machinery — a control that
    runs on a different code path is a second engine, and a comparison between
    two engines is not a comparison between two strategies.
    """
    if cadence not in CADENCES:
        raise BookError(f"cadence {cadence!r} is not one of {list(CADENCES)}")
    asof = asof or date.today()
    created_utc = created_utc or _now()
    parent_id = book_id_for(strategy)

    pool: list[str] = []
    parent_symbols: list[str] = []
    if bars is not None:
        try:
            parent_symbols = resolve_universe(strategy, bars, asof)
            pool = _band_pool(strategy, bars, asof, parent_symbols)
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("twin universe could not be resolved (%s) — the twin "
                           "carries the parent's declaration instead of a draw", exc)

    twins: list[PaperBook] = []
    twins.append(_random_universe_twin(strategy, cadence, parent_id, pool,
                                       parent_symbols, created_utc))
    if is_long_only(strategy):
        twins.append(_beta_matched_twin(strategy, cadence, parent_id, pool,
                                        parent_symbols, bars, asof, created_utc))
    if cadence == "30m":
        twins.append(_overnight_only_twin(strategy, cadence, parent_id,
                                          parent_symbols, created_utc))
    return twins


def _band_pool(strategy: Strategy, bars, asof: date,
               parent_symbols: Sequence[str]) -> list[str]:
    """Every name in the SAME dollar-volume band as the parent's universe.

    The band is a DECILE band of the eligible pool, not the parent's own
    [min, max] range. The difference matters: a book declared as "the 40 most
    liquid names above the floor" occupies exactly the top of its own range, so
    a band defined as that range contains only the parent's own names and the
    random twin degenerates into the book itself. The decile band keeps the
    control comparable -- same liquidity regime, same execution costs -- without
    making it a copy.

    The draw is NOT forbidden to touch the parent's names: a random draw with
    the parent's holdings excluded is not a random draw, it is a draw from the
    complement. The overlap is measured and recorded on the twin instead.
    """
    panel = liquidity_panel(bars, asof)
    if panel.empty:
        return []
    u = strategy.universe
    if u.floor_dollar_vol_usd is not None:
        panel = panel[panel["dollar_vol"] >= float(u.floor_dollar_vol_usd)]
    if u.min_price_usd is not None:
        panel = panel[panel["close"] >= float(u.min_price_usd)]
    panel = panel[panel["n_bars"] >= 5]
    if panel.empty:
        return []
    if parent_symbols:
        edges = _decile_edges(panel["dollar_vol"].astype(float).tolist())
        own = panel[panel["symbol"].isin(list(parent_symbols))]
        if not own.empty:
            keep = {_decile_of(edges, float(v)) for v in own["dollar_vol"]}
            panel = panel[[_decile_of(edges, float(v)) in keep
                           for v in panel["dollar_vol"]]]
    return sorted(panel["symbol"].astype(str).tolist())


def _draw(pool: Sequence[str], n: int, seed: int) -> list[str]:
    import numpy as np
    if not pool:
        return []
    rng = np.random.default_rng(seed)
    n = min(int(n), len(pool))
    idx = rng.choice(len(pool), size=n, replace=False)
    return sorted(str(pool[int(i)]) for i in idx)


def _twin_book(strategy: Strategy, *, cadence: str, parent_id: str, kind: str,
               signal_name: str, construction_note: str, symbols: Sequence[str],
               extra: dict, created_utc: str) -> PaperBook:
    params = dict(strategy.engine_params or {})
    params["twin"] = {"kind": kind, "of": parent_id, **extra}
    if symbols:
        params["symbols"] = list(symbols)
    twin_strategy = strategy.with_(
        strategy_id=f"{strategy.strategy_id}::{kind}",
        title=f"{strategy.title} — {kind} twin",
        signal=Signal(name=signal_name, column=None,
                      direction=strategy.signal.direction,
                      source=f"control twin of {parent_id}",
                      note=construction_note),
        universe=Universe(
            name=f"{strategy.universe.name}::{kind}",
            source=f"control draw for {parent_id}",
            floor_dollar_vol_usd=strategy.universe.floor_dollar_vol_usd,
            min_price_usd=strategy.universe.min_price_usd,
            max_names=strategy.universe.max_names,
            note=construction_note),
        engine_params=params,
        parents=tuple(strategy.parents) + (strategy.strategy_id,),
    )
    return PaperBook(
        book_id=book_id_for(twin_strategy),
        strategy=twin_strategy,
        cadence=cadence,
        created_utc=created_utc,
        origin=f"{TWIN_PREFIX}{parent_id}",
        origin_text=construction_note,
        control_twin_ids=(),
        control_construction=construction_note,
    )


def _overlap(drawn: Sequence[str], parent_symbols: Sequence[str]) -> float | None:
    """What fraction of the twin's UNIVERSE is also in the parent's universe.

    Not a holdings overlap: the random twin selects at random WITHIN its
    universe every period, so two books can share a universe entirely and still
    hold disjoint names. It is recorded because the one case that must never be
    invisible is a book whose declared universe is the whole eligible pool --
    there the draw is the pool, this reads 1.0, and the control is doing its
    work through the SIGNAL alone. A reader has to be able to see which of the
    two is happening.
    """
    if not drawn:
        return None
    return round(len(set(drawn) & set(parent_symbols)) / len(set(drawn)), 4)


def _random_universe_twin(strategy, cadence, parent_id, pool, parent_symbols,
                          created_utc) -> PaperBook:
    seed = _twin_seed(strategy, "random_universe")
    n = len(parent_symbols) or int(strategy.construction.k)
    drawn = _draw(pool, n, seed)
    return _twin_book(
        strategy, cadence=cadence, parent_id=parent_id, kind="random_universe",
        signal_name="random_genome_null", construction_note=TWIN_RANDOM,
        symbols=drawn,
        extra={"seed": seed, "pool_size": len(pool), "n_drawn": len(drawn),
               "universe_overlap_with_parent": _overlap(drawn, parent_symbols),
               "band": "the dollar-volume DECILE band the parent's names occupy"},
        created_utc=created_utc)


def _beta_matched_twin(strategy, cadence, parent_id, pool, parent_symbols, bars,
                       asof, created_utc) -> PaperBook:
    seed = _twin_seed(strategy, "beta_matched")
    drawn: list[str] = []
    detail: dict = {"seed": seed, "estimator": BETA_ESTIMATOR}
    if bars is not None and pool and parent_symbols:
        try:
            betas = pre_period_beta(bars, sorted(set(pool) | set(parent_symbols)), asof)
            if betas:
                edges = _decile_edges(list(betas.values()))
                want: dict[int, int] = {}
                for sym in parent_symbols:
                    if sym in betas:
                        d = _decile_of(edges, betas[sym])
                        want[d] = want.get(d, 0) + 1
                by_decile: dict[int, list[str]] = {}
                for sym, b in betas.items():
                    if sym not in pool:
                        continue
                    by_decile.setdefault(_decile_of(edges, b), []).append(sym)
                short: dict[str, int] = {}
                for d, count in sorted(want.items()):
                    picked = _draw(sorted(by_decile.get(d, [])), count, seed + d)
                    if len(picked) < count:
                        # A decile the pool cannot fill is recorded BY DECILE
                        # rather than quietly topped up from elsewhere: a twin
                        # that says "beta-matched" while three of its ten
                        # buckets came from whatever was left is not matched.
                        short[str(d)] = count - len(picked)
                    drawn.extend(picked)
                detail["deciles_matched"] = {str(k): v for k, v in sorted(want.items())}
                detail["deciles_short"] = short
                detail["n_with_beta"] = len(betas)
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("beta-matched twin: %s", exc)
            detail["error"] = f"{type(exc).__name__}: {exc}"[:200]
    if not drawn:
        # NOT a silent fallback to the random draw: a beta-matched twin that is
        # secretly a random twin is worse than no beta twin, because it is
        # reported as the stricter control. The book says so on its own row.
        detail["UNMATCHED"] = ("no beta could be estimated from the local bars; "
                               "this twin is a RANDOM draw and must not be read "
                               "as beta-matched")
        drawn = _draw(pool, len(parent_symbols) or int(strategy.construction.k),
                      seed)
    detail["universe_overlap_with_parent"] = _overlap(drawn, parent_symbols)
    note = TWIN_BETA if "UNMATCHED" not in detail else (
        TWIN_BETA + " -- NOT MATCHED on this machine: " + detail["UNMATCHED"])
    return _twin_book(strategy, cadence=cadence, parent_id=parent_id,
                      kind="beta_matched", signal_name="beta_matched_index_sleeve",
                      construction_note=note, symbols=sorted(set(drawn)),
                      extra=detail, created_utc=created_utc)


def _overnight_only_twin(strategy, cadence, parent_id, parent_symbols,
                         created_utc) -> PaperBook:
    return _twin_book(
        strategy, cadence=cadence, parent_id=parent_id, kind="overnight_only",
        signal_name="overnight_only", construction_note=TWIN_OVERNIGHT,
        symbols=list(parent_symbols),
        extra={"holds": "close to next open, flat intraday",
               "why": ("FINDING_2026-08-23_OVERNIGHT_INTRADAY measured the split "
                       "at daily resolution; this twin is the systems check "
                       "against that known answer, not a new question")},
        created_utc=created_utc)


# --------------------------------------------------------------------------
# persistence


def _conn(db_path: Path | None = None) -> sqlite3.Connection:
    from backend.db import get_connection, init_db
    init_db(db_path)
    return get_connection(db_path)


def _strategy_from_dict(d: dict) -> Strategy:
    """Rebuild a `Strategy` from `as_dict()`. Unknown field -> refusal.

    A contract that round-trips through a lenient loader is a contract that can
    silently lose a field, and the field it loses will be the cost one.
    """
    from backend.strategy.contract import (Benchmark, CostModel, HoldRule,
                                           LossBudget, Objective, Sizing)

    def _sub(cls, payload: dict, **over):
        payload = dict(payload or {})
        payload.update(over)
        allowed = {f for f in cls.__dataclass_fields__}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise StrategyError(
                f"{cls.__name__} has no field(s) {unknown}. A contract loaded "
                f"leniently is a contract that can lose a field, and the field "
                f"it loses will be the cost one.")
        return cls(**payload)

    sizing = dict(d.get("sizing") or {})
    if sizing.get("overlays") is not None:
        # JSON has no tuple. Coercing here is what makes `as_dict()` round-trip
        # EXACTLY -- the fingerprint is computed over JSON and is unaffected
        # either way, but a reader comparing two contracts field by field would
        # see a spurious difference.
        sizing["overlays"] = tuple(sizing["overlays"])
    hold = dict(d.get("hold") or {})
    hold["roi_ladder"] = {int(k): float(v)
                          for k, v in (hold.get("roi_ladder") or {}).items()}
    if hold.get("exit_priority") is not None:
        hold["exit_priority"] = tuple(hold["exit_priority"])
    top = dict(d)
    return Strategy(
        strategy_id=top["strategy_id"], title=top.get("title", ""),
        universe=_sub(Universe, top.get("universe")),
        signal=_sub(Signal, top.get("signal")),
        construction=_sub(Construction, top.get("construction")),
        hold=_sub(HoldRule, hold),
        sizing=_sub(Sizing, sizing),
        costs=_sub(CostModel, top.get("costs")),
        benchmark=_sub(Benchmark, top.get("benchmark")),
        objective=_sub(Objective, top.get("objective")),
        loss_budget=_sub(LossBudget, top.get("loss_budget")),
        licence=Licence(top.get("licence", "PRODUCT_EXPERIMENT")),
        engine=top.get("engine", "series"),
        engine_params=dict(top.get("engine_params") or {}),
        parents=tuple(top.get("parents") or ()),
        note=top.get("note", ""),
    )


def _row_to_book(row) -> PaperBook:
    return PaperBook(
        book_id=row["id"],
        strategy=_strategy_from_dict(json.loads(row["contract_json"])),
        cadence=row["cadence"],
        created_utc=row["created_utc"],
        origin=row["origin"],
        origin_text=row["origin_text"] or "",
        control_twin_ids=tuple(json.loads(row["control_twin_ids"] or "[]")),
        control_construction=row["control_construction"] or "",
        ips_hash=row["ips_hash"],
        shadow=bool(row["shadow"]),
        status=row["status"],
    )


#: What a book's `paper_portfolios` row is worth at inception. Declared, not
#: inherited from the reference lanes' 100,000: a book's NAV series is compared
#: against its twin's, and both start here.
INCEPTION_VALUE = 100_000.0


def _persist(conn: sqlite3.Connection, book: PaperBook) -> None:
    from backend.db import _write_lock
    payload = json.dumps(book.strategy.as_dict(), sort_keys=True)
    with _write_lock:
        conn.execute(
            "INSERT OR IGNORE INTO paper_portfolios "
            "(id, inception_date, inception_value, config_version) VALUES (?,?,?,?)",
            (book.book_id, book.created_utc[:10], INCEPTION_VALUE,
             book.strategy.fingerprint))
        conn.execute(
            "INSERT OR REPLACE INTO paper_books "
            "(id, fingerprint, strategy_id, title, contract_json, cadence, origin,"
            " origin_text, control_twin_ids, control_construction, ips_hash,"
            " shadow, created_utc, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (book.book_id, book.strategy.fingerprint, book.strategy.strategy_id,
             book.strategy.title, payload, book.cadence, book.origin,
             book.origin_text, json.dumps(list(book.control_twin_ids)),
             book.control_construction, book.ips_hash, int(book.shadow),
             book.created_utc, book.status))
        conn.commit()


def create(strategy: Strategy, *, cadence: str, origin: str,
           origin_text: str = "", ips_hash: str | None = None,
           shadow: bool = False, bars=None, asof: date | None = None,
           db_path: Path | None = None,
           conn: sqlite3.Connection | None = None) -> tuple[PaperBook, list[PaperBook]]:
    """Create a book AND its twins, or create nothing.

    REFUSALS, and why each one is a refusal rather than a warning:

    * **no twin** — a book whose number can be shown without a control's number
      beside it is the thing B3 exists to prevent, and the cheapest place to
      enforce it is before the book has a number at all;
    * **zero cost** — `CostModel` already refuses a zero-cost policy unless
      `zero_cost_diagnostic=True`, and a diagnostic is not a paper book: it is a
      frictionless measurement that must never accrue a forward record;
    * **an origin that is not one of the three** — an unattributed book cannot
      later be told from one a human held, and B2's hold gate is about exactly
      that distinction.
    """
    if origin not in ORIGINS:
        raise BookError(f"origin {origin!r} must be one of {list(ORIGINS)}; a "
                        f"twin is created by `make_twins`, never by `create`")
    if strategy.costs.zero_cost_diagnostic:
        raise BookError(
            "this contract is a ZERO-COST DIAGNOSTIC. A frictionless run is a "
            "measurement, not a book: it may never accrue a forward record, "
            "because every number it produces would be quoted as net by whoever "
            "reads the NAV series. Declare real costs, or keep it in the farm.")
    asof = asof or date.today()
    created = _now()
    twins = make_twins(strategy, cadence=cadence, bars=bars, asof=asof,
                       created_utc=created)
    if not twins:
        raise BookError(
            "REFUSED: no control twin could be constructed for this book. A "
            "book without a twin is a number with nothing beside it (B3), and "
            "this programme has five months of evidence about what that costs.")
    book = PaperBook(
        book_id=book_id_for(strategy), strategy=strategy, cadence=cadence,
        created_utc=created, origin=origin, origin_text=origin_text,
        control_twin_ids=tuple(t.book_id for t in twins),
        control_construction=" | ".join(
            f"{t.strategy.engine_params['twin']['kind']}: {t.control_construction}"
            for t in twins),
        ips_hash=ips_hash, shadow=shadow)

    own = conn is None
    conn = conn or _conn(db_path)
    try:
        _persist(conn, book)
        for t in twins:
            _persist(conn, t)
    finally:
        if own:
            conn.close()
    logger.info("book %s created (%s, %s) with %d twin(s)", book.book_id,
                cadence, origin, len(twins))
    return book, twins


def get(book_id: str, *, db_path: Path | None = None,
        conn: sqlite3.Connection | None = None) -> PaperBook | None:
    own = conn is None
    conn = conn or _conn(db_path)
    try:
        row = conn.execute("SELECT * FROM paper_books WHERE id = ?",
                           (book_id,)).fetchone()
        return _row_to_book(row) if row else None
    finally:
        if own:
            conn.close()


def list_books(*, cadence: str | None = None, status: str | None = None,
               include_twins: bool = True, db_path: Path | None = None,
               conn: sqlite3.Connection | None = None) -> list[PaperBook]:
    own = conn is None
    conn = conn or _conn(db_path)
    try:
        sql = "SELECT * FROM paper_books"
        where, args = [], []
        if cadence:
            where.append("cadence = ?")
            args.append(cadence)
        if status:
            where.append("status = ?")
            args.append(status)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_utc, id"
        rows = conn.execute(sql, args).fetchall()
    finally:
        if own:
            conn.close()
    books = [_row_to_book(r) for r in rows]
    if not include_twins:
        books = [b for b in books if not b.is_twin]
    return books


def set_status(book_id: str, status: str, *, db_path: Path | None = None,
               conn: sqlite3.Connection | None = None) -> None:
    if status not in ("holding", "flipped", "retired"):
        raise BookError(f"status {status!r} is not holding/flipped/retired")
    from backend.db import _write_lock
    own = conn is None
    conn = conn or _conn(db_path)
    try:
        with _write_lock:
            conn.execute("UPDATE paper_books SET status = ? WHERE id = ?",
                         (status, book_id))
            conn.commit()
    finally:
        if own:
            conn.close()


def nav_series(book_ids: Iterable[str] | None = None, *,
               db_path: Path | None = None,
               conn: sqlite3.Connection | None = None
               ) -> dict[str, list[tuple[str, float]]]:
    """{book_id: [(date, nav)]} for the book namespace only.

    The companion of `morning.lane_nav_series` for books, and the reason a book
    forecast (`<book> beats <twin>`) can ever be graded: neither id is a
    security, so the resolver needs a price series for both and the marked NAV
    IS that series.
    """
    own = conn is None
    conn = conn or _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT portfolio_id, date, nav FROM paper_nav "
            "WHERE portfolio_id LIKE ? ORDER BY portfolio_id, date",
            (f"{BOOK_PREFIX}%",)).fetchall()
    finally:
        if own:
            conn.close()
    wanted = set(book_ids) if book_ids is not None else None
    out: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        pid = str(r["portfolio_id"])
        if wanted is not None and pid not in wanted:
            continue
        if r["nav"] is None:
            continue
        out.setdefault(pid, []).append((str(r["date"]), float(r["nav"])))
    return out


def worst_case(book: PaperBook, *, equity_usd: float | None = None) -> dict:
    """SESSION PROTOCOL RULE 4 for one book, from the contract's own function.

    Never re-derived here: `contract.loss_budget_worst_case` is the one place
    that prints the gross line beside the stop line, and a second copy is a
    second place for them to drift apart (28 Aug, -9% became -24%).
    """
    k = int(book.strategy.construction.k)
    equity = float(equity_usd if equity_usd is not None
                   else book.strategy.sizing.notional_usd)
    # THE BINDING CONSTRAINT, not the loosest one. `max_single_name` is a
    # ceiling per name and `gross_cap` is a ceiling on the sum; the selector
    # produces min(max_single_name, gross_cap / k) per name, so quoting
    # `max_single_name` alone reports a gross the book cannot reach and makes
    # `gross_within_cap` read false on every correctly-specified book. The
    # first real night_job book printed 1.2x gross against a 1.0 cap for
    # exactly this reason, on 2026-09-12, before it had bought anything.
    cap_per_name = float(book.strategy.construction.max_single_name) or 1.0
    ew_per_name = float(book.strategy.construction.gross_cap) / max(k, 1)
    notional_pct = min(cap_per_name, ew_per_name)
    out = loss_budget_worst_case(book.strategy, n_names=k,
                                 notional_pct=notional_pct, equity_usd=equity)
    out["notional_pct_binding_constraint"] = (
        "max_single_name" if cap_per_name <= ew_per_name else "gross_cap / k")
    out["max_single_name"] = cap_per_name
    out["equal_weight_per_name"] = ew_per_name
    return out


__all__ = ["BOOK_PREFIX", "CADENCES", "CADENCE_SESSIONS", "ORIGINS", "BookError",
           "PaperBook", "create", "get", "is_book_id", "list_books", "load_bars",
           "liquidity_panel", "make_twins", "nav_series", "pre_period_beta",
           "resolve_universe", "set_status", "worst_case", "book_id_for"]
