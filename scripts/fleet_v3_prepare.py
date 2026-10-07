"""CHUNK C20 (2026-10-07): PREPARE the six-role v3 fleet, the D14 core and the
D13 cap fix. Nothing here seeds, orders or edits a live contract.

    python -m scripts.fleet_v3_prepare            # freeze the six PREPARED contracts + receipt
    python -m scripts.fleet_v3_prepare --dry      # print only, write nothing
    python -m scripts.fleet_v3_prepare --archive  # OWNER STEP: copy the fleet manager's record

The receipt is `fleet_manager/contracts_v3/PREPARE_<runid>.json` (run id in the
name: a second run never overwrites the first). Every number in the C20 note
comes from it. A step that cannot compute REFUSES with its reason; it is never
filled with a default.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend import config as _cfg
from backend.services import benchmark_core as BC
from backend.services import fleet_manager as FM
from backend.services import fleet_v3_contracts as V3
from backend.services import pc_broker as PB
from backend.services import pc_risk as PR
from backend.services import rules_capfix_proposal as CF

LEDGER = Path(_cfg.OPTIMUS_LEDGER_DIR)
HYP = LEDGER / "hyp_lab"
FAIR = [HYP / "twin_board_FT_2026-10-07_1.jsonl", HYP / "twin_board_FT_2026-10-07_2.jsonl"]
STICKY = [HYP / "twin_board_STK_2026-10-07_2.jsonl", HYP / "twin_board_STK_2026-10-07_3.jsonl"]
#: The review's stressed SPY sigma (C2 review: "SPY's ~1.2% daily sigma").
SPY_STRESSED_SIGMA = 0.012


def _spy_series() -> tuple[float | None, str | None, int]:
    import pandas as pd                                            # noqa: PLC0415
    df = pd.read_parquet(LEDGER / "prices_2025_26" / "bars.parquet",
                         columns=["symbol", "date", "close"], filters=[("symbol", "==", "SPY")])
    r = df.sort_values("date").set_index("date")["close"].pct_change().dropna()
    if r.empty:
        return None, None, 0
    return float(r.min()), str(r.idxmin().date()), int(r.count())


def _v2_book_names(account: str) -> list[str]:
    c = json.loads(FM.contract_file(account, "v2").read_text(encoding="utf-8"))
    return [p["ticker"] for p in (c.get("selection") or {}).get("positions") or []
            if p.get("ticker") != "CASH"]


def _innovation_pool() -> tuple[list[str], str | None]:
    from backend.services import opportunities as O                # noqa: PLC0415
    d = O.load_latest()
    if not d:
        return [], None
    names = sorted({r["ticker"] for L in d.get("lists") or [] for r in L.get("rows") or []
                    if r.get("lane") == "HIGH_RISK_INNOVATION"})
    return names, d.get("receipt_file")


def kill_prior() -> dict:
    """The pooled measured book-minus-twin daily sd over every fleet grade row
    (review 2026-10-07 M6: size the kill line from the measured gap). Refuses
    below 20 rows: a line sized on nothing is not a line."""
    import statistics as st                                        # noqa: PLC0415
    rows = FM.read_jsonl(FM.grades_path())
    v = [float(r["vs_twin"]) for r in rows if isinstance(r.get("vs_twin"), (int, float))]
    if len(v) < 20:
        raise V3.PreparedRefusal(f"REFUSED: only {len(v)} fleet book-minus-twin rows; "
                                 "no measured gap to size a kill line on")
    return {"sd_daily": st.stdev(v), "n_rows": len(v),
            "roles": sorted({r["role"] for r in rows if r.get("vs_twin") is not None}),
            "last_session": max(str(r.get("session")) for r in rows),
            "source": "paper_accounts/fleet_manager/grades.jsonl vs_twin (pooled across roles)"}


def reference() -> dict:
    sig = PR.panel_sigmas()
    if not sig:
        raise V3.PreparedRefusal("REFUSED: the bars panel is unreadable; no sigma, no worst case")
    st = PR.universe_stats(sig)
    worst, worst_d, n = _spy_series()
    if not sig.get("SPY"):
        raise V3.PreparedRefusal("REFUSED: SPY has no panel sigma")
    pool, receipt = _innovation_pool()
    n_sig_ok = sum(1 for s_ in pool if sig.get(s_) and sig[s_] <= 0.20 / 3.0)

    def _max(names: list[str]) -> float | None:
        v = [sig[s] for s in names if sig.get(s)]
        return max(v) if v else None
    cand = {"thematic": _max(_v2_book_names("hack1")),
            "revision_snowball": _max(_v2_book_names("hack2")),
            "innovation": _max(pool)}
    import pandas as pd                                            # noqa: PLC0415
    asof = str(pd.read_parquet(LEDGER / "prices_2025_26" / "bars.parquet",
                               columns=["date"])["date"].max().date())
    return {
        "asof": asof,
        "universe_sigma": {"p50": st["p50"], "p75": st["p75"], "p90": st["p90"], "n": st["n"]},
        "spy_sigma": sig["SPY"], "spy_worst_day": worst, "spy_worst_day_date": worst_d,
        "spy_n_returns": n,
        "candidate_sigma": {k: v for k, v in cand.items() if v},
        "innovation_pool": {"n": len(pool), "receipt": receipt, "n_sigma_eligible": n_sig_ok},
        "kill_prior": kill_prior(),
        "quant": V3.quant_eligibility(FAIR, STICKY),
        "lineage": {r: V3.v2_lineage(V3.ACCOUNT[r]) for r in V3.ROLES},
        "_sigmas": sig,
    }


def pc_state() -> dict:
    p = LEDGER / "paper_accounts" / "pc_snapshot" / "state_latest.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        eq = float(d["equity"])
        held = {str(x["symbol"]): float(x["market_value"]) / eq for x in d.get("positions") or []
                if isinstance(x.get("market_value"), (int, float)) and x["market_value"] > 0}
        return {"equity": eq, "held": held, "cash_frac": float(d.get("cash") or 0.0) / eq,
                "source": f"pc_snapshot/state_latest.json t={d.get('t')}"}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise V3.PreparedRefusal(f"REFUSED: PC-PAPER state unreadable: {exc}")


def d14_table(ref: dict) -> dict:
    """Core + sleeves worst case for TODAY's PC-PAPER state (review 2026-10-07
    H2: the core is min(1 - acting, MAX_NAME_FRAC) planned AFTER the sleeves,
    which keep their share counts). Today's sleeves are priced on their OWN
    panel sigmas; the hypothetical books on the universe p90."""
    st = pc_state()
    eq = st["equity"]
    sig = ref["_sigmas"]
    spy, p90 = float(ref["spy_sigma"]), float(ref["universe_sigma"]["p90"])
    held = {k: v for k, v in st["held"].items() if k != "SPY"}
    acting = sum(held.values())
    cap = float(PB.MAX_NAME_FRAC)
    n, w = int(_cfg.PROBE_MAX_NAMES), float(_cfg.PROBE_MAX_WEIGHT)
    probe = {f"PROBE{i}": w for i in range(n)}
    exploit = {f"EXPL{i}": float(_cfg.ER_EXPLOIT_MAX_WEIGHT) for i in range(8)}
    rows = []
    for label, core, sleeves, s, sg in (
            (f"TODAY, flag OFF: {len(held)} held names ({acting:.1%}), {st['cash_frac']:.1%} cash",
             0.0, held, spy, sig),
            ("TODAY, flag ON (H2-fixed): core min(1 - acting, 12%), sleeves' shares untouched",
             min(max(0.0, 1 - acting), cap), held, spy, sig),
            ("today's sleeves + a full core (needs the D22 exemption)", max(0.0, 1 - acting),
             held, spy, sig),
            ("same, SPY at the review's stressed 1.2%", max(0.0, 1 - acting), held,
             SPY_STRESSED_SIGMA, sig),
            ("largest admissible PROBE (10 x 2% at p90) + full core", 0.80, probe, spy, {}),
            ("no sleeve acting: 100% core (full)", 1.00, {}, spy, {}),
            ("EXPLOIT + PROBE acting at caps (before the gate), core 0", 0.0,
             {**probe, **exploit}, spy, {})):
        rows.append(BC.worst_case(equity=eq, core_frac=core, core_sigma=s,
                                  sleeve_weights=sleeves, sleeve_sigmas=sg, fallback_sigma=p90,
                                  core_worst_day=ref["spy_worst_day"], label=label))
    return {"equity_usd": eq, "equity_source": st["source"], "spy_daily_sigma": spy,
            "acting_gross_today": acting, "held_today": held,
            "sleeve_sigma": "today's names: own 63-session panel sigma (p90 if absent); "
                            f"hypothetical books: universe p90 {p90:.4f}",
            "spy_worst_day": ref["spy_worst_day"], "spy_worst_day_date": ref["spy_worst_day_date"],
            "core_plan_today_if_on": BC.core_plan(held, enabled=True), "rows": rows}


def d13_table(ref: dict) -> dict:
    p = LEDGER / "paper_accounts" / "roi_2026-10-06T160824Z.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    nav = next(float(r["equity"]) for r in d["rows"] if r.get("account") == "mirror")
    cap = float(_cfg.book_lanes["mirror"]["max_single_name"])
    sec = float(_cfg.book_lanes["mirror"]["max_sector"])
    sig = ref["_sigmas"]
    two = {"DKNG": 0.5, "SLDP": 0.5}                                # the 06-16 -> 07-14 state
    fixed = CF.enforce_position_limits_with_cash(two, cap, sec, {})
    rows = CF.worst_case_rows(nav=nav, weights_unfixed=two, weights_fixed=fixed, sigmas=sig,
                              label="mirror, 2 priced names (06-16 / 07-14)")
    return {"mirror_nav_usd": nav, "nav_source": p.name, "declared_cap": cap,
            "hole": CF.cap_hole(two, cap), "fixed_weights": fixed, "rows": rows,
            "today": ("12 names priced since 2026-08-02: n x cap = 3.0 >= 1, the fix defers to "
                      "rules.enforce_position_limits unchanged (no-op); the largest name at a "
                      "rebalance is <= 25%: one name to zero = -${:,.0f}".format(cap * nav)),
            "wired": False}


def summary(bodies: dict) -> list[dict]:
    out = []
    for role, b in bodies.items():
        sr, wc = b["stop_rule"], b["worst_case"]
        out.append({"role": role, "account": b["account"], "policy_hash": b.get("policy_hash"),
                    "rule_hash": b.get("rule_hash"), "source": b["alpha_source"],
                    "gross_cap": b["caps"]["max_gross_frac"],
                    "name_cap": (b["caps"].get("name_cap_overrides") or {}).get(
                        "SPY", b["caps"]["max_name_frac"]),
                    "stop": f"{sr['k_sigma']:g} sigma, clip [{sr['min_frac']:.0%}, {sr['max_frac']:.0%}]",
                    "worst_case_line": wc["line"], "twin": b["twin"]["kind"],
                    "supersedes": b.get("supersedes"),
                    "kill_rule": (b["kill_rule"]["kill_if"] if isinstance(b["kill_rule"], dict)
                                  else b["kill_rule"])})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--archive", action="store_true",
                    help="OWNER STEP: copy the fleet manager's local record (never moves)")
    a = ap.parse_args(argv)
    if a.archive:
        res = V3.archive_snapshot(FM.root() / "archive")
        print(f"archived {res['n_files']} files")
        return 0
    try:
        ref = reference()
        bodies = V3.build_bodies(ref)
        if not a.dry:
            # supersede: a PREPARED contract was never seeded; the old file is kept
            # under contracts_v3/superseded/ and its hash goes into `supersedes`
            bodies = {r: V3.freeze_prepared(b, supersede=True) for r, b in bodies.items()}
        d14, d13 = d14_table(ref), d13_table(ref)
    except V3.PreparedRefusal as exc:
        print(str(exc))
        return 2
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt = {"schema": "fleet_v3_prepare/1", "run_id": run_id, "chunk": "C20",
               "status": _cfg.FLEET_V3_STATUS_PREPARED, "seeded": False, "orders": 0,
               "reference": {k: v for k, v in ref.items() if k != "_sigmas"},
               "contracts": summary(bodies), "d14": d14, "d13": d13}
    print(json.dumps(receipt["contracts"], indent=1, default=str)[:4000])
    for r in d14["rows"]:
        print(r["line"])
    for r in d13["rows"]:
        print(r)
    if not a.dry:
        FM.atomic_write_json(V3.contracts_dir() / f"PREPARE_{run_id}.json", receipt)
        print(f"receipt: contracts_v3/PREPARE_{run_id}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
