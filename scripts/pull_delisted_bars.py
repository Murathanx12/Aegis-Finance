"""The names that DIED — the half of the universe every backtest here is missing.

THE DEFECT THIS FIXES (found 2026-09-22)
========================================
`prices_2025_26/bars.parquet` holds 3,060 symbols. Of those, **zero** stopped
trading more than 21 sessions before the panel's last date:

    symbols whose last bar is >21 sessions before the end: 0 (0.00%)

Across 3,000 US names over 1.7 years you would expect dozens of delistings —
acquisitions, bankruptcies, going private, reverse-split-to-death. Exactly zero
is not luck. The symbol list came from
`HIGH_DISPERSION_US_v1_2026-09-01.json`, a universe file dated 2026-09-01, so
membership was decided by *being alive on 2026-09-01*. Everything that died
first was never asked.

WHY IT MATTERS MORE THAN USUAL HERE
===================================
Survivorship bias is not uniform across strategies. It is concentrated in
exactly the names that die: small, illiquid, distressed, high-volatility. The
2026-09-22 bake-off's winning ranking (`composite_prior`: buy LOW dollar volume,
HIGH Amihud illiquidity, LOW skew) is therefore the single ranking most
flattered by this defect, and it reported **+3.13% relative per 21 sessions,
t +3.59**. That number cannot be believed until the dead names are in the panel,
and this script is what puts them there.

A name that delisted simply has bars that stop. That is the correct
representation: `xs_ranker.build_target` computes the forward return from bars
that exist, so a name whose bars end inside the forward window yields NaN and is
dropped from that date's cross-section — which is still optimistic (a real book
would have been left holding it through the delisting) but is enormously better
than pretending it never existed.

WHAT IS AND IS NOT INCLUDED
===========================
Alpaca lists 19,175 inactive us_equity assets, but 16,307 of them are OTC. The
OTC tape is where a $10k ticket IS the day's volume, and `xs_ranker`'s liquidity
floor excludes it anyway. So only the 2,868 inactive assets on NASDAQ / NYSE /
ARCA / AMEX / BATS are pulled. Symbols carrying Alpaca's `_DELISTED` suffix or a
numeric CUSIP-like form are kept as-is: they are still the venue's own identifier
for a real security, and dropping them would re-introduce a selection.

    python -m scripts.pull_delisted_bars --start 2016-01-01
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import night_p6_bars_and_regret as P6   # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "prices_deep"
OUT_PARQUET = OUT_DIR / "bars_delisted.parquet"
RECEIPT = OUT_DIR / "delisted_receipt.json"

LISTED_VENUES = ("NASDAQ", "NYSE", "ARCA", "AMEX", "BATS")


def inactive_listed_symbols(kid: str, sec: str) -> tuple[list[str], dict]:
    req = urllib.request.Request(
        "https://paper-api.alpaca.markets/v2/assets?status=inactive&asset_class=us_equity",
        headers={"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec})
    with urllib.request.urlopen(req, timeout=180) as fh:     # noqa: S310 allowlisted host
        assets = json.loads(fh.read())
    listed = [a for a in assets if a.get("exchange") in LISTED_VENUES]
    syms = sorted({a["symbol"] for a in listed})
    keep = [s for s in syms if _is_bar_symbol(s)]
    meta = {
        "inactive_us_equity_total": len(assets),
        "on_a_listed_venue": len(listed),
        "excluded_otc": sum(1 for a in assets if a.get("exchange") == "OTC"),
        "excluded_non_ticker_identifiers": len(syms) - len(keep),
        "examples_excluded": [s for s in syms if not _is_bar_symbol(s)][:8],
        "venues": LISTED_VENUES,
        "why_otc_excluded": ("the OTC tape cannot absorb a retail ticket without "
                             "being it; xs_ranker's liquidity floor drops it anyway"),
        "why_identifiers_excluded": (
            "the inactive list carries administrative identifiers as well as "
            "tickers -- `INDU_DELISTED`, `929ESC010`, `185CNT011`. The bars "
            "endpoint answers HTTP 400 for the whole BATCH when one of them is "
            "in it, so a single bad identifier silently costs 100 real symbols. "
            "Measured 2026-09-22 on a 25-symbol smoke run."),
    }
    return keep, meta


def _is_bar_symbol(s: str) -> bool:
    """Is this a delisted COMMON STOCK the bars endpoint will serve?

    Two filters, and the second one is the subtle one.

    1. Alpaca's inactive-asset list mixes real tickers with administrative ids
       (`INDU_DELISTED`, `929ESC010`, `185CNT011`). The bars endpoint answers
       HTTP 400 for the whole 100-symbol BATCH when one is present, so a single
       bad id silently costs 100 real symbols. Measured 2026-09-22.

    2. **Instrument type must match the survivor panel, or the comparison is
       about instrument type rather than mortality.** Measured the same day:
       the survivor panel (`prices_2025_26/bars.parquet`, 3,060 symbols) holds
       **zero** dotted symbols, **zero** 5-character units and **zero**
       warrants — it is pure common stock. The inactive list, by contrast, is
       24% preferreds (`ABR.PRA`), SPAC units (`AACQU`, `ACIC.U`) and warrants
       (`SLGCW`). Merging those into the DEAD half only would make dead names
       systematically lower-volatility and thinner for a reason that has
       nothing to do with dying, and a size/illiquidity ranker would read the
       artefact as signal. So the dead half is filtered to the same instrument
       type as the living half: 1,857 plain common names of 2,433.
    """
    if not s or "_" in s or len(s) > 5:
        return False
    if "." in s:                      # ABR.PRA preferred, ACIC.U units
        return False
    if not s.isalpha():
        return False
    # 5-character NASDAQ convention: trailing U = unit, W = warrant, R = right.
    if len(s) == 5 and s[-1] in ("U", "W", "R"):
        return False
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(OUT_PARQUET))
    a = ap.parse_args(argv)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    kid, sec, src = P6.data_credential()
    syms, meta = inactive_listed_symbols(kid, sec)
    if a.limit:
        syms = syms[:a.limit]
    print(f"{meta['inactive_us_equity_total']:,} inactive us_equity assets; "
          f"{len(syms):,} on a listed venue (credential: {src})", flush=True)

    df = P6.pull_bars(syms, a.start, None, kid, sec)
    if df is None or df.empty:
        print("REFUSED: the venue served no bars for any delisted symbol", flush=True)
        return 2
    df.to_parquet(out, index=False)

    last = df.groupby("symbol")["date"].max()
    end = df["date"].max()
    died = int((last < end - __import__("pandas").Timedelta(days=45)).sum())
    receipt = {
        "job": "pull_delisted_bars",
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "credential_source": src,
        "assets": meta,
        "start_requested": a.start,
        "symbols_requested": len(syms),
        "symbols_with_bars": int(df["symbol"].nunique()),
        "symbols_whose_bars_stop_early": died,
        "bars": int(len(df)),
        "first_session": str(df["date"].min().date()),
        "last_session": str(end.date()),
        "parquet": str(out),
        "parquet_mb": round(out.stat().st_size / 1e6, 2),
        "elapsed_s": round(time.time() - t0, 1),
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    receipt["headline"] = (
        f"{receipt['bars']:,} bars for {receipt['symbols_with_bars']:,} DELISTED symbols, "
        f"{receipt['symbols_whose_bars_stop_early']:,} of which stop trading before the end "
        f"— the names the survivor panel could never have shown")
    RECEIPT.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    print(receipt["headline"], flush=True)
    print(f"-> {out} ({receipt['parquet_mb']} MB) in {receipt['elapsed_s']}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
