"""BOOK F'S FROZEN INPUT -- the seasonality ranking the execution repo trades.

WHAT SHIPS, AND WHAT NEVER SHIPS
================================
`scripts/seal_authority.py` in `aegis-alpha-terminal` established the pattern and
this job copies it exactly: **the research side produces a frozen JSON that the
execution side installs and hash-verifies; the SEARCH itself never crosses the
boundary.** Nothing in the terminal repo reads CRSP, and nothing in it should
ever try to recompute a twenty-year seasonality average at 09:31 ET. It reads a
file, checks the file against its own `content_sha256`, and trades the list --
or it declines, loudly, with the reason.

WHY THE JKP COLUMN CANNOT BE USED FOR 2026
==========================================
`backend/services/book_signals.seasonality_score` reads JKP's own
`seas_11_15an` / `seas_16_20an`, stamped `eom`. That panel ENDS 2024-12, so for
a month in 2026 the column does not exist. It does not have to: the column IS a
same-calendar-month average of the name's own returns at year lags 11-15 and
16-20, and every year those lags need for a 2026 month lies INSIDE the CRSP
panel we hold (2026-10 needs 2006-10..2015-10; 2026-09 needs 2006-09..2015-09).
So this job computes the two columns from the monthly panel's own history and
then hands them to the SAME `seasonality_score` the replay used -- the z-score,
the both-columns-required rule and the tercile cut are not re-implemented here.

THE CONSTRUCTION IS PRINTED, AND SO ARE ITS DEVIATIONS
======================================================
Book C's 2026-09-13 lesson (a 60-month registration warmed at 24 months, with a
receipt that said otherwise) is why `construction` below carries every frozen
parameter AND a `deviations_from_the_replay` list. Three deviations exist and
none of them is silent:

  1. the universe is the EXECUTION repo's current tradable universe, not the
     CRSP eligible band -- the book has to trade names Alpaca lists;
  2. the two columns are DERIVED here rather than read from JKP, because the
     panel ends 2024-12 (above);
  3. the mandate that will run it holds k=10 (hack3's frozen construction),
     which is a PREFIX of this file's registered k=30 ranking.

A reader who does not know (3) would compare a k=10 live book against a k=30
receipt and call the difference alpha.

    python -m scripts.night_factory_jobs F_seasonality_export --smoke
    F_EXPORT_MONTHS=2026-09,2026-10 python -m scripts.night_factory_jobs F_seasonality_export

TIME: one `load_monthly_panel` over the ten lag years (~10 CRSP daily files).
Measured on the dev machine at roughly 2-4 minutes; no LLM, no network.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger("f_seasonality_export")

JOB = "F_seasonality_export"
ENGINE = "seasonality_11_20_v0"
ENGINE_KEY = "F"
REGISTRATION = "TRIAL-DRAFT-F-calendar-seasonality-v0 (UNSIGNED)"
FAMILY = "NIGHT_JOB_BOOKS_2026_09_13"
LICENCE = "PRODUCT_EXPERIMENT"

#: Frozen by TRIAL-DRAFT-F section 6 and NOT re-decided here.
K = 30
TERCILE = 2.0 / 3.0
MIN_PRICE_USD = 5.0

#: The SECONDARY floor, chosen deliberately over the $3M primary: the roadmap's
#: third read (§11c) put F in an account because it is the only book of the four
#: that is positive AT $10M in the current era (+0.4328%/month, t 3.1178, 419
#: blocks). A live book that screened at $3M would not be the cell that earned
#: the deploy.
FLOOR_USD = 10_000_000.0

#: The two same-calendar-month windows, in YEARS back from the month the book
#: EARNS. Heston-Sadka's lag structure, mechanically disjoint from 12-1 momentum.
LAG_WINDOWS = {"seas_11_15an": (11, 12, 13, 14, 15),
               "seas_16_20an": (16, 17, 18, 19, 20)}

#: Every year of a window must be observed. There is no "3 of 5" here on
#: purpose: a partial average is a DIFFERENT characteristic for a young name
#: than for an old one, and the age of a listing is exactly what a twenty-year
#: lag selects on (`book_signals.seasonality_score`'s own docstring). Names that
#: cannot fill both windows are reported as a coverage fact, not imputed.
REQUIRED_YEARS_PER_WINDOW = 5

#: CRSP share codes for ordinary common stock. The live universe is an Alpaca
#: asset list and carries ETFs, ADRs and trusts; the replay's band was CRSP
#: names. Restricting here keeps the live book the same KIND of object the
#: receipt measured.
SHARE_CODES = (10, 11)

#: The cell of the replay receipt this engine is the live expression of.
RECEIPT_RELPATH = ("night_factory_2026-09-13/B_books_efg_replay_run01.json")
RECEIPT_CELL = {
    "floor_usd": 10_000_000.0,
    "n_blocks": 419,
    "mean_book_net_monthly": 0.008996,
    "mean_twin_net_monthly": 0.004668,
    "mean_excess_net_monthly": 0.004328,
    "nw_lag2_t": 3.1178,
    "p_two_sided": 0.001822,
    "cost_curve": "flat_25bps_pending_5c",
    "by_era_2017_2024": {"mean_excess_net_monthly": 0.007637, "nw_lag2_t": 2.2972},
    "verdict": "CONDITIONAL",
}

DEVIATIONS = [
    "universe: the EXECUTION repo's current tradable universe (Alpaca assets at "
    "the $10M median-dollar-volume floor, ETFs excluded, price >= $5), not the "
    "replay's CRSP eligible band. A book has to trade names the venue lists.",
    "columns: seas_11_15an / seas_16_20an are DERIVED from the CRSP monthly "
    "panel's own same-calendar-month returns at the registered year lags, "
    "because JKP's panel ends 2024-12 and cannot stamp a 2026 month. The "
    "combination, the both-columns rule and the tercile cut are the registered "
    "code path (`book_signals.seasonality_score`), not a second implementation.",
    "k: this file ranks and cuts at the registered k=30. The mandate that runs "
    "it (hack3) holds k=10 x 8.3%, which is a PREFIX of this ranking and not a "
    "different selection rule -- but it is not the k the receipt measured.",
]


class ExportRefused(RuntimeError):
    """This engine file cannot be produced honestly, and says which input failed.

    Raised rather than returned as an empty ranking: an engine file with no rows
    and one with a missing universe are the same object to a consumer, and the
    consumer is an order path.
    """


# --------------------------------------------------------------------------
# paths


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def engines_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "engines"


def terminal_repo() -> Path:
    """The execution repo. `AEGIS_TERMINAL_REPO` overrides the sibling default."""
    env = os.getenv("AEGIS_TERMINAL_REPO")
    if env:
        return Path(env)
    return repo_root().parent / "aegis-alpha-terminal"


def universe_path(explicit: str | Path | None = None) -> Path:
    """The newest stored tradable universe in the execution repo.

    A universe is not derived here and not guessed: the execution repo builds it
    from the venue's own asset list (`alpha/universe.py`), and this job reads
    whatever that build last wrote. A missing file is a REFUSAL -- a book cannot
    be ranked over a universe nobody has stated.
    """
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise ExportRefused(f"universe file {p} does not exist")
        return p
    d = terminal_repo() / "state" / "universe"
    cands = sorted(d.glob("HIGH_DISPERSION_US_v1_*.json"))
    if not cands:
        raise ExportRefused(
            f"no stored tradable universe under {d}. The execution repo builds it "
            f"(`alpha.universe.build`/`save`); this job does not invent one, "
            f"because a universe chosen here would not be the universe the loop "
            f"can actually trade.")
    return cands[-1]


# --------------------------------------------------------------------------
# the inputs


def load_universe(path: str | Path | None = None) -> dict:
    """The live tradable band: symbols at the floor, ETFs and cheap names out."""
    p = universe_path(path)
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    members = d.get("members") or []
    if not members:
        raise ExportRefused(f"{p} carries no members")
    kept, dropped = {}, {"etf_like": 0, "below_floor": 0, "below_price": 0}
    for m in members:
        sym = str(m.get("symbol") or "").strip().upper()
        if not sym:
            continue
        if m.get("etf_like"):
            dropped["etf_like"] += 1
            continue
        dv = float(m.get("median_dollar_volume") or 0.0)
        if dv < FLOOR_USD:
            dropped["below_floor"] += 1
            continue
        px = m.get("price")
        if px is not None and float(px) < MIN_PRICE_USD:
            dropped["below_price"] += 1
            continue
        kept[sym] = {"median_dollar_volume": dv, "price": px,
                     "exchange": m.get("exchange")}
    if not kept:
        raise ExportRefused(
            f"{p} has {len(members)} members and none survived the floor "
            f"(${FLOOR_USD:,.0f} median dollar volume, price >= ${MIN_PRICE_USD:g}, "
            f"ETFs excluded)")
    return {"path": str(p), "asof": d.get("asof"), "n_members": len(members),
            "n_kept": len(kept), "dropped": dropped, "symbols": kept,
            "screen": d.get("screen")}


def dsenames_path() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "wrds" / "bulk" / "crsp__dsenames.parquet"


def ticker_to_permno(*, path: Path | None = None) -> dict:
    """{TICKER: permno} by the name row that ended LAST, common stock only.

    CRSP recycles tickers, so "the permno for AAPL" is only well defined once a
    rule picks between the histories that ever carried it. The rule here is the
    LAST-KNOWN ticker -- the name row with the greatest `nameendt` -- because the
    universe being mapped is TODAY's, and the name that carried the ticker most
    recently in CRSP is the one today's ticker most likely continues. The
    alternative (first match) would map a live symbol onto a 1994 company.

    Names outside `SHARE_CODES` are dropped before the contest, so a delisted
    trust cannot win a ticker away from the common stock that now carries it.
    """
    import pandas as pd

    p = Path(path) if path is not None else dsenames_path()
    if not p.is_file():
        raise ExportRefused(
            f"no CRSP name table at {p}; a symbol cannot be mapped to a permno "
            f"without one and this job does not guess the join")
    nm = pd.read_parquet(p, columns=["permno", "ticker", "nameendt", "shrcd"])
    nm = nm.dropna(subset=["permno", "ticker"])
    nm = nm[nm["shrcd"].isin(SHARE_CODES)]
    nm["ticker"] = nm["ticker"].astype(str).str.strip().str.upper()
    nm = nm[nm["ticker"] != ""]
    nm["nameendt"] = pd.to_datetime(nm["nameendt"], errors="coerce")
    nm = nm.sort_values(["ticker", "nameendt"], kind="mergesort")
    nm = nm.drop_duplicates(subset=["ticker"], keep="last")
    return {t: int(p_) for t, p_ in zip(nm["ticker"], nm["permno"])}


def lag_years(month: str) -> tuple[int, int]:
    """(first, last) calendar YEAR the two windows of `month` need."""
    y = int(str(month)[:4])
    lags = [x for w in LAG_WINDOWS.values() for x in w]
    return y - max(lags), y - min(lags)


def seasonality_frame(panel, month: str):
    """(frame, per-name year counts) for `month`: one row per permno, two columns.

    `panel` is `night_first_books_replay.load_monthly_panel`'s output -- per
    (permno, ym) monthly return. Each column is the plain mean of the name's own
    return in the SAME calendar month at the window's year lags, which is what
    JKP's `seas_*an` columns are; nothing is winsorised, demeaned or shifted,
    because the cross-sectional z the selector applies is the only normalisation
    the registration declares.
    """
    import pandas as pd

    per = pd.Period(month, freq="M")
    cols, counts = {}, {}
    for name, lags in LAG_WINDOWS.items():
        wanted = {per - 12 * L for L in lags}
        sub = panel[panel["ym"].isin(wanted)]
        g = sub.groupby("permno")["ret_m"].agg(["mean", "size"])
        g = g[g["size"] >= REQUIRED_YEARS_PER_WINDOW]
        cols[name] = g["mean"]
        counts[name] = g["size"]
    frame = pd.concat(cols, axis=1).dropna()
    frame = frame.reset_index().rename(columns={"index": "permno"})
    frame["permno"] = frame["permno"].astype("int64")
    return frame, {k: int(v.size) for k, v in counts.items()}


# --------------------------------------------------------------------------
# the receipt


def content_sha256(payload: dict) -> str:
    """Byte-identical to `scripts.prediction_book._sha` in the execution repo.

    Deliberately re-written rather than imported: the two repositories share no
    code and never will. `tests_smoke_engine_seasonality` in the terminal repo
    pins its own copy against a fixture written by THIS function, so the two
    cannot drift in silence -- which is the only guarantee the hash is worth.
    """
    body = dict(payload)
    body.pop("content_sha256", None)
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")).hexdigest()


def build_month(panel, universe: dict, tickers: dict, month: str,
                *, panel_last_month: str, k: int = K) -> dict:
    """The engine payload for one calendar month. Pure over its inputs."""
    from backend.services import book_signals as BS

    syms = universe["symbols"]
    mapped = {s: tickers[s] for s in syms if s in tickers}
    # One permno may be reachable from only one ticker here (the map is
    # ticker-keyed and deduplicated), but a defensive inverse keeps the receipt
    # honest if that ever stops being true.
    by_permno: dict[int, str] = {}
    for s, pn in mapped.items():
        by_permno.setdefault(int(pn), s)

    frame, window_counts = seasonality_frame(panel, month)
    frame = frame[frame["permno"].isin(set(by_permno))]

    covered = int(len(frame))
    if covered < BS.MIN_CHARACTERISTIC_NAMES:
        raise ExportRefused(
            f"{month}: only {covered} live name(s) carry BOTH seasonality windows "
            f"in full ({REQUIRED_YEARS_PER_WINDOW} years each); a cross-sectional "
            f"tercile over fewer than {BS.MIN_CHARACTERISTIC_NAMES} is a cut of the "
            f"survivors, not of the market. This is a coverage fact -- the panel "
            f"ends {panel_last_month} and a name needs ~20 years of tape -- and it "
            f"is a REFUSAL, not an empty book.")

    # TWO CALLS TO THE SAME FUNCTION, never a second implementation of the z.
    # `tercile=0.0` keeps every covered name (the 0-quantile is the minimum), so
    # the receipt can print the whole cross-section AND the registered cut
    # without this file ever computing a quantile of its own.
    all_scores = BS.seasonality_score(frame, side="top", tercile=0.0)
    top_scores = BS.seasonality_score(frame, side="top", tercile=TERCILE)

    order = sorted(all_scores.items(), key=lambda kv: (-kv[1], by_permno[kv[0]]))
    rows = []
    for i, (pn, score) in enumerate(order, start=1):
        rows.append({"symbol": by_permno[pn], "permno": int(pn),
                     "score": round(float(score), 6), "rank": i,
                     "tercile": "top" if pn in top_scores else "below"})
    selected = [r["symbol"] for r in rows if r["tercile"] == "top"][:int(k)]

    coverage = {
        "universe_members": universe["n_members"],
        "universe_after_floor": universe["n_kept"],
        "universe_dropped": universe["dropped"],
        "mapped_to_permno": len(mapped),
        "mapped_share_of_universe": round(len(mapped) / max(1, universe["n_kept"]), 4),
        "unmapped_symbols": sorted(set(syms) - set(mapped))[:40],
        "unmapped_count": len(set(syms) - set(mapped)),
        "carrying_both_windows": covered,
        "carrying_both_windows_share_of_mapped": round(covered / max(1, len(mapped)), 4),
        "per_window_names_in_panel": window_counts,
        "top_tercile_names": len(top_scores),
        "selected": len(selected),
        "mapping": ("CRSP dsenames, last-known ticker (greatest nameendt), share "
                    f"codes {list(SHARE_CODES)}"),
    }

    payload = {
        "engine": ENGINE,
        "engine_key": ENGINE_KEY,
        "registration": REGISTRATION,
        "family": FAMILY,
        "licence": LICENCE,
        "job": JOB,
        "month": str(month),
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "panel_last_month": panel_last_month,
        "receipt": RECEIPT_RELPATH,
        "receipt_cell": RECEIPT_CELL,
        "construction": {
            "k": int(k),
            "tercile": TERCILE,
            "floor_usd": FLOOR_USD,
            "min_price_usd": MIN_PRICE_USD,
            "columns": sorted(LAG_WINDOWS),
            "both_columns_required": True,
            "lag_years": {c: list(v) for c, v in LAG_WINDOWS.items()},
            "required_years_per_window": REQUIRED_YEARS_PER_WINDOW,
            "share_codes": list(SHARE_CODES),
            "cut": "top tercile of the equal-weight mean of the within-month z-scores",
            "hold": "one month, monthly rebalance",
            "selector": "backend.services.book_signals.seasonality_score",
            "deviations_from_the_replay": DEVIATIONS,
        },
        "universe_source": {"path": universe["path"], "asof": universe["asof"],
                            "screen": universe["screen"]},
        "coverage": coverage,
        "selected": selected,
        "rows": rows,
    }
    payload["content_sha256"] = content_sha256(payload)
    return payload


def default_months(today: date | None = None) -> list[str]:
    """This calendar month and the next one, DERIVED from `today`.

    Never a literal: a fixture or a default that names a month is correct until
    that month passes (CLAUDE.md, the expiry-fixture lesson). `F_EXPORT_MONTHS`
    overrides with a comma-separated list.
    """
    env = os.getenv("F_EXPORT_MONTHS")
    if env:
        return [m.strip() for m in env.split(",") if m.strip()]
    t = today or date.today()
    nxt = date(t.year + (t.month == 12), (t.month % 12) + 1, 1)
    return [f"{t.year:04d}-{t.month:02d}", f"{nxt.year:04d}-{nxt.month:02d}"]


def F_seasonality_export(*, smoke: bool = False, months=None,      # noqa: N802
                         universe_file=None, out_dir=None) -> dict:
    """Write one frozen engine file per requested month. Returns the receipt."""
    from scripts.night_first_books_replay import load_monthly_panel

    months = list(months) if months else default_months()
    if smoke:
        months = months[:1]
    lo = min(lag_years(m)[0] for m in months)
    hi = max(lag_years(m)[1] for m in months)

    universe = load_universe(universe_file)
    tickers = ticker_to_permno()
    logger.info("F export: %s, universe %d names, %d tickers mapped in CRSP",
                months, universe["n_kept"], len(tickers))
    panel = load_monthly_panel(lo, hi)
    panel_last = str(panel["ym"].max())

    d = Path(out_dir) if out_dir else engines_dir()
    d.mkdir(parents=True, exist_ok=True)
    written, cells = [], []
    for m in months:
        payload = build_month(panel, universe, tickers, m, panel_last_month=panel_last)
        out = d / f"F_seasonality_{m}.json"
        out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        written.append(str(out))
        cells.append({"month": m, "sha256": payload["content_sha256"],
                      "coverage": payload["coverage"],
                      "selected": payload["selected"]})

    head = "; ".join(
        f"{c['month']}: {c['coverage']['carrying_both_windows']} covered of "
        f"{c['coverage']['mapped_to_permno']} mapped "
        f"({c['coverage']['mapped_to_permno']}/{c['coverage']['universe_after_floor']} of the band), "
        f"top tercile {c['coverage']['top_tercile_names']}, selected {c['coverage']['selected']}"
        for c in cells)
    return {
        "job": JOB, "engine": ENGINE, "registration": REGISTRATION,
        "licence": LICENCE, "family": FAMILY, "llm_spend_usd": 0.0,
        "lag_years_read": [lo, hi], "panel_last_month": panel_last,
        "universe_source": universe["path"], "universe_asof": universe["asof"],
        "months": months, "files": written, "cells": cells,
        "stage": "signal",
        "headline": head,
        "verdict": ("ENGINE FILE WRITTEN. This is an INPUT, not a read: it carries "
                    "no new evidence about F and changes no verdict. F stands "
                    "CONDITIONAL at +0.4328%/month, t 3.1178, 419 blocks, $10M floor."),
        "family_max_p": None,
    }


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--months", default=None,
                    help="comma-separated YYYY-MM; default is this month and next")
    ap.add_argument("--universe-file", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    r = F_seasonality_export(
        smoke=a.smoke,
        months=[m.strip() for m in a.months.split(",")] if a.months else None,
        universe_file=a.universe_file, out_dir=a.out_dir)
    print(json.dumps({k: v for k, v in r.items() if k != "cells"}, indent=1))
    for c in r["cells"]:
        print(f"\n{c['month']}  sha {c['sha256'][:16]}  "
              f"selected: {', '.join(c['selected'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
