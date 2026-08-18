"""Run the IIF-1 grader. Three modes, and only one of them reads an outcome.

    # what the campaign can detect. Consumes NO outcome, needs no licence.
    python -m scripts.iif1_grade --power

    # the whole pipeline on synthetic outcomes, so 08-21 flows straight through
    python -m scripts.iif1_grade --synthetic

    # the real read. Refused unless the read gate licenses a look.
    python -m scripts.iif1_grade --grade

WHY `--power` IS THE DEFAULT THING TO RUN TODAY
===============================================
§64: a power check that consumes no outcome is FREE and therefore OBLIGATORY
before any confirmation. A candidate has to clear the confirmation window's MDE,
recorded at reservation time; below it the test returns "not established"
whatever the world does, and the window is gone with nothing learned.

For IIF-1 that check is available the moment the forecasts are minted, because
the only two inputs are the arms' forecast DISAGREEMENT — which is in the ledger
— and a base rate from history. If the arms barely disagree, forty nights buys
nothing and it is knowable today for $0.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services import investigator_night as N
from backend.services import iif1_grader as G


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                          # noqa: BLE001
            pass


def _print_brier(tag: str, b: dict) -> None:
    """The base rate is on the SAME LINE as the Brier. Deliberately."""
    print(f"    {tag:<14s} Brier {b['brier']:.5f}   base rate "
          f"{b['base_rate']:.4f}   n={b['n']}")
    print(f"    {'':<14s}   reliability {b['reliability']:.5f}  "
          f"resolution {b['resolution']:.5f}  uncertainty {b['uncertainty']:.5f}")
    if b["brier_skill_score"] is not None:
        print(f"    {'':<14s}   BSS {b['brier_skill_score']:+.4f} vs "
              f"climatology {b['climatology']:.4f}")
    else:
        print(f"    {'':<14s}   BSS  —  {b['bss_reference']}")
    if b["resolution"] < 1e-6:
        print(f"    {'':<14s}   *** RESOLUTION ~ 0: this forecaster did not "
              f"separate high-risk from low-risk cases. A low Brier here is "
              f"the base rate wearing a model.")


def _print_licence(lic: dict) -> None:
    print(f"  read licence  {lic.get('disposition')}  "
          f"(n_graded_nights={lic.get('n_graded_nights')}, "
          f"{lic.get('n_graded_nights_basis', 'basis not stated')})")
    for line in _wrap(str(lic.get("reason", "")), 68):
        print(f"      {line}")


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def _load_base_rates(a) -> dict:
    """Measured climatologies, keyed by registered cell. Never a default.

    Read from the files `climatological_base_rate` wrote. A `--base-rate` flag
    that applied one number to every cell would pool two thresholds whose
    measured rates differ by a factor of two.
    """
    out = {}
    for p in sorted(Path(a.climatology_dir).glob("iif1_climatology_*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        out[(G.FROZEN_LOSS_OBSERVABLE, int(c["horizon_days"]),
             float(c["threshold"]))] = float(c["base_rate"])
    return out


def cmd_power(a) -> int:
    rates = _load_base_rates(a)
    if not rates:
        print(f"no measured climatology files in {a.climatology_dir}. Measure "
              f"them first — a base rate is not something to assert.")
        return 2
    rep = G.power_report(ledger=a.ledger, base_rates=rates,
                         n_nights_target=a.nights,
                         outcome_correlation=a.rho)
    print("=" * 74)
    print("IIF-1 FORWARD POWER — §64, and it consumed NO outcome")
    print("=" * 74)
    _print_licence(rep["read_licence"])
    print()
    p = rep["pairing"]
    print(f"  pairing       {p['n_cells_paired']} paired / {p['n_cells_union']} "
          f"union  ({p['n_cells_dropped_unpaired']} dropped unpaired)")
    print(f"  key           {' x '.join(p['pairing_key'])}")
    for arm, d in p["per_arm"].items():
        if d["n_missing_from_arm"]:
            print(f"    {arm:<14s} missing {d['n_missing_from_arm']} cell(s) "
                  f"— a failure mode available only to some arms is a BIAS "
                  f"WITH A DIRECTION, toward the null")
    print(f"  versions      {rep['records_by_implementation_version']}")
    if G.UNSTAMPED_VERSION in rep["records_by_implementation_version"]:
        print(f"    *** {G.UNSTAMPED_VERSION}: that night's receipt carries no "
              f"implementation_version. The within-version contrast has a hole "
              f"exactly at the boundary the field exists to mark.")
    print()
    print(f"  contrast      {G.PRIMARY_TREATMENT} - {G.PRIMARY_CONTROL}")
    print("  PER REGISTERED CELL — the thresholds have different base rates, "
          "and one\n  pooled MDE across them would be arithmetic against the "
          "wrong world.")
    for cell, m in rep["forward_mde_by_cell"].items():
        print(f"\n  ── {cell} ──")
        print(f"    base rate     {m['base_rate']:.4f}   (MEASURED climatology)")
        print(f"    RMS |f_t-f_c| {m['rms_forecast_difference']:.5f}   "
              f"the arms' disagreement — the ONLY thing that makes")
        print(f"    {'':<14s}  the contrast detectable at any n")
        print(f"    cells/night   {m['cells_per_night']}   over "
              f"{m['n_nights_observed']} completed night(s)")
        print(f"    SD per night  {m['sd_per_night']:.6f}")
        print(f"    MDE @ {m['n_nights_target']} nights  {m['mde']:.6f}   "
              f"[{m['basis']}]")
        for line in _wrap(m["outcome_correlation_note"], 64):
            print(f"        {line}")
    print()
    print("  READ THIS AS A FLOOR. The number to compare it against is the "
          "smallest\n  paired Brier difference that would matter — declare "
          "that before the read,\n  not after seeing this.")
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=2, default=str),
                                encoding="utf-8")
        print(f"\n  json -> {a.json}")
    return 0


def cmd_synthetic(a) -> int:
    """Prove the pipeline end to end without touching a campaign record."""
    import random

    rng = random.Random(a.seed)
    intervals = G.night_intervals()
    if not intervals:
        print("no night receipts found — the synthetic path still needs real "
              "night intervals to attribute its records to.")
        return 1
    recs = []
    for iv in intervals:
        made = iv["finished_utc"].isoformat()
        for i in range(a.cells):
            y = 1 if rng.random() < a.synthetic_base_rate else 0
            base = 0.2 + 0.4 * rng.random()
            for arm in N.ARMS:
                p = base
                if arm == G.PRIMARY_TREATMENT:
                    p = min(0.98, max(0.02, base + a.edge * (1 if y else -1)))
                recs.append({
                    "prediction_id": f"syn-{iv['night']}-{arm}-{i}",
                    "arm": arm, "ticker": f"SYN{i}",
                    "observable": G.FROZEN_LOSS_OBSERVABLE,
                    "horizon_days": 5, "threshold": 0.05,
                    "probability": round(p, 4), "outcome": y,
                    "made_at": made, "evidence_population": "synthetic"})
    recs = G.attach_night(recs)
    rep = G.grade_synthetic(recs, climatology=a.synthetic_base_rate)
    _print_grade(rep, title="IIF-1 GRADER — SYNTHETIC OUTCOMES (no campaign "
                            "record was read)")
    print(f"\n  edge injected into {G.PRIMARY_TREATMENT}: {a.edge:+.2f}  "
          f"(so a NEGATIVE mean_diff is the correct answer)")
    return 0


def cmd_grade(a) -> int:
    rep = G.grade_report(ledger=a.ledger, climatology=a.climatology)
    _print_grade(rep, title="IIF-1 GRADER — LICENSED READ")
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=2, default=str),
                                encoding="utf-8")
        print(f"\n  json -> {a.json}")
    return 0


def _print_grade(rep: dict, *, title: str) -> None:
    print("=" * 74)
    print(title)
    print("=" * 74)
    _print_licence(rep["read_licence"])
    print(f"  frozen loss   {rep['frozen_loss']}")
    p = rep["pairing"]
    print(f"  pairing       {p['n_cells_paired']} paired / {p['n_cells_union']} "
          f"union  ({p['n_cells_dropped_unpaired']} dropped unpaired)")
    print()
    for scope, c in [("POOLED", rep["pooled"])] + [
            (f"VERSION {v}", d) for v, d in
            sorted(rep["by_implementation_version"].items())]:
        print(f"  ── {scope} ──")
        if "refused" in c:
            for line in _wrap(c["refused"], 66):
                print(f"    {line}")
            print()
            continue
        print(f"    {c['direction']}")
        print(f"    nights {c['n_nights']}   paired cells {c['n_paired_cells']}")
        print(f"    mean paired diff  {c['mean_diff']:+.6f}")
        print(f"    SE  iid {c['se_iid']}  HAC {c['se_hac']}  "
              f"used {c['se_used']}")
        print(f"    t   {c['t_stat']}")
        if c["t_stat"] is None:
            for line in _wrap(c["t_stat_note"], 66):
                print(f"      {line}")
        _print_brier(c["treatment"], c[c["treatment"]])
        _print_brier(c["control"], c[c["control"]])
        print()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="iif1_grade")
    ap.add_argument("--power", action="store_true",
                    help="§64 forward MDE from forecasts alone; no outcomes")
    ap.add_argument("--synthetic", action="store_true",
                    help="run the whole pipeline on synthetic outcomes")
    ap.add_argument("--grade", action="store_true",
                    help="the real read; refused unless licensed")
    ap.add_argument("--ledger",
                    default=str(_config.OPTIMUS_LEDGER_DIR / "predictions.jsonl"))
    ap.add_argument("--climatology-dir",
                    default=str(_config.OPTIMUS_LEDGER_DIR),
                    help="where the measured iif1_climatology_*.json files "
                         "live. There is deliberately no --base-rate flag: one "
                         "number applied to every cell would pool two "
                         "thresholds whose measured rates differ two-fold.")
    ap.add_argument("--climatology", type=float, default=None,
                    help="PIT climatology for the Brier skill score")
    ap.add_argument("--nights", type=int,
                    default=N.GRADED_NIGHTS_TO_FIRST_LOOK)
    ap.add_argument("--rho", type=float, default=0.0,
                    help="DECLARED intra-night outcome correlation; 0 is a "
                         "floor, not an estimate")
    ap.add_argument("--synthetic-base-rate", type=float, default=0.30,
                    help="outcome frequency for the SYNTHETIC path only")
    ap.add_argument("--cells", type=int, default=40)
    ap.add_argument("--edge", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    _utf8()

    if sum(bool(x) for x in (a.power, a.synthetic, a.grade)) != 1:
        ap.error("choose exactly one of --power / --synthetic / --grade")

    try:
        if a.power:
            return cmd_power(a)
        if a.synthetic:
            return cmd_synthetic(a)
        return cmd_grade(a)
    except G.GradeRefused as e:
        # A REFUSAL IS THE PRODUCT. It exits nonzero so a caller cannot mistake
        # it for a result, and it prints in full rather than as a traceback,
        # because the reason is the thing worth reading.
        print("\n" + "=" * 74)
        print("REFUSED")
        print("=" * 74)
        for line in _wrap(str(e), 70):
            print(f"  {line}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
