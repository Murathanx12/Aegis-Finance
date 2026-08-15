"""Does the market-relative precursor mean the same thing the VIX one means?

    python -m scripts.n2b_verify_portable_precursor

N2 found that every precursor in the library is written over `vix`, that
exactly one market has a VIX, and that the transfer atlas was therefore
unreachable in principle. `stress_pctile` is the proposed fix.

A fix that makes rules RUN everywhere and mean something different in each
place is worse than no fix, because it converts an honest UNTESTED into a
dishonest tested. So two things are measured here, in this order:

1. **Faithfulness.** On the US — the one market where both can be evaluated —
   does `stress_pctile >= 1 - f` select the same days as `vix >= 35`? Reported
   as overlap, precision and recall, not as a correlation.
2. **Reach.** On the international slices, how many days and episodes become
   evaluable that previously could not be evaluated at all?

Faithfulness first. If the translation does not reproduce the incumbent where
it can be checked, its behaviour where it cannot be checked is worthless.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import autopsy as AU
from backend.services.research_gym import market_stress as MS
from backend.services.research_gym import power as PW

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "n2b_portable_precursor.json"

MARKETS = {
    "US_SP500": "^GSPC", "Japan": "^N225", "Germany": "^GDAXI",
    "UK": "^FTSE", "HongKong": "^HSI", "Korea": "^KS11",
    "Australia": "^AXJO", "India": "^BSESN", "Switzerland": "^SSMI",
}


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

    import pandas as pd
    import yfinance as yf

    vix_rule = AU.compile_precursor(
        {"all": [{"feature": "vix", "op": ">=", "value": 35}]})
    bar = MS.frequency_matched_threshold()
    pct_rule = AU.compile_precursor(
        {"all": [{"feature": "stress_pctile", "op": ">=", "value": bar}]})
    print(f"incumbent   vix >= 35")
    print(f"portable    stress_pctile >= {bar:.4f}   "
          f"(frequency {MS.INCUMBENT_STRESS_FREQUENCY:.4%})\n")

    vix = yf.download("^VIX", start=a.start, end=a.end, progress=False)["Close"]
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()
    vix = vix.dropna()

    out: dict = {"threshold": bar, "markets": {}}

    # ── 1. FAITHFULNESS, on the only market where both can be checked ───────
    px = yf.download("^GSPC", start=a.start, end=a.end, progress=False)["Close"]
    if isinstance(px, pd.DataFrame):
        px = px.squeeze()
    px = px.dropna()
    r = px.pct_change().dropna()
    st = MS.stress_state([float(x) for x in r.to_numpy()])
    v = vix.reindex(r.index).ffill()

    both, only_vix, only_pct, neither = 0, 0, 0, 0
    for i, d in enumerate(r.index):
        s = st[i]
        if s["stress_pctile"] is None or pd.isna(v.iloc[i]):
            continue
        a_fire = vix_rule({"vix": float(v.iloc[i])})
        b_fire = pct_rule({"stress_pctile": s["stress_pctile"]})
        if a_fire and b_fire:
            both += 1
        elif a_fire:
            only_vix += 1
        elif b_fire:
            only_pct += 1
        else:
            neither += 1

    n_vix = both + only_vix
    n_pct = both + only_pct
    prec = both / n_pct if n_pct else 0.0
    rec = both / n_vix if n_vix else 0.0
    jac = both / max(both + only_vix + only_pct, 1)
    print("FAITHFULNESS on the US, where BOTH rules can be evaluated")
    print(f"  days the VIX rule fires        {n_vix:6d}")
    print(f"  days the portable rule fires   {n_pct:6d}")
    print(f"  both                           {both:6d}")
    print(f"  VIX only                       {only_vix:6d}")
    print(f"  portable only                  {only_pct:6d}")
    print(f"  precision {prec:.1%}   recall {rec:.1%}   Jaccard {jac:.1%}")
    out["faithfulness"] = {"both": both, "only_vix": only_vix,
                           "only_pctile": only_pct, "precision": prec,
                           "recall": rec, "jaccard": jac}
    if jac < 0.4:
        print("\n  *** The translation does NOT reproduce the incumbent where "
              "it can be checked.\n      Its behaviour where it cannot be "
              "checked is worthless. STOP HERE.")
    else:
        print(f"\n  The two rules pick out substantially the same state. The "
              f"portable one\n  can be trusted where the incumbent cannot be "
              f"evaluated at all.")

    # ── 2. REACH: what becomes evaluable that was not ──────────────────────
    print("\nREACH — days and episodes that were previously UNEVALUABLE")
    print(f"{'market':<13s} {'days':>7s} {'evaluable':>10s} {'fires':>7s} "
          f"{'episodes':>9s} {'vix rule?':>10s}")
    total_eps = 0
    for name, tkr in MARKETS.items():
        p = yf.download(tkr, start=a.start, end=a.end, progress=False)["Close"]
        if isinstance(p, pd.DataFrame):
            p = p.squeeze()
        p = p.dropna()
        if len(p) < 1000:
            continue
        rr = p.pct_change().dropna()
        stt = MS.stress_state([float(x) for x in rr.to_numpy()])
        evaluable = [i for i, s in enumerate(stt)
                     if s["stress_pctile"] is not None]
        fires = [i for i in evaluable
                 if pct_rule({"stress_pctile": stt[i]["stress_pctile"]})]
        eps = PW.count_episodes(fires, gap_days=PW.DEFAULT_EPISODE_GAP_DAYS)
        if name != "US_SP500":
            total_eps += eps
        vix_ok = "yes" if name == "US_SP500" else "NO — has no VIX"
        print(f"{name:<13s} {len(rr):>7d} {len(evaluable):>10d} "
              f"{len(fires):>7d} {eps:>9d} {vix_ok:>10s}")
        out["markets"][name] = {"ticker": tkr, "n_days": len(rr),
                                "n_evaluable": len(evaluable),
                                "n_fires": len(fires), "n_episodes": eps}

    print(f"\n  episodes now evaluable OUTSIDE the US: {total_eps}")
    print(f"  before this feature existed:           0")

    p_out = Path(a.out)
    p_out.parent.mkdir(parents=True, exist_ok=True)
    p_out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwritten  {p_out}")
    print("Gym output. Cells are hypotheses, never claims (R2 wall 1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
