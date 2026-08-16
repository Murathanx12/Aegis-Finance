"""N1 — does the return accrue BEFORE the insider trade is disclosed?

    python -m scripts.n1_disclosure_lag_decay

WHY THIS IS THE HIGHEST-VALUE CHEAP TEST
========================================
COPY-LAB's premise is that an observed expert action can be copied. That
premise has a precondition nobody has measured: **the move must still be
available when the action becomes public.** A Form 4 discloses a trade that
already happened. If the abnormal return accrues between the transaction and
the filing, the signal can be real, strong and perfectly identified — and still
uncopyable, because by the time anyone outside can see it, it has been paid.

One measurement can therefore terminate or license an entire track, which is
why it outranks work that merely improves an estimate.

THE TWO HALVES, AND WHY ONLY ONE IS ANSWERABLE TODAY
====================================================
* **Pre-disclosure** (transaction -> filing): definitionally uncopyable. Fully
  measurable from history, because both dates are in the past.
* **Post-disclosure** (filing -> forward): the copyable half. Needs forward
  price history AFTER the filing date.

This script measures both and reports the sample size of each honestly. It does
not average them into one number, because they answer different questions and
one of them may have no sample at all.

EVERY ROW OWES ITS OWN n_effective (SS19, and §41's lesson specifically)
=======================================================================
Events filed on the SAME day are not independent draws: they share one market
day, and market-adjusting removes the index but not the day. The effective
sample is bounded by the number of distinct FILING DAYS, not by the number of
filings — the same mistake as counting six co-moving ETFs across nine months of
the GFC as fifty-four observations.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import power as PW

EVENTS = (_config.OPTIMUS_LEDGER_DIR / "teacher_library" / "events.jsonl")
OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "n1_disclosure_lag.json"
BENCH = "SPY"

#: Lag buckets in calendar days. Chosen before any number was computed, from
#: the SEC's own rule: Form 4 is due within two business days of the trade, so
#: 0-2 is compliance, 3+ is late, and >10 is a different animal.
LAG_BUCKETS = ((0, 0), (1, 1), (2, 2), (3, 5), (6, 10), (11, 10_000))


def _bucket(lag: float) -> str:
    for lo, hi in LAG_BUCKETS:
        if lo <= lag <= hi:
            return f"{lo}d" if lo == hi else (f"{lo}-{hi}d" if hi < 1000
                                              else f"{lo}d+")
    return "?"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--events", default=str(EVENTS))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--forward-days", type=int, default=5)
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    import pandas as pd
    import yfinance as yf

    rows = [json.loads(ln) for ln in
            Path(a.events).read_text(encoding="utf-8").splitlines() if ln.strip()]
    evs = []
    for r in rows:
        if r.get("action_type") not in ("BUY", "SELL"):
            continue
        tkr = r.get("security_id") or r.get("ticker_at_event")
        tx, fl = r.get("transaction_at"), (r.get("public_at")
                                           or r.get("filed_at"))
        if not (tkr and tx and fl):
            continue
        evs.append({"ticker": str(tkr).upper(), "action": r["action_type"],
                    "tx": str(tx)[:10], "filed": str(fl)[:10],
                    "lag": float(r.get("disclosure_lag_days") or 0.0),
                    "actor": r.get("actor_id") or ""})

    print(f"events with a transaction date and a filing date: {len(evs)}")
    if not evs:
        print("nothing to measure")
        return 1

    filing_days = sorted({e["filed"] for e in evs})
    tickers = sorted({e["ticker"] for e in evs})
    print(f"  distinct tickers      {len(tickers)}")
    print(f"  distinct FILING DAYS  {len(filing_days)}  "
          f"{filing_days[:3]}{' ...' if len(filing_days) > 3 else ''}")
    print(f"  transaction range     {min(e['tx'] for e in evs)} -> "
          f"{max(e['tx'] for e in evs)}")

    # THE BINDING CONSTRAINT, STATED BEFORE ANY RETURN IS COMPUTED.
    if len(filing_days) < 5:
        print(f"\n*** THE CORPUS IS {len(filing_days)} FILING DAY(S) DEEP. "
              f"Whatever the cross-section shows, the post-disclosure half of "
              f"this test has at most {len(filing_days)} independent calendar "
              f"draw(s), and market-adjusting removes the index but not the "
              f"day. Read the n_effective column, not the n column.")

    start = (pd.Timestamp(min(e["tx"] for e in evs))
             - pd.Timedelta(days=15)).date().isoformat()
    print(f"\ndownloading prices for {len(tickers)} tickers + {BENCH} "
          f"from {start}")
    px = yf.download(tickers + [BENCH], start=start, progress=False,
                     auto_adjust=True)["Close"]
    if isinstance(px, pd.Series):
        px = px.to_frame()
    px = px.ffill()
    if BENCH not in px.columns:
        print(f"benchmark {BENCH} missing — cannot market-adjust")
        return 1

    def _ret(tkr: str, d0: str, d1: str):
        """Close-to-close return between two dates, or None."""
        if tkr not in px.columns:
            return None
        s = px[tkr].dropna()
        try:
            i0 = s.index.searchsorted(pd.Timestamp(d0), side="right") - 1
            i1 = s.index.searchsorted(pd.Timestamp(d1), side="right") - 1
        except Exception:                                        # noqa: BLE001
            return None
        if i0 < 0 or i1 < 0 or i1 <= i0 or i1 >= len(s):
            return None
        return float(s.iloc[i1] / s.iloc[i0] - 1.0)

    def _fwd(tkr: str, d0: str, n: int):
        if tkr not in px.columns:
            return None
        s = px[tkr].dropna()
        i0 = s.index.searchsorted(pd.Timestamp(d0), side="right") - 1
        if i0 < 0 or i0 + 1 >= len(s):
            return None
        i1 = min(i0 + n, len(s) - 1)
        if i1 <= i0:
            return None
        return float(s.iloc[i1] / s.iloc[i0] - 1.0), int(i1 - i0)

    # ── HOW MANY INDEPENDENT DRAWS IS A CROSS-SECTION ON ONE DAY? ──────────
    # This script's own header says n_effective is bounded by distinct FILING
    # DAYS, and the first version then computed it as the count of distinct
    # (ticker, filing-day) pairs — 32 names filed on one day counted as 32
    # observations. That is §41 exactly, in the code of the script that quotes
    # §41, and it inflated a "detectable" +1.8% post-disclosure buy return.
    #
    # Neither extreme is right: 193 different companies are not one draw, and
    # they are certainly not 193. The standard correction for m observations
    # with average pairwise correlation rho is m / (1 + (m-1) * rho), and rho
    # is MEASURED here from the market-adjusted daily returns of the names
    # actually involved rather than assumed.
    def _mean_pairwise_corr(names: list[str]) -> float:
        cols = [n for n in names if n in px.columns][:60]
        if len(cols) < 3:
            return 1.0                       # cannot measure -> assume one draw
        r = px[cols].pct_change()
        r = r.sub(px[BENCH].pct_change(), axis=0).dropna(how="all")
        if len(r) < 30:
            return 1.0
        c = r.corr().to_numpy()
        n = c.shape[0]
        off = [c[i][j] for i in range(n) for j in range(i + 1, n)
               if c[i][j] == c[i][j]]
        return float(sum(off) / len(off)) if off else 1.0

    RHO = _mean_pairwise_corr(tickers)
    print(f"\nmean pairwise correlation of MARKET-ADJUSTED daily returns "
          f"across the event names: rho = {RHO:.3f}")
    print(f"  -> m names filed on one day are worth m / (1 + (m-1)*rho) "
          f"independent draws, not m")

    def _n_eff(n_names: int, n_days: int) -> float:
        """Independent draws from `n_names` names spread over `n_days` days."""
        if n_names <= 0:
            return 0.0
        per_day = max(1.0, n_names / max(n_days, 1))
        shrunk = per_day / (1.0 + (per_day - 1.0) * max(RHO, 0.0))
        return min(float(n_names), shrunk * max(n_days, 1))

    pre: dict[tuple, list[float]] = defaultdict(list)
    post: dict[tuple, list[float]] = defaultdict(list)
    #: SS18. Two tables of separate means cannot answer COPY-LAB's question,
    #: which is a DIFFERENCE: does more of the move accrue before disclosure
    #: than after it? "Detectable pre, not detectable post" is the exact
    #: substitution the canon names, and it is the one this script would
    #: otherwise invite a reader to make from the two tables below. Paired per
    #: EVENT so the difference has its own SE on the same names.
    paired: dict[tuple, list[float]] = defaultdict(list)
    post_days: list[int] = []
    clusters: dict[tuple, set] = defaultdict(set)
    n_no_pre = 0

    for e in evs:
        sign = 1.0 if e["action"] == "BUY" else -1.0
        key = (e["action"], _bucket(e["lag"]))
        clusters[key].add((e["ticker"], e["filed"]))

        rt = _ret(e["ticker"], e["tx"], e["filed"])
        rb = _ret(BENCH, e["tx"], e["filed"])
        pre_val = None
        if rt is None or rb is None:
            n_no_pre += 1
        else:
            # Signed so a positive number always means "the move went the
            # insider's way", for buys and sells alike.
            pre_val = sign * (rt - rb) * 100.0
            pre[key].append(pre_val)

        f_t = _fwd(e["ticker"], e["filed"], a.forward_days)
        f_b = _fwd(BENCH, e["filed"], a.forward_days)
        post_val = None
        if f_t and f_b:
            post_val = sign * (f_t[0] - f_b[0]) * 100.0
            post[key].append(post_val)
            post_days.append(f_t[1])

        if pre_val is not None and post_val is not None:
            paired[key].append(pre_val - post_val)

    print(f"\npre-disclosure windows unmeasurable: {n_no_pre} "
          f"(same-day transaction/filing, or no price history)")
    if post_days:
        print(f"post-disclosure window actually available: "
              f"{min(post_days)}-{max(post_days)} trading days "
              f"(asked for {a.forward_days})")
    else:
        print(f"post-disclosure window actually available: NONE — the newest "
              f"filing is too recent for any forward price to exist")

    out: dict = {"filing_days": filing_days, "n_events": len(evs),
                 "n_tickers": len(tickers), "rows": []}

    def _report(title: str, data: dict[tuple, list[float]]):
        print(f"\n{title}")
        print(f"{'action':<6s} {'lag':<7s} {'n':>5s} {'days':>5s} {'n_eff':>6s} "
              f"{'mean%':>8s} {'median%':>8s} {'sd':>7s} {'MDE%':>7s} "
              f"{'detectable':>11s}")
        for key in sorted(data):
            act, buck = key
            xs = data[key]
            if not xs:
                continue
            n = len(xs)
            mean = sum(xs) / n
            srt = sorted(xs)
            med = srt[n // 2] if n % 2 else 0.5 * (srt[n // 2 - 1] + srt[n // 2])
            sd = ((sum((x - mean) ** 2 for x in xs) / (n - 1)) ** 0.5
                  if n > 1 else None)
            # n_eff shrinks for BOTH dependencies and takes the smaller, the
            # same rule `power.effective_n` applies: distinct (ticker, filing)
            # pairs, then the measured cross-sectional correlation among names
            # filed on the same day.
            n_days = len({f for _t, f in clusters[key]})
            n_eff = min(float(len(clusters[key])), float(n),
                        _n_eff(len(clusters[key]), n_days))
            mde = PW.mde_mean(sd, n_eff) if sd else None
            det = ("-" if mde is None
                   else ("YES" if abs(mean) >= mde else "no"))
            print(f"{act:<6s} {buck:<7s} {n:>5d} {n_days:>5d} {n_eff:>6.1f} "
                  f"{mean:>8.3f} {med:>8.3f} "
                  f"{('-' if sd is None else f'{sd:7.3f}')} "
                  f"{('-' if mde is None else f'{mde:7.3f}')} {det:>11s}")
            out["rows"].append({
                "window": title, "action": act, "lag_bucket": buck,
                "n": n, "n_effective": n_eff, "n_filing_days": n_days,
                "mean_pct": mean, "median_pct": med, "sd": sd, "mde_pct": mde,
                "detectable": None if mde is None else abs(mean) >= mde})

    _report("PRE-DISCLOSURE — transaction to filing, market-adjusted, signed "
            "the insider's way\n(this return is UNCOPYABLE by construction)",
            pre)
    _report(f"POST-DISCLOSURE — filing to +{a.forward_days} trading days "
            f"(the copyable half)", post)

    # ── SS18: the question is the DIFFERENCE, on the same events ────────────
    # COPY-LAB dies if the move is already paid by the time it is disclosable.
    # That is `pre - post > 0` with its own SE, not "one table has a YES and
    # the other has a no". Paired within event, so the name and the market day
    # cancel and only the split between the two windows remains.
    print("\nPRE MINUS POST — the quantity COPY-LAB actually turns on (SS18)\n"
          "positive = more of the move accrued BEFORE it could be copied")
    print(f"{'action':<6s} {'lag':<7s} {'n':>5s} {'days':>5s} {'n_eff':>6s} "
          f"{'diff%':>8s} {'sd':>7s} {'MDE%':>7s} {'detectable':>11s}")
    for key in sorted(paired):
        act, buck = key
        xs = paired[key]
        n = len(xs)
        if n < 2:
            continue
        mean = sum(xs) / n
        sd = (sum((x - mean) ** 2 for x in xs) / (n - 1)) ** 0.5
        n_days = len({f for _t, f in clusters[key]})
        n_eff = min(float(len(clusters[key])), float(n),
                    _n_eff(len(clusters[key]), n_days))
        mde = PW.mde_mean(sd, n_eff) if sd else None
        det = "-" if mde is None else ("YES" if abs(mean) >= mde else "no")
        print(f"{act:<6s} {buck:<7s} {n:>5d} {n_days:>5d} {n_eff:>6.1f} "
              f"{mean:>8.3f} {sd:>7.3f} "
              f"{('-' if mde is None else f'{mde:7.3f}')} {det:>11s}")
        out["rows"].append({
            "window": "PRE MINUS POST (SS18 difference, paired within event)",
            "action": act, "lag_bucket": buck, "n": n,
            "n_effective": n_eff, "n_filing_days": n_days,
            "mean_pct": mean, "median_pct": None, "sd": sd, "mde_pct": mde,
            "detectable": None if mde is None else abs(mean) >= mde})

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nwritten  {p}")
    print("\nGym output. Cells are hypotheses, never claims (R2 wall 1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
