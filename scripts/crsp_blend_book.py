"""CRSP_BLEND_v0: the one shadow paper book the library-on-CRSP read produced (2026-09-29).

    python -m scripts.crsp_blend_book --asof 2026-09-28            # compute + receipt (dry)
    python -m scripts.crsp_blend_book --asof 2026-09-28 --freeze   # + freeze book and matched twin21

WHAT IT IS. Four library rules, 25% of capital each, chosen AFTER reading
`crsp_rebuild/library_board_LIB_2026-09-29T0802Z__*.json` (so: a FINDING to test
forward, never a prior; licence PRODUCT_EXPERIMENT). They are the best rule of
four nearly uncorrelated clusters (pairwise rho of rule - twin between -0.14 and
+0.18 on CRSP 1991-2024):

  px_vs_ma200_large              trend in large caps (the large-cap trend/momentum cluster)
  trend_quality_trend            price/200d + profitability + low debt, SPY-trend gated
  co03_reversal_in_high_margin   5-day reversal inside high-gross-margin names
  vol_compression                lowest vol_21 / vol_63

Each sleeve holds its rule's `latest_selection` (top-k, the rule's own weights)
on the CURRENT vendor panel, built exactly as the factory builds it
(`bridge_report.build_library_panel`: stitch cut + bar-defect screen ON, SEC
fundamentals). A gated sleeve whose gate is off holds CASH (the engine's rule).

THE TWIN. Every held name is replaced by 21 draws from the same size band
(63-session median $ volume: mega >= 1e9 / large >= 1e8 / mid >= 2e7 / small) x
vol_63 tercile x 12-1 momentum tercile among eligible names on the same date --
the backtest's matching. The book is graded as book minus twin.

KILL RULE (declared here, before entry). The CRSP estimate for the blend is
+0.64%/mo rule - twin (t 5.3 on 3-month blocks, 1991-2024; 1991-2016 +0.63, t
4.6; 2017-2024 +0.68, t 2.9). Read at 63 and 126 sessions: book - twin below
-1.645 sd of its own 21-draw noise at 126 sessions -> FAILED_VARIANT; inside
+/- -> CANNOT_DISTINGUISH (the expected read: a 0.6%/mo edge needs years of
forward months to confirm; this book can only kill, not confirm, in 2026).
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
OUT_DIR = OPT / "shadow_bayes"
BOARD_GLOB = "library_board_LIB_2026-09-29T0802Z__*.json"
RULES = ("px_vs_ma200_large", "trend_quality_trend", "co03_reversal_in_high_margin", "vol_compression")
SLEEVE = 1.0 / len(RULES)
TWIN_DRAWS = 21
BANDS = ((1e9, "mega"), (1e8, "large"), (2e7, "mid"))


def band_of(mdv: float) -> str:
    if not np.isfinite(mdv):
        return "small"
    for lo, name in BANDS:
        if mdv >= lo:
            return name
    return "small"


def combine_sleeves(sleeves: dict) -> dict:
    """{rule: {ticker: weight within sleeve}} -> {ticker: book weight}, SLEEVE each;
    an empty sleeve (gate off) is CASH."""
    book: dict = {}
    cash = 0.0
    for rid, w in sleeves.items():
        tot = sum(w.values())
        if not w or tot <= 0:
            cash += SLEEVE
            continue
        for t, x in w.items():
            book[t] = book.get(t, 0.0) + SLEEVE * x / tot
    if cash:
        book["CASH"] = cash
    return book


def matched_twin(held: dict, day: pd.DataFrame, *, seed: int, draws: int = TWIN_DRAWS) -> tuple[dict, dict]:
    """`day`: one date of the panel, indexed by symbol, with eligible, median_dollar_vol,
    vol_63, mom_252_21. Each held name -> `draws` names of the same band x vol tercile x
    12-1 tercile (fallback band x vol -> band -> any), weight/draws each; held names excluded."""
    rng = np.random.default_rng(seed)
    el = day[day["eligible"].astype(bool)].copy()
    el["band"] = el["median_dollar_vol"].map(band_of)
    el["vol_t"] = pd.qcut(el["vol_63"].rank(method="first"), 3, labels=False)
    el["mom_t"] = pd.qcut(el["mom_252_21"].rank(method="first"), 3, labels=False)
    pool = el[~el.index.isin(held)]
    fb = {"cell": 0, "band_vol": 0, "band": 0, "any": 0}
    tw: dict = {}
    for _ in range(draws):
        taken: set = set()
        for t, w in sorted(held.items()):
            if t == "CASH":
                continue
            r = el.loc[t] if t in el.index else None
            levels = []
            if r is not None:
                levels = [("cell", (pool.band == r.band) & (pool.vol_t == r.vol_t) & (pool.mom_t == r.mom_t)),
                          ("band_vol", (pool.band == r.band) & (pool.vol_t == r.vol_t)),
                          ("band", pool.band == r.band)]
            levels.append(("any", pool.band == pool.band))
            for lvl, mask in levels:
                c = [s for s in pool.index[mask] if s not in taken]
                if c:
                    pick = str(c[int(rng.integers(len(c)))])
                    fb[lvl] += 1
                    break
            else:
                raise SystemExit("REFUSED: the matched twin ran out of names")
            taken.add(pick)
            tw[pick] = tw.get(pick, 0.0) + w / draws
    if "CASH" in held:
        tw["CASH"] = held["CASH"]
    return tw, {"seed": seed, "draws": draws, "fallbacks": fb,
                "matching": "band (mega>=1e9/large>=1e8/mid>=2e7/small, 63-session median $vol) x vol_63 "
                            "tercile x mom_252_21 tercile among eligible names on the bars date"}


def evidence() -> dict:
    """The blend's CRSP numbers, recomputed from the run's series (receipt paths printed)."""
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    from backend.services import strategy_library as SL              # noqa: PLC0415
    from scripts import library_on_crsp as L                         # noqa: PLC0415
    boards = sorted((OPT / "crsp_rebuild").glob(BOARD_GLOB))
    board = json.loads(boards[-1].read_text(encoding="utf-8"))
    sd = OPT / "crsp_rebuild" / f"library_series_{board['run_id']}"
    ser = {}
    for rid in RULES:
        d = pd.read_parquet(sd / f"{rid}.parquet")
        ser[rid] = d["rule_net"] - d["twin21_net"]
    s = pd.concat(ser.values(), axis=1).dropna().mean(axis=1)
    n_trials = int(board["dsr_n_trials"]["primary_all_cells_ever"]) + 2   # + the two blends read
    cell = [{"id": "blend", "active_returns": s.tolist()}]
    SL.deflate(cell, n_trials=n_trials)
    corr = pd.DataFrame(ser).dropna().corr().round(3)
    return {"board": boards[-1].name, "series_dir": sd.name, "rules": list(RULES),
            "full": CR.window_stats(s), "holdout_1991_2016": CR.window_stats(s, *L.HOLDOUT),
            "libwin_2017_2024": CR.window_stats(s, *L.LIBWIN), "years": L.year_signs(s),
            "trimmed5_mean": L.trimmed_mean(s), "loo_worst_mean": L.loo_worst_mean(s),
            "top5pct_share": L.top_share(s), "dsr": cell[0].get("dsr"), "dsr_n_trials": n_trials,
            "rule_minus_twin_corr": corr.to_dict(),
            "chosen_after_looking": True}


def main(argv=None) -> int:
    from backend.services import bar_defects as BD                   # noqa: PLC0415
    from backend.services import strategy_library as SL              # noqa: PLC0415
    from backend.services import stitched_tickers as ST              # noqa: PLC0415
    from scripts.bridge_report import build_library_panel            # noqa: PLC0415
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", required=True, help="the last closed session the bars reach")
    ap.add_argument("--freeze", action="store_true")
    a = ap.parse_args(argv)
    ev = evidence()
    print(f"evidence: blend full {ev['full']['mean_monthly']*100:+.2f}%/mo t {ev['full']['t_blocks']:+.2f}; "
          f"DSR {ev['dsr']} at n={ev['dsr_n_trials']}", flush=True)
    panel, _bars = build_library_panel()
    last = pd.Timestamp(panel["date"].max())
    if str(last.date()) != a.asof:
        raise SystemExit(f"REFUSED: the panel's last date is {last.date()}, not --asof {a.asof}")
    suspects = list(((ST.LAST_AUDIT or {}).get("defect_screen") or {}).get("suspects") or [])
    flagged = BD.flagged_keys(panel, suspects)
    day_idx = panel.index[(panel["date"] == last).to_numpy()]
    dpan = panel.loc[day_idx].reset_index(drop=True)
    pos = {s: j for j, s in enumerate(dpan["symbol"])}
    sleeves, picks_out, gates = {}, {}, {}
    for rid in RULES:
        rule = SL.rule_by_id(rid)
        g = rule.regime_gate
        on = True
        if g:
            gv = pd.to_numeric(dpan[g], errors="coerce").dropna()
            on = bool(len(gv) == 0 or float(gv.iloc[0]) > 0.5)       # NaN regime = ON (engine rule)
        gates[rid] = {"gate": g, "on": on}
        if not on:
            sleeves[rid], picks_out[rid] = {}, []
            continue
        picks = SL.latest_selection(panel, rule)
        top = np.array([pos[p["symbol"]] for p in picks])
        w = SL._weights(rule, dpan, top)
        sleeves[rid] = {p["symbol"]: float(x) for p, x in zip(picks, w)}
        picks_out[rid] = picks
    held = combine_sleeves(sleeves)
    dshare = BD.book_defect_share([{"date": last, "symbols": [t for t in held if t != "CASH"]}], flagged)
    if dshare.get("refuse"):
        raise SystemExit(f"REFUSED: bar-defect screen: {dshare}")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rule_hash = hashlib.sha256(json.dumps({"held": held, "asof": a.asof, "rules": RULES},
                                          sort_keys=True, default=str).encode()).hexdigest()[:16]
    seed = int(rule_hash, 16) % (2 ** 32)
    twin, twin_meta = matched_twin(held, dpan.set_index("symbol"), seed=seed)
    rec = {"receipt": "crsp_blend_book v0", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "run_id": run_id, "rule_hash": rule_hash, "asof": a.asof, "panel_last_date": str(last.date()),
           "bar_screen": "ON (reader default: stitch cut + defect screen)", "bar_defect_share": dshare,
           "evidence_crsp": ev, "gates": gates, "sleeve_weight": SLEEVE, "picks": picks_out,
           "held": held, "n_names": len([t for t in held if t != "CASH"]),
           "twin": twin_meta, "twin_book": twin,
           "label": "chosen AFTER looking at the CRSP board: a finding to test forward, never a prior"}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"crsp_blend_v0_{a.asof}_{run_id}.json"
    out.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    print(f"-> {out}: {rec['n_names']} names, gates {gates}, twin {len(twin)} names, defect {dshare}", flush=True)
    for rid, ps in picks_out.items():
        print(f"  {rid}: {[p['symbol'] for p in ps]}", flush=True)
    if a.freeze:
        freeze(a, rec, out)
    return 0


def freeze(a, rec: dict, rule_path: Path) -> dict:
    from backend.services import llm_portfolio as LP                 # noqa: PLC0415
    held = rec["held"]
    ev = rec["evidence_crsp"]
    fals = ("CRSP_BLEND_v0 kill rule: book minus matched twin21 below -1.645 x its 21-draw noise sd at 126 "
            "sessions -> FAILED_VARIANT; inside +/- -> CANNOT_DISTINGUISH (expected in 2026)")
    positions = [{"ticker": t, "weight": round(float(w), 8), "thesis": "CRSP_BLEND_v0 sleeve weight",
                  "falsifier": fals} for t, w in sorted(held.items()) if t != "CASH"]
    positions.append({"ticker": "CASH", "weight": round(float(held.get("CASH", 0.0)), 8),
                      "thesis": "a gated sleeve whose gate is off", "falsifier": "n/a"})
    book = {"name": f"CRSP_BLEND_v0 {a.asof}", "kind": "personal",
            "objective": "beat the matched twin21 over 63/126 sessions; the statistic is book minus twin",
            "model": "crsp_blend_book v0 (deterministic; no LLM)",
            "strategy": (f"4 library rules x 25%: {', '.join(RULES)}; receipt {rule_path.name} hash "
                         f"{rec['rule_hash']}; CRSP 1991-2024 blend rule-twin "
                         f"{ev['full']['mean_monthly']*100:+.2f}%/mo t {ev['full']['t_blocks']:.2f}")[:2000],
            "horizon_days": [21, 63, 126],
            "source": {"rule_receipt": rule_path.name, "rule_hash": rec["rule_hash"], "version": "v0"},
            "positions": positions}
    rb = LP.freeze(book, today=a.asof)
    twin_pos = [{"ticker": t, "weight": round(float(w), 8), "thesis": "matched replacement"}
                for t, w in sorted(rec["twin_book"].items()) if t != "CASH"]
    twin_pos.append({"ticker": "CASH", "weight": round(float(rec["twin_book"].get("CASH", 0.0)), 8),
                     "thesis": "the same cash leg"})
    twin = LP.freeze({"name": f"{rb['name']}__matched_twin21", "kind": "twin", "twin": "matched_twin21",
                      "objective": f"twin of {rb['name']}", "model": "twin",
                      "strategy": f"matched_twin21 twin of {rb['book_id']}; seed {rec['twin']['seed']}",
                      "parent_book_id": rb["book_id"], "parent_kind": "personal",
                      "horizon_days": [21, 63, 126], "source": rec["twin"], "positions": twin_pos},
                     today=a.asof)
    LP.append_book(rb)
    LP.append_book(twin)
    entry = str(LP.entry_session(a.asof).date())
    reg = {"registration": "CRSP_BLEND_v0",
           "licence": "PRODUCT_EXPERIMENT (paper, local frozen book, no broker orders, no LLM authority)",
           "registered_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "book_id": rb["book_id"], "twin_book_id": twin["book_id"], "twin": rec["twin"],
           "asof": a.asof, "entry": f"open of {entry} (llm_portfolio.entry_session)",
           "rules": list(RULES), "sleeve_weight": SLEEVE,
           "rule_receipt": f"backend/data/optimus/shadow_bayes/{rule_path.name} (hash {rec['rule_hash']})",
           "rule_code": "scripts/crsp_blend_book.py (uncommitted at registration: commit owed before any read)",
           "evidence": {k: ev[k] for k in ("board", "full", "holdout_1991_2016", "libwin_2017_2024", "years",
                                           "dsr", "dsr_n_trials", "chosen_after_looking")},
           "primary_statistic": "book minus matched twin21, 63 and 126 sessions after entry",
           "kill_rule": fals,
           "honest_power": ("a +0.64%/mo true edge against a ~2.5%/mo tracking sd gives a 6-month t of ~0.6: "
                            "this book can kill the blend (a large negative gap), it cannot confirm it in 2026"),
           "roadmap_conflict": ("a new book inside ROADMAP_2026-09-28's 'no new book to 2026-10-26' window; "
                                "frozen on the 2026-09-29 builder brief (owner away); voidable before entry "
                                "with llm_portfolio.void")}
    rp = OUT_DIR / f"REGISTRATION_CRSP_BLEND_v0_{a.asof}_{rec['run_id']}.json"
    rp.write_text(json.dumps(reg, indent=1, default=str), encoding="utf-8")
    print(f"-> frozen {rb['book_id']} + twin {twin['book_id']}; registration {rp}", flush=True)
    return reg


if __name__ == "__main__":
    raise SystemExit(main())
