"""Forecast and evidence expiry (CH-42) -- read-only over the live ledgers.

    python -m scripts.forecast_expiry sweep  --data-root <optimus dir> --out <dir> [--as-of D]
           [--campaign-ref 7e3fb909^] [--campaign-as-of D] [--no-campaign]
    python -m scripts.forecast_expiry labels --data-root <optimus dir> --out <dir> [--run-id R]

`sweep` classifies every forecast in `<data-root>/predictions.jsonl` (ACTIVE /
EXPIRED_GRADED / EXPIRED_UNGRADED / VOID / UNDATED), appends state changes to
`<out>/forecast_expiry/expiry.jsonl`, and accounts one by one for the overdue
forecasts of the campaign ledger copy named by `--campaign-ref` (read with
`git show` from this checkout, streamed, never copied). `labels` prints each
book's evidence label beside the label `book_dna.evidence_label` gives on the
trailing window, and the regime each was earned in. Neither changes a ledger,
a label or a book; both refuse an `--out` inside the data folder's parent.

Exit codes: 0 OK; 2 refused (missing input, or --out inside the data folder);
3 the counts do not reconcile; 4 a path carrying this tool's output name
(`forecast_expiry`) appeared, changed or vanished in the data folder. Files the live
jobs add or grow while it runs are printed by name and do not change the exit code.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from backend import config as _config
from backend.services import forecast_expiry as FE

REPO = Path(__file__).resolve().parents[1]


def _print_tree_check(before: dict, after: dict) -> dict:
    d = FE.tree_diff(before, after)
    print(f"\nlive folder files: before {d['n_before']:,}  after {d['n_after']:,}  "
          f"added {d['n_added']}  removed {d['n_removed']}  size changed {d['n_resized']}")
    for k in ("added", "removed", "resized"):
        for f in d[k][:20]:
            print(f"  {k:8s} {f}")
    return d


def _ours_or_zero(d: dict) -> int:
    """4 when a path in the live folder carrying this tool's output name moved, else 0.
    The full lists are compared, not the printed sample."""
    name = _config.FORECAST_EXPIRY_SUBDIR
    ours = [f for k in ("all_added", "all_removed", "all_resized") for f in d.get(k, []) if name in f]
    if ours:
        print(f"\nFAILED: {len(ours)} path(s) named {name!r} moved inside the live folder: {ours[:10]}")
        return 4
    if d["n_added"] or d["n_removed"] or d["n_resized"]:
        print("\nNOTE: the live jobs changed the files named above while this ran; none carries this "
              f"tool's output name ({name!r}), and this process writes only under --out")
    return 0


def cmd_sweep(a: argparse.Namespace) -> int:
    root, out = Path(a.data_root), Path(a.out)
    as_of = date.fromisoformat(a.as_of) if a.as_of else None
    camp_as_of = date.fromisoformat(a.campaign_as_of) if a.campaign_as_of else None
    lines = None
    label = ""
    if not a.no_campaign:
        ref, path = a.campaign_ref, _config.FORECAST_EXPIRY_CAMPAIGN_PATH
        lines = lambda: FE.iter_git_blob_lines(REPO, ref, path)      # noqa: E731
        label = f"git show {ref}:{path} (repo {REPO})"
    before = FE.snapshot_tree(root)
    try:
        rec = FE.sweep(data_root=root, out_dir=out, as_of=as_of, campaign_lines=lines,
                       campaign_label=label, campaign_as_of=camp_as_of)
    except FE.ForecastExpiryRefused as exc:
        print(f"REFUSED: {exc}")
        return 2
    after = FE.snapshot_tree(root)
    print("=" * 72)
    print(f"FORECAST EXPIRY SWEEP  as of {rec['as_of']}  ({rec['ledger']})")
    print("=" * 72)
    print("\nVOID RULE (stated before counting):\n  " + rec["void_rule"])
    ok = True
    for led, r in rec["reconciliation"].items():
        print(f"\nreconciliation [{led}]")
        print(f"  rows read          {r['rows_read']:>8,}")
        for s in FE.STATES:
            print(f"  {s:18s} {r[s]:>8,}")
        print(f"  sum of states      {r['sum_of_states']:>8,}   reconciles: {r['reconciles']}  "
              f"(unparseable {r['unparseable_lines']}, duplicate ids {r['duplicate_ids']})")
        ok &= bool(r["reconciles"])
    print(f"\nvalid_until basis: {rec['valid_until_basis_counts']}")
    print("\nby kind (observable|horizon): rows, valid_until derivable, states")
    for k, v in rec["by_kind"].items():
        print(f"  {k:28s} {v['rows']:>7,}  derivable {v['derivable']:>7,}  "
              + "  ".join(f"{s} {v[s]:,}" for s in FE.STATES if v[s]))
    print(f"\nUNDATED: {rec['undated']['n']}")
    for u in rec["undated"]["rows"][:20]:
        print(f"  {u['forecast_id']} line {u['line']}: {u['reason']}")
    eu = rec["expired_ungraded"]
    print(f"\nEXPIRED_UNGRADED (a grade is owed): {eu['n']}  "
          f"({eu['n_before_resolver_date']} before the resolver's own resolves_after)")
    print(f"  dispositions: {eu['dispositions']}")
    print(f"  waiting for: {eu['waiting_for']}")
    sc = rec["score"]
    print(f"\nscore: mean Brier {sc['mean_brier_voids_excluded']} over {sc['graded_rows_with_brier']:,} graded "
          f"rows; {sc['voids_on_record']} voids on record carry no Brier. {sc['note']}")
    if "campaign" in rec:
        c = rec["campaign"]
        print(f"\ncampaign ledger copy: {c['source']}")
        print(f"  rows read {c['rows_read']:,}; overdue as of {c['overdue_as_of']} "
              f"({c['overdue_predicate']}): {c['n_overdue']:,}   council quoted {c['quoted']:,}")
        for k, v in c["dispositions"].items():
            print(f"  {k:20s} {v:>7,}")
        print(f"  sum                  {c['sum_of_dispositions']:>7,}   reconciles: {c['reconciles']}")
        print(f"  VOID on the ledger's own record {c['void_on_ledger_record']:,}; proposed here "
              f"(side ledger only) {c['void_proposed_side_ledger_only']:,}; codes {c['void_codes']}")
        print(f"  WAITING_INPUT for: {c['waiting_for']}")
        print(f"  ...of which the bars exist only in llm_portfolio/global_bars.parquet (not read by "
              f"forecast_grader): {c['waiting_with_bars_only_in_global_panel']}")
        ok &= bool(c["reconciles"])
    print(f"\nbar panel: {rec['bar_panel']}")
    print(f"side ledger {rec['side_ledger']}")
    print(f"receipt {rec.get('receipt_path')}")
    print(f"ledger bytes before {rec['ledger_bytes_before']:,} after {rec['ledger_bytes_after']:,} "
          f"(live jobs rewrite it in place; this process opened it read-only)")
    d = _print_tree_check(before, after)
    if not ok:
        print("\nFAILED: the counts do not reconcile")
        return 3
    return _ours_or_zero(d)


def _newest_pair(pa_dir: Path, run_id: str | None) -> str:
    if run_id:
        return run_id
    dna = {x.stem.replace("book_dna_", "") for x in pa_dir.glob("book_dna_*.json")}
    roi = {x.stem.replace("roi_", "") for x in pa_dir.glob("roi_*.json")}
    shared = sorted(dna & roi)
    if not shared:
        raise FE.ForecastExpiryRefused(f"no roi_<run> + book_dna_<run> pair in {pa_dir}")
    return shared[-1]


def cmd_labels(a: argparse.Namespace) -> int:
    from backend import db as _db
    from backend.services import book_dna as BD
    from backend.services import xs_ranker as XR
    root, out = Path(a.data_root), Path(a.out)
    try:
        FE._out_must_be_outside(root, out)
        pa = root / "paper_accounts"
        run_id = _newest_pair(pa, a.run_id)
        dna = json.loads((pa / f"book_dna_{run_id}.json").read_text(encoding="utf-8"))
        roi = json.loads((pa / f"roi_{run_id}.json").read_text(encoding="utf-8"))
    except (FE.ForecastExpiryRefused, OSError, ValueError) as exc:
        print(f"REFUSED: {exc}")
        return 2
    before = FE.snapshot_tree(root)
    # Point book_dna's readers at the data root (module attributes, this process only),
    # and the paper-books database at a COPY in a temp folder (book_dna opens it immutable).
    BD.PA_DIR, BD.LLM_DIR = root / "paper_accounts", root / "llm_portfolio"
    BD.PC_NAV, BD.UNIVERSE_DIR = root / "pc_book" / "nav.jsonl", root / "potential_universe"
    XR.BARS_PATH = root / "prices_2025_26" / "bars.parquet"
    tmp = Path(tempfile.mkdtemp(prefix="aegis-ch42-db-"))
    try:
        src_db = root.parent / "aegis_pi.db"
        if src_db.exists():
            shutil.copy2(src_db, tmp / "aegis_pi.db")
            _db.DB_PATH = tmp / "aegis_pi.db"
        inputs = BD.load_inputs(roi, fetch_lanes=False, read_only_db=True)
        syms: set = set()
        for b in inputs.get("books") or []:
            syms |= {str(x.get("ticker")) for x in b.get("positions") or [] if x.get("ticker")}
        px, src = BD.load_prices(syms)
        p = BD.params()
        today = date.fromisoformat(str(dna.get("generated_utc"))[:10]) if dna.get("generated_utc") else date.today()
        books = BD.book_rows(roi, inputs, px, p, today)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    shipped = {str(b.get("account")): (b.get("evidence") or {}).get("label") for b in dna.get("books") or []}
    mism = [(b["account"], shipped.get(b["account"]), b["evidence"]["label"]) for b in books
            if shipped.get(b["account"]) is not None and shipped[b["account"]] != b["evidence"]["label"]]
    n = int(a.trailing or _config.FORECAST_EXPIRY_LABEL_TRAILING_SESSIONS)
    rows = FE.label_stepdown(books, spy_sessions=px.dates("SPY"), p=p, n_trailing=n,
                             vol_cut=float(_config.FORECAST_EXPIRY_REGIME_VOL_CUT))
    down = [r for r in rows if r["would_step_down"]]
    undet = [r for r in rows if r["step_down"] == "CANNOT_DETERMINE"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt = {"schema": FE.SCHEMA + "/labels", "generated_utc": stamp, "run_id": run_id,
               "data_root": str(root), "prices": src, "trailing_sessions": n,
               "label_rule": "book_dna.evidence_label, unchanged; fair twin not recomputed on the trailing window "
                             "(REPLICATED on the trailing window can come only from a same-rule book that is "
                             "itself EARLY_EVIDENCE on its trailing window)",
               "gaps": inputs.get("gaps"), "n_books": len(rows),
               "rebuilt_vs_shipped_label_mismatches": mism,
               "n_would_step_down": len(down), "would_step_down": [r["account"] for r in down],
               "n_step_down_cannot_determine": len(undet),
               "step_down_cannot_determine": [r["account"] for r in undet],
               "books": rows, "note": "REPORT ONLY: no label was changed; results_voice is untouched."}
    sub = out / _config.FORECAST_EXPIRY_SUBDIR
    sub.mkdir(parents=True, exist_ok=True)
    path = FE._write_new(sub / f"labels_{stamp}.json", json.dumps(receipt, indent=1, default=str))
    after = FE.snapshot_tree(root)
    print("=" * 72)
    print(f"EVIDENCE LABEL STEP-DOWN (report only)  roi/book_dna run {run_id}; trailing {n} SPY sessions")
    print("=" * 72)
    print(f"books {len(rows)}; rebuilt label differs from the shipped receipt on {len(mism)}: {mism[:10]}")
    print(f"gaps: {inputs.get('gaps')}")
    print(f"\n{'account':34s} {'label':18s} {'earned':23s} {'regime':22s} {'trailing':18s} {'trail regime':22s}")
    for r in sorted(rows, key=lambda r: (not r["would_step_down"], r["account"])):
        if not (r["step_down"] != "NO" or not str(r["label"]).startswith("OBSERVED")):
            continue
        ew, tw = r["earned_window"], r["trailing_window"]
        print(f"{r['account'][:34]:34s} {str(r['label'])[:18]:18s} "
              f"{str(ew['from'])[:10]}..{str(ew['to'])[:10]} {str(r['earned_regime'].get('tag'))[:22]:22s} "
              f"{r['trailing_label'][:18]:18s} {str(r['trailing_regime'].get('tag'))[:22]:22s}"
              f"{'  STEP DOWN' if r['would_step_down'] else ''}"
              f"{'  STEP DOWN? CANNOT DETERMINE' if r['step_down'] == 'CANNOT_DETERMINE' else ''}")
        if r["step_down"] != "NO":
            print(f"    trailing {tw['from']}..{str(tw['to'])[:10]} {tw['sessions']} sessions, excess "
                  f"{tw['excess_pp']} pp: {r['trailing_why']}")
    print(f"\nwould step down: {len(down)}  {[r['account'] for r in down]}")
    print(f"step-down cannot be determined: {len(undet)}  {[r['account'] for r in undet]}")
    print(f"receipt {path}")
    d = _print_tree_check(before, after)
    return _ours_or_zero(d)


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("sweep")
    s.add_argument("--data-root", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--as-of", default=None)
    s.add_argument("--campaign-ref", default=_config.FORECAST_EXPIRY_CAMPAIGN_REF)
    s.add_argument("--campaign-as-of", default=None)
    s.add_argument("--no-campaign", action="store_true")
    s.set_defaults(fn=cmd_sweep)
    lab = sp.add_parser("labels")
    lab.add_argument("--data-root", required=True)
    lab.add_argument("--out", required=True)
    lab.add_argument("--run-id", default=None)
    lab.add_argument("--trailing", type=int, default=None)
    lab.set_defaults(fn=cmd_labels)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
