"""One arena pass per session: fill, mark, decide, record, mature.

Order of operations per book (all against the frozen day state):
  1. fill orders queued at the PREVIOUS decision, at TODAY's open (+costs);
  2. mark the book at today's close → nav.jsonl;
  3. if a decision is due (first run, or new calendar month, or a daily
     substitution for books that declare one): select → screen → size →
     winner-exemption → LLM tilt → queue orders for the NEXT session;
  4. write decisions + EXPERIENCE records (chosen AND rejected);
  5. receipt.
Then one namespace-level maturation pass resolves every experience whose
horizon has closed. Idempotent per session: a book already marked for the
day is skipped, and the frozen snapshot refuses to change content.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from backend.services.arena import (
    beliefs, discovery, experience, policies, reliability, trackers,
)
from backend.services.arena import spec as spec_mod
from backend.services.arena import store

logger = logging.getLogger(__name__)

RULES_MODEL_ID = "arena_rules@v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _init_positions(spec) -> dict:
    return {"cash": spec.notional_usd, "positions": {}, "pending": [],
            "session_index": 0, "last_rebalance_month": None,
            "last_marked": None}


def _fill_pending(book: dict, panel, day: date, spec) -> list[dict]:
    """Fill queued orders at today's open. Unpriceable fills are dropped WITH
    a receipt row — a queued order that silently evaporates is the house
    failure mode."""
    fills = []
    rate = (spec.cost_bps + spec.slippage_bps) / 10_000.0
    for o in book.get("pending", []):
        px = panel.open_price(o["ticker"], day)
        row = dict(o)
        row["fill_date"] = str(day)
        if px is None:
            row["status"] = "dropped_no_open_price"
            fills.append(row)
            continue
        usd = o["usd"]
        cost = usd * rate
        pos = book["positions"].setdefault(
            o["ticker"], {"shares": 0.0, "cost_basis": px,
                          "opened_session": book["session_index"],
                          "exempt_since_session": None, "last_px": px})
        if o["side"] == "buy":
            shares = usd / px
            old_sh = pos["shares"]
            pos["cost_basis"] = ((pos["cost_basis"] * old_sh + px * shares)
                                 / (old_sh + shares)) if old_sh + shares else px
            pos["shares"] = old_sh + shares
            book["cash"] -= usd + cost
        else:
            shares = min(usd / px, pos["shares"])
            pos["shares"] -= shares
            book["cash"] += shares * px - cost
            if pos["shares"] * px < 1.0:
                del book["positions"][o["ticker"]]
        row.update(status="filled", fill_price=px, cost_usd=round(cost, 4))
        fills.append(row)
    book["pending"] = []
    return fills


def _mark(book: dict, panel, day: date) -> tuple[float, int]:
    """Cash + positions at today's close; a missing price carries the last
    known price and is counted stale, never dropped."""
    total = book["cash"]
    stale = 0
    for t, pos in book["positions"].items():
        px = panel.close_price(t, day)
        if px is None:
            px = pos.get("last_px") or pos["cost_basis"]
            stale += 1
        else:
            pos["last_px"] = px
        total += pos["shares"] * px
    return total, stale


def _decision_due(book: dict, day: date) -> str | None:
    if not book["positions"] and not book.get("pending"):
        return "initial_build"
    lrm = book.get("last_rebalance_month")
    if lrm != f"{day.year}-{day.month:02d}":
        return "monthly_rebalance"
    return None


def _select(spec, day_state: dict) -> policies.Selection:
    return policies.select(day_state, top_k=spec.top_k,
                           min_price=spec.min_price, screens=spec.screens,
                           signal=spec.selection_signal)


def _decide(spec, book: dict, day_state: dict, is_hash: str, *,
            llm_tilts: dict | None = None, sel=None, root=None) -> dict:
    """Compute targets and queue orders. Returns the decision receipt.

    `llm_tilts` arrive already computed by the DAILY belief review — this
    function no longer calls an LLM. That separation is the point: the review
    runs on every session and the decision runs on ~1 in 20, so binding them
    together is what made the model's only look at a name the same call that
    traded it.
    """
    # A degraded fetch is not a thin day. Cross-sectional z-scores computed
    # over 20 of 180 names are correct arithmetic against the wrong world, and
    # `insufficient_breadth` would not catch it — 20 priced names still yield
    # 12 chosen. The book HOLDS and says why; the snapshot stays frozen as the
    # record of what was actually fetched.
    priced = day_state.get("priced_fraction")
    floor = spec.min_priced_fraction
    if priced is not None and priced < floor:
        return {"status": "degraded_information_state",
                "priced_fraction": priced, "min_priced_fraction": floor,
                "priced_n": day_state.get("priced_n"),
                "universe_n": day_state.get("universe_n"),
                "note": ("the cross-section this state's z-scores were "
                         "computed over is not the declared universe — "
                         "holding rather than ranking a different world")}

    sel = sel if sel is not None else _select(spec, day_state)
    min_breadth = max(5, spec.top_k // 2)
    if len(sel.chosen) < min_breadth:
        # The rehearsal case: a thin PIT store scored 1 of 180 names and every
        # book would have concentrated 100% into it. A selection too narrow to
        # diversify is a data problem wearing a portfolio's clothes — hold,
        # and say so loudly.
        return {"status": "insufficient_breadth",
                "chosen_n": len(sel.chosen), "min_breadth": min_breadth,
                "excluded_n": len(sel.excluded),
                "note": "selection too narrow — book holds; loud, not silent"}
    weights = policies.size(sel.chosen, day_state, sizing=spec.sizing,
                            max_single_name=spec.max_single_name)
    exemption_receipts: list[dict] = []
    if spec.winner_exemption:
        weights, exemption_receipts = policies.apply_winner_exemption(
            weights, book, day_state, book["session_index"],
            gain_threshold_pct=float(
                spec.winner_exemption.get("gain_threshold_pct", 40.0)),
            exempt_trading_days=int(
                spec.winner_exemption.get("exempt_trading_days", 60)))
    tilts = {t: f for t, f in (llm_tilts or {}).items() if t in weights}
    if tilts:
        weights = policies.apply_llm_tilts(
            weights, tilts,
            tilt_cap=float(spec.llm.get("tilt_cap", 0.20)),
            max_single_name=spec.max_single_name)
    orders = policies.orders_from_targets(
        book, weights, day_state,
        cost_bps=spec.cost_bps, slippage_bps=spec.slippage_bps)
    for o in orders:
        o["decision_date"] = day_state["date"]
        o["information_state_hash"] = is_hash
    book["pending"] = orders
    day = day_state["date"]
    book["last_rebalance_month"] = f"{day[:4]}-{day[5:7]}"
    return {"status": "decided", "selection": sel, "weights": weights,
            "orders_queued": len(orders),
            "llm_tilts": tilts, "exemptions": exemption_receipts}


def _experiences_from_decision(spec, dec: dict, book_before: set[str],
                               day: str, is_hash: str,
                               prediction_ids: dict | None = None
                               ) -> tuple[list[dict], list[dict]]:
    """Decision rows + experience rows, chosen AND rejected."""
    sel: policies.Selection = dec["selection"]
    weights: dict = dec["weights"]
    prediction_ids = prediction_ids or {}
    model_id = RULES_MODEL_ID if not dec.get("llm_tilts") else (
        RULES_MODEL_ID + "+llm_tilt")
    decisions, experiences = [], []
    chosen_set = {c["ticker"] for c in sel.chosen}
    top_pick = sel.chosen[0]["ticker"] if sel.chosen else None
    for c in sel.chosen:
        t = c["ticker"]
        action = "HOLD" if t in book_before else "ENTER"
        thesis = (f"rank {c['rank']}/{spec.top_k} on "
                  f"{spec.selection_signal} ({c['score']:.3f}); "
                  f"sizing={spec.sizing}; screens={list(spec.screens)}")
        conf = max(0.0, 1.0 - (c["rank"] - 1) / max(spec.top_k, 1))
        rec = experience.make_experience(
            book_id=spec.book_id, policy_version=spec.policy_version,
            ticker=t, action=action, decision_date=day,
            information_state_hash=is_hash, model_id=model_id,
            thesis=thesis, confidence=conf,
            invalidation="drops below rank cutoff at next rebalance",
            weight=weights.get(t), rank=c["rank"], score=c["score"],
            llm_prediction_id=prediction_ids.get(t))
        experiences.append(rec)
        decisions.append({"date": day, "ticker": t, "action": action,
                          "rank": c["rank"], "score": c["score"],
                          "weight": weights.get(t),
                          "information_state_hash": is_hash,
                          "experience_id": rec["experience_id"]})
    for t in sorted(book_before - chosen_set):
        rec = experience.make_experience(
            book_id=spec.book_id, policy_version=spec.policy_version,
            ticker=t, action="EXIT", decision_date=day,
            information_state_hash=is_hash, model_id=model_id,
            thesis="fell out of selection at rebalance", confidence=None,
            invalidation="")
        experiences.append(rec)
        decisions.append({"date": day, "ticker": t, "action": "EXIT",
                          "information_state_hash": is_hash,
                          "experience_id": rec["experience_id"]})
    for r in sel.rejected:
        rec = experience.make_experience(
            book_id=spec.book_id, policy_version=spec.policy_version,
            ticker=r["ticker"], action="REJECT", decision_date=day,
            information_state_hash=is_hash, model_id=model_id,
            thesis=f"rank {r['rank']} — {r['reason']}",
            confidence=None, invalidation="",
            score=r["score"], rank=r["rank"],
            chosen_alternative=top_pick)
        experiences.append(rec)
        decisions.append({"date": day, "ticker": r["ticker"],
                          "action": "REJECT", "rank": r["rank"],
                          "information_state_hash": is_hash,
                          "experience_id": rec["experience_id"]})
    return decisions, experiences


def run_book(spec, panel, day: date, day_state: dict, is_hash: str, *,
             root=None) -> dict:
    seed = store.assert_config_current(spec, root=root)
    book = store.read_positions(spec.book_id, root) or _init_positions(spec)
    receipt: dict = {"book_id": spec.book_id, "run_at": _now(),
                     "session": str(day), "config_hash": spec.config_hash,
                     "policy_fingerprint": spec.policy_fingerprint,
                     "composite_version": day_state.get("composite_version"),
                     "coverage_histogram": day_state.get("coverage_histogram"),
                     "policy_version": spec.policy_version,
                     "validation_status": spec.validation_status,
                     "simulation": True, "seeded_at": seed["seeded_at"]}
    if book.get("last_marked") == str(day):
        receipt["status"] = "already_marked"
        return receipt

    fills = _fill_pending(book, panel, day, spec)
    if fills:
        store.append_orders(spec.book_id, fills, root)
    nav, stale = _mark(book, panel, day)
    book["session_index"] = int(book.get("session_index", 0)) + 1
    book["last_marked"] = str(day)
    if spec.winner_exemption:
        thr = float(spec.winner_exemption.get("gain_threshold_pct", 40.0))
        for pos in book["positions"].values():
            px, basis = pos.get("last_px"), pos.get("cost_basis")
            if (px and basis and pos.get("exempt_since_session") is None
                    and (px / basis - 1.0) * 100.0 >= thr):
                pos["exempt_since_session"] = book["session_index"]
    store.append_nav(spec.book_id, [{
        "date": str(day), "nav": round(nav, 2), "stale_positions": stale,
        "config_version": spec.config_version, "config_hash": spec.config_hash,
        "policy_version": spec.policy_version,
        "benchmark_close": panel.close_price(spec.benchmark, day),
        "computed_at": _now(), "simulation": True,
    }], root)

    book_before = set(book["positions"].keys())
    due = _decision_due(book, day)

    # ── the DAILY belief review: every session, decision or not ─────────────
    # Thinking daily and trading daily are different things, and only the
    # second one costs money. Before this, the LLM's only look at a name was
    # the call that also traded it — roughly one session in twenty — and it
    # supplied its own prior in that same call.
    sel = _select(spec, day_state)
    review = {"status": "disabled", "tilts": {}}
    if spec.llm_perception:
        try:
            review = beliefs.daily_review(
                day_state, book_id=spec.book_id, holdings=book_before,
                challengers=[c["ticker"] for c in sel.chosen],
                llm_cfg=spec.llm, root=root)
        except Exception as exc:  # noqa: BLE001 — review never kills the book
            logger.exception("ARENA: belief review failed for %s", spec.book_id)
            review = {"status": f"error: {type(exc).__name__}: {exc}",
                      "tilts": {}}
    receipt["belief_review"] = {k: v for k, v in review.items()
                                if k != "tilts"}
    prediction_ids = {r["ticker"]: r.get("prediction_id")
                      for r in review.get("reviewed", [])
                      if isinstance(r, dict)}

    substitution = None
    if due:
        dec = _decide(spec, book, day_state, is_hash, sel=sel,
                      llm_tilts=review.get("tilts"), root=root)
        receipt["decision"] = {k: v for k, v in dec.items()
                               if k not in ("selection", "weights")}
        receipt["decision_reason"] = due
        if dec["status"] == "decided":
            decisions, experiences = _experiences_from_decision(
                spec, dec, book_before, str(day), is_hash, prediction_ids)
            store.append_decisions(spec.book_id, decisions, root)
            store.append_experiences(experiences, root)
            receipt["experiences_written"] = len(experiences)
    elif spec.substitution:
        rate = 2 * (spec.cost_bps + spec.slippage_bps) / 10_000.0
        substitution = policies.substitution_check(
            book, sel, day_state,
            margin_z=float(spec.substitution.get("margin_z", 0.5)),
            round_trip_cost=rate, signal=spec.selection_signal)
        if substitution:
            names = day_state.get("names", {})
            sell_t, buy_t = substitution["sell"], substitution["buy"]
            sell_px = names.get(sell_t, {}).get("close")
            pos = book["positions"].get(sell_t, {})
            usd = (pos.get("shares", 0.0) * sell_px) if sell_px else 0.0
            if usd > 0:
                book["pending"] = [
                    {"ticker": sell_t, "side": "sell", "usd": round(usd, 2),
                     "decision_close": sell_px, "cost_bps": spec.cost_bps,
                     "slippage_bps": spec.slippage_bps, "status": "queued",
                     "decision_date": str(day),
                     "information_state_hash": is_hash,
                     "reason": "substitution"},
                    {"ticker": buy_t, "side": "buy", "usd": round(usd, 2),
                     "decision_close": names.get(buy_t, {}).get("close"),
                     "cost_bps": spec.cost_bps,
                     "slippage_bps": spec.slippage_bps, "status": "queued",
                     "decision_date": str(day),
                     "information_state_hash": is_hash,
                     "reason": "substitution"},
                ]
                swap_rows = []
                for tkr, action in ((buy_t, "SWAP_IN"), (sell_t, "SWAP_OUT")):
                    rec = experience.make_experience(
                        book_id=spec.book_id,
                        policy_version=spec.policy_version, ticker=tkr,
                        action=action, decision_date=str(day),
                        information_state_hash=is_hash,
                        model_id=RULES_MODEL_ID,
                        thesis=(f"substitution: {buy_t} beats weakest holding "
                                f"{sell_t} by {substitution['score_gap']}σ"),
                        invalidation="score gap closes")
                    swap_rows.append(rec)
                store.append_experiences(swap_rows, root)
                receipt["substitution"] = substitution

    receipt.setdefault("status", "ok")
    receipt["nav"] = round(nav, 2)
    receipt["fills"] = len(fills)
    receipt["open_positions"] = len(book["positions"])
    receipt["pending_orders"] = len(book.get("pending", []))
    store.write_positions(spec.book_id, book, root)
    store.write_receipt(spec.book_id, receipt, root)
    return receipt


def run_daily(as_of=None, *, panel=None, root=None, db_path=None) -> dict:
    """The scheduled entry point: one pass over every seeded arena book."""
    specs = spec_mod.active_specs()
    seeded = {b: s for b, s in specs.items() if store.is_seeded(b, root)}
    summary: dict = {"run_at": _now(), "books_authorised": len(specs),
                     "books_seeded": len(seeded), "receipts": [],
                     "skipped_unseeded": sorted(set(specs) - set(seeded))}
    if not seeded:
        summary["status"] = "no_seeded_books"
        return summary

    held: set[str] = set()
    for b in seeded:
        held.update((store.read_positions(b, root).get("positions")
                     or {}).keys())
    core = discovery.candidate_universe(extra=sorted(held))
    scan_n = max((s.scan_universe_n for s in seeded.values()), default=0)
    scan = discovery.scan_universe(scan_n) if scan_n else []

    if panel is None:
        start = str(date.today() - timedelta(days=430))
        # ONE fetch over core + scan. The scan is the only route by which a
        # name the watchlist never contained can reach a book.
        panel = discovery.ArenaPanel(
            sorted(set(core) | set(scan) | {"QQQ"}), start=start)
    as_of_d = _iso_date(as_of) or date.today()
    sessions = [s for s in panel.sessions() if s <= as_of_d]
    if not sessions:
        summary["status"] = "no_sessions"
        return summary
    day = sessions[-1]
    summary["session"] = str(day)

    # STAGE A — cheap scan over everything, before anything expensive.
    # Observations are CONTEXT and DISCOVERY, never a score (trackers.py).
    try:
        obs = trackers.observe(day, panel, sorted(set(scan) | set(core)))
        noms = trackers.nominations(obs["observations"], core=set(core))
    except Exception as exc:  # noqa: BLE001
        logger.exception("ARENA: tracker scan failed")
        obs = {"scanned_n": 0, "observations": [], "by_kind": {},
               "error": f"{type(exc).__name__}: {exc}"}
        noms = []
    # STAGE B — the core universe PLUS whatever the scan nominated.
    universe = sorted(set(core) | {n["ticker"] for n in noms})
    summary["discovery"] = {
        "core_n": len(core), "scan_n": len(scan),
        "scanned_n": obs.get("scanned_n"), "priced_n": obs.get("priced_n"),
        "observations_n": len(obs.get("observations") or []),
        "by_kind": obs.get("by_kind"),
        "nominated_n": len(noms),
        "nominated": [{"ticker": n["ticker"], "reason": n["reason"]}
                      for n in noms],
        "error": obs.get("error"),
    }

    snap = discovery.freeze_day_state(day, panel, universe,
                                      root=root, db_path=db_path,
                                      core=core, scan=scan,
                                      tracker_block=obs, nominations=noms)
    day_state = snap["state"]
    is_hash = snap["information_state_hash"]
    summary["information_state_hash"] = is_hash
    summary["scored_n"] = day_state.get("scored_n")
    summary["composite_version"] = day_state.get("composite_version")
    # How many names were ranked on how many factors. FEATURE-COVERAGE-AUDIT-1
    # measured the arena ranking ~93% of its universe on 12-1 momentum alone;
    # printing it every pass is what stops that from going quiet again.
    summary["coverage_histogram"] = day_state.get("coverage_histogram")

    for book_id, s in seeded.items():
        try:
            summary["receipts"].append(
                run_book(s, panel, day, day_state, is_hash, root=root))
        except Exception as exc:  # noqa: BLE001 — one book never kills the rest
            logger.exception("ARENA: %s pass failed", book_id)
            summary["receipts"].append({"book_id": book_id,
                                        "status": "error",
                                        "error": f"{type(exc).__name__}: {exc}"})

    try:
        summary["maturation"] = experience.mature_outcomes(
            panel, today=day, root=root)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ARENA: maturation failed")
        summary["maturation"] = {"status": "error",
                                 "error": f"{type(exc).__name__}: {exc}"}

    # Grading the LLM's own forecasts is a SEPARATE step from maturing the
    # rules decisions: they live in different files, answer different
    # questions, and one failing must not silence the other.
    try:
        summary["perception_grading"] = experience.resolve_perceptions(
            panel, today=day, root=root)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ARENA: perception grading failed")
        summary["perception_grading"] = {"status": "error",
                                         "error": f"{type(exc).__name__}: {exc}"}

    try:
        summary["reliability"] = reliability.snapshot(today=day, root=root)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ARENA: reliability snapshot failed")
        summary["reliability"] = {"status": "error",
                                  "error": f"{type(exc).__name__}: {exc}"}
    summary["status"] = "ok"
    return summary


def seed_all(root=None) -> list[dict]:
    """Seed every authorised book (idempotent; refuses moved inceptions)."""
    return [store.seed_book(s, root=root)
            for s in spec_mod.active_specs().values()]


def status(root=None) -> dict:
    specs = spec_mod.active_specs()
    out: dict = {"config_hash": spec_mod.config_hash(), "books": {}}
    for b, s in specs.items():
        seed = store.read_seed(b, root)
        nav = store.read_nav(b, root)
        out["books"][b] = {
            "seeded": seed is not None,
            "seeded_at": (seed or {}).get("seeded_at"),
            "nav_rows": len(nav),
            "last_nav": nav[-1] if nav else None,
            "positions": len((store.read_positions(b, root).get("positions")
                              or {})),
            "validation_status": s.validation_status,
        }
    out["experiences"] = len(store.read_experiences(root))
    out["experience_outcomes"] = len(store.read_outcomes(root))
    return out
