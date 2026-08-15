"""N2 — do candidate transfer slices actually SUPPLY affected episodes?

    python -m scripts.n2_transfer_slice_supply

THE QUESTION, SHARPENED BY N5 AND PRICED BY N8
===============================================
N5 found that two of the five existing transfer slices contain **zero**
VIX>=35 episodes — VIX never reached 35 between 2014 and 2019 — so a
"five-slice corpus" is, for that precursor, a corpus of three. The atlas's
binding constraint is not history, rows or tickers. It is **slices in which the
precursor fires.**

N8 then priced the target: at the crisis slices' measured dispersion (~17.7pp),
a 10pp minimum effect of interest needs ~25 independent episodes and a 3pp one
needs ~273. So the only useful thing to measure about a candidate slice is
**how many independent affected episodes it supplies**, and how many of those
are not already counted somewhere else.

THE THRESHOLD IS FIXED BEFORE MEASUREMENT, AND IT IS A FREQUENCY
=================================================================
Non-US indices have no VIX. Choosing a local volatility bar until episodes
appear is the obvious way to manufacture a corpus, so the protocol fixed the
mapping in advance:

1. measure the unconditional frequency `f` with which the US satisfies the
   incumbent precursor (VIX >= 35);
2. for every other market, set its threshold at **the same percentile `f`** of
   its OWN trailing-20d annualised realised volatility.

The bar is therefore never chosen to produce episodes — it is chosen to produce
the same RATE as the incumbent. A calmer market gets a lower absolute bar and
the same frequency, which is the point: the scarce resource is independent
crises, not large numbers.

AND THE DISCOUNT THAT STOPS THIS BEING §41 AGAIN
=================================================
**2008 is in every market.** A slice whose crises are the US crises with a
different ticker is one observation however many rows it holds, so every
candidate reports the correlation of its stress-period returns with the US and
its episode count is discounted by `1 / (1 + (m-1) * rho)` — the same
correction N1 needed after making the same mistake.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import power as PW

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "n2_slice_supply.json"

#: Fixed in the protocol before any count was read.
CANDIDATES = {
    "US_SP500":      "^GSPC",
    "Japan":         "^N225",
    "Germany":       "^GDAXI",
    "UK":            "^FTSE",
    "HongKong":      "^HSI",
    "Korea":         "^KS11",
    "Australia":     "^AXJO",
    "EM":            "EEM",
    "France":        "^FCHI",
    "Canada":        "^GSPTSE",
    "India":         "^BSESN",
    "Switzerland":   "^SSMI",
}
INCUMBENT = "US_SP500"

#: Trailing window for realised volatility, and the episode gap. Both match the
#: rules already in use so a count here is comparable to a count there.
VOL_WINDOW = 20
EPISODE_GAP_DAYS = PW.DEFAULT_EPISODE_GAP_DAYS

#: The incumbent precursor, in the shared vocabulary.
VIX_THRESHOLD = 35.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="1990-01-01")
    ap.add_argument("--end", default="2026-08-15")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    import numpy as np
    import pandas as pd
    import yfinance as yf

    # ── 1. the incumbent's FREQUENCY, which sets everyone else's bar ────────
    vix = yf.download("^VIX", start=a.start, end=a.end, progress=False)["Close"]
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()
    vix = vix.dropna()
    f = float((vix >= VIX_THRESHOLD).mean())
    print(f"incumbent precursor  VIX >= {VIX_THRESHOLD:g}")
    print(f"  VIX history        {vix.index.min().date()} -> "
          f"{vix.index.max().date()}  ({len(vix)} days)")
    print(f"  unconditional f    {f:.4%}  <- every other market's threshold is")
    print(f"                     the SAME PERCENTILE of its own realised vol\n")

    rows: dict[str, dict] = {}
    rets_by_slice: dict[str, "pd.Series"] = {}
    stress_by_slice: dict[str, "pd.Series"] = {}

    for name, tkr in CANDIDATES.items():
        try:
            px = yf.download(tkr, start=a.start, end=a.end,
                             progress=False)["Close"]
        except Exception as exc:                                 # noqa: BLE001
            print(f"  {name:<13s} {tkr:<10s} FETCH FAILED: {exc}")
            continue
        if isinstance(px, pd.DataFrame):
            px = px.squeeze()
        px = px.dropna()
        if len(px) < 500:
            print(f"  {name:<13s} {tkr:<10s} too short ({len(px)}), skipped")
            continue
        r = px.pct_change().dropna()
        rv = r.rolling(VOL_WINDOW).std() * np.sqrt(252) * 100.0
        rv = rv.dropna()
        if rv.empty:
            continue

        if name == INCUMBENT:
            # The incumbent uses its REAL precursor, not a proxy — otherwise
            # the comparison is proxy-vs-proxy and says nothing about whether
            # the proxy is faithful.
            v = vix.reindex(rv.index).ffill()
            stress = (v >= VIX_THRESHOLD) & v.notna()
            thresh = VIX_THRESHOLD
            thresh_kind = "VIX"
        else:
            thresh = float(np.nanquantile(rv.to_numpy(), 1.0 - f))
            stress = rv >= thresh
            thresh_kind = "realised vol %"

        stress = stress.fillna(False)
        pos = [i for i, x in enumerate(stress.to_numpy()) if x]
        n_days = len(pos)
        n_eps = PW.count_episodes(pos, gap_days=EPISODE_GAP_DAYS)
        rows[name] = {
            "ticker": tkr, "threshold": round(thresh, 3),
            "threshold_kind": thresh_kind,
            "first": str(rv.index.min().date()), "last": str(rv.index.max().date()),
            "n_days_total": int(len(rv)), "n_stress_days": int(n_days),
            "stress_rate": (n_days / len(rv)) if len(rv) else 0.0,
            "n_episodes_raw": int(n_eps),
        }
        rets_by_slice[name] = r
        stress_by_slice[name] = stress
        print(f"  {name:<13s} {tkr:<10s} {rv.index.min().date()} -> "
              f"{rv.index.max().date()}  bar {thresh:8.2f} ({thresh_kind})  "
              f"stress days {n_days:5d}  EPISODES {n_eps:3d}")

    if INCUMBENT not in rows:
        print("the incumbent slice failed to build; nothing to compare against")
        return 1

    # ── 2. HOW MUCH OF THIS IS ALREADY THE US? ─────────────────────────────
    print(f"\nINDEPENDENCE — 2008 is in every market. Correlation of "
          f"STRESS-PERIOD daily returns\nwith {INCUMBENT}, and the episode "
          f"count discounted by it.")
    us_r = rets_by_slice[INCUMBENT]
    us_stress = stress_by_slice[INCUMBENT]

    print(f"{'slice':<13s} {'episodes':>9s} {'rho|stress':>11s} "
          f"{'overlap d':>10s} {'INDEP eps':>10s}")
    for name, rec in rows.items():
        if name == INCUMBENT:
            rec["rho_with_us"], rec["n_episodes_independent"] = 0.0, \
                float(rec["n_episodes_raw"])
            print(f"{name:<13s} {rec['n_episodes_raw']:>9d} "
                  f"{'-':>11s} {'-':>10s} "
                  f"{rec['n_episodes_independent']:>10.1f}")
            continue
        r = rets_by_slice[name]
        joint = us_stress.reindex(r.index).fillna(False) | \
            stress_by_slice[name]
        idx = r.index.intersection(us_r.index)
        idx = [d for d in idx if bool(joint.get(d, False))]
        rho = 0.0
        if len(idx) > 30:
            rho = float(r.reindex(idx).corr(us_r.reindex(idx)))
            if rho != rho:
                rho = 0.0
        # Two co-moving slices are worth 2/(1+rho) independent slices, so a
        # candidate contributes its episodes discounted by its overlap with the
        # incumbent. rho=1 => it adds half a slice's worth; rho=0 => all of it.
        rec["rho_with_us"] = round(rho, 3)
        rec["n_overlap_days"] = len(idx)
        rec["n_episodes_independent"] = round(
            rec["n_episodes_raw"] * (1.0 - max(rho, 0.0)), 1)
        print(f"{name:<13s} {rec['n_episodes_raw']:>9d} "
              f"{rho:>11.3f} {len(idx):>10d} "
              f"{rec['n_episodes_independent']:>10.1f}")

    total_raw = sum(r["n_episodes_raw"] for r in rows.values())
    us_eps = rows[INCUMBENT]["n_episodes_raw"]

    # ── THE PAIRWISE DISCOUNT IS NOT ENOUGH, AND IT IS TOO KIND ─────────────
    # Two things are wrong with discounting each candidate by its own
    # correlation with the US:
    #
    #  1. the arithmetic. For m observations with average correlation rho the
    #     independent-equivalent count is m / (1 + (m-1) rho), so a PAIR is
    #     worth 2/(1+rho) and the candidate's marginal contribution is
    #     (1-rho)/(1+rho) — not (1-rho). At rho = 0.66 that is 0.21, not 0.34.
    #  2. the shape. Germany, France and the UK are not merely correlated with
    #     the US; they are correlated with EACH OTHER. Discounting every
    #     candidate against the incumbent alone counts the European crises
    #     three times over.
    #
    # This is §41's error waiting to happen in a new place, and it points the
    # flattering way, so the FULL correlation matrix is used: the effective
    # number of independent SLICES, times the mean episodes per slice.
    names = [n for n in rows if n in rets_by_slice]
    stress_rets = {}
    for n in names:
        st = stress_by_slice[n]
        r = rets_by_slice[n]
        stress_rets[n] = r[st.reindex(r.index).fillna(False)]
    panel = pd.DataFrame({n: rets_by_slice[n] for n in names})
    # Correlation measured on STRESS days only — that is when the episodes
    # this atlas is made of actually happen, and markets co-move more then.
    any_stress = None
    for n in names:
        s = stress_by_slice[n].reindex(panel.index).fillna(False)
        any_stress = s if any_stress is None else (any_stress | s)
    cm = panel[any_stress].corr().to_numpy()
    m = len(names)
    off = [cm[i][j] for i in range(m) for j in range(i + 1, m)
           if cm[i][j] == cm[i][j]]
    rho_bar = float(sum(off) / len(off)) if off else 1.0
    eff_slices = m / (1.0 + (m - 1) * max(rho_bar, 0.0))
    mean_eps = total_raw / m
    total_ind = eff_slices * mean_eps

    print(f"\nSUPPLY")
    print(f"  slices                          {m:8d}")
    print(f"  mean pairwise correlation on stress days   rho_bar = {rho_bar:.3f}")
    print(f"  effective INDEPENDENT slices    {eff_slices:8.2f}   "
          f"(m / (1 + (m-1) rho))")
    print(f"  incumbent (US) alone            {us_eps:8.1f} episodes")
    print(f"  all candidates, RAW             {total_raw:8.1f} episodes")
    print(f"  all candidates, INDEPENDENT     {total_ind:8.1f} episodes")
    print(f"  multiple over the incumbent     {total_ind / max(us_eps, 1):8.2f}x")
    print("\n  The raw total is the number that would have been reported by a "
          "count of\n  slices. The independent total is the number the atlas "
          "actually supplies.")

    # ── AND THE MORE DIRECT QUESTION: ARE THEY THE SAME CRISES? ─────────────
    # A return correlation is the right dependency for the ESTIMATES (co-moving
    # slices give co-moving edge measurements). It is not quite the right one
    # for counting EPISODES: two markets could have weakly correlated daily
    # returns and still have all their crises in the same months.
    #
    # So the timing is measured directly. An episode is NOVEL if no US stress
    # episode starts within +/- the episode gap of it. This answers "is this a
    # new crisis, or 2008 again with a different ticker" without going through
    # a correlation at all.
    def _episode_starts(name):
        st = stress_by_slice[name]
        idx = st.index[st.to_numpy()]
        out, prev = [], None
        for d in idx:
            if prev is None or (d - prev).days > EPISODE_GAP_DAYS * 1.5:
                out.append(d)
            prev = d
        return out

    us_starts = _episode_starts(INCUMBENT)
    print(f"\nARE THEY THE SAME CRISES? An episode is NOVEL if no US stress "
          f"episode begins\nwithin +/-{EPISODE_GAP_DAYS * 2} calendar days "
          f"of it.")
    print(f"{'slice':<13s} {'episodes':>9s} {'novel':>7s} {'novel %':>9s}")
    n_novel_total = 0
    for name in names:
        starts = _episode_starts(name)
        if name == INCUMBENT:
            rows[name]["n_episodes_novel"] = len(starts)
            n_novel_total += len(starts)
            print(f"{name:<13s} {len(starts):>9d} {len(starts):>7d} "
                  f"{'(incumbent)':>9s}")
            continue
        novel = [d for d in starts
                 if not any(abs((d - u).days) <= EPISODE_GAP_DAYS * 2
                            for u in us_starts)]
        rows[name]["n_episodes_novel"] = len(novel)
        n_novel_total += len(novel)
        pct = 100.0 * len(novel) / max(len(starts), 1)
        print(f"{name:<13s} {len(starts):>9d} {len(novel):>7d} {pct:>8.0f}%")

    print(f"\n  episodes that are NOT a US crisis in disguise: "
          f"{n_novel_total}  (raw total {total_raw:.0f})")
    print(f"  two independent measurements of the same scarcity: "
          f"{total_ind:.1f} (correlation) vs {n_novel_total} (timing)")

    # ── 3. against N8's design curve ───────────────────────────────────────
    print(f"\nAGAINST N8'S DESIGN CURVE (crisis dispersion 17.69pp)")
    print(f"  {'min effect of interest':>24s} {'episodes needed':>16s} "
          f"{'reachable?':>12s}")
    for moi in (1.0, 2.0, 3.0, 5.0, 10.0, 20.0):
        need = PW.n_required_for(moi, 17.69)
        ok = "YES" if total_ind >= need else "no"
        print(f"  {moi:>21.1f}pp {need:>16.0f} {ok:>12s}")

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(
        {"incumbent_frequency": f, "vix_threshold": VIX_THRESHOLD,
         "vol_window": VOL_WINDOW, "episode_gap_days": EPISODE_GAP_DAYS,
         "slices": rows, "total_raw_episodes": total_raw,
         "mean_pairwise_corr_on_stress": rho_bar,
         "effective_independent_slices": eff_slices,
         "total_independent_episodes": total_ind,
         "total_novel_episodes_by_timing": n_novel_total},
        indent=2), encoding="utf-8")
    print(f"\nwritten  {p}")
    print("Gym output. Cells are hypotheses, never claims (R2 wall 1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
