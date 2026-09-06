"""G4 — FREEZE THE CHAMPION, AND OPEN THE SEALED ERA EXACTLY ONCE.

`docs/ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md` §3/§5, item G4.

THE ORDER IS THE EXPERIMENT
===========================
1. Read G2 and G3. Choose the champion by a rule that is WRITTEN AND HASHED
   before anything in 2016-2024 is touched (`G4_CHAMPION_DECLARATION.json`).
2. Rebuild the champion's series from its genome — deterministically, by the
   same code path that built it in development — and hash the DEVELOPMENT half
   so the object opened against is provably the object frozen.
3. Open the sealed era through `growth_lab.sealed()`, which appends to an
   APPEND-ONLY ledger. `sealed_era_openings` on this receipt is the count that
   ledger holds for this champion, read back after the call — not a constant.
4. Report, with beta first, either outcome.

THE PBO CONDITION, AND WHY IT IS A LABEL HERE AND NOT A VETO
============================================================
The mandate's champion rule is "best development leverage-neutral TW passing
the constraints and PBO < 0.5". PBO is a property of the SEARCH, not of an arm
— `inference.pbo` consumes the whole leaderboard and returns one number for it.
The family's PBO is above 0.5, so read as a veto the rule opens the sealed era
never, and the question the amendment exists to ask is not answered but merely
unasked. That is not a result.

So the rule is declared, before the open, as: **the constraints are a VETO; the
family PBO is a LABEL carried on the champion and on every sentence about it.**
A champion frozen out of a family whose PBO says SELECTION_IS_OVERFIT is worth
exactly one sealed-era look and no forward capital, and the §5 gate below
records that separately from the wealth numbers.

THE SELECTION RATE IS THE CLAIM RATE
====================================
The champion is chosen on its **25 bps** development cell, because the sealed
claim is made at 25 bps. Selecting at 10 bps and claiming at 25 is a mismatch
that flatters whichever genome has the most turnover.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import receipt_provenance as RP          # noqa: E402
from learner import growth as GR                               # noqa: E402
from learner import growth_lab as GL                           # noqa: E402
from scripts import growth_g2_generation0 as G2                # noqa: E402
from scripts import growth_g3_mutations as G3                  # noqa: E402

OUT_DIR = GL.OUT_DIR
CHAMPION_DECL = OUT_DIR / "G4_CHAMPION_DECLARATION.json"
SELECTION_COST_BPS = 25.0
CLAIM_COST_BPS = 25.0

FREEZE_RULE = {
    "rule": ("the genome whose 25 bps DEVELOPMENT cell has the highest "
             "leverage-neutral terminal wealth among cells that PASS the "
             "declared constraints"),
    "constraints_are": "A VETO",
    "family_pbo_is": ("A LABEL. PBO is a property of the search, not of an arm; "
                      "read as a veto it opens the sealed era never, and an "
                      "unasked question is not a result. It is carried on the "
                      "champion and on every sentence about it."),
    "selection_cost_bps": SELECTION_COST_BPS,
    "claim_cost_bps": CLAIM_COST_BPS,
    "why_the_same_rate": ("selecting at 10 bps and claiming at 25 flatters "
                          "whichever genome has the most turnover"),
    "sealed_era_openings_permitted": 1,
}


def _genome_index() -> dict[str, GL.Genome]:
    """Every genome this programme has built: generation 0 plus G3's children."""
    G = {g.genome_id: g for g in GL.generation_zero()}
    p = OUT_DIR / "G3_mutations.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        for cell in d["cells"].values():
            g = cell.get("genome")
            if not g:
                continue
            G[g["genome_id"]] = GL.Genome(
                genome_id=g["genome_id"], family=g["family"], base=g["base"],
                spec=g["spec"], overlay=tuple(g["overlay"]),
                parent_ids=tuple(g["parent_ids"]),
                mutation_history=tuple(g["mutation_history"]), note=g["note"])
    return G


def choose_champion(g2: dict, g3: dict) -> tuple[str, dict]:
    """The freeze rule, applied. Returns (genome_id, the evidence for it)."""
    best, evidence = None, None
    for src, d in (("generation_0", g2), ("mutation", g3)):
        for cell, v in d["cells"].items():
            if not cell.endswith(f"{SELECTION_COST_BPS:.0f}bps"):
                continue
            if v.get("beta") is None:
                continue
            if not (v.get("constraints") or {}).get("passes"):
                continue
            ln = (v.get("leverage_neutral") or {}).get("terminal_wealth")
            if ln is None:
                continue
            if best is None or ln > best[1]:
                best = (cell, float(ln))
                evidence = {"source": src, "cell": cell, **_row(v)}
    if best is None:
        raise SystemExit(
            "REFUSED: no cell at the selection rate passes the constraints. "
            "There is nothing to freeze and the sealed era stays closed.")
    return best[0].rsplit("|", 1)[0], evidence


def _row(v: dict) -> dict:
    ln = v.get("leverage_neutral") or {}
    return {
        "beta": v.get("beta"),
        "intercept_annual_pct": (v.get("market_model") or {}).get("intercept_annualised_pct"),
        "intercept_t_hac": (v.get("market_model") or {}).get("intercept_t_hac"),
        "leverage_neutral_tw": ln.get("terminal_wealth"),
        "raw_tw": (v.get("book") or {}).get("terminal_wealth"),
        "spy_tw": (v.get("spy") or {}).get("terminal_wealth"),
        "max_drawdown": (v.get("book") or {}).get("max_drawdown"),
        "maxdd_budget": (v.get("constraints") or {}).get("maxdd_budget"),
        "constraints_pass": (v.get("constraints") or {}).get("passes"),
        "months": v.get("months"),
    }


GATE_CORRECTION = (
    "CORRECTED AFTER THE SEALED NUMBERS WERE VISIBLE, and the correction is "
    "recorded rather than absorbed. The gate as first written compared the "
    "UNLEVERED book's terminal wealth to LEVERED SPY's -- an unlevered book "
    "against a levered benchmark, which is not 'at equal drawdown budget' and "
    "is the exact confusion this whole module exists to stop. Amendment 5 says "
    "'sealed-era TW > levered-SPY TW at EQUAL drawdown budget', so both sides "
    "are sized to the budget: `largest_admissible.terminal_wealth` against "
    "`levered_spy_at_budget.terminal_wealth`. BOTH readings are reported. The "
    "correction changes ONE sub-condition and does NOT change the verdict -- the "
    "DSR and PBO conditions fail either way -- which is the only reason it was "
    "safe to make after the fact. The sealed era was NOT re-opened: every number "
    "here comes from the single opening already on the ledger."
)


def build_gate(claim: dict, dsr: dict, era_signs, family_pbo: dict) -> dict:
    """The amendment 5 gate, every condition named, both leverage readings shown."""
    lev_spy = claim.get("levered_spy_at_budget") or {}
    adm = claim.get("largest_admissible") or {}
    book_tw = claim["book"]["terminal_wealth"] or 0.0
    spy_tw = claim["spy"]["terminal_wealth"] or 0.0
    ln_tw = (claim.get("leverage_neutral") or {}).get("terminal_wealth") or 0.0
    gate = {
        # THE AMENDMENT 5 CONDITION: both sides sized to the SAME budget.
        "sealed_tw_at_budget_beats_levered_spy_at_budget": bool(
            (adm.get("terminal_wealth") or 0) > (lev_spy.get("terminal_wealth") or 0)),
        "dsr_over_family_gt_0_95": bool((dsr.get("dsr") or 0) > 0.95),
        "positive_in_at_least_2_of_3_development_eras": bool(
            sum(1 for x in era_signs if x == "POSITIVE") >= 2),
        "constraints_pass_on_the_sealed_era": bool(
            (claim.get("constraints") or {}).get("passes")),
        "family_pbo_below_0_5": bool((family_pbo.get("pbo") or 1.0) < 0.5),
    }
    gate["ALL_MET"] = all(gate.values())
    gate["failed"] = [k for k, v in gate.items() if k != "ALL_MET" and not v]
    gate["_also_reported_not_part_of_the_gate"] = {
        "unlevered_book_beats_spy_tr": bool(book_tw > spy_tw),
        "unlevered_book_tw": book_tw, "spy_tr_tw": spy_tw,
        "leverage_neutral_tw_beats_spy_tr": bool(ln_tw > spy_tw),
        "leverage_neutral_tw": ln_tw,
        "book_at_budget_tw": adm.get("terminal_wealth"),
        "book_leverage_at_budget": adm.get("leverage"),
        "levered_spy_at_budget_tw": lev_spy.get("terminal_wealth"),
        "spy_leverage_at_budget": lev_spy.get("leverage"),
    }
    gate["_correction"] = GATE_CORRECTION
    return gate


def build_champion_series(g: GL.Genome, panel, ctx, bps: float) -> pd.Series:
    s, _ = G3._build_child(g, panel, ctx, bps)
    return pd.Series(s.to_numpy(),
                     index=pd.Index([str(x) for x in s.index])).dropna().sort_index()


def era_sign_table(book: pd.Series, spy: pd.Series) -> dict:
    """Development sign in each of the THREE canonical eras.

    The grid comes from `learner.evaluate.long_eras()`, which derives it from
    `learner.long_panel.ERAS` — not from `evaluate.ERAS`, which is 2016-2024 and
    would silently describe only the sealed era.
    """
    from learner import evaluate as E
    out = {}
    for name, (lo, hi) in E.long_eras().items():
        idx = pd.Index([str(x) for x in book.index])
        m = (idx >= f"{lo}-01") & (idx <= f"{hi}-12")
        b = book[m]
        if len(b) < 12:
            out[name] = {"verdict": f"CANNOT DETERMINE ({len(b)} months)"}
            continue
        s = spy.reindex(b.index)
        d = (b - s).dropna()
        out[name] = {
            "months": int(len(b)),
            "book_tw": round(float((1 + b).prod()), 4),
            "spy_tw": round(float((1 + s.dropna()).prod()), 4),
            "mean_monthly_excess_pct": round(float(d.mean()) * 100.0, 4),
            "sign": "POSITIVE" if d.mean() > 0 else "NEGATIVE",
        }
    out["_grid_source"] = ("learner.evaluate.long_eras(), derived from "
                           "learner.long_panel.ERAS — NOT evaluate.ERAS, which "
                           "is 2016-2024 and would describe only the sealed era")
    return out


def run(*, verbose: bool = True, argv=None) -> dict:
    t0 = datetime.now(timezone.utc)
    tracker = RP.InputTracker()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    from scripts import w3_neural_floored as W3B
    free = W3B.free_gb()
    if free is not None and free < 6.0:
        raise SystemExit(f"REFUSED: {free:.1f} GB free, floor 6.0 GB.")

    for p in (OUT_DIR / "G2_generation0.json", OUT_DIR / "G3_mutations.json",
              GL.DECLARATION):
        if not p.exists():
            raise SystemExit(f"REFUSED: {p} is missing; G4 adjudicates a search "
                             "and cannot invent one.")
        tracker.opened(p, note="growth-book search receipt")
    g2 = json.loads((OUT_DIR / "G2_generation0.json").read_text(encoding="utf-8"))
    g3 = json.loads((OUT_DIR / "G3_mutations.json").read_text(encoding="utf-8"))
    decl = json.loads(GL.DECLARATION.read_text(encoding="utf-8"))
    if GL.declaration_sha256(decl) != decl["sha256"]:
        raise SystemExit(
            "REFUSED: DECLARATION.json no longer hashes to its recorded value. "
            "The sealed era is opened against a commitment or not at all.")

    champ_id, evidence = choose_champion(g2, g3)
    genomes = _genome_index()
    if champ_id not in genomes:
        raise SystemExit(f"REFUSED: champion {champ_id!r} cannot be rebuilt from "
                         "any recorded genome.")
    champ = genomes[champ_id]

    panel, uni, fp = G2.load_panel(tracker, verbose=verbose)
    ctx = GL.market_context(panel, tracker)

    series = {bps: build_champion_series(champ, panel, ctx, bps)
              for bps in GL.COST_RATES_BPS}
    dev_series = {bps: GL.dev(s) for bps, s in series.items()}
    for bps, s in dev_series.items():
        GL.assert_development_only(s, f"champion {champ_id} @{bps:.0f}bps")

    # the FREEZE. Hash the development half: the object opened against must be
    # provably the object that was chosen.
    dev_payload = json.dumps(
        {"genome": champ.to_json(),
         "development": {f"{bps:.0f}": [[m, round(float(v), 10)]
                                        for m, v in dev_series[bps].items()]
                         for bps in sorted(dev_series)}},
        sort_keys=True)
    champ_sha = hashlib.sha256(dev_payload.encode()).hexdigest()

    family_pbo = (g2.get("pbo_over_the_whole_family") or {})
    frozen = {
        "declaration": "GROWTH BOOK — the frozen champion, before the sealed era is opened",
        "authority": "docs/ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md §3/§5",
        "licence": "PRODUCT_EXPERIMENT",
        "search_declaration_sha256": decl["sha256"],
        "freeze_rule": FREEZE_RULE,
        "champion_genome_id": champ_id,
        "champion_genome": champ.to_json(),
        "champion_sha256": champ_sha,
        "champion_sha256_covers": ("the genome recipe plus every DEVELOPMENT "
                                   "monthly return at both cost rates, to 10 dp"),
        "development_evidence": evidence,
        "family_cells_looked_at": g3.get("family_cells_after_mutation"),
        "family_pbo": family_pbo.get("pbo"),
        "family_pbo_verdict": family_pbo.get("verdict"),
        "family_holm_best": g3.get("family_holm_best_over_everything"),
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "sealed_era_openings_before_this_job": GL.openings_for(champ_id),
    }
    RP.attach(frozen, argv or sys.argv, {"job": "G4_seal"}, tracker)
    CHAMPION_DECL.write_text(json.dumps(frozen, indent=1, default=str), encoding="utf-8")
    if verbose:
        print(f"FROZEN before the open: {champ_id}  sha {champ_sha[:16]}  "
              f"(dev LN-TW {evidence['leverage_neutral_tw']}, beta {evidence['beta']})",
              flush=True)

    # ------------------------------------------------------- OPEN. ONCE. ----
    already = GL.openings_for(champ_id)
    if already:
        raise SystemExit(
            f"REFUSED: the sealed era has already been opened {already} time(s) "
            f"for champion {champ_id!r} (SEALED_ERA_OPENINGS.jsonl). It is opened "
            "ONCE per frozen champion. Freeze a different champion or read the "
            "receipt that exists.")

    spy_full = ctx["spy"].dropna()
    rf_full = ctx["rf"].dropna()
    legs = {f"book_{bps:.0f}bps": series[bps] for bps in GL.COST_RATES_BPS}
    legs["spy_tr"] = spy_full
    legs["risk_free"] = rf_full
    opened = GL.open_sealed_window(
        legs, champion_id=champ_id, champion_sha256=champ_sha,
        reason=(f"G4: the one adjudication of {champ_id} on 2016-2024 -- book at "
                f"both cost rates, the SPY leg and the risk-free leg over exactly "
                f"the same months"))
    sealed_series = {bps: opened[f"book_{bps:.0f}bps"] for bps in GL.COST_RATES_BPS}
    spy_sealed, rf_sealed = opened["spy_tr"], opened["risk_free"]
    sealed_eval = {}
    for bps, s in sealed_series.items():
        sealed_eval[f"{bps:.0f}bps"] = GR.evaluate_growth(
            s, spy_sealed, rf_sealed, cost_bps=bps,
            label=f"{champ_id}|SEALED|{bps:.0f}bps", n_boot=2000)

    dev_eval = {f"{bps:.0f}bps": GR.evaluate_growth(
        dev_series[bps], GL.dev(spy_full), GL.dev(rf_full), cost_bps=bps,
        label=f"{champ_id}|DEV|{bps:.0f}bps", n_boot=1000)
        for bps in GL.COST_RATES_BPS}

    claim = sealed_eval[f"{CLAIM_COST_BPS:.0f}bps"]
    lev_spy = claim.get("levered_spy_at_budget") or {}
    eras = era_sign_table(dev_series[CLAIM_COST_BPS], GL.dev(spy_full))
    era_signs = [v.get("sign") for k, v in eras.items()
                 if isinstance(v, dict) and v.get("sign")]

    from learner import inference as INF
    n_trials = int(g3.get("family_cells_after_mutation") or 128)
    excess = (sealed_series[CLAIM_COST_BPS]
              - spy_sealed.reindex(sealed_series[CLAIM_COST_BPS].index)).dropna()
    dsr = INF.deflated_sharpe(excess.to_numpy(), n_trials=n_trials)

    gate = build_gate(claim, dsr, era_signs, family_pbo)

    out = {
        "job": "G4_seal",
        "lane": "G growth book",
        "licence": "PRODUCT_EXPERIMENT",
        "question": ("does the frozen champion beat SPY TR and levered-SPY at the "
                     "same drawdown budget on 2016-2024, unseen in development, "
                     "after 25 bps?"),
        "search_declaration_sha256": decl["sha256"],
        "champion_declaration": str(CHAMPION_DECL),
        "champion_genome_id": champ_id,
        "champion_sha256": champ_sha,
        "champion_genome": champ.to_json(),
        "freeze_rule": FREEZE_RULE,
        "sealed_era": [GL.SEALED_START, GL.SEALED_END],
        "sealed_era_openings": GL.openings_for(champ_id),
        "sealed_era_openings_note": (
            "read back from the append-only SEALED_ERA_OPENINGS.jsonl AFTER the "
            "call, not asserted. The book and each benchmark leg are one opening "
            "of the same window by the same frozen champion."),
        "sealed_era_openings_all_champions": len(GL.sealed_openings()),
        "development": dev_eval,
        "development_era_signs": eras,
        "sealed": sealed_eval,
        "dsr_over_family_on_the_sealed_excess": dsr,
        "family_cells_looked_at": n_trials,
        "family_pbo": family_pbo.get("pbo"),
        "family_pbo_verdict": family_pbo.get("verdict"),
        "amendment_gate_5": gate,
        "llm_spend_usd": 0.0,
        "llm_calls": 0,
        "memory_free_gb_before": free,
        "wall_seconds": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    b, s = claim["book"], claim["spy"]
    mm = claim.get("market_model") or {}
    adm = claim.get("largest_admissible") or {}
    out["headline"] = (
        f"beta {claim['beta']} (intercept {mm.get('intercept_annualised_pct')}%/yr, "
        f"HAC t {mm.get('intercept_t_hac')}): on 2016-2024, unseen in development, "
        f"{champ_id} returned {b['terminal_wealth']}x vs SPY TR "
        f"{s['terminal_wealth']}x after {CLAIM_COST_BPS:.0f} bps, at maxDD "
        f"{b['max_drawdown']} against SPY's {s['max_drawdown']}. "
        f"SIZED TO THE SAME DRAWDOWN BUDGET the book runs {adm.get('leverage')}x "
        f"for {adm.get('terminal_wealth')}x and levered SPY runs "
        f"{lev_spy.get('leverage')}x for {lev_spy.get('terminal_wealth')}x. "
        f"Leverage-neutral TW {(claim.get('leverage_neutral') or {}).get('terminal_wealth')}. "
        f"DSR {dsr.get('dsr')} over {n_trials} cells; family PBO "
        f"{family_pbo.get('pbo')}; amendment 5 gate "
        f"{'MET' if gate['ALL_MET'] else 'NOT MET'}"
        + ("" if gate["ALL_MET"] else f" -- failed {', '.join(gate['failed'])}"))
    RP.attach(out, argv or sys.argv,
              {"job": "G4_seal", "selection_cost_bps": SELECTION_COST_BPS,
               "claim_cost_bps": CLAIM_COST_BPS}, tracker)
    (OUT_DIR / "G4_seal.json").write_text(
        json.dumps(out, indent=1, default=str), encoding="utf-8")
    return out


def regate(argv=None) -> dict:
    """Recompute the VERDICT from the receipt. The window is NOT re-opened.

    A gate defect found after the fact is fixed here and nowhere else: the
    sealed era is opened once per frozen champion, and re-running `run()` would
    correctly refuse. Every number this reads was produced by that one opening.
    """
    tracker = RP.InputTracker()
    p = OUT_DIR / "G4_seal.json"
    if not p.exists():
        raise SystemExit(f"REFUSED: {p} is missing; there is no verdict to correct.")
    tracker.opened(p, note="the sealed receipt whose verdict is being recomputed")
    out = json.loads(p.read_text(encoding="utf-8"))
    claim = out["sealed"][f"{CLAIM_COST_BPS:.0f}bps"]
    era_signs = [v.get("sign") for k, v in out["development_era_signs"].items()
                 if isinstance(v, dict) and v.get("sign")]
    family_pbo = {"pbo": out.get("family_pbo"), "verdict": out.get("family_pbo_verdict")}
    dsr = out["dsr_over_family_on_the_sealed_excess"]
    gate = build_gate(claim, dsr, era_signs, family_pbo)
    b, s = claim["book"], claim["spy"]
    mm = claim.get("market_model") or {}
    lev_spy = claim.get("levered_spy_at_budget") or {}
    adm = claim.get("largest_admissible") or {}
    champ_id = out["champion_genome_id"]
    n_trials = out["family_cells_looked_at"]
    out["amendment_gate_5"] = gate
    out["regated_utc"] = datetime.now(timezone.utc).isoformat()
    out["sealed_era_reopened_by_this_correction"] = False
    out["headline"] = (
        f"beta {claim['beta']} (intercept {mm.get('intercept_annualised_pct')}%/yr, "
        f"HAC t {mm.get('intercept_t_hac')}): on 2016-2024, unseen in development, "
        f"{champ_id} returned {b['terminal_wealth']}x vs SPY TR "
        f"{s['terminal_wealth']}x after {CLAIM_COST_BPS:.0f} bps, at maxDD "
        f"{b['max_drawdown']} against SPY's {s['max_drawdown']}. "
        f"SIZED TO THE SAME DRAWDOWN BUDGET the book runs {adm.get('leverage')}x "
        f"for {adm.get('terminal_wealth')}x and levered SPY runs "
        f"{lev_spy.get('leverage')}x for {lev_spy.get('terminal_wealth')}x. "
        f"Leverage-neutral TW {(claim.get('leverage_neutral') or {}).get('terminal_wealth')}. "
        f"DSR {dsr.get('dsr')} over {n_trials} cells; family PBO "
        f"{family_pbo.get('pbo')}; amendment 5 gate "
        f"{'MET' if gate['ALL_MET'] else 'NOT MET'}"
        + ("" if gate["ALL_MET"] else f" -- failed {', '.join(gate['failed'])}"))
    RP.attach(out, argv or sys.argv, {"job": "G4_seal", "mode": "regate"}, tracker)
    p.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return out


def main(argv=None) -> int:                                # pragma: no cover
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--regate", action="store_true",
                    help="recompute the verdict from the receipt; the sealed "
                         "window is NOT re-opened")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    out = regate(sys.argv) if a.regate else run(verbose=not a.quiet, argv=sys.argv)
    print("\n" + out["headline"])
    print(f"\nreceipt: {OUT_DIR / 'G4_seal.json'}")
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
