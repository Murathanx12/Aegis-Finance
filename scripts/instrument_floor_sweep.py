"""INSTRUMENT-FLOOR-SWEEP-1 — run the whole shelf against synthetic truth.

    python -m scripts.instrument_floor_sweep                 # full sweep
    python -m scripts.instrument_floor_sweep --sims 40       # quick
    python -m scripts.instrument_floor_sweep --only roll_spread,agk_edge_spread

Writes `docs/INSTRUMENT_FLOORS.md` and `backend/data/optimus/instrument_floors.json`.

WHY THIS SCRIPT EXISTS (Order 18 §2)
=====================================
Track R found AGK's detection floor by handing it a tape whose true spread was
zero. The method is not AGK-specific, and until now no instrument on this shelf
had ever been asked what it reads when there is nothing to read. Each one feeds
a gate, a score or a report, and each one returns a confident number on empty
data.

This is NEGATIVE_RESULTS #34 — "calibrate gates before trusting their kills" —
turned from a lesson we relearn one instrument at a time into a procedure that
runs over all of them at once, for the cost of CPU and no calendar.

WHAT THE OUTPUT IS AND IS NOT
------------------------------
Every floor here is measured against a DECLARED synthetic microstructure that is
kinder than the market in every direction it simplifies (no volume clustering,
no overnight gaps, no time-varying spreads, no informed flow). So each number is
a LOWER BOUND on the real floor. The existence of a floor and the direction it
scales are robust; the magnitude is simulation-dependent, and the table says so
in its own header rather than in a footnote somebody skims.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import instrument_floor as IF   # noqa: E402

OUT_JSON = REPO / "backend" / "data" / "optimus" / "instrument_floors.json"
OUT_DOC = REPO / "docs" / "INSTRUMENT_FLOORS.md"


def _fmt(x, nd=4):
    if x is None:
        return "—"
    if isinstance(x, float):
        if x != 0 and (abs(x) < 1e-3 or abs(x) >= 1e5):
            return f"{x:.2e}"
        return f"{x:.{nd}g}"
    return str(x)


def _verdict(prof: IF.FloorProfile) -> str:
    """One line a reader can act on, derived from the profile, never declared."""
    if prof.smallest_resolvable_truth is None:
        return "BLIND on the declared ladder"
    bias = prof.bias_at_smallest_resolvable
    if prof.null_median > 0 and prof.smallest_resolvable_truth is not None:
        # A null reading that is large in the instrument's own units means the
        # LEVEL is uninterpretable even where changes resolve.
        pass
    if bias is not None and (bias > 1.5 or bias < 0.67):
        return (f"resolves from {_fmt(prof.smallest_resolvable_truth)}, but "
                f"reads {bias:.2f}x truth there")
    return f"resolves from {_fmt(prof.smallest_resolvable_truth)}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=IF.DEFAULT_SIMS)
    ap.add_argument("--only", type=str, default="",
                    help="comma-separated instrument names")
    ap.add_argument("--no-stability", action="store_true")
    ap.add_argument("--seed", type=int, default=IF.DEFAULT_SEED)
    ap.add_argument("--render-only", action="store_true",
                    help="re-render the doc from the last JSON without "
                         "re-measuring; the numbers are the sweep's, not this "
                         "run's, and the JSON's own timestamps say so")
    a = ap.parse_args()

    if a.render_only:
        if not OUT_JSON.exists():
            print(f"no {OUT_JSON} to render from")
            return 2
        payload = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        OUT_DOC.write_text(_render(payload), encoding="utf-8")
        print(f"re-rendered {OUT_DOC.relative_to(REPO)} from stored results")
        return 0

    names = ([s.strip() for s in a.only.split(",") if s.strip()]
             or list(IF.INSTRUMENTS))
    unknown = [n for n in names if n not in IF.INSTRUMENTS]
    if unknown:
        print(f"unknown instrument(s): {unknown}; have {sorted(IF.INSTRUMENTS)}")
        return 2

    profiles, rows = {}, []
    t0 = time.time()
    for name in names:
        inst = IF.INSTRUMENTS[name]
        t = time.time()
        try:
            prof = IF.profile_instrument(
                inst, sims=a.sims, seed=a.seed,
                measure_stability=not a.no_stability)
        except IF.InstrumentUnresolvable as e:
            # A refusal is a finding, and it is NAMED rather than dropped: an
            # instrument missing from the table would read as one that passed.
            print(f"  {name:24s} REFUSED: {e}")
            rows.append({"instrument": name, "refused": str(e)})
            continue
        row = prof.to_row()
        row["verdict"] = _verdict(prof)
        row["ladder"] = prof.ladder
        row["bias_comparable"] = inst.bias_comparable
        rows.append(row)
        profiles[name] = prof
        print(f"  {name:24s} floor={_fmt(prof.detection_floor)} "
              f"{inst.units:24s} {row['verdict']}  [{time.time() - t:.1f}s]")

    payload = {
        "trial": "INSTRUMENT-FLOOR-SWEEP-1",
        "generated_by": "scripts/instrument_floor_sweep.py",
        "sims": a.sims, "seed": a.seed,
        "null_quantile": IF.DEFAULT_NULL_QUANTILE,
        "stability_tolerance": IF.DEFAULT_STABILITY_TOLERANCE,
        "elapsed_sec": round(time.time() - t0, 1),
        "basis": ("every floor measured on a DECLARED synthetic microstructure "
                  "that is kinder than the market in every direction it "
                  "simplifies; each floor is therefore a LOWER BOUND"),
        "instruments": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    OUT_DOC.write_text(_render(payload), encoding="utf-8")
    print(f"\nwrote {OUT_JSON.relative_to(REPO)}")
    print(f"wrote {OUT_DOC.relative_to(REPO)}  ({time.time() - t0:.0f}s)")
    return 0


def _cell(x) -> str:
    """Markdown table cells cannot contain a raw pipe.

    Found by the Amihud row: its units are `|r|/$vol`, whose pipes split the
    cell and shifted every column after it. A table that silently mis-renders
    is worse than one that fails — a reader takes the shifted number as the
    answer to the question in the shifted header.
    """
    return str(x).replace("|", "\\|")


def _findings(p: dict) -> str:
    """The three things a reader should take away, DERIVED from the sweep.

    Written by the script rather than by hand, so it cannot drift from the
    numbers underneath it the way a summary paragraph does.
    """
    rows = [r for r in p["instruments"] if "refused" not in r]
    by_name = {r["instrument"]: r for r in rows}
    L = ["## What this sweep found", ""]

    spreads = [r for r in rows if r["units"].startswith("bps")]
    if spreads:
        ranked = sorted(spreads, key=lambda r: r["detection_floor"])
        best, worst = ranked[0], ranked[-1]
        L += [
            f"**1. The spread estimators differ by "
            f"{worst['detection_floor'] / max(best['detection_floor'], 1e-9):.0f}x "
            f"in what they can see.** "
            f"`{best['instrument']}` floors at "
            f"{best['detection_floor']:.0f}bp; `{worst['instrument']}` at "
            f"{worst['detection_floor']:.0f}bp and cannot resolve anything "
            f"below {_fmt(worst['smallest_resolvable_truth'])}bp. Every one of "
            f"these is used somewhere as \"the spread\". The AGK supersession "
            f"is now MEASURED rather than cited: "
            + ", ".join(f"`{r['instrument']}` {r['detection_floor']:.0f}bp"
                        for r in ranked) + ".",
            "",
        ]

    ar = by_name.get("absorption_ratio")
    if ar:
        L += [
            f"**2. The absorption ratio reads "
            f"{ar['null_median']:.2f} on completely INDEPENDENT assets.** "
            f"Its null is not zero — it is k/n plus sampling bias — so the "
            f"LEVEL carries no information about coupling, and a report saying "
            f"\"absorption {ar['null_median']:.2f}, markets tightly coupled\" is "
            f"reading noise. Its *changes* do resolve (from a "
            f"{_fmt(ar['smallest_resolvable_truth'])} factor share), so the "
            f"usable statistic is the movement, never the level.",
            "",
        ]

    control = by_name.get("realized_vol")
    if control:
        L += [
            f"**3. Not every instrument has a problem.** `realized_vol` reads "
            f"{control['null_median']:.4f} against a null of "
            f"{control['null_truth']} with a floor of "
            f"{control['detection_floor']:.4f} — essentially no gap. It is in "
            f"the table as the control: without one, a sweep that finds a "
            f"floor everywhere is indistinguishable from a sweep whose harness "
            f"manufactures floors.",
            "",
        ]
    return "\n".join(L)


def _render(p: dict) -> str:
    L = []
    A = L.append
    A("# INSTRUMENT FLOORS — what each estimator can and cannot see")
    A("")
    A(f"`INSTRUMENT-FLOOR-SWEEP-1` · {p['sims']} simulations per point · "
      f"null band at the {p['null_quantile']:.0%} quantile · seed {p['seed']}")
    A("")
    A("Generated by `scripts/instrument_floor_sweep.py`. Regenerate rather than")
    A("edit — a hand-corrected floor is a declared number wearing a measured")
    A("label, which is the exact defect this table exists to find.")
    A("")
    A("## Read this before reading the table")
    A("")
    A("**A floor is not an error.** It is the reading an instrument produces on")
    A("data containing *none* of what it measures. Every estimator has one;")
    A("almost none of them had been measured. The danger is not that the number")
    A("is wrong — it is that a reading below the floor is indistinguishable")
    A("from a real small value, and it is wrong in a *systematic direction*:")
    A("it OVER-states small quantities. That is how AGK came to over-charge")
    A("megacaps roughly tenfold while looking like a strict improvement.")
    A("")
    A("**Every floor here is a LOWER bound.** Each is measured on a *declared*")
    A("synthetic microstructure that is kinder than the market in every")
    A("direction it simplifies: volume clustering, overnight gaps,")
    A("time-varying spreads and informed flow are all omitted, and every one of")
    A("them would raise the floor.")
    A("")
    A("**A floor comes from the VARIANCE of the null reading, not its level.**")
    A("An instrument that always reads 3 too high is *biased* — subtract 3. One")
    A("whose null reading wanders over [0, 6] is *blind* below 6, and no")
    A("constant recovers it. The two need opposite remedies (recalibrate versus")
    A("replace), so the table reports the null band and the bias separately.")
    A("")
    A("**The rule (Order 18 §4):** an instrument's floor is part of the")
    A("instrument. Below it, refusal — the floor value is never the estimate.")
    A("`instrument_floor.guard_reading()` enforces this with")
    A("`UNRESOLVABLE_FOR_INPUT`.")
    A("")
    A(_findings(p))
    A("## The table")
    A("")
    A("| instrument | units | n | reads on EMPTY data | detection floor | "
      "resolves from | bias there | stabilises at | verdict |")
    A("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for r in p["instruments"]:
        if "refused" in r:
            A(f"| `{r['instrument']}` | — | — | — | — | — | — | — | "
              f"**REFUSED** — {r['refused'][:80]} |")
            continue
        bias = (_fmt(r["bias_at_smallest_resolvable"]) + "x"
                if r.get("bias_comparable") and r["bias_at_smallest_resolvable"]
                else "n/a")
        A(f"| `{r['instrument']}` | {_cell(r['units'])} | {r['n_obs']} | "
          f"{_fmt(r['null_median'])} | {_fmt(r['detection_floor'])} | "
          f"{_fmt(r['smallest_resolvable_truth'])} | {bias} | "
          f"{_fmt(r['stabilisation_n'])} | {_cell(r['verdict'])} |")
    A("")
    A("`bias = n/a` means the injected truth and the instrument's reading are")
    A("in different units — Amihud reads `|r|/$vol` while the truth injected is")
    A("an impact coefficient — so a ratio across that gap would be a made-up")
    A("number. Resolvability still means something there; the ratio does not.")
    A("")
    A("## Per-instrument ladders")
    A("")
    for r in p["instruments"]:
        if "refused" in r:
            continue
        A(f"### `{r['instrument']}`")
        A("")
        A(f"*{r['basis']}*")
        A("")
        if r.get("consumers"):
            A("Feeds: " + ", ".join(f"`{c}`" for c in r["consumers"]))
            A("")
        A("| true value | median read | p05 | p95 | resolved |")
        A("|---:|---:|---:|---:|:--:|")
        for row in r["ladder"]:
            mark = "yes" if row.get("resolved") else "**no**"
            A(f"| {_fmt(row['truth'])} | {_fmt(row.get('median_read'))} | "
              f"{_fmt(row.get('p05'))} | {_fmt(row.get('p95'))} | {mark} |")
        A("")
    A("---")
    A("")
    A(f"Sweep took {p['elapsed_sec']}s. `backend/data/optimus/"
      "instrument_floors.json` carries the machine-readable form.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
