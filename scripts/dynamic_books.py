"""Dynamic exposure book family (CH-45): growth / balanced / preservation on the rolling cohorts.

    python -m scripts.dynamic_books compile-contracts            (attended; write-once)
    python -m scripts.dynamic_books backfill --data-root <optimus> --out <dir> [--from D] [--to D]
    python -m scripts.dynamic_books step --data-root <optimus> [--out <dir>]
    python -m scripts.dynamic_books pit-check --data-root <optimus> --out <dir>

`backfill` births every scheduled cohort whose entry is already in the bars
(flagged `backfilled: true`, never forward evidence); `step` births the due
cohort while its entry has not opened. Both extend the append-only path and
mark tables and print one row per cohort and personality. `pit-check` poisons
every bar dated on or after each session and requires every exposure decided up
to that session to be unchanged. Nothing is written under --data-root except
`<data-root>/dynamic_books`.

Exit codes: 0 ok, 2 refused (DynamicBookRefused / RollingCohortRefused), 1 crash.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def table_lines(table: list[dict]) -> list[str]:
    from backend.services.portfolio_intelligence.dynamic_exposure_books import fmt_pct
    head = (f"{'cohort':10} {'bf':2} {'personality':12} {'k':>3} {'ret':>8} {'SPY':>8} {'beta':>5} "
            f"{'b-adj ex':>8} {'maxDD':>8} {'worst$':>8} {'wday$':>7} {'gross':>9} {'sqz$':>13} "
            f"{'sect1':>5} {'bets':>5}  exposure path")
    out = [head, "-" * len(head)]
    for r in table:
        path = (f"cut {r['sessions_cut']}s mean e {r['mean_exposure']:.2f}; hedged {r['sessions_hedged']}s "
                f"mean h {r['mean_hedge']:.2f}")
        if r["first_rule_session"]:
            path += f"; rule {r['first_rule_session']}..{r['last_rule_session']}"
        s1 = r["sector_top1"]
        gross = f"{r['gross_notional_max']:.2f}/{r['gross_notional_admissible']:.2f}"
        sqz = f"{r['squeeze_usd_observed']:.0f}/{r['squeeze_usd_admissible']:.0f}"
        out.append(f"{r['cohort_id']:10} {'BF' if r['backfilled'] else 'FW':2} {r['personality']:12} "
                   f"{r['mark_k']:>3}{'*' if r['provisional'] else ' '}"
                   f"{fmt_pct(r['ret_net']):>8} {fmt_pct(r['spy_ret']):>8} {r['beta_eff']:>5.2f} "
                   f"{fmt_pct(r['beta_adj_excess']):>8} {fmt_pct(r['max_drawdown']):>8} "
                   f"{r['worst_case_usd']:>8.0f} {r['worst_day_usd']:>7.0f} {gross:>9} {sqz:>13} "
                   f"{'n/a' if s1 is None else f'{s1:.2f}':>5} "
                   f"{'n/a' if r['effective_bets'] is None else r['effective_bets']:>5}  {path}")
    out.append("bf: BF = BACKFILLED (never forward evidence; calendar observation time unknown), FW = forward. "
               "gross = sum |notional| / equity, observed max / largest the contract admits (beta clip 3). "
               "sqz$ = a one-session +10% QQQ against the hedge on $100k, observed / admissible (longs "
               "credited 0). The hedge trades AT the close it reads (replay convention, not strictly "
               "executable); the balanced cut reads the open gap and trades at the close (executable).")
    out.append("k* = provisional running state (not a declared mark). ret = net of the base band round trip "
               "and the rule's own costs. beta = mean exposure x ex-ante book beta - hedge x QQQ beta. "
               "worst$ = every long name gaps -30% at peak stock exposure on a $100k book (hedge credited 0); "
               "wday$ = worst realised session. sect1 = top-1 sector share of the base book; bets = "
               "effective bets (participation ratio of 63-session return correlations before D).")
    return out


def main(argv: list[str] | None = None) -> int:
    from backend.services.portfolio_intelligence import branch_population_rolling as R
    from backend.services.portfolio_intelligence import dynamic_exposure_books as D

    ap = argparse.ArgumentParser(prog="dynamic_books", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    cc = sub.add_parser("compile-contracts", help="freeze the three contracts (write-once)")
    cc.add_argument("--frozen-utc", default=None)
    for name in ("backfill", "step", "pit-check"):
        p = sub.add_parser(name)
        p.add_argument("--data-root", required=True, type=Path, help="the optimus ledger dir (read only)")
        p.add_argument("--out", type=Path, default=None, help="default <data-root>/dynamic_books")
        p.add_argument("--asof", default=None)
        p.add_argument("--accept-code-version", action="store_true",
                       help="attended: accept a code version other than the declared one (journaled)")
        p.add_argument("--rolling-out", type=Path, default=None,
                       help="a rolling population to cross-check base holdings against (read only)")
        if name == "backfill":
            p.add_argument("--from", dest="date_from", default=None)
            p.add_argument("--to", dest="date_to", default=None)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "compile-contracts":
            target = D.REPO / D.CONTRACTS_REL
            if target.exists():
                raise D.DynamicBookRefused(f"{target.name} exists; frozen contracts are never rewritten. "
                                           f"A changed rule is a new contract id in a new file")
            specs, _ = R.load_specs(D.REPO / D.SPECS_V2_REL)
            doc = D.compile_contracts(frozen_utc=a.frozen_utc or datetime.now(timezone.utc).isoformat(),
                                      specs=specs)
            R._write_once(target, json.dumps(doc, indent=1, sort_keys=True) + "\n")
            print(json.dumps({"written": str(target), "manifest_sha256": doc["manifest_sha256"],
                              "contracts": {c["contract_id"]: c["contract_sha256"] for c in doc["contracts"]}},
                             indent=1))
            return 0
        out = D.output_dir(a.data_root, a.out)
        if a.cmd == "pit-check":
            import pandas as pd
            from backend import config as C
            specs, _ = R.load_specs(D.REPO / D.SPECS_V2_REL)
            spec = next(s for s in specs["specifications"] if s["policy_id"] == C.DYNAMIC_BOOK_BASE_POLICY_ID)
            anchor = pd.Timestamp(C.ROLLING_COHORT_ANCHOR)
            through = pd.Timestamp(a.asof) if a.asof else pd.Timestamp(datetime.now(timezone.utc).date())
            bars = R.load_bars(a.data_root, start=anchor - pd.Timedelta(days=400), end=through)
            sessions = R.bench_sessions(bars)
            earn = D.load_earnings(a.data_root)
            cal = R.XnysCalendar()
            dec = {s: pd.Timestamp(cal.close_of(s)) for s in sessions if s >= anchor - pd.Timedelta(days=10)}
            facts_p = out / D.FACTS_FILE
            facts: dict = {}
            for line in (facts_p.read_text(encoding="utf8").splitlines() if facts_p.is_file() else []):
                f = json.loads(line)
                facts.setdefault((f["leader"], f["earnings_date"]), f)
            res = []
            for p in sorted((out / "cohorts").glob("dxb_cohort_*.json")):
                c = json.loads(p.read_bytes())
                res.append(D.pit_recheck(c, bars, sessions, earn, horizon=int(spec["horizon_sessions"]),
                                         through=sessions[-1], facts=facts or None,
                                         decision_utc=dec if facts else None))
            print(json.dumps(res, indent=1))
            bad = sum(r["differ"] for r in res)
            print(f"PIT poison check: {sum(r['decisions_checked'] for r in res)} decisions, {bad} moved")
            return 2 if bad else 0
        row = D.run(a.cmd, data_root=a.data_root, out=out, asof=a.asof,
                    date_from=getattr(a, "date_from", None), date_to=getattr(a, "date_to", None),
                    rolling_out=a.rolling_out, accept_code_version=a.accept_code_version)
    except (D.DynamicBookRefused, R.RollingCohortRefused) as exc:
        print(json.dumps({"task": D.TASK_NAME, "action": "REFUSED", "rc": 2, "reason": str(exc),
                          "utc": datetime.now(timezone.utc).isoformat()}))
        return 2
    table = row.pop("table")
    cohorts = row.pop("cohorts")
    print(json.dumps(row, indent=1, default=str))
    print("\nCOHORT ENTRIES (base selection, shared by the three books)")
    for cid, c in sorted(cohorts.items()):
        st = c["stats"]
        ts = st["sector"].get("top_sector") or {}
        print(f"  {cid} entry {c['entry_session']} names {c['n_names']} holdings {c['holdings_hash']} "
              f"top sector {ts.get('sector')} {ts.get('weight_of_covered')} (coverage "
              f"{st['sector'].get('sector_coverage')}) effective bets {st.get('effective_bets_raw')} "
              f"({st.get('effective_bets_spy_residual')} net of SPY; median corr {st.get('median_pairwise_corr')}) "
              f"beta ex-ante {st['beta_ex_ante']:.2f} rolling cross-check {c.get('rolling_crosscheck')} "
              f"backfilled {c['backfilled']}")
    print("\nPER COHORT AND PERSONALITY (latest state through " + row["through"] + ")")
    for line in table_lines(table):
        print(line)
    if row["calendar_stale"]:
        print("\nLEADER CALENDAR STALE (the leader-gap rule cannot fire on time for these):")
        for t, why in sorted(row["calendar_stale"].items()):
            print(f"  {t}: {'; '.join(why)}")
    if row["rc"]:
        print(f"EXIT {row['rc']} ({row['action']})")
    return int(row["rc"])


if __name__ == "__main__":
    raise SystemExit(main())
