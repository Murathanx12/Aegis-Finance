"""
Aegis Finance — Daily Digest (the brain reads its own day)
==========================================================

Every day the system decides, forecasts, grades, collects, and marks — and
until now the only durable cross-cutting record of "what happened vs what we
thought" was scattered across five stores and a log stream that Railway
rotates away. This module assembles ONE dated record per day from the durable
state on disk and appends it to an append-only corpus.

The corpus is the point. Murat's instruction (2026-08-21): *"if everyday we
logged what happened, what we thought was going to happen, we would have had
so much data + training."* Six months of sessions produced exactly zero rows
of that corpus because no job owned it. This job owns it.

WHAT THIS IS NOT — read before extending
-----------------------------------------
* **Documentation, never a signal.** Nothing in the scoring, decision, or
  allocation path may import this module or read its output. The digest
  OBSERVES the day; the moment a digest field feeds a decision it becomes an
  unregistered feature with no PIT discipline.
* **Not a health check.** /api/health/full already pages on degradation. A
  digest section reading `unavailable` is a fact about the record, not an
  alarm to route.
* **Derived from DISK, not from job return values.** A summary a job logged
  and a state a job left behind are two different claims (the WRDS pull wrote
  `completed_at` at 21%). The digest only reports what it can re-read.

Section statuses follow the house convention: `ok` (data present), `ok_empty`
(source readable, nothing there — a real result), `unavailable` (source could
not be read — never a pass, reason attached).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from backend import config as _config

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

#: Sections build_digest() always emits, in order. A consumer can rely on
#: every key existing with a `status` — absence of a section is a bug, not a
#: quiet day.
SECTIONS = ("arena", "ledger", "lanes", "collections", "iif",
            "prediction_markets")


def digests_dir(ledger_dir: Path | None = None) -> Path:
    return (ledger_dir or _config.OPTIMUS_LEDGER_DIR) / "digests"


def corpus_path(ledger_dir: Path | None = None) -> Path:
    return digests_dir(ledger_dir) / "digest_corpus.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _unavailable(reason: str) -> dict:
    return {"status": "unavailable", "reason": reason}


# ── sections ────────────────────────────────────────────────────────────────

def _arena_section(day: str, arena_root: Path | None) -> dict:
    """Arena state for the day: what it decided, believed, matured, and how
    reliable it has measured itself to be. All read from the arena store."""
    try:
        from backend.services.arena import engine as arena_engine
        from backend.services.arena import regret as arena_regret
        from backend.services.arena import reliability as arena_reliability
        from backend.services.arena import store as arena_store
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"arena modules not importable: {exc}")

    out: dict = {"status": "ok"}
    try:
        st = arena_engine.status(arena_root)
        books = st.get("books", {})
        out["books_seeded"] = sum(1 for b in books.values() if b.get("seeded"))
        out["books_total"] = len(books)
        out["last_nav"] = {b: (v.get("last_nav") or {}).get("nav")
                           for b, v in books.items() if v.get("seeded")}
        out["experiences_total"] = st.get("experiences")
        out["experience_outcomes_total"] = st.get("experience_outcomes")
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"arena store unreadable: {type(exc).__name__}: {exc}")

    snap = None
    try:
        snap = arena_store.read_snapshot(day, arena_root)
    except Exception as exc:  # noqa: BLE001
        out["snapshot_error"] = f"{type(exc).__name__}: {exc}"
    if snap:
        out["snapshot"] = {
            k: snap.get(k)
            for k in ("scored_n", "coverage_histogram", "composite_version",
                      "information_state_hash")
            if k in snap
        }
    else:
        out["snapshot"] = None  # no frozen day-state — non-trading day or pass not run

    try:
        rows = arena_store.read_beliefs(arena_root)
        out["beliefs_total"] = len(rows)
        out["beliefs_today"] = sum(
            1 for r in rows
            if str(r.get("session") or r.get("as_of") or r.get("date") or "")
            .startswith(day))
    except Exception as exc:  # noqa: BLE001
        out["beliefs_error"] = f"{type(exc).__name__}: {exc}"

    try:
        outcomes = arena_store.read_outcomes(arena_root)
        out["outcomes_total"] = len(outcomes)
        out["outcomes_matured_today"] = sum(
            1 for r in outcomes
            if str(r.get("resolved_at") or r.get("resolved") or "")
            .startswith(day))
    except Exception as exc:  # noqa: BLE001
        out["outcomes_error"] = f"{type(exc).__name__}: {exc}"

    try:
        rel = arena_reliability.latest(arena_root)
        out["reliability"] = None if rel is None else {
            k: rel.get(k) for k in ("as_of", "status", "n_cells", "cells_min_n")
            if isinstance(rel, dict) and k in rel
        }
    except Exception as exc:  # noqa: BLE001
        out["reliability_error"] = f"{type(exc).__name__}: {exc}"

    try:
        reg = arena_regret.summary(root=arena_root)
        out["regret"] = {k: reg.get(k) for k in ("status", "n_pairs", "leg")
                         if isinstance(reg, dict) and k in reg} or None
    except Exception as exc:  # noqa: BLE001
        out["regret_error"] = f"{type(exc).__name__}: {exc}"

    # What RELIABILITY_ROUTER_v1 would have recommended today — recorded so
    # the learner has a longitudinal trail from its first day, BEFORE anything
    # is allowed to act on it. Global verdict + weights only; the full
    # per-state receipt is one recompute away at /api/arena/router.
    try:
        from backend.services.arena import trust_router as arena_trust
        rec = arena_trust.recommend(root=arena_root)
        g = rec.get("global") or {}
        out["trust_router"] = {
            "router_version": rec.get("router_version"),
            "verdict": g.get("verdict"),
            "n_reported_cells": rec.get("n_reported_cells"),
            "weights": ({a: v.get("weight")
                         for a, v in (g.get("actors") or {}).items()}
                        if g.get("verdict") == "RECOMMENDED" else None),
        }
    except Exception as exc:  # noqa: BLE001
        out["trust_router_error"] = f"{type(exc).__name__}: {exc}"

    if out.get("books_seeded", 0) == 0 and not snap:
        out["status"] = "ok_empty"  # arena present but nothing accrued today
    return out


def _ledger_section(day: str, ledger_dir: Path) -> dict:
    """The latest resolver receipt — what was due, what resolved, what is
    overdue. The receipt file IS the evidence the resolver ran (its docstring
    explains why the log line cannot be)."""
    d = ledger_dir / "resolver_receipts"
    if not d.is_dir():
        return _unavailable("resolver_receipts directory does not exist")
    files = sorted(d.glob("*.json"))
    if not files:
        return {"status": "ok_empty", "reason": "no resolver receipts yet"}
    try:
        latest = json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"latest receipt unreadable: {exc}")
    ran_today = str(latest.get("ran_at", "")).startswith(day)
    return {
        "status": "ok",
        "ran_today": ran_today,
        "latest_receipt": {
            k: latest.get(k)
            for k in ("ran_at", "status", "due", "newly_resolved", "pending",
                      "overdue", "nothing_was_due")
        },
        "n_receipts": len(files),
    }


def _lanes_section() -> dict:
    """Lane NAV freshness — rows landed, not jobs ran."""
    try:
        from backend.services.portfolio_intelligence.scheduler import nav_freshness
        nav = nav_freshness()
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"nav_freshness failed: {type(exc).__name__}: {exc}")
    if "error" in nav:
        return _unavailable(f"nav_freshness error: {nav['error']}")
    lanes = nav.get("lanes", {})
    return {
        "status": "ok" if lanes else "ok_empty",
        "expected_nav_date": nav.get("expected_nav_date"),
        "all_fresh": nav.get("all_fresh"),
        "n_lanes": len(lanes),
        "stale": sorted(k for k, v in lanes.items() if not v.get("fresh")),
    }


def _collections_section(day: str, ledger_dir: Path) -> dict:
    """Ownership-forms collection receipt for the day (the corpus grows one
    PIT day at a time; a day with no receipt is a day the collector left no
    evidence)."""
    d = ledger_dir / "teacher_library" / "collection_receipts"
    if not d.is_dir():
        return _unavailable("collection_receipts directory does not exist")
    # The 06:00 ET job collects YESTERDAY's index; today's receipt may cover
    # day-1. Report the most recent receipt and whether one landed for `day`.
    files = sorted(d.glob("*.json"))
    if not files:
        return {"status": "ok_empty", "reason": "no collection receipts yet"}
    latest_day = files[-1].stem
    try:
        latest = json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"latest receipt unreadable: {exc}")
    return {
        "status": "ok",
        "latest_day": latest_day,
        "written": latest.get("written"),
        "source_status": latest.get("source_status"),
        "n_receipts": len(files),
    }


def _iif_section(day: str, ledger_dir: Path) -> dict:
    """IIF-1 launch record for the day. This artifact exists only on the
    machine that hosts the night launcher; on any other host `unavailable`
    is the true answer, not a failure."""
    d = ledger_dir / "iif1_launches"
    if not d.is_dir():
        return _unavailable("iif1_launches directory not present on this host")
    f = d / f"{day}.json"
    if not f.exists():
        return {"status": "ok_empty",
                "reason": f"no launch record for {day} (yet)"}
    try:
        rec = json.loads(f.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"launch record unreadable: {exc}")
    return {"status": "ok",
            "outcome": rec.get("outcome") or rec.get("status"),
            "record": {k: rec.get(k)
                       for k in ("outcome", "status", "reason", "launched_at",
                                 "margin_minutes") if k in rec}}


# ── assembly ────────────────────────────────────────────────────────────────

def _prediction_markets_section(day: str) -> dict:
    """TRIAL-PREDMARKET-1/-2: what the crowd priced today, and whether the
    two venues disagreed. Documentation of a measurement, never a signal —
    and the 17:55 ET snapshot precedes the 18:15 digest by design."""
    try:
        from backend.services import prediction_market_matching as mm
        from backend.services.prediction_markets import (SOURCES,
                                                         _receipt_path)

        out: dict = {"status": "ok_empty",
                     "note": "no snapshot receipts for this day"}
        receipts = {}
        for source in SOURCES:
            p = _receipt_path(day, source)
            if p.exists():
                r = json.loads(p.read_text(encoding="utf-8"))
                receipts[source] = {"status": r.get("status"),
                                    "rows": r.get("rows_written"),
                                    "truncated": r.get("pages_truncated")}
        if receipts:
            out = {"status": "ok", "receipts": receipts}
        div = mm.match_day(day)
        if div.get("status") == "ok":
            out["status"] = "ok"
            out["divergence"] = {
                "n_measured": div.get("n_measured"),
                "n_above_cost_bar": div.get("n_above_cost_bar"),
                "cost_bar": div.get("cost_bar"),
                "spec": div.get("spec"),
            }
        return out
    except Exception as exc:  # noqa: BLE001 — a section never kills the digest
        return {"status": "unavailable",
                "reason": f"{type(exc).__name__}: {exc}"}


def build_digest(day: str | None = None, *,
                 ledger_dir: Path | None = None,
                 arena_root: Path | None = None) -> dict:
    """Assemble the day's digest from durable state. Never raises: a section
    that cannot be read reports `unavailable` with its reason."""
    day = day or _today()
    ldir = ledger_dir or _config.OPTIMUS_LEDGER_DIR
    sections = {
        "arena": _arena_section(day, arena_root),
        "ledger": _ledger_section(day, ldir),
        "lanes": _lanes_section(),
        "collections": _collections_section(day, ldir),
        "iif": _iif_section(day, ldir),
        "prediction_markets": _prediction_markets_section(day),
    }
    statuses = {name: s.get("status") for name, s in sections.items()}
    return {
        "schema_version": SCHEMA_VERSION,
        "population": "documentation",  # never a signal — see module docstring
        "day": day,
        "generated_at": _now_iso(),
        "sections": sections,
        "section_statuses": statuses,
        "n_ok": sum(1 for s in statuses.values() if s == "ok"),
        "n_ok_empty": sum(1 for s in statuses.values() if s == "ok_empty"),
        "unavailable": sorted(k for k, v in statuses.items()
                              if v == "unavailable"),
    }


def _render_md(digest: dict) -> str:
    lines = [f"# Daily digest — {digest['day']}",
             "",
             f"Generated {digest['generated_at']} · schema v{digest['schema_version']}"
             " · documentation only, never a signal.",
             ""]
    for name in SECTIONS:
        s = digest["sections"].get(name, {})
        status = s.get("status", "missing")
        lines.append(f"## {name} — {status}")
        for k, v in s.items():
            if k == "status":
                continue
            lines.append(f"- **{k}**: {json.dumps(v, default=str)}")
        lines.append("")
    return "\n".join(lines)


def _corpus_days(path: Path) -> set[str]:
    days: set[str] = set()
    if not path.exists():
        return days
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                days.add(json.loads(line).get("day", ""))
            except Exception:  # noqa: BLE001 — a corrupt line must not kill the job
                continue
    return days


def write_digest(digest: dict, *, ledger_dir: Path | None = None) -> dict:
    """Persist: dated JSON + MD (overwritten on re-run — a fresher read of the
    same disk state), and one corpus line per day (append-only, deduped so a
    manual re-run cannot double-count a day)."""
    d = digests_dir(ledger_dir)
    d.mkdir(parents=True, exist_ok=True)
    day = digest["day"]
    json_path = d / f"{day}.json"
    md_path = d / f"{day}.md"
    json_path.write_text(json.dumps(digest, indent=2, default=str),
                         encoding="utf-8")
    md_path.write_text(_render_md(digest), encoding="utf-8")
    cpath = corpus_path(ledger_dir)
    appended = False
    if day not in _corpus_days(cpath):
        with cpath.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(digest, default=str) + "\n")
        appended = True
    return {"json": str(json_path), "md": str(md_path),
            "corpus": str(cpath), "corpus_appended": appended}


def run_daily_digest(day: str | None = None, *,
                     ledger_dir: Path | None = None,
                     arena_root: Path | None = None) -> dict:
    """Build + persist the day's digest. The scheduler's entry point."""
    digest = build_digest(day, ledger_dir=ledger_dir, arena_root=arena_root)
    paths = write_digest(digest, ledger_dir=ledger_dir)
    return {
        "status": "ok",
        "day": digest["day"],
        "n_ok": digest["n_ok"],
        "n_ok_empty": digest["n_ok_empty"],
        "unavailable": digest["unavailable"],
        "corpus_appended": paths["corpus_appended"],
        "paths": paths,
    }


def read_digest(day: str, *, ledger_dir: Path | None = None) -> dict | None:
    f = digests_dir(ledger_dir) / f"{day}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def latest_digest(*, ledger_dir: Path | None = None) -> dict | None:
    d = digests_dir(ledger_dir)
    if not d.is_dir():
        return None
    files = sorted(f for f in d.glob("*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))
