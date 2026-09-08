"""`run_one(strategy, universe, window, objective) -> receipt`.

ONE CALL FROM AN IDEA TO A GRADED, COST-AWARE, RECEIPTED RESULT.

    PIT data load -> predictions -> candidate selection -> construction ->
    sizing -> holding rules -> costs -> benchmark -> simulation -> grading ->
    receipt

WHAT IT DOES AND DOES NOT DO
============================
It does not compute a return. Every number on a `run_one` receipt is produced
by machinery that already existed and already has tests -- `learner.growth`,
`learner.growth_lab`, `learner.fundamental_law`, `backend.services.arena.policies`,
`backend.services.portfolio_farm` -- and the acceptance test for this whole
block is that two existing books, re-expressed through the contract, reproduce
their existing receipts. A wrapper that produced slightly different numbers
would be a second engine wearing an interface, which is worse than no
interface at all.

BETA IS PRINTED FIRST
=====================
`beta` is literally the first key of the returned dict, and
`test_strategy_run_one.py` asserts it. `docs/AEGIS_STRATEGIC_INVARIANTS.md`
and S43 ("the ruler changed -- excess is a LOADING"): a book that is 1.2x the
market is not a book with alpha, and putting beta anywhere but first lets the
reader form an impression from the wealth line before reaching it.

A SEALED WINDOW IS REFUSED
==========================
`Window.sealed=True` is refused unless `sealed_authorisation` is passed. The
growth book's 2016-2024 era is opened ONCE per frozen champion against an
append-only ledger; a verification re-run is still a look, and a convenience
flag that quietly re-opened it would destroy the only property the seal has.
The refusal names the ledger and the receipt that already holds the answer.

COSTS ARE NEVER ZERO
====================
The refusal lives in `CostModel.__post_init__`, which constructs a
`portfolio_farm.Policy` so that the ONE zero-cost refusal in the repository is
the one that fires. `zero_cost_diagnostic` travels onto the receipt's cost
block, its headline and its `strategy_row`.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from backend.services import receipt_provenance as RP
from backend.strategy import chain as CH
from backend.strategy import execution as EX
from backend.strategy import ladder as LAD
from backend.strategy import leak as LK
from backend.strategy import manifold as MF
from backend.strategy import numerai as NM
from backend.strategy import protections as PR
from backend.strategy import verdict as V
from backend.strategy.contract import (Objective, Strategy, StrategyError,
                                       Universe, Window)

RECEIPT_SCHEMA = "strategy-receipt-1"

#: engine name -> callable(strategy, universe, window, objective, ctx) -> dict
#: Each returns a block with, at minimum, `book` (the graded outcome) and
#: optionally `series`, `weights_by_period`, `panel`, `pred_col`, `exits`.
_ENGINES: dict[str, Callable[..., dict]] = {}


class SealedWindowRefused(RuntimeError):
    """A sealed era was reached for without an explicit authorisation."""


class EngineNotRegistered(RuntimeError):
    """The strategy names an engine `run_one` cannot dispatch to."""


def register_engine(name: str) -> Callable[[Callable[..., dict]], Callable[..., dict]]:
    def deco(fn: Callable[..., dict]) -> Callable[..., dict]:
        _ENGINES[name] = fn
        return fn
    return deco


def engines() -> list[str]:
    return sorted(_ENGINES)


# --------------------------------------------------------------------------
# the entry point


def run_one(strategy: Strategy,
            universe: Universe | None = None,
            window: Window | None = None,
            objective: Objective | None = None,
            *,
            data: Mapping[str, Any] | None = None,
            sealed_authorisation: str | None = None,
            argv: list[str] | None = None,
            out_path: str | Path | None = None,
            tracker: RP.InputTracker | None = None,
            verbose: bool = False) -> dict:
    """Run one strategy end to end and return its receipt.

    `universe` and `objective` default to the strategy's own declarations, so
    the two-argument call `run_one(strategy, window=w)` is the common case; the
    four-argument form exists to run the SAME strategy against a different
    universe or ruler without editing it, which is how a foreign-slice test is
    written.
    """
    t0 = datetime.now(timezone.utc)
    tracker = tracker or RP.InputTracker()
    universe = universe or strategy.universe
    objective = objective or strategy.objective
    if window is None:
        raise StrategyError(
            "run_one needs a Window. A book graded over 'whatever was in the "
            "file' is a book whose window is a property of the data directory, "
            "and two sessions cannot compare it.")

    if window.sealed and not sealed_authorisation:
        raise SealedWindowRefused(
            f"REFUSED: window {window.label or window.start + '..' + window.end} "
            f"is SEALED. A sealed era is opened once per frozen strategy against "
            f"an append-only ledger, and recomputation is still a look. Pass "
            f"`sealed_authorisation=<why, in words>` to record one, or read the "
            f"receipt that already holds the answer. This refusal is the reason "
            f"a sealed receipt cannot be reproduced end to end by re-running: "
            f"that is correct behaviour, not a gap in the interface.")

    engine = _ENGINES.get(strategy.engine)
    if engine is None:
        raise EngineNotRegistered(
            f"strategy {strategy.strategy_id!r} names engine {strategy.engine!r}; "
            f"registered: {engines()}. `run_one` never computes returns itself, "
            f"so an unregistered engine is a refusal rather than a fallback.")

    ctx = dict(data or {})
    ctx["tracker"] = tracker
    ctx["verbose"] = verbose
    block = engine(strategy=strategy, universe=universe, window=window,
                   objective=objective, ctx=ctx)

    receipt = _assemble(strategy, universe, window, objective, block,
                        sealed_authorisation=sealed_authorisation, t0=t0,
                        ctx=ctx)
    RP.attach(receipt, argv or sys.argv,
              {"strategy_id": strategy.strategy_id,
               "strategy_fingerprint": strategy.fingerprint,
               "engine": strategy.engine,
               "window": [window.start, window.end],
               "objective": objective.name,
               "licence": strategy.licence.value}, tracker)
    if out_path:
        import json
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
        receipt["written_to"] = str(p)
    if verbose:
        print(receipt["headline"], flush=True)
    return receipt


# --------------------------------------------------------------------------
# receipt assembly


def _assemble(strategy: Strategy, universe: Universe, window: Window,
              objective: Objective, block: Mapping[str, Any], *,
              sealed_authorisation: str | None, t0: datetime,
              ctx: Mapping[str, Any] | None = None) -> dict:
    book = dict(block.get("book") or {})
    beta = block.get("beta", book.get("beta"))

    ch = block.get("information_chain")
    if ch is None:
        ch = CH.information_chain(
            panel=block.get("panel"),
            pred_col=block.get("pred_col"),
            weights_by_period=block.get("weights_by_period"),
            net=block.get("net"),
            benchmark=block.get("benchmark_series"),
            beta=beta,
            exits=block.get("exits") or (),
            declared_exit_priority=strategy.hold.exit_priority,
            periods_per_year=objective.periods_per_year,
        )

    # BETA FIRST. Literally: this dict is built beta-first and the test pins it.
    receipt: dict[str, Any] = {}
    receipt["beta"] = beta
    receipt["beta_note"] = (
        "printed first, always. An excess return is a LOADING before it is an "
        "intercept (S43): a book at beta 1.2 in a rising tape produces excess "
        "with no alpha in it, and a reader who meets the wealth line first has "
        "already formed the wrong impression."
    )
    receipt["schema"] = RECEIPT_SCHEMA
    receipt["strategy_id"] = strategy.strategy_id
    receipt["title"] = strategy.title
    receipt["licence"] = strategy.licence.value
    receipt["strategy_fingerprint"] = strategy.fingerprint
    receipt["strategy_row"] = strategy.as_row()
    receipt["strategy"] = strategy.as_dict()
    receipt["universe"] = {"name": universe.name, "source": universe.source,
                           "floor_dollar_vol_usd": universe.floor_dollar_vol_usd,
                           "min_price_usd": universe.min_price_usd,
                           "max_names": universe.max_names,
                           "fingerprint": universe.fingerprint}
    receipt["window"] = {"start": window.start, "end": window.end,
                         "label": window.label, "sealed": bool(window.sealed),
                         "periods_per_year": int(window.periods_per_year)}
    if window.sealed:
        receipt["sealed_authorisation"] = sealed_authorisation
    receipt["objective"] = {"name": objective.name,
                            "periods_per_year": objective.periods_per_year,
                            "drawdown_budget": objective.drawdown_budget,
                            "utility": objective.utility,
                            "note": ("every ranked comparison names the objective "
                                     "it was computed under")}
    receipt["costs"] = strategy.costs.as_row()
    receipt["information_chain"] = ch
    receipt["construction_defect"] = ch.get("construction_defect")
    receipt["signal_verdict"] = ch.get("signal_verdict_readable_from_this_book")
    receipt["benchmark"] = {
        "name": strategy.benchmark.name,
        "series_key": strategy.benchmark.series_key,
        "beta_matched": strategy.benchmark.beta_matched,
        "levered_at_budget": strategy.benchmark.levered_at_budget,
        "is_own_universe_average": strategy.benchmark.is_own_universe_average,
        **(block.get("benchmark") or {}),
    }
    if strategy.benchmark.is_own_universe_average:
        receipt["benchmark"]["WARNING"] = (
            "the benchmark is the equal-weight average of this book's own traded "
            "universe. That is a DIAGNOSTIC, never a claim: an EW average against "
            "a VW market is the regime, not the edge.")
    receipt["book"] = book
    receipt["grade"] = block.get("grade") or {}
    receipt["loss_budget"] = {
        "positions_judged_at": strategy.loss_budget.positions_judged,
        "expected_losers": strategy.loss_budget.expected_losers,
        "note": strategy.loss_budget.note,
        **(block.get("loss_budget") or {}),
    }
    receipt["execution"] = _execution_block(strategy, block, ctx or {})
    receipt["exit_ladder"] = _exit_ladder_block(strategy, block, ctx or {})
    receipt["protections"] = _protections_block(strategy, ctx or {})
    receipt["leak_analysis"] = _leak_block(ctx or {})
    receipt["manifold"] = _manifold_block(block, ctx or {})
    receipt["marginal_contribution"] = _mmc_block(ctx or {})
    receipt["engine"] = strategy.engine
    receipt["engine_block"] = {k: v for k, v in block.items()
                               if k not in ("book", "grade", "panel", "net",
                                            "benchmark_series", "weights_by_period",
                                            "information_chain", "benchmark",
                                            "loss_budget", "beta", "exits",
                                            "pred_col", "series")}
    receipt["llm_spend_usd"] = 0.0
    receipt["llm_calls"] = 0
    receipt["wall_seconds"] = round(
        (datetime.now(timezone.utc) - t0).total_seconds(), 3)
    receipt["generated_utc"] = datetime.now(timezone.utc).isoformat()
    receipt["headline"] = _headline(strategy, objective, receipt)
    return receipt


# --------------------------------------------------------------------------
# THE S3-S8 BLOCKS. Each is attached to EVERY receipt: either the number, or a
# named `CANNOT DETERMINE` saying which input was missing. A block that
# vanished when its input did would let a reader mistake "not measured" for
# "not a problem", which is the failure every one of these ports exists to
# stop.


def _cd(what: str) -> dict:
    return {"verdict": f"{V.CANNOT_DETERMINE}: {what}"}


def _execution_block(strategy: Strategy, block: Mapping[str, Any],
                     ctx: Mapping[str, Any]) -> dict:
    """S5. `breakeven_fee_bps` on every result row, plus ADV capacity."""
    book = block.get("book") or {}
    gross = ctx.get("gross_return")
    if gross is None:
        tw = book.get("terminal_wealth")
        gross = (float(tw) - 1.0) if tw is not None else None
    trades = ctx.get("trades")
    if trades is None:
        ic = block.get("information_chain") or {}
        turn = ic.get("one_sided_turnover")
        if turn is None:
            turn = (block.get("hold_statistics") or {}).get("one_sided_turnover")
        if turn is not None:
            trades = EX.trades_from_turnover([float(turn)])
    cap = ctx.get("capacity")
    if (cap is None and ctx.get("adv_value") is not None
            and ctx.get("target_weights") is not None):
        cap = EX.adv_capped_path(ctx["target_weights"], ctx["adv_value"],
                                 capital=float(ctx.get("capital", 1e6)),
                                 max_participation=float(
                                     ctx.get("max_participation", 0.10)))
    return EX.execution_row(
        gross_return=gross, trades=trades,
        position_size=ctx.get("position_size"),
        # PER SIDE, matching the identity's units and COST_BPS_PER_SIDE.
        # `costs.round_trip_bps` is twice this and comparing against it would
        # give every book double its real headroom.
        declared_cost_bps_per_side=(float(strategy.costs.transaction_cost_bps)
                                    + float(strategy.costs.slippage_bps)),
        capacity=cap)


def _exit_ladder_block(strategy: Strategy, block: Mapping[str, Any],
                       ctx: Mapping[str, Any]) -> dict:
    """S6. The stop width against the holding-period volatility, always."""
    sd = ctx.get("per_period_sd")
    supplied = sd is not None
    if sd is None:
        net = block.get("net")
        if net is not None and len(net) > 2:
            sd = float(pd.Series(net).astype(float).std(ddof=1))
    out = {
        "roi_ladder": {str(k): v for k, v in strategy.hold.roi_ladder.items()},
        "exit_priority": list(strategy.hold.exit_priority),
        "min_hold_periods": int(strategy.hold.min_hold_periods),
        "horizon_periods": int(strategy.hold.horizon_periods),
        "stop_vs_volatility": LAD.stop_vs_volatility(
            strategy.hold,
            per_period_sd=sd if sd is not None else float("nan")),
        "sd_source": ("supplied by the caller" if supplied
                      else "the book own period return sd" if sd is not None
                      else V.CANNOT_DETERMINE),
    }
    if ctx.get("exit_records"):
        out["meta_labelled_exits"] = LAD.meta_label_exits(ctx["exit_records"])
    else:
        out["meta_labelled_exits"] = _cd(
            "no exit records with a held counterfactual were supplied, so the "
            "EXIT RULE is ungraded. Entry alpha and exit alpha are different "
            "problems and only one of them was measured here")
    return out


def _protections_block(strategy: Strategy, ctx: Mapping[str, Any]) -> dict:
    """S7. Evaluated BEFORE entries; the guard list is never empty."""
    state = ctx.get("book_state")
    stack = ctx.get("protection_stack")
    if stack is None:
        profile = ctx.get("risk_profile")
        if profile:
            stack = PR.ProtectionStack(PR.default_protections(profile),
                                       profile=profile)
        else:
            stop = abs(float(strategy.hold.stop_loss or 0.10))
            gross = float(strategy.sizing.gross_cap)
            stack = PR.ProtectionStack([
                PR.GrossExposureCap(
                    gross_cap=gross,
                    leverage_reason=(
                        None if gross <= 1.0 else
                        f"the strategy contract {strategy.strategy_id!r} "
                        f"declares sizing.gross_cap {gross:.2f}; a book graded "
                        f"on terminal wealth at a drawdown budget is compared "
                        f"to LEVERED SPY, so leverage is the claim, not a leak")),
                PR.WorstCaseStopBudget(budget_pct_of_equity=gross * stop),
                PR.DailyLossLimit(),
                PR.StoplossGuard(),
                PR.CooldownPeriod(periods=int(strategy.hold.min_hold_periods) or 1),
                PR.MaxDrawdownGuard(),
            ])
    out = stack.evaluate(state if state is not None else PR.BookState())
    out["profile_bounds"] = PR.profile_bounds()
    stop = (abs(float(strategy.hold.stop_loss))
            if strategy.hold.stop_loss is not None else None)
    out["worst_case_from_the_contract"] = {
        "gross_cap": float(strategy.sizing.gross_cap),
        "stop_pct": stop,
        "worst_case_pct_of_equity": (None if stop is None
                                     else float(strategy.sizing.gross_cap) * stop),
        "note": ("gross x stop, printed together: a wider stop on uncapped "
                 "gross is a bigger loss, so neither is ever quoted alone"),
    }
    if state is None:
        out["state_note"] = (
            f"{V.CANNOT_DETERMINE}: no live book state was supplied, so every "
            f"guard that needs one LOCKED rather than assuming a flat book.")
    return out


def _leak_block(ctx: Mapping[str, Any]) -> dict:
    """S3. Both detectors, when the caller hands over its feature builder."""
    build, frame = ctx.get("feature_builder"), ctx.get("raw_frame")
    if build is None or frame is None:
        return _cd("no `feature_builder` + `raw_frame` were supplied, so "
                   "neither leak detector ran. A book whose features were "
                   "never differenced is not a book shown to be leak-free")
    out: dict[str, Any] = {}
    try:
        out["lookahead"] = LK.lookahead_analysis(
            build, frame, ctx.get("checkpoints")).as_dict()
    except LK.LeakAnalysisRefused as exc:
        out["lookahead"] = {"verdict": str(exc)}
    try:
        out["recursive"] = LK.recursive_analysis(
            build, frame, declared_warmup=ctx.get("declared_warmup")).as_dict()
    except LK.LeakAnalysisRefused as exc:
        out["recursive"] = {"verdict": str(exc)}
    return out


def _manifold_block(block: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict:
    """S4. `do_predict` beside every score; books admit only `== 1`."""
    gate = ctx.get("manifold_gate")
    if gate is None:
        train = ctx.get("manifold_train")
        if train is None:
            return _cd("no training feature matrix was supplied, so no "
                       "in-manifold check ran. Every score on this receipt is "
                       "ungated: the model was not asked whether it had ever "
                       "seen a name like this one")
        try:
            gate = MF.fit_manifold(train)
        except MF.ManifoldRefusal as exc:
            return {"verdict": str(exc)}
    out = gate.report()
    rows = ctx.get("manifold_score_rows")
    if rows is not None:
        flags = gate.do_predict(rows)
        out["n_scored"] = int(len(flags))
        out["n_trustworthy"] = int((flags == MF.DO_PREDICT_TRUSTWORTHY).sum())
        out["share_trustworthy"] = (out["n_trustworthy"] / out["n_scored"]
                                    if out["n_scored"] else None)
    return out


def _mmc_block(ctx: Mapping[str, Any]) -> dict:
    """S8. Are its errors DIFFERENT errors, as a number?"""
    panel = ctx.get("mmc_panel")
    if panel is None:
        return _cd("no panel with a meta-model column was supplied, so the "
                   "book MARGINAL contribution over the ensemble it would "
                   "join is unmeasured. A healthy IC and a zero MMC is a "
                   "re-expression, not a mechanism")
    try:
        return NM.mmc(panel, pred_col=ctx["mmc_pred_col"],
                      meta_col=ctx["mmc_meta_col"],
                      target_col=ctx["mmc_target_col"],
                      era_col=ctx["mmc_era_col"])
    except (KeyError, NM.EraScoringRefused) as exc:
        return {"verdict": f"{V.CANNOT_DETERMINE}: {exc}"}


def _headline(strategy: Strategy, objective: Objective, receipt: Mapping[str, Any]) -> str:
    beta = receipt.get("beta")
    book = receipt.get("book") or {}
    grade = receipt.get("grade") or {}
    cost = ("FRICTIONLESS DIAGNOSTIC" if strategy.costs.zero_cost_diagnostic
            else f"{strategy.costs.round_trip_bps:.0f} bps round trip")
    bits = [f"beta {beta if beta is not None else 'CANNOT DETERMINE'}"]
    if book.get("terminal_wealth") is not None:
        bits.append(f"TW {book['terminal_wealth']}")
    if book.get("max_drawdown") is not None:
        bits.append(f"maxDD {book['max_drawdown']}")
    if grade.get("dsr") is not None:
        bits.append(f"DSR {round(float(grade['dsr']), 4)}")
    tc = receipt.get("information_chain", {}).get("transfer_coefficient")
    bits.append(f"TC {tc if tc is not None else 'CANNOT DETERMINE'}")
    verdict = receipt.get("signal_verdict")
    return (f"[{strategy.licence.value}] {strategy.strategy_id} @ {cost}, "
            f"objective {objective.name}: " + ", ".join(str(b) for b in bits)
            + f"; signal verdict {verdict}")


# --------------------------------------------------------------------------
# ENGINE: series -- grade a monthly/period return series that already exists
#
# This is the smallest possible engine and the one the tests use: it takes a
# book series, a benchmark series and a risk-free series and grades them with
# `learner.growth.evaluate_growth`, which is the same function the growth book
# receipts were written with. It computes nothing new.


@register_engine("series")
def _engine_series(*, strategy: Strategy, universe: Universe, window: Window,
                   objective: Objective, ctx: Mapping[str, Any]) -> dict:
    from learner import growth as GR

    book = ctx.get("book")
    if book is None:
        raise StrategyError(
            "engine 'series' needs `data={'book': <pd.Series of period returns>}`. "
            "It grades a series that already exists; it does not build one.")
    bench = ctx.get("benchmark")
    rf = ctx.get("rf")
    book = _slice(pd.Series(book).dropna(), window)
    if bench is None or rf is None:
        raise StrategyError(
            "engine 'series' needs `benchmark` and `rf` series too. A book "
            "graded without its benchmark cannot report beta, and beta is "
            "printed first on every book.")
    bench = _slice(pd.Series(bench).dropna(), window).reindex(book.index)
    rf = _slice(pd.Series(rf).dropna(), window).reindex(book.index)

    ev = GR.evaluate_growth(book, bench, rf,
                            cost_bps=float(strategy.costs.transaction_cost_bps),
                            label=f"{strategy.strategy_id}|{window.label or window.start}",
                            n_boot=int(ctx.get("n_boot", 1000)))
    out: dict[str, Any] = {
        "beta": ev.get("beta"),
        "book": ev.get("book"),
        "benchmark": {"terminal_wealth": (ev.get("spy") or {}).get("terminal_wealth"),
                      "max_drawdown": (ev.get("spy") or {}).get("max_drawdown")},
        "net": book,
        "benchmark_series": bench,
        "evaluate_growth": ev,
    }
    if ctx.get("panel") is not None:
        out["panel"] = ctx["panel"]
        out["pred_col"] = ctx.get("pred_col")
    if ctx.get("weights_by_period") is not None:
        out["weights_by_period"] = ctx["weights_by_period"]
    if ctx.get("exits"):
        out["exits"] = ctx["exits"]

    n_trials = int(ctx.get("n_trials", 1))
    excess = (book - bench).dropna()
    out["grade"] = {
        "market_model": ev.get("market_model"),
        "deflated_sharpe": V.deflated_sharpe_from_returns(
            excess.to_numpy(), n_trials=n_trials,
            trial_sharpes=ctx.get("trial_sharpes")),
        "n_effective": V.n_effective_date_blocks(list(book.index)),
        "objective_value": _objective_value(objective, ev),
    }
    return out


def _objective_value(objective: Objective, ev: Mapping[str, Any]) -> dict:
    """The one number the book is RANKED by, named with its ruler."""
    book = ev.get("book") or {}
    mm = ev.get("market_model") or {}
    if objective.name == "alpha_intercept":
        return {"ruler": "alpha_intercept",
                "value": mm.get("intercept_annualised_pct"),
                "t": mm.get("intercept_t_hac"),
                "units": "%/yr, HAC t beside it"}
    if objective.name == "terminal_wealth_at_drawdown_budget":
        adm = ev.get("largest_admissible") or {}
        return {"ruler": "terminal_wealth_at_drawdown_budget",
                "value": adm.get("terminal_wealth"),
                "leverage": adm.get("leverage"),
                "budget_maxdd": adm.get("budget_maxdd"),
                "units": "terminal wealth of the largest admissible book"}
    if objective.name == "sharpe":
        m = V.moments(list(ev.get("_returns", []))) if ev.get("_returns") else {}
        return {"ruler": "sharpe", "value": m.get("sharpe_per_observation"),
                "units": "per observation, NOT annualised"}
    return {"ruler": objective.name, "value": None,
            "units": f"{V.CANNOT_DETERMINE} (no extractor for this ruler)"}


def _slice(s: pd.Series, window: Window) -> pd.Series:
    idx = pd.Index([str(x) for x in s.index])
    out = s[(idx >= window.start) & (idx <= window.end)]
    out.index = [str(x) for x in out.index]
    return out


__all__ = ["run_one", "register_engine", "engines", "SealedWindowRefused",
           "EngineNotRegistered", "RECEIPT_SCHEMA"]
