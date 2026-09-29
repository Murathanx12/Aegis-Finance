"""Lane M1 (2026-09-28): the quarterly-offset triplet for the hold-3 leads.

    python -m scripts.calendar_offset_triplet            # the four rules of the brief
    python -m scripts.calendar_offset_triplet --offline  # SPY/IWM from the bars

Runs each rule at its frozen k through `strategy_library.run_strategy` at the
three quarterly calendars (`SL.QUARTER_OFFSETS`) AND at its default calendar
(to show which offset the board scored), costs on, and reads every offset
against SPY, IWM, the panel's random portfolio and its characteristic-matched
twin (21 draws). The verdict rule lives in `backend/services/calendar_offsets.py`
and was written before this ran.

BAR DEFECTS (2026-09-29): the panel is read through `stitched_tickers.cut_reader_bars`,
which runs `bar_defects.screen` first (zero-volume dark runs, spike prints and proven level
breaks). Every cell's book is checked with `bar_defects.book_defect_share` and REFUSED when
more than `BAR_DEFECT_BOOK_MAX_SHARE` of its slots sit on a name with a SUSPECT level break
(kept by the screen, not proven) in its 12-1 or hold window.
`--bar-screen off` is the AUDIT leg only (the pre-screen panel, to print old beside new):
it records the share and does not refuse, and its receipt says so.

WHAT IT WRITES: one JSON receipt
`strategy_library/calendar_offsets_<run_id>.json`. It writes NO panel, no facts
table, no leaderboard. It REFUSES to run when its inputs are smaller than the
reference run's (a shrink is the 2026-09-26 failure: a 25-name facts table
printed +149%), and prints the sizes it compared before any number.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                              # noqa: E402
from backend.services import bar_defects as BD                  # noqa: E402
from backend.services import calendar_offsets as CO             # noqa: E402
from backend.services import matched_twins as MT                # noqa: E402
from backend.services import strategy_library as SL             # noqa: E402
from scripts import night_backtest_factory as F                 # noqa: E402
from scripts.night_checkpoint import atomic_write_json          # noqa: E402

JOB = "M1_calendar_offset_triplet"
#: the leads of `docs/BOOK_2026-09-27_LEADS_FROM_THE_FAMILY_POOL.md` + the row the triplet was first run on
DEFAULT_RULES = ("mom_12_1_q", "disp_short_avoid", "qc470_mom252_quarterly_riskparity",
                 "mom_12_1_q_trend")
REFERENCE_RUN = "2026-09-27T082553Z"
#: a panel may lose this share of symbols vs the reference before the run refuses
SHRINK_TOLERANCE = 0.01


def peak_rss_mb() -> float | None:
    """Peak working set of this process (Windows), MB; None elsewhere."""
    try:
        class PMC(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        c = PMC()
        c.cb = ctypes.sizeof(PMC)
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        fn = k32.K32GetProcessMemoryInfo
        fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
        if fn(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return round(c.PeakWorkingSetSize / 1e6, 1)
    except Exception:                                   # noqa: BLE001 -- not Windows
        return None
    return None


def shrink_check(ref: dict, panel: pd.DataFrame, ratings_meta: dict | None) -> dict:
    """Compare this run's inputs with the reference run's receipt. Returns the
    comparison; `refuse` names every shrink."""
    rp = ref.get("panel") or {}
    now = {"rows": int(len(panel)), "dates": int(panel["date"].nunique()),
           "symbols": int(panel["symbol"].nunique()),
           "first": str(panel["date"].min().date()), "last": str(panel["date"].max().date())}
    refuse = []
    if now["symbols"] < (1.0 - SHRINK_TOLERANCE) * int(rp.get("symbols") or 0):
        refuse.append(f"panel symbols {now['symbols']} < reference {rp.get('symbols')}")
    if now["dates"] < int(rp.get("dates") or 0):
        refuse.append(f"panel dates {now['dates']} < reference {rp.get('dates')}")
    if now["first"] != rp.get("first"):
        refuse.append(f"panel starts {now['first']}, reference {rp.get('first')} (the calendar moved)")
    ref_ev = ((ref.get("chunk_d_inputs") or {}).get("ratings") or {}).get("n_events")
    cur_ev = (ratings_meta or {}).get("n_events")
    if ratings_meta is not None:
        if (ratings_meta or {}).get("status") != "OK":
            refuse.append(f"ratings attach {ratings_meta.get('status')}: {ratings_meta.get('why')}")
        elif ref_ev and cur_ev is not None and cur_ev < (1.0 - SHRINK_TOLERANCE) * ref_ev:
            refuse.append(f"revision events {cur_ev} < reference {ref_ev}")
    return {"reference_run": ref.get("run_id"), "reference_panel": rp, "this_panel": now,
            "reference_revision_events": ref_ev, "this_revision_events": cur_ev,
            "tolerance": SHRINK_TOLERANCE, "refuse": refuse}


def run_one(panel, spy, benches, rule, *, k: int, by_date, cache, grid, n_spy: int,
            n_twin: int, log=print, flagged: set | None = None, refuse_defects: bool = True) -> dict:
    hold: list = []
    sc = SL.selection_scores(panel, rule)
    m = SL.run_strategy(panel, rule, k=k, scores=sc, holdings=hold)
    if m is None or not len(m):
        raise CO.OffsetInputMissing(f"{rule.id}@k{k}: no month had k selectable names")
    dshare = BD.book_defect_share(hold, flagged or set())
    if refuse_defects and dshare["refuse"]:
        raise BD.BarDefectRefusal(f"{rule.id}@k{k}: {dshare['flagged_slots']} of {dshare['slots']} "
                                  f"slots ({dshare['share']:.1%}) on unproven level breaks; first "
                                  f"{dshare['hits'][:5]}")
    ev = SL.evaluate(m, spy, hold_months=rule.hold_months,
                     registered_utc=rule.first_registered_utc, since=_cfg.STRATEGY_LIB_SINCE,
                     iwm=benches["iwm"], random_panel=benches["random_panel"])
    rec = CO.twin_record(rule.id, k, hold, m)
    cid = f"{rule.id}@k{k}"
    tw = CO.twin21(rec, panel, cell_id=cid, by_date=by_date, cache=cache, grid=grid,
                   n_extra=CO.DRAWS_PER_SET - 1,
                   n_second_set=CO.DRAWS_PER_SET * (CO.N_SEED_SETS - 1))
    row = CO.offset_row(monthly=m, ev=ev, spy=spy, random_panel=benches["random_panel"], twin=tw,
                        n_trials_spy=n_spy, n_trials_twin=n_twin)
    row["cell"] = cid
    row["bar_defect_slots"] = dshare
    row["_series"] = pd.DataFrame({"rule_net": tw["rule_net"], "twin21_net": tw["twin21_net"],
                                   "spy": spy.reindex(tw["rule_net"].index)})
    row["rebalance_months"] = list(rule.rebalance_months) if rule.rebalance_months else None
    row["first_rebalance_offset"] = CO.offset_of_month(CO.first_rebalance_month(m))
    row["n_delisting_fills"] = ev.get("n_delisting_fills")
    row["mean_cost_bps_per_month"] = ev.get("mean_cost_bps_per_month")
    tf = row["twin"]["full"]
    tb = (row["twin"].get("setB") or {}).get("full") or {}
    sp_ = (row["twin"].get("per_draw") or {}).get("summary") or {}
    log(f"    {cid:52s} cum2020 {_p(row['cum_net_since_2020'])} sealed-SPY {_p(row['sealed_vs_spy'])} "
        f"rule-twin21 {_p(tf['mean_monthly'], 2)}/mo t_blk A {_n(tf['t_blocks'])} B {_n(tb.get('t_blocks'))} "
        f"per-draw t [{_n(sp_.get('t_min'))}, {_n(sp_.get('t_median'))}, {_n(sp_.get('t_max'))}] "
        f"MDE {_p(tf['mde_monthly'], 2)}")
    return row


def _p(v, nd=1):
    return "n/a" if v is None else f"{v * 100:+.{nd}f}%"


def _n(v, nd=2):
    return "n/a" if v is None else f"{v:+.{nd}f}"


def main(argv=None) -> int:
    from backend.services import disk_guard as DG                 # noqa: PLC0415
    from backend.services import xs_ranker as XR                  # noqa: PLC0415
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", nargs="*", default=list(DEFAULT_RULES))
    ap.add_argument("--k", type=int, default=20, help="the k every lead is frozen at")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--reference-run", default=REFERENCE_RUN)
    ap.add_argument("--bar-screen", choices=("on", "off"), default="on",
                    help="off = the AUDIT leg (pre-screen panel, no refusal); never a decision input")
    a = ap.parse_args(argv)
    BD.ENABLED = a.bar_screen == "on"
    try:
        DG.require_free(_cfg.DISK_FREE_DEAD_GB + 1, JOB, path=_cfg.OPTIMUS_LEDGER_DIR)
    except DG.DiskTooFull as exc:
        print(f"REFUSED: {exc}", flush=True)
        return 2
    t0 = time.time()
    out = F.out_dir()
    run_id = F.new_run_id()
    rp = out / f"calendar_offsets_{run_id}.json"
    if rp.exists():
        print(f"REFUSED: {rp.name} exists; a receipt is never overwritten", flush=True)
        return 2
    ref_path = out / f"run_{a.reference_run}.json"
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    rules = [SL.rule_by_id(r) for r in a.rules]
    for r in rules:
        if r.hold_months != 3:
            print(f"REFUSED: {r.id} holds {r.hold_months} months; the triplet needs 3", flush=True)
            return 2
    need_ratings = any("target_cv_180" in r.requires for r in rules)
    paths = XR.survivorship_free_paths()
    import pyarrow.parquet as pq                                   # noqa: PLC0415
    bar_rows = {p.name: int(pq.ParquetFile(p).metadata.num_rows) for p in paths}
    print(f"{JOB} run {run_id}: rules {a.rules} at k={a.k}; bars {bar_rows}; "
          f"reference {ref_path.name} panel {ref.get('panel')}", flush=True)
    print(f"  writes ONE receipt ({rp.name}); no panel, facts table or leaderboard is written",
          flush=True)
    W = F.load_wide(paths, start=_cfg.STRATEGY_LIB_START)
    from backend.services import stitched_tickers as ST            # noqa: PLC0415
    _full = (ST.LAST_AUDIT or {}).get("defect_screen") or {}
    suspects = list(_full.get("suspects") or [])
    screen_audit = BD.summary(_full)
    stitch_audit = {k: (len(v) if isinstance(v, list) else v)
                    for k, v in (ST.LAST_AUDIT or {}).items() if k != "defect_screen"}
    print(f"  BAR SCREEN {a.bar_screen}: removed {screen_audit.get('rows_removed')} rows "
          f"{screen_audit.get('rows_removed_by_reason')}, cuts {screen_audit.get('cuts_by_reason')}; "
          f"stitch {stitch_audit.get('by_verdict')}", flush=True)
    print(f"  wide {W['close'].shape} ({W['n_bar_rows']:,} bars) {time.time()-t0:.0f}s; "
          f"peak {peak_rss_mb()} MB", flush=True)
    panel = F.build_panel(W, delist_return=float(_cfg.STRATEGY_LIB_DELIST_RETURN))
    for c_ in ("high", "low", "volume"):
        W.pop(c_, None)
    rmeta = None
    if need_ratings:
        panel, rmeta = F.attach_ratings(panel, W)
    panel["tiebreak"] = SL._tiebreak(panel)
    flagged = BD.flagged_keys(panel, suspects)
    elig_ = panel["eligible"].astype(bool) if "eligible" in panel.columns else slice(None)
    n_impl_elig = int(BD.implausible_rows(panel[elig_]).sum())
    print(f"  suspects {len(suspects)} -> {len(flagged)} flagged panel rows; implausible rows "
          f"(vol_63 > {BD.IMPLAUSIBLE_VOL} or |12-1| > {BD.IMPLAUSIBLE_MOM}, descriptive): "
          f"{n_impl_elig} eligible", flush=True)
    chk = shrink_check(ref, panel, rmeta)
    print(f"  SIZE CHECK: this {chk['this_panel']} vs reference {chk['reference_panel']}; "
          f"revision events {chk['this_revision_events']} vs {chk['reference_revision_events']}",
          flush=True)
    if chk["refuse"]:
        print("REFUSED (input shrink): " + "; ".join(chk["refuse"]), flush=True)
        return 2
    spy, spy_meta = F.spy_leg(panel, W, network=not a.offline)
    try:
        iwm, iwm_meta = F.iwm_leg(panel, W, network=not a.offline)
    except SL.BenchmarkMissing as e:
        iwm, iwm_meta = str(e), {"status": f"REFUSED: {e}"}
    try:
        rpanel, rp_meta = F.random_panel_leg(panel)
    except Exception as e:                                        # noqa: BLE001 -- named
        rpanel, rp_meta = f"RANDOM_PANEL_SERIES_MISSING: {type(e).__name__}: {e}", {"status": "REFUSED"}
    benches = {"iwm": iwm, "random_panel": rpanel}
    print(f"  SPY {spy_meta.get('source')}; IWM {iwm_meta.get('source') or iwm_meta.get('status')}; "
          f"random panel {rp_meta.get('status')} {time.time()-t0:.0f}s; peak {peak_rss_mb()} MB",
          flush=True)
    ref_board = json.loads((out / f"leaderboard_{a.reference_run}.json").read_text(encoding="utf-8"))
    n_ref = int((ref_board.get("multiplicity") or {}).get("n_cells_looked_at")
                or (ref_board.get("multiplicity") or {}).get("cells_looked_at") or 868)
    n_new = len(rules) * (len(SL.QUARTER_OFFSETS) + 1)
    n_spy = n_ref + n_new
    n_twin = int((ref_board.get("multiplicity") or {}).get("n_candidate_rules") or 288)
    grid = sorted(pd.DatetimeIndex(panel.loc[panel["fwd_ret"].notna(), "date"].unique()))
    by_date = MT.panel_by_date(panel)
    cache: dict = {}
    results = {}
    refused = {}
    series_rows: list = []
    for rule in rules:
        print(f"  {rule.id} (hold {rule.hold_months}, weight {rule.weight_rule}, "
              f"gate {rule.regime_gate or '-'})", flush=True)
        entry = {"meta": {"id": rule.id, "family": rule.family, "k": a.k,
                          "weight_rule": rule.weight_rule, "regime_gate": rule.regime_gate,
                          "universe_rule": rule.universe_rule, "fingerprint": rule.fingerprint()},
                 "offsets": {}}
        try:
            entry["default"] = run_one(panel, spy, benches, rule, k=a.k, by_date=by_date,
                                       cache=cache, grid=grid, n_spy=n_spy, n_twin=n_twin,
                                       flagged=flagged, refuse_defects=BD.ENABLED)
            for tag, var in CO.offset_variants(rule).items():
                entry["offsets"][tag] = run_one(panel, spy, benches, var, k=a.k, by_date=by_date,
                                                cache=cache, grid=grid, n_spy=n_spy, n_twin=n_twin,
                                                flagged=flagged, refuse_defects=BD.ENABLED)
        except (CO.OffsetInputMissing, MT.TwinInputMissing, SL.RuleInputMissing,
                BD.BarDefectRefusal) as e:
            refused[rule.id] = f"{type(e).__name__}: {e}"
            print(f"    REFUSED {rule.id}: {e}", flush=True)
            continue
        entry["classification"] = CO.classify(entry["offsets"])
        ser = {tag: r.pop("_series") for tag, r in entry["offsets"].items()}
        entry["default"].pop("_series", None)
        entry["tranche_average"] = CO.tranche_average(ser)
        for tag, df in ser.items():
            series_rows.append(df.assign(rule=rule.id, offset=tag).reset_index()
                               .rename(columns={"index": "date"}))
        d_off = entry["default"].get("first_rebalance_offset")
        same = entry["offsets"].get(d_off) if d_off else None
        entry["default_equals_offset"] = d_off
        entry["default_matches_offset_series"] = (
            None if same is None else bool(abs((same["cum_net_full"] or 0) -
                                                (entry["default"]["cum_net_full"] or 0)) < 1e-9))
        results[rule.id] = entry
        ta = entry["tranche_average"]
        print(f"    TRANCHE (1/3 in each offset) {rule.id}: rule - twin21 "
              f"{_p(ta['rule_minus_twin21']['mean_monthly'], 2)}/mo t {_n(ta['rule_minus_twin21']['t_blocks'])} "
              f"MDE {_p(ta['rule_minus_twin21']['mde_monthly'], 2)}; cum2020 {_p(ta['cum_net_since_2020'])} "
              f"(SPY {_p(ta['cum_spy_since_2020'])})", flush=True)
        cl_ = entry["classification"]
        print(f"    VERDICT {rule.id}: {cl_['verdict']} ({cl_.get('why')}; A {cl_['set_a']['verdict']}, "
              f"B {(cl_.get('set_b') or {}).get('verdict')}, per-draw {cl_.get('per_draw_verdicts')}; "
              f"old rule v1 {cl_.get('verdict_rule_v1')}); peak {peak_rss_mb()} MB", flush=True)
    # re-confirmation against the reference board's own offset controls
    reconfirm = {}
    rows = {r.get("id"): r for key in ("controls", "all_rows") for r in (ref_board.get(key) or [])
            if isinstance(r, dict)}
    for tag in SL.QUARTER_OFFSETS:
        ref_row = rows.get(f"mom_12_1_q_{tag}") or {}
        mine = ((results.get("mom_12_1_q") or {}).get("offsets") or {}).get(tag) or {}
        reconfirm[tag] = {"reference_cum_since_2020": ref_row.get("hindsight_cum_since_2020"),
                          "this_cum_since_2020": mine.get("cum_net_since_2020"),
                          "reference_sealed_vs_spy": ref_row.get("sealed_vs_spy"),
                          "this_sealed_vs_spy": mine.get("sealed_vs_spy")}
    doc = {
        "schema": "strategy_library/calendar_offsets/1", "job": JOB, "run_id": run_id,
        "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": ("HINDSIGHT: every rule was registered 2026-09-26, after every month here; this "
                  "receipt asks whether a lead survives a change of rebalance CALENDAR, nothing more"),
        "why": ("ROADMAP_2026-09-28 lane M1; adversarial review 2026-09-28 §1 and §5.2: only "
                "mom_12_1_q had been run at its three quarterly offsets"),
        "verdict_rule": CO.VERDICT_RULE, "beats_t": CO.BEATS_T, "reach_t": CO.REACH_T,
        "mde_z": CO.MDE_Z,
        "verdict_rule_v1": CO.VERDICT_RULE_V1,
        "rule_changed_after_first_verdicts": {
            "changed_utc": "2026-09-28T07:00Z (approx.)",
            "first_verdict_receipts": ["calendar_offsets_2026-09-28T055728Z.json",
                                       "calendar_offsets_2026-09-28T055923Z.json"],
            "first_verdicts": "4 x CANNOT_DISTINGUISH under v1",
            "why": ("review F3 (docs/reviews/REVIEW_2026-09-28_LANE_M_MEASUREMENT.md): v1's LOSES needed "
                    "mean <= 0, which a 12-1-tercile-matched twin almost never gives a momentum sort, so "
                    "v1 could almost never label a calendar artefact; v2 is the roadmap's LANE M1 rule "
                    "(committed in b1010061 before either run). F4: one seed set decided labels at t 2.04-"
                    "2.12, so v2 reads two disjoint 21-draw seed sets and stores every draw's t. F9: a "
                    "missing t is NOT_COMPUTED, not a measured null. This receipt is a NEW run id; the "
                    "two earlier receipts are kept unchanged.")},
        "seed_sets": {"n_sets": CO.N_SEED_SETS, "draws_per_set": CO.DRAWS_PER_SET,
                      "set_a": "seed_for(cell, j), j = 0..20", "set_b": "seed_for(cell, j), j = 21..41"},
        "k": a.k, "rules": a.rules, "offsets": {t: list(m_) for t, m_ in SL.QUARTER_OFFSETS.items()},
        "conventions": {
            "engine": "strategy_library.run_strategy with rebalance_months; band costs on (cost_scale 1.0)",
            "twin": ("matched_twins: size band x vol_63 tercile x 12-1 tercile, 21 seeded draws "
                     "(seed_for(cell id)); twin net = twin gross - the rule's cost that month"),
            "t_blocks": "non-overlapping rebalance periods (block value = sum of monthly differences)",
            "mde": "MDE_Z x SE, in %/month",
            "by_year": "keyed on the HOLD month (entry session = decision date + 1 business day)",
            "dsr_vs_spy_n_trials": f"{n_ref} reference cells + {n_new} cells run here = {n_spy}",
            "dsr_rule_minus_twin21_n_trials": f"{n_twin} (the reference board's candidate rules, "
                                              "as the leads doc read rule - twin21)"},
        "bar_screen": {"mode": a.bar_screen,
                       "note": ("ON = the reader default; OFF = audit leg, pre-screen panel, "
                                "book refusal not enforced" if a.bar_screen == "off" else
                                "ON = the reader default; book refusal enforced"),
                       "screen": screen_audit, "stitch": stitch_audit,
                       "suspects": suspects, "flagged_panel_rows": len(flagged),
                       "implausible_rows_eligible": n_impl_elig,
                       "book_max_share": BD.BOOK_MAX_SHARE},
        "size_check": chk, "spy": spy_meta.get("source"), "iwm": iwm_meta,
        "random_panel": rp_meta, "reference_run": a.reference_run,
        "reconfirm_mom_12_1_q_vs_reference": reconfirm,
        "results": results, "refused": refused,
        "summary": {rid: e["classification"]["verdict"] for rid, e in results.items()},
        "summary_v1_rule": {rid: e["classification"].get("verdict_rule_v1") for rid, e in results.items()},
        "elapsed_s": round(time.time() - t0, 1), "peak_working_set_mb": peak_rss_mb(),
    }
    sp_path = out / f"calendar_offsets_monthly_{run_id}.parquet"
    if series_rows:
        allm = pd.concat(series_rows, ignore_index=True)
        allm.to_parquet(sp_path)
        doc["monthly_series"] = F._rel(sp_path)
        doc["cross_rule_correlation"] = CO.cross_rule_correlation(allm)
    atomic_write_json(rp, F._round(doc), indent=1)
    print(f"-> {rp}  ({time.time()-t0:.0f}s, peak {peak_rss_mb()} MB)", flush=True)
    for rid, v in doc["summary"].items():
        print(f"  {rid}: {v}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
