"""
Investment Committee — graceful degradation (NIGHT-13 ruling, §2)
=================================================================

Adopted ruling: when evidence cannot fill a book, the answer is a low-cost
benchmark core plus evidence-scaled tilts — **never an empty page, never a
refusal**. The archetype factory's refusals stay exactly what they are
(findings about the evidence), but they are CAUGHT here and become the printed
reason the tilts are small, instead of propagating into an empty product.

Three layers, three contracts
-----------------------------

* :func:`build_page` — the strict page the CLI script has always printed. It
  RAISES when the ranking gate is dirty, exactly as before: a page that cannot
  prove its own ranking is clean does not print. Promoted here from
  ``scripts/investment_committee.py`` so the API and the CLI share one build.
* :func:`funnel_state` — the degrading wrapper the composer feeds on. A missing
  funnel file, a void ranking gate, a refused archetype: each becomes a
  ``degradation_reasons`` entry, never an exception. Cached (config TTL) because
  the funnel is a nightly artifact.
* :func:`compose_book` — benchmark core + evidence-scaled tilts, per capital
  level. NEVER returns an empty book: with zero eligible candidates the book is
  100% core and says why. Composition is computed per request (it is cheap and
  capital-dependent); only the funnel-derived state is cached.

Every position carries ``source`` ("evidence-led" | "benchmark-core") and a
``reason`` string, and the wealth block always prints the ruin number beside
the dream number.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend import config
from backend.cache import cache_get, cache_set
from backend.services import capital_frontier as CF
from backend.services import kill_conditions
from backend.services import pm_actions
from backend.services import portfolio_factory as PF
from backend.services import recommendation as REC
from backend.services import signal_registry as SR

logger = logging.getLogger(__name__)

#: The adopted framing, verbatim on every committee page.
CORE_AND_TILTS_SENTENCE = (
    "A market portfolio with cost discipline already beats most investors "
    "net; the tilts are small because the evidence is small.")

DEGRADATION_NO_FUNNEL = "no funnel run available"


def _kill_condition(rec: Any) -> tuple[str, str]:
    """A kill condition tied to the signal that actually decided the rank.

    NIGHT-13 §0 ruling: proposed kill conditions AUTO-ADOPT as active defaults
    instead of parking as PROPOSED_AWAITING_MURAT — honestly labelled, override
    always available. Thesis labels only; nothing executes them (CANON §15).
    The five recovered book names use the shared adopted texts.
    """
    adopted = kill_conditions.default_for(getattr(rec, "ticker", ""))
    if adopted:
        return adopted, "ACTIVE_DEFAULT"
    lead = rec.leader()
    if lead is None:
        return "", "NONE_SET"
    if lead.signal_id == "profitability_small":
        return (f"gross profitability falls below the small-cap cross-sectional "
                f"median for two consecutive quarters (currently "
                f"{lead.raw_value:.2f})"), "ACTIVE_DEFAULT"
    if lead.signal_id.startswith("insider"):
        return ("the insiders who bought sell any part of the stake, or two "
                "quarters pass with no further open-market purchase"), \
            "ACTIVE_DEFAULT"
    return (f"{lead.signal_id} reverses sign and holds there for one quarter"), \
        "ACTIVE_DEFAULT"


def _risk_factors(rec: Any, cand: dict) -> list[str]:
    out = []
    vol = cand.get("vol_annual")
    if vol:
        out.append(f"annualised volatility {100*vol:.0f}%")
    mc = rec.market_cap
    if mc and mc < 2e9:
        out.append("small cap — thinner liquidity, wider spreads, higher "
                   "delisting and dilution risk")
    if rec.confidence in ("LOW", "NONE"):
        out.append(f"confidence {rec.confidence}: only "
                   f"{sum(1 for c in rec.signal_contributions if c.rank_bearing and c.available)} "
                   f"licensed signal(s) speak to this name")
    for c in rec.signal_contributions:
        if c.role == "CLOSED" and c.available and c.signal_id.startswith("analyst"):
            out.append(f"analyst implied upside {100*(c.raw_value or 0):+.0f}% is "
                       f"recorded but NOT used — it is PERVERSE as a picker")
    return out


def build_page(funnel_path: Path) -> dict:
    """The strict committee page. RAISES on a dirty ranking gate.

    This is the CLI contract, unchanged: `assert_registry_discipline` raising
    stops the page from printing at all. The API path uses `funnel_state`,
    which catches that raise into a degradation reason instead.
    """
    payload = json.loads(Path(funnel_path).read_text(encoding="utf-8"))
    cands = payload["candidates"]
    reg = SR.load()

    gate = REC.assert_registry_discipline(cands, registry=reg)
    recs = REC.score_candidates(cands, registry=reg)
    by_ticker = {c["ticker"]: c for c in cands}

    vols = {c["ticker"]: c.get("vol_annual") for c in cands
            if c.get("vol_annual")}
    books = PF.build_all(recs, vols=vols)

    opportunities = []
    for r in recs:
        cand = by_ticker.get(r.ticker, {})
        kill, kill_status = _kill_condition(r)
        r.kill_condition, r.kill_condition_status = kill, kill_status
        r.risk_factors = _risk_factors(r, cand)
        d = r.to_dict()
        d["median_dollar_vol"] = cand.get("median_dollar_vol")
        d["vol_annual"] = cand.get("vol_annual")
        d["why"] = cand.get("why", [])
        d["capacity"] = [
            row.to_dict() for row in CF.capacity_for(
                weight=(books["built"].get("OPTIMUS_BALANCED", {})
                        .get("weights", {}).get(r.ticker, 0.0)),
                median_dollar_vol=cand.get("median_dollar_vol"))
        ]
        opportunities.append(d)

    frontiers = {}
    for name, book in books["built"].items():
        frontiers[name] = CF.frontier(cands, book["weights"])

    licensed = [o for o in opportunities if o["evidence_grade"] != "NO_EVIDENCE"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_funnel": str(funnel_path),
        "funnel_generated_at": payload.get("generated_at"),
        "universe_screened": (payload.get("universe") or {}).get("screened"),
        "registry_gate": {"status": gate["status"],
                          "invariance_checks": gate["invariance_checks"],
                          "violations": gate["violations"]},
        "n_candidates": len(recs),
        "n_with_licensed_evidence": len(licensed),
        "opportunities": opportunities,
        "books": books,
        "capital_frontier": frontiers,
        "evidence_basis": payload.get("evidence_basis"),
        "honesty": {
            "expected_return": (
                "NOT CALIBRATED for any name. The permitted pickers are graded "
                "SUPPORTED, not VALIDATED, and no map from picker composite to "
                "a 12-month expected return exists in this programme. The page "
                "reports an ordering and its percentile, and refuses to print a "
                "return it cannot defend."),
            "capacity": CF.frontier(cands, {}).get("impact_caveat"),
            "kill_conditions": (
                "ACTIVE_DEFAULT (NIGHT-13 §0). Kill conditions auto-adopt as "
                "defaults — thesis labels for paper/shadow evaluation, "
                "overridable by Murat at any time; none is armed."),
            "no_trade": ("Paper only. No lane seeded, no flag flipped, no "
                         "order path touched."),
        },
    }


# ───────────────────────── degrading funnel state ────────────────────────────

def _empty_state(reasons: list[str]) -> dict:
    return {
        "available": False,
        "gate": {"status": "UNAVAILABLE"},
        "recs": [],
        "candidates": {},
        "books": {"built": {}, "refused": {}},
        "universe_screened": None,
        "funnel_generated_at": None,
        "evidence_basis": None,
        "degradation_reasons": list(reasons),
    }


def _compute_funnel_state(path: Path) -> dict:
    if not path.exists():
        logger.warning("IC funnel missing at %s — degrading to pure core", path)
        return _empty_state([DEGRADATION_NO_FUNNEL])

    payload = json.loads(path.read_text(encoding="utf-8"))
    cands = payload["candidates"]
    by_ticker = {c["ticker"]: c for c in cands}
    reg = SR.load()
    degradation: list[str] = []

    try:
        gate = {"status": "CLEAN",
                **{k: v for k, v in
                   REC.assert_registry_discipline(cands, registry=reg).items()
                   if k in ("invariance_checks", "violations")}}
    except REC.RankLeadershipError as exc:
        # The gate holds: a void ranking licenses NO tilts. The core still
        # prints — that is the whole ruling.
        logger.error("IC ranking gate VOID: %s", exc)
        state = _empty_state([f"ranking gate VOID — no tilts licensed: {exc}"])
        state.update(available=True, gate={"status": "VOID", "error": str(exc)},
                     universe_screened=(payload.get("universe") or {}).get("screened"),
                     funnel_generated_at=payload.get("generated_at"),
                     evidence_basis=payload.get("evidence_basis"))
        return state

    recs = REC.score_candidates(cands, registry=reg)
    vols = {c["ticker"]: c.get("vol_annual") for c in cands
            if c.get("vol_annual")}
    try:
        books = PF.build_all(recs, vols=vols)
    except PF.ArchetypeRefused as exc:  # build_all catches per-archetype; belt+braces
        books = {"built": {}, "refused": {"ALL_ARCHETYPES": str(exc)}}
    for name, why in (books.get("refused") or {}).items():
        degradation.append(f"{name} REFUSED: {why}")

    return {
        "available": True,
        "gate": gate,
        "recs": recs,
        "candidates": by_ticker,
        "books": books,
        "universe_screened": (payload.get("universe") or {}).get("screened"),
        "funnel_generated_at": payload.get("generated_at"),
        "evidence_basis": payload.get("evidence_basis"),
        "degradation_reasons": degradation,
    }


def ic_health(funnel_path: Optional[Path] = None) -> dict:
    """Cheap health row for /api/health/full — file presence, never compute.

    The funnel artifact ships in the image (backend/data); if it is absent in
    prod the page degrades to pure benchmark core on every request while local
    tests stay green — that state must be visible on the health surface, not
    only inside the page payload (NIGHT-13 audit F1).
    """
    path = Path(funnel_path or config.IC_FUNNEL_PATH)
    row: dict = {"funnel_available": path.exists(), "funnel_path": str(path)}
    if row["funnel_available"]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            row["funnel_generated_at"] = payload.get("generated_at")
            row["status"] = "ok"
        except Exception as e:
            row["status"] = "DEGRADED"
            row["error"] = f"funnel unreadable: {e}"
    else:
        row["status"] = "DEGRADED"
        row["error"] = DEGRADATION_NO_FUNNEL
    return row


def funnel_state(funnel_path: Optional[Path] = None,
                 *, use_cache: bool = True) -> dict:
    """Funnel-derived inputs (gate, ranking, archetype books), cached 1h."""
    path = Path(funnel_path or config.IC_FUNNEL_PATH)
    key = f"ic:funnel_state:{path}"
    if use_cache:
        hit = cache_get(key, config.IC_FUNNEL_TTL)
        if hit is not None:
            return hit
    state = _compute_funnel_state(path)
    # A forced refresh (use_cache=False) still WRITES: recomputing and then
    # serving the next caller the stale entry would make refresh a no-op.
    cache_set(key, state)
    return state


# ───────────────────────────── the composer ──────────────────────────────────

def _tilt_size(rec: Any) -> float:
    """Evidence-scaled tilt: cap x verdict scale x confidence scale."""
    v = config.IC_TILT_VERDICT_SCALE.get(rec.recommendation, 0.0)
    c = config.IC_TILT_CONFIDENCE_SCALE.get(rec.confidence, 0.0)
    return config.IC_SINGLE_NAME_TILT_CAP * v * c


def compose_book(recs: list[Any], *, capital: float,
                 candidates: Optional[dict[str, dict]] = None,
                 refusal_reasons: Optional[dict[str, str]] = None,
                 extra_degradation: Optional[list[str]] = None,
                 template_name: Optional[str] = None) -> dict:
    """Benchmark core + evidence-scaled tilts at one capital level.

    NEVER returns an empty book. `ArchetypeRefused` cannot escape: refusal
    strings arrive as `refusal_reasons` (or are caught here) and become the
    printed reason the tilts are small.
    """
    # Imported here, not at module top: portfolio_engine drags in the GARCH /
    # MC stack, which the strict CLI path never needs.
    from backend.services.portfolio_engine import _ALLOCATION_TEMPLATES

    tname = template_name or config.IC_BENCHMARK_TEMPLATE
    template = _ALLOCATION_TEMPLATES.get(tname) or _ALLOCATION_TEMPLATES["moderate"]
    candidates = candidates or {}
    degradation: list[str] = list(extra_degradation or [])
    for name, why in (refusal_reasons or {}).items():
        line = f"{name} REFUSED: {why}"
        if line not in degradation:
            degradation.append(line)

    # 1. eligible tilts: BUY/WATCH verdict, licensed evidence, positive score.
    eligible = []
    try:
        for r in recs or []:
            if (getattr(r, "recommendation", "") in config.IC_TILT_VERDICT_SCALE
                    and getattr(r, "evidence_grade", "NO_EVIDENCE") != "NO_EVIDENCE"
                    and getattr(r, "ranking_score", 0.0) > 0):
                eligible.append(r)
    except PF.ArchetypeRefused as exc:  # defensive: recs may be lazily built
        degradation.append(f"tilt selection refused: {exc}")
    eligible.sort(key=lambda r: (r.rank, -r.ranking_score))
    eligible = eligible[:config.IC_MAX_TILT_NAMES]

    tilts: dict[str, float] = {}
    tilt_meta: dict[str, dict] = {}
    for r in eligible:
        w = _tilt_size(r)
        if w <= 0:
            continue
        cand = candidates.get(r.ticker, {})
        price = cand.get("price") or r.price
        mdv = cand.get("median_dollar_vol")

        # Capacity check at THIS capital: a blocked tilt returns to the core.
        cap_row = CF.capacity_for(weight=w, median_dollar_vol=mdv,
                                  capital_levels=[capital])[0]
        if mdv and not cap_row.tradeable:
            degradation.append(
                f"{r.ticker}: {w:.1%} tilt is untradeable at "
                f"${capital:,.0f} ({cap_row.binding_constraint}) — weight "
                f"returned to the core")
            continue
        # A tilt that cannot buy one share is not a position at this capital.
        if price and w * capital < price:
            degradation.append(
                f"{r.ticker}: {w:.1%} tilt (${w * capital:,.0f}) is below one "
                f"share (${price:,.2f}) at ${capital:,.0f} — weight returned "
                f"to the core")
            continue
        tilts[r.ticker] = w
        tilt_meta[r.ticker] = {"rec": r, "price": price, "mdv": mdv,
                               "capacity": cap_row.to_dict()}

    # 2. total-budget cap: scale all tilts down proportionally, never up.
    total = sum(tilts.values())
    if total > config.IC_TOTAL_TILT_BUDGET:
        f = config.IC_TOTAL_TILT_BUDGET / total
        tilts = {t: w * f for t, w in tilts.items()}
        total = config.IC_TOTAL_TILT_BUDGET
        degradation.append(
            f"evidence tilts scaled by x{f:.2f} to the "
            f"{config.IC_TOTAL_TILT_BUDGET:.0%} total tilt budget")

    if not tilts:
        degradation.append(
            "no candidate clears the tilt gate (BUY/WATCH verdict + licensed "
            "evidence + tradeable at this capital) — the book is 100% "
            "benchmark core")

    # 3. the book: core scaled to fund the tilts, tilts on top. Never empty —
    #    the template is a constant and total < 1 by construction.
    core_scale = 1.0 - total
    positions: list[dict] = []
    for etf, tw in template["allocations"].items():
        w = tw * core_scale
        positions.append({
            "ticker": etf,
            "weight": round(w, 6),
            "dollars": round(w * capital, 2),
            "shares": None,   # no offline ETF price; dollar amount is the instruction
            "price": None,
            "source": "benchmark-core",
            "reason": (f"low-cost benchmark core: {tw:.0%} of the '{tname}' "
                       f"template"
                       + (f", scaled x{core_scale:.3f} to fund the evidence "
                          f"tilts" if total > 0 else "")),
            "capacity": {"checked": False,
                         "note": "broad-market ETF — no funnel volume reading; "
                                 "capacity is not the binding constraint at "
                                 "these capital levels"},
        })
    for t, w in tilts.items():
        m = tilt_meta[t]
        r = m["rec"]
        price = m["price"]
        shares = math.floor(w * capital / price) if price else None
        positions.append({
            "ticker": t,
            "weight": round(w, 6),
            "dollars": round(w * capital, 2),
            "shares": shares,
            "price": price,
            "source": "evidence-led",
            "reason": (f"{r.recommendation}/{r.confidence}/{r.evidence_grade}: "
                       f"{r.reason_for_rank or 'licensed evidence'}; tilt "
                       f"capped at {config.IC_SINGLE_NAME_TILT_CAP:.0%} per "
                       f"name"),
            "capacity": m["capacity"],
        })

    wealth = _wealth(positions, capital, candidates)
    return {
        "capital": capital,
        "template": tname,
        "template_description": template["description"],
        "n_positions": len(positions),
        "core_weight": round(core_scale, 6),
        "tilt_weight": round(total, 6),
        "positions": positions,
        "degradation_reasons": degradation,
        "wealth": wealth,
    }


def _wealth(positions: list[dict], capital: float,
            candidates: dict[str, dict]) -> dict:
    """Ruin beside dream for the composed book, via pm_actions.simulate_wealth.

    Assumptions are config-driven and printed: core ETFs get consensus-style
    mu/vol; evidence tilts get the equity-core drift and their OWN volatility —
    the pickers are an ordering, not a magnitude, so no tilt earns extra drift.
    """
    rows = []
    for p in positions:
        if p["source"] == "benchmark-core":
            a = config.IC_CORE_ASSUMPTIONS.get(p["ticker"])
            if a is None:
                a = {"mu": config.IC_TILT_ASSUMED_RETURN,
                     "vol": config.IC_TILT_FALLBACK_VOL}
        else:
            cand = candidates.get(p["ticker"], {})
            a = {"mu": config.IC_TILT_ASSUMED_RETURN,
                 "vol": cand.get("vol_annual") or config.IC_TILT_FALLBACK_VOL}
        rows.append({
            "ticker": p["ticker"],
            "proposed": {"target_weight": p["weight"]},
            "distribution": {"available": True,
                             "expected_return": a["mu"],
                             "annual_vol": a["vol"]},
        })
    targets = {
        "horizon_months": config.IC_WEALTH_HORIZON_MONTHS,
        "target_value": capital * config.IC_WEALTH_TARGET_MULT,
        "floor_value": capital * config.IC_WEALTH_FLOOR_MULT,
        "ruin_value": capital * config.IC_WEALTH_RUIN_MULT,
    }
    sim = pm_actions.simulate_wealth(rows, nav=capital, cash=0.0,
                                     targets=targets, n=config.IC_WEALTH_DRAWS)
    sim["targets"] = targets
    sim["assumption_note"] = (
        "core ETF mu/vol are config-driven consensus-style scenario inputs "
        "(IC_CORE_ASSUMPTIONS), not engine forecasts; evidence tilts get the "
        "equity-core drift and their own volatility — the licensed pickers "
        "are an ordering, not a magnitude, so no tilt earns extra drift. "
        f"Dream = P(reach {config.IC_WEALTH_TARGET_MULT:.1f}x in "
        f"{config.IC_WEALTH_HORIZON_MONTHS}mo); ruin = P(end below "
        f"{config.IC_WEALTH_RUIN_MULT:.0%} of start). Read them together, "
        "never apart.")
    return sim


# ───────────────────────────── the full page ─────────────────────────────────

def committee(capital: Optional[float] = None,
              *, funnel_path: Optional[Path] = None,
              use_cache: bool = True) -> dict:
    """The committee page for one capital level, or all configured levels."""
    state = funnel_state(funnel_path, use_cache=use_cache)
    levels = ([float(capital)] if capital is not None
              else [float(c) for c in config.IC_CAPITAL_LEVELS])

    recs = state.get("recs") or []
    licensed = [r for r in recs if r.evidence_grade != "NO_EVIDENCE"]
    books = {}
    for lvl in levels:
        books[f"{int(lvl)}"] = compose_book(
            recs, capital=lvl,
            candidates=state.get("candidates") or {},
            refusal_reasons=(state.get("books") or {}).get("refused") or {},
            extra_degradation=[d for d in state.get("degradation_reasons") or []
                               if "REFUSED" not in d])

    # page-level degradation = union across books (order-preserving)
    page_degradation: list[str] = []
    for b in books.values():
        for d in b["degradation_reasons"]:
            if d not in page_degradation:
                page_degradation.append(d)

    opportunities = []
    for r in licensed[:25]:
        cand = (state.get("candidates") or {}).get(r.ticker, {})
        kill, kill_status = _kill_condition(r)
        r.kill_condition, r.kill_condition_status = kill, kill_status
        r.risk_factors = _risk_factors(r, cand)
        d = r.to_dict()
        d["vol_annual"] = cand.get("vol_annual")
        d["median_dollar_vol"] = cand.get("median_dollar_vol")
        opportunities.append(d)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "funnel_available": bool(state.get("available")),
        "funnel_generated_at": state.get("funnel_generated_at"),
        "universe_screened": state.get("universe_screened"),
        "registry_gate": state.get("gate"),
        "ranking_summary": {
            "n_candidates": len(recs),
            "n_with_licensed_evidence": len(licensed),
            "n_buy": sum(1 for r in recs if r.recommendation == "BUY"),
            "n_watch": sum(1 for r in recs if r.recommendation == "WATCH"),
        },
        "top_opportunities": opportunities,
        "books": books,
        "degradation_reasons": page_degradation,
        "evidence_basis": state.get("evidence_basis"),
        "honesty": {
            "core_and_tilts": CORE_AND_TILTS_SENTENCE,
            "expected_return": (
                "NOT CALIBRATED for any tilt name. The permitted pickers are "
                "SUPPORTED, not VALIDATED; the page reports an ordering and "
                "refuses to print a per-name return it cannot defend. The "
                "wealth numbers below rest on config-declared scenario "
                "assumptions, not engine forecasts."),
            "capacity": ("DELAY-ONLY LOWER BOUND — the programme's cost model "
                         "cannot price market impact (CANON §17)."),
            "kill_conditions": (
                "ACTIVE_DEFAULT (NIGHT-13 §0). Kill conditions auto-adopt as "
                "defaults — thesis labels for paper/shadow evaluation, "
                "overridable by Murat at any time; none is armed."),
            "no_trade": ("Paper only. No lane seeded, no flag flipped, no "
                         "order path touched."),
            "ruin_beside_dream": (
                "every book prints P(reach target) BESIDE P(ruin); reading "
                "one without the other is the failure mode this page exists "
                "to prevent."),
        },
    }
