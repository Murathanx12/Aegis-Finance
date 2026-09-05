"""LABOR DAY LAB — lane B, item B3. SCENARIO BRIDGE v2 FIELD COVERAGE.

    python -m scripts.labor_b3_bridge_coverage            # full (re-grades 20)
    python -m scripts.labor_b3_bridge_coverage --no-regrade

THE QUESTION
============
On 2026-09-04 `scenario_bridge_rerun` moved `event_type` from UNMAPPABLE to
PROXY on the strength of the SEC 8-K item tape, and maps-to-nothing fell from
46.7% to **40.0%** (6 of 15 retrieval fields). Two more artefacts have landed
since: `backend/data/optimus/graph/companyworld_v1.parquet` (2,020 typed,
permno-resolved, quote-verified relation edges) and
`graph/companyworld_inputs/cik_lookup.parquet` (1.05M EDGAR name -> CIK rows,
which `companyworld_extract.cik_permno_windows` turns into a HISTORICAL,
rename-proof CIK <-> permno bridge). This item asks what they actually buy.

THE ANSWER IS REPORTED UNDER TWO STANDARDS, AND THE DIFFERENCE IS THE FINDING
============================================================================
The 20260904 rerun's standard was OWNERSHIP: "the concept now maps to a dated
tape we hold, with a documented bridge". Applied consistently, that standard
promotes two more fields — `company_role` (the customer/supplier/competitor
relation IS what companyworld_v1 stores) and `actors` (1,059 named
counterparties, each resolved to a permno).

But the companyworld tape runs **1999-09-01 to 2011-03-03**, and it contains
**ZERO** edges inside the 2013-2024 panel window. So a second, stricter standard
is computed beside it — PANEL-OVERLAP: a field is only upgraded when the tape it
maps to actually covers the panel's own dates. Under that standard those two
fields stay UNMAPPABLE and only `event_type` (8-K tape, 2013-01-02 onward)
survives.

Reporting one number would have been a choice about which standard the reader
gets. Reporting both makes the honest headline visible: **the coverage gain from
companyworld_v1 is NOMINAL, not EFFECTIVE** — we own the concept and cannot yet
use it on this panel. The 8-K tape starts 2013, so there is no 2010-13 EDGAR era
and no coverage is claimed there.

GRADES ARE UNCHANGED BY CONSTRUCTION and the run proves it rather than asserting
it: none of these fields is a retrieval predicate (`scenario_predicates` still
ignores every one of them), so the 20 sealed scenarios must re-grade to exactly
the same spreads. A nonzero change count is a bug report.

Licence: PRODUCT_EXPERIMENT. Zero LLM calls; the same 20 scenarios, not
regenerated.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pandas as pd                                             # noqa: E402

from scripts import companyworld_extract as CW                  # noqa: E402
from scripts import edgar_8k_items as E8K                       # noqa: E402
from scripts import scenario_bridge as SB                       # noqa: E402
from scripts import scenario_bridge_grade as SBG                # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "labor_day_lab_2026-09-07"
RECEIPT = OUT_DIR / "B3_bridge_coverage.json"
REGRADE_RECEIPT = OUT_DIR / "B3_bridge_coverage_regrade.json"
CONTROL_RECEIPT = OUT_DIR / "B3_bridge_coverage_control.json"

#: The 20260904 rerun receipt this one is measured against.
PRIOR_RECEIPT = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
                 / "scenario_bridge_rerun_20260904.json")

PANEL_YEARS = (2013, 2024)


def _stamp(paths: dict[str, Path]) -> list[dict]:
    out = []
    for why, p in paths.items():
        try:
            st = p.stat()
            out.append({"path": str(p), "bytes": st.st_size,
                        "mtime_utc": datetime.fromtimestamp(
                            st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                        "why": why})
        except OSError:
            out.append({"path": str(p), "bytes": None, "mtime_utc": None,
                        "why": why + " — ABSENT"})
    return out


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                              capture_output=True, text=True,
                              timeout=20).stdout.strip() or None
    except Exception:                                           # noqa: BLE001
        return None


# ─────────────────────────────────────────────── what the new tapes actually are


def companyworld_status(panel_permnos: set[int]) -> dict:
    """MEASURED, never assumed: what the relation tape covers and whether any of
    it falls inside the panel window."""
    p = CW.OUT_PARQUET
    if not p.exists():
        return {"exists": False, "why": f"{p} absent"}
    d = pd.read_parquet(p)
    fd = pd.to_datetime(d["filing_date"])
    lo, hi = pd.Timestamp(f"{PANEL_YEARS[0]}-01-01"), pd.Timestamp(f"{PANEL_YEARS[1]}-12-31")
    in_window = int(((fd >= lo) & (fd <= hi)).sum())
    permnos = set(pd.concat([d["subject_permno"], d["counterparty_permno"]])
                  .astype("int64").unique().tolist())
    return {
        "exists": True, "path": str(p), "rows": int(len(d)),
        "filing_date_min": str(fd.min().date()),
        "filing_date_max": str(fd.max().date()),
        "types": {str(k): int(v) for k, v in d["type"].value_counts().items()},
        "directions": {str(k): int(v) for k, v in d["direction"].value_counts().items()},
        "graph_layers": {str(k): int(v) for k, v in d["graph_layer"].value_counts().items()},
        "quote_verified_rate": round(float(d["quote_verified"].mean()), 4),
        "distinct_permnos": len(permnos),
        "named_counterparties": int(d["counterparty_name"].nunique()),
        "permnos_also_in_panel": len(permnos & panel_permnos),
        "edges_inside_panel_window": in_window,
        "panel_window": f"{PANEL_YEARS[0]}-01-01..{PANEL_YEARS[1]}-12-31",
        "reads_as": (
            "the relation tape is REAL, typed, quote-verified and permno-resolved "
            f"— and {in_window} of its {len(d)} edges fall inside the panel "
            "window. Ownership of a concept is not coverage of a panel."),
    }


def cik_link_status(panel_permnos: set[int]) -> dict:
    """How many panel permnos reach a CIK — through TODAY's ticker map (what the
    20260904 rerun measured) versus through the HISTORICAL name-window bridge
    that `cik_lookup.parquet` makes possible."""
    out: dict = {"panel_permnos": len(panel_permnos)}

    # (a) the 20260904 route: permno -> last CRSP ticker -> current CIK
    try:
        px = pd.read_parquet(E8K.CRSP_PIT_MONTHLY,
                             columns=["permno", "date", "ticker"])
        px = px[px["permno"].isin(panel_permnos) & px["ticker"].notna()]
        last = px.sort_values("date").groupby("permno")["ticker"].last()
        t2c = {str(v["ticker"]).upper(): int(v["cik_str"]) for v in
               json.loads(E8K.TICKER_CIK_CACHE.read_text(encoding="utf-8")).values()}
        n_today = int(sum(1 for t in last.values if str(t).upper() in t2c))
        out["today_ticker_map"] = {
            "with_crsp_ticker": int(len(last)),
            "resolving_to_current_cik": n_today,
            "rate": round(n_today / max(len(panel_permnos), 1), 4),
            "route": "permno -> last CRSP ticker -> company_tickers.json (CURRENT "
                     "registrants only; delisted names cannot resolve)",
        }
        del px, last
    except Exception as e:                                      # noqa: BLE001
        out["today_ticker_map"] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}

    # (b) the historical route the cik_lookup file makes possible
    try:
        w = CW.cik_permno_windows()
        hist = set(w["permno"].astype("int64").unique().tolist())
        n_hist = len(panel_permnos & hist)
        out["historical_name_window_bridge"] = {
            "bridge_rows": int(len(w)),
            "distinct_permnos_in_bridge": len(hist),
            "panel_permnos_resolving": n_hist,
            "rate": round(n_hist / max(len(panel_permnos), 1), 4),
            "route": "CRSP stocknames (comnam, namedt..nameenddt) -> normalised "
                     "name_key -> EDGAR cik_lookup -> cik. Rename-proof and "
                     "survivorship-neutral, per companyworld_extract."
                     "cik_permno_windows",
            "source": str(CW.CIKLOOKUP),
        }
        del w, hist
    except Exception as e:                                      # noqa: BLE001
        out["historical_name_window_bridge"] = {
            "error": f"{type(e).__name__}: {str(e)[:200]}"}

    a = (out.get("today_ticker_map") or {}).get("rate")
    b = (out.get("historical_name_window_bridge") or {}).get("rate")
    out["delta"] = (round(b - a, 4) if isinstance(a, float) and isinstance(b, float)
                    else None)
    out["reads_as"] = (
        "the CIK link is the gate between 'we own an 8-K tape' and 'event_type "
        "can filter the panel'. The 20260904 receipt measured the survivor-tilted "
        "route; this measures the historical one. A higher rate here is the "
        "distance that actually closed."
        if out["delta"] is not None else
        "one of the two routes could not be measured; the delta is CANNOT "
        "DETERMINE rather than zero.")
    return out


# ───────────────────────────────────────────────────────── the two field maps


def field_maps(cw: dict) -> dict:
    """The current map, and the two v2 candidates, with the EVIDENCE for every
    upgrade attached to the field it upgrades."""
    current = SB.field_map_current()          # = FIELD_MAP_DOC + event_type PROXY

    owns_relations = bool(cw.get("exists") and cw.get("rows"))
    overlaps_panel = bool(cw.get("edges_inside_panel_window", 0) > 0)

    ownership = {k: dict(v) for k, v in current.items()}
    if owns_relations:
        ownership["company_role"] = {
            "grade": "PROXY",
            "panel": (f"graph/companyworld_v1.parquet ({cw['rows']} typed edges, "
                      f"{cw['distinct_permnos']} permnos, "
                      f"{cw['filing_date_min']}..{cw['filing_date_max']})"),
            "note": ("supplier / customer / competitor is exactly what this tape "
                     "stores, quote-verified and permno-resolved. PROXY, never "
                     "DIRECT: an extracted filing sentence is a claim about a "
                     "relationship, not a measured revenue share. NOT a retrieval "
                     "predicate: the tape ends 2011-03-03 and has ZERO edges "
                     "inside the 2013-2024 panel window."),
        }
        ownership["actors"] = {
            "grade": "PROXY",
            "panel": (f"companyworld_v1.counterparty_name "
                      f"({cw['named_counterparties']} named entities, each "
                      "resolved to a permno)"),
            "note": ("the 20260903 map said 'no entity graph links a named actor "
                     "to a permno'; this one does. It links COMPANIES, not people "
                     "or regulators, so a scenario naming a regulator or an "
                     "activist still maps to nothing. Same date problem as "
                     "company_role."),
        }

    panel_joined = {k: dict(v) for k, v in current.items()}
    if not overlaps_panel:
        # Nothing to add: company_role and actors stay exactly as FIELD_MAP_DOC
        # left them, and the note says why rather than leaving the reader to
        # infer that the tape was not found.
        for f in ("company_role", "actors"):
            panel_joined[f] = dict(panel_joined[f])
            panel_joined[f]["note"] += (
                " | 2026-09-07: companyworld_v1 OWNS this concept "
                f"({cw.get('rows')} edges) but {cw.get('edges_inside_panel_window')} "
                "of them fall inside 2013-2024, so under a panel-overlap standard "
                "the field is still unmappable HERE.")
    return {"current_20260904": current,
            "v2_ownership_standard": ownership,
            "v2_panel_overlap_standard": panel_joined}


def movement_table(before: dict, after: dict) -> list[dict]:
    rows = []
    for f in SB.RETRIEVAL_FIELDS:
        b, a = before[f]["grade"], after[f]["grade"]
        rows.append({"field": f, "before": b, "after": a,
                     "moved": bool(b != a),
                     "movement": (f"{b} -> {a}" if b != a else "unchanged"),
                     "panel_after": after[f]["panel"]})
    return rows


# ────────────────────────────────────────────────────────────────── the run


def run(regrade: bool = True) -> dict:
    inputs = _stamp({
        "the 2013-2024 training panel (permno universe)": SB.TRAIN_TABLE,
        "SEC 8-K item tape": SB.EIGHTK_PARQUET,
        "SEC 8-K manifest": SB.EIGHTK_MANIFEST,
        "current ticker -> CIK map": E8K.TICKER_CIK_CACHE,
        "companyworld_v1 relation edges": CW.OUT_PARQUET,
        "EDGAR name -> CIK lookup": CW.CIKLOOKUP,
        "CRSP stocknames (name windows)": CW.STOCKNAMES,
        "CRSP PIT monthly (permno -> ticker/comnam)": E8K.CRSP_PIT_MONTHLY,
        "the 20260904 rerun receipt this is measured against": PRIOR_RECEIPT,
    })

    panel_permnos = set(
        pd.read_parquet(SB.TRAIN_TABLE, columns=["permno"])["permno"]
        .astype("int64").unique().tolist())

    eightk = SB.eightk_tape_status()
    cw = companyworld_status(panel_permnos)
    cik = cik_link_status(panel_permnos)
    fms = field_maps(cw)

    base = SB.mappability_summary(SB.FIELD_MAP_DOC)
    cur = SB.mappability_summary(fms["current_20260904"])
    own = SB.mappability_summary(fms["v2_ownership_standard"])
    pjn = SB.mappability_summary(fms["v2_panel_overlap_standard"])

    def _mtn(s):
        return round(s["unmappable"] / s["retrieval_fields"], 4)

    coverage = {
        "retrieval_fields": base["retrieval_fields"],
        "maps_to_nothing": {
            "20260903_baseline": _mtn(base),
            "20260904_after_8K": _mtn(cur),
            "20260907_v2_ownership_standard": _mtn(own),
            "20260907_v2_panel_overlap_standard": _mtn(pjn),
        },
        "summaries": {"20260903_baseline": base, "20260904_after_8K": cur,
                      "v2_ownership": own, "v2_panel_overlap": pjn},
        "movement_since_20260904": {
            "ownership_standard": movement_table(fms["current_20260904"],
                                                 fms["v2_ownership_standard"]),
            "panel_overlap_standard": movement_table(
                fms["current_20260904"], fms["v2_panel_overlap_standard"]),
        },
        "headline": (
            f"maps-to-nothing {_mtn(cur):.1%} -> {_mtn(own):.1%} under the "
            f"OWNERSHIP standard the 20260904 receipt used, and "
            f"{_mtn(pjn):.1%} (UNCHANGED) under a panel-overlap standard. The "
            "gap is the whole finding: companyworld_v1 gives us the concept and "
            "not the dates."),
    }

    receipt = {
        "item": "LABOR_DAY_LAB_2026-09-07 / lane B / B3",
        "title": "scenario bridge v2 field coverage",
        "licence": "PRODUCT_EXPERIMENT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "argv": list(sys.argv), "git_commit": _git_commit(),
        "python": sys.version.split()[0],
        "config": {"panel_years": list(PANEL_YEARS), "k": 20,
                   "with_holders": True, "regrade": regrade,
                   "scenarios": "the SAME 20, not regenerated"},
        "inputs_opened": inputs,
        "llm_spend": {"n_calls": 0, "usd": 0.0,
                      "note": "nothing is regenerated; code re-grades code"},
        "no_2010_2013_edgar_era": (
            "the 8-K tape's first filing_date is "
            f"{eightk.get('filing_date_min')} — there is NO 2010-2013 EDGAR era "
            "on disk and none is claimed."),
        "tapes": {"edgar_8k": eightk, "companyworld_v1": cw},
        "cik_link": cik,
        "coverage": coverage,
        "field_maps": fms,
    }

    if regrade:
        prior = (json.loads(PRIOR_RECEIPT.read_text(encoding="utf-8"))
                 if PRIOR_RECEIPT.exists() else None)
        # THE CONTROL RUNS FIRST, AND IT IS WHAT MAKES THE CLAIM CHECKABLE.
        #
        # The first draft of this item compared the v2 re-grade straight against
        # the 20260904 receipt, got 18 of 20 scenarios moved, and printed
        # "GRADES MOVED - investigate". The field map was innocent: the TRAIN
        # TABLE was rebuilt on 2026-09-04 23:51 (441,278 -> 441,797 rows, 5,713
        # -> 5,721 names, plus a sector-taxonomy fix that stopped folding
        # "Public Administration" into the unclassified bucket). A receipt
        # comparison that crosses a panel rebuild reads exactly like a code
        # change and is not one.
        #
        # So the same 20 scenarios are graded TWICE on TODAY's panel: once with
        # the 20260904 field map (the control) and once with v2. v2 minus
        # control isolates the FIELD MAP and must be exactly zero; control minus
        # the old receipt isolates the PANEL and is a reproducibility
        # measurement, not a bug.
        control = SBG.run(k=20, with_holders=True,
                          receipt_path=CONTROL_RECEIPT,
                          field_map=fms["current_20260904"],
                          run_tag="20260907_labor_b3_control",
                          extra={"labor_b3": {
                              "role": ("CONTROL - the 20260904 field map on "
                                       "TODAY's panel, so a panel rebuild "
                                       "cannot be mistaken for a field-map "
                                       "effect")}})
        new_rec = SBG.run(k=20, with_holders=True,
                          receipt_path=REGRADE_RECEIPT,
                          field_map=fms["v2_ownership_standard"],
                          run_tag="20260907_labor_b3",
                          extra={"labor_b3": {
                              "what_changed": ("field map only: company_role "
                                               "and actors graded PROXY on the "
                                               "ownership standard. Retrieval "
                                               "and grading code UNCHANGED; "
                                               "none of these fields is a "
                                               "predicate."),
                              "expected_grade_changes": 0}})
        receipt["regrade"] = {
            "v2_vs_control_SAME_PANEL": compare_grades(
                control, new_rec,
                label="field map only (v2 vs the 20260904 map, both on today's "
                      "panel)", expect_zero=True),
            "control_vs_20260904_receipt": compare_grades(
                prior, control,
                label="panel only (the 20260904 map, then vs now)",
                expect_zero=False),
            "panel_provenance_diff": panel_diff(prior, control),
            "receipt_paths": {"v2": str(REGRADE_RECEIPT),
                              "control": str(CONTROL_RECEIPT)},
            "how_to_read": (
                "the FIRST comparison is the claim - the field map changes no "
                "grade, because none of the upgraded fields is a retrieval "
                "predicate. The SECOND is a reproducibility measurement: it is "
                "what a panel rebuild does to a sealed receipt."),
        }
    else:
        receipt["regrade"] = {"skipped": True,
                              "why": "--no-regrade; the coverage table does not "
                                     "depend on it, but the 'grades unchanged' "
                                     "claim is then UNVERIFIED"}
    return receipt


def panel_diff(a: dict | None, b: dict | None) -> dict:
    """What changed about the PANEL between two receipts. Without this, a
    comparison across a rebuild is unattributable and reads as a code change."""
    pa = (a or {}).get("panel_provenance") or {}
    pb = (b or {}).get("panel_provenance") or {}
    keys = sorted(set(pa) | set(pb))
    diffs = {k: {"before": pa.get(k), "after": pb.get(k)}
             for k in keys if pa.get(k) != pb.get(k)}
    return {"identical": not diffs, "n_fields_differing": len(diffs),
            "diffs": diffs,
            "reads_as": ("the panel is the same object in both receipts"
                         if not diffs else
                         "the panel was REBUILT between the two receipts; a "
                         "grade difference across this boundary cannot be "
                         "attributed to a code change")}


def compare_grades(prior: dict | None, new: dict, label: str = "",
                   expect_zero: bool = True) -> dict:
    def _by_id(rec):
        out = {}
        for r in (rec or {}).get("scenarios", []):
            h = str(r.get("expected_horizon_months"))
            hh = ((r.get("grade") or {}).get("horizons") or {}).get(h) or {}
            out[r["scenario_id"]] = {
                "status": (r.get("grade") or {}).get("status"),
                "horizon": h,
                "spread_net": hh.get("spread_net"),
                "t_paired_by_month": hh.get("t_paired_by_month"),
            }
        return out

    if prior is None:
        return {"compared": False, "label": label,
                "why": "no prior receipt - nothing to compare against"}
    o, n = _by_id(prior), _by_id(new)
    rows, changed = [], []
    for sid in sorted(set(o) | set(n)):
        row = {"scenario_id": sid, "old": o.get(sid), "new": n.get(sid),
               "changed": o.get(sid) != n.get(sid)}
        rows.append(row)
        if row["changed"]:
            changed.append(sid)
    if expect_zero:
        verdict = ("GRADES UNCHANGED - as constructed" if not changed
                   else "GRADES MOVED - the field map touched a grade it "
                        "cannot touch; this is a bug report")
        expected = ("zero: none of the upgraded fields is a retrieval "
                    "predicate, so the analogue sets are identical by "
                    "construction")
    else:
        verdict = ("IDENTICAL ACROSS THE REBUILD" if not changed
                   else f"{len(changed)} of {len(rows)} scenarios moved - "
                        "attributable to the panel, see panel_provenance_diff")
        expected = ("not zero, and not a bug: this comparison crosses a panel "
                    "rebuild and measures its effect")
    return {"compared": True, "label": label,
            "n_scenarios": len(rows), "n_changed": len(changed),
            "changed_ids": changed, "expected": expected,
            "VERDICT": verdict, "rows": rows}


def write_receipt(receipt: dict, path: Path = RECEIPT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="labor_b3_bridge_coverage")
    ap.add_argument("--no-regrade", action="store_true",
                    help="skip the 20-scenario re-grade (coverage table only)")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                       # noqa: BLE001
            pass
    try:
        rec = run(regrade=not a.no_regrade)
    except BaseException as e:                                  # noqa: BLE001
        import traceback
        write_receipt({"item": "LABOR_DAY_LAB_2026-09-07 / lane B / B3",
                       "status": "FAILED",
                       "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                       "argv": list(sys.argv), "git_commit": _git_commit(),
                       "error": f"{type(e).__name__}: {e}",
                       "traceback": traceback.format_exc(),
                       "note": "a traceback is a receipt"})
        print("FAILED — receipt written")
        raise
    write_receipt(rec)
    c = rec["coverage"]["maps_to_nothing"]
    print("\nMAPS-TO-NOTHING")
    for k, v in c.items():
        print(f"  {k:42s} {v:.1%}")
    for name, tbl in rec["coverage"]["movement_since_20260904"].items():
        moved = [r for r in tbl if r["moved"]]
        print(f"  [{name}] moved: "
              + (", ".join(f"{r['field']} {r['movement']}" for r in moved)
                 if moved else "nothing"))
    rg = rec["regrade"]
    if rg.get("skipped"):
        print(f"REGRADE: skipped - {rg['why']}")
    else:
        print(f"FIELD MAP  : {rg['v2_vs_control_SAME_PANEL']['VERDICT']}")
        print(f"PANEL      : {rg['control_vs_20260904_receipt']['VERDICT']}")
        print(f"PANEL DIFF : {rg['panel_provenance_diff']['n_fields_differing']}"
              " provenance fields differ")
    print(f"[receipt] -> {RECEIPT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
