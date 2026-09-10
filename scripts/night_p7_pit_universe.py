"""P7 -- A POINT-IN-TIME UNIVERSE VINTAGE FOR 2025-26.

    python -m scripts.night_p7_pit_universe --smoke
    python -m scripts.night_p7_pit_universe --run 1

WHY THIS JOB EXISTS
===================
P6 (`night_p6_bars_and_regret.py`, receipts
`night_factory_2026-09-08/P6_bars_and_regret_run0{1..4}.json`) refused to grade
anything against its own equal-weight universe row and stamped it:

    "the universe is the 2026-09-01 screen: every member is a name that still
     exists and still clears $3m/day TODAY. Replaying it from 2025-01 silently
     drops whatever was delisted, acquired or fell below the floor, so this row
     is an UPPER bound, not a benchmark."

Two separate look-aheads hide in that one sentence:

  (1) SURVIVAL -- names that stopped trading inside the window are absent from
      a screen taken at the end of it;
  (2) LIQUIDITY -- the $3m/day floor is applied with TODAY's dollar volume, so
      a name that was untradable in 2025-03 and is liquid now is wrongly in the
      2025-03 book, and a name that was liquid in 2025-03 and is dead now is
      wrongly out of it.

This file fixes (2) exactly and MEASURES (1) rather than claiming to fix it.
Membership for month M is decided only from bars dated strictly before M's
first session:

    traded_through(M) : first_bar <= M's first session AND last_bar >= M's last
                        session (the name was actually trading across all of M)
    liquid_at(M)      : median dollar volume over the 20 sessions ENDING at the
                        last session strictly BEFORE M >= TRADABLE_DOLLAR_VOL

`TRADABLE_DOLLAR_VOL` is imported from `learner.evaluate` ($3,000,000/day, the
repo's own execution floor -- [[feedback-apply-the-execution-floor-before-
believing-the-book]]). It is not re-declared here; a floor that exists twice is
a floor that will disagree with itself.

WHAT THE RECEIPT MUST SAY OUT LOUD
==================================
The count of names that are IN an early vintage and OUT of the final one is the
survivorship the old benchmark was hiding. If that count is zero -- or if it is
entirely liquidity and contains no name that stopped trading -- then the BAR
SOURCE is itself survivor-screened and this vintage does not repair (1). The
receipt says so in `bar_source_survivor_screened`, because a vintage that looks
point-in-time and is not is worse than the biased row it replaced.

LICENCE: PRODUCT_EXPERIMENT. No model, no signal, no claim, no order. This file
writes a membership table.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
BARS = REPO / "backend" / "data" / "optimus" / "prices_2025_26" / "bars.parquet"
OUT_PARQUET = (REPO / "backend" / "data" / "optimus" / "text_return_panel"
               / "pit_universe_vintage_2025_26.parquet")
RECEIPT_DIR = REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-09"

#: the four index proxies P6 pulled alongside the tracker screen; they are
#: benchmarks, not universe members, and an ETF inside an equal-weight book is
#: a second copy of the market.
INDEX_PROXIES = ("SPY", "QQQ", "IWM", "RSP")

#: trailing window for the liquidity screen, in SESSIONS (not calendar days)
LOOKBACK_SESSIONS = 20


def _floor() -> float:
    """The repo's execution floor, imported -- never re-typed here."""
    from learner.evaluate import TRADABLE_DOLLAR_VOL
    return float(TRADABLE_DOLLAR_VOL)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write(path: Path, payload: dict) -> None:
    """Incremental receipt write: tmp + replace, so a kill never truncates it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


def build(smoke: bool = False, receipt_path: Path | None = None) -> dict:
    t0 = time.time()
    floor = _floor()
    payload: dict = {
        "job": "P7_pit_universe_vintage",
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "state": "RUNNING",
        "bars": str(BARS),
        "floor_median_dollar_volume": floor,
        "floor_source": "learner.evaluate.TRADABLE_DOLLAR_VOL",
        "lookback_sessions": LOOKBACK_SESSIONS,
        "index_proxies_excluded": list(INDEX_PROXIES),
        "smoke": bool(smoke),
        "written_utc": _now(),
    }
    if receipt_path is not None:
        _write(receipt_path, payload)

    if not BARS.is_file():
        payload.update(state="DONE",
                       verdict=("REFUSED: the 2025-26 bar panel is not on this machine "
                                f"({BARS}); P6a writes it"),
                       headline="REFUSED -- no bars on this machine",
                       written_utc=_now())
        if receipt_path is not None:
            _write(receipt_path, payload)
        return payload

    df = pd.read_parquet(BARS, columns=["symbol", "date", "close", "volume", "vwap"])
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    if smoke:                                   # first 200 symbols alphabetically
        keep = set(sorted(df["symbol"].unique())[:200]) | set(INDEX_PROXIES)
        df = df[df["symbol"].isin(keep)]

    # dollar volume: vwap x volume where the venue gave a usable vwap, else close
    px = df["vwap"].where(np.isfinite(df["vwap"]) & (df["vwap"] > 0), df["close"])
    df["dv"] = px.astype(float) * df["volume"].astype(float)

    first_bar = df.groupby("symbol")["date"].min()
    last_bar = df.groupby("symbol")["date"].max()

    piv = df.pivot_table(index="date", columns="symbol", values="dv", aggfunc="last").sort_index()
    sessions = piv.index
    # rolling median over LOOKBACK_SESSIONS requiring a FULL window: a median of
    # three sessions is not the same statistic and would let a fresh listing in.
    med = piv.rolling(LOOKBACK_SESSIONS, min_periods=LOOKBACK_SESSIONS).median()

    months = sessions.to_period("M")
    month_list = list(pd.PeriodIndex(sorted(set(months))))
    symbols = [s for s in piv.columns if s not in INDEX_PROXIES]

    rows: list[dict] = []
    per_month: dict[str, dict] = {}
    prev_members: set[str] | None = None
    for m in month_list:
        sess_m = sessions[months == m]
        m_start, m_end = sess_m[0], sess_m[-1]
        # the last session STRICTLY BEFORE the month starts -- the newest bar a
        # decision taken on the morning of m_start could possibly have seen
        prior = sessions[sessions < m_start]
        if len(prior) == 0:
            asof = None
            mv = pd.Series(np.nan, index=symbols, dtype=float)
            no_hist = "no session precedes this month in the panel"
        else:
            asof = prior[-1]
            mv = med.loc[asof].reindex(symbols).astype(float)
            no_hist = f"fewer than {LOOKBACK_SESSIONS} sessions on or before {asof.date()}"

        traded = ((first_bar.reindex(symbols) <= m_start)
                  & (last_bar.reindex(symbols) >= m_end)).fillna(False)
        liquid = (mv >= floor).fillna(False)
        member = traded & liquid

        for sym in symbols:
            if bool(member[sym]):
                reason = "IN"
            elif not bool(traded[sym]):
                fb, lb = first_bar.get(sym), last_bar.get(sym)
                reason = ("not_yet_listed" if pd.notna(fb) and fb > m_start
                          else "stopped_trading" if pd.notna(lb) and lb < m_end
                          else "no_bars")
            elif pd.isna(mv[sym]):
                reason = no_hist
            else:
                reason = "below_dollar_vol_floor"
            rows.append({
                "month": str(m),
                "symbol": sym,
                "first_bar": first_bar.get(sym, pd.NaT),
                "last_bar": last_bar.get(sym, pd.NaT),
                "asof_session": asof,
                "median_dollar_vol_20d": float(mv[sym]) if pd.notna(mv[sym]) else np.nan,
                "in_universe": bool(member[sym]),
                "reason": reason,
            })

        members = {s for s in symbols if bool(member[s])}
        entered = sorted(members - prev_members) if prev_members is not None else []
        exited = sorted(prev_members - members) if prev_members is not None else []
        per_month[str(m)] = {
            "sessions": int(len(sess_m)),
            "month_first_session": str(m_start.date()),
            "month_last_session": str(m_end.date()),
            "liquidity_asof_session": str(asof.date()) if asof is not None else None,
            "names": len(members),
            "entered": len(entered),
            "exited": len(exited),
            "entered_examples": entered[:8],
            "exited_examples": exited[:8],
        }
        prev_members = members
        payload["per_month"] = per_month
        payload["written_utc"] = _now()
        if receipt_path is not None:
            _write(receipt_path, payload)          # incremental: one write per month

    vin = pd.DataFrame(rows)
    vin["month"] = vin["month"].astype(str)
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    vin.to_parquet(OUT_PARQUET, index=False)

    # ---- the survivorship number -------------------------------------------
    valid_months = [m for m, c in per_month.items() if c["names"] > 0]
    if not valid_months:
        payload.update(state="DONE",
                       verdict="REFUSED: no month has a gradable vintage",
                       headline="REFUSED -- every vintage is empty",
                       parquet=str(OUT_PARQUET), parquet_rows=int(len(vin)),
                       written_utc=_now())
        if receipt_path is not None:
            _write(receipt_path, payload)
        return payload

    first_m, final_m = valid_months[0], valid_months[-1]
    memb = {m: set(vin.loc[(vin["month"] == m) & vin["in_universe"], "symbol"])
            for m in valid_months}
    final = memb[final_m]
    gone_from_first = sorted(memb[first_m] - final)
    ever = set().union(*memb.values())
    gone_from_any = sorted(ever - final)
    panel_end = sessions[-1]

    def _why(sym: str) -> str:
        lb = last_bar.get(sym)
        if pd.notna(lb) and lb < panel_end:
            return "stopped_trading"
        return "below_dollar_vol_floor"

    def _counts(names: list[str]) -> dict:
        out: dict[str, int] = {}
        for s in names:
            k = _why(s)
            out[k] = out.get(k, 0) + 1
        return out

    stopped_trading = sorted(s for s in symbols
                             if pd.notna(last_bar.get(s)) and last_bar[s] < panel_end)
    # a bar panel drawn from a screen taken at the END of the window contains
    # almost no name that stopped trading; that ratio is the tell.
    screened = len(stopped_trading) <= max(3, 0.005 * len(symbols))

    payload.update({
        "state": "DONE",
        "parquet": str(OUT_PARQUET),
        "parquet_rows": int(len(vin)),
        "symbols_considered": len(symbols),
        "panel": {"first_session": str(sessions[0].date()),
                  "last_session": str(panel_end.date()),
                  "sessions": int(len(sessions)),
                  "bars": int(len(df))},
        "months_total": len(month_list),
        "months_gradable": len(valid_months),
        "first_gradable_month": first_m,
        "final_month": final_m,
        "names_first_gradable_month": len(memb[first_m]),
        "names_final_month": len(final),
        "survivorship": {
            "in_first_vintage_absent_from_final": len(gone_from_first),
            "in_first_vintage_absent_from_final_by_cause": _counts(gone_from_first),
            "in_any_earlier_vintage_absent_from_final": len(gone_from_any),
            "in_any_earlier_vintage_absent_from_final_by_cause": _counts(gone_from_any),
            "examples": gone_from_first[:15],
        },
        "bar_source_survivor_screened": bool(screened),
        "symbols_that_stopped_trading_inside_the_window": len(stopped_trading),
        "symbols_that_stopped_trading_examples": stopped_trading[:15],
        "elapsed_s": round(time.time() - t0, 1),
        "written_utc": _now(),
    })
    payload["verdict"] = (
        ("PANEL BUILT, PARTIAL FIX. The LIQUIDITY look-ahead is repaired: membership is decided "
         f"on the trailing-{LOOKBACK_SESSIONS}-session median dollar volume as of each month's "
         "start, so a name liquid in 2025 and illiquid now is IN the early vintage and OUT of "
         "the late one. The SURVIVAL look-ahead is NOT repaired: only "
         f"{len(stopped_trading)} of {len(symbols)} symbols in this bar panel ever stop trading, "
         "because the bar pull itself started from the 2026-09-01 screen. Any name delisted or "
         "acquired before 2026-09-01 has NO BARS AT ALL and cannot appear in any vintage. Read "
         "an equal-weight book over this vintage as still an UPPER bound on survival, and keep "
         "INDEX_RSP as the honest equal-weight bar until a listing-history source (CRSP delist "
         "codes, or an Alpaca assets snapshot taken BEFORE the window) is joined.")
        if screened else
        ("PANEL BUILT. Membership is point-in-time on both survival and liquidity: "
         f"{len(stopped_trading)} symbols stop trading inside the window and are out of every "
         "vintage after they do."))
    payload["headline"] = (
        f"{len(vin):,} (month, symbol) rows over {len(symbols):,} symbols and "
        f"{len(valid_months)} gradable months {first_m}..{final_m}; "
        f"{len(memb[first_m]):,} names in the first vintage vs {len(final):,} in the last; "
        f"{len(gone_from_first)} are IN the first and OUT of the last "
        f"({_counts(gone_from_first)}); the bar source is "
        f"{'ITSELF SURVIVOR-SCREENED' if screened else 'not survivor-screened'} -- "
        f"{len(stopped_trading)} of {len(symbols)} symbols ever stop trading")
    if receipt_path is not None:
        _write(receipt_path, payload)
    return payload


def P7_pit_universe_vintage(smoke: bool = False) -> dict:
    """Entry point in the shape `night_factory` dispatches its jobs."""
    return build(smoke=smoke)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="first 200 symbols only")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else (
        RECEIPT_DIR / f"P7_pit_universe_vintage_run{a.run:02d}{'_smoke' if a.smoke else ''}.json")
    payload = build(smoke=a.smoke, receipt_path=out)
    print(payload.get("headline"))
    print(f"\nP7 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
