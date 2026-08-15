"""AUTOPSY-TO-RULE-1 — dissect resolved episodes, then test the rules elsewhere.

    python -m scripts.gym_autopsy_run --episodes <dataset_zero_*.jsonl> --limit 5

WHAT THIS DOES, IN ORDER
========================
1. Loads resolved episodes and their counterfactual surfaces.
2. Asks Optimus for a STRUCTURED autopsy of each — it is shown the outcome,
   which is the point, and the schema refuses anything that is not testable.
3. Compiles each proposed precursor and runs it on FOREIGN slices: other
   securities, other periods, other regimes. The parent episode is excluded
   mechanically, not by convention.
4. Ledgers every mechanism, including the dead ones.

WHY THE DEAD ONES ARE LEDGERED
==============================
A mechanism that fires nowhere but its parent is the expected outcome, not an
embarrassment — that is what "discovered by staring at April 2020" produces.
Dropping those silently would leave this campaign's multiple-comparison count
understated, and every deflation computed against it too generous (SS20).

THE TRANSFER SLICES ARE FOREIGN BY CONSTRUCTION
===============================================
The slices are built from securities and periods the autopsied episode does not
belong to. A "foreign" slice that happens to contain the parent is contaminated
in the direction that flatters, and nothing downstream would notice — so
`run_transfer` removes origin ids itself and reports what it removed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend import config as _config
from backend.services import research_gym as G
from backend.services.research_gym import autopsy_llm as AL

OUT_DIR = _config.OPTIMUS_LEDGER_DIR / "research_gym"
HORIZON_DAYS = 63

#: Securities the transfer slices are drawn from. Deliberately not SPY: a rule
#: extracted from index episodes and tested on the index is tested on the thing
#: it was extracted from wearing a different date.
TRANSFER_UNIVERSE = ["QQQ", "IWM", "XLF", "XLE", "XLK", "EFA"]

#: Foreign periods. Each is a distinct stress regime that the 2020-2025 dataset
#: either does not contain or contains only once, so a mechanism cannot pass by
#: rediscovering its own crisis.
TRANSFER_SLICES = {
    "dotcom_2000_2003": ("2000-01-01", "2003-12-31"),
    "gfc_2007_2010": ("2007-01-01", "2010-12-31"),
    "eurocrisis_2011_2013": ("2011-01-01", "2013-12-31"),
    "taper_2014_2016": ("2014-01-01", "2016-12-31"),
    "latecycle_2017_2019": ("2017-01-01", "2019-12-31"),
}


def _load(path: Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _rehydrate(row: dict):
    """(episode, surface) from a stored dataset-zero line."""
    e, s = row["episode"], row["surface"]
    ep = G.DecisionEpisode(
        decision_ts=e["decision_ts"], security=e["security"],
        action=e["action"], provenance=e["provenance"],
        exposure_before=e["exposure_before"], exposure_after=e["exposure_after"],
        stated_reason=e["stated_reason"], state=e["state"],
        beliefs=G.Beliefs(**{k: v for k, v in e["beliefs"].items()}),
        outcome=G.Outcome(**e["outcome"]) if e.get("outcome") else None,
        failure_mode=e.get("failure_mode", G.UNCLASSIFIED),
        failure_detail=e.get("failure_detail", ""),
        regret=e.get("regret") or {},
        evidence_strength=e.get("evidence_strength", ""),
        source=e.get("source", ""))
    surface = G.ResponseSurface(
        episode_id=s["episode_id"], security=s["security"],
        decision_ts=s["decision_ts"], horizon_days=s["horizon_days"],
        taken_policy=s["taken_policy"], cost_bps=s["cost_bps"])
    for r in s["surface"]:
        surface.results[r["policy"]] = G.PolicyResult(
            name=r["policy"], exposure_path=(),
            gross_return_pct=r["gross_return_pct"], cost_pct=r["cost_pct"],
            net_return_pct=r["net_return_pct"], turnover=r["turnover"],
            first_divergence_day=r["first_divergence_day"])
    return ep, surface


def _probe_state(tkr, slice_name, ts, vixv, dd, rv20, rv60, r1m, r3m, r6m
                 ) -> dict:
    """A probe's state, in the SHARED vocabulary and nothing less.

    Every key in `TRANSFERABLE_FEATURES` must be answerable here. The first run
    of this script shipped probes carrying four keys, the model wrote rules
    over `sp500_1m_return_pct`, and three mechanisms were reported DEAD when
    they had never been evaluated once. `assert_probe_vocabulary` below now
    fails loudly rather than letting that recur quietly.
    """
    import pandas as pd

    def at(series):
        """The value, or None. A cold rolling window is unmeasured, not zero."""
        s = series.reindex([ts], method="ffill")
        v = s.iloc[0] if len(s) else None
        return None if v is None or pd.isna(v) else float(v)

    rv_s, rv_l = at(rv20), at(rv60)
    return {
        "vix": vixv,
        "vix_bucket": G.vix_bucket(vixv),
        "drawdown_pct": at(dd),
        "ret_1m_pct": at(r1m),
        "ret_3m_pct": at(r3m),
        "ret_6m_pct": at(r6m),
        "realised_vol_20d": rv_s,
        "vol_ratio_20_60": ((rv_s / rv_l) if (rv_s is not None and rv_l)
                            else None),
        "security": tkr,
        "slice": slice_name,
    }


def assert_probe_vocabulary(state: dict) -> None:
    """Every transferable feature must be answerable on a probe, or stop.

    A missing key here does not raise later — it silently becomes "the rule did
    not fire", which reads as a refutation on every report.
    """
    from backend.services.research_gym import autopsy as AU
    missing = sorted(AU.TRANSFERABLE_FEATURES - set(state))
    if missing:
        raise SystemExit(
            f"transfer probes do not carry {missing}, which the autopsy "
            f"vocabulary declares transferable. Every rule reading one of "
            f"those would be reported as failing to transfer without ever "
            f"being run. Fix the probe, or remove the feature from "
            f"TRANSFERABLE_FEATURES — do not proceed.")


def build_transfer_slices(cost_bps: float) -> dict[str, list[tuple]]:
    """Foreign episodes: other securities, other decades, one decision a month.

    The decisions here are SYNTHETIC — one per month per security, action-free —
    because the point is not to replay a strategy but to ask what the proposed
    precursor's states did elsewhere. A mechanism claiming "extreme stress is a
    re-entry state" must show that on QQQ in 2008 whether or not anyone traded
    it then.
    """
    import numpy as np
    import pandas as pd
    import yfinance as yf

    out: dict[str, list[tuple]] = {}
    vix = yf.download("^VIX", start="1999-01-01", end="2020-01-01",
                      progress=False)["Close"]
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()

    for name, (start, end) in TRANSFER_SLICES.items():
        recs: list[tuple] = []
        for tkr in TRANSFER_UNIVERSE:
            px = yf.download(tkr, start=start, end=end, progress=False)["Close"]
            if isinstance(px, pd.DataFrame):
                px = px.squeeze()
            px = px.dropna()
            if len(px) < HORIZON_DAYS + 30:
                continue
            rets = px.pct_change().dropna()
            peak = px.rolling(252, min_periods=20).max()
            dd = (px / peak - 1.0) * 100.0
            # The rest of the shared vocabulary. Computed here so a probe
            # episode can answer every question a precursor is allowed to ask —
            # the first run failed precisely because it could not.
            rv20 = rets.rolling(20).std() * (252 ** 0.5) * 100.0
            rv60 = rets.rolling(60).std() * (252 ** 0.5) * 100.0
            r1m = px.pct_change(21) * 100.0
            r3m = px.pct_change(63) * 100.0
            r6m = px.pct_change(126) * 100.0
            # One decision per month keeps the windows from overlapping so
            # heavily that the slice is one observation with many rows.
            marks = rets.resample("MS").first().index
            for ts in marks:
                if ts not in rets.index:
                    nxt = rets.index[rets.index >= ts]
                    if len(nxt) == 0:
                        continue
                    ts = nxt[0]
                fwd = rets[rets.index > ts].head(HORIZON_DAYS)
                if len(fwd) < HORIZON_DAYS:
                    continue
                v = vix.reindex([ts], method="ffill")
                if v.empty or pd.isna(v.iloc[0]):
                    continue
                vixv = float(v.iloc[0])
                daily = [float(x) for x in fwd.to_numpy()]
                realised = float((np.prod([1 + r for r in daily]) - 1.0) * 100.0)
                ep = G.DecisionEpisode(
                    decision_ts=str(ts.date()), security=tkr,
                    action="HOLD", provenance=G.GYM,
                    exposure_before=1.0, exposure_after=1.0,
                    stated_reason="synthetic transfer probe — no decision was "
                                  "taken here; this exists to evaluate a "
                                  "precursor's states out of sample",
                    state=_probe_state(tkr, name, ts, vixv, dd, rv20, rv60,
                                       r1m, r3m, r6m),
                    beliefs=G.Beliefs(horizon_days=HORIZON_DAYS),
                    outcome=G.Outcome(resolved_at=str(fwd.index[-1].date()),
                                      horizon_days=HORIZON_DAYS,
                                      realised_return_pct=realised),
                    source="transfer_probe")
                if not recs:
                    assert_probe_vocabulary(ep.state)
                surf = G.replay(ep, daily, cost_bps=cost_bps)
                recs.append((ep, surf))
        out[name] = recs
        print(f"  slice {name:<22s} {len(recs):>5d} probe episodes")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--episodes", default=None,
                    help="dataset_zero jsonl; defaults to the newest")
    ap.add_argument("--limit", type=int, default=5,
                    help="how many episodes to autopsy (each costs one call)")
    ap.add_argument("--only-failures", action="store_true",
                    help="autopsy only episodes carrying a failure mode")
    ap.add_argument("--offline", action="store_true",
                    help="skip the LLM and the transfer fetch; validate wiring")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    path = Path(a.episodes) if a.episodes else max(
        OUT_DIR.glob("dataset_zero_*.jsonl"), key=lambda p: p.stat().st_mtime)
    rows = _load(path)
    records = [_rehydrate(r) for r in rows]
    print(f"AUTOPSY-TO-RULE-1 · {len(records)} episodes from {path.name}")
    print("Gym output is a HYPOTHESIS, never evidence (R2 wall 1).\n")

    pool = [(e, s) for e, s in records
            if e.is_resolved and (not a.only_failures
                                  or e.failure_mode not in (G.NO_FAILURE,
                                                            G.UNCLASSIFIED))]
    # Worst-first by the UNBIASED denominator. Ordering by regret-vs-best would
    # rank by how large the menu is in that state, which is G1 choosing the
    # subjects of the study.
    pool.sort(key=lambda t: -(t[0].regret.get("vs_fixed_default_pp") or 0.0))
    pool = pool[:a.limit]
    print(f"autopsying {len(pool)} episode(s), worst-first by regret vs HOLD\n")

    if a.offline:
        for ep, _ in pool:
            print(f"  {ep.decision_ts}  {ep.action:<12s} "
                  f"{ep.failure_mode:<26s} "
                  f"vs-HOLD {ep.regret.get('vs_fixed_default_pp')}")
        print("\n--offline: nothing was asked and nothing was spent.")
        return 0

    slices = build_transfer_slices(
        records[0][1].cost_bps if records else G.DEFAULT_COST_BPS)

    results, n_ok, n_dropped = [], 0, 0
    for ep, surface in pool:
        print(f"\n── {ep.decision_ts}  {ep.security}  {ep.action} "
              f"({ep.failure_mode}) ──")
        out = AL.propose(ep, surface)
        if out["autopsy"] is None:
            n_dropped += 1
            print(f"  DROPPED  {out['drop_reason']}")
            continue
        n_ok += 1
        au = out["autopsy"]
        print(f"  mechanism   {au.proposed_mechanism[:150]}")
        print(f"  precursor   {json.dumps(au.executable_precursor)[:150]}")
        print(f"  action      {au.proposed_action} vs {au.default_action}")
        print(f"  falsifier   {au.falsifier[:150]}")
        print(f"  rival       {au.alternative_explanation[:150]}")

        rep = G.adjudicate(au, slices, origin_episode_ids=[ep.episode_id])
        print(f"  VERDICT     {rep['verdict'][:200]}")
        for k, sl in rep["slices"].items():
            print(f"    {k:<22s} fired {sl['n_fired']:>4d}  "
                  f"edge {sl['mean_edge_pp']}  MDE {sl['mde_pp']}  "
                  f"{'PASS' if sl['passed'] else 'no'}")
        results.append({"episode_id": ep.episode_id,
                        "autopsy": au.as_dict(), "adjudication": rep,
                        "call": out.get("call")})

    print(f"\n{'=' * 68}")
    print(f"mechanisms proposed   {n_ok}")
    print(f"replies dropped       {n_dropped}  (counted — a model asked and "
          f"producing nothing testable belongs in the denominator)")
    exportable = sum(1 for r in results if r["adjudication"]["exportable"])
    dead = sum(1 for r in results
               if r["adjudication"]["verdict"].startswith("DEAD"))
    print(f"explains only parent  {dead}")
    print(f"exportable            {exportable}  (and export still needs a "
          f"frozen prereg and forward certification — the Gym cannot certify "
          f"itself)")

    if a.write and results:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        p = OUT_DIR / f"autopsies_{stamp}.jsonl"
        with p.open("w", encoding="utf-8") as fh:
            for r in results:
                fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        print(f"\nwritten               {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
