"""Dynamic exposure book family (CH-45): growth / balanced / preservation on the rolling cohorts.

    python -m scripts.dynamic_books compile-contracts            (attended; write-once)
    python -m scripts.dynamic_books backfill --data-root <optimus> --out <dir> [--from D] [--to D]
    python -m scripts.dynamic_books step --data-root <optimus> [--out <dir>]
    python -m scripts.dynamic_books pit-check --data-root <optimus> --out <dir>
    python -m scripts.dynamic_books status --data-root <optimus> [--out <dir>]     (read-only)
    python -m scripts.dynamic_books compare-v2 --data-root <optimus> --out <dir>   (read-only)

`backfill` births every scheduled cohort whose entry is already in the bars
(flagged `backfilled: true`, never forward evidence); `step` births the due
cohort while its entry has not opened. Both extend the append-only path and
mark tables and print one row per cohort and personality. `pit-check` poisons
every bar dated on or after each session and requires every exposure decided up
to that session to be unchanged; it also drops every calendar observation made
after the close that decided each session. `status` prints what a scheduler reads
first (contract version in force, the forward calendar's freshness, each leader's
next announced date with its observation stamp, cohorts tracked, the last run row)
and writes nothing. `compare-v2` prints preservation under the v2 form (beta clip
only) beside v3 (hedge <= 1.0x equity) for every cohort in --out, and writes nothing.
Nothing is written under --data-root except `<data-root>/dynamic_books`.

Contracts v3 (docs/TRIALS/DYNAMIC-EXPOSURE-BOOKS-CONTRACTS-v3.json): leader report
dates from the forward catalyst calendar (each observation's own pulled_utc), the
preservation hedge capped at 1.0x equity (gross <= 2.0). An --out declared under v1
or v2 refuses under v3 code, with or without --accept-code-version: a changed
family is a new --out.

Exit codes: 0 ok, 2 refused (DynamicBookRefused / RollingCohortRefused), 3 the
forward calendar is STALE (step and status), 1 crash.
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
    out.append("bf: BF = BACKFILLED (never forward evidence), FW = forward. Calendar facts act only from "
               "their own forward-calendar observation stamp. gross = sum |notional| / equity at a decision, "
               "observed max / largest the contract admits (v3: hedge <= 1.0x, gross <= 2.0). sqz$ = a "
               "one-session +10% QQQ against the hedge on $100k, observed / admissible (longs credited 0). "
               "The hedge trades AT the close it reads (replay convention, not strictly executable); the "
               "balanced cut reads the open gap and trades at the close (executable).")
    out.append("k* = provisional running state (not a declared mark). ret = net of the base band round trip "
               "and the rule's own costs. beta = mean exposure x ex-ante book beta - hedge x QQQ beta. "
               "worst$ = every long name gaps -30% at peak stock exposure on a $100k book (hedge credited 0); "
               "wday$ = worst realised session. sect1 = top-1 sector share of the base book; bets = "
               "effective bets (participation ratio of 63-session return correlations before D).")
    return out


def leader_lines(leaders: dict) -> list[str]:
    out = []
    for t, v in leaders.items():
        out.append(f"  {t:5} {v.get('state', '?'):13} next {v.get('next_date') or '-':10} "
                   f"timing {v.get('timing') or '-':7} {v.get('confirmation') or '-':16} "
                   f"observed {v.get('observed_utc') or '-'} (age {v.get('age_days')} d)  "
                   f"last {v.get('last_reported') or '-'}")
    return out


def status_lines(res: dict) -> list[str]:
    fc = res.get("forward_calendar") or {}
    out = [f"dynamic books status at {res['utc']}",
           f"  contracts in force {res['contract_version']} ({res['contracts_file']}) manifest "
           f"{res.get('contracts_manifest_sha256')}"]
    for cid, h in sorted((res.get("contracts") or {}).items()):
        out.append(f"    {cid} {h}")
    d = res.get("declaration")
    out.append(f"  out {res['out']}: " + ("not declared yet (the first run declares it)" if d is None else
                                         f"declared {d.get('declared_utc')} under "
                                         f"{d.get('contract_version') or 'v1/v2'} code {d.get('code_version')}"))
    age = None if fc.get("age_s") is None else round(fc["age_s"] / 86400, 2)
    out.append(f"  forward calendar {fc.get('verdict')} evidence {fc.get('evidence_utc')} age {age} d: "
               f"{fc.get('detail')}")
    out.append("  leaders (next announced date and its observation stamp):")
    out += ["  " + x for x in leader_lines(res.get("leaders") or {})]
    for t, why in sorted((res.get("calendar_unscheduled") or {}).items()):
        out.append(f"  UNSCHEDULED {t}: {'; '.join(why)}")
    for t, why in sorted((res.get("calendar_stale") or {}).items()):
        out.append(f"  STALE {t}: {'; '.join(why)}")
    out.append(f"  cohorts tracked {len(res['cohorts'])}: " + ", ".join(
        f"{c['cohort_id']}{'(BF)' if c['backfilled'] else '(FW)'}" for c in res["cohorts"]))
    out.append(f"  calendar observations on record {res.get('calendar_observations_on_record')}")
    out.append(f"  last run {json.dumps(res.get('last_run'), default=str)}")
    for p in res["problems"]:
        out.append(f"  PROBLEM {p}")
    out.append(f"  rc {res['rc']} (0 ok, 3 calendar STALE: a step would exit 3, 2 contracts/out refuse)")
    return out


def compare_lines(rows: list[dict]) -> list[str]:
    from backend.services.portfolio_intelligence.dynamic_exposure_books import fmt_pct
    head = (f"{'cohort':10} {'bf':2} {'k':>3}  {'ret v2':>8} {'ret v3':>8}  {'maxDD v2':>8} {'maxDD v3':>8}  "
            f"{'beta v2':>7} {'beta v3':>7}  {'gross v2':>9} {'gross v3':>9}  {'sqz$ v2':>13} {'sqz$ v3':>13}  "
            f"{'mean h v2/v3':>12} {'cap bound':>9}")
    out = ["PRESERVATION: v2 form (beta clip [0,3]) vs v3 (hedge <= 1.0x equity, gross <= 2.0); "
           "latest state; BACKFILLED, one episode, no claim", head, "-" * len(head)]
    for r in rows:
        a, b = r["v2"], r["v3"]
        out.append(f"{r['cohort_id']:10} {'BF' if r['backfilled'] else 'FW':2} {b['mark_k']:>3}  "
                   f"{fmt_pct(a['ret_net']):>8} {fmt_pct(b['ret_net']):>8}  {fmt_pct(a['max_drawdown']):>8} "
                   f"{fmt_pct(b['max_drawdown']):>8}  {a['beta_eff']:>7.2f} {b['beta_eff']:>7.2f}  "
                   f"{a['gross_notional_max']:.2f}/{a['gross_notional_admissible']:.2f} "
                   f"{b['gross_notional_max']:.2f}/{b['gross_notional_admissible']:.2f}  "
                   f"{a['squeeze_usd_observed']:>6.0f}/{a['squeeze_usd_admissible']:<6.0f} "
                   f"{b['squeeze_usd_observed']:>6.0f}/{b['squeeze_usd_admissible']:<6.0f}  "
                   f"{a['mean_hedge']:.2f}/{b['mean_hedge']:.2f} "
                   f"{b['sessions_hedge_cap_bound']:>5}/{b['sessions_hedged']}")
    out.append("ret = net of the base band and the rule's costs (SPY over the same window is in the main "
               "table); gross = observed max / admissible at a decision; sqz$ = +10% QQQ in one session "
               "against the hedge on $100k, observed / admissible; cap bound = hedged sessions where the "
               "1.0x cap cut the clipped beta.")
    return out


def main(argv: list[str] | None = None) -> int:
    from backend.services.portfolio_intelligence import branch_population_rolling as R
    from backend.services.portfolio_intelligence import dynamic_exposure_books as D

    ap = argparse.ArgumentParser(prog="dynamic_books", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    cc = sub.add_parser("compile-contracts", help="freeze the three contracts (write-once)")
    cc.add_argument("--frozen-utc", default=None)
    st = sub.add_parser("status", help="read-only: what a scheduler reads first; writes nothing")
    st.add_argument("--data-root", required=True, type=Path)
    st.add_argument("--out", type=Path, default=None, help="default <data-root>/dynamic_books")
    st.add_argument("--json", action="store_true")
    cv = sub.add_parser("compare-v2", help="read-only: preservation v2 form vs v3 cap per cohort in --out")
    cv.add_argument("--data-root", required=True, type=Path)
    cv.add_argument("--out", type=Path, required=True)
    cv.add_argument("--asof", default=None)
    for name in ("backfill", "step", "pit-check"):
        p = sub.add_parser(name)
        p.add_argument("--data-root", required=True, type=Path, help="the optimus ledger dir (read only)")
        p.add_argument("--out", type=Path, default=None, help="default <data-root>/dynamic_books")
        p.add_argument("--asof", default=None)
        p.add_argument("--accept-code-version", action="store_true",
                       help=("ATTENDED ONLY, never in a scheduled task. Accepts a code version (git HEAD "
                             "of the running checkout) other than the one in <out>/declaration.json and "
                             "every one accepted before. Journals one line {code_version, accepted_utc, "
                             "run_id} to <out>/code_versions_accepted.jsonl (append-only; later runs on "
                             "that version need no flag) and puts code_note on the run row. It does NOT "
                             "accept a changed contract, config or rolling grading config (those refuse: "
                             "a new --out), and every stored path row is still recomputed: any row that "
                             "would change refuses with nothing appended"))
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
        if a.cmd == "status":
            res = D.status(a.data_root, out)
            if a.json:
                print(json.dumps(res, indent=1, default=str))
            else:
                for line in status_lines(res):
                    print(line)
            return int(res["rc"])
        if a.cmd == "compare-v2":
            rows = D.preservation_cap_comparison(out, a.data_root, asof=a.asof)
            for line in compare_lines(rows):
                print(line)
            return 0
        if a.cmd == "pit-check":
            import pandas as pd
            from backend import config as C
            specs, _ = R.load_specs(D.REPO / D.SPECS_V2_REL)
            spec = next(s for s in specs["specifications"] if s["policy_id"] == C.DYNAMIC_BOOK_BASE_POLICY_ID)
            anchor = pd.Timestamp(C.ROLLING_COHORT_ANCHOR)
            through = pd.Timestamp(a.asof) if a.asof else pd.Timestamp(datetime.now(timezone.utc).date())
            bars = R.load_bars(a.data_root, start=anchor - pd.Timedelta(days=400), end=through)
            sessions = R.bench_sessions(bars)
            cal = R.XnysCalendar()
            dec = {s: pd.Timestamp(cal.close_of(s)) for s in sessions if s >= anchor - pd.Timedelta(days=10)}
            obs = D.read_observations(out)
            res = []
            for p in sorted((out / "cohorts").glob("dxb_cohort_*.json")):
                c = json.loads(p.read_bytes())
                res.append(D.pit_recheck(c, bars, sessions, obs, horizon=int(spec["horizon_sessions"]),
                                         through=sessions[-1], decision_utc=dec, cal=cal))
            print(json.dumps(res, indent=1))
            bad = sum(r["differ"] for r in res)
            print(f"PIT poison check (bars and calendar observations): "
                  f"{sum(r['decisions_checked'] for r in res)} decisions, {bad} moved")
            return 2 if bad else 0
        row = D.run(a.cmd, data_root=a.data_root, out=out, asof=a.asof,
                    date_from=getattr(a, "date_from", None), date_to=getattr(a, "date_to", None),
                    rolling_out=a.rolling_out, accept_code_version=a.accept_code_version)
    except (D.DynamicBookRefused, R.RollingCohortRefused) as exc:
        refusal = {"task": D.TASK_NAME, "schema": "dynamic_exposure_run/3", "contract_version": D.CONTRACT_VERSION,
                   "mode": a.cmd, "action": "REFUSED",
                   "rc": 2, "reason": str(exc), "utc": datetime.now(timezone.utc).isoformat()}
        print(json.dumps(refusal))
        if a.cmd in ("backfill", "step"):              # the task receipt reads this journal
            try:
                from backend.services import disk_guard
                o = D.output_dir(a.data_root, a.out)
                o.mkdir(parents=True, exist_ok=True)
                disk_guard.locked_append_line(o / "runs.jsonl", json.dumps(refusal, sort_keys=True), fsync=True)
            except (OSError, D.DynamicBookRefused):
                pass
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
    print("\nLEADER CALENDAR (forward calendar, as of this run)")
    for line in leader_lines(row["leader_calendar"]):
        print(line)
    if row["calendar_unscheduled"]:
        print("UNSCHEDULED (no announced next date; healthy while the calendar is fresh):")
        for t, why in sorted(row["calendar_unscheduled"].items()):
            print(f"  {t}: {'; '.join(why)}")
    print("\nLEADER EVENTS (reaction-session gaps; only ON_TIME / later-believed facts act)")
    for e in row["leader_events"]:
        print(f"  {e['leader']:5} report {e['earnings_date']} timing {e['timing']:12} reaction {e['session']} "
              f"gap {e['gap']:+.4f} fires {e['fires']} status {e['status']} first observed "
              f"{e['first_observed_utc']} announced ahead {e['announced_before_event']}")
    if row["calendar_stale"]:
        print("\nFORWARD CALENDAR STALE (the leader-gap rule cannot fire on time for these):")
        for t, why in sorted(row["calendar_stale"].items()):
            print(f"  {t}: {'; '.join(why)}")
    if row["rc"]:
        print(f"EXIT {row['rc']} ({row['action']})")
    return int(row["rc"])


if __name__ == "__main__":
    raise SystemExit(main())
