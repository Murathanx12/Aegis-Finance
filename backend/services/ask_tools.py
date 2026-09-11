"""ASK AEGIS READS THE PROJECT — the retrieval half (roadmap O6).

WHAT CHANGED, AND WHY IT IS A SEPARATE MODULE
=============================================
Until today the assistant saw exactly one thing: the last two nights'
`LEADERBOARD.md`. Asked "look at `scripts/night_g3_evolve_v2.py`" it answered
from a leaderboard, which is the failure mode the whole programme is built
against -- a plausible sentence with no receipt under it.

This module chooses WHAT the model is allowed to see, deterministically, from
the question alone. It lives beside the route rather than inside it because the
property that matters is testable only on a narrow file: **there is no write
tool, no subprocess, no broker and no outbound POST in the ask path.** An AST
test walks this module and `routers/control_ask.py` and fails on any of them.
A module-wide guard over `routers/control.py` could never say that -- that file
legitimately spawns night jobs.

THE ROUTER IS DETERMINISTIC, AND THAT IS THE POINT
==================================================
The model does not choose its tools. A question is matched against an ORDERED
list of rules, most specific first, and the first match decides. Two
consequences, both deliberate:

* the same question always retrieves the same receipts, so an answer can be
  reproduced and an answer that was wrong can be diagnosed as a retrieval
  failure or a reading failure -- never both at once;
* a tool the model cannot request is a tool the model cannot misuse. The tool
  set is the board's own read-only routes and nothing else.

EVERY ANSWER ENDS WITH ITS SOURCES
==================================
`sources` is built by this module from the paths it actually read, and the route
appends it to the answer text ITSELF rather than asking the model to cite. A
model asked to cite its sources will invent one; a list computed from the files
that were opened cannot.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent.parent


REPO = _repo_root()
OPTIMUS = REPO / "backend" / "data" / "optimus"
DOCS = REPO / "docs"

#: The whole context budget, in characters. A 7B at 4k tokens cannot read more
#: than this and a truncated receipt read as a whole one is worse than a refusal.
MAX_CONTEXT_CHARS = 12000

#: Per-source cap, so one long file cannot crowd out the other three sources.
MAX_PER_SOURCE_CHARS = 6000

#: The declared TOOLS. There is no other way for this module to reach disk, and
#: `test_ask_authority.py` asserts each is a read.
TOOLS: tuple[str, ...] = (
    "file",          # one repo file, through the board's own sandbox
    "receipt",       # a night job's newest receipt
    "fleet",         # the six books' excess, with their standard errors
    "night_plan",    # the newest NIGHT_PLAN receipt
    "morning",       # today's morning receipt and its forecast rows
    "universe",      # the tracker universe's header
    "default",       # INDEX TIER 0 names, the newest handoff's head, today's receipts
)

#: A repo-relative path, e.g. `scripts/night_g3_evolve_v2.py` or
#: `backend/services/belief_state.py`. Anchored on a known top-level directory so
#: an English sentence containing a slash is not mistaken for a path.
_PATH_RE = re.compile(
    r"\b((?:backend|frontend|scripts|learner|docs|desktop|alpha|engine)"
    r"(?:/[\w.\-]+)+\.(?:py|md|json|yaml|yml|ts|tsx|txt|csv))\b")

#: A night-job id: one capital letter, digits, an underscore. `G3_evolve_v2`,
#: `R2_widened_panelB`, `N3_frozen_embedding_head`.
_JOB_RE = re.compile(r"\b([A-Z]\d+_[A-Za-z0-9_]+)\b")

#: A bare job FAMILY, as a person says it: "the G3 receipt", "what did D4 do".
_JOB_STUB_RE = re.compile(r"\b([A-Z]\d+)\b")

_FLEET_WORDS = ("fleet", "books", "positions", "paper account", "paper book")
_PLAN_WORDS = ("tonight", "queue", "plan", "what should run", "next test")
_MORNING_WORDS = ("today", "morning", "brief", "what happens", "what do you think happens")
_UNIVERSE_WORDS = ("universe", "screener", "all the stocks", "3,056", "3056")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rel(p: Path | str) -> str:
    try:
        return Path(p).resolve().relative_to(REPO.resolve()).as_posix()
    except (ValueError, OSError):
        return str(p)


def _clip(text: str, n: int = MAX_PER_SOURCE_CHARS) -> str:
    text = text or ""
    return text if len(text) <= n else text[:n] + "\n…[truncated]"


# ===========================================================================
# THE ROUTER
# ===========================================================================


def known_jobs() -> set[str]:
    """The night factory's own job ids. DERIVED, never re-typed here."""
    try:
        from scripts.night_factory_jobs import JOBS
        return set(JOBS)
    except Exception:                                              # noqa: BLE001
        return set()


def route(question: str) -> dict:
    """Which tool answers this question, and with what argument.

    Ordered, most specific first. Returns `{"tool": ..., "arg": ..., "why": ...}`
    so the payload can show the reader WHY it looked where it looked -- a
    retrieval that cannot be audited is a retrieval nobody can fix.
    """
    q = (question or "").strip()
    low = q.lower()

    m = _PATH_RE.search(q)
    if m:
        return {"tool": "file", "arg": m.group(1),
                "why": f"the question names a repo path ({m.group(1)})"}

    for cand in _JOB_RE.findall(q):
        return {"tool": "receipt", "arg": cand,
                "why": f"the question names a job id ({cand})"}
    jobs = known_jobs()
    for job in sorted(jobs, key=len, reverse=True):
        if job.lower() in low:
            return {"tool": "receipt", "arg": job,
                    "why": f"the question names a job in the night queue ({job})"}
    # A bare lane prefix -- "what does the G3 receipt say?" -- is how a person
    # refers to a job. Resolved against the queue's own ids, alphabetically so
    # the choice is reproducible, and the reason names which one was picked and
    # what else it could have been. A guess that says it is a guess is usable.
    for stub in _JOB_STUB_RE.findall(q):
        matches = sorted(j for j in jobs if j.upper().startswith(stub.upper() + "_"))
        if matches:
            extra = (f" (also matched: {', '.join(matches[1:])})" if len(matches) > 1 else "")
            return {"tool": "receipt", "arg": matches[0],
                    "why": f"the question names the job family {stub}{extra}"}

    if any(w in low for w in _MORNING_WORDS):
        return {"tool": "morning", "arg": None,
                "why": "the question is about today, so it is answered from today's forecast rows"}
    if any(w in low for w in _FLEET_WORDS):
        return {"tool": "fleet", "arg": None, "why": "the question is about the books"}
    if any(w in low for w in _PLAN_WORDS):
        return {"tool": "night_plan", "arg": None, "why": "the question is about tonight's queue"}
    if any(w in low for w in _UNIVERSE_WORDS):
        return {"tool": "universe", "arg": None, "why": "the question is about the universe"}
    return {"tool": "default", "arg": None,
            "why": "no tool matched, so the canon's TIER 0 names, the newest handoff and today's receipts"}


# ===========================================================================
# THE TOOLS. Each returns (text, sources) and each is a READ.
# ===========================================================================


def tool_file(path: str) -> tuple[str, list[str]]:
    """One repo file, through the BOARD'S OWN sandbox.

    `_resolve_in_checkout` is imported rather than reimplemented: the
    never-served list (`.env`, keys, `.git`) and the checkout confinement are
    security properties, and a second copy of a security check is a second copy
    that can drift. A refusal comes back as TEXT the model can read out, not as
    an exception -- "I cannot show you .env and here is the rule" is a better
    answer than a 403 the page has to interpret.
    """
    from fastapi import HTTPException

    from backend.routers.control import file as _file

    try:
        blob = _file(path)
    except HTTPException as exc:
        return (f"### {path}\nREFUSED: {exc.detail}", [])
    head = "\n".join(blob.get("commits") or []) or (blob.get("git_note") or "")
    text = (f"### {blob['path']} ({blob['lines']} lines)\n"
            f"last commits:\n{head}\n\n{_clip(blob['text'])}")
    return text, [blob["path"]]


def _receipt_files(job: str) -> list[Path]:
    """Every receipt whose filename starts with this job id, newest last."""
    if not OPTIMUS.is_dir():
        return []
    hits = [p for p in OPTIMUS.glob(f"night_factory_*/{job}*.json") if p.is_file()]
    hits += [p for p in OPTIMUS.glob(f"{job}*.json") if p.is_file()]
    return sorted(hits, key=lambda p: (p.stat().st_mtime, p.name))


def tool_receipt(job: str) -> tuple[str, list[str]]:
    files = _receipt_files(job)
    if not files:
        return (f"### {job}\nNo receipt for `{job}` under {_rel(OPTIMUS)}. "
                f"Either the job has not run in this checkout or the id is not the "
                f"one the queue uses.", [])
    newest = files[-1]
    try:
        text = newest.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return (f"### {job}\nreceipt unreadable: {type(exc).__name__}: {exc}", [_rel(newest)])
    other = [_rel(p) for p in files[-4:-1]]
    body = (f"### {job} — newest receipt {_rel(newest)}\n{_clip(text)}")
    if other:
        body += f"\n\nearlier receipts for the same job: {', '.join(other)}"
    return body, [_rel(newest)] + other


def tool_fleet() -> tuple[str, list[str]]:
    from backend.routers.control import PAPER_CACHE, fleet as _fleet

    parts: list[str] = []
    sources: list[str] = []
    try:
        f = _fleet()
        parts.append("### fleet vs the benchmark (every mean carries its SE)\n"
                     + _clip(json.dumps(f, indent=1), 5000))
        sources.append("backend/routers/control.py::fleet (computed from paper_nav)")
    except Exception as exc:                                       # noqa: BLE001
        parts.append(f"### fleet\nunavailable: {type(exc).__name__}: {exc}")
    if PAPER_CACHE.exists():
        try:
            parts.append("### last paper snapshot (cached; nothing was fetched)\n"
                         + _clip(PAPER_CACHE.read_text(encoding="utf-8"), 3000))
            sources.append(_rel(PAPER_CACHE))
        except OSError:
            pass
    else:
        parts.append(f"### paper snapshot\nnone on disk at {_rel(PAPER_CACHE)}; the "
                     f"lanes are marked by the remote deployment and this checkout "
                     f"has not pulled once.")
    return "\n\n".join(parts), sources


def _newest(paths: list[Path]) -> Path | None:
    real = [p for p in paths if p.is_file()]
    return max(real, key=lambda p: p.stat().st_mtime) if real else None


def tool_night_plan() -> tuple[str, list[str]]:
    p = _newest(list(OPTIMUS.glob("night_factory_*/NIGHT_PLAN*.json"))) if OPTIMUS.is_dir() else None
    if p is None:
        return ("### tonight's queue\nNo NIGHT_PLAN receipt in this checkout. The plan "
                "is written by the night factory; without one, nothing here knows "
                "what is queued.", [])
    return (f"### tonight's queue — {_rel(p)}\n"
            + _clip(p.read_text(encoding="utf-8", errors="replace")), [_rel(p)])


def tool_morning() -> tuple[str, list[str]]:
    """Today's morning receipt and the forecast rows it wrote.

    When no morning has run this returns the ABSENCE, in words, and
    `forecast_rows: 0` -- the route reads that and answers without the model at
    all. "What do you think happens today?" must be answered from rows that were
    written before the market opened and are graded tomorrow; a model asked the
    same question with no rows in front of it will produce a forecast that is
    not in any ledger, which is the one thing this feature must never do.
    """
    from backend.services import morning as M

    blob = M.latest_receipt()
    if blob is None:
        return ("### today\nThe morning has not run today. There are no forecast rows, "
                "so there is nothing to say about today that would be graded tomorrow.",
                [])
    rows = next((s for s in blob.get("steps", []) if s.get("step") == "forecasts"), {})
    text = (f"### today's morning receipt — {_rel(blob.get('path', ''))}\n"
            f"{_clip(json.dumps(blob, indent=1), 7000)}")
    return text, [_rel(blob.get("path", ""))] + ([] if rows else [])


def morning_forecast_rows() -> tuple[list[dict], str | None]:
    """(rows, receipt path). The route's own check, not the model's."""
    from backend.services import morning as M

    blob = M.latest_receipt()
    if blob is None:
        return [], None
    step = next((s for s in blob.get("steps", []) if s.get("step") == "forecasts"), {})
    rows = step.get("rows") if step.get("status") == "ok" else []
    return list(rows or []), _rel(blob.get("path", ""))


def tool_universe() -> tuple[str, list[str]]:
    from backend.routers.control import universe as _universe

    try:
        blob = _universe(limit=5)
    except Exception as exc:                                       # noqa: BLE001
        return (f"### universe\nunavailable: {type(exc).__name__}: {exc}", [])
    header = {k: v for k, v in blob.items() if k != "rows"}
    return (f"### the tracker universe\n{_clip(json.dumps(header, indent=1), 4000)}",
            [str(blob.get("universe_source") or "")] if blob.get("universe_source") else [])


def _index_tier0() -> tuple[str, list[str]]:
    p = DOCS / "INDEX.md"
    if not p.is_file():
        return "", []
    text = p.read_text(encoding="utf-8", errors="replace")
    start = text.find("## TIER 0")
    if start < 0:
        return _clip(text, 2000), [_rel(p)]
    end = text.find("\n## ", start + 5)
    return text[start:end if end > 0 else start + 2000], [_rel(p)]


def _newest_handoff_head() -> tuple[str, list[str]]:
    """The newest handoff's SCOREBOARD (its §0), not the whole file.

    Every handoff in this repo opens with the scoreboard by house rule, so the
    head is the part that says what is true today; the rest is the plan.
    """
    cands = sorted(DOCS.glob("HANDOFF_*.md"), key=lambda p: p.name, reverse=True)
    if not cands:
        return "", []
    p = cands[0]
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    head, seen_zero = [], False
    for ln in lines:
        if ln.startswith("## ") and seen_zero:
            break
        if ln.startswith("## 0") or ln.startswith("## SCOREBOARD"):
            seen_zero = True
        head.append(ln)
        if len(head) > 70:
            break
    return f"### newest handoff — {_rel(p)}\n" + "\n".join(head), [_rel(p)]


def _todays_receipts(day: str | None = None) -> tuple[str, list[str]]:
    day = day or str(datetime.now(timezone.utc).date())
    if not OPTIMUS.is_dir():
        return "", []
    hits: list[Path] = []
    for p in OPTIMUS.glob("night_factory_*/*.json"):
        try:
            if datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).date().isoformat() == day:
                hits.append(p)
        except OSError:
            continue
    for p in (OPTIMUS / "morning").glob(f"{day}_run*.json"):
        hits.append(p)
    if not hits:
        return (f"### receipts written today ({day})\nnone.", [])
    names = sorted(_rel(p) for p in hits)[:20]
    return (f"### receipts written today ({day})\n" + "\n".join(names), names)


def tool_default() -> tuple[str, list[str]]:
    parts, sources = [], []
    for fn in (_index_tier0, _newest_handoff_head, _todays_receipts):
        text, src = fn()
        if text:
            parts.append(text)
        sources.extend(src)
    return "\n\n".join(parts), sources


_DISPATCH = {
    "file": tool_file,
    "receipt": tool_receipt,
    "fleet": tool_fleet,
    "night_plan": tool_night_plan,
    "morning": tool_morning,
    "universe": tool_universe,
    "default": tool_default,
}
assert set(_DISPATCH) == set(TOOLS), "every declared tool needs a handler"


def build_context(question: str, *, max_chars: int = MAX_CONTEXT_CHARS) -> dict:
    """Route, read, and return what the model is allowed to see."""
    r = route(question)
    fn = _DISPATCH[r["tool"]]
    try:
        text, sources = fn(r["arg"]) if r["arg"] is not None else fn()
    except Exception as exc:                                       # noqa: BLE001
        logger.exception("ask retrieval failed for tool %s", r["tool"])
        text, sources = (f"retrieval failed: {type(exc).__name__}: {exc}", [])
    truncated = len(text) > max_chars
    return {"text": text[:max_chars], "sources": [s for s in sources if s],
            "truncated": truncated, "tool": r["tool"], "tool_arg": r["arg"],
            "routed_because": r["why"], "utc": _now(),
            "tools_available": list(TOOLS)}


def sources_line(sources: list[str]) -> str:
    """The line every answer ends with. Computed, never asked of the model."""
    return "sources: " + (json.dumps(sources, ensure_ascii=False) if sources else "[]")


def forecast_answer(rows: list[dict], receipt: str | None) -> str:
    """Today's answer, written from the LEDGER rows, with no model involved.

    Deterministic on purpose. The claim "what do you think happens today" is a
    forecast, forecasts in this programme are written before the session and
    graded after it, and a sentence generated at question time is neither.
    """
    if not rows:
        return ("The morning has not written any forecast rows today, so I have no "
                "forecast to report. Click **Run the morning** on the board (it writes "
                "one gradeable row per lane before it answers). I will not invent one: "
                "a forecast that is not in the ledger cannot be graded tomorrow.")
    lines = [f"Today's forecast rows, written by the engine before the session and "
             f"graded tomorrow ({len(rows)} rows):"]
    for r in rows:
        p = r.get("probability")
        lines.append(
            f"- {r.get('lane')} beats {r.get('benchmark')}"
            f"{' (an index, not a twin)' if r.get('benchmark_is_fallback') else ''}: "
            f"p = {p}, basis {r.get('basis')} on {r.get('n_paired_days')} paired sessions, "
            f"resolves after {r.get('resolves_after')}")
    lines.append("These are the engine's numbers from the lanes' own realised history. "
                 "No model was asked, and none of them sizes or ranks anything.")
    if receipt:
        lines.append(f"receipt: {receipt}")
    return "\n".join(lines)
