"""Retire the Order 18 declared cost band, one name at a time, against TAQ.

    python -m scripts.taq_calibrate                 # table + docs/TAQ_COST_CALIBRATION.md
    python -m scripts.taq_calibrate --render-only   # re-render from the saved JSON

Reads `backend/data/optimus/taq_quoted_spreads_calibration.csv` (WRDS millisecond
TAQ NBBO, pulled 2026-08-18) and writes:

    docs/TAQ_COST_CALIBRATION.md
    backend/data/optimus/taq_cost_calibration.json

WHAT THIS SCRIPT WILL NOT DO
============================
It will not report a panel-wide average for a name the panel did not cover, and
it will not retire a band on thin coverage. Both are `taq_calibration` refusals
rather than choices made here, so the rule lives in one place and a second
caller cannot make a different one.

The AGK overlap is OFF by default. Comparing the two instruments needs OHLC bars
per name, which is a network fetch; on the evening of a paid night run that is
competition for the same machine, and the comparison is not time-critical.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import config                                  # noqa: E402
from backend.services import cost_model as CM                      # noqa: E402
from backend.services import taq_calibration as TC                 # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "TAQ_COST_CALIBRATION.md"
JSON_OUT = ROOT / "backend" / "data" / "optimus" / "taq_cost_calibration.json"


def _cell(x: object) -> str:
    """Escape pipes. Learned from the floor sweep, where Amihud's units
    (`|r|/$vol`) split a markdown row into three cells."""
    return str(x).replace("|", "\\|")


def _universe() -> list[str]:
    uni = config["stock_universe"]
    out = set(uni.get("default_watchlist", []))
    for names in uni.get("sector_stocks", {}).values():
        out.update(names)
    out.update({"PLUG", "SOC", "IWM"})
    return sorted(out)


def build() -> dict:
    panel = TC.load_panel()
    meta = TC.load_meta()
    tickers = sorted({r["ticker"] for r in panel} | set(_universe()))

    rows = []
    for t in tickers:
        res = TC.cost_for(panel, t)
        reading = res.get("reading")
        rows.append({
            "ticker": t,
            "retired": bool(res.get("band_retired")),
            "one_way_bps": (round(res["cost"].value, 4)
                            if res.get("cost") is not None else None),
            "full_bps": round(reading.full_bps, 4) if reading else None,
            "day_low": round(reading.full_bps_day_low, 4) if reading else None,
            "day_high": round(reading.full_bps_day_high, 4) if reading else None,
            "n_days": reading.n_days if reading else 0,
            "mid": round(reading.mid_price, 2) if reading else None,
            "tick_floor_bps": round(reading.tick_floor, 4) if reading else None,
            "ticks_wide": round(reading.ticks_wide, 2) if reading else None,
            "at_tick_floor": bool(reading.at_tick_floor) if reading else False,
            "notes": list(reading.notes) if reading else [],
            "reason": res.get("reason"),
        })

    summary = TC.summarise_retirement(
        [{"band_retired": r["retired"], "at_tick_floor": r["at_tick_floor"]}
         for r in rows])

    # The two claims the sensitivity test separates, computed rather than
    # remembered. `lo` is the declared band's low end, `hi` its high end.
    lo, hi = CM.LIQUID_BAND_ONE_WAY_BPS
    retired = [r for r in rows if r["retired"] and r["one_way_bps"] is not None]
    sens = None
    if retired:
        # THE MEDIAN NAME, NOT THE CHEAPEST. The cheapest retired name is the
        # one most flattering to every claim below, and quoting it would be
        # picking the convenient end of the panel the same way
        # `resolve_band_by_picking` refuses to pick the convenient end of a
        # band. The counts beside it are what the claim actually rests on.
        ordered = sorted(retired, key=lambda r: r["one_way_bps"])
        ref = ordered[len(ordered) // 2]
        sens = {
            "reference_name": ref["ticker"],
            "reference_rank": "median of retired names",
            "n_retired": len(retired),
            "below_band_high": TC.survives_bias_sensitivity(
                ref["one_way_bps"], hi),
            "below_band_low": TC.survives_bias_sensitivity(
                ref["one_way_bps"], lo),
            "n_survive_below_high": sum(
                TC.survives_bias_sensitivity(r["one_way_bps"], hi)["survives"]
                for r in retired),
            "n_survive_below_low": sum(
                TC.survives_bias_sensitivity(r["one_way_bps"], lo)["survives"]
                for r in retired),
            "cheapest": {"ticker": ordered[0]["ticker"],
                         "one_way_bps": ordered[0]["one_way_bps"]},
            "widest": {"ticker": ordered[-1]["ticker"],
                       "one_way_bps": ordered[-1]["one_way_bps"]},
            # Where the panel actually sits RELATIVE TO THE BAND. This is the
            # number the whole page turns on and it was missing: every claim
            # above is a tail statement, and a tail statement invites the
            # reader to supply the middle themselves.
            "below_band": sum(1 for r in retired if r["one_way_bps"] < lo),
            "inside_band": sum(1 for r in retired
                               if lo <= r["one_way_bps"] <= hi),
            "above_band": sum(1 for r in retired if r["one_way_bps"] > hi),
        }

    # ── coverage: an absence is not one thing ──────────────────────────────
    # "Not in the panel" has at least two causes with opposite remedies, and a
    # single count of missing names hides which. TAQ stores a symbol as a root
    # of at most 4 characters plus a suffix (probed 2026-08-14: 8,717 distinct
    # 4-char roots, 9 of length 5), so GOOGL is `GOOG`+`L` and CMCSA is
    # `CMCS`+`A`. A pull that maps only the hyphen form (BRK-B -> BRK+B) asks
    # for a root that does not exist and gets silence. That is ACTIONABLE.
    # A name that is simply dead or renamed (PXD delisted, SQ now trades as
    # XYZ) is also absent, and waiting will not fix it. That is DELIBERATE.
    in_panel = {r["ticker"] for r in panel}
    absent = sorted(set(_universe()) - in_panel)
    coverage = {
        "n_universe": len(_universe()),
        "n_in_panel": len(in_panel & set(_universe())),
        "absent": absent,
        "actionable": [t for t in absent if len(t) > 4 and "-" not in t],
        "deliberate_or_unknown": [t for t in absent
                                  if not (len(t) > 4 and "-" not in t)],
        "rule": ("a ticker longer than 4 characters with no hyphen is stored "
                 "in TAQ as root=first 4 chars + suffix=the rest; a pull that "
                 "queries the whole ticker as the root finds nothing"),
    }

    return {
        "coverage": coverage,
        "panel_meta": meta,
        "n_panel_rows": len(panel),
        "declared_band_one_way_bps": [lo, hi],
        "taq_entitlement": CM.TAQ_ENTITLEMENT,
        "provenance": TC.MEASURED_TAQ_QUOTED,
        "bias_ledger": TC.bias_ledger(),
        "net_bias_sign": TC.net_bias_sign(),
        "bias_sensitivity_factor": TC.BIAS_SENSITIVITY_FACTOR,
        "sensitivity": sens,
        "summary": summary,
        "rows": rows,
    }


def _findings(d: dict) -> list[str]:
    """Derived from the data so they cannot drift from the table above them."""
    out = []
    s = d["summary"]
    out.append(
        f"**{s['n_band_retired']} of {s['n_names']} names retired their "
        f"declared band** ({s['fraction_retired']:.0%}); {s['n_band_stays']} "
        f"keep it and each keeps it for a recorded reason, not for lack of a "
        f"row.")
    if s["n_at_tick_floor"]:
        out.append(
            f"**{s['n_at_tick_floor']} name(s) sit at the one-tick quantisation "
            f"floor.** Their readings are hard UPPER bounds — the tape cannot "
            f"express a narrower spread — so they are flagged and still used, "
            f"which is the difference between quantisation and blindness.")
    sens = d.get("sensitivity")
    if sens:
        lo, hi = d["declared_band_one_way_bps"]
        ref, n = sens["reference_name"], sens["n_retired"]
        f = d["bias_sensitivity_factor"]
        b_hi, b_lo = sens["below_band_high"], sens["below_band_low"]

        def _v(b):
            return "HOLDS" if b["survives"] else "FAILS"

        def _br(b):
            side = "beyond" if b["breaks_at_factor"] > f else "inside"
            return f"breaks at {b['breaks_at_factor']:.2f}x, {side} the {f}x"

        out.append(
            f"**The declared band's TOP over-charges the typical name**: the "
            f"MEDIAN retired name ({ref}) at "
            f"{b_hi['measured_one_way_bps']:.3f}bp one-way stays under {hi}bp "
            f"inflated {f}x — {_v(b_hi)}, {_br(b_hi)}. "
            f"**{sens['n_survive_below_high']} of {n}** retired names survive "
            f"that test. The cheapest is "
            f"{sens['cheapest']['ticker']} at "
            f"{sens['cheapest']['one_way_bps']}bp and the widest "
            f"{sens['widest']['ticker']} at "
            f"{sens['widest']['one_way_bps']}bp — the median is quoted here "
            f"because the cheapest is the name most flattering to every claim "
            f"on this page.")
        out.append(
            f"**Against the band's {lo}bp FLOOR the answer is different and "
            f"much thinner**: the median name {_v(b_lo)} ({_br(b_lo)}), and "
            f"only **{sens['n_survive_below_low']} of {n}** retired names "
            f"survive it. So 'TAQ shows the band over-charges' is one sentence "
            f"covering two claims of very different strength, and only the "
            f"first is established across the panel.")
    if sens:
        lo, hi = d["declared_band_one_way_bps"]
        mid_band = (lo + hi) / 2
        med = sens["below_band_high"]["measured_one_way_bps"]
        out.append(
            f"**{sens['inside_band']} of {sens['n_retired']} retired names "
            f"land INSIDE the declared {lo}-{hi}bp one-way band** "
            f"({sens['inside_band'] / sens['n_retired']:.0%}); "
            f"{sens['below_band']} sit below it and {sens['above_band']} above. "
            f"**Beware the unit here**: {lo}-{hi}bp ONE-WAY is {lo * 2}-{hi * 2}bp "
            f"FULL spread, so a name quoted at '5bp' on the tape is at "
            f"{5 / 2}bp one-way — the lower-middle of the band, not below it. "
            f"That is the same full-vs-one-way confusion the "
            f"`COST_BPS_ONE_WAY` type was introduced to stop, arriving in the "
            f"INTERPRETATION rather than the code.")
        out.append(
            f"**So the declared band was a GOOD DECLARATION, not an "
            f"over-charge.** Its midpoint is {mid_band}bp one-way and the "
            f"panel's median retired name is {med:.3f}bp — within "
            f"{abs(med - mid_band) / mid_band:.0%} of it. Order 18 declared "
            f"{lo}-{hi}bp before any of this was measurable and the measurement "
            f"lands inside it. The headline is not that the stopgap was wrong; "
            f"it is that a stopgap is now a measurement for {sens['n_retired']} "
            f"names.")
        out.append(
            f"**DENOMINATOR WARNING, and it is the one that could flip this "
            f"page.** The band was declared for the names AGK CANNOT RESOLVE — "
            f"the tight end — and the figures above are computed over the WHOLE "
            f"panel, because no per-name AGK reading is joined here. The two "
            f"populations are not the same and the tight end is exactly where "
            f"'below the band' is most likely to hold. Read every count above "
            f"as 'of all panel names', never as 'of the segment the band was "
            f"for'. Computing the correct denominator needs the AGK overlap, "
            f"which is the next run and is not done.")
    cov = d.get("coverage")
    if cov and cov["absent"]:
        out.append(
            f"**{len(cov['absent'])} universe names are absent from the panel, "
            f"and absence is not one thing.** "
            f"**ACTIONABLE ({len(cov['actionable'])}): "
            f"{', '.join(cov['actionable']) or 'none'}** — TAQ stores a symbol "
            f"as a root of at most 4 characters plus a suffix, so GOOGL is "
            f"`GOOG`+`L` and CMCSA is `CMCS`+`A`. The pull mapped only the "
            f"hyphen form, asked for a root that does not exist, and got "
            f"silence; the quotes are there (GOOGL 381,220 and CMCSA 161,730 "
            f"on 2026-08-14, probed directly). Re-pull fixes these. "
            f"**DELIBERATE/UNKNOWN ({len(cov['deliberate_or_unknown'])}): "
            f"{', '.join(cov['deliberate_or_unknown']) or 'none'}** — dead or "
            f"renamed universe entries (PXD delisted 2024; SQ now trades as "
            f"XYZ, present in TAQ under that ticker), which no re-pull fixes "
            f"and which are a universe-staleness item instead.")
    out.append(
        f"**Net bias sign is {d['net_bias_sign']}.** Two of the three known "
        f"biases point DOWN and one points UP; a conclusion drawn from the "
        f"point estimate is drawn from a number of unknown direction, which is "
        f"why every headline above is stated as a sensitivity instead.")
    return out


def render(d: dict) -> str:
    lo, hi = d["declared_band_one_way_bps"]
    L = [
        "# TAQ cost calibration — what the declared band retires against",
        "",
        f"Generated by `scripts/taq_calibrate.py`. Provenance "
        f"`{d['provenance']}`; TAQ entitlement `{d['taq_entitlement']}`.",
        "",
        "Order 18 §1 gave names AGK could not resolve a DECLARED band of "
        f"{lo}-{hi}bp one-way, with the clause that the band retires when a "
        "resolving instrument arrives. This is that retirement. It happens "
        "**one name at a time**: entitlement is a fact about a subscription, a "
        "retired band is a fact about a name.",
        "",
        "## Findings",
        "",
    ]
    L += [f"{i}. {t}" for i, t in enumerate(_findings(d), 1)]
    L += [
        "",
        "## The bias ledger — all three, with signs",
        "",
        "The panel is a QUOTED NBBO spread. Three things sit between it and "
        "what a strategy pays, and they do not agree in sign. This table is "
        "generated from `taq_calibration.bias_ledger()` so a write-up cannot "
        "carry only the flattering entry.",
        "",
        "| bias | sign | detail | resolvable by |",
        "|---|---|---|---|",
    ]
    for b in d["bias_ledger"]:
        L.append(f"| `{_cell(b['name'])}` | **{b['sign']}** | "
                 f"{_cell(b['detail'])} | {_cell(b['resolvable_by'])} |")
    L += [
        "",
        f"Net sign: **{d['net_bias_sign']}**. Declared sensitivity factor: "
        f"**{d['bias_sensitivity_factor']}x**.",
        "",
        "## Per name",
        "",
        "`ticks` is the reading divided by the one-tick floor implied by the "
        "name's own mid price. A name at ~1.0 tick is at the QUANTISATION "
        "floor: the reading is an upper bound that more data cannot tighten.",
        "",
        "| ticker | band | one-way bps | full bps | daily range | days | mid | "
        "tick floor | ticks | note |",
        "|---|---|---:|---:|---|---:|---:|---:|---:|---|",
    ]
    for r in sorted(d["rows"], key=lambda x: (not x["retired"], x["ticker"])):
        if r["retired"]:
            note = "AT TICK FLOOR" if r["at_tick_floor"] else ""
            L.append(
                f"| {_cell(r['ticker'])} | RETIRED | {r['one_way_bps']} | "
                f"{r['full_bps']} | {r['day_low']}-{r['day_high']} | "
                f"{r['n_days']} | {r['mid']} | {r['tick_floor_bps']} | "
                f"{r['ticks_wide']} | {_cell(note)} |")
        else:
            why = (r["reason"] or "").split(".")[0][:90]
            L.append(f"| {_cell(r['ticker'])} | **stays** | — | — | — | "
                     f"{r['n_days']} | — | — | — | {_cell(why)} |")
    L += [
        "",
        "## What this does not establish",
        "",
        "* **Quoted is not effective.** The effective spread needs a "
        "trade-quote join (Holden-Jacobsen); until that exists no cost here "
        "may carry `MEASURED_TAQ`, only `MEASURED_TAQ_QUOTED`.",
        "* **A retired band is not a validated strategy.** It removes a "
        "`COST_MODEL_SENSITIVE` verdict's cause; it says nothing about whether "
        "the verdict is any good.",
        "* **The AGK overlap is not computed here.** AGK resolves only the "
        "wide end, so any ratio measured on the overlap belongs to that end — "
        "`apply_calibration` refuses outside the range it was measured on.",
        "",
    ]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--render-only", action="store_true",
                    help="re-render the doc from the saved JSON")
    a = ap.parse_args(argv)

    if a.render_only:
        if not JSON_OUT.exists():
            print(f"no saved run at {JSON_OUT}", file=sys.stderr)
            return 2
        d = json.loads(JSON_OUT.read_text(encoding="utf-8"))
    else:
        try:
            d = build()
        except TC.TaqRefused as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
        JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
        JSON_OUT.write_text(json.dumps(d, indent=1, default=str),
                            encoding="utf-8")

    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(render(d), encoding="utf-8")
    s = d["summary"]
    print(f"{s['n_band_retired']}/{s['n_names']} bands retired "
          f"({s['fraction_retired']:.0%}); {s['n_at_tick_floor']} at the tick "
          f"floor; net bias sign {d['net_bias_sign']}")
    for t in _findings(d):
        print("  - " + t.replace("**", ""))
    print(f"\nwrote {DOC}\nwrote {JSON_OUT}")

    # CANARY. An actionable coverage hole must not be reportable as a clean
    # run: the table above is complete-looking whether or not the pull asked
    # for every name, and a silent gap is exactly what a summary launders.
    act = d.get("coverage", {}).get("actionable") or []
    if act:
        print(f"\nCANARY: {len(act)} name(s) absent for a fixable reason "
              f"({', '.join(act)}). Re-pull with root/suffix mapping.",
              file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
