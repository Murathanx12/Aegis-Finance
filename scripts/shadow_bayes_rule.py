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
    ap.add_argument("--version", default="v0", choices=["v0", "v1"],
                    help="v1 = the 2026-09-29 successor (matched twin21, live-size graded book)")
    ap.add_argument("--freeze", action="store_true", help="v1: freeze the book and its twin (books.jsonl)")
    ap.add_argument("--bars-to", default=None, help="v1: last bar date (default: the plan's last closed session)")
    a = ap.parse_args(argv)
    if a.version == "v1":
        return main_v1(a)

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


# ═══════════════════════════════ v1 (successor, 2026-09-29) ═══════════════════════════════
# v0 (book 439fd84f869744e0) is frozen and is not changed. v1 answers
# docs/reviews/REVIEW_2026-09-29_SHADOW_BOOK_AND_TRUST_WEIGHTS.md F2-F5 and F9, and is
# registered as a NEW shadow contract:
#   * the evidence is the lower-noise `twin21` reading of the same receipt (F5), with the
#     "sealed" 2024-26 window's SE inflated too (it has been read repeatedly since 09-26);
#   * `ranker_lgbm` gets NO observation: its t of -0.7 was declared, never computed (F5);
#   * LLM direction keeps weight 0 because there is NO EVIDENCE FOR a weight -- not because
#     it was "measured below a coin": the AMNESIA-2 Opus arm (n 120) abstained (sd of p 0.019,
#     37 of 120 exactly 0.50) and reads CANNOT_DISTINGUISH (REVIEW_2026-09-29_FICTION_BACKTEST 1);
#   * MIN_WEIGHT is applied to the RAW weight, and the graded book is the rule's actual
#     output: the sleeve names at their live size plus SPY for the rest (F4);
#   * the twin is matched like the evidence: liquidity band x vol_63 tercile x 12-1 momentum
#     tercile, 21 draws averaged, seed recorded (F2);
#   * the kill rule has a stated power (F3); stitched tickers are cut before any feature (F9).

SEALED_SE_INFLATION_V1 = 1.5
TWIN_DRAWS_V1 = 21
KILL_Z_V1 = 1.645            # one-sided 5%
EVIDENCE_V1: dict[str, dict] = {
    "momentum_12_1": {
        "obs": [(0.018052285252756428, 2.284987598009328, 83, "dev"),
                (0.003603355961420544, 0.2422703723156821, 32, "sealed")],
        "receipt": f"{MT} cell mom_12_1@k20, twin21 (mean of 21 matched draws)",
    },
    "profitability_gp": {
        "obs": [(0.004440716760751998, 1.2554463895855492, 83, "dev"),
                (-0.0048936814789656185, -0.5564304631089773, 32, "sealed")],
        "receipt": f"{MT} cell gp_at@k20, twin21",
    },
    "ranker_lgbm": {"obs": [], "receipt": "v1: no observation -- v0's t of -0.7 was declared, never computed"},
    "llm_direction": {"obs": [], "receipt": (
        "no evidence FOR a weight, so the prior 0 stands. The AMNESIA-2 Opus arm (n 120) abstained "
        "(CANNOT_DISTINGUISH); DeepSeek at n 569 is FAILED_VARIANT on its own rule. Neither is cited as "
        "a measured 'below-coin' skill.")},
    "analyst_revisions": {"obs": [], "receipt": "S57b: brokers 50.1% hit; ANALYST-SKILL-1 never run"},
    "thesis_card": {"obs": [], "receipt": "0 graded dates"},
}


def posterior_v1(obs: list[tuple]) -> dict:
    if not obs:
        return {"m_pooled": None, "se_pooled": None, "post_mean": 0.0, "post_sd": TAU,
                "shrink": 0.0, "note": "no measurement: the prior (0) stands"}
    prec, num = 0.0, 0.0
    for m, t, n, window in obs:
        se = abs(m / t) if t else float("inf")
        se *= SELECTION_SE_INFLATION if window == "dev" else SEALED_SE_INFLATION_V1
        prec += 1.0 / se ** 2
        num += m / se ** 2
    m_pool, se_pool = num / prec, math.sqrt(1.0 / prec)
    shrink = TAU ** 2 / (TAU ** 2 + se_pool ** 2)
    return {"m_pooled": m_pool, "se_pooled": se_pool, "post_mean": m_pool * shrink,
            "post_sd": math.sqrt(1.0 / (1.0 / TAU ** 2 + 1.0 / se_pool ** 2)), "shrink": shrink}


def band_of(mdv: float) -> str:
    """The evidence's size bands (63-session median dollar volume)."""
    return "mega" if mdv >= 1e9 else "large" if mdv >= 1e8 else "mid" if mdv >= 2e7 else "small"


def features_v1(bars: pd.DataFrame) -> pd.DataFrame:
    """v0's features on stitch-cut bars, plus the twin's matching cells."""
    from backend.services.stitched_tickers import cut_reader_bars   # noqa: PLC0415
    f = features(cut_reader_bars(bars))
    px = bars.pivot_table(index="date", columns="symbol", values="close").sort_index()
    vol63 = px.pct_change().iloc[-63:].std()
    dv = (bars.assign(dv=bars.close * bars.volume).pivot_table(index="date", columns="symbol", values="dv")
          .sort_index().iloc[-63:].median())
    f["vol_63"] = vol63.reindex(f.index)
    f["mdv63"] = dv.reindex(f.index)
    f["band"] = f.mdv63.map(lambda x: band_of(x) if np.isfinite(x) else "small")
    f["vol_t"] = pd.qcut(f.vol_63.rank(method="first"), 3, labels=False)
    f["mom_t"] = pd.qcut(f.mom_12_1.rank(method="first"), 3, labels=False)
    return f


def matched_twin21(held: dict[str, float], f: pd.DataFrame, *, seed: int, exclude: set,
                   draws: int = TWIN_DRAWS_V1) -> tuple[dict[str, float], dict]:
    """{ticker: weight} of the twin sleeve: each held name replaced by a name from the same
    band x vol tercile x mom tercile cell, `draws` independent draws (without replacement
    within a draw), each carrying weight/draws. Fallback band x vol -> band -> any, counted."""
    from backend.services.llm_portfolio import is_etf                 # noqa: PLC0415
    rng = np.random.default_rng(seed)
    pool = f[~f.index.isin(exclude) & ~pd.Index(f.index).map(lambda t: is_etf(t) or "#" in str(t))]
    tw: dict[str, float] = {}
    fb = {"cell": 0, "band_vol": 0, "band": 0, "any": 0}
    for _ in range(draws):
        taken: set = set()
        for t, w in sorted(held.items()):
            r = f.loc[t]
            for lvl, mask in (("cell", (pool.band == r.band) & (pool.vol_t == r.vol_t) & (pool.mom_t == r.mom_t)),
                              ("band_vol", (pool.band == r.band) & (pool.vol_t == r.vol_t)),
                              ("band", pool.band == r.band), ("any", pool.band == pool.band)):
                c = [s for s in pool.index[mask] if s not in taken]
                if c:
                    pick = str(c[int(rng.integers(len(c)))])
                    fb[lvl] += 1
                    break
            else:
                raise SystemExit("REFUSED: the matched twin ran out of names")
            taken.add(pick)
            tw[pick] = tw.get(pick, 0.0) + w / draws
    return tw, {"seed": seed, "draws": draws, "fallbacks": fb,
                "matching": "band (mega>=1e9/large>=1e8/mid>=2e7/small, 63-session median $vol) x "
                            "vol_63 tercile x mom_12_1 tercile, over the eligible universe on the bars date"}


def kill_rule_power(held: dict[str, float], alpha21: dict[str, float], sig21: dict[str, float], *,
                    draws: int = TWIN_DRAWS_V1, sessions: int = 63, z: float = KILL_Z_V1) -> dict:
    """D = sleeve return minus twin-sleeve return over `sessions` (scale-free: the live-size
    book minus its twin, divided by the sleeve weight). sd(D) from each name's residual sd;
    the twin's 21 draws average its idiosyncratic noise down by sqrt(21)."""
    tot = sum(held.values())
    v = {t: w / tot for t, w in held.items()}
    k = sessions / 21.0
    var = sum((v[t] ** 2) * (sig21[t] ** 2) * k for t in v) * (1.0 + 1.0 / draws)
    sd = math.sqrt(var)
    mu = sum(v[t] * alpha21[t] for t in v) * k
    from math import erf, sqrt                                        # noqa: PLC0415
    Phi = lambda x: 0.5 * (1.0 + erf(x / sqrt(2.0)))                  # noqa: E731
    return {"statistic": f"D = sleeve minus matched twin21 sleeve, {sessions} sessions",
            "n_eff_names": round(1.0 / sum(x ** 2 for x in v.values()), 2),
            "sd_D": round(sd, 5), "expected_D_at_posterior": round(mu, 5),
            "kill_if": f"D < -{z} x sd_D = {-z * sd:+.4f}",
            "P_kill_if_rule_worthless": round(1 - Phi(z), 4),
            "P_kill_if_posterior_true": round(Phi(-z - mu / sd), 4),
            "P_pass_if_posterior_true (D > +z sd)": round(1 - Phi(z - mu / sd), 4),
            "mde80_one_sided_5pct": round((z + 0.8416) * sd, 5),
            "reading": ("the design can reject a rule that loses badly; it cannot confirm an edge this "
                        "small. D inside +/- z sd reads CANNOT_DISTINGUISH, which is the expected outcome "
                        "and is stated before entry")}


def main_v1(a) -> int:
    post = {k: {**posterior_v1(v["obs"]), "receipt": v["receipt"]} for k, v in EVIDENCE_V1.items()}
    te = tracking_error(EVIDENCE_V1["momentum_12_1"]["obs"])
    plan_p = OPT / "pc_book" / a.asof / "intended_book.json"
    plan = json.loads(plan_p.read_text(encoding="utf-8"))
    er_p = Path(plan["er"]["path"])
    er = json.loads(er_p.read_text(encoding="utf-8"))
    cand = sorted(er["names"].keys())
    funnel = json.loads((REPO / "backend" / "data" / "funnel_night10.json").read_text(encoding="utf-8"))
    fq = {c["ticker"]: c for c in funnel["candidates"]}
    bars_to = a.bars_to or plan["bars_gate"]["last_closed_session"]
    f = features_v1(load_bars(bars_to))
    rows = []
    for t in cand:
        e = {"momentum_12_1": expo(f.pct_mom.get(t)) if t in f.index else 0.0,
             "profitability_gp": expo(fq[t]["quality"]) if t in fq and fq[t].get("quality") is not None else 0.0}
        alpha = sum(post[k]["post_mean"] * v for k, v in e.items())
        unc = sum((v ** 2) * post[k]["post_sd"] ** 2 for k, v in e.items())
        sr = float(f.sigma_resid_21.get(t)) if t in f.index else float("nan")
        if not np.isfinite(sr):
            rows.append({"ticker": t, "alpha_21": alpha, "refused": "no 63-session residual volatility "
                         "(or a reused ticker cut to its new company)", "exposure": e})
            continue
        s2 = sr ** 2 + unc
        p = 0.5 * (1.0 + math.erf(alpha / math.sqrt(2.0 * s2)))
        raw = KELLY_FRACTION * alpha / s2 if alpha > 0 else 0.0
        rows.append({"ticker": t, "alpha_21": alpha, "sigma_resid_21": sr, "s_21": math.sqrt(s2),
                     "p_beats_twin_21": p, "w_raw": min(raw, NAME_CAP), "exposure": e,
                     "mom_12_1": float(f.mom_12_1.get(t)) if t in f.index else None})
    # MIN_WEIGHT on the RAW weight (v0 applied it after the sleeve scale and kept 4 of 10)
    ok = sorted([r for r in rows if r.get("w_raw", 0) >= MIN_WEIGHT], key=lambda r: -r["w_raw"])[:MAX_NAMES]
    tot = sum(r["w_raw"] for r in ok)
    sleeve_alpha = (sum(r["w_raw"] * r["alpha_21"] for r in ok) / tot) if ok else 0.0
    sleeve_cap = KELLY_FRACTION * sleeve_alpha / te ** 2 if te else 0.0
    scale = min(1.0, sleeve_cap / tot) if tot > 0 else 0.0
    for r in ok:
        r["w_live"] = r["w_raw"] * scale
    sleeve = sum(r["w_live"] for r in ok)
    held = {r["ticker"]: r["w_live"] for r in ok}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rule_hash = hashlib.sha256(json.dumps({"post": post, "held": held, "asof": a.asof, "bars_to": bars_to},
                                          sort_keys=True, default=str).encode()).hexdigest()[:16]
    seed = int(rule_hash, 16) % (2 ** 32)
    twin, twin_meta = (matched_twin21(held, f, seed=seed, exclude=set(held)) if held else ({}, {}))
    power = kill_rule_power(held, {r["ticker"]: r["alpha_21"] for r in ok},
                            {r["ticker"]: r["sigma_resid_21"] for r in ok}) if held else {}
    rec = {"receipt": "shadow_bayes_rule v1", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "run_id": run_id, "rule_hash": rule_hash, "asof_plan": a.asof, "bars_to": bars_to,
           "bars_asof": f.attrs.get("asof_bar"), "supersedes_for_new_entries": "SHADOW_BAYES_v0 (439fd84f869744e0, unchanged)",
           "inputs": {"plan": str(plan_p), "er": str(er_p), "funnel_generated_at": funnel.get("generated_at"),
                      "n_candidates": len(cand), "n_universe_for_percentiles": int(len(f))},
           "params": {"TAU": TAU, "SELECTION_SE_INFLATION_dev": SELECTION_SE_INFLATION,
                      "SEALED_SE_INFLATION_V1": SEALED_SE_INFLATION_V1, "KELLY_FRACTION": KELLY_FRACTION,
                      "NAME_CAP": NAME_CAP, "MAX_NAMES": MAX_NAMES, "MIN_WEIGHT_on_raw": MIN_WEIGHT,
                      "tracking_error_monthly": te},
           "posteriors": post,
           "sleeve": {"alpha_21_weighted": sleeve_alpha, "cap": sleeve_cap, "scale": scale,
                      "weight_total": sleeve, "spy_weight": 1.0 - sleeve},
           "held_live": held, "twin_sleeve": twin, "twin": twin_meta, "kill_rule": power,
           "top": ok, "all": rows}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"rule_v1_{a.asof}_{run_id}.json"
    out.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    print(f"v1 sleeve {sleeve:.4f} + SPY {1 - sleeve:.4f}; {len(held)} names; twin {len(twin)} names; "
          f"kill rule: {power.get('kill_if')}; P(kill | posterior true) {power.get('P_kill_if_posterior_true')}")
    for r in ok:
        print(f"  {r['ticker']:<6} alpha {r['alpha_21']*100:+.3f}%  w_live {r['w_live']:.4f}  "
              f"P(beat twin 21s) {r['p_beats_twin_21']:.3f}")
    print(f"-> {out}")
    if a.freeze and held:
        freeze_v1(a, rec, out)
    return 0


def freeze_v1(a, rec: dict, rule_path: Path) -> dict:
    """Freeze the graded book (the rule's actual output) and its matched twin21, append both to
    books.jsonl (append-only), and write the registration beside the rule receipt."""
    from backend.services import llm_portfolio as LP                 # noqa: PLC0415
    held, sleeve = rec["held_live"], rec["sleeve"]["weight_total"]
    fals = ("v1 kill rule: " + rec["kill_rule"]["kill_if"] + " at 63 sessions -> FAILED_VARIANT; inside "
            "+/- z sd -> CANNOT_DISTINGUISH (expected). Brier of P(beats twin) is reported, never deciding.")
    book = {"name": f"SHADOW_BAYES_v1 live-size {a.asof}", "kind": "personal",
            "objective": "beat the matched twin21 over 63 sessions with the rule's live-size output "
                         "(sleeve + SPY); the statistic is sleeve minus twin sleeve",
            "model": "shadow_bayes_rule v1 (deterministic; no LLM)",
            "strategy": f"rule receipt {rule_path.name} hash {rec['rule_hash']}; sleeve {sleeve:.4f} + SPY",
            "horizon_days": [21, 63],
            "source": {"rule_receipt": rule_path.name, "rule_hash": rec["rule_hash"], "version": "v1"},
            "positions": [{"ticker": t, "weight": w, "thesis": f"shadow v1 live-size weight {w:.4f}",
                           "falsifier": fals} for t, w in sorted(held.items())]
            + [{"ticker": "SPY", "weight": 1.0 - sleeve, "thesis": "the rest of the capital (rule output)",
                "falsifier": "n/a: the market leg, identical in the twin", "is_etf": True},
               {"ticker": "CASH", "weight": 0.0, "thesis": "fully invested", "falsifier": "n/a"}]}
    rb = LP.freeze(book, today=a.asof)
    twin = LP.freeze({"name": f"{rb['name']}__matched_twin21", "kind": "twin", "twin": "matched_twin21",
                      "objective": f"twin of {rb['name']}", "model": "twin",
                      "strategy": f"matched_twin21 twin of {rb['book_id']}; seed {rec['twin']['seed']}",
                      "parent_book_id": rb["book_id"], "parent_kind": "personal",
                      "horizon_days": [21, 63], "source": rec["twin"],
                      "positions": [{"ticker": t, "weight": w, "thesis": "matched replacement"}
                                    for t, w in sorted(rec["twin_sleeve"].items())]
                      + [{"ticker": "SPY", "weight": 1.0 - sleeve, "thesis": "the same market leg"}]},
                     today=a.asof)
    LP.append_book(rb)
    LP.append_book(twin)
    entry = str(LP.entry_session(a.asof).date())
    reg = {"registration": "SHADOW_BAYES_v1", "licence": "PRODUCT_EXPERIMENT (paper, local frozen book, "
           "no broker orders, no LLM authority)", "registered_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "book_id": rb["book_id"], "twin_book_id": twin["book_id"], "twin": rec["twin"],
           "asof": a.asof, "entry": f"open of {entry} (llm_portfolio.entry_session)",
           "rule_receipt": f"backend/data/optimus/shadow_bayes/{rule_path.name} (hash {rec['rule_hash']})",
           "rule_code": "scripts/shadow_bayes_rule.py main_v1 (uncommitted at registration: commit owed "
                        "before any read; the files are in git-tracked paths, none ignored)",
           "graded_book": "the rule's actual output: sleeve names at live size + SPY for the rest (not renormalised)",
           "primary_statistic": rec["kill_rule"], "read_dates": "21 and 63 sessions after entry",
           "secondary": ["Brier / reliability of P(beats twin 21s): resolution near zero by construction; "
                         "reported, never deciding", "book vs SPY (beta read, not a test)"],
           "relation_to_v0": "v0 439fd84f869744e0 is unchanged and still graded; see "
                             "backend/data/optimus/shadow_bayes/AMENDMENT_SHADOW_BAYES_v0_2026-09-29.json",
           "roadmap_conflict": "a new book inside ROADMAP_2026-09-28's 'no new book to 2026-10-26' window; "
                               "registered on the orchestrator's instruction of 2026-09-29 (owner away); "
                               "voidable before entry with llm_portfolio.void"}
    rp = OUT_DIR / f"REGISTRATION_SHADOW_BAYES_v1_{a.asof}_{rec['run_id']}.json"
    rp.write_text(json.dumps(reg, indent=1, default=str), encoding="utf-8")
    print(f"-> frozen {rb['book_id']} + twin {twin['book_id']}; registration {rp}")
    return reg


if __name__ == "__main__":
    raise SystemExit(main())
