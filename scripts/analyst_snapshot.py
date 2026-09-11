"""N-E — THE DAILY ANALYST SNAPSHOT. A series that starts today, and says so.

    python -m scripts.analyst_snapshot --max-symbols 50
    python -m scripts.analyst_snapshot --max-symbols 3056

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
from scripts.news_pull import finnhub_key_name, universe_path  # noqa: E402

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

    t = yf.Ticker(symbol)
    out: dict[str, Any] = {"status": "ok", "error": ""}
    try:
        info = t.info or {}
    except Exception as e:  # noqa: BLE001
        info = {}
        out["error"] = f"info: {type(e).__name__}: {e}"
    out["company_name"] = info.get("shortName") or info.get("longName") or ""
    out["recommendation_mean"] = info.get("recommendationMean")
    out["recommendation_key"] = info.get("recommendationKey")
    out["n_analysts"] = info.get("numberOfAnalystOpinions")
    out["current_price"] = info.get("currentPrice") or info.get("regularMarketPrice")
    try:
        tgt = t.analyst_price_targets or {}
        if isinstance(tgt, dict):
            out["target_low"] = tgt.get("low")
            out["target_mean"] = tgt.get("mean")
            out["target_median"] = tgt.get("median")
            out["target_high"] = tgt.get("high")
            out["current_price"] = out.get("current_price") or tgt.get("current")
    except Exception as e:  # noqa: BLE001
        out["error"] = (out["error"] + " | " if out["error"] else "") + f"targets: {type(e).__name__}: {e}"
    try:
        rec = t.recommendations
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


def _symbols(limit: int | None) -> list[str]:
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
    return out[:limit] if limit else out


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
             update_names: bool = True) -> dict:
    """Pull, write one parquet for today, return the receipt."""
    t0 = time.time()
    fetch = fetch or fetch_yfinance
    observed = _now()
    day = observed.date().isoformat()
    symbols = _symbols(max_symbols)
    rows: list[dict] = []
    learned: dict[str, str] = {}
    errors: list[str] = []
    counts = {"ok": 0, "partial": 0, "empty": 0, "error": 0}
    path = out_dir() / f"{day}.parquet"

    def _flush() -> bool:
        if not rows:
            return False
        try:
            import pandas as pd
            out_dir().mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows, columns=list(COLUMNS)).to_parquet(path, index=False)
            return True
        except Exception:  # noqa: BLE001 — a failed checkpoint must not end the sweep
            return False

    for i, sym in enumerate(symbols):
        if i and pace_s:
            time.sleep(pace_s)
        try:
            got = fetch(sym)
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
            print(f"  checkpoint {i + 1}/{len(symbols)} symbols "
                  f"({(time.time() - t0) / (i + 1):.2f}s/symbol) -> {path}", flush=True)

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
        "headline": (f"{len(rows):,} (symbol, date) rows for {day}; "
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
    a = ap.parse_args(argv)
    out = snapshot(a.max_symbols, pace_s=a.pace, update_names=not a.no_name_table)
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
