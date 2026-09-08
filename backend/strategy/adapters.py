"""EXISTING BOOKS, EXPRESSED THROUGH THE CONTRACT.

This module is the proof that `Strategy` + `run_one` is an interface over what
Aegis already has rather than a parallel universe beside it. Two books are
expressed here, and both are chosen because they already carry a receipt that
can be compared against, field by field:

* **the composite arena book** (`ENGINE_BASELINE_v1`, selector `arena_composite`)
  -- its sealed artefact is its IDENTITY: `config_hash`, `policy_fingerprint`
  and `book_fingerprint` under scheme `book-v1`, plus the deterministic
  `policies.select` / `policies.size` pair. There is no sealed BACKTEST receipt
  for it in this repository: the arena is a forward paper engine whose NAV rows
  come from live marks, so "reproduce its sealed receipt" means reproducing the
  identity and the selection, not a replayed NAV. That is stated on the receipt
  rather than papered over.
* **the growth-book champion** (`m12_quality_mom|dd`) -- its sealed artefact is
  `backend/data/optimus/growth_book/G4_seal.json`, whose `development` block is
  fully reproducible and whose `sealed` block is NOT, by design: the era is
  opened once per frozen champion against an append-only ledger.

WHY THE ADAPTERS BUILD A `Strategy` RATHER THAN SUBCLASSING ONE
==============================================================
The contract is data. An adapter reads a YAML or a declaration JSON and emits
the frozen record; nothing about a book lives in a Python subclass, so two
books can be diffed by diffing their `as_dict()`. This is the shape freqtrade
does NOT have (its strategies are classes and cannot be compared as values) and
the one Vibe-Trading's `config.json` does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from backend.strategy.contract import (Benchmark, Construction, CostModel,
                                       HoldRule, Licence, LossBudget, Objective,
                                       Signal, Sizing, Strategy, StrategyError,
                                       Universe, Window)
from backend.strategy.run import register_engine

REPO = Path(__file__).resolve().parents[2]
GROWTH_DIR = REPO / "backend" / "data" / "optimus" / "growth_book"
CHAMPION_DECL = GROWTH_DIR / "G4_CHAMPION_DECLARATION.json"
G4_SEAL = GROWTH_DIR / "G4_seal.json"


# ==========================================================================
# (a) THE COMPOSITE ARENA BOOK


def arena_book_strategy(book_id: str = "ENGINE_BASELINE_v1") -> Strategy:
    """The arena book, as a `Strategy`. Read from the YAML, never hand-written.

    A hand-built dict is exactly what missed the 2026-08-24 selector defect
    (`spec.py`: `book_selection_signal` fell back to `arena_composite` while
    `BookSpec.selection_signal` fell back to `multifactor_score`), so this
    reads the real file through the real loader.
    """
    from backend.services.arena import spec as SPEC

    specs = SPEC.load_specs()
    if book_id not in specs:
        raise StrategyError(f"unknown arena book {book_id!r}; declared: "
                            f"{sorted(specs)}")
    b = specs[book_id]
    d = b.defaults
    signal_name = d.get("selection_signal", SPEC.DEFAULT_SELECTION_SIGNAL)
    return Strategy(
        strategy_id=f"arena:{book_id}",
        title=f"arena book {book_id} ({b.purpose})",
        universe=Universe(
            name="arena_scan_universe",
            source="backend/services/arena/discovery.py",
            min_price_usd=float(d.get("min_price", 5.0)),
            max_names=int(d.get("scan_universe_n", 400)),
            note="the arena's daily scan universe; NOT a survivorship-free panel",
        ),
        signal=Signal(
            name=signal_name,
            column=signal_name,
            source="backend/services/arena/information_bus.py",
            note=("THE BOTTLENECK: `COMPOSITE_WEIGHTS` is momentum 1.0 + "
                  "multifactor 1.0 + four 0.5s, and coverage is {'1': 206, "
                  "'6': 1} -- 99.5% of names carry exactly one factor, 12-1 "
                  "momentum. Expressing this book through the contract does not "
                  "fix that; it makes it a field a reader can see."),
        ),
        construction=Construction(
            rule="composite_top_k",
            k=int(d.get("select_top_k", 12)),
            weighting=("inverse_vol" if b.sizing == "inverse_trailing_vol"
                       else "ce_kelly" if b.sizing == "ce_kelly" else "ew"),
            max_single_name=float(d.get("max_single_name", 0.15)),
        ),
        hold=HoldRule(
            horizon_periods=21,
            min_hold_periods=0,
            exit_priority=("THESIS_INVALIDATED", "REBALANCE"),
            scheduled_review_periods=21,
            note=("`rebalance: monthly_calendar` and `execution: "
                  "next_session_open` are DESCRIPTIVE defaults in the YAML -- "
                  "implemented in engine._decision_due and "
                  "policies.orders_from_targets. The contract records them as "
                  "the hold rule they actually are."),
        ),
        sizing=Sizing(rule=b.sizing, gross_cap=1.0,
                      notional_usd=float(d.get("notional_usd", 100_000.0))),
        costs=CostModel(transaction_cost_bps=float(d.get("transaction_cost_bps", 5)),
                        slippage_bps=float(d.get("slippage_bps", 1))),
        benchmark=Benchmark(name=str(d.get("benchmark", "SPY")),
                            series_key="spy_tr", beta_matched=True),
        objective=Objective(name="alpha_intercept", periods_per_year=12),
        loss_budget=LossBudget(
            positions_judged=int(d.get("select_top_k", 12)) * 4,
            expected_losers=int(int(d.get("select_top_k", 12)) * 4 * 0.5),
            note=("invariant 19 made explicit for a book that never declared "
                  "one: judged over four monthly rebalances, half expected to "
                  "lag. Declared HERE by the adapter and NOT read from the "
                  "YAML, which has no such field -- so it is a proposal to be "
                  "frozen, not a record of an existing commitment."),
        ),
        licence=Licence.PRODUCT_EXPERIMENT,
        engine="arena_composite",
        engine_params={"book_id": book_id,
                       "selection_signal": signal_name,
                       "screens": list(b.screens),
                       "config_hash": b.config_hash,
                       "policy_fingerprint": b.policy_fingerprint,
                       "book_fingerprint": b.book_fingerprint,
                       "config_version": b.config_version},
        note=b.purpose,
    )


@register_engine("arena_composite")
def _engine_arena(*, strategy: Strategy, universe: Universe, window: Window,
                  objective: Objective, ctx: Mapping[str, Any]) -> dict:
    """Run the arena book's SELECTION and report its identity.

    `ctx["day_state"]` is the arena's own day-state dict
    (`{"names": {ticker: {"scores": {...}, "price": ..., "vol63": ...}}}`).
    Without one the engine returns identity only and says so -- it does not
    invent a universe, and it does not report a beta it did not measure.
    """
    from backend.services.arena import policies as POL
    from backend.services.arena import selector_identity as SI
    from backend.services.arena import spec as SPEC

    p = dict(strategy.engine_params)
    book_id = p["book_id"]
    signal = p["selection_signal"]
    specs = SPEC.load_specs()
    b = specs[book_id]

    identity = {
        "book_id": book_id,
        "config_version": b.config_version,
        "config_hash": b.config_hash,
        "policy_fingerprint": b.policy_fingerprint,
        "book_fingerprint": b.book_fingerprint,
        "selector_identity": SI.selector_identity(signal),
        "composite_weight_fingerprint": SI.composite_weight_fingerprint(),
        "validation_status": b.validation_status,
        "reproduced_from": str(SPEC.CONFIG_PATH),
    }

    out: dict[str, Any] = {
        "beta": None,
        "beta_note_engine": (
            "CANNOT DETERMINE from this engine. The arena is a FORWARD paper "
            "engine: its NAV rows come from live marks, not from a replay, so "
            "there is no offline series to regress. Beta for this book comes "
            "from its lane NAV table, which is separately marked STALE "
            "(roadmap X2) and is therefore not quoted here rather than quoted "
            "wrongly."),
        "identity": identity,
        "book": {"terminal_wealth": None, "max_drawdown": None,
                 "why": ("no offline replay exists for a forward paper book; "
                         "this receipt reproduces IDENTITY and SELECTION")},
        "grade": {"verdict": "IDENTITY_AND_SELECTION_ONLY"},
    }

    day_state = ctx.get("day_state")
    if day_state is None:
        out["selection"] = {"verdict": ("CANNOT DETERMINE (no day_state supplied; "
                                        "the engine does not invent a universe)")}
        return out

    sel = POL.select(day_state,
                     top_k=strategy.construction.k,
                     min_price=float(universe.min_price_usd or 0.0),
                     screens=tuple(p.get("screens") or ()),
                     signal=signal)
    weights = POL.size(sel.chosen, day_state,
                       sizing=strategy.sizing.rule,
                       max_single_name=strategy.construction.max_single_name)
    out["selection"] = {
        "chosen": sel.chosen,
        "rejected": sel.rejected,
        "excluded": sel.excluded,
        "weights": weights,
        "n_chosen": len(sel.chosen),
        "gross": float(sum(abs(v) for v in weights.values())),
        "computed_by": "backend.services.arena.policies.select + .size",
    }
    out["weights_by_period"] = {str(window.end): weights}
    return out


# ==========================================================================
# (b) THE GROWTH-BOOK CHAMPION


def growth_champion_strategy(*, cost_bps: float = 25.0,
                             declaration: Path | None = None) -> Strategy:
    """The frozen growth champion, as a `Strategy`.

    Read from `G4_CHAMPION_DECLARATION.json` -- the object that was hashed
    BEFORE the sealed era was opened -- so the strategy this returns is the
    strategy that was frozen, and `engine_params["champion_sha256"]` carries
    the proof.
    """
    path = Path(declaration or CHAMPION_DECL)
    if not path.exists():
        raise StrategyError(
            f"REFUSED: {path} is missing. The growth champion is defined by its "
            "frozen declaration; reconstructing it from the leaderboard would "
            "be a different object with the same name.")
    d = json.loads(path.read_text(encoding="utf-8"))
    g = d["champion_genome"]
    spec = dict(g["spec"])
    dd_budget = -0.50   # the EXTREME personality's declared drawdown budget
    return Strategy(
        strategy_id=f"growth:{g['genome_id']}",
        title="growth book champion -- quality-momentum with a drawdown overlay",
        universe=Universe(
            name="tradable_long_panel",
            source="learner.long_panel.LONG_TABLE via learner.neural_long.tradable_universe",
            floor_dollar_vol_usd=3_000_000.0,
            min_price_usd=5.0,
            note=("the FLOORED training universe; the floor is applied to the "
                  "population the stage predictions were fitted on, and the "
                  "universe fingerprint is checked rather than assumed"),
        ),
        signal=Signal(name=spec.get("pred_col", "quality_mom"),
                      column=spec.get("pred_col", "quality_mom"),
                      source="learner.growth_lab.build_panel_base"),
        construction=Construction(
            rule="top_k",
            k=int(spec.get("k", 110)),
            weighting=str(spec.get("weight", "vw")),
            max_single_name=1.0,
            hysteresis_rank=int(spec["hold_k"]) if spec.get("hold_k") else None,
            gross_cap=2.0,
            note=("`hold_k` is hysteresis, not a second k: a name is bought at "
                  "rank <= k and held until rank > hold_k. That is stage four "
                  "expressed in stage three's parameters, which is why the "
                  "contract names it explicitly."),
        ),
        hold=HoldRule(horizon_periods=1, min_hold_periods=0,
                      exit_priority=("THESIS_INVALIDATED", "REBALANCE"),
                      scheduled_review_periods=1,
                      note="monthly rebalance with rank hysteresis at hold_k"),
        sizing=Sizing(rule="vw_with_overlays", gross_cap=2.0,
                      overlays=tuple(g.get("overlay") or ()),
                      params={k: v for k, v in spec.items()
                              if k not in ("pred_col", "weight", "k", "hold_k")}),
        costs=CostModel(transaction_cost_bps=float(cost_bps), slippage_bps=0.0,
                        financing_bps_over_rf=100.0,
                        note=("the growth lab charges ONE per-side rate and no "
                              "separate slippage leg; the rate is the claim "
                              "rate and the selection rate, deliberately equal")),
        benchmark=Benchmark(name="SPY TR", series_key="spy_tr",
                            beta_matched=True, levered_at_budget=True),
        objective=Objective(name="terminal_wealth_at_drawdown_budget",
                            periods_per_year=12, drawdown_budget=dd_budget,
                            utility="extreme_growth",
                            note="the PRODUCT ruler; the claims ruler is reported beside it"),
        loss_budget=LossBudget(
            positions_judged=15, expected_losers=6,
            note=("roadmap block F, hack4: judged at 15 positions, 6 expected "
                  "to lose, at 1x under the EXTREME budget -- it does not fit "
                  "the aggressive 35% budget (contract maxDD -46.88%, "
                  "P(lose half) 0.232, proxy MC 0.442)"),
        ),
        licence=Licence.PRODUCT_EXPERIMENT,
        engine="growth_lab",
        engine_params={
            "genome": g,
            "champion_sha256": d.get("champion_sha256"),
            "search_declaration_sha256": d.get("search_declaration_sha256"),
            "family_pbo": d.get("family_pbo"),
            "family_pbo_verdict": d.get("family_pbo_verdict"),
            "family_cells_looked_at": d.get("family_cells_looked_at"),
            "cost_bps": float(cost_bps),
            "n_boot": 1000,
            "label": f"{g['genome_id']}|DEV|{float(cost_bps):.0f}bps",
        },
        parents=tuple(g.get("parent_ids") or ()),
        note=g.get("note", ""),
    )


@register_engine("growth_lab")
def _engine_growth(*, strategy: Strategy, universe: Universe, window: Window,
                   objective: Objective, ctx: Mapping[str, Any]) -> dict:
    """Rebuild the genome's series and grade it -- by the same code path.

    Nothing is recomputed here: `growth_g3_mutations._build_child` is the
    function that built the series in development, and
    `learner.growth.evaluate_growth` is the function that graded it. This
    engine only supplies the arguments.
    """
    from learner import growth as GR
    from learner import growth_lab as GL
    from scripts import growth_g2_generation0 as G2
    from scripts import growth_g3_mutations as G3

    tracker = ctx.get("tracker")
    p = dict(strategy.engine_params)
    gj = p["genome"]
    genome = GL.Genome(genome_id=gj["genome_id"], family=gj["family"],
                       base=gj["base"], spec=gj["spec"],
                       overlay=tuple(gj.get("overlay") or ()),
                       parent_ids=tuple(gj.get("parent_ids") or ()),
                       mutation_history=tuple(gj.get("mutation_history") or ()),
                       note=gj.get("note", ""))
    bps = float(p.get("cost_bps", 25.0))

    panel = ctx.get("panel")
    market = ctx.get("market_context")
    if panel is None or market is None:
        panel, _uni, _fp = G2.load_panel(tracker, verbose=bool(ctx.get("verbose")))
        market = GL.market_context(panel, tracker)

    raw, meta = G3._build_child(genome, panel, market, bps)
    series = pd.Series(raw.to_numpy(),
                       index=pd.Index([str(x) for x in raw.index])).dropna().sort_index()
    spy_full = market["spy"].dropna()
    rf_full = market["rf"].dropna()

    book = GL.dev(series) if not window.sealed else _sealed_slice(series, window)
    if not window.sealed:
        # A development run that reached into the sealed era would be the one
        # failure this whole lab is built to make impossible.
        GL.assert_development_only(book, f"{strategy.strategy_id} @{bps:.0f}bps")
    bench = GL.dev(spy_full) if not window.sealed else _sealed_slice(spy_full, window)
    rf = GL.dev(rf_full) if not window.sealed else _sealed_slice(rf_full, window)

    ev = GR.evaluate_growth(book, bench, rf, cost_bps=bps,
                            label=p.get("label"),
                            n_boot=int(p.get("n_boot", 1000)))
    excess = (book - pd.Series(bench).reindex(book.index)).dropna()
    from backend.strategy import verdict as V
    n_trials = int(p.get("family_cells_looked_at") or 1)
    return {
        "beta": ev.get("beta"),
        "book": ev.get("book"),
        "benchmark": {"terminal_wealth": (ev.get("spy") or {}).get("terminal_wealth"),
                      "max_drawdown": (ev.get("spy") or {}).get("max_drawdown")},
        "net": book,
        "benchmark_series": bench,
        "evaluate_growth": ev,
        "genome_meta": meta,
        "champion_sha256": p.get("champion_sha256"),
        "family_pbo": p.get("family_pbo"),
        "family_pbo_verdict": p.get("family_pbo_verdict"),
        "grade": {
            "market_model": ev.get("market_model"),
            "deflated_sharpe": V.deflated_sharpe_from_returns(
                excess.to_numpy(), n_trials=n_trials),
            "n_effective": V.n_effective_date_blocks(list(book.index)),
            "family_pbo": p.get("family_pbo"),
            "family_pbo_note": ("PBO is a property of the SEARCH, not of this arm. "
                                "It is a LABEL carried on the champion and on every "
                                "sentence about it."),
        },
        "leverage_neutral": ev.get("leverage_neutral"),
        "largest_admissible": ev.get("largest_admissible"),
        "levered_spy_at_budget": ev.get("levered_spy_at_budget"),
        "constraints": ev.get("constraints"),
    }


def _sealed_slice(s: pd.Series, window: Window) -> pd.Series:
    """Only ever reached with an explicit `sealed_authorisation`; `run_one`
    refuses before this point otherwise."""
    idx = pd.Index([str(x) for x in s.index])
    out = s[(idx >= window.start) & (idx <= window.end)]
    out.index = [str(x) for x in out.index]
    return out


# ==========================================================================
# comparing a run against a sealed receipt


def compare_to_sealed(receipt: Mapping[str, Any], sealed_block: Mapping[str, Any],
                      *, path: str = "") -> dict:
    """Field-by-field diff of a `run_one` receipt against a sealed receipt block.

    Returns findings; raises nothing. Non-comparable keys (timestamps, wall
    clock, provenance) are named rather than skipped, because "we did not
    compare it" and "it agreed" must never read the same.
    """
    ignore = {"generated_utc", "frozen_utc", "wall_seconds", "_provenance",
              "regated_utc", "opened_utc"}
    same, differ, missing = [], [], []

    def walk(a: Any, b: Any, trail: str) -> None:
        if isinstance(b, Mapping):
            if not isinstance(a, Mapping):
                missing.append({"field": trail, "sealed": "<block>", "run": repr(a)[:80]})
                return
            for k, v in b.items():
                if k in ignore:
                    continue
                if k not in a:
                    missing.append({"field": f"{trail}.{k}" if trail else k,
                                    "sealed": _short(v), "run": "<absent>"})
                    continue
                walk(a[k], v, f"{trail}.{k}" if trail else k)
            return
        if isinstance(b, (list, tuple)):
            if not isinstance(a, (list, tuple)) or len(a) != len(b):
                differ.append({"field": trail, "sealed": _short(b), "run": _short(a)})
                return
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{trail}[{i}]")
            return
        if isinstance(b, float) and isinstance(a, (int, float)):
            if abs(float(a) - float(b)) <= 1e-12:
                same.append(trail)
            else:
                differ.append({"field": trail, "sealed": b, "run": a,
                               "delta": abs(float(a) - float(b))})
            return
        if a == b:
            same.append(trail)
        else:
            differ.append({"field": trail, "sealed": _short(b), "run": _short(a)})

    walk(receipt, sealed_block, path)
    return {
        "n_compared": len(same) + len(differ),
        "n_same": len(same),
        "n_differ": len(differ),
        "n_absent_from_run": len(missing),
        "identical": not differ and not missing,
        "differences": differ,
        "absent_from_run": missing,
        "ignored_keys": sorted(ignore),
        "reading": ("`identical` means every field the sealed block declares was "
                    "present in the run and equal to it. Timestamps and provenance "
                    "are named in `ignored_keys` rather than silently skipped."),
    }


def _short(v: Any) -> Any:
    s = repr(v)
    return v if len(s) <= 120 else s[:117] + "..."


__all__ = ["arena_book_strategy", "growth_champion_strategy", "compare_to_sealed",
           "CHAMPION_DECL", "G4_SEAL", "GROWTH_DIR"]
