"""RE-GRADE every night receipt that says "net" under the TAQ empirical curve.

    python -m scripts.cost_curve_regrade --dry-run
    python -m scripts.cost_curve_regrade

NOTHING IS EVER OVERWRITTEN. Each source receipt gets a NEW file beside it,
`<name>_regrade_taq.json`, and the summary lands in
`backend/data/optimus/cost_curve/`. A receipt is an append-only record of what
was believed when; editing one in place is how a number changes identity
without changing its name.

WHAT A RE-GRADE IS, AND WHAT IT IS NOT
======================================
It is a RATE SUBSTITUTION on the SAME realised turnover, compounded over the
same periods:

    adj      = ((1 - c_curve) / (1 - c_flat)) ** n_periods
    net_curve = net_archived * adj                     where c_x = turnover * 2 * bps_x / 1e4

It is NOT a re-run. Re-running 300+ archived books over their own histories is
days of compute and would change the holdings too, which is a different
question ("what would the book have DONE at these costs") from the one the
roadmap asks ("what would it have BEEN WORTH"). The substitution answers the
second exactly and says so.

WHY THIS FORM AND NOT "RECONSTRUCT NET FROM GROSS"
==================================================
Because `adj` is identically 1 when the target curve IS the source curve, so a
no-op re-grade reproduces the archived net TO THE CENT by construction rather
than by luck -- which is the regression test (spec S4 item 5) that proves the
new path is a superset of the old one. Reconstructing net from gross instead
would require the per-period turnover series, which these receipts did not
keep, and would miss by the amount turnover varied.

WHERE IT REFUSES
================
A node with no turnover on disk, no identifiable cost rate, or no period count
is REFUSED BY NAME and counted. A check that did not run is not a check that
passed, and "skipped silently" is how 400 unscoreable rows once got a clean
verdict printed over them.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from backend.services import cost_curve as CC

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "backend" / "data" / "optimus"
OUT_DIR = DATA / "cost_curve"

#: Where the night jobs and the tracker write. Named, not globbed from the
#: whole tree: a re-grade that wandered into the arena's sealed seeds would be
#: writing beside the track record.
SOURCE_DIRS = ("night_factory_*", "tracker_backtest")

#: Keys a node may carry its realised turnover under. Per REBALANCE period.
TURNOVER_KEYS = ("mean_turnover", "turnover_mean", "mean_turnover_monthly")
#: Keys a node (or an enclosing dict) may carry its flat one-way rate under.
COST_KEYS = ("cost_bps_per_side", "cost_bps", "COST_BPS", "cost_bps_side")
#: Keys a node may carry its period count under.
PERIOD_KEYS = ("months", "n_months", "n_periods")

SUFFIX = "_regrade_taq.json"


def cross_section() -> tuple[np.ndarray, np.ndarray]:
    """(predicted half spread bps, dollar volume) for every local symbol.

    Computed ONCE. The archived books are graded on a CRSP panel keyed on
    permno; this curve is keyed on ticker over 23 days of 2026. There is no
    honest join, so what the re-grade substitutes is the regression's median
    prediction over a REAL cross-section above the book's own declared
    execution floor -- a representative rate, labelled as one.
    """
    import pandas as pd

    from scripts.cost_curve_fit import BARS, RHS_WINDOW_SESSIONS
    bars = pd.read_parquet(BARS, columns=["symbol", "date", "close", "volume"])
    fit = CC.load_regression()
    spreads, dvs = [], []
    for _sym, d in bars.groupby("symbol", sort=True):
        d = d.sort_values("date").tail(RHS_WINDOW_SESSIONS)
        if len(d) < RHS_WINDOW_SESSIONS // 2:
            continue
        close = d["close"].to_numpy(dtype=float)
        vol = d["volume"].to_numpy(dtype=float)
        if not (np.all(np.isfinite(close)) and close.min() > 0):
            continue
        dv = float(np.median(close * vol))
        r = np.diff(np.log(close))
        spreads.append(CC.regression_half_spread_bps(
            dv, float(np.median(close)),
            float(np.std(r, ddof=1) * math.sqrt(252.0)), fit))
        dvs.append(dv)
    return np.asarray(spreads), np.asarray(dvs)


def representative_bps(spreads: np.ndarray, dvs: np.ndarray,
                       floor_usd: float | None) -> float:
    f = float(floor_usd) if floor_usd else 0.0
    m = dvs >= f
    if not m.any():                                       # pragma: no cover
        m = np.ones_like(dvs, dtype=bool)
    return float(np.median(spreads[m]))


def _first(d: dict, keys) -> tuple[str, float] | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return k, float(v)
    return None


def find_books(blob, path="", inherited=None, out=None, family=None):
    """Every node that reports a NET and might be re-gradable, with its family.

    `inherited` carries a cost rate declared by an enclosing dict (a job's
    `search_space.cost_bps`, a design block's `cost_bps_per_side`) down to the
    rows it governs. Inheritance is RECORDED on the output row, because "the
    rate came from three levels up" is exactly the kind of fact that stops
    being true after a refactor.
    """
    out = [] if out is None else out
    if isinstance(blob, dict):
        here = dict(inherited or {})
        got = _first(blob, COST_KEYS)
        if got:
            here["cost_bps"] = got[1]
            here["cost_bps_from"] = f"{path}/{got[0]}" or got[0]
        if "terminal_wealth_net" in blob and isinstance(
                blob.get("terminal_wealth_net"), (int, float)):
            # A FAMILY IS THE SIBLINGS, not the file. The node's family is the
            # container it sits in -- the list it is an element of, or the
            # dict whose values are the arms. Grouping every book in a file
            # into one family compares a top-50 value-weighted book against a
            # cohort study and calls the difference a rank change.
            out.append({"path": path or "/", "node": blob,
                        "inherited": here, "family": family or "/"})
        for k, v in blob.items():
            find_books(v, f"{path}/{k}", here, out, path or "/")
    elif isinstance(blob, list):
        for i, v in enumerate(blob):
            find_books(v, f"{path}[{i}]", inherited, out, path or "/")
    return out


def regrade_node(entry: dict, spreads, dvs, target_curve: str = "taq_empirical") -> dict:
    node, inh = entry["node"], entry["inherited"]
    row = {"path": entry["path"], "family": entry["family"],
           "label": node.get("label") or node.get("key") or node.get("arm"),
           "terminal_wealth_net_archived": float(node["terminal_wealth_net"])}

    turn = _first(node, TURNOVER_KEYS)
    per = _first(node, PERIOD_KEYS)
    bps = _first(node, COST_KEYS)
    src = "node"
    if bps is None and "cost_bps" in inh:
        bps, src = ("inherited", inh["cost_bps"]), inh.get("cost_bps_from", "?")

    missing = []
    if turn is None:
        missing.append("turnover (no mean_turnover on disk)")
    if per is None:
        missing.append("period count (no months)")
    if bps is None:
        missing.append("flat cost rate (no cost_bps_per_side, none inherited)")
    if missing:
        row.update(regraded=False, refused=True, refused_for=missing)
        return row

    n = int(per[1])
    turnover, flat_bps = turn[1], bps[1]
    floor = node.get("tradable_floor_usd") or inh.get("tradable_floor_usd")
    # `--target-curve flat` is the NO-OP re-grade: the same pipeline with the
    # target rate set back to the source rate. It is the regression test that
    # proves this code path is a superset of the old one rather than a rewrite
    # that happens to agree by construction (spec S4 item 5).
    curve_bps = (flat_bps if target_curve == "flat"
                 else representative_bps(spreads, dvs, floor))

    c_flat = turnover * 2.0 * flat_bps / 1e4
    c_curve = turnover * 2.0 * curve_bps / 1e4
    tw = row["terminal_wealth_net_archived"]
    # The no-op identity: with curve_bps == flat_bps this is exactly 1.0 and
    # the re-graded net IS the archived net, to the cent.
    adj = ((1.0 - c_curve) / (1.0 - c_flat)) ** n
    net_curve = tw * adj

    row.update({
        "regraded": True, "refused": False,
        "months": n, "mean_turnover_per_period": turnover,
        "cost_bps_per_side_flat": flat_bps, "cost_bps_source": src,
        "cost_bps_one_way_curve": round(curve_bps, 4),
        "tradable_floor_usd": floor,
        "monthly_cost_flat": round(c_flat, 6),
        "monthly_cost_curve": round(c_curve, 6),
        "terminal_wealth_net_flat_reproduced": round(tw, 6),
        "terminal_wealth_net_curve": round(net_curve, 6),
        "delta_tw_multiple": round(net_curve - tw, 6),
        "delta_tw_ratio": round(net_curve / tw, 6) if tw else None,
    })
    if n > 0 and tw > 0 and net_curve > 0:
        yrs = n / 12.0
        row["cagr_net_flat"] = round(tw ** (1 / yrs) - 1.0, 6)
        row["cagr_net_curve"] = round(net_curve ** (1 / yrs) - 1.0, 6)
        row["delta_cagr_pp"] = round(
            100.0 * (row["cagr_net_curve"] - row["cagr_net_flat"]), 4)
    gross = node.get("terminal_wealth_gross")
    if isinstance(gross, (int, float)) and gross > 0:
        # FIDELITY, not a claim: reconstructing net from gross assumes the
        # turnover was CONSTANT at its mean. The residual is how wrong that
        # assumption is on this book, printed rather than assumed small.
        recon = float(gross) * (1.0 - c_flat) ** n
        row["terminal_wealth_net_from_gross_const_turnover"] = round(recon, 6)
        row["reconstruction_residual_ratio"] = round(recon / tw, 6) if tw else None
    return row


def _ancestors(path: str) -> list[str]:
    """Every container path above a node, deepest first."""
    out, cur = [], path
    while True:
        cut = max(cur.rfind("/"), cur.rfind("["))
        if cut <= 0:
            out.append("/")
            return out
        cur = cur[:cut]
        out.append(cur)


def assign_families(rows: list[dict]) -> None:
    """A family is the DEEPEST container holding more than one book.

    The first version used the immediate parent, which made every
    `/scoreboards/1m/<model>/book` a family of one and reported "no ranking
    changed" because there were no rankings -- a check that cannot fail. The
    rule now climbs until it finds siblings, so `/scoreboards/1m` is the
    family and its models are compared against each other, which is the
    comparison a leaderboard actually makes.
    """
    counts: dict[str, int] = {}
    for r in rows:
        for a in _ancestors(r["path"]):
            counts[a] = counts.get(a, 0) + 1
    for r in rows:
        r["family"] = next((a for a in _ancestors(r["path"])
                            if counts.get(a, 0) >= 2), "/")


def family_rankings(rows: list[dict]) -> list[dict]:
    """Does the ORDER change, or only the LEVEL? Computed, never assumed."""
    fams: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("regraded"):
            fams.setdefault(r["family"] or "/", []).append(r)
    out = []
    for fam, rs in sorted(fams.items()):
        if len(rs) < 2:
            continue
        flat = [r["path"] for r in sorted(
            rs, key=lambda r: -r["terminal_wealth_net_archived"])]
        curve = [r["path"] for r in sorted(
            rs, key=lambda r: -r["terminal_wealth_net_curve"])]
        n_inv = sum(1 for i in range(len(rs)) for j in range(i + 1, len(rs))
                    if ((rs[i]["terminal_wealth_net_archived"]
                         - rs[j]["terminal_wealth_net_archived"])
                        * (rs[i]["terminal_wealth_net_curve"]
                           - rs[j]["terminal_wealth_net_curve"])) < 0)
        npairs = len(rs) * (len(rs) - 1) // 2
        out.append({"family": fam, "n": len(rs),
                    "ranking_unchanged": flat == curve,
                    "n_discordant_pairs": n_inv,
                    "kendall_tau": round(1.0 - 2.0 * n_inv / npairs, 6) if npairs else None,
                    "top_flat": flat[0], "top_curve": curve[0],
                    "top_unchanged": flat[0] == curve[0]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="re-grade night receipts")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--target-curve", default="taq_empirical",
                    choices=["taq_empirical", "flat"],
                    help="'flat' is the NO-OP re-grade: it must reproduce "
                         "every archived net to the cent")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    files: list[Path] = []
    for pat in SOURCE_DIRS:
        for d in sorted(DATA.glob(pat)):
            if d.is_dir():
                # `_smoke.json` receipts are SCRATCH: gitignored, never the record
                # (the leaderboard sync skips them the same way). Re-grading one
                # writes a tracked artefact beside an untracked source -- which is
                # exactly what turned CI red on 2026-09-12: the runner's checkout
                # had the re-grade and not the source.
                files += [p for p in sorted(d.rglob("*.json"))
                          if not p.name.endswith(SUFFIX)
                          and not p.name.endswith("_smoke.json")]

    spreads, dvs = cross_section()
    summary_files, n_reg, n_ref, n_fam_changed, deltas = [], 0, 0, 0, []
    noop_worst = 0.0
    refused_by_name: list[str] = []

    for p in files:
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:                          # pragma: no cover
            refused_by_name.append(f"{p.name}: unparseable ({exc})")
            continue
        entries = find_books(blob)
        if not entries:
            continue
        rows = [regrade_node(e, spreads, dvs, args.target_curve)
                for e in entries]
        reg = [r for r in rows if r.get("regraded")]
        ref = [r for r in rows if r.get("refused")]
        assign_families(rows)
        fams = family_rankings(rows)
        if args.target_curve == "flat":
            noop_worst = max([noop_worst] + [
                abs(r["terminal_wealth_net_curve"]
                    - r["terminal_wealth_net_archived"]) for r in reg])
        n_reg += len(reg)
        n_ref += len(ref)
        n_fam_changed += sum(1 for f in fams if not f["ranking_unchanged"])
        deltas += [r["delta_cagr_pp"] for r in reg if "delta_cagr_pp" in r]
        for r in ref:
            refused_by_name.append(
                f"{p.name}{r['path']}: {'; '.join(r['refused_for'])}")

        receipt = {
            "artefact": "COST-CURVE-REGRADE-1",
            "licence": "PRODUCT_EXPERIMENT (infrastructure; makes no claim)",
            "generated_at": datetime.now(UTC).isoformat(),
            "source_receipt": str(p.relative_to(ROOT)).replace("\\", "/"),
            "source_receipt_unchanged": True,
            "target_curve": args.target_curve,
            "eta": CC.ETA_SQRT_IMPACT,
            "method": ("rate substitution on the SAME realised turnover: "
                       "net_curve = net_archived * ((1-c_curve)/(1-c_flat))**n. "
                       "Identically 1 when the curves match, so a no-op "
                       "re-grade reproduces the archived net to the cent."),
            "what_this_is_not": (
                "NOT a re-run. The holdings are unchanged, so this answers "
                "'what would this book have been WORTH at these costs', not "
                "'what would it have DONE'."),
            "curve_rate_caveat": (
                "the curve rate is a REPRESENTATIVE median prediction over a "
                "2025-26 cross-section above the book's own declared "
                "execution floor -- these books are graded on a permno-keyed "
                "CRSP panel and there is no honest join to a ticker-keyed "
                "2026 TAQ panel. The IMPACT term is omitted: no notional is "
                "declared, so participation is undefined."),
            "source_panel_verdict_status": "DEFERRED (v1 unfiltered)",
            "n_regraded": len(reg), "n_refused": len(ref),
            "family_rankings": fams,
            "rows": rows,
        }
        target = p.with_name(p.stem + (SUFFIX if args.target_curve
                                       == "taq_empirical" else "_regrade_flat.json"))
        if not args.dry_run:
            target.write_text(json.dumps(receipt, indent=1) + "\n",
                              encoding="utf-8")
        summary_files.append({
            "source": receipt["source_receipt"],
            "regrade": str(target.relative_to(ROOT)).replace("\\", "/"),
            "n_regraded": len(reg), "n_refused": len(ref),
            "n_families": len(fams),
            "n_families_ranking_changed": sum(
                1 for f in fams if not f["ranking_unchanged"]),
        })

    summary = {
        "artefact": "COST-CURVE-REGRADE-SUMMARY-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "dry_run": bool(args.dry_run),
        "target_curve": args.target_curve,
        "n_source_files_scanned": len(files),
        "n_source_files_with_books": len(summary_files),
        "n_receipts_regraded": n_reg,
        "n_refused_unidentifiable": n_ref,
        "n_families_ranking_changed": n_fam_changed,
        "median_level_delta_cagr_pp": (round(float(np.median(deltas)), 4)
                                       if deltas else None),
        "max_abs_level_delta_cagr_pp": (round(float(np.max(np.abs(deltas))), 4)
                                        if deltas else None),
        "refused_by_name": sorted(refused_by_name),
        "files": summary_files,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = (Path(args.out) if args.out
           else OUT_DIR / f"regrade_summary_{datetime.now(UTC).date()}.json")
    if not args.dry_run:
        out.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    if args.target_curve == "flat":
        # THE NO-OP MUST BE EXACT. Not "close": `adj` is (1-c)/(1-c) to the
        # power n, which is 1.0 in IEEE arithmetic, so any non-zero here means
        # the pipeline is doing something to the number besides substituting
        # a rate.
        summary["no_op_max_abs_error"] = noop_worst
        print(f"  NO-OP re-grade worst absolute error: {noop_worst:.12g}")
    print(("DRY RUN: " if args.dry_run else "") + f"{n_reg} re-graded, "
          f"{n_ref} refused, {n_fam_changed} families changed ranking")
    print(f"  median level delta {summary['median_level_delta_cagr_pp']} pp CAGR, "
          f"max |delta| {summary['max_abs_level_delta_cagr_pp']} pp")
    if not args.dry_run:
        print(f"  summary -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
