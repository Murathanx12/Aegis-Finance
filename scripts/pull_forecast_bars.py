"""Prices for names we FORECAST on but never priced.

    python -m scripts.pull_forecast_bars

THE EVIDENCE THIS RECOVERS
==========================
`forecast_grader` logs, every run:

    2,911 record(s) are past their resolution date and still unresolved --
    check the price frame covers them

They are not unresolvable in principle. **105 of the 110 stranded tickers are
simply absent from `prices_2025_26/bars.parquet`** -- ETFs (XBI, SMH), REITs
(AVB, DLR), and a long tail of microcaps that a universe screen dropped before
the panel was built. Something forecast on them; nothing ever fetched a price
for them; and each run re-reports the same 2,911 records and keeps the ledger
canary DEGRADED.

That is roughly a fifth of the graded evidence in the building, and §64 is the
argument for bothering: the ledger settled more in one `groupby` than any panel
this month, and it did so on 14,703 rows. Recovering 2,911 more is the cheapest
information available.

WHY A SEPARATE PANEL AND NOT AN APPEND
======================================
`prices_2025_26/bars.parquet` is read by the RANKER, and `sim_run.u_rank`
fingerprints it on size and mtime. Appending would (a) rewrite a file a live
8-hour session is reading, and (b) silently widen the ranker's universe with
names its own eligibility screen had excluded -- a different change, with its
own survivorship argument, that should be made deliberately and not as a side
effect of fixing the grader.

So these land in their own file and only `local_price_fetch` unions it. The
grader needs prices for names the ranker is entitled to ignore.

WHAT THIS CANNOT FIX, AND SAYS SO
=================================
A handful of stranded tickers are not equities at all: `CL=F`, `ES=F`, `ZN=F`,
`GC=F` are futures and `DX-Y.NYB` is the dollar index, in Yahoo's notation. No
equity bar source has them, and `BRK-B` is a hyphen spelling of `BRK.B`.

Those are reported as `PERMANENTLY_UNPRICEABLE` with the reason, and are NOT
voided here. Voiding edits records in a tamper-evident ledger, which is a
decision for Murat, not a side effect of a price pull.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config          # noqa: E402

#: Its own file. See the module note on why this is not an append.
OUT_PARQUET = (Path(_config.OPTIMUS_LEDGER_DIR) / "prices_2025_26"
               / "bars_forecast_only.parquet")

#: Symbols no equity bar source can serve. Named, not silently skipped.
NON_EQUITY_SUFFIXES = ("=F",)
NON_EQUITY_EXACT = ("DX-Y.NYB", "^VIX", "^GSPC", "^TNX")

BATCH = 100
SLEEP_S = 0.4


def stranded_tickers(*, today: date | None = None) -> tuple[list[str], list[str]]:
    """(fetchable, permanently unpriceable) among tickers the grader cannot price."""
    from backend.services import belief_state as B
    from backend.services import paper_books as PB

    today = today or date.today()
    rows = B.read_predictions()
    have = set(PB.load_bars()["symbol"].unique())

    want: set[str] = set()
    for r in rows:
        if r.get("outcome") is not None:
            continue
        ra = r.get("resolves_after")
        if not ra:
            continue
        try:
            if pd.Timestamp(ra).date() >= today:
                continue                     # not due yet; not stranded
        except (ValueError, TypeError):
            continue
        t = str(r.get("ticker") or "").strip()
        if t and t not in have:
            want.add(t)

    dead = sorted(t for t in want
                  if t.endswith(NON_EQUITY_SUFFIXES) or t in NON_EQUITY_EXACT)
    return sorted(want - set(dead)), dead


def _vendor_symbol(t: str) -> str:
    """The ledger's spelling, in the vendor's notation.

    The ledger carries Yahoo-style class shares (`BRK-B`); Alpaca wants a dot
    (`BRK.B`) and rejects the whole request otherwise. Only a trailing single
    letter is rewritten -- plenty of legitimate tickers contain a hyphen and
    blanket-replacing it would invent symbols.
    """
    m = re.fullmatch(r"([A-Z]{1,5})-([A-Z])", t)
    return f"{m.group(1)}.{m.group(2)}" if m else t


def fetch(symbols: list[str], *, start: str, end: str) -> pd.DataFrame:
    """Daily bars from Alpaca, in batches. A symbol with no data is absent."""
    import requests

    # Reuse the resolver that already works rather than inventing a second set
    # of variable names. On 2026-09-21 a run aliased this repo's ALPACA pair
    # onto APCA_* and pre-empted the child's own working credential: 401, no
    # bars, night lost. `data_credential()` states its preference order and
    # REFUSES with the reason, which is the behaviour wanted here too.
    from scripts import night_p6_bars_and_regret as P6
    key, sec, source = P6.data_credential()
    print(f"  credential: {source}", flush=True)

    out = []
    head = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}
    n_batches = (len(symbols) + BATCH - 1) // BATCH
    for i in range(0, len(symbols), BATCH):
        # `vendor -> ledger` so rows come back under the spelling the ledger
        # uses, not the one the vendor wants.
        chunk = {_vendor_symbol(t): t for t in symbols[i:i + BATCH]}
        page = None
        dropped: list[str] = []
        while chunk:
            params = {"symbols": ",".join(sorted(chunk)), "timeframe": "1Day",
                      "start": start, "end": end, "limit": 10000,
                      "adjustment": "all", "feed": "iex"}
            if page:
                params["page_token"] = page
            r = requests.get("https://data.alpaca.markets/v2/stocks/bars",
                             headers=head, params=params, timeout=60)
            if r.status_code == 400:
                # ONE BAD SYMBOL MUST NOT DISCARD THE OTHER 98.
                # The vendor rejects the whole request and names the offender,
                # so drop exactly that one and retry. Without this, `BRK-B`
                # alone cost all 99 names and the run reported "no prices",
                # which is the house failure mode wearing a 400.
                bad = re.search(r"invalid symbol:\s*([^\"}\s,]+)", r.text or "")
                if bad and bad.group(1) in chunk:
                    sym = bad.group(1)
                    dropped.append(chunk.pop(sym))
                    print(f"    dropped {sym}: vendor says invalid symbol "
                          f"({len(chunk)} left in this batch)", flush=True)
                    continue
                print(f"    HTTP 400 on batch {i//BATCH+1}, unparsed: "
                      f"{(r.text or '')[:120]}", flush=True)
                break
            if r.status_code != 200:
                print(f"    HTTP {r.status_code} on batch {i//BATCH+1}: "
                      f"{(r.text or '')[:120]}", flush=True)
                break
            js = r.json()
            for sym, rows in (js.get("bars") or {}).items():
                ledger_sym = chunk.get(sym, sym)
                for b in rows:
                    out.append({"symbol": ledger_sym,
                                "date": pd.Timestamp(b["t"]).tz_localize(None).normalize(),
                                "open": b["o"], "high": b["h"], "low": b["l"],
                                "close": b["c"], "volume": b["v"],
                                "vwap": b.get("vw"), "trades": b.get("n")})
            page = js.get("next_page_token")
            if not page:
                break
            time.sleep(SLEEP_S)
        print(f"  batch {i//BATCH+1}/{n_batches}: {len(out):,} rows so far"
              + (f", {len(dropped)} rejected: {dropped}" if dropped else ""),
              flush=True)
        time.sleep(SLEEP_S)
    return pd.DataFrame(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--out", default=str(OUT_PARQUET))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    fetchable, dead = stranded_tickers()
    print(f"stranded and FETCHABLE   : {len(fetchable)}")
    print(f"permanently unpriceable  : {len(dead)}  {dead}")
    if a.dry_run:
        print(f"\nwould fetch: {', '.join(fetchable[:40])}"
              f"{' ...' if len(fetchable) > 40 else ''}")
        return 0
    if not fetchable:
        print("nothing to fetch")
        return 0

    end = a.end or str(date.today())
    bars = fetch(fetchable, start=a.start, end=end)
    if bars.empty:
        print("REFUSED: the fetch returned nothing. The existing panel is "
              "untouched -- an empty file here would read downstream as 'these "
              "names have no prices', which is the opposite of what happened.")
        return 2

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        bars = pd.concat([pd.read_parquet(out), bars], ignore_index=True)
    bars = bars.drop_duplicates(["symbol", "date"], keep="last").sort_values(
        ["symbol", "date"])
    bars.to_parquet(out, index=False)

    got = set(bars["symbol"].unique())
    missed = sorted(set(fetchable) - got)
    res = {"receipt": "forecast_bars_pull", "licence": "PRODUCT_EXPERIMENT",
           "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "n_requested": len(fetchable), "n_returned": len(got),
           "n_rows": int(len(bars)),
           "first_bar": str(bars["date"].min())[:10],
           "last_bar": str(bars["date"].max())[:10],
           "still_missing": missed,
           "permanently_unpriceable": dead,
           "why_a_separate_file": ("prices_2025_26/bars.parquet is read by the "
                                   "ranker and fingerprinted by sim_run.u_rank; "
                                   "appending would rewrite a file a live "
                                   "session is reading AND silently widen the "
                                   "ranker's universe"),
           "not_voided": ("the permanently-unpriceable records are NOT voided "
                          "here. Voiding edits a tamper-evident ledger and is "
                          "Murat's call, not a side effect of a price pull.")}
    p = out.parent / f"forecast_bars_pull_{date.today()}.json"
    p.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"\n{len(got)} of {len(fetchable)} symbols returned, {len(bars):,} rows, "
          f"{res['first_bar']}..{res['last_bar']}")
    if missed:
        print(f"still missing ({len(missed)}): {', '.join(missed[:20])}")
    print(f"-> {out}\n-> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
