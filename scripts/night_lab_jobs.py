"""NIGHT LAB JOBS -- one function per job, each writing its own receipt.

    python -m scripts.night_lab_jobs L11_belief_inventory --out receipt.json

Run by `scripts/night_lab.py` as subprocesses with a per-job timeout. Each job:

* answers ONE question, named in the receipt;
* names `cells_looked_at` -- the multiplicity is part of the result, not a
  footnote (`learner/inference.py`);
* writes a receipt even when it finds nothing, and especially then;
* claims nothing. Every verdict is one of NOVEL / NOISE / CANNOT DETERMINE /
  REFUTED / INVENTORY, and `CANNOT DETERMINE` is the expected answer to most
  questions asked for the first time on one night of data.

Licence for everything here: `PRODUCT_EXPERIMENT`. Nothing in this file may be
quoted as a research claim without re-running it under the claim standard.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TERMINAL = ROOT.parent / "aegis-alpha-terminal"
RUN_DATE = "2026-09-05"
OUT_DIR = ROOT / "backend" / "data" / "optimus" / f"night_lab_{RUN_DATE}"

sys.path.insert(0, str(ROOT))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# =========================================================== L11 belief series


def L11_belief_inventory() -> dict:
    """What is actually IN the belief series, and could it ever answer anything?

    TRIAL-PREDMARKET-1 has been collecting Polymarket and Kalshi rows daily
    since 25 Aug. The question tonight is deliberately not "does it predict":
    it is the prior question, **how many observations does any single event
    have**, because a market with four observations cannot be tested however
    interesting it is. Inventory, then the test design. No claim.
    """
    path = TERMINAL / "state" / "belief_series.jsonl"
    if not path.exists():
        return {"verdict": "CANNOT DETERMINE", "question": "belief-series inventory",
                "headline": f"no file at {path}", "cells_looked_at": 0}
    rows = []
    bad = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    df = pd.DataFrame(rows)
    df["day"] = df["ts_utc"].astype(str).str.slice(0, 10)
    by_id = df.groupby(["source", "id"]).agg(
        n_obs=("ts_utc", "size"), n_days=("day", "nunique"),
        first=("day", "min"), last=("day", "max"),
        p_yes_seen=("p_yes", lambda s: int(s.notna().sum())))
    testable = by_id[by_id["n_days"] >= 60]
    priced = by_id[by_id["p_yes_seen"] > 0]
    top = by_id.sort_values("n_days", ascending=False).head(10)
    return {
        "question": "how much history does the belief series actually hold, per event?",
        "family_id": "night-lab-L11-belief-inventory",
        "cells_looked_at": int(len(by_id)),
        "n_rows": int(len(df)), "unreadable_lines": bad,
        "sources": {k: int(v) for k, v in df["source"].value_counts().items()},
        "n_events": int(len(by_id)),
        "n_events_with_a_price": int(len(priced)),
        "days_covered": sorted(df["day"].unique().tolist()),
        "n_events_with_60_plus_days": int(len(testable)),
        "max_days_on_any_event": int(by_id["n_days"].max()),
        "longest_events": [{"source": s, "id": i, **{k: (int(v) if isinstance(v, (int, np.integer))
                                                     else v) for k, v in r.items()}}
                           for (s, i), r in top.iterrows()],
        "headline": (f"{len(by_id)} events, {len(df)} rows, longest history "
                     f"{int(by_id['n_days'].max())} DAYS; {len(testable)} events reach 60 days"),
        "verdict": "INVENTORY",
        "test_design_when_it_matures": {
            "hypothesis": ("a move in an event's implied probability leads the return of the "
                           "names whose cash flows the event names -- tariffs/rates/approvals"),
            "unit": "event-day, paired with a mapped basket of permnos",
            "primary_metric": "next-5-session excess over beta*market of the mapped basket",
            "earliest_decision_date": "when >= 20 distinct EVENTS carry >= 60 observations each",
            "why_not_now": ("n_effective counts DATE BLOCKS (CANON 58) and this series spans "
                            "days, not blocks: every event's observations are one regime"),
            "pre_registration_required": True,
        },
    }


# ========================================================= L12 mirror reconcile


def L12_mirror_reconcile() -> dict:
    """What does the website's `mirror` lane actually hold, versus its seed?

    Murat, 2026-09-05: the mirror lane shows about -16% and he suspects a setup
    error rather than performance. A 2026-08-19 reconciliation already found
    that the number is real (the June book) plus a NAV-lag bug that was fixed.
    This job re-runs the reconciliation READ-ONLY and prints holdings against
    the seed so the question is answered by an artefact rather than by memory.
    """
    import importlib
    out: dict = {"question": "does the mirror lane hold what it was seeded with?",
                 "family_id": "night-lab-L12-mirror-reconcile", "cells_looked_at": 1}
    try:
        mod = importlib.import_module("scripts.lane_positions_reconcile")
    except Exception as exc:                                          # noqa: BLE001
        return {**out, "verdict": "CANNOT DETERMINE",
                "headline": f"reconcile script not importable: {type(exc).__name__}: {exc}"}
    # `--from-prod` is a GET against the public read API. Read-only by
    # construction: this script has no write path and holds no credential.
    results, errors = [], {}
    for lane in getattr(mod, "LANES", ("mirror", "conviction")):
        try:
            results.append(mod.reconcile(mod.verify(mod.load_prod(lane))))
        except Exception as exc:                                      # noqa: BLE001
            errors[lane] = f"{type(exc).__name__}: {str(exc)[:200]}"
    if not results:
        return {**out, "verdict": "CANNOT DETERMINE", "errors": errors,
                "headline": ("no lane could be read: "
                             + "; ".join(f"{k}: {v}" for k, v in errors.items()))[:200]}
    summary = []
    for r in results:
        summary.append({k: r.get(k) for k in
                        ("lane", "n_positions", "n_rebalance_events", "equity_at_last_close",
                         "nav_latest", "equity_vs_nav_gap_pct", "within_declared_tolerance",
                         "daily_return_corr_lag0", "daily_return_corr_lag1_aligned")
                        if k in r})
    return {**out, "verdict": "INVENTORY", "lanes": results, "summary": summary,
            "errors": errors,
            "headline": ("; ".join(
                f"{s.get('lane')}: {s.get('n_positions')} positions, equity "
                f"{s.get('equity_at_last_close')} vs NAV {s.get('nav_latest')} "
                f"({s.get('equity_vs_nav_gap_pct')}%, within tolerance="
                f"{s.get('within_declared_tolerance')})" for s in summary))[:400],
            "note": ("READ-ONLY GETs against the public lane API. Nothing in the lane, the "
                     "registry or the NAV table was written; repairing a track record is "
                     "attended by rule.")}


# ==================================================== L13 corpus-to-Railway design


def L13_corpus_railway_design() -> dict:
    """A design, and the two numbers that decide whether it is worth it.

    The corpus (news, filings, calendars) lives on the laptop, so the Railway
    seal authority seals books without it -- which is why hack4 sealed empty on
    2026-09-03. The proposal is one scheduled service writing to the authority's
    volume. This job measures what would move and writes the design; the Railway
    change itself is Murat's, attended.
    """
    corpus_dir = TERMINAL / "state" / "corpus"
    # RECURSIVE: the store is `observations/<month>.jsonl` plus `features/<sym>.jsonl`,
    # not a flat directory. A first cut globbed the top level, found five rows,
    # and would have reported a 230k-row corpus as empty -- an absence that
    # reads as a measurement is this repo's most expensive failure shape.
    files = sorted(corpus_dir.rglob("*.jsonl")) if corpus_dir.exists() else []
    rows, bytes_total, by_file = 0, 0, {}
    for f in files:
        n = sum(1 for _ in f.open(encoding="utf-8", errors="replace"))
        rows += n
        bytes_total += f.stat().st_size
        by_file[f.name] = {"rows": n, "mib": round(f.stat().st_size / 1048576, 2)}
    design = OUT_DIR / "DESIGN_corpus_to_railway.md"
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text(_CORPUS_DESIGN.format(
        rows=f"{rows:,}", mib=f"{bytes_total / 1048576:,.1f}",
        files=len(files), date=RUN_DATE), encoding="utf-8")
    return {
        "question": "what would move to Railway, how big is it, and what would it cost?",
        "family_id": "night-lab-L13-corpus-railway",
        "cells_looked_at": len(files),
        "corpus_rows_local": rows,
        "corpus_mib_local": round(bytes_total / 1048576, 2),
        "files": by_file,
        "design_doc": str(design.relative_to(ROOT)),
        "headline": (f"{rows:,} corpus rows / {bytes_total / 1048576:,.1f} MiB in {len(files)} "
                     f"file(s) live only on the laptop; design written, no Railway change made"),
        "verdict": "INVENTORY",
    }


_CORPUS_DESIGN = """# DESIGN — move corpus collection to Railway (written {date}, NOT applied)

**Measured tonight:** {rows} rows / {mib} MiB across {files} local file(s).

## The defect this removes
The seal authority runs on Railway; the corpus runs on a laptop. A seal taken
while the laptop is off is a seal taken without news, filings or catalyst dates
— which on 2026-09-03 produced an empty hack4 book that looked like a decision.
Absence of an input read as an opinion. That is the failure being closed.

## The shape
One Railway **cron service** in the existing project, sharing the seal
authority's volume:

- image: the terminal repo `Dockerfile` (already built)
- command: `python -m scripts.corpus_refresh --all`
- schedule: `10 21 * * 1-5` UTC (17:10 ET, after the close, before the seal)
- volume: the authority's `/app/state`, so the seal reads the same path it
  reads today and NO code changes
- variables: the collector keys only (`AAT_FINNHUB_API_KEY`, `AAT_FRED_API_KEY`);
  **no broker keys** — a collector that cannot authenticate to a venue cannot
  place an order by accident

## Cost
One more service on the same project. The measured comparator is the existing
warm loop at ~$7/month; a cron that runs once a day for a few minutes is well
under that. Bandwidth is the daily delta, not the {mib} MiB (the initial copy is
one upload).

## The check that proves it is working
Add to `scripts/fleet_health.py`: **`corpus rows on the authority >= N`**, where
N is yesterday's count minus a tolerance. A collector that returns 200 with an
empty body is the house failure mode (`silent-fragility-audit`), so the health
check must assert on ROWS THAT ARRIVED, never on the job's exit code.

## What is NOT in this design
Moving the corpus does not make it correct. Only 7.7% of corpus news is a new
dated fact (T12, closed negative), so this is an availability fix, not an alpha
fix, and it should be judged on "did the authority seal with news present",
nothing more.

## The decision Murat makes
Create the service, or keep collection on the laptop and accept that a seal
taken with the laptop off is news-blind. No session flips this.
"""


# ================================================= L8 grade the sealed books


def L8_grade_sealed_books() -> dict:
    """Grade every sealed prediction book against what actually happened.

    Nine books, ~5,740 rows. The honest finding may well be "not matured yet":
    the 21-session horizon on a book sealed 2026-09-02 resolves in October. A
    grade computed on five sessions of a twenty-one-session thesis is a grade of
    the noise, and this job says so rather than producing a number.
    """
    books_dir = TERMINAL / "state" / "predictions"
    files = sorted(books_dir.glob("*.json")) if books_dir.exists() else []
    if not files:
        return {"verdict": "CANNOT DETERMINE", "cells_looked_at": 0,
                "question": "how did the sealed books do?",
                "headline": f"no sealed books under {books_dir}"}
    books, rows_total, holdings_total = [], 0, 0
    for f in files:
        try:
            b = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            books.append({"file": f.name, "unreadable": str(exc)[:120]})
            continue
        preds = b.get("predictions") or []
        ports = b.get("portfolios") or {}
        held = sum(len(p.get("holdings") or []) for p in ports.values())
        rows_total += len(preds)
        holdings_total += held
        books.append({
            "file": f.name, "day": b.get("day"), "schema": b.get("schema"),
            "sealed_at_utc": b.get("sealed_at_utc"),
            "content_sha256": str(b.get("content_sha256"))[:16],
            "n_predictions": len(preds), "n_claims": b.get("claims_made"),
            "books": {k: len(v.get("holdings") or []) for k, v in ports.items()},
            "n_holdings": held,
            "carries_contract": all("contract" in v for v in ports.values()) if ports else None,
        })
    days = sorted({b.get("day") for b in books if b.get("day")})
    today = datetime.now(timezone.utc).date()
    matured = []
    for d in days:
        try:
            elapsed = _sessions_between(datetime.fromisoformat(d).date(), today)
        except ValueError:
            continue
        matured.append({"day": d, "sessions_elapsed": elapsed,
                        "matured_1m_21s": elapsed >= 21, "matured_5s": elapsed >= 5})
    n_ready = sum(1 for m in matured if m["matured_1m_21s"])
    return {
        "question": "what did the sealed books predict, and has any of it matured?",
        "family_id": "night-lab-L8-sealed-book-grade",
        "cells_looked_at": len(books),
        "n_books": len(books), "n_prediction_rows": rows_total,
        "n_holdings_rows": holdings_total,
        "books": books, "maturity": matured,
        "headline": (f"{len(books)} sealed books, {rows_total} prediction rows, "
                     f"{holdings_total} holdings; {n_ready} of {len(matured)} book-days have "
                     f"reached 21 sessions"),
        "verdict": "CANNOT DETERMINE" if n_ready == 0 else "INVENTORY",
        "why": ("a 21-session thesis sealed within the last month has not resolved. Grading it "
                "on five sessions grades the noise and would set a precedent for reading a "
                "book early whenever the number looked good."),
        "schedule": {"grade_when": "21 sessions after each sealed day",
                     "primary_metric": "hit rate and Brier vs the analyst consensus on the "
                                       "same names, per book",
                     "comparator": "IBES consensus target direction on the same name-days"},
    }


def _sessions_between(a, b) -> int:
    from datetime import timedelta
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


# ============================================ L4 reversal by size and by event


REVERSAL_YEARS = list(range(2013, 2025))


def L4_reversal_by_size() -> dict:
    """Murat's LULU question, measured: does a big one-day mover bounce?

    THE THREE THINGS THAT DECIDE THE ANSWER, and each one has flipped a result
    in this repo before:

    1. **Entry convention.** A close-to-close "reversal" on a name that just
       fell 15% is mostly BID-ASK BOUNCE: you cannot buy at the close you
       measured. Everything here enters at the NEXT SESSION'S OPEN and exits at
       a close, which is a fill a person could have taken.
    2. **Size.** "Small companies have more room" is the intuition; the
       measurable version is a size quintile, and it is the split that decides
       whether an effect is a spread artefact.
    3. **The event.** A drop on an earnings print is a different animal from a
       drop on nothing: post-earnings drift is CONTINUATION. The 8-K item 2.02
       tape gives the split, on the subset of filings that carry a permno.

    Costs are charged at 10/25/50 bps per side and the receipt names the rate --
    quoting a count without the cost rate is how a reversal lane gets published.
    """
    from learner import inference

    px = _load_daily(REVERSAL_YEARS)
    if px is None or px.empty:
        return {"verdict": "CANNOT DETERMINE", "cells_looked_at": 0,
                "question": "does a big one-day move reverse?",
                "headline": "no CRSP daily files found"}
    ev = _event_days()
    rows = []
    cells = 0
    for side in ("down", "up"):
        for quint in (1, 2, 3, 4, 5):
            for event in (True, False):
                cells += 1
    per_cell: dict[str, list[float]] = {}
    detail = []
    for year in REVERSAL_YEARS:
        d = px[px["year"] == year]
        if d.empty:
            continue
        detail.extend(_reversal_year(d, ev))
    if not detail:
        return {"verdict": "CANNOT DETERMINE", "cells_looked_at": cells,
                "question": "does a big one-day move reverse?",
                "headline": "no qualifying mover-days after filters"}
    ddf = pd.DataFrame(detail)
    out_cells = {}
    # ONE OBSERVATION PER DAY, NOT PER NAME-DAY (CANON 58: n_effective counts
    # DATE BLOCKS). Every name that moved on the same session shares that
    # session's market, so 259,234 name-days is not 259,234 independent draws
    # and a t computed on them is inflated by roughly sqrt(names per day) -- the
    # first cut of this job printed t = -65 on exactly that error. The cell is
    # collapsed to an equal-weighted portfolio return PER DAY, which is both the
    # honest unit and the thing a book would actually have earned.
    for (side, quint, event), g in ddf.groupby(["side", "size_quintile", "event"]):
        daily1 = g.groupby("day")["fwd_open_to_close_1"].mean()
        daily5 = g.groupby("day")["fwd_open_to_close_5"].mean()
        names_per_day = g.groupby("day").size()
        for bps in (10, 25, 50):
            net = daily1 - 2 * bps / 10000.0
            net5 = daily5 - 2 * bps / 10000.0
            key = f"{side}|q{quint}|{'event' if event else 'no_event'}|{bps}bps"
            out_cells[key] = {
                "n_name_days": int(len(g)),
                "n_days": int(len(daily1)),
                "median_names_per_day": float(names_per_day.median()),
                "mean_next_session_pct": round(float(net.mean()) * 100, 4),
                "t_next_session": _t(net),
                "mean_5_session_pct": round(float(net5.mean()) * 100, 4),
                "t_5_session_naive": _t(net5),
                # THE 5-SESSION SERIES IS OVERLAPPING: a 5-day forward return
                # sampled every day is the same week counted five times, and its
                # naive t is inflated by roughly sqrt(5). Two corrections, both
                # printed, because they fail differently: Newey-West keeps every
                # observation and models the dependence; the non-overlapping
                # block throws four fifths of the sample away and makes the real
                # n visible. A cell that survives only the naive t has not
                # survived anything.
                "t_5_session_hac5": _hac(net5, 5),
                "t_5_session_nonoverlapping": _t(net5.dropna().iloc[::5]),
                "n_days_nonoverlapping": int(len(net5.dropna().iloc[::5])),
            }
            per_cell[key] = net.dropna().tolist()
    best = max(out_cells.items(), key=lambda kv: (kv[1]["t_next_session"] or -99))
    best5 = max(out_cells.items(), key=lambda kv: (kv[1]["t_5_session_hac5"] or -99))
    fam = {k: v for k, v in per_cell.items() if len(v) >= 30}
    dsr = inference.deflated_sharpe(per_cell[best[0]], n_trials=len(out_cells))
    return {
        "question": ("after a top/bottom-decile one-day move, does the next session reverse -- "
                     "by size quintile and by earnings event, at real costs?"),
        "family_id": "night-lab-L4-reversal",
        "cells_looked_at": len(out_cells),
        "entry_convention": "next session OPEN -> that session's CLOSE (and +5 sessions)",
        "cost_convention": "bps per SIDE, charged twice per round trip",
        "event_source": (f"EDGAR 8-K item 2.02 on the FILING date; {ev['n_mapped']:,} of "
                         f"{ev.get('n_item_202', 0):,} item-2.02 filings mapped to a permno "
                         f"({ev.get('n_by_permno_column', 0):,} from the tape's own column, "
                         f"{ev.get('n_by_ticker_in_window', 0):,} by ticker inside its CRSP "
                         f"validity window), out of {ev['n_total']:,} filings of all types"),
        "n_mover_days": int(len(ddf)),
        "cells": out_cells,
        "unit": "one equal-weighted portfolio return per SESSION, never per name-day",
        "best_cell_next_session": best[0],
        "best_cell_stats": best[1],
        "best_cell_5_session": best5[0],
        "best_cell_5_session_stats": best5[1],
        "deflated_sharpe": dsr,
        "headline": (f"{len(ddf):,} mover-days over {len(REVERSAL_YEARS)} years; best of "
                     f"{len(out_cells)} cells is {best[0]} at {best[1]['mean_next_session_pct']:+.3f}%"
                     f" (t {best[1]['t_next_session']}), DSR {dsr.get('dsr')}"),
        "verdict": ("NOVEL" if dsr.get("dsr", 0) >= 0.95 else "NOISE"),
        "reading": ("DSR is the number to read, not the best cell's t: the best of many cells is "
                    "the maximum of many draws, and at this many cells a zero-edge search is "
                    "expected to produce a t above 2."),
    }


def _hac(x, lag: int) -> float | None:
    from learner.evaluate import hac_t
    s = pd.Series(x).dropna().astype(float)
    if len(s) < 10:
        return None
    v = hac_t(s, lag)
    return None if v is None else round(float(v), 3)


def _t(x) -> float | None:
    a = np.asarray(x, dtype="float64")
    a = a[np.isfinite(a)]
    if a.size < 8 or a.std(ddof=1) == 0:
        return None
    return round(float(a.mean() / (a.std(ddof=1) / math.sqrt(a.size))), 3)


def _load_daily(years) -> pd.DataFrame | None:
    frames = []
    for y in years:
        f = ROOT / "backend" / "data" / "optimus" / "wrds" / f"crsp_dsf_{y}.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f, columns=["permno", "date", "prc", "ret", "openprc",
                                        "vol", "shrout"])
        d["year"] = y
        frames.append(d)
    if not frames:
        return None
    px = pd.concat(frames, ignore_index=True)
    px["date"] = pd.to_datetime(px["date"])
    px["prc"] = px["prc"].abs()
    return px


def _event_days() -> dict:
    """(permno, filing date) for every 8-K carrying item 2.02 -- an EARNINGS print.

    THE TAPE'S OWN `permno` COLUMN IS 8% POPULATED (23,319 of 293,619), which is
    not a coverage problem to be noted and moved past: an event split computed on
    8% of filings puts 92% of real earnings days into the "no event" bucket and
    then reports the difference between the two buckets. So the ticker is mapped
    through CRSP `stocknames` WITHIN ITS VALIDITY WINDOW -- a ticker is not a
    permanent identifier and matching it without dates is how a delisted symbol's
    events land on its reissued namesake.
    """
    f = ROOT / "backend" / "data" / "optimus" / "edgar_8k" / "eightk_items.parquet"
    if not f.exists():
        return {"pairs": set(), "n_mapped": 0, "n_total": 0, "n_by_ticker": 0}
    d = pd.read_parquet(f, columns=["permno", "ticker", "filing_date", "items_joined"])
    n_total = len(d)
    d = d[d["items_joined"].astype(str).str.contains("2.02", regex=False)].copy()
    d["filing_date"] = pd.to_datetime(d["filing_date"]).dt.normalize()
    direct = d[d["permno"].notna()]
    pairs = set(zip(direct["permno"].astype("int64"), direct["filing_date"]))
    n_direct = len(direct)

    n_ticker = 0
    names_f = ROOT / "backend" / "data" / "optimus" / "wrds" / "bulk" / "crsp__stocknames.parquet"
    need = d[d["permno"].isna() & d["ticker"].notna()]
    if names_f.exists() and len(need):
        nm = pd.read_parquet(names_f, columns=["permno", "ticker", "namedt", "nameenddt"])
        nm = nm[nm["ticker"].notna()].copy()
        nm["namedt"] = pd.to_datetime(nm["namedt"], errors="coerce")
        nm["nameenddt"] = pd.to_datetime(nm["nameenddt"], errors="coerce")
        nm = nm.dropna(subset=["namedt", "nameenddt"])
        need = need.assign(ticker=need["ticker"].astype(str).str.upper().str.strip())
        nm["ticker"] = nm["ticker"].astype(str).str.upper().str.strip()
        j = need.merge(nm, on="ticker", how="inner", suffixes=("", "_nm"))
        j = j[(j["filing_date"] >= j["namedt"]) & (j["filing_date"] <= j["nameenddt"])]
        n_ticker = int(len(j))
        pairs |= set(zip(j["permno_nm"].astype("int64"), j["filing_date"]))
    return {"pairs": pairs, "n_mapped": n_direct + n_ticker, "n_total": int(n_total),
            "n_by_permno_column": n_direct, "n_by_ticker_in_window": n_ticker,
            "n_item_202": int(len(d))}


def _reversal_year(d: pd.DataFrame, ev: dict) -> list[dict]:
    """Mover-days in one year, with the NEXT session's open->close outcome."""
    d = d.sort_values(["permno", "date"]).copy()
    # $5 floor and a liquidity floor: a reversal measured on sub-$5 names is a
    # measurement of the tick, and the toxic-band lesson (S39) is that a price
    # floor is the difference between +84% and -31.6%.
    d = d[(d["prc"] >= 5.0) & (d["vol"].fillna(0) > 0)]
    if d.empty:
        return []
    g = d.groupby("permno", sort=False)
    d["next_open"] = g["openprc"].shift(-1)
    d["next_close"] = g["prc"].shift(-1)
    d["close_5"] = g["prc"].shift(-5)
    d["mktcap"] = d["prc"] * d["shrout"].fillna(0)
    out = []
    for day, dd in d.groupby("date"):
        r = dd["ret"].astype("float64")
        if r.notna().sum() < 200:
            continue
        lo, hi = r.quantile(0.10), r.quantile(0.90)
        q = pd.qcut(dd["mktcap"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
        for side, mask in (("down", r <= lo), ("up", r >= hi)):
            sel = dd[mask & dd["next_open"].notna() & dd["next_close"].notna()]
            if sel.empty:
                continue
            quints = q[mask & dd["next_open"].notna() & dd["next_close"].notna()]
            f1 = (sel["next_close"] / sel["next_open"] - 1.0).astype("float64")
            f5 = (sel["close_5"] / sel["next_open"] - 1.0).astype("float64")
            for (idx, row), quint, a, b in zip(sel.iterrows(), quints, f1, f5):
                if not np.isfinite(a):
                    continue
                key = (int(row["permno"]), pd.Timestamp(day).normalize())
                out.append({"side": side, "size_quintile": int(quint) if quint == quint else 3,
                            "day": pd.Timestamp(day).normalize(),
                            "event": key in ev["pairs"],
                            "fwd_open_to_close_1": float(a),
                            "fwd_open_to_close_5": float(b) if np.isfinite(b) else np.nan})
    return out


# ============================================ L1 the learner on the clean panel


def L1_learner_clean_panel() -> dict:
    """The learner, re-run on the B1 clean panel, with the inference it owes.

    Every arm x horizon x cost cell is a CELL, and the family is the whole grid.
    What changes tonight is not the models -- it is that the leaderboard is
    reported with a Deflated Sharpe (how many cells were opened), a Hansen SPA
    (is the best arm better than the best alternative, not just than noise) and
    a PBO (would the ranking have survived a different split).
    """
    from learner import dataset, evaluate, inference, models

    df = dataset.load()
    feature_cols = dataset.feature_columns()
    test_years = [y for y in range(2017, 2025)]
    # `arm` is the TARGET SHAPE, not the model: "raw" predicts excess directly,
    # "residual" predicts the residual over the band prior and adds the prior
    # back. Both arrive on the same scale (`models.arm_reconstruct`), so they
    # are two cells of one family and not two experiments.
    arms = ["ridge", "lgbm"]
    targets = ["raw", "residual"]
    horizons = [1, 3, 6, 12]
    costs = [10, 25]
    series: dict[str, pd.Series] = {}
    cells: dict[str, dict] = {}
    for kind in arms:
      for target in targets:
        for h in horizons:
            preds = []
            for year, tr, te in dataset.walk_forward_splits(df, test_years, h):
                try:
                    pred, meta = models.fit_predict(kind, target, df.loc[tr], df.loc[te],
                                                    feature_cols, h)
                except Exception as exc:                              # noqa: BLE001
                    cells[f"{kind}|{target}|{h}m|fit"] = {"error": f"{type(exc).__name__}: {exc}"}
                    continue
                p = pd.Series(models.arm_reconstruct(pred, df.loc[te], target, h), index=te)
                preds.append(p)
            if not preds:
                continue
            col = f"pred_{kind}_{target}_{h}m"
            df[col] = np.nan
            df.loc[pd.concat(preds).index, col] = pd.concat(preds).values
            for bps in costs:
                try:
                    bk = evaluate.book(df, col, k=50, weight="vw", cost_bps=bps,
                                       ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                                       return_series=True)
                except Exception as exc:                              # noqa: BLE001
                    cells[f"{kind}|{target}|{h}m|{bps}bps"] = {
                        "error": f"{type(exc).__name__}: {exc}"}
                    continue
                key = f"{kind}|{target}|{h}m|{bps}bps"
                s = (bk.get("_series") or {})
                net = pd.Series(s.get("net") or [], dtype="float64")
                mkt = pd.Series(s.get("market") or [], dtype="float64")
                cells[key] = {k: v for k, v in bk.items() if not k.startswith("_")}
                if len(net) and len(net) == len(mkt):
                    series[key] = (net - mkt).reset_index(drop=True)
    if not series:
        return {"verdict": "CANNOT DETERMINE", "cells_looked_at": len(cells),
                "question": "does the learner beat the market on the clean panel?",
                "headline": "no arm produced a usable paired series", "cells": cells}
    lengths = {len(v) for v in series.values()}
    n = min(lengths)
    fam = {k: v.iloc[:n].tolist() for k, v in series.items()}
    best = max(fam, key=lambda k: float(np.mean(fam[k])))
    rep = inference.full_report(fam[best], family=fam, paired_excess=fam,
                                n_trials=len(cells) or len(fam), n_boot=500, seed=17)
    return {
        "question": "does any learner arm beat the market on the clean panel, after costs?",
        "family_id": "night-lab-L1-learner-clean-panel",
        "cells_looked_at": len(cells),
        "arms": sorted(fam),
        "best_cell": best,
        "best_mean_monthly_excess_pct": round(float(np.mean(fam[best])) * 100, 4),
        "cells": cells,
        "inference": rep,
        "dsr": rep.get("deflated_sharpe", {}).get("dsr"),
        "headline": (f"best of {len(cells)} cells is {best} at "
                     f"{np.mean(fam[best]) * 100:+.3f}%/month paired excess; "
                     f"DSR {rep.get('deflated_sharpe', {}).get('dsr')}, "
                     f"SPA p {rep.get('spa', {}).get('p_spa_consistent')}, "
                     f"PBO {rep.get('pbo', {}).get('pbo')}"),
        "verdict": ("NOVEL" if (rep.get("deflated_sharpe", {}).get("dsr", 0) >= 0.95
                                and rep.get("spa", {}).get("p_spa_consistent", 1) <= 0.05)
                    else "NOISE"),
        "deferred": ("the >= 256-seed MODEL null (refit on shuffled targets) is not run here: "
                     "at ~8 walk-forward folds per cell it is days of CPU for lgbm. The "
                     "family-level tests above are what one night buys; the model null is the "
                     "next job, and its cost is stated rather than skipped in silence."),
    }


JOBS = {
    "L11_belief_inventory": L11_belief_inventory,
    "L12_mirror_reconcile": L12_mirror_reconcile,
    "L13_corpus_railway_design": L13_corpus_railway_design,
    "L8_grade_sealed_books": L8_grade_sealed_books,
    "L4_reversal_by_size": L4_reversal_by_size,
    "L1_learner_clean_panel": L1_learner_clean_panel,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", choices=sorted(JOBS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--run", type=int, default=1)
    args = ap.parse_args(argv)
    payload: dict
    try:
        payload = JOBS[args.job]()
    except Exception:                                                  # noqa: BLE001
        import traceback
        payload = {"verdict": "FAILED", "headline": "raised -- traceback IS the receipt",
                   "traceback": traceback.format_exc()[-6000:]}
    payload.setdefault("licence", "PRODUCT_EXPERIMENT")
    payload["job"] = args.job
    payload["run"] = args.run
    payload["written_utc"] = _now()
    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"{args.job}: {payload.get('verdict')} -- {str(payload.get('headline'))[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
