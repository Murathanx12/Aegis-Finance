"""Dataset zero: dissect the sell signals that failed, one decision at a time.

    python -m scripts.gym_dissect_timing --start 2020-01-01 --end 2025-06-01

WHAT IS BEING ASKED
===================
The signal engine's market-timing backtest is the most thoroughly refuted idea
in this repository: sell-signal 3-month hit rate **28.6%** against buys at
**67.4%**, and the stated cause is that sells fired at VIX > 25 — historically
the best time to buy, not to sell.

That sentence contains a claim nobody has tested mechanically: it says the
STRESS DETECTION was fine and the MAPPING from stress to zero exposure was
wrong. If true, those are `action_mapping_failure`s, not `forecast_failure`s,
and the fix belongs in the policy layer rather than the model. If false — if the
engine simply had the direction wrong — then the policy layer is innocent and
the model is the problem. Those two readings imply completely different work,
and "28.6% hit rate" cannot distinguish them.

So this replays every sell decision under the full counterfactual menu and asks
the taxonomy instead of assuming the answer.

THE BELIEFS ARE RECONSTRUCTED, AND THAT IS DECLARED
===================================================
R3 wants beliefs recorded AT decision time. This backtest recorded none — it
stored an action and a composite score. So the beliefs here are RECONSTRUCTED,
every episode is stamped `beliefs_are_reconstructed: True`, and the
classification is built to depend only on the SIGN of the engine's view, never
on a calibration:

    a SELL signal means the engine expected down  ->  p_up < 0.5
    a BUY  signal means the engine expected up    ->  p_up > 0.5

The magnitude below is a monotone re-expression of the composite score so the
field is populated, but nothing in the forecast-vs-action-mapping split reads it
beyond its side of 0.5. Inventing a calibrated probability and then classifying
against it would be manufacturing the finding.

GYM OUTPUT IS NOT EVIDENCE
==========================
Everything this prints is `RESEARCH-GYM-1` material: hypotheses, not results.
No number here may appear in a README claim or a funding argument (R2 wall 1).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone

from backend import config as _config
from backend.services import research_gym as G

OUT_DIR = _config.OPTIMUS_LEDGER_DIR / "research_gym"

#: Trading days in the 3-month horizon the backtest scored.
HORIZON_DAYS = 63


def implied_p_up(action: str, composite_score: float) -> float:
    """A monotone re-expression of the engine's own view. NOT a calibration.

    Only its side of 0.5 is used downstream. The magnitude exists so the field
    is not None; treating it as a probability the engine actually held would be
    an invention, and it is flagged as reconstructed on every episode.
    """
    s = max(-1.0, min(1.0, float(composite_score) / 100.0
                      if abs(composite_score) > 1.0 else float(composite_score)))
    p = 0.5 + 0.4 * s
    if action.upper().startswith("SELL") or action.upper() == "REDUCE":
        return min(p, 0.45)
    if action.upper().startswith("BUY") or action.upper() == "ADD":
        return max(p, 0.55)
    return p


def exposure_for(action: str) -> float:
    """The exposure the timing strategy actually took. Fractions, never percent."""
    a = action.upper()
    if "STRONG_SELL" in a or a == "SELL":
        return 0.0
    if "REDUCE" in a:
        return 0.5
    if "STRONG_BUY" in a:
        return 1.5
    if a == "BUY" or "ADD" in a:
        return 1.25
    return 1.0


def build(start: str, end: str) -> tuple[list, dict]:
    """Run the backtest and turn every decision into an episode + surface."""
    import numpy as np
    import pandas as pd
    import yfinance as yf
    from backend.services.backtest import backtest_signal_engine

    df = backtest_signal_engine(start_date=start, end_date=end)
    if df.empty:
        return [], {"error": "backtest produced no rows"}

    buffer_end = (pd.Timestamp(end) + pd.DateOffset(months=14)).strftime("%Y-%m-%d")
    px = yf.download("^GSPC", start=start, end=buffer_end, progress=False)["Close"]
    if isinstance(px, pd.DataFrame):
        px = px.squeeze()
    rets = px.pct_change().dropna()

    # THE BASE RATES COME FROM LONG HISTORY, NOT FROM THE EPISODES BEING JUDGED.
    # Estimating "what usually follows VIX>35" from the same five decisions
    # under examination would be circular, and the circularity would be
    # invisible — the numbers would look perfectly reasonable.
    hist_px = yf.download("^GSPC", start="1990-01-01", end=buffer_end,
                          progress=False)["Close"]
    hist_vix = yf.download("^VIX", start="1990-01-01", end=buffer_end,
                           progress=False)["Close"]
    if isinstance(hist_px, pd.DataFrame):
        hist_px = hist_px.squeeze()
    if isinstance(hist_vix, pd.DataFrame):
        hist_vix = hist_vix.squeeze()
    base_rates = G.build_base_rates(hist_vix, hist_px,
                                    horizon_days=HORIZON_DAYS)
    print("conditional base rates (long history, Gym material):")
    for k, br in base_rates.items():
        if br.p_up is None:
            print(f"  {k:<10s} n=0")
            continue
        print(f"  {k:<10s} n={br.n:>5d}  P(up|state)={br.p_up:.3f}  "
              f"mean {HORIZON_DAYS}d {br.mean_forward_return_pct:+.2f}%")
    print()

    episodes = []
    for _, row in df.iterrows():
        d = pd.Timestamp(row["date"])
        fwd = rets[rets.index > d].head(HORIZON_DAYS)
        if len(fwd) < HORIZON_DAYS:
            continue                      # no full horizon — never a partial one
        daily = [float(x) for x in fwd.to_numpy()]
        action = str(row["signal_action"])
        realised = float((np.prod([1 + r for r in daily]) - 1.0) * 100.0)

        ep = G.DecisionEpisode(
            decision_ts=str(row["date"]),
            security="SPY",
            action=action,
            provenance=G.GYM,
            exposure_before=1.0,
            exposure_after=exposure_for(action),
            stated_reason="; ".join(row["reasons"])[:400]
            if isinstance(row["reasons"], list) else str(row["reasons"])[:400],
            state={
                "vix": float(row["vix"]),
                "regime": str(row["regime"]),
                "sp500_1m_return_pct": float(row["sp500_1m"]),
                "sp500_3m_return_pct": float(row["sp500_3m"]),
                "composite_score": float(row["composite_score"]),
                "confidence": row["confidence"],
                # Declared on the record, not only in this docstring.
                "beliefs_are_reconstructed": True,
                "reconstruction_note":
                    "the backtest stored an action and a composite score, not "
                    "beliefs; only the SIGN of p_up is used in attribution",
            },
            beliefs=G.Beliefs(
                p_up=implied_p_up(action, float(row["composite_score"])),
                horizon_days=HORIZON_DAYS),
            outcome=G.Outcome(resolved_at=str(fwd.index[-1].date()),
                              horizon_days=HORIZON_DAYS,
                              realised_return_pct=realised),
            source="backtest_signal_engine",
        )
        try:
            surface = G.replay(ep, daily)
        except ValueError as exc:
            print(f"  skipped {ep.decision_ts} ({action}): {exc}")
            continue
        # The base rate for THIS episode's state — the only pre-outcome
        # evidence about whether the expectation was reasonable at the time.
        br = base_rates.get(G.vix_bucket(float(row["vix"])))
        G.attribute_in_place(ep, surface, base_rate=br)
        episodes.append((ep, surface))

    return episodes, {"n_backtest_rows": len(df), "n_episodes": len(episodes),
                      "base_rates": {k: v.__dict__ for k, v in
                                     base_rates.items()}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2025-06-01")
    ap.add_argument("--write", action="store_true",
                    help="persist episodes and surfaces under research_gym/")
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    print(f"RESEARCH-GYM-1 · dataset zero · {a.start} → {a.end}")
    print("Gym output is a HYPOTHESIS, never evidence (R2 wall 1).\n")

    episodes, meta = build(a.start, a.end)
    if not episodes:
        print("no episodes:", meta)
        return 1

    sells = [(e, s) for e, s in episodes if e.exposure_after < 1.0]
    buys = [(e, s) for e, s in episodes if e.exposure_after > 1.0]
    holds = [(e, s) for e, s in episodes if e.exposure_after == 1.0]

    print(f"episodes            {len(episodes)}  "
          f"(de-risking {len(sells)}, adding {len(buys)}, hold {len(holds)})")

    def _block(title, group):
        if not group:
            return
        modes = Counter(e.failure_mode for e, _ in group)
        regrets = [s.regret_pct() for _, s in group if s.regret_pct() is not None]
        print(f"\n── {title} ({len(group)}) ──")
        print(f"  mean regret vs best alternative   "
              f"{sum(regrets)/len(regrets):+.2f} pp")
        print(f"  median realised {HORIZON_DAYS}d return          "
              f"{sorted(e.outcome.realised_return_pct for e, _ in group)[len(group)//2]:+.2f} %")
        for m, n in modes.most_common():
            print(f"  {m:<28s} {n:>3d}  ({100*n/len(group):.0f}%)")
        wins = Counter(s.best().name for _, s in group)
        print("  best alternative, by frequency:")
        for name, n in wins.most_common(5):
            print(f"    {name:<32s} {n:>3d}")

    _block("DE-RISKING DECISIONS — the 28.6% hit rate", sells)
    _block("ADDING DECISIONS — the 67.4% hit rate", buys)
    _block("HOLD DECISIONS", holds)

    # THE QUESTION ORDER 6 ASKS FIRST.
    if sells:
        modes = Counter(e.failure_mode for e, _ in sells)
        fore = modes.get(G.FORECAST_FAILURE, 0)
        act = (modes.get(G.ACTION_MAPPING_FAILURE, 0)
               + modes.get(G.SIZING_FAILURE, 0)
               + modes.get(G.TIMING_FAILURE, 0))
        print("\n" + "=" * 68)
        print("WAS THE FAILURE PERCEPTION OR POLICY?")
        print("=" * 68)
        s2f = modes.get(G.STATE_TO_FORECAST_FAILURE, 0)
        print(f"  state->forecast failures (LEARNABLE: the state's own")
        print(f"    history contradicted the expectation drawn from it) {s2f}")
        print(f"  forecast failures (unlucky draw, consistent with the")
        print(f"    state's own base rate)                              {fore}")
        print(f"  policy-layer failures (right view, wrong action)   {act}")
        print(f"    ... of which action-mapping                      "
              f"{modes.get(G.ACTION_MAPPING_FAILURE, 0)}")
        print(f"    ... of which sizing                              "
              f"{modes.get(G.SIZING_FAILURE, 0)}")
        print(f"    ... of which timing                              "
              f"{modes.get(G.TIMING_FAILURE, 0)}")
        print(f"  no failure (within {G.MATERIAL_EDGE_PCT}pp of best)          "
              f"{modes.get(G.NO_FAILURE, 0)}")
        print(f"  unclassified                                       "
              f"{modes.get(G.UNCLASSIFIED, 0)}")
        print("\n  A HYPOTHESIS, not a result. It was produced inside the Gym "
              "on\n  data this project has already studied many times, and it "
              "leaves\n  the Gym only via transfer test → prereg → forward "
              "(R2 wall 3).")

    if a.write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        p = OUT_DIR / f"dataset_zero_{stamp}.jsonl"
        with p.open("w", encoding="utf-8") as fh:
            for ep, s in episodes:
                fh.write(json.dumps({"episode": ep.as_dict(),
                                     "surface": s.as_dict()},
                                    ensure_ascii=False, default=str) + "\n")
        G.record_lineage(G.LineageRow(
            candidate_id=f"dataset_zero:{stamp}",
            campaign=G.CAMPAIGN,
            hypothesis="the timing backtest's de-risking failures are "
                       "action-mapping, not forecast, failures",
            params={"start": a.start, "end": a.end,
                    "horizon_days": HORIZON_DAYS,
                    "cost_bps": G.DEFAULT_COST_BPS},
            n_episodes=len(episodes)))
        print(f"\nwritten             {p}")
        print("lineage             row appended (R2 wall 2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
