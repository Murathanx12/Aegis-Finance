"""Shadow probabilistic decision rule -- acts on the best estimate, never on a gate.

    python -m scripts.shadow_bayes_rule --asof 2026-09-28            # compute + receipt
    python -m scripts.shadow_bayes_rule --asof 2026-09-28 --book-out book.json

WHY (Murat, 2026-09-28 20:30 HKT)
=================================
> "i am worried we are too focused on being certain, we dont have to, its a
>  game of probability and we need to make the best call based on the data and
>  the news."

The live plan (`sim_run.u_plan`) waits for gates: a component contributes to
E[r] only after `ER_MIN_GRADED` = 30 graded date blocks, and until then the
PROBE book is the funnel's order at an equal 2% per name. This script is the
alternative the owner asked for, written as a SHADOW: it never touches the live
plan path, never calls a broker and changes no limit.

THE RULE (every number below is printed on the receipt)
=======================================================
1. Each signal j has an on-disk measurement of its edge: a mean monthly excess
   of its top-20 book over a matched twin, with a standard error. Evidence the
   rule was chosen on (the pre-2024 `dev` window of a library registered after
   looking) has its SE multiplied by `SELECTION_SE_INFLATION`; the sealed
   2024-26 window is taken at face value.
2. Prior on every edge: N(0, TAU^2), centred on ZERO edge. Posterior mean =
   m * TAU^2 / (TAU^2 + se^2). No pass/fail: a noisy positive result gets a
   small positive weight, an absent measurement gets exactly its prior (0), a
   negative one gets a small negative weight.
3. A name's expected 21-session excess over SPY:
       alpha_i = sum_j post_mean_j * e_ij,   e_ij = clip((pct_ij - 0.5)/0.5, -1, 1)
   where pct_ij is the name's percentile on signal j over the whole eligible
   universe. Unknown exposure -> e_ij = 0.
4. Uncertainty: s_i^2 = sigma_resid_i^2 + sum_j e_ij^2 post_sd_j^2, with
   sigma_resid the 63-session residual (vs SPY) volatility scaled to 21
   sessions. P(name beats SPY over 21 sessions) = Phi(alpha_i / s_i).
5. Size: w_i = KELLY_FRACTION * alpha_i / s_i^2 for alpha_i > 0 (long only),
   each w_i <= NAME_CAP. The SLEEVE total is capped at
   KELLY_FRACTION * alpha_sleeve / TE^2 with TE the measured monthly tracking
   error of the dominant signal's top-20 book vs its twin -- the names in a
   factor sleeve are one correlated bet, not ten independent ones. The rest of
   the capital is SPY.

LICENCE: PRODUCT_EXPERIMENT. Paper only; no LLM authority; no broker call.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg  # noqa: E402

OPT = Path(_cfg.OPTIMUS_LEDGER_DIR)
BARS = OPT / "prices_deep" / "bars.parquet"
OUT_DIR = OPT / "shadow_bayes"

#: Prior sd of a TRUE monthly edge of a top-20 sleeve over its matched twin.
#: The largest published anomalies are ~0.5-1%/month gross long-short; a
#: long-only top-20 book net of costs vs a matched twin should be smaller.
TAU = 0.005
#: Evidence from the window a library was chosen on counts half as much
#: (SE x2 = variance x4 is harsher; x2 on the SE is the declared choice).
SELECTION_SE_INFLATION = 2.0
KELLY_FRACTION = 0.25
#: The existing EXPLOIT per-name cap (config.ER_EXPLOIT_MAX_WEIGHT); not changed.
NAME_CAP = float(getattr(_cfg, "ER_EXPLOIT_MAX_WEIGHT", 0.10))
MAX_NAMES = 10
MIN_WEIGHT = 0.005

MT = "backend/data/optimus/signal_structure/matched_twins_2026-09-27T082553Z.json"

#: Each component: the observations that measure it. (mean monthly excess vs
#: twin, t, n_months, window). A component with NO observation keeps its prior.
EVIDENCE: dict[str, dict] = {
    "momentum_12_1": {
        "obs": [(0.021664328657975226, 2.5896359145902106, 83, "dev"),
                (0.007918299491749823, 0.4589010967024443, 32, "sealed")],
        "receipt": f"{MT} cell mom_12_1@k20",
    },
    "profitability_gp": {
        "obs": [(0.004219706270826437, 0.854448512831128, 83, "dev"),
                (-0.006218478932468604, -0.6870447501399628, 32, "sealed")],
        "receipt": f"{MT} cell gp_at@k20; consistent with xs_ranker/bakeoff_fundamentals.json "
                   "(-1.34%/21 sessions, t -2.55, not pooled: same years)",
    },
    "ranker_lgbm": {
        # §59: gross +0.28%/21d vs a 35 bps toll on 122 blocks; t of the net
        # is not on the receipt, so it is taken as ~-0.7 (declared).
        "obs": [(-0.0007, -0.7, 122, "sealed")],
        "receipt": "memory §59 / xs_ranker bake-off; ranking.json top20_net_rel_21d -1.07% on 2026-09-25",
    },
    "investigator_dir": {
        # direction hit 48-49% held out; lane X: deepseek-flash 48-49% after cutoff
        "obs": [], "receipt": "lane_x_experiments_2026-09-28.md; §64 (skill is MAGNITUDE, direction -8.7%)",
    },
    "analyst_revisions": {"obs": [], "receipt": "S57b: brokers 50.1% hit; ANALYST-SKILL-1 never run"},
    "thesis_card": {"obs": [], "receipt": "refit_2026-09-28.json: 0 graded dates"},
    "catalyst_pdufa": {"obs": [], "receipt": "er_2026-09-27.json: no dated PDUFA inside 21 sessions"},
    "kronos": {"obs": [], "receipt": "experiments_2026-09-28: worse than trailing vol on 26/26 dates"},
}


def posterior(obs: list[tuple]) -> dict:
    if not obs:
        return {"m_pooled": None, "se_pooled": None, "post_mean": 0.0, "post_sd": TAU,
                "shrink": 0.0, "note": "no measurement: the prior (0) stands"}
    prec, num = 0.0, 0.0
    for m, t, n, window in obs:
        se = abs(m / t) if t else float("inf")
        if window == "dev":
            se *= SELECTION_SE_INFLATION
        prec += 1.0 / se ** 2
        num += m / se ** 2
    m_pool, se_pool = num / prec, math.sqrt(1.0 / prec)
    shrink = TAU ** 2 / (TAU ** 2 + se_pool ** 2)
    return {"m_pooled": m_pool, "se_pooled": se_pool, "post_mean": m_pool * shrink,
            "post_sd": math.sqrt(1.0 / (1.0 / TAU ** 2 + 1.0 / se_pool ** 2)),
            "shrink": shrink}


def tracking_error(obs: list[tuple]) -> float:
    """Monthly sd of rule-minus-twin, from the dev window's SE and n."""
    for m, t, n, window in obs:
        if window == "dev" and t:
            return abs(m / t) * math.sqrt(n)
    return 0.08


def load_bars(asof: str) -> pd.DataFrame:
    import pyarrow.parquet as pq
    start = pd.Timestamp(asof) - pd.Timedelta(days=420)
    t = pq.read_table(BARS, columns=["symbol", "date", "close", "volume"],
                      filters=[("date", ">=", start), ("date", "<=", pd.Timestamp(asof))])
    return t.to_pandas()


def features(bars: pd.DataFrame) -> pd.DataFrame:
    px = bars.pivot_table(index="date", columns="symbol", values="close").sort_index()
    dv = (bars.assign(dv=bars.close * bars.volume)
          .pivot_table(index="date", columns="symbol", values="dv").sort_index())
    n = len(px)
    if n < 253:
        raise SystemExit(f"REFUSED: only {n} sessions of bars; 12-1 momentum needs 253")
    mom = px.iloc[-22] / px.iloc[-253] - 1.0
    ret = px.pct_change().iloc[-63:]
    spy = ret["SPY"]
    var_spy = spy.var()
    beta = ret.apply(lambda c: c.cov(spy)) / var_spy
    resid = ret - np.outer(spy.values, beta.reindex(ret.columns).values)
    sig_resid_21 = resid.std() * math.sqrt(21)
    mdv = dv.iloc[-60:].median()
    f = pd.DataFrame({"mom_12_1": mom, "beta": beta, "sigma_resid_21": sig_resid_21,
                      "median_dollar_vol": mdv, "last_close": px.iloc[-1],
                      "n_obs": px.iloc[-253:].notna().sum()})
    f = f[(f.n_obs >= 240) & (f.median_dollar_vol >= 5e6) & f.mom_12_1.notna()]
    f["pct_mom"] = f.mom_12_1.rank(pct=True)
    f.attrs["asof_bar"] = str(px.index[-1].date())
    return f


def expo(p: float | None) -> float:
    if p is None or not np.isfinite(p):
        return 0.0
    return float(np.clip((p - 0.5) / 0.5, -1.0, 1.0))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--asof", required=True, help="the plan asof whose candidate set is scored")
    ap.add_argument("--book-out", default=None, help="also write a freezable book JSON here")
    a = ap.parse_args(argv)

    post = {k: {**posterior(v["obs"]), "receipt": v["receipt"]} for k, v in EVIDENCE.items()}
    te = tracking_error(EVIDENCE["momentum_12_1"]["obs"])

    plan_p = OPT / "pc_book" / a.asof / "intended_book.json"
    plan = json.loads(plan_p.read_text(encoding="utf-8"))
    er_p = Path(plan["er"]["path"])
    er = json.loads(er_p.read_text(encoding="utf-8"))
    cand = sorted(er["names"].keys())
    funnel = json.loads((REPO / "backend" / "data" / "funnel_night10.json").read_text(encoding="utf-8"))
    fq = {c["ticker"]: c for c in funnel["candidates"]}

    bars = load_bars(plan["bars_gate"]["last_closed_session"])
    f = features(bars)
    rows = []
    for t in cand:
        h21 = (er["names"][t].get("h21") or {})
        det = h21.get("detail") or {}
        in_rank_top = (det.get("ranker") or {}).get("decile") == 9
        e = {
            "momentum_12_1": expo(f.pct_mom.get(t)) if t in f.index else 0.0,
            # the funnel's `quality` is a gross-profitability percentile in [0,1]
            "profitability_gp": expo(fq[t]["quality"]) if t in fq and fq[t].get("quality") is not None else 0.0,
            "ranker_lgbm": 1.0 if in_rank_top else 0.0,
        }
        alpha = sum(post[k]["post_mean"] * v for k, v in e.items())
        unc = sum((v ** 2) * post[k]["post_sd"] ** 2 for k, v in e.items())
        sr = float(f.sigma_resid_21.get(t)) if t in f.index else float("nan")
        if not np.isfinite(sr):
            rows.append({"ticker": t, "alpha_21": alpha, "p_beats_spy_21": None,
                         "refused": "no 63-session residual volatility", "exposure": e})
            continue
        s2 = sr ** 2 + unc
        p = 0.5 * (1.0 + math.erf(alpha / math.sqrt(2.0 * s2)))
        raw = KELLY_FRACTION * alpha / s2 if alpha > 0 else 0.0
        rows.append({"ticker": t, "alpha_21": alpha, "sigma_resid_21": sr, "s_21": math.sqrt(s2),
                     "p_beats_spy_21": p, "w_raw": min(raw, NAME_CAP), "exposure": e,
                     "mom_12_1": float(f.mom_12_1.get(t)) if t in f.index else None})
    ok = sorted([r for r in rows if r.get("w_raw", 0) > 0], key=lambda r: -r["w_raw"])[:MAX_NAMES]
    sleeve_alpha = (sum(r["w_raw"] * r["alpha_21"] for r in ok) / sum(r["w_raw"] for r in ok)) if ok else 0.0
    sleeve_cap = KELLY_FRACTION * sleeve_alpha / te ** 2 if te else 0.0
    tot = sum(r["w_raw"] for r in ok)
    scale = min(1.0, sleeve_cap / tot) if tot > 0 else 0.0
    for r in ok:
        r["w_live_scale"] = r["w_raw"] * scale
    ok = [r for r in ok if r["w_live_scale"] >= MIN_WEIGHT] or ok[:0]
    sleeve = sum(r["w_live_scale"] for r in ok)

    probe = [{"ticker": x.get("symbol"), "weight": x.get("weight"), "state": x.get("state")}
             for x in (plan.get("book") or [])]

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rec = {
        "receipt": "shadow_bayes_rule", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "run_id": run_id, "asof_plan": a.asof, "bars_asof": f.attrs["asof_bar"],
        "inputs": {"plan": str(plan_p), "er": str(er_p), "funnel_generated_at": funnel.get("generated_at"),
                   "bars": str(BARS), "n_candidates": len(cand), "n_universe_for_percentiles": int(len(f))},
        "params": {"TAU": TAU, "SELECTION_SE_INFLATION": SELECTION_SE_INFLATION,
                   "KELLY_FRACTION": KELLY_FRACTION, "NAME_CAP": NAME_CAP, "MAX_NAMES": MAX_NAMES,
                   "tracking_error_monthly": te},
        "posteriors": post,
        "sleeve": {"alpha_21_weighted": sleeve_alpha, "cap": sleeve_cap, "scale": scale,
                   "weight_total": sleeve, "spy_weight": 1.0 - sleeve},
        "top": ok, "all": rows, "current_plan_targets": probe,
    }
    rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()[:16]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"rule_{a.asof}_{run_id}.json"
    out.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")

    print(f"posteriors (monthly edge vs matched twin; prior N(0, {TAU:.3f}^2)):")
    for k, v in post.items():
        mp = "   -   " if v["m_pooled"] is None else f"{v['m_pooled']*100:+.2f}%"
        print(f"  {k:<18} measured {mp}  shrink {v['shrink']:.2f}  posterior {v['post_mean']*100:+.3f}%/mo")
    print(f"sleeve: TE {te*100:.1f}%/mo, alpha {sleeve_alpha*100:+.3f}%, cap {sleeve_cap:.3f}, "
          f"weight {sleeve:.3f}, SPY {1-sleeve:.3f}")
    for r in ok:
        print(f"  {r['ticker']:<6} alpha {r['alpha_21']*100:+.3f}%  s {r['s_21']*100:.1f}%  "
              f"P(beat SPY 21s) {r['p_beats_spy_21']:.3f}  w {r['w_live_scale']:.4f}  mom {r['mom_12_1']:+.2f}")
    print(f"-> {out}")

    if a.book_out and ok:
        tot_s = sum(r["w_live_scale"] for r in ok)
        book = {
            "name": f"SHADOW_BAYES_v0 sleeve {a.asof}",
            "kind": "personal",
            "objective": "beat SPY over 21 and 63 sessions: the active sleeve of a shrunk-prior, "
                         "fractional-Kelly rule; the live-size book is "
                         f"{sleeve:.3f} x this sleeve + {1-sleeve:.3f} x SPY",
            "model": "shadow_bayes_rule v0 (deterministic; no LLM)",
            "strategy": (f"alpha_i = sum_j post_mean_j * e_ij; prior N(0,{TAU}^2); dev SE x{SELECTION_SE_INFLATION}; "
                         f"w = {KELLY_FRACTION} * alpha / s^2, cap {NAME_CAP}; sleeve cap by TE {te:.4f}; "
                         f"rule receipt {out.name} hash {rec['hash']}"),
            "horizon_days": [21, 63],
            "twins_requested": ["random_same_band", "spy", "ew"],
            "positions": [
                {"ticker": r["ticker"], "weight": r["w_live_scale"] / tot_s,
                 "thesis": (f"P(beats SPY over 21 sessions) = {r['p_beats_spy_21']:.3f}; "
                            f"alpha_21 {r['alpha_21']*100:+.3f}% from exposures {json.dumps({k: round(v, 3) for k, v in r['exposure'].items()})}"),
                 "falsifier": "the sleeve trails its random_same_band twin at 63 sessions, or the stated "
                              "probabilities are miscalibrated (Brier worse than 0.25) when graded"}
                for r in ok] + [{"ticker": "CASH", "weight": 0.0, "thesis": "fully invested sleeve",
                                 "falsifier": "n/a"}],
        }
        Path(a.book_out).write_text(json.dumps(book, indent=1), encoding="utf-8")
        print(f"-> book {a.book_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
