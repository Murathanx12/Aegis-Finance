"""Which of the things this repository computes can actually reach a decision.

THE FAILURE THIS MODULE EXISTS TO MAKE MECHANICAL
=================================================
Three times in three weeks, the same shape:

* `event_intel.py` -- a typed event feed with per-feed canaries -- had exactly
  ONE caller, `daily_brief.py`, which nothing schedules. It was "the 17th
  collector feeding nobody" for as long as it existed, and it was found by
  reading the file, not by any check.
* The "no new forecast in 11 days" alarm was true about the ledger it measured
  and false about the system, because a third forecast population existed that
  no health surface enumerated (`forecast_populations.py` fixed that one).
* The WRDS pull reported COMPLETE with seven planned tables never attempted,
  because every check read the record of what HAPPENED and a table nobody asked
  for leaves no trace.

All three are the same bug: **a check that reads the record of what ran cannot
see what never got called.** The fix is always to enumerate the PLAN. This
module enumerates the plan for CODE: every module under `backend/`, and whether
any entry point can reach it.

WHY THE CALL GRAPH AND NOT A REGISTRY
=====================================
A registry somebody has to remember to add to is the honour system with extra
steps -- the reasoning `guard_contract.py` already settled. So reachability is
DERIVED: parse every module's imports, walk forward from the real entry points
(the API routers, the scheduler, the app itself), and whatever is not in the
closure is computing for nobody.

A module can be unreachable for perfectly good reasons -- offline research, a
CLI tool, a superseded implementation kept for reference. Those are CLASSIFIED,
with the reason recorded here. What must never happen again is a module being
unreachable and nobody knowing.

WHAT THIS DOES AND DOES NOT PROVE
=================================
Reachable does NOT mean used: a module imported by a router whose endpoint
nobody calls is reachable and idle. This measures the weaker, mechanical
property -- **is there a path at all** -- because that is the one that can be
checked without running anything, and it is the one that was false in every
case above.

Unreachable, on the other hand, is conclusive: no entry point can call it, so
nothing it computes reaches a decision. Those are the rows worth reading.

ADDING A MODULE
===============
Nothing to do, if an entry point reaches it. If it does not, `test_signal_
reachability.py` FAILS until the module is classified below -- which is the
point: a new collector that feeds nobody should be a red suite, not a discovery
three weeks later.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BACKEND = Path(__file__).resolve().parents[1]
ROOT_PKG = "backend"

#: Where execution actually begins. Everything reachable from here is wired
#: into something a user or a clock can trigger.
ENTRY_POINTS: tuple[str, ...] = (
    "backend.main",                                        # the app itself
    "backend.services.portfolio_intelligence.scheduler",   # every timed job
)

#: Router modules are entry points too, but they are discovered rather than
#: listed: a new router that nobody adds here would silently narrow the closure
#: and make its whole dependency tree look like orphans.
ROUTER_DIR = BACKEND / "routers"

#: The SECOND closure. A module invoked from `scripts/` is offline research or
#: attended tooling: it never runs on a request or a timer, and that is correct
#: for most of this repository. Deriving that tier is what keeps the audit
#: honest -- the alternative was 79 hand-written "offline research" reasons,
#: which is a list somebody maintains by memory, i.e. the honour system the
#: whole approach exists to replace.
SCRIPTS_DIR = BACKEND.parent / "scripts"


#: Below this, the scan found nothing and any verdict is about an empty set.
#: Not tuned: the repository has ~650 modules and the number exists only to
#: separate "scanned the codebase" from "scanned a wrong or empty directory".
_MIN_MODULES = 50


class ReachabilityRefused(RuntimeError):
    """Base: this audit will not report a verdict it cannot support."""


class UnclassifiedOrphan(ReachabilityRefused):
    """A module no entry point can reach, and no reason recorded for it."""


class ReachabilityUnknowable(ReachabilityRefused):
    """The codebase could not be seen, so "no orphans" would be a lie.

    THE FAILURE THIS PREVENTS IS THIS AUDIT'S OWN. Point it at the wrong
    directory and `_all_modules` returns nothing, every set is empty, and
    `assert_no_unclassified_orphans` reports ALL CLEAR -- a guard handed
    nothing and answering anyway, which is precisely the class of bug it was
    written to catch. It must refuse instead.
    """


#: Modules that are deliberately outside the running system. Each carries the
#: reason, because "unreachable" and "unreachable ON PURPOSE" are different
#: facts and only one of them is a defect.
#:
#: Prefix match on the dotted module name, so a package classifies its subtree.
#: Three kinds of reason appear here, and they are NOT equivalent:
#:
#:   OK      it is supposed to be here and callable from nowhere.
#:   AWAITS  a corpus or an estimator built before its consumer exists. Fine
#:           for a while, a smell after a while, and the roadmap owns it.
#:   GAP     something that SHOULD have a caller and does not. Recorded as a
#:           gap rather than quietly excused, because the whole point of this
#:           module is that "unreachable and nobody knew" stops happening.
CLASSIFIED: dict[str, str] = {
    "backend.tests": (
        "OK — the suite. It reaches the system, not the other way round."),
    "backend.services.copy_lab": (
        "OK — offline lane research; invoked by the attended lane tooling."),
    "backend.services.signal_reachability": (
        "OK — this module. It audits the graph it sits in; being inside its "
        "own answer is the one case where unreachable is correct."),

    # ---- GAPS: a guard nothing invokes is a guard that guards nothing ----
    # `detectability_gate` WAS here, as the first GAP this audit found:
    # TOURNAMENT-2's declared precondition, named three times in
    # `scripts/panel2_planted_worlds.py` comments and imported by nothing.
    # "The T2 runner MUST call assert_detectable" was true as a sentence and
    # false as a fact. That script now calls it, so the module is tooling and
    # no longer needs a row here. Left as a comment because a gap that closes
    # silently teaches nothing.
    "backend.services.execution_boundary": (
        "GAP — a precursor can be observable, correct, and unreachable, and "
        "this is what decides which. Only its own test calls it, so no live "
        "signal is currently checked for reachability."),
    "backend.services.verdict_battery": (
        "GAP — measures whether the referee kills good ideas. It has never "
        "been run against the referee it was built to check."),
    "backend.services.strategy_library": (
        "GAP — the published-predictor library whose whole point is that a "
        "CLAIM is not a MEASUREMENT. Nothing consults it before a new signal "
        "is proposed, which is the moment it would be worth consulting."),
    "backend.services.winner_loser_factory": (
        "GAP — matched controls are CANON rule 4 ('study losers as hard as "
        "winners'). The factory exists; no analysis path calls it."),

    # ---- AWAITS: built ahead of a consumer the roadmap names ----
    "backend.services.relative_value_labels": (
        "AWAITS — NEURAL-RELATIVE-VALUE-1's pairwise labels. Its consumer is "
        "RELATIVE_VALUE_NN_v1 (ROADMAP_2026-08-24 §3.2), which does not exist "
        "yet. 72,495 labels over 145 DATE BLOCKS; the effective n is 145."),
    "backend.services.expectation_store": (
        "AWAITS — EXPECTATION-BACKFILL-1, the first rows G4 holds. Consumer "
        "is EVENT_RESPONSE_v1 (ROADMAP_2026-08-24 §3.1)."),
    "backend.services.graph_propagation": (
        "AWAITS — GRAPH_PROPAGATION_v1, the one mechanism "
        "ANALYST-COCOVERAGE-GRAPH-1 licensed. Its consumer is a separate "
        "PRODUCT_EXPERIMENT book in arena_books_v1.yaml, and that book cannot "
        "be added until the ten seeds written 2026-08-21 migrate to per-book "
        "identity on their next arena pass: they are still verified against "
        "the WHOLE-FILE config_hash, so adding a book first makes "
        "assert_config_current refuse to run AND refuse to migrate, for all "
        "ten. This is a SEQUENCING wait with a date, not a missing consumer."),
    "backend.services.theme_baskets": (
        "AWAITS — point-in-time secular theme baskets; the narrative work "
        "that would consume them is LOGGED, not queued (roadmap §5)."),
    "backend.services.thematic_momentum": (
        "AWAITS — thematic entry logic with no book declaring it. Would be a "
        "candidate selector under the §3 programme, not a composite factor."),

    # ---- OK: offline research and superseded implementations ----
    "backend.services.return_model": (
        "OK — offline quantile-return training tool; says so in line 2."),
    "backend.services.signal_optimizer": (
        "OK — offline weight-optimisation tool, superseded by the config- "
        "driven signal engine. Kept for reference."),
    "backend.services.shadow_portfolios": (
        "OK — forward shadow portfolios for finalists; attended, and the "
        "arena is the live successor to the idea."),
    "backend.services.teacher_library.adapters": (
        "OK — offline teacher-library adapters, driven by attended research."),
    "backend.services.teacher_library.adapters_13dg": (
        "OK — 13D/G adapter; MANAGER-* is BLOCKED (13F `fdate` is a vintage "
        "stamp), so it has no live consumer by decision, not by accident."),
    "backend.services.teacher_library.matched_controls": (
        "OK — offline matched-control construction for the teacher library."),
    "backend.services.portfolio_intelligence.comparator": (
        "OK — offline lane comparison, run attended."),
    "backend.services.portfolio_intelligence.cross_asset_rotation": (
        "OK — research module; no lane declares a cross-asset rotation arm."),
    "backend.services.portfolio_intelligence.forward_ic": (
        "OK — forward-IC analysis, run attended over collected snapshots."),
    "backend.services.portfolio_intelligence.rule_evolution": (
        "OK — offline rule-evolution research; deliberately not wired to a "
        "live decision path, since a rule that rewrites itself in production "
        "is exactly what the immutable-policy rule forbids."),
}


def _module_name(path: Path, base: Path | None = None) -> str:
    base = base or BACKEND
    rel = path.relative_to(base.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _all_modules(backend: Path | None = None) -> dict[str, Path]:
    backend = backend or BACKEND
    out: dict[str, Path] = {}
    for p in backend.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        out[_module_name(p, backend)] = p
    return out


def _imports_of(path: Path, module: str) -> set[str]:
    """Every `backend.*` module this file imports, at any nesting depth.

    Function-level imports count. They are the norm in this codebase -- the
    scheduler imports its jobs inside the coroutine that runs them -- so a
    module-level-only scan would report almost the entire system as orphaned.
    """
    try:
        # utf-8-SIG, not utf-8: `backend/routers/portfolio.py` carries a BOM,
        # which Python's own importer strips and `ast.parse` does not. Reading
        # it as plain utf-8 made that router unparseable, so its entire
        # dependency tree looked orphaned -- a discovery rule that
        # under-detects, which is the exact failure `guard_contract` warns
        # about one level up.
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError) as e:            # noqa: BLE001
        # Loud: a file this cannot read is a hole in the closure, and a hole
        # in the closure reports working code as dead.
        logger.error("signal_reachability: cannot parse %s (%s) — its "
                     "dependencies will read as orphaned", path, e)
        return set()

    found: set[str] = set()
    pkg = module.rsplit(".", 1)[0] if "." in module else module
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith(ROOT_PKG):
                    found.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # Relative import: resolve against this module's package.
                base = pkg.split(".")
                up = node.level - 1
                base = base[:len(base) - up] if up else base
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            if not mod.startswith(ROOT_PKG):
                continue
            found.add(mod)
            # `from backend.services import x, y` imports MODULES, not names,
            # and missing that reports every such dependency as an orphan.
            for a in node.names:
                found.add(f"{mod}.{a.name}")
    return found


#: Parsing 657 files takes ~4s, and the audit walks them three times per call.
#: Memoised for the REAL backend only: a caller passing its own directory is a
#: test building files as it goes, and handing it a stale graph would make the
#: audit lie about exactly the thing it measures.
_EDGE_MEMO: dict[str, tuple[dict, dict]] = {}


def _graph(backend: Path | None = None) -> tuple[dict, dict]:
    key = str(backend or BACKEND)
    if backend is None or backend == BACKEND:
        if key not in _EDGE_MEMO:
            mods = _all_modules(backend)
            _EDGE_MEMO[key] = (
                mods, {m: _imports_of(p, m) for m, p in mods.items()})
        return _EDGE_MEMO[key]
    mods = _all_modules(backend)
    return mods, {m: _imports_of(p, m) for m, p in mods.items()}


def _closure(modules: dict, edges: dict, seeds: list[str]) -> set[str]:
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in modules:
            continue
        seen.add(cur)
        # Importing `a.b.c` imports `a.b` and `a` — Python does it, so the
        # closure must too. Without this every package `__init__` reads as an
        # orphan, and an audit that cries wolf 20 times gets ignored on the
        # 21st, which is the one that matters.
        parts = cur.split(".")
        for i in range(1, len(parts)):
            anc = ".".join(parts[:i])
            if anc in modules and anc not in seen:
                stack.append(anc)
        for dep in edges.get(cur, ()):
            if dep in modules and dep not in seen:
                stack.append(dep)
            # `from backend.services import event_store` yields both
            # "backend.services" and "backend.services.event_store"; the
            # package itself is a legitimate node and resolves on its own.
    return seen


def _script_seeds(modules: dict) -> list[str]:
    """Every backend module any file under `scripts/` imports."""
    if not SCRIPTS_DIR.exists():
        return []
    seeds: set[str] = set()
    for f in SCRIPTS_DIR.rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        for dep in _imports_of(f, "scripts"):
            if dep in modules:
                seeds.add(dep)
    return sorted(seeds)


def reachable_set(backend: Path | None = None) -> set[str]:
    """Transitive closure of imports from every RUNTIME entry point."""
    modules, edges = _graph(backend)
    seeds = [e for e in ENTRY_POINTS if e in modules]
    seeds += [m for m in modules if m.startswith(f"{ROOT_PKG}.routers.")]
    return _closure(modules, edges, seeds)


def tooling_set(backend: Path | None = None) -> set[str]:
    """Transitive closure from `scripts/` — offline research and tooling."""
    modules, edges = _graph(backend)
    return _closure(modules, edges, _script_seeds(modules))


def _classification(module: str) -> str | None:
    for prefix, reason in CLASSIFIED.items():
        if module == prefix or module.startswith(prefix + "."):
            return reason
    return None


def audit(backend: Path | None = None) -> dict:
    """The plan, not the record: every module and whether anything can call it.

    Three tiers, because "unreachable" lumps two very different facts:

      reachable      a request or a timer can call it. It feeds decisions.
      tooling_only   only `scripts/` reaches it. Offline research and attended
                     tooling -- correct for most of this repository, and no
                     defect.
      orphan         NEITHER. Nothing but its own test can call it. These are
                     the rows worth reading: code that computes for nobody.
    """
    modules, _ = _graph(backend)
    reached = reachable_set(backend)
    tooling = tooling_set(backend)
    orphans, unclassified, tooling_only = [], [], []
    for m in sorted(modules):
        if m in reached or m == ROOT_PKG:
            continue
        if m in tooling:
            tooling_only.append(m)
            continue
        reason = _classification(m)
        orphans.append({"module": m, "reason": reason})
        if reason is None:
            unclassified.append(m)
    resolved = [e for e in ENTRY_POINTS if e in modules]
    resolved += sorted(m for m in modules
                       if m.startswith(f"{ROOT_PKG}.routers."))
    return {
        "n_modules": len(modules),
        "n_reachable": len([m for m in modules if m in reached]),
        "n_tooling_only": len(tooling_only),
        "tooling_only": tooling_only,
        "entry_points_resolved": resolved,
        "n_orphaned": len(orphans),
        "orphans": orphans,
        "unclassified": unclassified,
        "entry_points": list(ENTRY_POINTS) + ["backend.routers.*"],
        "note": ("reachable means A PATH EXISTS, not that anything calls it; "
                 "orphan is conclusive — neither the running system nor "
                 "scripts/ can call it, so only its own test does"),
    }


def assert_no_unclassified_orphans(backend: Path | None = None) -> dict:
    """Refuse a system that computes something nothing can consume.

    Refuses FIRST on not being able to see the codebase at all: an empty scan
    has no orphans, and reporting that as a pass is this module committing the
    bug it exists to find.
    """
    res = audit(backend)
    if res["n_modules"] < _MIN_MODULES:
        raise ReachabilityUnknowable(
            f"scanned {res['n_modules']} module(s) under "
            f"{backend or BACKEND} — this codebase has hundreds. Nothing was "
            f"read, so 'no unclassified orphans' would be a statement about "
            f"an empty set, not about the system.")
    if not res["entry_points_resolved"]:
        raise ReachabilityUnknowable(
            "no entry point resolved to a module in the scan, so the "
            "reachable closure is empty by construction and EVERYTHING would "
            "report as orphaned. Refusing rather than raising 600 false "
            "alarms.")
    if res["unclassified"]:
        raise UnclassifiedOrphan(
            "Neither the running system nor scripts/ can reach these "
            "modules, and no reason is recorded for them:\n  "
            + "\n  ".join(res["unclassified"])
            + "\n\nEither wire one in, or classify it in "
              "signal_reachability.CLASSIFIED with the reason. A collector "
              "that feeds nobody must be a red suite, not a discovery three "
              "weeks later.")
    return res
