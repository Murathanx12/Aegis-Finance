"""Declaration, run, turnover and board for `scripts/bridges_on_crsp.py` (2026-09-30).

Split out so the bridge builders stay small. Called only through
`python -m scripts.bridges_on_crsp --part declare|run|turnover|board`.
"""
from __future__ import annotations

import gc
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from scripts.bridges_on_crsp import (CS_CAP, CS_DAILY_RUN, EVENT_BRIDGE_RUN, EVENT_SOURCE_START, EVT_RUNS,
                                     FUND_RUN, JOB, LIB_RUN, OUT, PANEL_RUN, PRIOR_SEARCH, SPLITS, say)

#: the round-2 bridge run whose parquets feed the rules
BRIDGE_RUN = "PB_2026-09-29T1420Z"
BRIDGES = ("si", "f13", "eightk", "analyst2", "fund")
#: first decision date each new source may be used on (declared in `part_declare` from the bridge
#: receipts' coverage, BEFORE any rule was run); before it the columns are NaN, never 0
NEW_SOURCE_START = {
    "si": "1991-01-31",            # NYSE/AMEX only until 2003 (Nasdaq enters Compustat short interest in 2003)
    "f13": "1996-08-30",           # first fresh quarter 1996-03-31; a change needs two, public 45 days later
    "analyst2_timing": "1999-09-30",   # the IBES target flow start (event bridge)
    "analyst2_skill": "2000-12-29",    # 20 resolved raises per broker cannot exist before ~2000
    "eightk": "2014-01-31",        # the pull starts 2013-01; a full 365-day window from 2014
    "fund": "1991-01-31",
}
DESCRIPTION_ONLY = {"eightk": "8-K pull is 2013+ on 2,594 CIKs chosen from today's tickers: survivor-selected, "
                              "no design window"}
SOURCE_COLS = {
    "si": ["dtc", "si_chg_3m", "si_ratio"],
    "f13": ["inst_breadth_chg", "n_inst", "n_conc_init", "n_init"],
    "analyst2_timing": ["lead_raises_90", "chase_raises_90", "lead_minus_chase_90", "first_mover_raises_90",
                        "cluster_age_days"],
    "analyst2_skill": ["skill_net_raises_90", "unskilled_net_raises_90", "skill_first_mover_90",
                       "analyst_skill_weight", "first_mover_rank"],
    "eightk": ["n8k_90", "n101_90", "n701_90", "n502_180", "distress_365"],
}
DECISION_LINE = (
    "A rule SURVIVES iff, on the TURNOVER-SCALED Corwin-Schultz variant (rule net = flat net - measured monthly "
    "turnover x (flat net - full-CS net); twin = full CS; market costless): rule-twin > 0 AND rule-market > 0 in "
    "DESIGN (1991-2008) and in VALIDATE (2009-2016); rule-twin t >= 2 over 1991-2016 (3-month blocks); and "
    "DSR(rule-twin, 1991-2016) >= 0.95 at the FULL search count. It is a REGISTRATION CANDIDATE (job 3) only if it "
    "also has rule-market t >= 2 in VALIDATE and >= 5 of 8 VALIDATE years positive against the market. A rule whose "
    "inputs start after 2006 or are DESCRIPTION_ONLY is NOT_DECIDABLE. The full-CS variant (charged as a round "
    "trip every month) is printed beside as the upper-bound cost. 2017-2024 is read last, as description.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _missing_from_why(why: str) -> list:
    m = re.search(r"\[(.*)\]", why or "")
    return re.findall(r"'([^']+)'", m.group(1)) if m else ["?"]


def blocked_rules() -> list:
    """(rule, missing) for rules NOT_RUN on the LIB run and not run by the event runs."""
    rows = [json.loads(ln) for ln in (OUT / f"library_rules_{LIB_RUN}.jsonl").read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    ran = set()
    for r_ in EVT_RUNS:
        p = OUT / f"library_rules_{r_}.jsonl"
        if p.exists():
            ran |= {json.loads(ln)["rule"] for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()}
    return [(r["rule"], _missing_from_why(r.get("why", ""))) for r in rows
            if r.get("status") == "NOT_RUN" and r["rule"] not in ran]


def load_merged(cs: bool = False, loader=None):
    """library_on_crsp's full panel + the event bridge + every round-2 bridge, source starts applied."""
    from backend.services import crsp_event_bridge as B               # noqa: PLC0415
    from backend.services import strategy_library_ext as EXT         # noqa: PLC0415
    from backend.services import xs_ranker as XR                     # noqa: PLC0415
    from scripts import library_on_crsp as LOC                        # noqa: PLC0415
    P, meta = (loader or LOC.load_full_panel)(PANEL_RUN, FUND_RUN)
    E = pd.read_parquet(OUT / f"event_bridge_{EVENT_BRIDGE_RUN}.parquet")
    E["date"] = pd.to_datetime(E["date"])
    P = P.merge(E, on=["date", "symbol"], how="left")
    del E
    P["ins_buy_value_dv_90"] = P["ins_buy_value_90"] / P["median_dollar_vol"]
    gates = {"flow": B.FLOW_COLS, "rating": ["rating_net_90", "rating_downgrades_90", "initiations_90"],
             "target_cv": ["target_cv_180"], "insider": B.INSIDER_COLS + ["ins_buy_value_dv_90"]}
    for src, cols_ in gates.items():
        early = P["date"] < pd.Timestamp(EVENT_SOURCE_START[src])
        for c_ in cols_:
            if c_ in P.columns:
                P.loc[early, c_] = np.nan
    for b in BRIDGES:
        X = pd.read_parquet(OUT / f"pit_{b}_{BRIDGE_RUN}.parquet")
        X["date"] = pd.to_datetime(X["date"])
        dup = [c for c in X.columns if c in P.columns and c not in ("date", "symbol")]
        if dup:
            raise RuntimeError(f"bridge {b} would overwrite panel columns {dup}")
        P = P.merge(X, on=["date", "symbol"], how="left")
        del X
        gc.collect()
    for src, cols_ in SOURCE_COLS.items():
        early = P["date"] < pd.Timestamp(NEW_SOURCE_START[src])
        for c_ in cols_:
            if c_ in P.columns:
                P.loc[early, c_] = np.nan
    P["max_21"] = P["max_ret_21"]          # the panel's 21-session max daily return (bars <= d)
    P = EXT.derive_columns(P)              # ear_filed_dow from days_since_earn, now present
    meta["event_bridge"] = EVENT_BRIDGE_RUN
    meta["round2_bridge"] = BRIDGE_RUN
    if cs:
        D = pd.read_parquet(OUT / f"followups_daily_{CS_DAILY_RUN}.parquet", columns=["date", "permno", "cs_spread"])
        D["symbol"] = D["permno"].map(lambda p: f"{int(p):06d}")
        D["date"] = pd.to_datetime(D["date"])
        j = P[["date", "symbol"]].merge(D[["date", "symbol", "cs_spread"]], on=["date", "symbol"], how="left")
        cs_ = np.minimum(j["cs_spread"].to_numpy(dtype=float), CS_CAP)
        flat = np.array([XR.COST_BPS_BY_BAND[XR.liquidity_band(v)] / 1e4 if np.isfinite(v) else 0.0035
                         for v in P["median_dollar_vol"].to_numpy(dtype=float)])
        P["fwd_ret"] = P["fwd_ret"].to_numpy(dtype=float) - np.where(np.isfinite(cs_), cs_, flat)
        meta["cs"] = {"coverage": float(np.isfinite(cs_).mean())}
    return P, meta


def runnable_rules(columns) -> tuple[list, list]:
    from backend.services import strategy_library as SL              # noqa: PLC0415
    req = {r.id: list(r.requires) for r in SL.rules()}
    ok, still = [], []
    for rule, _miss in blocked_rules():
        miss = sorted(set(req.get(rule, ["?"])) - set(columns))
        if miss:
            still.append([rule, miss])
        else:
            ok.append(rule)
    return ok, still


def part_declare(run_id: str) -> int:
    import pyarrow.parquet as pq                                      # noqa: PLC0415
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    p = OUT / f"bridges_DECLARATION_{run_id}.json"
    if p.exists():
        say(f"REFUSED: {p.name} exists")
        return 2
    cov = {}
    for b in BRIDGES:
        j = json.loads((OUT / f"pit_{b}_{BRIDGE_RUN}.json").read_text(encoding="utf-8"))
        cov[b] = j.get("names_per_month_by_year")
    cols = set(pq.ParquetFile(OUT / f"library_panel_{PANEL_RUN}.parquet").schema_arrow.names)
    cols |= set(pq.ParquetFile(OUT / f"library_fund_{FUND_RUN}.parquet").schema_arrow.names)
    cols |= set(pq.ParquetFile(OUT / f"event_bridge_{EVENT_BRIDGE_RUN}.parquet").schema_arrow.names)
    for b in BRIDGES:
        cols |= set(pq.ParquetFile(OUT / f"pit_{b}_{BRIDGE_RUN}.parquet").schema_arrow.names)
    cols |= {"max_21", "ear_filed_dow", "sharpe_252", "mkt_not_stress", "low_vs_high_252", "tiebreak",
             "sector_mom", "sector_ret_21", "mom_minus_sector", "ins_buy_value_dv_90"}
    ok, still = runnable_rules(cols)
    body = {"schema": "crsp_rebuild/bridges_declaration/1", "job": JOB, "run_id": run_id,
            "licence": "PRODUCT_EXPERIMENT", "written_utc": _now(), "written_before_any_rule_ran": True,
            "bridge_run": BRIDGE_RUN, "event_bridge_run": EVENT_BRIDGE_RUN, "panel_run": PANEL_RUN,
            "splits_hold_month": SPLITS, "decision_line": DECISION_LINE,
            "honesty_note": ("2017-2024 is not a clean holdout for library rules: they were written on the "
                             "2016-2026 vendor calendar. The honest out-of-sample window for these designs is "
                             "1991-2016; validation is 2009-2016, read once."),
            "search_count_before": PRIOR_SEARCH,
            "search_count_this_run": "2 cost schemes x rules run (flat, full CS); the turnover-scaled read is a "
                                     "transformation of those two, not a new cell",
            "source_start": {**EVENT_SOURCE_START, **NEW_SOURCE_START}, "description_only": DESCRIPTION_ONLY,
            "source_start_basis": "bridge receipts' names-per-month coverage by year, read before any rule ran",
            "coverage_names_per_month_by_year": cov,
            "rules_runnable": ok, "rules_still_blocked": still,
            "blocked_reasons": {"attention_z / news_tone_z / fomo_reversal": "news corpus starts 2026-09-11: no history",
                                "short_vol_ratio_21 / _chg_21": "FINRA daily short volume starts 2009 and is not on "
                                                                "disk for the CRSP era"}}
    body["sha16"] = _sha({k: v for k, v in body.items() if k != "written_utc"})
    atomic_write_json(p, body, indent=1)
    say(f"-> {p.name}: {len(ok)} runnable, {len(still)} still blocked, sha {body['sha16']}")
    return 0


def _declaration(dec_id: str) -> dict:
    d = json.loads((OUT / f"bridges_DECLARATION_{dec_id}.json").read_text(encoding="utf-8"))
    if _sha({k: v for k, v in d.items() if k not in ("written_utc", "sha16")}) != d["sha16"]:
        raise RuntimeError("declaration hash mismatch: refused")
    return d


def part_run(dec_id: str, run_id: str, cs: bool) -> int:
    from scripts import library_on_crsp as LOC                        # noqa: PLC0415
    d = _declaration(dec_id)
    rules = list(d["rules_runnable"])
    say(f"{JOB} run {run_id}: {len(rules)} rules, cs={cs}, declaration {dec_id} sha {d['sha16']}")
    orig = LOC.load_full_panel
    LOC.load_full_panel = lambda panel_run, fund_run=None: load_merged(cs, loader=orig)
    try:
        return LOC.part_run(PANEL_RUN, run_id, only=rules, fund_run=FUND_RUN)
    finally:
        LOC.load_full_panel = orig


def part_turnover(dec_id: str, run_id: str) -> int:
    from backend.services import strategy_library as SL              # noqa: PLC0415
    from scripts.crsp_blend_followups_run import book_profile        # noqa: PLC0415
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    d = _declaration(dec_id)
    p = OUT / f"bridges_turnover_{run_id}.json"
    if p.exists():
        say(f"REFUSED: {p.name} exists")
        return 2
    P, _ = load_merged(False)
    rules = {r.id: r for r in SL.rules()}
    out = {}
    t0 = time.time()
    for rid in d["rules_runnable"]:
        try:
            out[rid] = book_profile(P, rules[rid], int(rules[rid].k))
        except Exception as e:                                       # noqa: BLE001 -- named per rule
            out[rid] = {"status": f"REFUSED: {type(e).__name__}: {e}"}
        say(f"  {rid}: {out[rid].get('turnover_per_month')} {time.time()-t0:.0f}s")
    atomic_write_json(p, {"schema": "crsp_rebuild/bridges_turnover/1", "declaration": dec_id, "written_utc": _now(),
                          "profiles": out}, indent=1)
    say(f"-> {p.name}")
    return 0


def _src_of(requires: list) -> list:
    return [s for s, cols in SOURCE_COLS.items() if set(cols) & set(requires)]


def verdict(rec: dict, decidable: bool) -> tuple[str, list]:
    """(verdict, fails) on the turnover-scaled series stats `rec` (keys vs_twin / vs_market / dsr)."""
    if not decidable:
        return "NOT_DECIDABLE", ["inputs start after 2006 or are description-only"]
    tw, mk = rec["vs_twin"], rec["vs_market"]
    fails = []
    for sp in ("design", "validate"):
        if not ((tw[sp].get("mean_monthly") or 0) > 0):
            fails.append(f"rule-twin <= 0 in {sp}")
        if not ((mk[sp].get("mean_monthly") or 0) > 0):
            fails.append(f"rule-market <= 0 in {sp}")
    if not ((tw["design_validate"].get("t_blocks") or 0) >= 2):
        fails.append("rule-twin t < 2 over 1991-2016")
    if not ((rec.get("dsr") or 0) >= 0.95):
        fails.append("DSR < 0.95 at the full count")
    if not fails:
        return "SURVIVES", fails
    if (tw["design_validate"].get("mean_monthly") or 0) <= 0:
        return "FAILED_VARIANT", fails
    return "CANNOT_DISTINGUISH", fails


#: where the fair-twin board (`scripts/hyp_twin_board.py`) writes its per-rule series
FAIR_DIR = OUT.parent / "hyp_lab"

DECISION_LINE_AMENDMENT_2026_10_06 = (
    "AMENDED 2026-10-06 (CHUNK C1), after the 2026-09-30 decomposition showed the declared variant's twin was "
    "charged the full Corwin-Schultz round trip every month while the rule paid its own turnover (106 of 161 "
    "rules beat their twin at t >= 2; 18 on gross selection). The line is unchanged EXCEPT the twin: it is now "
    "turnover-scaled with the SAME function as the rule (`matched_twins.turnover_scaled_net`) on its OWN measured "
    "turnover (the matched twin basket held as a portfolio, from the fair-twin board run), per "
    "`matched_twins.TWIN_COST_CONVENTION`. The old full-CS twin is printed in "
    "`matched_twins.UPPER_BOUND_COLUMN` and decides nothing. Changed after looking: every verdict this board "
    "issues is a re-issue, never a new claim.")


def board_columns(fl: pd.DataFrame, cs: pd.DataFrame, rule_tov: float, twin_tov: float) -> pd.DataFrame:
    """The four `MT.FOUR_COLUMNS` for one bridges rule from its flat and full-CS library series.

    * pure selection = flat rule net - flat twin21 net: in the flat run the twin is charged the
      RULE's own cost (`calendar_offsets.twin21`), so the cost cancels and this is gross - gross;
    * fair twin = both legs turnover-scaled by `MT.turnover_scaled_net`, each on its OWN turnover;
    * net minus market = the turnover-scaled rule net - the costless market;
    * UPPER BOUND = the turnover-scaled rule net - the full-CS twin (the 09-29 declared variant)."""
    from backend.services import matched_twins as MT                 # noqa: PLC0415
    common = fl.index.intersection(cs.index)
    fl, cs = fl.reindex(common), cs.reindex(common)
    rn = MT.turnover_scaled_net(fl["rule_net"], cs["rule_net"], rule_tov)
    tn = MT.turnover_scaled_net(fl["twin21_net"], cs["twin21_net"], twin_tov)
    return pd.DataFrame({MT.FOUR_COLUMNS[0]: fl["rule_net"] - fl["twin21_net"],
                         MT.FOUR_COLUMNS[1]: rn - tn,
                         MT.FOUR_COLUMNS[2]: rn - fl["market"],
                         MT.FOUR_COLUMNS[3]: rn - full_cs_twin_upper_bound(cs)})


def full_cs_twin_upper_bound(cs: pd.DataFrame) -> pd.Series:
    """The 09-29 declared twin (charged the full CS round trip every month). UPPER BOUND only."""
    return cs["twin21_net"]


def _variant_stats(dt: pd.Series, dm: pd.Series, n_total: int) -> dict:
    from backend.services import calendar_offsets as CO              # noqa: PLC0415
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    from learner.inference import deflated_sharpe                    # noqa: PLC0415
    dt, dm = dt.dropna(), dm.dropna()
    hold = pd.DatetimeIndex(dt.index) + pd.offsets.BDay(1)
    dv = dt[hold <= pd.Timestamp("2016-12-31")]
    ds = deflated_sharpe(dv.tolist(), n_trials=n_total) if len(dv) > 8 else {}
    hm = pd.DatetimeIndex(dm.index) + pd.offsets.BDay(1)
    dmv = dm[(hm >= pd.Timestamp("2009-01-01")) & (hm <= pd.Timestamp("2016-12-31"))]
    byy = CO.by_hold_year(dmv) if len(dmv) else {}
    return {"vs_twin": {k: CR.window_stats(dt, *w) for k, w in SPLITS.items()},
            "vs_market": {k: CR.window_stats(dm, *w) for k, w in SPLITS.items()},
            "dsr": ds.get("dsr"), "dsr_z": ds.get("z"),
            "validate_years_positive_vs_market": int(sum(1 for v in byy.values() if v["sum"] > 0)),
            "validate_years": int(len(byy)),
            "by_hold_year_vs_twin": {y: round(v["sum"], 4) for y, v in CO.by_hold_year(dt).items()},
            "by_hold_year_vs_market": {y: round(v["sum"], 4) for y, v in CO.by_hold_year(dm).items()},
            "loo_worst_vs_twin": {k: v for k, v in CO.loo_worst(dt).items() if k != "all"},
            "loo_worst_vs_market": {k: v for k, v in CO.loo_worst(dm).items() if k != "all"},
            "first_month": str(dt.index.min().date()) if len(dt) else None}


def part_board(dec_id: str, flat_run: str, cs_run: str, turnover_run: str, fair_run: Optional[str] = None,
               board_id: Optional[str] = None) -> int:
    """The bridges board under the fair-twin convention. REFUSES without `fair_run`: the twin's
    own turnover is measured there, and a missing turnover is never defaulted to 1.0."""
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    from backend.services import matched_twins as MT                 # noqa: PLC0415
    from backend.services import strategy_library as SL              # noqa: PLC0415
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    if not fair_run:
        say("REFUSED: --fair-run is required (the twin's own turnover comes from the fair-twin board run)")
        return 2
    d = _declaration(dec_id)
    bid = board_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    bj = OUT / f"bridges_board_{flat_run}__{fair_run}__{bid}.json"
    if bj.exists():
        say(f"REFUSED: {bj.name} exists")
        return 2
    to = json.loads((OUT / f"bridges_turnover_{turnover_run}.json").read_text(encoding="utf-8"))["profiles"]
    fair_rows = {}
    for ln in (FAIR_DIR / f"twin_board_{fair_run}.jsonl").read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            fair_rows[r["rule"]] = r
    req = {r.id: list(r.requires) for r in SL.rules()}
    fam = {r.id: r.family for r in SL.rules()}
    series, refused = {}, {}
    for rule in d["rules_runnable"]:
        a = OUT / f"library_series_{flat_run}" / f"{rule}.parquet"
        b = OUT / f"library_series_{cs_run}" / f"{rule}.parquet"
        if a.exists() and b.exists():
            series[rule] = (pd.read_parquet(a), pd.read_parquet(b))
    n_cells = 2 * len(series)
    n_total = PRIOR_SEARCH + n_cells
    starts = d["source_start"]
    rows = []
    for rule, (fl, cs) in series.items():
        tov = (to.get(rule) or {}).get("turnover_per_month")
        fr = fair_rows.get(rule) or {}
        if tov is None or fr.get("status") != "OK" or fr.get("twin_turnover") is None:
            refused[rule] = ("no measured turnover for the rule" if tov is None else
                             f"fair-twin board row not OK: {fr.get('status', 'absent')}")
            continue
        tov, twin_tov = float(tov), float(fr["twin_turnover"])
        C = board_columns(fl, cs, tov, twin_tov)
        srcs = _src_of(req.get(rule, []))
        latest_start = max([pd.Timestamp(starts[s]) for s in srcs] + [pd.Timestamp("1991-01-01")])
        decidable = latest_start <= pd.Timestamp("2006-12-31") and not (set(srcs) & set(DESCRIPTION_ONLY))
        rec = {"rule": rule, "family": fam.get(rule), "requires": req.get(rule), "sources_new": srcs,
               "cost_convention": MT.TWIN_COST_CONVENTION,
               "turnover_per_month": tov, "twin_turnover_per_month_measured": twin_tov,
               "median_pick_adv_musd_by_decade": (to.get(rule) or {}).get("median_pick_adv_musd_by_decade")}
        # the four columns side by side, every window (t on 3-month blocks, MDE beside)
        rec["four_columns"] = {c: {k: CR.window_stats(C[c].dropna(), *w) for k, w in SPLITS.items()}
                               for c in MT.FOUR_COLUMNS}
        # the declared line, read on the FAIR twin; the old variant read once more as the upper bound
        rec["fair"] = _variant_stats(C[MT.FOUR_COLUMNS[1]], C[MT.FOUR_COLUMNS[2]], n_total)
        rec["upper_bound_old_declared_variant"] = _variant_stats(C[MT.FOUR_COLUMNS[3]], C[MT.FOUR_COLUMNS[2]], n_total)
        v, fails = verdict(rec["fair"], decidable)
        rec["verdict"], rec["fails"] = v, fails
        rec["verdict_old_upper_bound_twin"] = verdict(rec["upper_bound_old_declared_variant"], decidable)[0]
        ts = rec["fair"]
        rec["registration_candidate"] = bool(
            v == "SURVIVES" and (ts["vs_market"]["validate"].get("t_blocks") or 0) >= 2
            and ts["validate_years_positive_vs_market"] >= 5)
        rows.append(rec)
    rows.sort(key=lambda r: -((r["fair"]["vs_twin"]["design_validate"].get("t_blocks")) or -9))
    counts = pd.Series([r["verdict"] for r in rows]).value_counts().to_dict() if rows else {}
    fail_counts: dict = {}
    for r in rows:
        for f in r["fails"]:
            fail_counts[f] = fail_counts.get(f, 0) + 1
    status = "OK" if not refused and rows else (f"REFUSED: no rule scored" if not rows else
                                                 f"PARTIAL: {len(refused)} rules refused (named in `refused`)")
    doc = {"schema": "crsp_rebuild/bridges_board/2", "job": JOB, "board_id": bid, "declaration": dec_id,
           "declaration_sha16": d["sha16"], "flat_run": flat_run, "cs_run": cs_run, "turnover_run": turnover_run,
           "fair_run": fair_run, "status": status, "refused": refused,
           "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0, "written_utc": _now(),
           "decision_line": DECISION_LINE, "decision_line_amendment": DECISION_LINE_AMENDMENT_2026_10_06,
           "cost_convention": MT.TWIN_COST_CONVENTION, "four_columns": list(MT.FOUR_COLUMNS),
           "upper_bound_column_never_in_verdicts": MT.UPPER_BOUND_COLUMN,
           "deflation_count": {"prior": PRIOR_SEARCH, "cells_this_run": n_cells, "n_trials_used": n_total},
           "n_rules": len(rows), "verdict_counts": counts, "fail_counts": fail_counts,
           "n_registration_candidates": sum(1 for r in rows if r["registration_candidate"]),
           "rows": rows}
    atomic_write_json(bj, doc, indent=1)
    say(f"-> {bj.name}: {len(rows)} rules {counts}; candidates {doc['n_registration_candidates']}; n {n_total}; "
        f"{status}")
    return 0 if rows else 2
