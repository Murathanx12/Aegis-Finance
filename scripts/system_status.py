"""The systems dashboard's collector (CH-22a): ONE read-only receipt, then ONE page.

    python -m scripts.system_status                 # collect -> status.json
    python -m scripts.system_status --html          # collect, then render status.html
    python -m scripts.system_status --render-only   # render the existing receipt
    python -m scripts.system_status --strict        # also exit 2 when any row is DOWN

WHY IT EXISTS
=============
The owner asked for the EXE to be "the dashboard of all working systems": the
engine, the universe, what is wrong, the local model, night simulations,
backtests, lessons. Every one of those already had a receipt; none was visible in
one place, and the learning loop sat blocked for 24 days while most tasks
reported rc 0. This script is the one place that reads them all.

WHAT IT REUSES (it does not duplicate)
======================================
* `backend.services.system_health` -- the ~40 probes (scheduled tasks judged by
  the receipt each must advance, bars panel, funnel, sim, lab, CI, Railway,
  disk ...). Their verdicts are mapped, not recomputed.
* `backend.services.task_receipts` -- the world-digest reader and the
  `schtasks` columns.
* `backend.services.provider_budget` -- the DeepSeek envelope's own view.

WHAT IT ADDS: the learning, universe, books, night-work, machine and lessons rows
that had no single reader, each with the AGE of the evidence compared against a
per-row limit in `config.SYSTEM_STATUS_LIMITS_H`.

RULES IT KEEPS
==============
* Read only. No broker call, no write outside its own receipt/page path, no
  secret read. Paths are explicit (`--optimus-dir`, `--repo`), so it can be
  pointed at the runtime checkout from anywhere.
* A row that prints a date compares it (`judge_age`). A missing, unparsable or
  future date is UNKNOWN, never OK. Nothing is dated by file mtime.
* Exit code: 0 collected; 3 when something REQUIRED could not be determined
  (an empty/failed section, a required row UNKNOWN); 2 with `--strict` and any
  DOWN row. A refusal is therefore never a silent rc 0 by default for the part
  that matters (undeterminable); the system's own reds are the page's job.
* Status words: OK / DEGRADED / DOWN / UNKNOWN. Everything else is mapped.
"""

from __future__ import annotations

import argparse
import html as _html
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as C  # noqa: E402

SCHEMA = "system_status/1"
STATUSES = ("OK", "DEGRADED", "DOWN", "UNKNOWN")
_SEV = {"OK": 0, "UNKNOWN": 1, "DEGRADED": 2, "DOWN": 3}
SECTIONS = (
    ("tasks", "Scheduled tasks"),
    ("learning", "Learning"),
    ("universe", "Universe"),
    ("decisions", "Decisions and books"),
    ("night", "Night work"),
    ("infrastructure", "Infrastructure"),
    ("lessons", "Lessons"),
)
#: A section with no row at all is a failure to determine.
FUTURE_SLACK_S = 300


# ═══════════════════════════════════════════════════════════════ small helpers

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DateOnly(datetime):
    """A stamp parsed from a DATE with no time part (a file named for a local
    day). Only these get the one-day 'ahead of UTC' slack in `judge_age`."""


def parse_ts(v: Any) -> Optional[datetime]:
    """ISO / compact (20261110T163035Z) / date string -> aware UTC datetime, else None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    s = str(v).strip()
    dm = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if dm:
        try:
            return DateOnly(*map(int, dm.groups()), tzinfo=timezone.utc)
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z?", s)
    if m:
        return datetime(*map(int, m.groups()), tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def iso(d: Optional[datetime]) -> Optional[str]:
    return d.astimezone(timezone.utc).isoformat(timespec="seconds") if d else None


def worst(*statuses: str) -> str:
    return max((s for s in statuses if s), key=lambda s: _SEV.get(s, 2), default="OK")


def fmt_age(s: Optional[float]) -> str:
    if s is None:
        return "unknown age"
    s = abs(s)
    if s < 5400:
        return f"{s / 60:.0f} min"
    if s < 172800:
        return f"{s / 3600:.1f} h"
    return f"{s / 86400:.1f} d"


def limit_s(name: str, limits: Optional[dict] = None) -> Optional[float]:
    h = (limits if limits is not None else C.SYSTEM_STATUS_LIMITS_H).get(name)
    return None if h is None else float(h) * 3600.0


def judge_age(stamp: Optional[datetime], now: datetime, lim_s: Optional[float],
              *, down_factor: float = C.SYSTEM_STATUS_DOWN_FACTOR) -> tuple[str, Optional[float], str]:
    """(status, age_s, why). The ONE comparison every dated row goes through.

    No stamp, or a stamp from the future, is UNKNOWN: evidence that cannot be
    dated cannot be fresh. Past the limit DEGRADED; past `down_factor` x limit DOWN.
    """
    if stamp is None:
        return "UNKNOWN", None, "no readable date on the evidence"
    age = (now - stamp).total_seconds()
    if isinstance(stamp, DateOnly) and -86400 <= age < 0:
        age = 0.0   # a date-only stamp (a file named for the owner's local day) may be ahead of UTC;
        #             a full timestamp that happens to be midnight gets no slack (review 3)
    if age < -FUTURE_SLACK_S:
        return "UNKNOWN", age, "evidence is dated in the future"
    if lim_s is None:
        return "UNKNOWN", age, "no limit declared for this row"
    if age > lim_s * down_factor:
        return "DOWN", age, f"{fmt_age(age)} old, limit {fmt_age(lim_s)} x {down_factor:g}"
    if age > lim_s:
        return "DEGRADED", age, f"{fmt_age(age)} old, limit {fmt_age(lim_s)}"
    return "OK", age, ""


def read_json(p: Path) -> Any:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tail_rows(p: Path, n: int = 5, nbytes: int = 262144) -> list[dict]:
    try:
        with open(p, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - nbytes))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for ln in lines[-(n * 3):]:
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out[-n:]


def newest_by_name(folder: Path, pattern: str, stamp_re: str = r"(\d{4}-\d{2}-\d{2}|\d{8}T\d{6}Z?|\d{8})"
                   ) -> tuple[Optional[Path], Optional[datetime]]:
    """The newest file matching `pattern`, DATED BY THE STAMP IN ITS NAME (never mtime)."""
    best: tuple[Optional[datetime], Optional[Path]] = (None, None)
    try:
        files = list(Path(folder).glob(pattern))
    except OSError:
        return None, None
    for p in files:
        m = re.search(stamp_re, p.name)
        if not m:
            continue
        s = m.group(1)
        if re.fullmatch(r"\d{8}", s):
            s = f"{s[:4]}-{s[4:6]}-{s[6:]}"
        d = parse_ts(s)
        if d and (best[0] is None or d > best[0]):
            best = (d, p)
    return best[1], best[0]


def row(section: str, name: str, status: str, detail: str, *, evidence: str = "",
        stamp: Optional[datetime] = None, now: Optional[datetime] = None,
        lim: Optional[float] = None, action: str = "", required: bool = True,
        one_shot: bool = False, extra: Optional[dict] = None) -> dict:
    age = None if (stamp is None or now is None) else (now - stamp).total_seconds()
    return {"section": section, "name": name, "status": status if status in STATUSES else "UNKNOWN",
            "detail": detail, "evidence_path": evidence, "evidence_utc": iso(stamp),
            "age_s": age, "limit_s": lim, "action": action, "required": required,
            "one_shot": one_shot, **({"extra": extra} if extra else {})}


def dated_row(section: str, name: str, content_status: str, detail: str, stamp: Optional[datetime],
              now: datetime, *, evidence: str, action_bad: str, limits: Optional[dict] = None,
              limit_key: Optional[str] = None, required: bool = True, extra: Optional[dict] = None) -> dict:
    """A row whose status is the worse of its content and the age of its evidence."""
    lim = limit_s(limit_key or name, limits)
    a_status, _age, why = judge_age(stamp, now, lim)
    status = worst(content_status, a_status)
    text = detail + (f" [{why}]" if why else "")
    act = "" if status == "OK" else action_bad
    return row(section, name, status, text, evidence=evidence, stamp=stamp, now=now, lim=lim,
               action=act, required=required, extra=extra)


# ═══════════════════════════════════════════════════════════════ probe mapping

#: system_health verdict -> dashboard status. REFUSED is DOWN (a guard's refusal is
#: red); STOPPED_BY_OPERATOR is DEGRADED (a pause carries an expiry).
PROBE_STATUS = {"ALIVE": "OK", "ALIVE_OBSERVE_ONLY": "OK", "STALE": "DEGRADED", "DEAD": "DOWN",
                "REFUSED": "DOWN", "UNKNOWN": "UNKNOWN", "STOPPED_BY_OPERATOR": "DEGRADED"}
PROBE_SECTION = {
    "bars_panel": None,            # replaced by the two bars rows below
    "iif1_night": None,            # replaced by the richer learning row
    "task": "tasks", "daily_pass": "tasks",
    "ranking": "universe", "u_funnel": "universe", "forward_calendar": "universe",
    "u_plan": "decisions", "decision_contract": "decisions", "policy_state": "decisions",
    "sim_session": "decisions", "live_market_loop": "decisions", "book_grader": "decisions",
    "u_review": "decisions",
    "u_forecast": "learning", "forecast_ledger": "learning", "forecast_grader": "learning",
    "learn_rota": "learning", "news_collectors": "learning", "social_sources": "learning",
    "dowjones_feeds": "learning", "optimus_brain": "learning", "accrual_canary": "learning",
    "always_on_lab": "night", "lab_loop": "night", "backtest_leaderboard": "night",
    "public_assets": "night",
}
PROBE_ACTION = {
    "STALE": "Evidence is past its cadence or reports a fault: read the detail, then repair the producer ({proof}).",
    "DEAD": "The process/endpoint is gone: restart it (by task or recorded PID) and re-run this status.",
    "REFUSED": "A guard refused: read the reason, fix its cause (budget, gate, lease); it stays red until fixed.",
    "UNKNOWN": "The evidence is missing: find why {proof} is absent, then re-run this status.",
    "STOPPED_BY_OPERATOR": "Paused on purpose: set an expiry or re-enable it; a pause that never expires is an outage.",
}


def map_probe_row(r: dict) -> Optional[dict]:
    """One `system_health` row -> one dashboard row, or None when a richer row replaces it."""
    probe = str(r.get("probe") or r.get("name") or "")
    sec = PROBE_SECTION.get(probe, "infrastructure")
    if sec is None:
        return None
    verdict = str(r.get("verdict") or "UNKNOWN")
    status = PROBE_STATUS.get(verdict, "UNKNOWN")
    if r.get("state") == "DEGRADED":
        status = worst(status, "DEGRADED")
    # a Railway endpoint that does not answer is UNKNOWN (offline is not a failure)
    if probe == "railway_backend" and verdict == "DEAD":
        status = "UNKNOWN"
    stamp = parse_ts(r.get("evidence_utc"))
    proof = str(r.get("proof") or r.get("evidence") or "")
    name = str(r.get("name") or probe)
    act = "" if status == "OK" else PROBE_ACTION.get(verdict, "Open the evidence and repair its producer.").format(proof=proof or name)
    if probe == "railway_backend" and status == "UNKNOWN":
        act = "Backend unreachable from here (offline or asleep); it is a website surface, not the engine. Re-check later."
    return {"section": sec, "name": name, "status": status,
            "detail": str(r.get("detail") or "")[:400], "evidence_path": proof,
            "evidence_utc": iso(stamp), "age_s": r.get("age_s_now", r.get("age_s")),
            "limit_s": (None if r.get("cadence_s") is None else float(r["cadence_s"]) * 1.25),
            "action": act, "required": probe not in ("railway_backend", "railway_fleet", "ci"),
            "one_shot": False, "extra": {"probe_verdict": verdict, "where": r.get("where")}}


def _short_http_json(url: str, timeout: float) -> tuple:
    """GET -> (json|None, elapsed_s, err). One request, a short timeout, no retry."""
    import time as _t
    import urllib.request
    t0 = _t.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "aegis-system-status/1"})
        with urllib.request.urlopen(req, timeout=min(timeout, C.SYSTEM_STATUS_RAILWAY_TIMEOUT_S)) as fh:  # noqa: S310
            return json.loads(fh.read().decode("utf-8", "replace")), round(_t.time() - t0, 2), None
    except Exception as exc:  # noqa: BLE001
        return None, round(_t.time() - t0, 2), type(exc).__name__


def raw_probe_rows(ctx: Any) -> list[dict]:
    """The `system_health` probe table WITHOUT its public-view redaction.

    `system_health.run_probes` ends by passing every red row through `public_row`,
    which replaces the detail with "service evidence failed; consult private
    receipt" so the table can be published. This dashboard is the private
    surface that sentence points at: local, gitignored, never served off-box. So
    it runs the same probes and keeps the detail. Nothing is recomputed.
    """
    from backend.services import system_health as SH
    rows: list[dict] = []
    for p in SH.PROBES:
        if p.needs_proc and not ctx.allow_proc:
            rows.append(SH._row(p, p.name, SH._unknown("not run: --no-proc")))
            continue
        try:
            out = p.fn(ctx)
        except Exception as exc:  # noqa: BLE001
            out = SH._unknown(f"probe unavailable ({type(exc).__name__})", error_type=type(exc).__name__)
        for sub, r in (out.items() if isinstance(out, dict) else [(None, out)]):
            rows.append(SH._row(p, f"{p.name}:{sub}" if sub is not None else p.name, r))
    for r in rows:
        r["age_s_now"] = SH._age(SH._ts(r.get("evidence_utc")), ctx.now)
    return rows


def group_loops(rows: list[dict], *, min_group: int = 4) -> list[dict]:
    """Collapse the lab's per-loop rows that share one verdict into one row.

    Twelve `lab_loop:*` rows all saying "stopped on purpose" are one fact (the lab
    is OFF), and listing them twelve times buries the reds that differ.
    """
    out, groups = [], {}
    for r in rows:
        if str(r["name"]).startswith("lab_loop:"):
            groups.setdefault((r["status"], (r.get("extra") or {}).get("probe_verdict")), []).append(r)
        else:
            out.append(r)
    for (_st, _v), g in groups.items():
        if len(g) < min_group:
            out.extend(g)
            continue
        first = dict(g[0])
        first["name"] = f"lab_loops ({len(g)} loops)"
        first["detail"] = f"{len(g)} loops share this state: " + ", ".join(x["name"].split(":", 1)[1] for x in g)[:300]
        out.append(first)
    return out


def tasks_section(ctx: Any, now: datetime, probe_rows: list[dict]) -> list[dict]:
    """Scheduled tasks: the probe judge (receipt-based) + schtasks' own columns."""
    from backend.services import system_health as SH
    out: list[dict] = []
    schtasks = SH._schtasks(ctx)
    if schtasks is None:
        return [row("tasks", "scheduler", "UNKNOWN",
                    "`schtasks /query` could not be read, so which tasks exist cannot be derived",
                    evidence="schtasks /query /fo CSV /v", now=now,
                    action="Run `schtasks /query /fo CSV /v` by hand; if it fails the scheduler service is the problem.")]
    one_shot = [re.compile(p) for p in C.SYSTEM_STATUS_ONE_SHOT_TASK_PATTERNS]
    by_name = {r["name"].split(":", 1)[1]: r for r in probe_rows
               if r.get("probe") == "task" and ":" in r["name"]}
    for name in sorted(set(schtasks) | set(by_name)):
        sch = schtasks.get(name) or {}
        last_run, last_res = sch.get("Last Run Time", ""), sch.get("Last Result", "")
        next_run, state = sch.get("Next Run Time", ""), sch.get("Scheduled Task State", "")
        pr = by_name.get(name)
        mapped = map_probe_row(pr) if pr else None
        # review 3: with no receipt reader the scheduler's "Last Result 0" is not
        # evidence the job did anything (10-15 -> 11-10 ran rc 0 while refused)
        status = mapped["status"] if mapped else "UNKNOWN"
        flags = []
        never = str(last_res).strip() == "267011" or "N/A" in str(last_run)
        running = str(last_res).strip() == "267009"
        if str(last_res).strip() not in ("", "0", "267011", "267009", "267008", "267010") and re.fullmatch(r"-?\d+", str(last_res).strip()):
            flags.append(f"last result {last_res} (non-zero)")
            status = worst(status, "DEGRADED")
        if never:
            flags.append("has never run")
            status = worst(status, "DEGRADED")
        if state.strip().lower() == "disabled":
            flags.append("DISABLED")
            status = worst(status, "DEGRADED")
        elif next_run.strip() in ("N/A", "") and not never and not running:
            flags.append("no next run scheduled")
            status = worst(status, "DEGRADED")
        is_one = any(p.search(name) for p in one_shot)
        detail = (f"last run {last_run or '-'} result {last_res or '-'}; next {next_run or '-'}"
                  + (f"; {', '.join(flags)}" if flags else "")
                  + (f"; receipt: {mapped['detail'][:200]}" if mapped else
                     ("; exit 0 with no receipt read" if str(last_res).strip() == "0" else "")
                     + "; scheduler view only (no receipt reader declared)"))
        act = "" if status == "OK" else (
            (mapped["action"] if mapped and mapped["action"] else
             "Open Task Scheduler for this task and read its receipt; declare a receipt reader "
             "(system_health task probe) so this row can be judged.")
            + (" One-shot: delete it once its job is done." if is_one else ""))
        out.append(row("tasks", name, status, detail,
                       evidence=(mapped or {}).get("evidence_path") or "schtasks",
                       stamp=parse_ts((mapped or {}).get("evidence_utc")), now=now,
                       lim=(mapped or {}).get("limit_s"), action=act, required=bool(mapped) and not is_one, one_shot=is_one,
                       extra={"last_run": last_run, "last_result": last_res, "next_run": next_run, "state": state}))
    if not out:
        out.append(row("tasks", "scheduler", "UNKNOWN", "no Aegis* tasks found and none declared",
                       evidence="schtasks", now=now, action="Register the tasks (task_keeper --register) or check the filter."))
    return out


# ═══════════════════════════════════════════════════════════════ learning

def learning_rows(optimus: Path, now: datetime, ctx: Any, limits: Optional[dict]) -> list[dict]:
    out: list[dict] = []
    # --- DeepSeek envelope
    env_p = optimus / "session_budget" / "deepseek_local.json"
    try:
        from backend.services import provider_budget as PB
        if not env_p.exists():
            raise FileNotFoundError(str(env_p))
        # review 3 (#97): read through the guard's own view, which applies the
        # deferred-settlement sidecar (and any block it carries) in memory, so
        # the row shows true spend; a raw _load does not see it.
        view = PB._peek(env_p)
        held, cap = PB._held(view) / PB.SCALE, view["cap_units"] / PB.SCALE
        room = view["cap_units"] - PB._held(view)
        starts = [parse_ts(c.get("started_utc")) for c in view["calls"].values()]
        last_call = max((s for s in starts if s), default=None)
        st = "OK"
        bits = [f"{view.get('month') or view.get('session_id')}: ${held:.4f} of ${cap:.2f} cap, "
                f"{len(view['calls'])} calls"]
        pending = view.get("sidecar_pending") or 0
        if pending:
            age_h = view.get("sidecar_oldest_age_h")
            lim_h = float(getattr(C, "DEEPSEEK_SIDECAR_STALE_HOURS", 12.0))
            bits.append(f"{pending} deferred settlement(s) in the sidecar, counted in held ("
                        + ("age unknown" if age_h is None else f"oldest {age_h:.1f} h") + ")")
            if age_h is None or age_h > lim_h:
                st = "DEGRADED"
        if view.get("blocked"):
            st, bits = "DOWN", bits + [f"BLOCKED ({str(view['blocked'])[:80]})"]
        elif room < PB.MIN_RESERVATION_UNITS:
            st, bits = "DOWN", bits + ["EXHAUSTED: every call refuses"]
        elif held / cap >= 0.8:
            st, bits = "DEGRADED", bits + ["over 80% of the cap"]
        out.append(dated_row("learning", "deepseek_envelope", st, "; ".join(bits), last_call, now,
                             evidence=f"session_budget/{env_p.name} calls[*].started_utc",
                             action_bad="Raise the cap with `python -m backend.services.provider_budget` (attended) or let the month roll; a refusal must stay red.",
                             limits=limits))
    except Exception as exc:  # noqa: BLE001
        out.append(row("learning", "deepseek_envelope", "UNKNOWN",
                       f"envelope unreadable ({type(exc).__name__}): spend UNKNOWN", evidence=str(env_p), now=now,
                       action="Create/repair the envelope (`python -m backend.services.provider_budget status`); without it the guard refuses every call."))
    # --- world digest
    try:
        from backend.services import task_receipts as TR
        rd = TR.r_world_digest(ctx, None)
        st = {"OK": "OK", "IDLE": "OK", "DEGRADED": "DEGRADED", "STOPPED": "DEGRADED", "REFUSED": "DOWN",
              "DEAD": "DOWN"}.get(rd.status, "DEGRADED")
        if rd.unknown_reason:
            st = "UNKNOWN"
        p, d = TR._newest(optimus / "digest", "world_digest_*.json")
        typed = d.get("n_rows") if isinstance(d, dict) else None
        written = ((d.get("writes") or {}).get("n_rows") if isinstance(d, dict) else None)
        detail = (f"{rd.detail or rd.unknown_reason}; typed rows {typed}, predictions written {written}"
                  + (f"; {rd.reason}" if rd.reason else ""))
        if typed == 0:
            st = worst(st, "DOWN")
        elif typed is None:
            st = worst(st, "UNKNOWN")                 # no typed count: cannot be judged (review 3)
        out.append(dated_row("learning", "world_digest", st, detail, rd.stamp, now,
                             evidence=rd.proof or "digest/world_digest_*.json", limits=limits,
                             action_bad="0 typed rows or a budget refusal means the learner is starved: read the digest's spend/refusal receipt and fix the cause (CH-04)."))
    except Exception as exc:  # noqa: BLE001
        out.append(row("learning", "world_digest", "UNKNOWN", f"unreadable ({type(exc).__name__})",
                       evidence="digest/world_digest_*.json", now=now, action="Run the digest by hand and read its receipt."))
    # --- learner
    runs = tail_rows(optimus / "brain" / "learn_runs.jsonl", 1)
    if runs:
        r = runs[-1]
        s = str(r.get("status") or "")
        cst = ("OK" if s.upper() in ("LEARNED", "OK") else "DEGRADED" if "DEGRADED" in s.upper() else "DOWN"
               if any(k in s.upper() for k in ("REFUS", "ERROR", "FAIL", "VOID", "BUDGET")) else "DEGRADED")
        out.append(dated_row("learning", "learner", cst,
                             f"status {s or '?'}; rules written {r.get('n_rules_written')}; {str(r.get('reason') or '')[:160]}",
                             parse_ts(r.get("written_utc")), now, evidence="brain/learn_runs.jsonl (last row)",
                             limits=limits, action_bad="Read the row's `reason`; no new graded rows means the loop upstream of the learner is idle."))
    else:
        out.append(row("learning", "learner", "UNKNOWN", "brain/learn_runs.jsonl has no readable row",
                       evidence="brain/learn_runs.jsonl", now=now, action="Run `python -m scripts.learner_run` and read its receipt."))
    # --- reputation refit
    p, d = newest_by_name(optimus / "reputation", "reputation_*.json")
    out.append(dated_row("learning", "reputation_refit", "OK" if p else "UNKNOWN",
                         f"newest refit {p.name}" if p else "no reputation_*.json found", d, now,
                         evidence=f"reputation/{p.name}" if p else "reputation/", limits=limits,
                         action_bad="Refit the reputation table; the learner weights rules by it."))
    # --- IIF-1 night
    p, d = newest_by_name(optimus / "iif1_nights", "20*.json")
    j = read_json(p) if p else None
    if isinstance(j, dict):
        s = str(j.get("status") or "")
        cst = "OK" if s.upper() in ("OK", "COMPLETE", "COMPLETED", "DONE") and (j.get("records_written") or 0) > 0 else \
              "DOWN" if "VOID" in s.upper() or (j.get("records_written") or 0) == 0 else "DEGRADED"
        out.append(dated_row("learning", "iif1_night", cst,
                             f"night {j.get('night')}: status {s}, records_written {j.get('records_written')}, spend ${j.get('spend_usd')}"
                             + (f", void: {str(j.get('void_reason'))[:100]}" if j.get("void_reason") else ""),
                             parse_ts(j.get("night")) or d, now, evidence=f"iif1_nights/{p.name}", limits=limits,
                             action_bad="IIF-1 is VOID or silent: fix its upstream (budget, digest) then run its night job."))
    else:
        out.append(row("learning", "iif1_night", "UNKNOWN", "no readable iif1_nights/*.json", evidence="iif1_nights/",
                       now=now, action="Run the IIF-1 night job and read its receipt."))
    # --- hyp_lab
    hl = tail_rows(optimus / "hyp_lab" / "ledger.jsonl", 3)
    if hl:
        r = hl[-1]
        txt = " ".join(str(r.get(k) or "") for k in ("status", "verdict", "reason")).upper()
        # the learner row's keyword set (review 3): REFUSED/ERROR/VOID/FAIL are red too
        cst = "DOWN" if any(k in txt for k in ("REFUS", "ERROR", "FAIL", "VOID", "BUDGET")) else "OK"
        out.append(dated_row("learning", "hyp_lab", cst,
                             f"last row {r.get('kind')} {r.get('hyp_id')} {r.get('status')} {r.get('verdict') or ''}".strip(),
                             parse_ts(r.get("utc")), now, evidence="hyp_lab/ledger.jsonl (last row)", limits=limits,
                             action_bad="Hypothesis lab is idle or budget-refused: check the envelope row, then its scheduled task."))
    else:
        out.append(row("learning", "hyp_lab", "UNKNOWN", "hyp_lab/ledger.jsonl has no readable row",
                       evidence="hyp_lab/ledger.jsonl", now=now, action="Run the lab once and read its ledger."))
    return out


# ═══════════════════════════════════════════════════════════════ universe

def parquet_max_date(p: Path) -> tuple[Optional[datetime], str]:
    """Newest `date` in a parquet panel, from row-group statistics (cheap), else a column read."""
    try:
        import pyarrow.compute as pc
        import pyarrow.parquet as pq
        f = pq.ParquetFile(p)
        names = list(f.schema_arrow.names)
        col = next((c for c in ("date", "Date", "dt", "timestamp") if c in names), None)
        if col is None:
            return None, f"no date column in {names[:6]}"
        i = names.index(col)
        best = None
        for g in range(f.metadata.num_row_groups):
            st = f.metadata.row_group(g).column(i).statistics
            if st is None or not st.has_min_max:
                best = None
                break
            best = st.max if best is None or st.max > best else best
        if best is None:
            best = pc.max(pq.read_table(p, columns=[col])[col]).as_py()
        return parse_ts(str(best)[:19] if best is not None else None), ""
    except Exception as exc:  # noqa: BLE001
        return None, type(exc).__name__


def universe_rows(optimus: Path, data_dir: Path, now: datetime, limits: Optional[dict]) -> list[dict]:
    out: list[dict] = []
    opt_rows = set(C.SYSTEM_STATUS_OPTIONAL_ROWS)
    # --- the universe graph receipt (CH-30 writes it; absent until then)
    gp, gd = newest_by_name(optimus / "universe_graph", "*.json")
    g = read_json(gp) if gp else None
    if isinstance(g, dict):
        nodes = g.get("nodes_by_type") or g.get("n_nodes")
        edges = g.get("edges_by_type") or g.get("n_edges")
        st = str(g.get("status") or "UNKNOWN")        # no status field is not OK (review 3)
        cst = ("OK" if st.upper() in ("OK", "ALIVE", "BUILT") else
               "UNKNOWN" if st == "UNKNOWN" else "DEGRADED")
        newest_bar = g.get("newest_bar_date")
        out.append(dated_row("universe", "universe_graph", cst,
                             f"nodes {nodes}; edges {edges}; newest bar {newest_bar}; status {st}",
                             parse_ts(g.get("generated_utc") or g.get("generated_at")) or gd, now,
                             evidence=f"universe_graph/{gp.name}", limits=limits,
                             action_bad="Rebuild the graph (CH-30 nightly job) and read its receipt.",
                             required="universe_graph" not in opt_rows))
    else:
        out.append(row("universe", "universe_graph", "UNKNOWN",
                       "no universe_graph receipt yet (CH-30 writes it)", evidence="universe_graph/*.json", now=now,
                       action="CH-30 builds this receipt; until then the universe is the funnel list only.",
                       required="universe_graph" not in opt_rows))
    # --- the funnel snapshot
    fp = data_dir / "funnel_night10.json"
    f = read_json(fp)
    if isinstance(f, dict):
        uni = f.get("universe")
        usz = len(uni) if hasattr(uni, "__len__") and not isinstance(uni, (int, float)) else uni
        cands = f.get("candidates") or []
        fails = f.get("failures") or []
        cst = "DEGRADED" if fails else "OK"
        if not cands:
            cst = "DOWN"
        out.append(dated_row("universe", "funnel", cst,
                             f"{len(cands)} candidates; universe block {usz}; failures {len(fails)}",
                             parse_ts(f.get("generated_at")), now, evidence=f"{fp.name} generated_at", limits=limits,
                             action_bad="Rebuild: `python -m backend.services.opportunity_funnel` (it refuses, without overwriting, when a stage fails)."))
    else:
        out.append(row("universe", "funnel", "UNKNOWN", f"{fp.name} unreadable or absent", evidence=str(fp), now=now,
                       action="Rebuild the funnel snapshot; a ranking over an unread candidate set is the 2026-09-22 failure."))
    # --- bars panels
    for label, rel in (("prices_2025_26", "prices_2025_26/bars.parquet"), ("prices_deep", "prices_deep/bars.parquet")):
        p = optimus / rel
        if not p.exists():
            out.append(row("universe", f"bars:{label}", "UNKNOWN", f"no panel at {rel}", evidence=rel, now=now,
                           action="Pull/refresh the panel (bars_refresh)."))
            continue
        d, why = parquet_max_date(p)
        out.append(dated_row("universe", f"bars:{label}", "OK" if d else "UNKNOWN",
                             f"newest bar {d.date() if d else '?'}" + (f" ({why})" if why else ""), d, now,
                             evidence=f"{rel} max(date)", limits=limits,
                             action_bad="Refresh the panel; every ranker and grader reads it."))
    return out


# ═══════════════════════════════════════════════════════════════ decisions / books

def _unprotected(acct: dict) -> list[str]:
    """Positions with no resting stop in the account's own stop_table."""
    have = {s.get("symbol") for s in (acct.get("stop_table") or []) if isinstance(s, dict) and s.get("resting")}
    return [p.get("symbol") for p in (acct.get("positions") or []) if isinstance(p, dict)
            and p.get("symbol") not in have]


def decision_rows(optimus: Path, now: datetime, limits: Optional[dict]) -> list[dict]:
    out: list[dict] = []
    p, d = newest_by_name(optimus / "decisions" / "pc_plan", "20*.json")
    j = read_json(p) if p else None
    if isinstance(j, dict):
        n = len(j.get("rows") or [])
        out.append(dated_row("decisions", "pc_plan", "OK" if n else "DEGRADED",
                             f"plan {p.stem}: {n} rows; source {j.get('source')}", d, now,
                             evidence=f"decisions/pc_plan/{p.name}", limits=limits,
                             action_bad="No fresh plan: check the planner unit (u_plan) and the funnel row."))
    else:
        out.append(row("decisions", "pc_plan", "UNKNOWN", "no readable decisions/pc_plan/20*.json",
                       evidence="decisions/pc_plan/", now=now, action="Run the planner and read its receipt."))
    # paper accounts from the newest fleet-manager run (a receipt; no broker call)
    runs = optimus / "paper_accounts" / "fleet_manager" / "runs"
    rp, _rd = newest_by_name(runs, "run_*.json", r"(\d{8}T\d{6}Z)")
    rj = read_json(rp) if rp else None
    if not isinstance(rj, dict) or not isinstance(rj.get("accounts"), list):
        out.append(row("decisions", "paper_accounts", "UNKNOWN", "no readable fleet_manager run receipt",
                       evidence="paper_accounts/fleet_manager/runs/", now=now,
                       action="Run the fleet manager pass (attended) or read why its task wrote nothing."))
        return out
    stamp = parse_ts(rj.get("finished_utc") or rj.get("started_utc"))
    for a in rj["accounts"]:
        if not isinstance(a, dict):
            continue
        if a.get("role") in set(getattr(C, "PAPER_ACCOUNTS_RETIRED_UNREADABLE", ()) or ()):
            out.append(row("decisions", f"account:{a.get('role')}", "OK",
                           f"retired, excused by config.PAPER_ACCOUNTS_RETIRED_UNREADABLE (status {a.get('status')})",
                           evidence=f"paper_accounts/fleet_manager/runs/{rp.name}", stamp=stamp, now=now, required=False))
            continue
        unp = _unprotected(a)
        rec = (a.get("reconcile") or {}).get("status")
        cst = "OK"
        notes = []
        if str(a.get("status")).lower() not in ("ok",):
            cst, notes = "DEGRADED", notes + [f"status {a.get('status')}"]
        if rec not in (None, "OK"):
            cst, notes = worst(cst, "DEGRADED"), notes + [f"reconcile {rec}"]
        if unp:
            cst, notes = "DOWN", notes + [f"UNPROTECTED {unp}"]
        try:
            eq = f"${float(a.get('equity')):,.2f}"
        except (TypeError, ValueError):
            eq = "equity unknown"
        out.append(dated_row("decisions", f"account:{a.get('role')}", cst,
                             f"{eq}; {a.get('n_positions')} positions; {len(unp)} unprotected; pass {rj.get('pass')}"
                             + (f"; {', '.join(notes)}" if notes else ""),
                             stamp, now, evidence=f"paper_accounts/fleet_manager/runs/{rp.name}", limits=limits,
                             limit_key="paper_accounts",
                             action_bad="A position without a resting stop is the worst case here: place the stop (attended) or flatten; otherwise re-run the fleet pass.",
                             extra={"equity": a.get("equity"), "n_positions": a.get("n_positions"), "unprotected": unp}))
    return out


# ═══════════════════════════════════════════════════════════════ night work

def night_rows(optimus: Path, now: datetime, limits: Optional[dict]) -> list[dict]:
    out: list[dict] = []
    hist = tail_rows(optimus / "nn_lab_history.jsonl", 1)
    if hist:
        r = hist[-1]
        out.append(dated_row("night", "nn_lab", "OK", f"last row head {r.get('head')} held-out {r.get('held_out_month')} IC {r.get('ic')}",
                             parse_ts(r.get("written_utc")), now, evidence="nn_lab_history.jsonl (last row)", limits=limits,
                             action_bad="The NN lab has not written for a while: check its night task and the GPU/RAM gates."))
    else:
        out.append(row("night", "nn_lab", "UNKNOWN", "nn_lab_history.jsonl has no readable row",
                       evidence="nn_lab_history.jsonl", now=now, action="Run the NN lab and read its receipt."))
    try:
        dirs = [x for x in optimus.glob("night_factory_20*") if x.is_dir()]
    except OSError:
        dirs = []
    best = None
    for dd in dirs:
        t = parse_ts(dd.name.replace("night_factory_", ""))
        if t and (best is None or t > best[0]):
            best = (t, dd)
    if best:
        n_files = sum(1 for _ in best[1].iterdir()) if best[1].exists() else 0
        out.append(dated_row("night", "night_factory", "OK" if n_files else "DEGRADED",
                             f"{best[1].name}: {n_files} files", best[0], now, evidence=best[1].name, limits=limits,
                             action_bad="The night factory wrote nothing recent: check the night launcher task."))
    else:
        out.append(row("night", "night_factory", "UNKNOWN", "no night_factory_* folder", evidence="night_factory_*",
                       now=now, action="Run the night launcher and read its receipt."))
    return out


# ═══════════════════════════════════════════════════════════════ machine

def _ram_free_gb() -> Optional[float]:
    if sys.platform == "win32":
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return m.ullAvailPhys / 1024 ** 3
        return None
    try:
        for ln in Path("/proc/meminfo").read_text().splitlines():
            if ln.startswith("MemAvailable"):
                return int(ln.split()[1]) / 1024 ** 2
    except OSError:
        pass
    return None


def _boot_time(now: datetime) -> Optional[datetime]:
    if sys.platform == "win32":
        import ctypes
        try:
            return now - timedelta(milliseconds=int(ctypes.windll.kernel32.GetTickCount64()))
        except Exception:  # noqa: BLE001
            return None
    try:
        return now - timedelta(seconds=float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError):
        return None


def _powercfg(run: Callable[[list, float], tuple]) -> Optional[tuple[int, int]]:
    """(AC seconds, battery seconds) of 'Sleep after', or None. 0 = never sleeps."""
    rc, txt = run(["powercfg", "/query", "SCHEME_CURRENT", "SUB_SLEEP", "STANDBYIDLE"], 20)
    if rc != 0 or not txt:
        return None
    ac = re.search(r"Current AC Power Setting Index:\s*0x([0-9a-fA-F]+)", txt)
    dc = re.search(r"Current DC Power Setting Index:\s*0x([0-9a-fA-F]+)", txt)
    if not (ac and dc):
        return None
    return int(ac.group(1), 16), int(dc.group(1), 16)


def _default_run(argv: list, timeout: float) -> tuple:
    try:
        cp = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)  # noqa: S603
        return cp.returncode, (cp.stdout or "")
    except Exception:  # noqa: BLE001
        return 127, ""


def machine_rows(now: datetime, *, run: Callable[[list, float], tuple] = _default_run,
                 ram_free: Callable[[], Optional[float]] = _ram_free_gb,
                 boot: Callable[[datetime], Optional[datetime]] = _boot_time,
                 repo_slug: str = "Murathanx12/Aegis-Finance") -> list[dict]:
    out: list[dict] = []
    ram = ram_free()
    if ram is None:
        out.append(row("infrastructure", "ram_free", "UNKNOWN", "free RAM could not be read", now=now,
                       evidence="GlobalMemoryStatusEx", action="Check Task Manager; builders and the lab need >= 3 GB free."))
    else:
        st = "DOWN" if ram < C.SYSTEM_STATUS_RAM_DOWN_GB else "DEGRADED" if ram < C.SYSTEM_STATUS_RAM_DEGRADED_GB else "OK"
        out.append(row("infrastructure", "ram_free", st, f"{ram:.1f} GB free (degraded < {C.SYSTEM_STATUS_RAM_DEGRADED_GB} GB)",
                       evidence="GlobalMemoryStatusEx (live)", now=now,
                       action="" if st == "OK" else "Close the largest browser/builder process by PID; do not start long jobs."))
    b = boot(now)
    if b is None:
        out.append(row("infrastructure", "last_boot", "UNKNOWN", "boot time could not be read", now=now,
                       evidence="GetTickCount64", action="Check `systeminfo | find \"Boot Time\"`."))
    else:
        up_d = (now - b).total_seconds() / 86400
        st = "DEGRADED" if up_d > C.SYSTEM_STATUS_UPTIME_DEGRADED_DAYS else "OK"
        out.append(row("infrastructure", "last_boot", st, f"booted {iso(b)} ({up_d:.1f} days up)", evidence="GetTickCount64 (live)",
                       stamp=b, now=now, action="" if st == "OK" else "Reboot in a quiet window; updates and leaks pile up."))
    pc = _powercfg(run) if sys.platform == "win32" else None
    if pc is None:
        out.append(row("infrastructure", "sleep_settings", "UNKNOWN", "powercfg could not be read" if sys.platform == "win32"
                       else "not a Windows host", evidence="powercfg /query SUB_SLEEP STANDBYIDLE", now=now,
                       action="Run `powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE` by hand."))
    else:
        ac, dc = pc
        fmt = lambda s: "never" if s == 0 else f"{s // 60} min"  # noqa: E731
        st = "OK" if ac == 0 else "DEGRADED"
        out.append(row("infrastructure", "sleep_settings", st, f"sleep after: on AC {fmt(ac)}, on battery {fmt(dc)}",
                       evidence="powercfg /query SUB_SLEEP STANDBYIDLE", now=now,
                       action="" if st == "OK" else "The PC sleeps on AC, so scheduled night work stops: `powercfg /change standby-timeout-ac 0`."))
    rc, txt = run(["gh", "pr", "list", "--repo", repo_slug, "--state", "open", "--json", "number", "--limit", "100"], 30)
    try:
        n = len(json.loads(txt)) if rc == 0 else None
    except ValueError:
        n = None
    if n is None:
        out.append(row("infrastructure", "open_prs", "UNKNOWN", "`gh pr list` failed (offline or not logged in)", now=now,
                       evidence="gh pr list", required=False, action="`gh auth status`; not an engine failure."))
    else:
        out.append(row("infrastructure", "open_prs", "OK", f"{n} open PR(s)", evidence="gh pr list", now=now, required=False))
    return out


# ═══════════════════════════════════════════════════════════════ lessons

def lesson_rows(optimus: Path, now: datetime, limits: Optional[dict], n: int = 5) -> list[dict]:
    p = optimus / "brain" / "learned_rules.jsonl"
    rows = tail_rows(p, 400, nbytes=2_000_000)
    dated = sorted(((parse_ts(r.get("created_utc")), r) for r in rows if r.get("rule_text")),
                   key=lambda t: t[0] or datetime.min.replace(tzinfo=timezone.utc))
    if not dated:
        return [row("lessons", "learned_rules", "UNKNOWN", "brain/learned_rules.jsonl has no readable rule",
                    evidence="brain/learned_rules.jsonl", now=now, action="The learner has written no rule: see the learner row.")]
    out = [dated_row("lessons", "learned_rules", "OK", f"newest rule written {iso(dated[-1][0])}", dated[-1][0], now,
                     evidence="brain/learned_rules.jsonl created_utc", limits=limits, limit_key="lessons",
                     action_bad="No new lesson recently: the learner is starved or idle (see the Learning rows).")]
    for ts, r in reversed(dated[-n:]):
        out.append(row("lessons", f"rule {r.get('rule_id')}", "OK", str(r.get("rule_text"))[:300],
                       evidence="brain/learned_rules.jsonl", stamp=ts, now=now, required=False,
                       extra={"kind": r.get("kind"), "source": r.get("source")}))
    return out


# ═══════════════════════════════════════════════════════════════ collect

def collect(*, optimus_dir: Path, repo: Path, now: Optional[datetime] = None, allow_proc: bool = True,
            limits: Optional[dict] = None, probe_rows_in: Optional[list[dict]] = None,
            ctx: Any = None, run: Callable[[list, float], tuple] = _default_run) -> dict:
    """Build the receipt. Never raises: a section that fails is an error + an UNKNOWN row."""
    now = now or utcnow()
    optimus_dir, repo = Path(optimus_dir), Path(repo)
    data_dir = optimus_dir.parent
    sections: dict[str, dict] = {k: {"title": t, "rows": [], "error": None} for k, t in SECTIONS}

    def guard(key: str, fn: Callable[[], list[dict]]) -> None:
        try:
            sections[key]["rows"].extend(fn())
        except Exception as exc:  # noqa: BLE001
            sections[key]["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            sections[key]["rows"].append(row(key, f"{key}_collector", "UNKNOWN",
                                             f"section collector failed ({type(exc).__name__})", now=now,
                                             action="Fix the collector (scripts/system_status.py) -- the section cannot be trusted."))

    probes: list[dict] = list(probe_rows_in or [])
    if probe_rows_in is None:
        try:
            from backend.services import system_health as SH
            ctx = ctx or SH.make_ctx(optimus_dir=optimus_dir, now=now, allow_proc=allow_proc, repo=repo,
                                     http_json=_short_http_json)
            probes = raw_probe_rows(ctx)
        except Exception as exc:  # noqa: BLE001
            sections["infrastructure"]["error"] = f"probes: {type(exc).__name__}"
            sections["infrastructure"]["rows"].append(row("infrastructure", "system_health_probes", "UNKNOWN",
                                                         f"the probe table could not run ({type(exc).__name__})", now=now,
                                                         action="Run `python -m scripts.health_probe` and read the error."))
    guard("tasks", lambda: tasks_section(ctx, now, probes) if ctx is not None
          else [row("tasks", "scheduler", "UNKNOWN", "no probe context", now=now, action="Re-run with probes enabled.")])
    guard("learning", lambda: learning_rows(optimus_dir, now, ctx, limits))
    guard("universe", lambda: universe_rows(optimus_dir, data_dir, now, limits))
    guard("decisions", lambda: decision_rows(optimus_dir, now, limits))
    guard("night", lambda: night_rows(optimus_dir, now, limits))
    guard("infrastructure", lambda: machine_rows(now, run=run))
    guard("lessons", lambda: lesson_rows(optimus_dir, now, limits))
    mapped_probes = [m for m in (map_probe_row(p_) for p_ in probes if p_.get("probe") != "task") if m]
    for m in group_loops(mapped_probes):
        sections[m["section"]]["rows"].append(m)
    # worst first inside each section
    for s in sections.values():
        s["rows"].sort(key=lambda r: (-_SEV[_st(r)], r["name"]))
    counted = [r for s in sections.values() for r in s["rows"] if not r.get("one_shot")
               and not r["name"].startswith("rule ")]
    counts = {k: sum(1 for r in counted if r["status"] == k) for k in STATUSES}
    rec = {"receipt": SCHEMA, "generated_utc": iso(now), "optimus_dir": str(optimus_dir), "repo": str(repo),
           "allow_proc": allow_proc, "counts": counts, "sections": sections,
           "read_me_first": "Read-only. Every dated row compares its evidence date to a limit in config.SYSTEM_STATUS_LIMITS_H; "
                            "UNKNOWN means the evidence is missing, never fine. No broker was called."}
    rec["exit_code"] = exit_code(rec)
    rec["undetermined"] = undetermined(rec)
    return rec


def undetermined(rec: dict) -> list[str]:
    """What the collector failed to determine (drives exit 3)."""
    bad = []
    for key, s in rec["sections"].items():
        if s.get("error"):
            bad.append(f"{key}: collector error {s['error']}")
        if not s["rows"]:
            bad.append(f"{key}: no rows")
        for r in s["rows"]:
            if r["status"] == "UNKNOWN" and r.get("required") and not r.get("one_shot"):
                bad.append(f"{key}/{r['name']}: UNKNOWN ({r['detail'][:80]})")
    return bad


def exit_code(rec: dict, *, strict: bool = False) -> int:
    if undetermined(rec):
        return 3
    if strict and rec["counts"].get("DOWN"):
        return 2
    return 0


def header_line(rec: dict) -> str:
    c = rec["counts"]
    return f"{c['OK']} OK · {c['DEGRADED']} degraded · {c['DOWN']} down · {c['UNKNOWN']} unknown"


def reds(rec: dict) -> list[dict]:
    rows = [r for s in rec["sections"].values() for r in s["rows"] if _st(r) != "OK"
            and not r.get("one_shot")]
    return sorted(rows, key=lambda r: (-_SEV[_st(r)], str(r.get("section")), str(r.get("name"))))


def _st(r: dict) -> str:
    """A row's status, normalised: anything outside STATUSES is UNKNOWN (a stale
    or foreign status.json can carry anything)."""
    s = r.get("status")
    return s if s in STATUSES else "UNKNOWN"


# ═══════════════════════════════════════════════════════════════ rendering

def render_text(rec: dict) -> str:
    L = [f"AEGIS SYSTEMS STATUS  {rec['generated_utc']}", header_line(rec), ""]
    red = reds(rec)
    if red:
        L.append("NEEDS ATTENTION")
        for r in red:
            L.append(f"  [{_st(r):<8}] {r['section']}/{r['name']} -- {r['detail'][:150]}")
            if r.get("action"):
                L.append(f"             -> {r['action']}")
        L.append("")
    for key, s in rec["sections"].items():
        L.append(f"{s['title'].upper()} ({len(s['rows'])})")
        for r in s["rows"]:
            tag = "one-shot" if r.get("one_shot") else _st(r)
            L.append(f"  {tag:<8} {r['name']:<34} {r['detail'][:110]}")
        L.append("")
    if rec.get("undetermined"):
        L.append("COULD NOT DETERMINE (exit 3): " + "; ".join(rec["undetermined"][:8]))
    return "\n".join(L)


_CSS = """
:root{--bg:#f6f7f9;--fg:#15181c;--mut:#5d6672;--card:#fff;--line:#dde1e6;--ok:#1a7f4b;--deg:#a35c00;--down:#c62828;--unk:#5d6672}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0e1115;--fg:#e6e8ea;--mut:#98a1ac;--card:#161b21;--line:#2a313a;--ok:#4cc38a;--deg:#e8a23a;--down:#ff6b6b;--unk:#98a1ac}}
:root[data-theme=dark]{--bg:#0e1115;--fg:#e6e8ea;--mut:#98a1ac;--card:#161b21;--line:#2a313a;--ok:#4cc38a;--deg:#e8a23a;--down:#ff6b6b;--unk:#98a1ac}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:14px;align-items:baseline;flex-wrap:wrap;z-index:2}
h1{font-size:15px;margin:0;letter-spacing:.02em}.hl{font-weight:600;font-size:14px}.mut{color:var(--mut)}
main{padding:12px 16px;max-width:1200px;margin:0 auto}h2{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin:16px 0 6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.r{display:grid;grid-template-columns:78px 220px 1fr;gap:10px;padding:6px 12px;border-top:1px solid var(--line);align-items:baseline}.r:first-child{border-top:0}
.b{font-size:11px;font-weight:700;text-align:center;border-radius:4px;padding:1px 0;color:#fff}
.OK{background:var(--ok)}.DEGRADED{background:var(--deg)}.DOWN{background:var(--down)}.UNKNOWN{background:var(--unk)}
.n{font-weight:600;overflow-wrap:anywhere}.d{overflow-wrap:anywhere}.a{color:var(--mut);display:block;font-size:12px}.ev{color:var(--mut);font-size:11px}
.act{display:block;color:var(--fg);font-size:12px}.act::before{content:"to do: ";color:var(--mut)}
button{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:3px 9px;cursor:pointer;font:inherit}
a{color:inherit}.stale{color:var(--down);font-weight:600}
@media (max-width:700px){.r{grid-template-columns:70px 1fr}.r .d{grid-column:1 / -1}}
"""

_JS = """
(function(){var t=document.getElementById('theme');if(!t)return;
function set(v){try{document.documentElement.setAttribute('data-theme',v);localStorage.setItem('aegis_status_theme',v)}catch(e){}}
try{var s=localStorage.getItem('aegis_status_theme');if(s)set(s)}catch(e){}
t.onclick=function(){var cur=document.documentElement.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');set(cur==='dark'?'light':'dark')};
document.querySelectorAll('[data-fold]').forEach(function(b){b.onclick=function(){var el=document.getElementById(b.dataset.fold);el.hidden=!el.hidden;b.textContent=el.hidden?'show':'hide'}});
})();
"""


def _row_html(r: dict, *, show_section: bool = False) -> str:
    e = _html.escape
    name = (f"{e(r['section'])} / " if show_section else "") + e(r["name"])
    age = f" · age {fmt_age(r['age_s'])}" if r.get("age_s") is not None else ""
    lim = f" / limit {fmt_age(r['limit_s'])}" if r.get("limit_s") else ""
    ev = f"<span class=ev>{e(r['evidence_path'])}{e(age)}{e(lim)}</span>" if r.get("evidence_path") or age else ""
    act = f"<span class=act>{e(r['action'])}</span>" if r.get("action") else ""
    st = _st(r)                                     # a foreign status renders UNKNOWN (review 3 N1)
    return (f"<div class=r><span class='b {st}'>{e(st)}</span><span class=n>{name}</span>"
            f"<span class=d>{e(r['detail'])}{ev}{act}</span></div>")


def render_html(rec: dict, *, now: Optional[datetime] = None) -> str:
    """One self-contained page: no network, no CDN, light/dark aware."""
    e = _html.escape
    gen = parse_ts(rec.get("generated_utc"))
    age = None if (gen is None) else ((now or utcnow()) - gen).total_seconds()
    lim = limit_s("status_receipt")
    stale = age is not None and lim is not None and age > lim
    red = reds(rec)
    parts = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>Aegis systems</title><style>{_CSS}</style></head><body><header><h1>Aegis systems</h1>"
             f"<span class=hl>{e(header_line(rec))}</span>"
             f"<span class=mut>collected {e(rec.get('generated_utc') or '?')}"
             + (f" · <span class=stale>{fmt_age(age)} old, refresh: python -m scripts.system_status --html</span>" if stale else
                f" · {fmt_age(age)} ago") + "</span>"
             "<button id=theme type=button>theme</button></header><main>"]
    if rec.get("undetermined"):
        parts.append("<h2>Could not determine</h2><div class=card>" + "".join(
            f"<div class=r><span class='b UNKNOWN'>UNKNOWN</span><span class=n></span><span class=d>{e(u)}</span></div>"
            for u in rec["undetermined"][:12]) + "</div>")
    if red:
        parts.append(f"<h2>Needs attention ({len(red)})</h2><div class=card>"
                     + "".join(_row_html(r, show_section=True) for r in red) + "</div>")
    else:
        parts.append("<h2>Needs attention</h2><div class=card><div class=r><span class='b OK'>OK</span><span class=n></span><span class=d>nothing is red</span></div></div>")
    for key, s in rec["sections"].items():
        rows = [r for r in s["rows"] if not r.get("one_shot")]
        ones = [r for r in s["rows"] if r.get("one_shot")]
        k = e(str(key), quote=True)
        parts.append(f"<h2>{e(str(s.get('title') or key))} <span class=mut>({len(rows)})</span> "
                     f"<button type=button data-fold='sec-{k}'>{'hide' if len(rows) <= 12 else 'show'}</button></h2>"
                     f"<div class=card id='sec-{k}'{'' if len(rows) <= 12 else ' hidden'}>"
                     + "".join(_row_html(r) for r in rows) + "</div>")
        if ones:
            parts.append("<p class=mut>Known one-shot tasks (not counted): " + e(", ".join(r["name"] for r in ones)) + "</p>")
    parts.append(f"<p class=mut>{e(rec.get('read_me_first') or '')} Local page; not part of the public tool. "
                 f"<a href='/desktop'>Open the lists</a></p></main><script>{_JS}</script></body></html>")
    return "".join(parts)


# ═══════════════════════════════════════════════════════════════ io + cli

def default_out_dir(optimus: Path) -> Path:
    return Path(optimus) / "system_status"


def write_atomic(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    if tmp.stat().st_size == 0 and text:
        tmp.unlink(missing_ok=True)
        raise OSError(f"zero-byte write to {tmp}")
    os.replace(tmp, path)
    return path


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Read-only systems status receipt (+ HTML page).")
    ap.add_argument("--optimus-dir", type=Path, default=Path(C.OPTIMUS_LEDGER_DIR))
    ap.add_argument("--repo", type=Path, default=REPO)
    ap.add_argument("--out-dir", type=Path, default=None, help="default: <optimus-dir>/system_status")
    ap.add_argument("--html", action="store_true", help="also write status.html")
    ap.add_argument("--render-only", action="store_true", help="render status.html from the existing status.json")
    ap.add_argument("--no-proc", action="store_true", help="skip probes that shell out (schtasks, gh, railway ...)")
    ap.add_argument("--strict", action="store_true", help="exit 2 when any row is DOWN")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    out_dir = a.out_dir or default_out_dir(a.optimus_dir)
    if a.render_only:
        rec = read_json(out_dir / "status.json")
        if not isinstance(rec, dict) or rec.get("receipt") != SCHEMA:
            print(f"no readable {SCHEMA} receipt at {out_dir / 'status.json'}", file=sys.stderr)
            return 3
    else:
        rec = collect(optimus_dir=a.optimus_dir, repo=a.repo, allow_proc=not a.no_proc)
        write_atomic(out_dir / "status.json", json.dumps(rec, indent=1, default=str))
    if a.html or a.render_only:
        write_atomic(out_dir / "status.html", render_html(rec))
    if not a.quiet:
        print(render_text(rec))
    return exit_code(rec, strict=a.strict)


if __name__ == "__main__":
    raise SystemExit(main())
