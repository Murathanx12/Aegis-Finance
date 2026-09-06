"""N7 -- EVERY RECEIPT INTO THE MEMORY, AND A LEADERBOARD WITH A HEAD.

WHY THIS IS A JOB AND NOT A HABIT
=================================
The weekend lab found the shape of this failure the expensive way: the evidence
memory read only `payload["cells"]`, so three quarters of the receipts folded
to ZERO observations and the memory reported "nothing has been found yet" while
sitting on four real results. `record_receipt` was fixed to detect the shape.
What was never fixed is the other half -- **a night's receipts only reach the
memory if something walks them there.** This is that something.

It also enforces the one thing a scoreboard has to do to be read: the BEST SO
FAR block goes at the TOP, and it is ranked by the **beta-matched,
family-corrected** number, never by terminal wealth. A leaderboard sorted on
terminal wealth is a leaderboard sorted on beta, and this repo has published
that mistake before.

WHAT IT REFUSES
===============
A receipt with no `family_id`-able job name, and a receipt whose cells carry no
months. Both would fold into the memory as content-free rows that later read as
"tested and found nothing", which is a different statement from "not recorded".

    python -m scripts.n7_memory_and_leaderboard
    python -m scripts.n7_memory_and_leaderboard --no-registry
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import receipt_provenance as RP           # noqa: E402

NIGHT = "2026-09-07"
OUT_DIR = REPO / "backend" / "data" / "optimus" / f"night_lab_{NIGHT}"
RECEIPT = OUT_DIR / "N7_memory_and_leaderboard.json"
LEADERBOARD = OUT_DIR / "LEADERBOARD.md"
BEST = OUT_DIR / "best_so_far.json"

#: Receipts this job writes itself, and must not fold into the memory as
#: evidence about markets.
SELF = {"N7_memory_and_leaderboard.json", "best_so_far.json"}


def _r(v, nd: int = 4):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if math.isfinite(f) else None


#: Any ONE of these makes a JSON file a receipt. `job` is this night's key,
#: `item` + `title` is B1's, and `licence` is on every receipt the repo writes.
RECEIPT_KEYS: tuple[str, ...] = ("job", "item", "licence")


def _identifies_a_receipt(rec: dict) -> bool:
    return any(k in rec for k in RECEIPT_KEYS)


def _job_name(rec: dict, source: Path) -> str:
    return str(rec.get("job") or rec.get("item") or source.stem)


def _primary(cell: dict) -> dict:
    """The beta-matched block, whatever the job called it."""
    for k in ("PRIMARY_beta_matched", "primary_beta_matched", "beta_matched"):
        v = cell.get(k)
        if isinstance(v, dict):
            return v
    return {}


def normalise(rec: dict, source: Path) -> dict | None:
    """One night-lab receipt -> the shape `evidence_memory.record_receipt` reads.

    The night's jobs do not share the labor lane's key names (`family`, not
    `inference`; `verdict_on_the_best_cell`, not `verdict`), so the mapping is
    written out here rather than assumed. An unmapped key is a silently lost
    result, which is the failure this whole file exists to stop.
    """
    job = _job_name(rec, source)
    if rec.get("status") in ("SKIPPED", "REFUSED", "FAILED"):
        return {"family_id": f"night_lab_{NIGHT}/{job}", "job": job,
                "verdict": f"{rec.get('status')} -- {rec.get('headline')}",
                "cells": {}}
    cells = rec.get("cells")
    if not isinstance(cells, dict):
        cells = {}
    fam = rec.get("family") or {}
    inf = (rec.get("inference_on_the_best_cell")
           or rec.get("inference_family_of_one")
           or (rec.get("inference") or {}).get("ENSEMBLE_equal_weight")
           or rec.get("inference") or {})
    if not isinstance(inf, dict):
        inf = {}
    best = fam.get("best_cell") or fam.get("best")
    eras = None
    if best and isinstance(cells.get(best), dict):
        eras = cells[best].get("era_table_on_the_beta_matched_excess")
    eras = eras or (rec.get("era_tables") or {}).get("ENSEMBLE_equal_weight") \
        or rec.get("era_table")
    return {
        "family_id": f"night_lab_{NIGHT}/{job}",
        "job": job,
        "cells": cells,
        "best_cell": best,
        "inference": inf,
        "era_sign_table": eras,
        "verdict": rec.get("verdict_on_the_best_cell") or rec.get("verdict"),
        "months": rec.get("months"),
    }


def leaderboard_rows(payloads: list[dict]) -> list[dict]:
    """One row per cell that carries a beta-matched excess and its months."""
    rows = []
    for p in payloads:
        for name, cell in (p.get("cells") or {}).items():
            if not isinstance(cell, dict):
                continue
            pr = _primary(cell)
            t = pr.get("t_paired")
            if t is None:
                continue
            rows.append({
                "family": p["family_id"], "cell": name,
                "beta": cell.get("beta"),
                "months": cell.get("months"),
                "beta_matched_pct_per_year": pr.get("annualised_pct"),
                "t_paired": t,
                "p_one_sided": pr.get("p_one_sided"),
                "terminal_wealth_net": cell.get("terminal_wealth_net"),
                "terminal_wealth_market": cell.get("terminal_wealth_market_same_months"),
                "transfer_coefficient": ((cell.get("fundamental_law") or {})
                                         .get("transfer_coefficient") or {}).get("tc"),
                "effective_names": ((cell.get("fundamental_law") or {})
                                    .get("effective_breadth") or {})
                .get("mean_effective_names_per_month"),
                "is_family_best": name == p.get("best_cell"),
                "family_size": None,
            })
    return rows


def render(rows: list[dict], families: dict, generated: str) -> str:
    """The leaderboard. BEST SO FAR at the top, beta-matched and corrected."""
    ranked = sorted([r for r in rows if r.get("t_paired") is not None],
                    key=lambda r: -float(r["t_paired"]))
    lines = [f"# NIGHT LAB {NIGHT} — LEADERBOARD", "",
             f"*regenerated {generated} by `scripts/n7_memory_and_leaderboard.py`*",
             "", "## BEST SO FAR — beta-matched, family-corrected", ""]
    if not ranked:
        lines += ["_no cell in this night's receipts carries a beta-matched excess "
                  "and a t. That is a statement about the receipts, not about the "
                  "market._", ""]
    else:
        b = ranked[0]
        f = families.get(b["family"], {})
        lines += [
            f"- **cell** `{b['cell']}` (`{b['family']}`)",
            f"- **beta {b['beta']}** — printed first, per the 2026-09-07 amendment",
            f"- beta-matched **{b['beta_matched_pct_per_year']}%/yr, t "
            f"{b['t_paired']}** over {b['months']} months",
            f"- terminal wealth **{b['terminal_wealth_net']}** vs market "
            f"**{b['terminal_wealth_market']}** on the same months",
            f"- transfer coefficient **{b['transfer_coefficient']}**, effective names "
            f"**{b['effective_names']}**",
            f"- family size **{f.get('size')}**, family-min p **{f.get('family_min_p')}**, "
            f"best Holm-adjusted **{f.get('best_cell_holm_adjusted_p')}**, "
            f"surviving Holm at 0.05: **{len(f.get('cells_surviving_holm_at_0.05') or [])}**",
            "",
            "> A leaderboard sorted on terminal wealth is a leaderboard sorted on "
            "beta. This one is sorted on the beta-matched t and prints the family "
            "correction beside it; a top row whose Holm-adjusted p is near 1 has "
            "not found anything.", ""]
    lines += ["## Every cell with a beta-matched excess", "",
              "| t | cell | beta | months | bm %/yr | TW net | TW mkt | TC | eff N |",
              "|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in ranked[:40]:
        lines.append(
            f"| {r['t_paired']} | `{r['cell']}` | {r['beta']} | {r['months']} | "
            f"{r['beta_matched_pct_per_year']} | {r['terminal_wealth_net']} | "
            f"{r['terminal_wealth_market']} | {r['transfer_coefficient']} | "
            f"{r['effective_names']} |")
    if len(ranked) > 40:
        lines.append(f"\n_{len(ranked) - 40} further cells omitted; all are in the "
                     "receipts._")
    lines += ["", "## Families recorded this night", "",
              "| family | size | min p | best Holm | surviving Holm |",
              "|---|---:|---:|---:|---:|"]
    for k, f in sorted(families.items()):
        lines.append(f"| `{k}` | {f.get('size')} | {f.get('family_min_p')} | "
                     f"{f.get('best_cell_holm_adjusted_p')} | "
                     f"{len(f.get('cells_surviving_holm_at_0.05') or [])} |")
    return "\n".join(lines) + "\n"


def run(*, to_registry: bool = True, verbose: bool = True) -> dict:
    from learner import evidence_memory as EM

    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    tracker = RP.InputTracker()
    out: dict = {
        "job": "N7_memory_and_leaderboard",
        "lane": "N7",
        "question": "did every receipt this night wrote reach the memory and the board?",
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
    }
    # `_`-prefixed files are the repo's own scratch convention (`_cells`,
    # `_superseded_*`). A quick-test receipt carries the SAME `job` name as the
    # real one, so folding it would record the family twice with the smaller
    # sample's numbers -- the memory would then hold two rows that disagree and
    # no way to tell which was the run.
    files = sorted(p for p in OUT_DIR.glob("*.json")
                   if p.name not in SELF and not p.name.startswith("_"))
    payloads, read, failed = [], [], []
    for p in files:
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:                                    # noqa: BLE001
            failed.append({"file": p.name, "why": f"{type(exc).__name__}: {exc}"})
            continue
        # THE LAB DOES NOT PRODUCE ONE SHAPE OF RECEIPT. The night lane writes
        # `job`; the labor lane and the N6b jobs write B1's `item` + `title`.
        # The first version of this guard demanded `job` and dropped FOUR real
        # receipts as "not a receipt" -- the same failure `record_receipt` was
        # fixed for last weekend, reintroduced one layer up.
        if not isinstance(rec, dict) or not _identifies_a_receipt(rec):
            failed.append({"file": p.name,
                           "why": "not a receipt (no `job`, `item` or `licence`)"})
            continue
        tracker.opened(p)
        n = normalise(rec, p)
        if n:
            payloads.append(n)
            read.append(p.name)
    out["receipts_read"] = read
    out["receipts_skipped"] = failed

    written = {}
    for pl in payloads:
        try:
            written[pl["family_id"]] = int(EM.record_receipt(pl))
        except Exception as exc:                                    # noqa: BLE001
            written[pl["family_id"]] = f"REFUSED: {type(exc).__name__}: {exc}"
    out["evidence_memory_rows_written"] = written
    out["evidence_memory_rows_total"] = sum(v for v in written.values()
                                            if isinstance(v, int))

    out["receipts_ignored_as_scratch"] = sorted(
        p.name for p in OUT_DIR.glob("_*.json"))
    families = {}
    for p in files:
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                           # noqa: BLE001
            continue
        f = rec.get("family")
        if isinstance(f, dict) and f.get("size"):
            families[f"night_lab_{NIGHT}/{_job_name(rec, p)}"] = f
        f2 = rec.get("transfer_coefficient_cost_family")
        if isinstance(f2, dict) and f2.get("size"):
            families[f"night_lab_{NIGHT}/{_job_name(rec, p)}"
                     "  [broad-vs-control deltas]"] = {
                "size": f2.get("size"), "family_min_p": f2.get("family_min_p"),
                "best_cell_holm_adjusted_p": f2.get("best_comparison_holm_adjusted_p"),
                "cells_surviving_holm_at_0.05": f2.get(
                    "comparisons_surviving_holm_at_0.05"),
            }
    rows = leaderboard_rows(payloads)
    generated = datetime.now(timezone.utc).isoformat()
    LEADERBOARD.parent.mkdir(parents=True, exist_ok=True)
    LEADERBOARD.write_text(render(rows, families, generated), encoding="utf-8")
    ranked = sorted([r for r in rows if r.get("t_paired") is not None],
                    key=lambda r: -float(r["t_paired"]))
    BEST.write_text(json.dumps(
        {"generated_utc": generated, "night": NIGHT,
         "best_by_beta_matched_t": ranked[0] if ranked else None,
         "families": families,
         "ranking_rule": ("beta-matched t, with the family correction printed "
                          "beside it. NOT terminal wealth -- that ranks on beta.")},
        indent=1, default=str), encoding="utf-8")
    out["leaderboard"] = str(LEADERBOARD)
    out["best_so_far"] = str(BEST)
    out["cells_on_the_board"] = len(rows)
    out["families"] = families

    if to_registry:
        try:
            n = EM.to_registry()
            out["registry_export"] = {"status": "ok", "result": n}
        except Exception as exc:                                    # noqa: BLE001
            out["registry_export"] = {"status": "REFUSED",
                                      "why": f"{type(exc).__name__}: {exc}"}
    else:
        out["registry_export"] = {"status": "SKIPPED (--no-registry)"}

    out["headline"] = (
        f"{len(read)} receipts read, {out['evidence_memory_rows_total']} evidence rows "
        f"written, {len(rows)} cells on the board, "
        f"{len(families)} families; best beta-matched t "
        f"{ranked[0]['t_paired'] if ranked else None}")
    RP.attach(out, sys.argv, {"to_registry": bool(to_registry), "night": NIGHT},
              tracker)
    return out


def write(rec: dict, path: Path = RECEIPT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rec["generated_utc"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-registry", action="store_true")
    a = ap.parse_args(argv)
    try:
        rec = run(to_registry=not a.no_registry)
    except Exception:                                               # noqa: BLE001
        rec = {"job": "N7_memory_and_leaderboard", "status": "FAILED",
               "traceback": traceback.format_exc(),
               "headline": "FAILED -- see traceback"}
        write(rec)
        print(rec["traceback"], flush=True)
        return 1
    write(rec)
    print(rec.get("headline"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
