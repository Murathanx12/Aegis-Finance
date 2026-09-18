"""N-E — THE DAILY ANALYST SNAPSHOT. A series that starts today, and says so.

    python -m scripts.analyst_snapshot --max-symbols 50
    python -m scripts.analyst_snapshot --max-symbols 3056
    python -m scripts.analyst_snapshot --universe tradable     # the band we can trade

One parquet row per (symbol, date) at

    <DATA_DIR>/optimus/analyst_snapshots/<YYYY-MM-DD>.parquet

WHY A SNAPSHOT AT ALL, WHEN THE DATA IS ALREADY THERE
=====================================================
Because it is not. Both free analyst sources are `pit_grade: index_state` in the
registry, and that is the whole reason this job exists:

* yfinance's `recommendations` / `analyst_price_targets` report Yahoo's
  **current** consensus. There is no dated history behind them; the `period`
  column is relative ("0m", "-1m"), not a date.
* Finnhub's recommendation trend keeps roughly **four months** server-side. A
  history older than that cannot be bought back at any price on the free tier.

So the point-in-time series does not exist until we start writing it, and it
starts the day this job first runs. `series_starts` in every receipt says
exactly that, in the receipt rather than in a doc, because the first person to
regress on this panel will otherwise assume the history goes back further than
it does.

An index_state source may never LABEL a return (invariant 20, enforced in
`news_registry`). What it may do is sit beside one as a feature computed from
OUR OWN dated snapshots — a change in consensus between two dates we wrote is a
fact about our observations, not a claim about Yahoo's.

AND THE CORPSE THAT BINDS ANY USE OF IT
=======================================
`analyst_target_upside_xs` is graded **PERVERSE/CLOSED** (ANALYST-IBES-1,
2026-08-11): ranking on the raw consensus upside lost 8-18%/yr gross over 21
years of PIT IBES, and `signal_registry` bars a PERVERSE signal from leading a
ranking. This file writes data. It does not rank anything, and nothing
downstream may rank on the raw upside without a fresh pre-registered trial.

THE SECOND DELIVERABLE, FOR FREE
================================
The same `.info` call that carries `recommendationMean` also carries
`shortName` / `longName`. The 09-11 name-table probe measured yfinance at
1.38 s/name and stopped at 200 of 3,056 names for budget, which is why N-D's
resolver can only name-match 230 symbols. Rather than pay that 70 minutes
twice, `--update-name-table` writes the names this run learned back into
`backend/data/news_entities/issuers.csv`. One pass, two deliverables — maximise
information per dollar, not minimise calls.

FINNHUB is attempted only if `FINNHUB_API_KEY` or `AAT_FINNHUB_API_KEY`
resolves. Neither does here, so the receipt names them and moves on. Names only,
never a value.

WHICH UNIVERSE, AND WHY THE DAILY PASS ASKS FOR THE SMALLER ONE (chunk 15b)
===========================================================================
`--universe all` (the CLI default) is the 3,056-name potential universe in
`backend/data/optimus/potential_universe/`. Measured, not estimated --
`analyst_snapshots/2026-09-13_receipt.json`: 3,056 symbols, **3.987 s/symbol,
12,184 s = 3.39 h** of a 3.9-hour daily pass. Roughly a quarter of that is spent
on names no book here can hold: below the $10M median-dollar-volume floor, below
$5, or an ETF.

At the same rate the tradable band (2,362 names on the 2026-09-01 universe file)
projects to **9,417 s = 2.62 h, saving 0.77 h a day** -- about 23%, which is the
share of the list the floor removes. The saving is in WALL TIME, not in
information: every name dropped is one no book in this programme can hold.

`--universe tradable` is the band `night_f_seasonality_export.load_universe`
already defines -- **and it is READ from that function, not re-derived here.**
Two definitions of "the universe we trade" is two things to keep in step, and
the one that would drift is this one, because the band's real owner is the
EXECUTION repo (`alpha/universe.py` writes
`state/universe/HIGH_DISPERSION_US_v1_<asof>.json`; the exporter applies the
floor). The receipt prints the file it read, its `asof`, the filter in numbers
and how many names each clause dropped, so a reader can tell a shrinking band
from a broken path.

`daily_pass.py` passes `tradable`. The CLI default stays `all`, because a
one-off sweep for the NAME TABLE wants every name it can get and that
deliverable has nothing to do with tradability.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402
from backend.services import news_entities as entities  # noqa: E402
from scripts.news_pull import (  # noqa: E402
    call_with_timeout, finnhub_key_name, universe_path,
)

#: Hard bound on ONE yfinance property read. Yahoo is unofficial and has no
#: SLA: on 2026-09-11 a `Ticker.news` call held an ESTABLISHED socket for five
#: minutes with no timeout of ours. A guard that protects only the news path
#: protects nothing here — this sweep is ~70 minutes and reads three
#: properties per symbol, so it is the MORE exposed of the two.
YF_PROPERTY_TIMEOUT_S = 25.0

#: Hard bound on the `yfinance.Ticker(symbol)` CONSTRUCTION.
#:
#: FOUND 2026-09-18, looking for what held the 09-14 daily pass. Every property
#: read below was already boxed at 25 s, and the construction was not — and it
#: is not free. `TickerBase.__init__` (yfinance 1.2.0, base.py:84) runs
#:
#:     self.session = session or requests.Session(impersonate="chrome")
#:
#: which is a **curl_cffi** session: a C-level libcurl handle, allocated on the
#: MAIN thread, outside every box in this file. It is also the one place the
#: sweep touches a shared C library while abandoned daemon threads from earlier
#: timed-out property reads are still inside their own curl calls. That is not
#: a proof — nobody dumped the stack of the wedged process — but it IS the only
#: unbounded call in the loop, and an unbounded call in a job that runs
#: unattended for three hours does not get to stay unbounded on the grounds
#: that we could not prove it was the one.
YF_CONSTRUCT_TIMEOUT_S = 20.0

#: Hard bound on ONE symbol, end to end. Defence in depth: it bounds the three
#: property reads, the construction, and anything a future edit adds between
#: them without remembering to box it. The sum of the parts plus slack.
SYMBOL_TIMEOUT_S = 3 * YF_PROPERTY_TIMEOUT_S + YF_CONSTRUCT_TIMEOUT_S + 10.0

#: Hard bound on ONE checkpoint write. The parquet lands on local disk and
#: should take milliseconds; it is boxed because `DATA_DIR` is a configurable
#: path and a job that runs for three hours unattended should not be able to
#: hang on a filesystem.
FLUSH_TIMEOUT_S = 120.0

COLUMNS = (
    "symbol", "date", "observed_utc", "source",
    "current_price", "target_low", "target_mean", "target_median", "target_high",
    "recommendation_mean", "recommendation_key", "n_analysts",
    "strong_buy", "buy", "hold", "sell", "strong_sell", "rec_period",
    "company_name", "status", "error",
)


def out_dir() -> Path:
    return Path(_config.DATA_DIR) / "optimus" / "analyst_snapshots"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _f(v) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _i(v) -> int | None:
    f = _f(v)
    return int(f) if f is not None else None


# ------------------------------------------------------------------- fetching

def fetch_yfinance(symbol: str) -> dict:
    """One symbol's consensus snapshot. THE network door — tests replace it.

    Every field is optional: a thinly covered name returns a row with nulls and
    `status: "partial"`, never a dropped row. A symbol that fails entirely
    returns `status: "error"` with the exception string, because a silently
    missing symbol is how a coverage gap becomes invisible.
    """
    import yfinance as yf

    # BOXED — see YF_CONSTRUCT_TIMEOUT_S. This line allocates a curl_cffi
    # session; it is not the free attribute assignment it looks like.
    t = call_with_timeout(lambda: yf.Ticker(symbol), YF_CONSTRUCT_TIMEOUT_S,
                          f"{symbol}.Ticker()")
    out: dict[str, Any] = {"status": "ok", "error": ""}
    try:
        info = call_with_timeout(lambda: t.info or {}, YF_PROPERTY_TIMEOUT_S,
                                 f"{symbol}.info") or {}
    except Exception as e:  # noqa: BLE001
        info = {}
        out["error"] = f"info: {type(e).__name__}: {e}"
    out["company_name"] = info.get("shortName") or info.get("longName") or ""
    out["recommendation_mean"] = info.get("recommendationMean")
    out["recommendation_key"] = info.get("recommendationKey")
    out["n_analysts"] = info.get("numberOfAnalystOpinions")
    out["current_price"] = info.get("currentPrice") or info.get("regularMarketPrice")
    try:
        tgt = call_with_timeout(lambda: t.analyst_price_targets or {},
                                YF_PROPERTY_TIMEOUT_S, f"{symbol}.analyst_price_targets") or {}
        if isinstance(tgt, dict):
            out["target_low"] = tgt.get("low")
            out["target_mean"] = tgt.get("mean")
            out["target_median"] = tgt.get("median")
            out["target_high"] = tgt.get("high")
            out["current_price"] = out.get("current_price") or tgt.get("current")
    except Exception as e:  # noqa: BLE001
        out["error"] = (out["error"] + " | " if out["error"] else "") + f"targets: {type(e).__name__}: {e}"
    try:
        rec = call_with_timeout(lambda: t.recommendations, YF_PROPERTY_TIMEOUT_S,
                                f"{symbol}.recommendations")
        if rec is not None and hasattr(rec, "empty") and not rec.empty:
            row = rec.iloc[0].to_dict()
            out["rec_period"] = str(row.get("period", ""))
            out["strong_buy"] = row.get("strongBuy")
            out["buy"] = row.get("buy")
            out["hold"] = row.get("hold")
            out["sell"] = row.get("sell")
            out["strong_sell"] = row.get("strongSell")
    except Exception as e:  # noqa: BLE001
        out["error"] = (out["error"] + " | " if out["error"] else "") + f"recs: {type(e).__name__}: {e}"
    filled = [k for k in ("recommendation_mean", "target_mean", "strong_buy") if out.get(k) is not None]
    if not filled:
        out["status"] = "empty" if not out["error"] else "error"
    elif out["error"]:
        out["status"] = "partial"
    return out


def _row(symbol: str, day: str, observed: str, got: dict) -> dict:
    return {
        "symbol": symbol, "date": day, "observed_utc": observed, "source": "yfinance",
        "current_price": _f(got.get("current_price")),
        "target_low": _f(got.get("target_low")),
        "target_mean": _f(got.get("target_mean")),
        "target_median": _f(got.get("target_median")),
        "target_high": _f(got.get("target_high")),
        "recommendation_mean": _f(got.get("recommendation_mean")),
        "recommendation_key": str(got.get("recommendation_key") or "") or None,
        "n_analysts": _i(got.get("n_analysts")),
        "strong_buy": _i(got.get("strong_buy")), "buy": _i(got.get("buy")),
        "hold": _i(got.get("hold")), "sell": _i(got.get("sell")),
        "strong_sell": _i(got.get("strong_sell")),
        "rec_period": str(got.get("rec_period") or "") or None,
        "company_name": str(got.get("company_name") or "") or None,
        "status": got.get("status", "ok"), "error": got.get("error") or None,
    }


#: The two universes this job can sweep. `all` is the historical behaviour and
#: stays the CLI default; `tradable` is the band the books can actually hold.
UNIVERSES = ("all", "tradable")


def _symbols_all(limit: int | None) -> tuple[list[str], dict]:
    p = universe_path()
    out: list[str] = []
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            s = d.get("symbol")
            if isinstance(s, str) and s.strip():
                out.append(s.strip().upper())
    prov = {"universe": "all", "source": str(p), "exists": p.exists(),
            "n_available": len(out),
            "filter": "none -- every symbol in the potential universe"}
    return (out[:limit] if limit else out), prov


def _symbols_tradable(limit: int | None) -> tuple[list[str], dict]:
    """The tradable band, READ from the one function that already defines it.

    `night_f_seasonality_export.load_universe` applies the $10M median-dollar-
    volume floor, the $5 price minimum and the ETF flag to the execution repo's
    stored universe file. Importing it is the point: a second copy of those three
    clauses here would be a second definition of "the universe we trade", and the
    day they disagreed the receipts would still both say "tradable".

    A refusal there (no stored universe file, no members, nothing above the
    floor) is re-raised as a refusal HERE -- an empty band is not silently
    swapped for the 3,056-name list, because a sweep that quietly grew by 700
    names is exactly the kind of thing nobody notices in a receipt.
    """
    from scripts.night_f_seasonality_export import (
        FLOOR_USD, MIN_PRICE_USD, load_universe,
    )

    band = load_universe()
    syms = sorted(band["symbols"])
    prov = {
        "universe": "tradable",
        "source": band["path"],
        "asof": band.get("asof"),
        "exists": True,
        "n_members": band["n_members"],
        "n_available": band["n_kept"],
        "dropped": dict(band["dropped"]),
        "filter": (f"median dollar volume >= ${FLOOR_USD:,.0f}, "
                   f"price >= ${MIN_PRICE_USD:g}, ETFs excluded"),
        "filter_owner": ("scripts/night_f_seasonality_export.load_universe -- read, "
                         "not re-derived; the band's own owner is the execution "
                         "repo's alpha/universe.py"),
    }
    return (syms[:limit] if limit else syms), prov


def _symbols(limit: int | None, universe: str = "all") -> tuple[list[str], dict]:
    u = (universe or "all").strip().lower()
    if u not in UNIVERSES:
        raise ValueError(f"unknown universe {universe!r}; expected one of {UNIVERSES}")
    return _symbols_all(limit) if u == "all" else _symbols_tradable(limit)


def update_name_table(learned: dict[str, str]) -> dict:
    """Write newly learned company names into `issuers.csv`. Never overwrites.

    An existing `primary_name` is left alone: the name table is version
    controlled, and a run that silently rewrote 200 hand-checked names with
    whatever Yahoo said today would be a change nobody reviewed.
    """
    path = entities.entities_dir() / "issuers.csv"
    if not path.exists() or not learned:
        return {"updated": 0, "path": str(path), "note": "no table or nothing learned"}
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
        fields = list(rows[0].keys()) if rows else []
    n = 0
    for row in rows:
        sym = (row.get("symbol") or "").strip().upper()
        name = learned.get(sym, "").strip()
        if name and not (row.get("primary_name") or "").strip():
            row["primary_name"] = name
            aliases = [a for a in (row.get("aliases") or "").split("|") if a.strip()]
            if name not in aliases:
                aliases.append(name)
            row["aliases"] = "|".join(aliases)
            n += 1
    if n:
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    return {"updated": n, "path": str(path),
            "note": "existing primary_name values are never overwritten"}


#: Rows are flushed to the parquet every this many symbols.
#:
#: A 3,056-symbol sweep is ~70 minutes at the rate the 09-11 probe measured
#: (1.38 s/name). A job that only writes at exit loses the whole run to one
#: crash, one reboot or one kill — which is exactly what happened to
#: `G3_evolve_v2` on 2026-09-10, and the lesson was "checkpoint per unit of
#: work", not "hope". The partial file is a valid snapshot of the symbols
#: reached; the receipt says how many that was.
CHECKPOINT_EVERY = 250


def snapshot(max_symbols: int | None = None, *, pace_s: float = 1.0,
             fetch: Callable[[str], dict] | None = None,
             update_names: bool = True, universe: str = "all") -> dict:
    """Pull, write one parquet for today, return the receipt.

    `universe` is "all" (the 3,056-name potential universe) or "tradable" (the
    ~2,362-name band at the $10M floor). A refusal from the band's own loader is
    returned AS a refusal -- never silently downgraded to the larger list.
    """
    t0 = time.time()
    fetch = fetch or fetch_yfinance
    observed = _now()
    day = observed.date().isoformat()
    try:
        symbols, universe_prov = _symbols(max_symbols, universe)
    except Exception as exc:  # noqa: BLE001
        return {
            "job": "analyst_snapshot", "licence": "PRODUCT_EXPERIMENT",
            "llm_spend_usd": 0.0, "date": day, "rows": 0,
            "symbols_requested": 0,
            "refused": (f"universe {universe!r} could not be resolved "
                        f"({type(exc).__name__}: {exc})"),
            "universe": {"universe": universe, "resolved": False},
            "written_utc": _now().isoformat(timespec="seconds"),
            "headline": f"REFUSED: no {universe} universe to sweep",
        }
    rows: list[dict] = []
    learned: dict[str, str] = {}
    errors: list[str] = []
    counts = {"ok": 0, "partial": 0, "empty": 0, "error": 0}
    path = out_dir() / f"{day}.parquet"

    def _write_parquet() -> bool:
        import pandas as pd
        out_dir().mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows, columns=list(COLUMNS)).to_parquet(path, index=False)
        return True

    def _flush() -> bool:
        if not rows:
            return False
        try:
            return bool(call_with_timeout(_write_parquet, FLUSH_TIMEOUT_S,
                                          f"checkpoint {len(rows)} rows"))
        except Exception:  # noqa: BLE001 — a failed checkpoint must not end the sweep
            return False

    for i, sym in enumerate(symbols):
        if i and pace_s:
            time.sleep(pace_s)
        try:
            # THE WHOLE SYMBOL IS BOXED, not just the calls inside it. On
            # 2026-09-14 the daily pass wedged here after 1,500 of 2,362 symbols
            # and stayed alive for four days while every scheduled firing after
            # it died at 0x80070420. Every network call in `fetch_yfinance` was
            # already bounded at 25 s, which is exactly why the outer box has to
            # exist: a per-call box does not bound the call site.
            got = call_with_timeout(lambda s=sym: fetch(s), SYMBOL_TIMEOUT_S, sym)
        except Exception as e:  # noqa: BLE001 — one bad symbol must not end the sweep
            got = {"status": "error", "error": f"{type(e).__name__}: {e}"}
        counts[got.get("status", "error")] = counts.get(got.get("status", "error"), 0) + 1
        if got.get("error") and len(errors) < 20:
            errors.append(f"{sym}: {got['error']}")
        name = (got.get("company_name") or "").strip()
        if name:
            learned[sym] = name
        rows.append(_row(sym, day, observed.isoformat(timespec="seconds"), got))
        if CHECKPOINT_EVERY and (i + 1) % CHECKPOINT_EVERY == 0:
            _flush()
            rate = (time.time() - t0) / (i + 1)
            # The parquet alone is a number with no provenance. A checkpoint
            # writes its own PARTIAL receipt so a killed sweep is still
            # readable: how far it got, at what rate, and that it is partial.
            try:
                (out_dir() / f"{day}_receipt.json").write_text(json.dumps({
                    "job": "analyst_snapshot", "status": "PARTIAL",
                    "date": day, "path": str(path),
                    "symbols_requested": len(symbols), "rows": len(rows),
                    "universe": dict(universe_prov),
                    "by_status": dict(counts),
                    "rate_s_per_symbol": round(rate, 3),
                    "projected_total_min": round(rate * len(symbols) / 60.0, 1),
                    "note": ("written at a checkpoint; the run had not finished. "
                             "The parquet holds the symbols reached so far."),
                    "written_utc": _now().isoformat(timespec="seconds"),
                }, indent=1, default=str), encoding="utf-8")
            except Exception:  # noqa: BLE001 — a receipt must not end the sweep
                pass
            print(f"  checkpoint {i + 1}/{len(symbols)} symbols "
                  f"({rate:.2f}s/symbol, ~{rate * len(symbols) / 60:.0f} min total) -> {path}",
                  flush=True)

    written = False
    write_note = ""
    if rows:
        out_dir().mkdir(parents=True, exist_ok=True)
        try:
            import pandas as pd
            pd.DataFrame(rows, columns=list(COLUMNS)).to_parquet(path, index=False)
            written = True
        except Exception as e:  # noqa: BLE001
            write_note = f"parquet write failed ({type(e).__name__}: {e}); wrote JSONL instead"
            path = out_dir() / f"{day}.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    name_update = update_name_table(learned) if update_names else {"updated": 0, "note": "disabled"}
    existing = sorted(p.stem for p in out_dir().glob("*.parquet")) if out_dir().exists() else []
    fk = finnhub_key_name()
    graded = counts["ok"] + counts["partial"]

    receipt = {
        "job": "analyst_snapshot", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "date": day, "observed_utc": observed.isoformat(timespec="seconds"),
        "symbols_requested": len(symbols), "rows": len(rows),
        "universe": universe_prov,
        "by_status": counts,
        "coverage_rate": round(graded / len(rows), 4) if rows else None,
        "path": str(path), "parquet": written, "write_note": write_note,
        "wall_s": round(time.time() - t0, 1),
        "rate_s_per_symbol": round((time.time() - t0) / len(rows), 3) if rows else None,
        "series_starts": existing[0] if existing else day,
        "series_days": len(existing) or 1,
        "series_note": (
            "THE SERIES STARTS THE DAY THIS JOB FIRST RAN. yfinance's consensus is a "
            "CURRENT snapshot with no dated history (pit_grade index_state) and Finnhub "
            "keeps ~4 months server-side, so there is no earlier history to fetch — only "
            "history to accumulate from here."
        ),
        "finnhub": (
            {"attempted": False, "reason": "no FINNHUB_API_KEY / AAT_FINNHUB_API_KEY resolves "
                                           "in this environment (names only, never values)"}
            if not fk else {"attempted": False, "reason": f"key {fk} resolves; the Finnhub leg "
                                                          f"is not implemented yet"}
        ),
        "name_table_update": name_update,
        "corpse_that_binds": (
            "analyst_target_upside_xs is PERVERSE/CLOSED (ANALYST-IBES-1, 2026-08-11: "
            "-8 to -18%/yr gross over 21 years of PIT IBES). This job writes data and "
            "ranks nothing; the raw upside may not lead a ranking without a fresh prereg."
        ),
        "errors_first_20": errors,
        "written_utc": _now().isoformat(timespec="seconds"),
        "headline": (f"{len(rows):,} (symbol, date) rows for {day} over the "
                     f"{universe_prov['universe']} universe "
                     f"({universe_prov['n_available']:,} available, "
                     f"{universe_prov['filter']}); "
                     f"{graded:,} carried at least one analyst field"),
    }
    if rows:
        (out_dir() / f"{day}_receipt.json").write_text(
            json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--max-symbols", type=int, default=None)
    ap.add_argument("--pace", type=float, default=1.0, help="seconds between symbols")
    ap.add_argument("--no-name-table", action="store_true",
                    help="do not write learned company names back into issuers.csv")
    ap.add_argument("--universe", choices=list(UNIVERSES), default="all",
                    help=("all = the 3,056-name potential universe (default, and what "
                          "the name-table deliverable wants); tradable = the band at "
                          "the $10M median-dollar-volume floor, >= $5, ETFs out "
                          "(~2,362 names; what daily_pass asks for)"))
    a = ap.parse_args(argv)
    out = snapshot(a.max_symbols, pace_s=a.pace, update_names=not a.no_name_table,
                   universe=a.universe)
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
