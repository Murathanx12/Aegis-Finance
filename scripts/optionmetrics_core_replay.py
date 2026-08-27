"""OPTIONMETRICS_CORE_REPLAY_v1 -- does SELLING the proposed core actually pay?

    python -m scripts.optionmetrics_core_replay
    python -m scripts.optionmetrics_core_replay --hold 5 --delta 0.25 --start 2005

THE QUESTION, AND WHY NOTHING SO FAR HAS ANSWERED IT
====================================================
The competition book puts 70% of its risk in short put spreads on SPY/QQQ/IWM.
The evidence offered was `scripts/structure_lab`, which priced every structure
over MEASURED UNDERLYING RETURNS using Black-Scholes at an ASSUMED sigma. That
can only say "given this volatility assumption, this payoff shape has this
distribution". It cannot say whether the market's ACTUAL price for the shape was
generous, because the price was an input.

The option seller is paid for variance the underlying goes on to realise. The
question is whether the payment exceeded it. Only real quotes answer, so this
replays over `optionm.opprcd` best bid / best offer -- thirty years of listed
prices.

EXECUTION IS PESSIMISTIC ON ALL FOUR CROSSINGS
==============================================
    entry: sell at BEST BID      buy at BEST OFFER
    exit:  buy at BEST OFFER     sell at BEST BID

We never touch the mid. A mid-to-mid replay of a credit spread is the easiest
way to manufacture an edge that does not exist.

EVERY STRUCTURE IS PRICED ON THE SAME BLOCKS
============================================
The first version of this script compared the spread's terminal wealth against
a buy-and-hold computed only over the blocks where a chain happened to exist --
which is not buy-and-hold, it is "hold on the weeks we had data". Here each
block prices every structure from the same two dates, and a block missing any
structure is dropped from ALL of them. Coverage is printed, because a comparison
over a filtered subsample is only as good as the filter.

MARKED AT THE HORIZON, NOT AT EXPIRY
====================================
The contest ends on a date, not an expiration. Held to expiry a structure
collects all its theta and none of its path risk. Entries are ~30 DTE and exits
~25 DTE, so every exit is a real two-sided quote.

NON-OVERLAPPING BY CONSTRUCTION
===============================
One entry per `--hold` sessions (canon 58: n_effective counts DATE BLOCKS).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DATA = REPO / "backend" / "data" / "optimus" / "wrds" / "optionm_etf_quotes"
SECIDS = {"SPY": 109820, "QQQ": 107899, "IWM": 106445, "SMH": 151720}
MULT = 100.0

STRUCTURES = ["short_put_spread", "call_debit_spread", "long_atm_call",
              "long_straddle", "long_shares"]


# ----------------------------------------------------------------- loading
def load(symbol: str, start: int, end: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    secid = SECIDS[symbol]
    q, u = [], []
    for y in range(start, end + 1):
        fq, fu = DATA / f"quotes_{y}.parquet", DATA / f"under_{y}.parquet"
        if fq.exists():
            a = pd.read_parquet(fq)
            a = a[a["secid"] == secid]
            if len(a):
                q.append(a)
        if fu.exists():
            b = pd.read_parquet(fu)
            b = b[b["secid"] == secid]
            if len(b):
                u.append(b)
    if not q or not u:
        return pd.DataFrame(), pd.DataFrame()
    qq = pd.concat(q, ignore_index=True)
    uu = pd.concat(u, ignore_index=True).sort_values("date").reset_index(drop=True)
    qq["date"] = pd.to_datetime(qq["date"])
    qq["exdate"] = pd.to_datetime(qq["exdate"])
    uu["date"] = pd.to_datetime(uu["date"])
    qq["ss_flag"] = qq["ss_flag"].astype(str)
    return qq, uu


def _nearest(df: pd.DataFrame, col: str, target: float):
    if df.empty:
        return None
    i = (df[col].astype(float) - target).abs().idxmin()
    return df.loc[i]


def _leg_exit(g1: pd.DataFrame, optionid) -> pd.Series | None:
    m = g1[g1["optionid"] == optionid]
    return m.iloc[0] if len(m) else None


# ------------------------------------------------------------- the replay
def replay_symbol(symbol: str, *, hold: int, short_delta: float,
                  width_frac: float, start: int, end: int,
                  target_dte: int = 30) -> dict:
    q, u = load(symbol, start, end)
    if q.empty or u.empty:
        return {"symbol": symbol, "n": 0, "note": "no data"}

    n_nonstd = int((q["ss_flag"] != "0").sum())
    q = q[q["ss_flag"] == "0"]

    dates = np.array(sorted(u["date"].unique()))
    close = u.set_index("date")["close"].astype(float)
    by_date = {d: g for d, g in q.groupby("date")}

    rows, skipped = [], {}

    def skip(why):
        skipped[why] = skipped.get(why, 0) + 1

    n_blocks_possible = 0
    for i in range(0, len(dates) - hold, hold):
        n_blocks_possible += 1
        d0, d1 = dates[i], dates[i + hold]
        g0, g1 = by_date.get(d0), by_date.get(d1)
        if g0 is None or g1 is None:
            skip("no chain on entry or exit date")
            continue
        spot0, spot1 = float(close.get(d0, np.nan)), float(close.get(d1, np.nan))
        if not (np.isfinite(spot0) and np.isfinite(spot1)):
            skip("no underlying close")
            continue

        alive = g0[g0["exdate"] > d1]
        if alive.empty:
            skip("no expiry survives the hold")
            continue
        exps = alive["exdate"].unique()
        exp = min(exps, key=lambda e: abs((pd.Timestamp(e) - pd.Timestamp(d0)).days
                                          - target_dte))
        c0 = alive[alive["exdate"] == exp]
        puts0, calls0 = c0[c0["cp_flag"] == "P"], c0[c0["cp_flag"] == "C"]
        if puts0.empty or calls0.empty:
            skip("expiry missing a right")
            continue

        rec = {"entry": pd.Timestamp(d0), "exit": pd.Timestamp(d1),
               "spot0": spot0, "spot1": spot1,
               "under_ret": spot1 / spot0 - 1.0,
               "dte": int((pd.Timestamp(exp) - pd.Timestamp(d0)).days)}
        ok = True

        # ---- 1. SHORT PUT SPREAD: the proposed core ------------------------
        sp = puts0.dropna(subset=["delta"])
        short = _nearest(sp, "delta", -abs(short_delta)) if len(sp) else None
        if short is None:
            skip("no short put leg")
            continue
        lower = puts0[puts0["strike"] < short["strike"]]
        if lower.empty:
            skip("no protective strike below")
            continue
        long = _nearest(lower, "strike", short["strike"] - max(1.0, spot0 * width_frac))
        width = float(short["strike"] - long["strike"])
        credit = float(short["best_bid"]) - float(long["best_offer"])
        xs, xl = _leg_exit(g1, short["optionid"]), _leg_exit(g1, long["optionid"])
        if width <= 0 or credit <= 0 or xs is None or xl is None:
            skip("put spread not priceable end to end")
            continue
        max_loss = (width - credit) * MULT
        if max_loss <= 0:
            skip("credit >= width")
            continue
        cost = float(xs["best_offer"]) - float(xl["best_bid"])
        rec["short_put_spread_pnl"] = (credit - cost) * MULT
        rec["short_put_spread_risk"] = max_loss
        rec["credit_ratio"] = credit / width
        rec["short_delta"] = float(short["delta"])

        # ---- 2. CALL DEBIT SPREAD: the convexity alternative ---------------
        ca = calls0.dropna(subset=["delta"])
        lc = _nearest(ca, "delta", 0.50) if len(ca) else None
        if lc is None:
            ok = False
        else:
            higher = calls0[calls0["strike"] > lc["strike"]]
            sc = _nearest(higher, "strike",
                          lc["strike"] + max(1.0, spot0 * width_frac)) \
                if not higher.empty else None
            if sc is None:
                ok = False
            else:
                debit = float(lc["best_offer"]) - float(sc["best_bid"])
                x1, x2 = _leg_exit(g1, lc["optionid"]), _leg_exit(g1, sc["optionid"])
                if debit <= 0 or x1 is None or x2 is None:
                    ok = False
                else:
                    val = float(x1["best_bid"]) - float(x2["best_offer"])
                    rec["call_debit_spread_pnl"] = (val - debit) * MULT
                    rec["call_debit_spread_risk"] = debit * MULT

        # ---- 3. LONG ATM CALL and 4. LONG STRADDLE -------------------------
        atm_c = _nearest(calls0, "strike", spot0)
        atm_p = _nearest(puts0, "strike", spot0)
        xc = _leg_exit(g1, atm_c["optionid"]) if atm_c is not None else None
        xp = _leg_exit(g1, atm_p["optionid"]) if atm_p is not None else None
        if xc is None or xp is None:
            ok = False
        else:
            cpay = float(atm_c["best_offer"])
            rec["long_atm_call_pnl"] = (float(xc["best_bid"]) - cpay) * MULT
            rec["long_atm_call_risk"] = cpay * MULT
            spay = cpay + float(atm_p["best_offer"])
            rec["long_straddle_pnl"] = (
                float(xc["best_bid"]) + float(xp["best_bid"]) - spay) * MULT
            rec["long_straddle_risk"] = spay * MULT

        # ---- 5. SHARES ------------------------------------------------------
        # "Risk" for shares is taken as the NOTIONAL, which HANDICAPS them, and
        # the handicap is left in deliberately.
        #
        # An earlier version of this comment claimed the opposite -- that using
        # notional was "generous to shares". It is not. A share position cannot
        # lose 100% over five sessions (SPY's worst block here is -12.5%), so
        # equating notional with risk lets the shares row hold only 20% of
        # equity where an equal-risk sizing would hold roughly 150%. Every
        # option row, by contrast, really can lose its whole stake.
        #
        # The handicap stays because it points the wrong way for the thing on
        # trial: if the option structures still fail to beat shares while shares
        # are being under-sized, the conclusion is safe. It also means the
        # shares row must NOT be read as a return forecast -- the buy-and-hold
        # reference line below is the honest number for that.
        rec["long_shares_pnl"] = (spot1 - spot0) * MULT
        rec["long_shares_risk"] = spot0 * MULT

        if not ok:
            skip("a comparison structure was not priceable; block dropped from ALL")
            continue
        rows.append(rec)

    df = pd.DataFrame(rows)

    # SHARES: restate "risk" as the MEASURED worst five-session loss.
    #
    # Using notional made every option row directly comparable in P&L per dollar
    # allocated, but not in RISK: $10,000 of notional in SPY cannot lose
    # $10,000, while $10,000 of defined loss in a spread genuinely can. Feeding
    # both to an allocator that thinks in max-loss dollars therefore
    # under-sizes shares by roughly 8x and hands the book to the options by an
    # accounting convention rather than by evidence.
    #
    # The denominator is the worst block actually observed in this sample. That
    # is in-sample and is stated as such -- it is the same convention the book
    # already used (`WORST_5D = 0.1331`, measured), and any figure here is a
    # choice about how much share exposure one unit of "risk" buys, not a claim
    # about the return.
    if len(df):
        worst_frac = float(abs(df["under_ret"].min()))
        if worst_frac > 0:
            df["long_shares_risk"] = df["long_shares_risk"] * worst_frac
            df["shares_worst_5d"] = worst_frac

    return {"symbol": symbol, "df": df, "skipped": skipped,
            "n_nonstandard_dropped": n_nonstd, "n": len(df),
            "n_blocks_possible": n_blocks_possible,
            # Buy-and-hold over the SAME window the blocks cover. SPY's option
            # history starts in 2005 while its underlying series starts in 1999,
            # so a reference spanning the whole price file compared a 20-year
            # strategy against a 26-year benchmark and silently flattered the
            # benchmark by six years of the dot-com recovery.
            "full_hold": _hold_over(close, rows),
            "span": _span_over(close, rows)}


def _window(close, rows):
    if not rows:
        return None
    lo, hi = rows[0]["entry"], rows[-1]["exit"]
    w = close[(close.index >= lo) & (close.index <= hi)]
    return w if len(w) >= 2 else None


def _hold_over(close, rows) -> float:
    w = _window(close, rows)
    return float(w.iloc[-1] / w.iloc[0]) if w is not None else float("nan")


def _span_over(close, rows) -> tuple[str, str]:
    w = _window(close, rows)
    if w is None:
        return ("", "")
    return (str(w.index[0].date()), str(w.index[-1].date()))


# ------------------------------------------------------------------ reporting
def stats(x: np.ndarray) -> dict:
    x = x[np.isfinite(x)]
    if x.size < 2:
        return {"n": int(x.size), "mean": float("nan"), "median": float("nan"),
                "hit": float("nan"), "t": float("nan"), "p05": float("nan"),
                "worst": float("nan")}
    sd = float(np.std(x, ddof=1))
    return {"n": int(x.size), "mean": float(np.mean(x)),
            "median": float(np.median(x)), "hit": float((x > 0).mean()),
            "sd": sd,
            "t": float(np.mean(x) / sd * math.sqrt(x.size)) if sd > 0 else 0.0,
            "p05": float(np.percentile(x, 5)), "worst": float(np.min(x))}


def wealth(ret_on_risk: np.ndarray, frac: float) -> float:
    """Terminal wealth risking `frac` of CURRENT equity each block.

    Terminal wealth, not the mean: `FINDING_2026-08-28_VARIANCE_DRAG_ATE_THE_
    EDGE.md` exists because a book with a positive mean per window compounded to
    0.1x. A credit spread's geometry -- many small wins, rare large losses -- is
    exactly the shape that lies in a mean.
    """
    r = ret_on_risk[np.isfinite(ret_on_risk)]
    return float(np.prod(1.0 + frac * r))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="SPY,QQQ,IWM")
    ap.add_argument("--hold", type=int, default=5)
    ap.add_argument("--delta", type=float, default=0.25)
    ap.add_argument("--width-frac", type=float, default=0.05)
    ap.add_argument("--start", type=int, default=1996)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--risk-frac", type=float, default=0.20)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    print(f"OPTIONMETRICS CORE REPLAY   sell {args.delta:.2f}-delta put, "
          f"{args.width_frac:.0%} wide, ~30 DTE, held {args.hold} sessions")
    print("execution: sell at BID, buy at OFFER, entry AND exit. Never the mid.")
    print("=" * 96)

    out = {}
    for sym in args.symbols.split(","):
        r = replay_symbol(sym, hold=args.hold, short_delta=args.delta,
                          width_frac=args.width_frac, start=args.start, end=args.end)
        if r["n"] == 0:
            print(f"\n{sym}: NO USABLE BLOCKS  {r.get('skipped', {})}")
            continue
        df = r["df"]
        yrs = (df["exit"].max() - df["entry"].min()).days / 365.25
        cov = r["n"] / max(1, r["n_blocks_possible"])
        print(f"\n{sym}  {df['entry'].min().date()} .. {df['exit'].max().date()}"
              f"   {r['n']} blocks of {r['n_blocks_possible']} possible "
              f"({cov:.0%} coverage, {yrs:.1f}y)")
        print(f"  skips: {dict(sorted(r['skipped'].items(), key=lambda kv: -kv[1])[:3])}")
        print(f"  credit received: median {df['credit_ratio'].median():.1%} of width "
              f"(p10 {df['credit_ratio'].quantile(.1):.1%}, "
              f"p90 {df['credit_ratio'].quantile(.9):.1%})")
        print(f"\n  {'structure':<20}{'median':>9}{'mean':>9}{'hit':>8}{'t':>7}"
              f"{'p05':>9}{'worst':>10}{'wealth':>9}")
        print("  " + "-" * 81)
        srow = {}
        for s in STRUCTURES:
            col = f"{s}_pnl"
            if col not in df:
                continue
            ror = (df[col] / df[f"{s}_risk"]).to_numpy()
            st = stats(ror)
            w = wealth(ror, args.risk_frac)
            srow[s] = {**st, "wealth": w}
            print(f"  {s:<20}{st['median']:>+9.2%}{st['mean']:>+9.2%}"
                  f"{st['hit']:>8.1%}{st['t']:>+7.2f}{st['p05']:>+9.2%}"
                  f"{st['worst']:>+10.2%}{w:>9.2f}x")
        print(f"  {'CASH':<20}{0:>+9.2%}{0:>+9.2%}{'--':>8}{'--':>7}"
              f"{0:>+9.2%}{0:>+10.2%}{1.00:>9.2f}x")
        print(f"\n  reference: buy and hold the WHOLE span "
              f"{r['span'][0]}..{r['span'][1]} = {r['full_hold']:.2f}x "
              f"(every session, not just sampled blocks)")

        df["era"] = pd.cut(df["entry"].dt.year, [1995, 2007, 2012, 2019, 2026],
                           labels=["<=2007", "2008-2012", "2013-2019", "2020-2025"])
        print(f"  short_put_spread by era:")
        for era, g in df.groupby("era", observed=True):
            if len(g) < 5:
                continue
            ror = (g["short_put_spread_pnl"] / g["short_put_spread_risk"]).to_numpy()
            es = stats(ror)
            print(f"    {str(era):<12} n={es['n']:>4}  median {es['median']:>+7.2%}"
                  f"  hit {es['hit']:>5.1%}  t {es['t']:>+5.2f}"
                  f"  wealth {wealth(ror, args.risk_frac):>6.2f}x"
                  f"  worst {es['worst']:>+7.2%}")
        # The per-block return-on-risk SAMPLES travel in the receipt, not just
        # the summary statistics. `alpha/tournament.Opportunity` resamples them
        # directly, so the allocator never sees a fitted normal: a credit spread
        # (wins small and often) and a debit spread (loses small and often) have
        # the same sign of mean and opposite shapes, and a mean/sd summary
        # destroys exactly the property that distinguishes them.
        samples = {}
        for s in STRUCTURES:
            col = f"{s}_pnl"
            if col in df:
                v = (df[col] / df[f"{s}_risk"]).to_numpy()
                samples[s] = [round(float(x), 6) for x in v[np.isfinite(v)]]

        recent = df[df["entry"].dt.year >= 2021]
        out[sym] = {"structures": srow, "years": yrs, "n_blocks": r["n"],
                    "coverage": cov, "full_hold": r["full_hold"],
                    "credit_ratio_median": float(df["credit_ratio"].median()),
                    "credit_ratio_p10": float(df["credit_ratio"].quantile(.1)),
                    "samples": samples,
                    "samples_recent": {
                        s: [round(float(x), 6) for x in
                            (recent[f"{s}_pnl"] / recent[f"{s}_risk"]).to_numpy()
                            if np.isfinite(x)]
                        for s in STRUCTURES if f"{s}_pnl" in recent and len(recent)},
                    "entry_dates": [str(d.date()) for d in df["entry"]]}

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2, default=str),
                                   encoding="utf-8")
        print(f"\nreceipt -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
