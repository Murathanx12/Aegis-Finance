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
from backend.services.research_gym import base_rate as BR

OUT_DIR = _config.OPTIMUS_LEDGER_DIR / "research_gym"
NULL_PATH = OUT_DIR / "matched_null_v1.json"

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
    print("conditional base rates (long history, Gym material)")
    print("  SS19: every row prints n_effective and its 80%-power MDE. `n` is "
          "daily\n  observations of an overlapping window and is NOT a sample "
          "size.")
    print(f"  {'state':<10s} {'n':>5s} {'n_eff':>6s} {'episodes':>9s} "
          f"{'P(up)':>6s} {'mean':>7s} {'MDE':>7s}  verdict")
    for k, br in base_rates.items():
        if br.p_up is None:
            print(f"  {k:<10s} n=0")
            continue
        p = br.power
        mde = "  n/a" if p is None or p.mde_mean_pct is None \
            else f"{p.mde_mean_pct:6.2f}"
        detectable = (p is not None and p.mde_mean_pct is not None
                      and abs(br.mean_forward_return_pct) >= p.mde_mean_pct)
        print(f"  {k:<10s} {br.n:>5d} "
              f"{(p.n_effective if p else 0):>6.1f} "
              f"{(p.n_episodes if p else 0):>9d} "
              f"{br.p_up:>6.3f} {br.mean_forward_return_pct:>+7.2f} {mde}  "
              f"{'detectable' if detectable else 'BELOW ITS OWN MDE'}")

    # THE SHAPE, TESTED AS A SHAPE (SS18). Five means printed in a column let
    # the eye supply a curve. The U-shape is a claim that the middle bucket is
    # LOWER THAN the extremes, and that is a difference — so it is measured as
    # one, with the standard error the comparison actually has at n_effective.
    trough = min((b for b in base_rates.values()
                  if b.mean_forward_return_pct is not None),
                 key=lambda b: b.mean_forward_return_pct)
    print(f"\n  IS THE U-SHAPE A SHAPE? trough = {trough.state_key} "
          f"({trough.mean_forward_return_pct:+.2f}%), each arm tested against "
          f"it as a DIFFERENCE")
    print(f"    {'arm':<10s} {'diff':>7s} {'SE':>7s} {'t':>6s} {'MDE':>7s}  "
          f"verdict")
    for key, br in base_rates.items():
        if br.state_key == trough.state_key or br.mean_forward_return_pct is None:
            continue
        d = BR.bucket_difference(br, trough)
        se = "  n/a" if d.se_pct is None else f"{d.se_pct:6.2f}"
        t = "  n/a" if d.t_stat is None else f"{d.t_stat:5.2f}"
        mde = "  n/a" if d.mde_pct is None else f"{d.mde_pct:6.2f}"
        print(f"    {key:<10s} {d.diff_pct:>+7.2f} {se} {t} {mde}  "
              f"{'detectable' if d.is_detectable else 'NOT DETECTABLE'}")

    # THE MECHANICAL CONFOUND, MEASURED RATHER THAN NOTED. VIX>=35 occurs
    # essentially only after a large fall, so part of the +6.97% is rebound
    # from a depressed price and not information in the volatility.
    ctrl = BR.drawdown_matched_control(hist_vix, hist_px,
                                       horizon_days=HORIZON_DAYS)
    print(f"\n  DOES PANIC ADD ANYTHING TO THE DRAWDOWN? "
          f"(deep = 15%+ below the trailing 252d high)")
    print(f"    {'cell':<26s} {'n':>5s} {'n_eff':>6s} {'P(up)':>6s} "
          f"{'mean':>7s} {'MDE':>7s}")
    for k in ("deep_drawdown_only", "deep_drawdown_and_panic", "panic_only"):
        b = ctrl[k]
        if b.p_up is None:
            print(f"    {k:<26s} {b.n:>5d}  — no observations")
            continue
        mde = ("  n/a" if b.power is None or b.power.mde_mean_pct is None
               else f"{b.power.mde_mean_pct:6.2f}")
        print(f"    {k:<26s} {b.n:>5d} {b.power.n_effective:>6.1f} "
              f"{b.p_up:>6.3f} {b.mean_forward_return_pct:>+7.2f} {mde}")
    d = BR.bucket_difference(ctrl["deep_drawdown_and_panic"],
                             ctrl["deep_drawdown_only"])
    if d.se_pct is not None:
        print(f"    panic's marginal contribution over the drawdown alone: "
              f"{d.diff_pct:+.2f}pp  SE {d.se_pct:.2f}  t {d.t_stat:.2f}  "
              f"{'detectable' if d.is_detectable else 'NOT DETECTABLE'}")

    # THE CORPSE AS CONTROL. "Buy when VIX spikes" is among the most published
    # and most traded rules in existence. Any Aegis re-entry mechanism is
    # measured against that naive published rule, never against a strawman.
    print("\n  CORPSE CONTROL: 'buy the VIX spike' is a widely published rule. "
          "Any\n  re-entry mechanism derived here is measured against it, not "
          "against\n  a strawman, before it may be pre-registered.")
    print()

    # THE MATCHED NULL (G1). Without it every regret number below is a maximum
    # over seventeen policies and has a large positive value for a decision
    # nobody could fault.
    matched_null = None
    if NULL_PATH.exists():
        matched_null = G.MatchedNull.read(NULL_PATH)
        print(f"matched null       {NULL_PATH.name}  universe "
              f"{matched_null.universe}  {matched_null.cost_bps}bps  "
              f"{matched_null.horizon_days}d  menu {matched_null.menu_hash}")
        if matched_null.universe != "^GSPC":
            raise SystemExit(
                f"null universe {matched_null.universe} != ^GSPC used here — "
                f"an unmatched null is worse than none")
    else:
        print("matched null       ABSENT — run scripts/gym_build_matched_null. "
              "Every\n                   regret below will be reported against "
              "the biased\n                   denominator only, and the "
              "failure gate falls back to\n                   the uncalibrated "
              "1.0pp constant.")
    print()

    # The shared-vocabulary features. Computed on the LONG history, not on the
    # backtest window: a 60-day rolling standard deviation started at
    # 2020-01-01 is NaN for its first quarter, and the first version of this
    # code filled that with 0.0 — producing episodes whose declared realised
    # volatility was exactly zero. A precursor reading `realised_vol_20d < 5`
    # would have fired on every one of them for a reason having nothing to do
    # with volatility. This repo already bans `fillna(0)` on feature matrices;
    # the same rule applies to a state vector.
    _hret = hist_px.pct_change().dropna()
    _peak = hist_px.rolling(252, min_periods=20).max()
    _dd = (hist_px / _peak - 1.0) * 100.0
    _rv20 = _hret.rolling(20).std() * (252 ** 0.5) * 100.0
    _rv60 = _hret.rolling(60).std() * (252 ** 0.5) * 100.0
    _vr = _rv20 / _rv60
    _r6m = hist_px.pct_change(126) * 100.0

    def _at(series, ts):
        """The value, or None. NEVER a stand-in — see above."""
        s = series.reindex([pd.Timestamp(ts)], method="ffill")
        v = s.iloc[0] if len(s) else None
        return None if v is None or pd.isna(v) else float(v)

    def dd_at(ts):
        return _at(_dd, ts)

    def rv_at(ts):
        return _at(_rv20, ts)

    def vr_at(ts):
        return _at(_vr, ts)

    def r6m_at(ts):
        return _at(_r6m, ts)

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
                "vix_bucket": G.vix_bucket(float(row["vix"])),
                "regime": str(row["regime"]),
                "sp500_1m_return_pct": float(row["sp500_1m"]),
                "sp500_3m_return_pct": float(row["sp500_3m"]),
                # THE SHARED NAMES. The same quantities under the vocabulary
                # the transfer corpus also speaks — a rule written over
                # `sp500_1m_return_pct` is untestable out of sample because
                # nothing outside this backtest carries that field.
                "ret_1m_pct": float(row["sp500_1m"]),
                "ret_3m_pct": float(row["sp500_3m"]),
                "ret_6m_pct": r6m_at(d),
                "drawdown_pct": dd_at(d),
                "realised_vol_20d": rv_at(d),
                "vol_ratio_20_60": vr_at(d),
                "security": "SPY",
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
        bucket = G.vix_bucket(float(row["vix"]))
        br = base_rates.get(bucket)
        G.attribute_in_place(ep, surface, base_rate=br,
                             matched_null=matched_null, state_key=bucket)
        episodes.append((ep, surface))

    return episodes, {"n_backtest_rows": len(df), "n_episodes": len(episodes),
                      "base_rates": {k: v.as_dict() for k, v in
                                     base_rates.items()},
                      "matched_null": None if matched_null is None
                      else {"universe": matched_null.universe,
                            "cost_bps": matched_null.cost_bps,
                            "horizon_days": matched_null.horizon_days,
                            "menu_hash": matched_null.menu_hash,
                            "sample": [matched_null.sample_start,
                                       matched_null.sample_end]}}


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
        raw = [e.regret.get("vs_ex_post_best_pp") for e, _ in group
               if e.regret.get("vs_ex_post_best_pp") is not None]
        dflt = [e.regret.get("vs_fixed_default_pp") for e, _ in group
                if e.regret.get("vs_fixed_default_pp") is not None]
        exc = [e.regret.get("excess_vs_matched_null_pp") for e, _ in group
               if e.regret.get("excess_vs_matched_null_pp") is not None]
        print(f"\n── {title} ({len(group)}) ──")
        # THREE DENOMINATORS, ALWAYS. Printing only the first is the G1 defect,
        # and the first is the one that always looks the most alarming.
        print(f"  mean regret vs ex-post best       "
              f"{sum(raw)/len(raw):+.2f} pp   (UPPER BOUND, biased upward by "
              f"the size of the menu)")
        if dflt:
            print(f"  mean regret vs HOLD               "
                  f"{sum(dflt)/len(dflt):+.2f} pp   (fixed default; negative "
                  f"means the action beat holding)")
        if exc:
            print(f"  mean EXCESS over matched null     "
                  f"{sum(exc)/len(exc):+.2f} pp   (n={len(exc)}; the "
                  f"skill-relevant number)")
        else:
            print("  mean EXCESS over matched null     UNAVAILABLE — no "
                  "matched null, so nothing here separates the engine from a "
                  "coin flip")
        print(f"  median realised {HORIZON_DAYS}d return          "
              f"{sorted(e.outcome.realised_return_pct for e, _ in group)[len(group)//2]:+.2f} %")
        for m, n in modes.most_common():
            strengths = Counter(e.evidence_strength for e, _ in group
                                if e.failure_mode == m and e.evidence_strength)
            tail = ("  [" + ", ".join(f"{k} {v}" for k, v
                                      in strengths.most_common()) + "]"
                    if strengths else "")
            print(f"  {m:<28s} {n:>3d}  ({100*n/len(group):.0f}%){tail}")
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
        print(f"  no failure (below the calibrated gate)             "
              f"{modes.get(G.NO_FAILURE, 0)}")
        print(f"  unclassified                                       "
              f"{modes.get(G.UNCLASSIFIED, 0)}")
        # The gate that decided all of the above, printed with its provenance.
        # The previous run used a round 1.0pp that a blameless hold clears 93%
        # of the time, so the counts measured the threshold, not the engine.
        seen = {}
        for e, _ in sells:
            c = (e.regret or {}).get("null_cell")
            if c:
                seen[(c["state_key"], c["policy"])] = c
        if seen:
            print("\n  THE GATE EACH DECISION WAS JUDGED AGAINST")
            print(f"    {'state':<10s} {'action':<12s} {'null mean':>10s} "
                  f"{'gate p90':>9s} {'n_eff':>6s}")
            for (st, pol), c in sorted(seen.items()):
                print(f"    {st:<10s} {pol:<12s} "
                      f"{c['mean_regret_pct']:>10.2f} "
                      f"{c['percentiles']['90']:>9.2f} "
                      f"{c['power']['n_effective']:>6.1f}")
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
                    "cost_bps": G.DEFAULT_COST_BPS_ONE_WAY},
            n_episodes=len(episodes)))
        print(f"\nwritten             {p}")
        print("lineage             row appended (R2 wall 2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
