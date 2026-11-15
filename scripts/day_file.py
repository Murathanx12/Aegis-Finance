"""The day file (ROADMAP CH-44 part 1): ONE generated page per day, built only from receipts.

    python -m scripts.day_file --data-root <optimus dir> [--out <dir>] [--now <iso>]

WHY IT EXISTS
=============
The owner (2026-11-13): "we are missing the stress point: how to make it right".
Every session re-discovered what is scheduled, what is stale and where each book
stands, and much of what was built had no caller. This file adds NO mechanism. It
READS receipts that already exist and prints each line beside the receipt path it
came from and that receipt's age, so a cold reader can answer "what is open today,
what is red, where does each main account stand" from this one page.

WHAT IT REUSES (it does not re-probe)
=====================================
1. Systems rows: the newest `system_status/status.json` (written every 15 minutes by
   `scripts.system_status`; this page runs no probe, no `schtasks` and no `gh` itself).
   Its age is compared to DAY_FILE_STATUS_STALE_HOURS; only non-OK rows are printed, and
   the DOWN rows are named. The same record gives the schedule (each task's next run).
2. Dates: `forward_calendar.next_dates` / `next_macro` (point-in-time readers that
   never use a row pulled after `--now`) and `macro_calendar.fomc_table`.
3. Event nodes: `event_nodes.nodes_known_at` (the store as it stood at `--now`).
4. Books: the newest `paper_accounts/roi_<run>.json` + `book_dna_<run>.json` pair
   (the same pair `results_voice` reads; `results_voice.run_ids`). Beta and
   beta-adjusted excess come from book_dna's `market_exposure` block when present.
5. Worst case: the fleet manager's own `worst_case_now` per account, the PC paper
   snapshot's positions, and book_dna weights x the ROI row's equity.
6. Forecasts: `forecast_ledger.logical_lines` streamed once (a count only; expiry
   logic is CH-42's). predictions.jsonl is never opened for writing.
7. Owner calls: `owner_calls/states.jsonl` (the pinned, hash-chained readings).

WHY THIS IS NOT `scripts.local_runtime_digest`
==============================================
That digest samples four reader logs and asks the on-box model for a four-sentence
summary; it has no books, no dates, no worst case and no receipt per line, and its
output is labelled UNVERIFIED_MODEL_SUMMARY. Extending it would put an LLM between
the receipts and the reader, which is the opposite of this page. Nothing is shared
but the habit of reading tails, which this reuses from `system_status`.

RULES IT KEEPS
==============
* Read only, except its own two output files (temp -> verify -> replace). With
  `--out`, nothing is written under the data root.
* Every number names its receipt. Unknown is printed CANNOT DETERMINE with the
  reason, never 0. A date is compared to a limit, never just printed.
* `--now` in the past is a REPLAY: rows written after it are skipped by the
  readers; live-only state (Windows scheduler, RAM, processes) is CANNOT DETERMINE.
* No network, no broker, no LLM, no subprocess.
* Exit 0: written and faithful, even when it reports red content (that is its job).
  Exit 2: written, but the day file itself is defective: the systems receipt is stale or
  missing, a section reader raised, or a source of truth could not be read (the `defects`
  list in the JSON). Exit 3: not written (bad or future `--now`, no data root, write failed).
  The red sections are listed in the JSON (`red_sections`) and in the markdown's first line.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as C  # noqa: E402

SCHEMA = "day-file/1"
OK, RED, CD, INFO = "OK", "RED", "CANNOT_DETERMINE", "INFO"
_SEV = {OK: 0, INFO: 0, RED: 1, CD: 2}
SECTIONS = (
    ("red", "1. Systems headline and red rows (stale, empty, refused or missing sources)"),
    ("schedule", "2. Scheduled today (task table) and the next sessions (session calendar)"),
    ("dates", "3. Dated events ahead (held names, sensors, macro)"),
    ("events", "4. Open event nodes"),
    ("books", "5. Books (main accounts first)"),
    ("worst", "6. Largest dollar worst case across open paper books"),
    ("cohorts", "7. Rolling cohorts and dynamic books"),
    ("forecasts", "8. Forecasts (counts only)"),
    ("owner_calls", "9. Owner-calls reading (yesterday)"),
    ("inbox", "10. Owner inbox (count only)"),
)
_STAMP_RE = re.compile(r"^DAY_(\d{4}-\d{2}-\d{2})__(\d{8}T\d{6}Z)\.json$")


class DayFileRefused(RuntimeError):
    """The day file will not be built (no data root, or a clock it cannot trust).
    `code` is the machine-readable reason; the CLI turns it into exit 3."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


# ═══════════════════════════════════════════════════════════════ small helpers

def _cfg(name: str, default: Any) -> Any:
    return getattr(C, name, default)


def utc(v: Any) -> Optional[datetime]:
    """ISO / compact / date -> aware UTC datetime, else None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    s = str(v).strip()
    m = re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})T(\d{2}):?(\d{2}):?(\d{2})Z", s)
    if m:
        return datetime(*map(int, m.groups()), tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def iso(d: Optional[datetime]) -> Optional[str]:
    return d.astimezone(timezone.utc).isoformat(timespec="seconds") if d else None


def fmt_age(s: Optional[float]) -> str:
    if s is None:
        return "age unknown"
    if s < 0:
        return f"{fmt_age(-s)} AFTER the clock"
    if s < 5400:
        return f"{s / 60:.0f} min"
    if s < 172800:
        return f"{s / 3600:.1f} h"
    return f"{s / 86400:.1f} d"


def read_json(p: Path) -> Any:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None


#: A Windows drive path, or a POSIX absolute path of at least two segments (a receipt written
#: on Linux, e.g. CI or Railway). A relative `a/b`, a URL and `<data root>/x` are not matched.
_ABS = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:(?:\\|/(?!/))[^\s'\"`;,)\]]*"
                  r"|(?<![A-Za-z0-9_.:/<>~-])/(?:[A-Za-z0-9_.+-]+/)+[A-Za-z0-9_.+-]*")


def clean_path(text: str) -> str:
    """No absolute path of another checkout or worktree reaches the page: a path inside a data
    folder prints relative to it, a repo path as `repo:<path>`, anything else as its base name."""
    def sub(m: "re.Match[str]") -> str:
        t = m.group(0).replace("\\", "/")
        for mark in ("/backend/data/optimus/", "/optimus/"):
            if mark in t:
                return t.split(mark, 1)[1]
        for mark in ("/backend/", "/docs/", "/scripts/"):
            i = t.find(mark)
            if i >= 0:
                return "repo:" + t[i + 1:]
        return "<abs>/" + t.rstrip("/").rsplit("/", 1)[-1]
    return _ABS.sub(sub, str(text))


def line(status: str, text: str, receipt: str = "", stamp: Optional[datetime] = None,
         now: Optional[datetime] = None, **extra: Any) -> dict:
    """One printed line. `defect=True` marks a line that says the DAY FILE ITSELF is defective
    (a source of truth it needs is missing, stale or unreadable): the exit code reads it."""
    age = None if (stamp is None or now is None) else round((now - stamp).total_seconds(), 1)
    return {"status": status, "text": clean_path(text), "receipt": clean_path(receipt), "receipt_utc": iso(stamp),
            "age_s": age, **({"extra": extra} if extra else {})}


def section(key: str, lines: list[dict], *, error: Optional[str] = None, data: Any = None) -> dict:
    title = dict(SECTIONS)[key]
    if error:
        lines = lines + [line(CD, f"section reader failed: {error}", defect=True)]
    if not lines:
        lines = [line(CD, "the section produced no line at all")]
    st = max((ln["status"] for ln in lines), key=lambda s: _SEV.get(s, 2))
    return {"key": key, "title": title, "status": OK if st == INFO else st, "lines": lines,
            **({"data": data} if data is not None else {})}


def rel(p: Path, root: Path) -> str:
    """A receipt path relative to the data root when it is inside it."""
    try:
        return str(Path(p).resolve().relative_to(Path(root).resolve())).replace("\\", "/")
    except (ValueError, OSError):
        return clean_path(str(p).replace("\\", "/"))


def is_replay(now: datetime, wall: datetime) -> bool:
    return abs((wall - now).total_seconds()) > float(_cfg("DAY_FILE_REPLAY_SLACK_S", 3600))


def local_day(now: datetime) -> str:
    from zoneinfo import ZoneInfo
    return now.astimezone(ZoneInfo(str(_cfg("DAY_FILE_TZ", "Asia/Hong_Kong")))).date().isoformat()


def market_day(now: datetime) -> date:
    from backend.services import forward_calendar as FC
    return FC.market_date(now)


def is_session(d: date) -> Optional[bool]:
    try:
        from backend.services import market_sessions as MS
        return bool(MS.is_session(d))
    except Exception:  # noqa: BLE001
        return None


# ═══════════════════════════════════════════════════════════════ 1. red rows

_LIVE_ONLY_ROWS = {"ram_free", "last_boot", "sleep_settings", "open_prs"}


STATUS_REL = "system_status/status.json"


def collect_status(data_root: Path, now: datetime, *, replay: bool,
                   status_fn: Optional[Callable[..., dict]] = None) -> tuple[Optional[dict], str]:
    """The systems receipt, read ONCE: (record, why-not text). The red rows, the schedule and
    the headline all read this one record. It reads `system_status/status.json` (written
    every 15 minutes by `scripts.system_status`); it does not re-probe the machine, so the
    day file runs no `schtasks`, no `gh` and no network of its own."""
    if status_fn is not None:
        try:
            rec = status_fn(data_root=data_root, now=now, replay=replay)
        except Exception as exc:  # noqa: BLE001
            return None, f"status reader raised {type(exc).__name__}: {str(exc)[:200]}"
    else:
        rec = read_json(Path(data_root) / STATUS_REL)
        if rec is None:
            return None, f"{STATUS_REL} is absent or unreadable"
    if not isinstance(rec, dict) or not isinstance(rec.get("sections"), dict):
        return None, f"{STATUS_REL} has no `sections` record"
    t = utc(rec.get("generated_utc"))
    if t is None:
        return None, f"{STATUS_REL} carries no readable generated_utc"
    if t > now:
        return None, (f"{STATUS_REL} is stamped {iso(t)}, after the clock {iso(now)} (only the latest is kept): "
                      f"the systems state as of that clock cannot be read")
    return rec, ""


def red_section(rec: Optional[dict], err: str, now: datetime, *, replay: bool) -> dict:
    lines: list[dict] = []
    if rec is None:
        return section("red", [line(CD, f"the systems receipt cannot be read: {err}", STATUS_REL, defect=not replay)])
    counts = rec.get("counts") or {}
    tasks = (rec.get("sections") or {}).get("tasks", {}).get("rows") or []
    sched_unknown = any(r.get("name") == "scheduler" and r.get("status") == "UNKNOWN" for r in tasks)
    gen = utc(rec.get("generated_utc"))
    lim_h = float(_cfg("DAY_FILE_STATUS_STALE_HOURS", 1.0))
    if gen is not None and (now - gen).total_seconds() > lim_h * 3600:
        lines.append(line(RED, f"the systems receipt is {fmt_age((now - gen).total_seconds())} old (red after "
                               f"{lim_h:g} h; it is rewritten every 15 minutes): every row below is as of then, "
                               f"and the task that writes it is itself not running",
                          STATUS_REL, gen, now, defect=not replay))
    if replay:
        lines.append(line(CD, "REPLAY: live machine state (scheduler, processes, RAM) cannot be read as of this clock",
                          STATUS_REL))
    elif sched_unknown:
        lines.append(line(CD, "`schtasks /query /fo CSV /v` could not be read: which tasks ran, and their "
                              "last result, CANNOT be determined", "schtasks /query /fo CSV /v"))
    n_red = 0
    for key, sec in (rec.get("sections") or {}).items():
        for r in sec.get("rows") or []:
            st = r.get("status")
            if st == "OK" or r.get("one_shot") or str(r.get("name", "")).startswith("rule "):
                continue
            if replay and r.get("name") in _LIVE_ONLY_ROWS:
                continue
            if replay and key == "tasks" and r.get("name") == "scheduler":
                continue
            if not replay and key == "tasks" and r.get("name") == "scheduler" and sched_unknown:
                continue
            n_red += 1
            stamp = utc(r.get("evidence_utc"))
            word = {"UNKNOWN": "MISSING/UNKNOWN", "DEGRADED": "STALE/DEGRADED", "DOWN": "DOWN"}.get(st, st)
            act = f" -> {r['action']}" if r.get("action") else ""
            lines.append(line(RED, f"[{word}] {key}/{r.get('name')}: {str(r.get('detail') or '')[:260]}{act[:220]}",
                              str(r.get("evidence_path") or "") or "(no evidence path)", stamp, now,
                              sev=st))
    lines.sort(key=lambda ln: (-_SEV[ln["status"]], {"DOWN": 0, "DEGRADED": 1, "UNKNOWN": 2}.get(
        (ln.get("extra") or {}).get("sev"), 3), ln["text"]))
    down = sorted(f"{key}/{r.get('name')}" for key, sec in (rec.get("sections") or {}).items()
                  for r in sec.get("rows") or [] if r.get("status") == "DOWN" and not r.get("one_shot"))
    cap = int(_cfg("DAY_FILE_TOP_RED_ROWS", 10))
    row_lines = [ln for ln in lines if (ln.get("extra") or {}).get("sev")]
    other = [ln for ln in lines if not (ln.get("extra") or {}).get("sev")]
    if len(row_lines) > cap:
        rest = row_lines[cap:]
        lines = other + row_lines[:cap] + [line(RED, f"{len(rest)} more non-OK rows are not printed here (all in the "
                                                     f"JSON, worst first)", STATUS_REL, gen, now)]
        all_rows = [ln["text"] for ln in row_lines]
    else:
        lines = other + row_lines
        all_rows = [ln["text"] for ln in row_lines]
    lines.insert(0, line(RED if down else OK, (f"DOWN rows ({len(down)}): " + ", ".join(down)) if down
                         else "no row is DOWN", STATUS_REL,
                         gen, now))
    lines.insert(0, line(INFO, f"system_status: {counts.get('OK', 0)} OK, {counts.get('DEGRADED', 0)} degraded, "
                               f"{counts.get('DOWN', 0)} down, {counts.get('UNKNOWN', 0)} unknown; "
                               f"{n_red} non-OK rows listed below",
                         STATUS_REL, gen, now))
    return section("red", lines, data={"counts": counts, "down": down, "non_ok_rows": all_rows,
                                       "undetermined": rec.get("undetermined")})


# ═══════════════════════════════════════════════════════════════ 2. scheduled today

def _task_cadence_h(name: str) -> Optional[float]:
    try:
        from backend.services import task_receipts as TR
        spec = TR.TASK_RECEIPT.get(name)
        if spec is not None and spec.cadence_h is not None:
            return float(spec.cadence_h)
    except Exception:  # noqa: BLE001
        pass
    v = getattr(C, "HEALTH_TASK_CADENCE_H", {}).get(name)
    return None if v is None else float(v)


_DT = re.compile(r"^\s*(\d{1,4})([/.\-])(\d{1,2})\2(\d{1,4})[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?\s*$")


def infer_date_order(strings: Iterable[Any]) -> Optional[str]:
    """`dmy` or `mdy` when the table's OWN dates prove it (a first number above 12 means day
    first, a second above 12 means month first, and not both); otherwise None: never a guess."""
    dmy = mdy = False
    for t in strings:
        m = _DT.match(str(t or ""))
        if not m or len(m.group(1)) == 4:
            continue
        a, b = int(m.group(1)), int(m.group(3))
        dmy = dmy or a > 12
        mdy = mdy or b > 12
    return "dmy" if dmy and not mdy else "mdy" if mdy and not dmy else None


def _sched_dt(text: Any, order: Optional[str] = None) -> Optional[datetime]:
    """A schtasks local date-time -> aware UTC. A numeric date whose day/month order is not
    proven (by its own digits or by `order`) is UNREADABLE (None), never guessed."""
    m = _DT.match(str(text or ""))
    if not m:
        return None
    a, _sep, b, c, hh, mm, ss, ap = m.groups()
    try:
        if len(a) == 4:
            y, mo, d = int(a), int(b), int(c)
        else:
            if len(c) != 4:
                return None
            y = int(c)
            if order == "dmy":
                d, mo = int(a), int(b)
            elif order == "mdy":
                mo, d = int(a), int(b)
            elif int(a) > 12:
                d, mo = int(a), int(b)
            elif int(b) > 12:
                mo, d = int(a), int(b)
            else:
                return None
        h = int(hh)
        if ap:
            if not 1 <= h <= 12:
                return None
            h = h % 12 + (12 if ap.lower().startswith("p") else 0)
        elif h > 23:
            return None
        return datetime(y, mo, d, h, int(mm), int(ss or 0)).astimezone().astimezone(timezone.utc)
    except ValueError:
        return None


def _row_time(r: dict, which: str, order: Optional[str]) -> Optional[datetime]:
    ex = r.get("extra") or {}
    iso_v = utc(ex.get(f"{which}_utc"))          # an ISO field wins when system_status emits one
    return iso_v if iso_v is not None else _sched_dt(ex.get(which), order)


def next_sessions(today: date, n: int) -> Optional[list[date]]:
    out: list[date] = []
    d = today
    for _ in range(n * 4 + 14):
        d += timedelta(days=1)
        ok = is_session(d)
        if ok is None:
            return None
        if ok:
            out.append(d)
            if len(out) == n:
                return out
    return out


def schedule_section(rec: Optional[dict], err: str, now: datetime) -> dict:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(str(_cfg("DAY_FILE_TZ", "Asia/Hong_Kong")))
    today_local = now.astimezone(tz).date()
    lines: list[dict] = []
    mday = market_day(now)
    sess = is_session(mday)
    n_sess = int(_cfg("DAY_FILE_UPCOMING_SESSIONS", 10))
    nxt = next_sessions(mday, n_sess)
    lines.append(line(INFO if sess is not None else CD,
                      f"New York market date {mday.isoformat()}: "
                      + ("a session day" if sess else "NOT a session day" if sess is False
                         else "session status CANNOT be determined")
                      + "; next " + str(n_sess) + " sessions: "
                      + (", ".join(d.isoformat() for d in nxt) if nxt else "CANNOT DETERMINE (calendar unavailable)"),
                      "backend/services/market_sessions.py"))
    if rec is None:
        lines.append(line(CD, f"the task table cannot be read, so what is scheduled today CANNOT be determined: {err}",
                          STATUS_REL))
        return section("schedule", lines)
    gen = utc(rec.get("generated_utc"))
    lim_h = float(_cfg("DAY_FILE_STATUS_STALE_HOURS", 1.0))
    if gen is None or (now - gen).total_seconds() > lim_h * 3600:
        lines.append(line(CD, f"the task table is {fmt_age(None if gen is None else (now - gen).total_seconds())} old "
                              f"(limit {lim_h:g} h): what is scheduled today CANNOT be determined from it",
                          STATUS_REL, gen, now))
        return section("schedule", lines)
    rows = [r for r in ((rec.get("sections") or {}).get("tasks") or {}).get("rows") or []
            if isinstance(r, dict) and not r.get("one_shot") and r.get("name") != "scheduler"]
    if not rows:
        lines.append(line(CD, "the systems receipt carries no task rows (the scheduler was not readable)", STATUS_REL))
        return section("schedule", lines)
    order = infer_date_order(x for r in rows for x in ((r.get("extra") or {}).get("next_run"),
                                                        (r.get("extra") or {}).get("last_run")))
    due, ran, unreadable = [], [], 0
    for r in rows:
        nr, lr = _row_time(r, "next_run", order), _row_time(r, "last_run", order)
        if nr is not None and nr.astimezone(tz).date() == today_local:
            due.append((nr, r))
        if lr is not None and lr.astimezone(tz).date() == today_local and lr <= now:
            ran.append((lr, r))
        if nr is None and lr is None:
            unreadable += 1
    share = unreadable / len(rows)
    if share >= 0.5:
        lines.append(line(CD, f"{unreadable} of {len(rows)} tasks have no parseable run time (date order proven from the "
                              f"table: {order or 'NOT PROVEN, ambiguous numeric dates are left unread'}): what is "
                              f"scheduled today CANNOT be determined. Fix: system_status should emit "
                              f"`extra.next_run_utc` and `extra.last_run_utc` (ISO 8601 UTC) on each task row",
                          STATUS_REL, gen, now))
        return section("schedule", lines, data={"n_tasks": len(rows), "n_unreadable": unreadable})
    due.sort(key=lambda x: (x[0], str(x[1].get("name"))))
    cap = int(_cfg("DAY_FILE_TOP_SCHEDULED", 40))
    lines.append(line(INFO, f"{len(rows)} tasks; {len(due)} have a next run on local day {today_local.isoformat()} "
                            f"({_cfg('DAY_FILE_TZ', 'Asia/Hong_Kong')}), {len(ran)} already ran today, {unreadable} carry no "
                            f"readable run time (date order {order or 'by digits only'})", STATUS_REL, gen, now))
    if due:
        lines.append(line(INFO, "due today: " + ", ".join(
            f"{nr.astimezone(tz).strftime('%H:%M')} {r.get('name')}" + (" [DOWN]" if r.get("status") == "DOWN" else "")
            for nr, r in due[:cap]) + (f" (+{len(due) - cap} more in the JSON)" if len(due) > cap else ""),
                          STATUS_REL, gen, now))
    return section("schedule", lines, data={
        "today_local": today_local.isoformat(), "date_order": order, "n_unreadable": unreadable,
        "due_today": [str(r.get("name")) for _, r in due], "ran_today": [str(r.get("name")) for _, r in ran],
        "next_sessions": [d.isoformat() for d in nxt or []]})


# ═══════════════════════════════════════════════════════════════ held names

def newest_fleet_run(data_root: Path, now: datetime) -> tuple[Optional[Path], Optional[dict]]:
    runs = data_root / "paper_accounts" / "fleet_manager" / "runs"
    best: tuple[Optional[datetime], Optional[Path]] = (None, None)
    for p in (runs.glob("run_*.json") if runs.is_dir() else []):
        m = re.match(r"run_(\d{8}T\d{6}Z)", p.name)
        t = utc(m.group(1)) if m else None
        if t is None or t > now:
            continue
        if best[0] is None or t > best[0]:
            best = (t, p)
    if best[1] is None:
        return None, None
    d = read_json(best[1])
    return best[1], d if isinstance(d, dict) else None


def pc_snapshot(data_root: Path, now: datetime) -> tuple[Path, Optional[dict], str]:
    p = data_root / "paper_accounts" / "pc_snapshot" / "state_latest.json"
    d = read_json(p)
    if not isinstance(d, dict):
        return p, None, "unreadable or absent"
    t = utc(d.get("t"))
    if t is None:
        return p, None, "no `t` stamp in the snapshot"
    if t > now:
        return p, None, f"the only snapshot is stamped {iso(t)}, after the clock (only the latest is kept)"
    return p, d, ""


def held_names(data_root: Path, now: datetime, dna: Optional[dict]) -> tuple[set, list[str]]:
    """Tickers held by any open paper book, and where each set came from."""
    names: set = set()
    src: list[str] = []
    fp, fr = newest_fleet_run(data_root, now)
    if fr:
        n0 = len(names)
        for a in fr.get("accounts") or []:
            for pos in (a.get("positions") or []) if isinstance(a, dict) else []:
                if isinstance(pos, dict) and pos.get("symbol"):
                    names.add(str(pos["symbol"]).upper())
        src.append(f"{rel(fp, data_root)} ({len(names) - n0} names)")
    sp, sd, _why = pc_snapshot(data_root, now)
    if sd:
        n0 = len(names)
        names |= {str(p.get("symbol")).upper() for p in sd.get("positions") or [] if isinstance(p, dict) and p.get("symbol")}
        src.append(f"{rel(sp, data_root)} ({len(names) - n0} new names)")
    if isinstance(dna, dict):
        n0 = len(names)
        for b in dna.get("books") or []:
            if isinstance(b, dict) and b.get("status") == "LIVE":
                names |= {str(t).upper() for t in b.get("tickers") or []}
        src.append(f"book_dna LIVE books' tickers ({len(names) - n0} new names)")
    return names, src


# ═══════════════════════════════════════════════════════════════ 2. dates

def _fomc_path(override: Optional[Path]) -> Path:
    """The Fed table resolves through the repo helper, never through a path next to the data root."""
    if override:
        return Path(override)
    from backend.services import macro_calendar as MC
    return MC.fomc_path()


def dates_section(data_root: Path, now: datetime, dna: Optional[dict], *, fomc_file: Optional[Path] = None) -> dict:
    from backend.services import forward_calendar as FC
    lines: list[dict] = []
    n_sess = int(_cfg("DAY_FILE_UPCOMING_SESSIONS", 10))
    ahead: list[tuple[str, str]] = []           # (date, what): the next dated event is the earliest
    held, srcs = held_names(data_root, now, dna)
    sensors = [str(t).upper() for t in _cfg("DAY_FILE_SENSOR_TICKERS", ())]
    want = sorted(held | set(sensors))
    fresh = FC.freshness(data_root, now)
    st_line = OK if fresh["verdict"] == "ALIVE" else RED
    lines.append(line(st_line, f"forward calendar {fresh['verdict']}: {fresh['detail'][:300]}",
                      "forward_calendar/snapshots/fc_<stamp>_receipt.json", utc(fresh.get("evidence_utc")), now))
    data: dict = {"n_held_names": len(held), "held_sources": srcs, "sensors": sensors}
    try:
        nd = FC.next_dates(want, now, root=data_root)
    except Exception as exc:  # noqa: BLE001
        lines.append(line(CD, f"forward_calendar.next_dates raised {type(exc).__name__}: {str(exc)[:200]}",
                          "forward_calendar/snapshots/"))
        nd = None
    if nd is not None:
        counts = nd["counts"]
        store = rel(Path(nd["store"]), data_root)
        upcoming = sorted(((t, r) for t, r in nd["tickers"].items()
                           if r["label"] == FC.DATE_IN_HORIZON and r.get("sessions_away") is not None
                           and r["sessions_away"] <= n_sess),
                          key=lambda tr: (tr[1]["date"], tr[0]))
        bad = counts.get(FC.NOT_COVERED, 0) + counts.get(FC.CALENDAR_STALE, 0) + counts.get(
            FC.FROM_OLDER_SNAPSHOT_NEWEST_DAMAGED, 0)
        lines.append(line(RED if bad or not nd["n_snapshots_available"] else OK,
                          f"{len(held)} names held by an open paper book (count only) plus {len(sensors)} sensors; "
                          f"{len(upcoming)} of them report within {n_sess} sessions (listed below, sensors first); "
                          f"labels {counts}; {nd['n_snapshots_available']} snapshot(s) at or before the clock, "
                          f"{nd['n_snapshots_after_now_skipped']} after it skipped",
                          store, None, now))
        for t in sensors:
            r = nd["tickers"].get(t) or {}
            if r.get("label") != FC.DATE_IN_HORIZON:
                lines.append(line(RED if r.get("label") in (FC.NOT_COVERED, FC.CALENDAR_STALE, None) else INFO,
                                  f"sensor {t}: {r.get('label')} ({r.get('reason')})"
                                  + (f"; last reported {r['last_reported']['date']}" if r.get("last_reported") else ""),
                                  store, utc(r.get("pulled_utc")), now))
        cap_d = int(_cfg("DAY_FILE_TOP_DATES", 25))
        shown = sorted(upcoming, key=lambda tr: (tr[0] not in sensors, tr[1]["date"], tr[0]))[:cap_d]
        shown = sorted(shown, key=lambda tr: (tr[1]["date"], tr[0]))
        if len(upcoming) > len(shown):
            lines.append(line(INFO, f"{len(upcoming)} names report within {n_sess} sessions; the {len(shown)} printed are "
                                    f"the sensors first, then the soonest (all are in the JSON)", store))
        for t, r in shown:
            who = "sensor" if t in sensors else "held"
            lines.append(line(INFO, f"{r['date']} ({r['sessions_away']} session(s) away, {r.get('timing') or 'time ?'}, "
                                    f"{r.get('confirmation') or 'unconfirmed'}): {t} earnings [{who}]",
                              f"{store} pull {r.get('pull_id')}", utc(r.get("pulled_utc")), now))
        if not upcoming:
            lines.append(line(INFO, f"no held or sensor name has an earnings date in the next {n_sess} sessions "
                                    f"(among the {counts.get(FC.DATE_IN_HORIZON, 0)} names with a date in horizon)",
                              store))
        data["counts"] = counts
        ahead += [(r["date"], f"{t} earnings [sensor]") for t, r in upcoming if t in sensors]
        data["upcoming"] = [{"ticker": t, **{k: r.get(k) for k in ("date", "sessions_away", "timing", "confirmation",
                                                                   "pull_id", "pulled_utc")}} for t, r in upcoming]
    # macro dates (CPI / NFP / FOMC) from the newest snapshot at or before the clock
    hz = int(_cfg("DAY_FILE_MACRO_HORIZON_DAYS", 16))
    try:
        mac = FC.next_macro(now, hz, root=data_root)
    except Exception as exc:  # noqa: BLE001
        mac = {"status": f"RAISED {type(exc).__name__}", "dates": [], "refusals": []}
    if mac.get("status") != "OK":
        lines.append(line(RED, f"macro dates from the forward-calendar store: {mac.get('status')}",
                          "forward_calendar/snapshots/ (macro rows)"))
    else:
        for r in mac.get("refusals") or []:
            lines.append(line(RED, f"macro leg {r.get('kind')} REFUSED in the pull: {str(r.get('refusal'))[:200]}",
                              f"forward_calendar/snapshots/{mac.get('pull_id')}.jsonl", utc(mac.get("pulled_utc")), now))
        ahead += [(r["date"], f"{r.get('kind')} (macro)") for r in mac.get("dates") or []]
        for r in sorted(mac.get("dates") or [], key=lambda x: (x["date"], str(x.get("kind")))):
            lines.append(line(INFO, f"{r['date']} ({r['days_away']} day(s) away): {r.get('kind')} - {r.get('what')}",
                              f"forward_calendar/snapshots/{mac.get('pull_id')}.jsonl ({r.get('source')})",
                              utc(mac.get("pulled_utc")), now))
    # the Fed table itself: NOT_SEEDED / STALE / verified after the clock are red rows
    try:
        from backend.services import macro_calendar as MC
        fp = _fomc_path(fomc_file)
        tb = MC.fomc_table(fp)
        ver = tb.get("verified_on")
        status = tb.get("status")
        tb_age_d = None
        if ver:
            try:
                tb_age_d = (now.date() - date.fromisoformat(ver)).days
            except ValueError:
                tb_age_d = None
        if ver and tb_age_d is not None and tb_age_d < 0:
            status = "FOMC_TABLE_VERIFIED_AFTER_THE_CLOCK"
        elif tb_age_d is not None and tb_age_d > int(MC.STALE_AFTER_DAYS):
            status = "FOMC_SCHEDULE_STALE"
        ok_tb = status == "ok"
        nxt = [d for d in tb.get("dates") or [] if d >= now.date().isoformat()][:2]
        lines.append(line(OK if ok_tb else RED,
                          f"FOMC table {status}" + (f", verified_on {ver} ({tb_age_d} d before the clock)" if ver else "")
                          + (f"; next statement day(s) {', '.join(nxt)}" if ok_tb and nxt else ""),
                          rel(fp, data_root)))
        if ok_tb:
            for d in nxt:
                dd = (date.fromisoformat(d) - now.date()).days
                if dd <= hz:
                    ahead.append((d, "FOMC statement"))
                    lines.append(line(INFO, f"{d} ({dd} day(s) away): FOMC statement", rel(fp, data_root)))
    except Exception as exc:  # noqa: BLE001
        lines.append(line(CD, f"FOMC table unreadable ({type(exc).__name__}: {str(exc)[:160]})", "fomc_schedule.json"))
    future = sorted(x for x in ahead if x[0] >= now.date().isoformat())
    data["next_event"] = None if not future else {"date": future[0][0], "what": future[0][1]}
    if not future:
        lines.append(line(CD, "no dated event (sensor earnings, macro, FOMC) was found ahead", "forward_calendar/"))
    return section("dates", lines, data=data)


# ═══════════════════════════════════════════════════════════════ 3. event nodes

def events_section(data_root: Path, now: datetime) -> dict:
    from backend.services import event_nodes as EN
    store = data_root / str(_cfg("EVENT_NODES_DIRNAME", "event_nodes")) / EN.STORE_NAME
    if not store.exists():
        return section("events", [line(RED, "no event-node store: nothing has built an event node", rel(store, data_root))])
    try:
        k = EN.nodes_known_at(store, now)
    except Exception as exc:  # noqa: BLE001
        return section("events", [line(CD, f"event_nodes.nodes_known_at refused/raised {type(exc).__name__}: "
                                           f"{str(exc)[:200]}", rel(store, data_root), defect=True)])
    newest = utc(k.get("newest_build_utc"))
    lim_h = float(_cfg("DAY_FILE_EVENT_NODES_STALE_HOURS", 6.0))
    sess = is_session(market_day(now))
    age_h = k.get("age_hours")
    stale = newest is None or (age_h is not None and age_h > lim_h and sess is not False)
    mx = float(_cfg("EVENT_NODES_CONSUMER_MAX_AGE_HOURS", 120.0))
    briefs = []
    for n in k["nodes"].values():
        fs = utc(n.get("first_seen_utc"))
        if fs is None or fs >= now or (now - fs).total_seconds() / 3600.0 > mx:
            continue
        imp = n.get("importance") or {}
        try:
            at = EN.decay(imp.get("importance_0") or 0.0, fs, now, (n.get("decay") or {}).get("half_life_hours"))
        except Exception:  # noqa: BLE001
            at = None
        briefs.append({"event_id": n.get("event_id"), "primary_ticker": n.get("primary_ticker"),
                       "first_seen_utc": n.get("first_seen_utc"), "importance_0": imp.get("importance_0"),
                       "importance_at": None if at is None else round(float(at), 4),
                       "n_publishers": (imp.get("facts") or {}).get("n_publishers"),
                       "n_evidence": n.get("n_evidence"), "built_now_utc": n.get("built_now_utc")})
    briefs.sort(key=lambda b: (-(b["importance_at"] if b["importance_at"] is not None else -1), str(b["event_id"])))
    r = rel(store, data_root)
    lines = [line(RED if stale else OK,
                  f"store newest build {k.get('newest_build_utc')} ({age_h} h before the clock; red after {lim_h:g} h on "
                  f"a session day; today {'is' if sess else 'is not' if sess is False else 'may or may not be'} a session); "
                  f"{len(k['nodes'])} live nodes, {len(briefs)} open (first seen within {mx:g} h), {k.get('n_retired')} retired, "
                  f"{k.get('n_versions_after_t_skipped')} versions after the clock skipped",
                  r, newest, now)]
    for i, b in enumerate(briefs[:int(_cfg("DAY_FILE_TOP_EVENTS", 5))], 1):
        lines.append(line(INFO, f"#{i} {b['primary_ticker']} importance {b['importance_at']} (at build "
                                f"{b['importance_0']}), {b['n_publishers']} publisher(s), {b['n_evidence']} item(s), "
                                f"first seen {b['first_seen_utc']} [{b['event_id']}]",
                          r, utc(b["built_now_utc"]), now))
    return section("events", lines, data={"n_live": len(k["nodes"]), "n_open": len(briefs), "top": briefs[:10]})


# ═══════════════════════════════════════════════════════════════ 4. books

def book_pair(data_root: Path, now: datetime) -> tuple[Optional[str], Optional[dict], Optional[dict], str]:
    from backend.services import results_voice as RV
    pa = data_root / "paper_accounts"
    shared = RV.run_ids(pa, "roi") & RV.run_ids(pa, "book_dna")
    ok = sorted(r for r in shared if (utc(r) or now + timedelta(days=1)) <= now)
    if not ok:
        return None, None, None, (f"no run id has both roi_<run>.json and book_dna_<run>.json at or before the clock "
                                  f"in {rel(pa, data_root)} ({len(shared)} pairs exist in all)")
    rid = ok[-1]
    roi, dna = read_json(pa / f"roi_{rid}.json"), read_json(pa / f"book_dna_{rid}.json")
    if not isinstance(roi, dict) or not isinstance(dna, dict):
        return rid, None, None, f"roi_{rid}.json or book_dna_{rid}.json unreadable"
    return rid, roi, dna, ""


def is_main(account: str, family: Optional[str]) -> bool:
    """A main account is broker-held (the Alpaca fleet, the PC paper account) or one of the
    accounts the site shows. A twin, control or random sleeve (`__`) is never main."""
    if "__" in account:
        return False
    if account in set(_cfg("DAY_FILE_SHOWN_ACCOUNTS", ())) or family in set(_cfg("DAY_FILE_BROKER_FAMILIES", ())):
        return True
    return any(re.search(p, account) for p in _cfg("DAY_FILE_MAIN_ACCOUNT_PATTERNS", ()))


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def exposure(book: dict) -> tuple[str, str, Optional[str]]:
    """(beta text, beta-adjusted excess text, why when undeterminable) from book_dna."""
    me = book.get("market_exposure")
    if isinstance(me, dict):
        b = (me.get("beta") or {})
        x = (me.get("beta_adjusted_excess_pp") or {})
        bv, xv = _num(b.get("value")), _num(x.get("value"))
        bt = f"{bv:.2f}" if bv is not None else f"CANNOT DETERMINE ({str(b.get('why') or b.get('value'))[:80]})"
        xt = f"{xv:+.2f}" if xv is not None else f"CANNOT DETERMINE ({str(x.get('why') or x.get('value'))[:80]})"
        return bt, xt, None if (bv is not None and xv is not None) else "market_exposure field undetermined"
    why = "book_dna predates the market_exposure block (PR #140, CH-11 note)"
    bvs = book.get("beta_vs_spy") or {}
    bv = _num(bvs.get("value")) if isinstance(bvs, dict) else None
    bt = (f"{bv:.2f} (book_dna.beta_vs_spy)" if bv is not None
          else f"CANNOT DETERMINE ({str((bvs or {}).get('why') or 'no beta field')[:80]})")
    return bt, f"CANNOT DETERMINE ({why})", why


def books_section(data_root: Path, now: datetime, rid: Optional[str], roi: Optional[dict], dna: Optional[dict],
                  why: str) -> dict:
    if roi is None or dna is None:
        return section("books", [line(CD, f"no book pair: {why}", "paper_accounts/roi_<run>.json + book_dna_<run>.json",
                                      defect=True)])
    rr, dr = f"paper_accounts/roi_{rid}.json", f"paper_accounts/book_dna_{rid}.json"
    gen = utc(roi.get("generated_utc"))
    lim_h = float(_cfg("DAY_FILE_BOOKS_STALE_HOURS", 36.0))
    age_h = None if gen is None else (now - gen).total_seconds() / 3600.0
    books = {str(b.get("account")): b for b in dna.get("books") or [] if isinstance(b, dict)}
    excl_fam = set(_cfg("DAY_FILE_EXCLUDED_FAMILIES", ()))
    lines = [line(RED if age_h is None or age_h > lim_h else OK,
                  f"pair run {rid}: ROI generated {iso(gen)} ({fmt_age(None if age_h is None else age_h * 3600)} old, "
                  f"red after {lim_h:g} h); {len(roi.get('rows') or [])} ROI rows, {len(books)} book_dna books",
                  f"{rr} + {dr}", gen, now)]
    rv_p = data_root / "paper_accounts" / f"results_voice_{rid}.json"
    rv = read_json(rv_p)
    if isinstance(rv, dict) and rv.get("headline_lines"):
        lines.append(line(INFO, "results voice: " + str(rv["headline_lines"][0])[:400]
                          + (f"; labels held {(rv.get('claims') or {}).get('labels_held')}"
                             if (rv.get("claims") or {}).get("labels_held") else ""),
                          rel(rv_p, data_root), utc(rv.get("roi_generated_utc")), now))
    else:
        lines.append(line(CD, f"no results_voice_{rid}.json: the headline count of books ahead of SPY CANNOT be "
                              f"read from the results voice for this pair", rel(rv_p, data_root)))
    rows_main, rows_other, excluded = [], [], []
    if age_h is None or age_h > lim_h:
        lines[0]["extra"] = {"defect": True}     # a stale ROI pair: the books on this page are not today's
    for r in roi.get("rows") or []:
        a, fam = str(r.get("account")), r.get("family")
        if fam in excl_fam:
            excluded.append(a)
            continue
        b = books.get(a) or {}
        bt, xt, ewhy = exposure(b) if b else ("CANNOT DETERMINE (no book_dna row)", "CANNOT DETERMINE (no book_dna row)", "no row")
        ev = (b.get("evidence") or {}).get("label") if b else None
        row = {"account": a, "family": fam, "status": r.get("status"), "roi_pct": _num(r.get("roi_pct")),
               "spy_same_window_pct": _num(r.get("spy_same_window_pct")), "vs_spy_pp": _num(r.get("vs_spy_pp")),
               "inception": r.get("inception"), "last_mark": r.get("last_mark"), "mark_age_days": r.get("mark_age_days"),
               "sessions_graded": b.get("sessions_graded"), "evidence_label": ev, "beta": bt,
               "beta_adjusted_excess_pp": xt, "equity": _num(r.get("equity"))}
        (rows_main if is_main(a, fam) else rows_other).append(row)
    rows_main.sort(key=lambda x: (x["family"] or "", x["account"]))
    rows_other.sort(key=lambda x: (x["family"] or "", -(x["vs_spy_pp"] if x["vs_spy_pp"] is not None else -1e9), x["account"]))
    for row in rows_main:
        if row["status"] != "LIVE" or row["roi_pct"] is None:
            lines.append(line(RED, f"MAIN {row['account']} ({row['family']}): status {row['status']}, return CANNOT "
                                   f"DETERMINE", rr, gen, now, main=True))
    n_ctrl = sum(1 for r in rows_other if _excluded_from_headline(r["account"], r["family"]))
    ranked = sorted((r for r in rows_other if r["vs_spy_pp"] is not None
                     and not _excluded_from_headline(r["account"], r["family"])),
                    key=lambda x: (-x["vs_spy_pp"], x["account"]))
    k = int(_cfg("DAY_FILE_BOOKS_TOP_BOTTOM", 5))
    top, bottom = ranked[:k], ranked[-k:] if len(ranked) > k else []
    shown = {r["account"] for r in top + bottom}
    n_unrated = len(rows_other) - len(ranked)
    lines.append(line(INFO, f"{len(rows_main)} main accounts and the {len(top)} best and {len(bottom)} worst others by "
                            f"raw excess over SPY are in the tables; {len(rows_other) - len(shown)} other books are "
                            f"counted only ({n_unrated} of them have no SPY comparison, {n_ctrl} are twins / controls / "
                            f"rehearsal books kept out of the ranking); the full table is in the JSON",
                      rr, gen, now))
    if excluded:
        lines.append(line(INFO, f"left out by config.DAY_FILE_EXCLUDED_FAMILIES (the owner's own holdings are not "
                                f"reviewed): {', '.join(sorted(excluded))}", rr))
    return section("books", lines, data={"run_id": rid, "receipts": [rr, dr], "main": rows_main, "top": top,
                                          "bottom": bottom, "n_other": len(rows_other), "other": rows_other,
                                          "excluded": excluded})


# ═══════════════════════════════════════════════════════════════ 5. worst case

def _excluded_from_headline(book: str, family: Optional[str]) -> Optional[str]:
    """Why a book is left out of the worst-case headline (it is COUNTED, never silently dropped)."""
    if family in set(_cfg("DAY_FILE_WORST_EXCLUDE_FAMILIES", ())) or re.search(
            str(_cfg("DAY_FILE_WORST_EXCLUDE_RE", r"rehearsal")), book):
        return "retired / contest rehearsal / random twin or control"
    return None


def worst_section(data_root: Path, now: datetime, roi: Optional[dict], dna: Optional[dict], rid: Optional[str]) -> dict:
    gap = float(_cfg("DAY_FILE_GAP_NO_STOP", 0.30))
    out: list[dict] = []
    lines: list[dict] = []
    n_excl = n_not_live = 0
    fp, fr = newest_fleet_run(data_root, now)
    if fr is None:
        lines.append(line(CD, "no fleet_manager run receipt at or before the clock: the Alpaca accounts' positions "
                              "are not readable", "paper_accounts/fleet_manager/runs/"))
    else:
        fs = utc(fr.get("finished_utc") or fr.get("started_utc"))
        for a in fr.get("accounts") or []:
            if not isinstance(a, dict):
                continue
            role = str(a.get("role"))
            if str(a.get("status")).lower() != "ok":
                out.append({"book": role, "source": rel(fp, data_root), "stamp": fs, "worst_usd": None, "broker": True,
                            "why": f"status {a.get('status')} ({str(a.get('why') or '')[:80]}): positions not readable"})
                continue
            if not a.get("positions"):
                continue
            wc = a.get("worst_case_now") or {}
            if _num(wc.get("worst_usd")) is None:
                out.append({"book": role, "source": rel(fp, data_root), "stamp": fs, "worst_usd": None, "broker": True,
                            "why": "positions present but worst_case_now absent in the receipt"})
                continue
            out.append({"book": role, "source": f"{rel(fp, data_root)} accounts[{role}].worst_case_now", "stamp": fs,
                        "worst_usd": float(wc["worst_usd"]), "n_names": wc.get("n_names"),
                        "gross_over_equity": _num(wc.get("gross_over_equity")), "equity": _num(a.get("equity")),
                        "basis": "fleet manager: resting stop per name, else its own gap rule", "broker": True})
    sp, sd, why = pc_snapshot(data_root, now)
    if sd is None:
        out.append({"book": "PC-PAPER", "source": rel(sp, data_root), "stamp": None, "worst_usd": None, "broker": True,
                    "why": f"positions not readable: {why}"})
    else:
        pos = [p for p in sd.get("positions") or [] if isinstance(p, dict)]
        mv = [abs(_num(p.get("market_value")) or 0.0) for p in pos if _num(p.get("market_value")) is not None]
        eq = _num(sd.get("equity"))
        if pos and len(mv) == len(pos) and eq:
            out.append({"book": "PC-PAPER", "source": rel(sp, data_root), "stamp": utc(sd.get("t")),
                        "worst_usd": round(sum(mv) * gap, 2), "n_names": len(pos),
                        "gross_over_equity": round(sum(mv) / eq, 4), "equity": eq, "broker": True,
                        "basis": f"no stop recorded in this snapshot: |market value| x {gap:.0%} gap"})
        elif pos:
            out.append({"book": "PC-PAPER", "source": rel(sp, data_root), "stamp": utc(sd.get("t")), "worst_usd": None,
                        "broker": True, "why": f"{len(pos) - len(mv)} of {len(pos)} positions carry no market value, or no equity"})
    if isinstance(roi, dict) and isinstance(dna, dict):
        eq_by = {str(r.get("account")): _num(r.get("equity")) for r in roi.get("rows") or []}
        excl = set(_cfg("DAY_FILE_EXCLUDED_FAMILIES", ()))
        done = {x["book"] for x in out}
        for b in dna.get("books") or []:
            a = str(b.get("account"))
            if a in done or b.get("family") in excl or b.get("family") in ("alpaca_fleet", "pc_paper"):
                continue
            if b.get("status") != "LIVE":
                n_not_live += 1
                continue
            if _excluded_from_headline(a, b.get("family")):
                n_excl += 1
                continue
            w = b.get("weights")
            eq = eq_by.get(a)
            if not isinstance(w, dict) or not w:
                continue
            known = {t: abs(float(v)) for t, v in w.items() if _num(v) is not None}
            unknown = [t for t, v in w.items() if _num(v) is None]
            if eq is None or not known:
                out.append({"book": a, "source": f"paper_accounts/book_dna_{rid}.json", "stamp": None, "worst_usd": None,
                            "why": "no equity on the ROI row" if eq is None else "every weight is unpriced"})
                continue
            gross = sum(known.values())
            row = {"book": a, "source": f"paper_accounts/book_dna_{rid}.json weights x roi_{rid}.json equity",
                   "stamp": utc(roi.get("generated_utc")), "worst_usd": round(gross * eq * gap, 2),
                   "n_names": len(known), "gross_over_equity": round(gross, 4), "equity": eq,
                   "basis": f"no stop recorded: |weight| x equity x {gap:.0%} gap"}
            if unknown:
                row["basis"] += f"; LOWER BOUND, {len(unknown)} of {len(w)} names unpriced"
            out.append(row)
    known = sorted((x for x in out if x.get("worst_usd") is not None), key=lambda x: (-x["worst_usd"], x["book"]))
    unknown = [x for x in out if x.get("worst_usd") is None]
    brk = [x for x in known if x.get("broker")]
    oth = [x for x in known if not x.get("broker")]
    assume = (f"where a receipt records no stop the loss is assumed at a {gap:.0%} gap of the position "
              f"(config DAY_FILE_GAP_NO_STOP); a book's worst case is its gross exposure times that gap, not a forecast")
    if brk:
        x = brk[0]
        lines.append(line(INFO, f"LARGEST BROKER-HELD worst case: {x['book']} ${x['worst_usd']:,.0f} on {x['n_names']} "
                                f"name(s), gross {x['gross_over_equity']:.2f}x equity ${x['equity']:,.0f}; basis: "
                                f"{x['basis']}; {assume}", x["source"], x["stamp"], now))
    else:
        lines.append(line(CD, "no broker-held account's positions were readable, so the largest real-account worst "
                              "case CANNOT be determined", "fleet_manager/runs, pc_snapshot"))
    if oth:
        x = oth[0]
        lines.append(line(INFO, f"largest among the other {len(oth)} live paper books: {x['book']} ${x['worst_usd']:,.0f} "
                                f"(gross {x['gross_over_equity']:.2f}x equity ${x['equity']:,.0f}; {x['basis']}); left "
                                f"out of this ranking and counted: {n_excl} retired / contest-rehearsal / random-twin / "
                                f"control books, {n_not_live} not LIVE", x["source"], x["stamp"], now))
    for x in unknown:
        lines.append(line(RED, f"{x['book']}: worst case CANNOT be computed - {x['why']}", x["source"], x["stamp"], now))
    if not out:
        lines.append(line(CD, "no open paper book's positions were readable from any receipt",
                          "fleet_manager/runs, pc_snapshot, book_dna"))
    for x in out:
        x["stamp"] = iso(x["stamp"])
    return section("worst", lines, data={"gap_no_stop": gap, "assumption": assume, "broker_largest": brk[0] if brk else None,
                                         "n_excluded": n_excl, "n_not_live": n_not_live,
                                         "books": known + unknown})


# ═══════════════════════════════════════════════════════════════ 7. cohorts + dynamic books

def last_row(path: Path) -> tuple[Optional[dict], str]:
    """The newest JSON row of a journal, read from its tail: (row, why-not)."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 262144))
            tail = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None, f"{path.name} is absent or unreadable"
    for ln in reversed([x for x in tail.splitlines() if x.strip()]):
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if isinstance(d, dict):
            return d, ""
    return None, f"{path.name} has no readable row"


def _report_needs(rep: dict) -> dict:
    """Per family: the largest `cohorts_still_needed` over horizons and labels the report could
    plan (status OK), as (cohorts, weeks, horizon); None when it could not plan any."""
    out: dict = {}
    for fam, hz in ((rep.get("section_3_horizons") or {}).get("families") or {}).items():
        best = None
        for ks, labels in (hz or {}).items():
            for c in (labels or {}).values():
                pl = (c or {}).get("planning") or {}
                n = pl.get("cohorts_still_needed")
                if pl.get("status") == "OK" and type(n) is int and (best is None or n > best[0]):
                    best = (n, pl.get("weeks_at_cadence"), ks)
        out[fam] = best
    return out


def _newest_report(rc_dir: Path) -> tuple[Optional[Path], Optional[dict]]:
    files = sorted((rc_dir / "reports").glob("cohort_report_*.json")) if (rc_dir / "reports").is_dir() else []
    for p in reversed(files):
        d = read_json(p)
        if isinstance(d, dict) and d.get("report_id"):
            return p, d
    return None, None


def cohorts_section(data_root: Path, now: datetime) -> dict:
    lines: list[dict] = []
    rc_dir = data_root / "rolling_cohorts"
    p = rc_dir / "runs.jsonl"
    r = rel(p, data_root)
    row, why = last_row(p)
    data: dict = {}
    if row is None:
        lines.append(line(CD, f"rolling cohorts: no newest journal row ({why}): the newest cohort and the forward "
                              f"count CANNOT be determined", r, defect=p.exists()))
    else:
        t = utc(row.get("utc"))
        lim_h = float(_cfg("DAY_FILE_COHORT_STALE_HOURS", 8.0))
        stale = t is None or t > now or (now - t).total_seconds() > lim_h * 3600
        fa, sl = row.get("forward_age_sessions"), row.get("stale_limit_sessions")
        fa_bad = type(fa) is not int or (type(sl) is int and fa > sl)
        bad_act = row.get("action") in ("REFUSED", "STALE_PRICES", "MISSED_ENTRY_WINDOW")
        lines.append(line(RED if stale or bad_act else OK,
                          f"rolling cohorts: last step {row.get('action')} rc {row.get('rc')}, through "
                          f"{row.get('through')}; newest cohort {row.get('newest_cohort')}; newest FORWARD cohort "
                          f"{row.get('newest_forward_cohort') or 'none yet'}; {row.get('cohorts_forward')} forward of "
                          f"{row.get('cohorts_total')} cohorts ({row.get('cohorts_live')} live); "
                          f"{row.get('marks_total')} marks (red when the row is older than {lim_h:g} h)",
                          f"{r}[-1]", t, now))
        if fa_bad:
            lines.append(line(RED, f"forward cohort age is {fa!r} sessions against a limit of {sl!r}: the population is "
                                   f"not producing forward cohorts", f"{r}[-1]", t, now))
        data["rolling"] = {k: row.get(k) for k in ("action", "through", "newest_cohort", "newest_forward_cohort",
                                                   "cohorts_forward", "cohorts_total", "cohorts_live", "marks_total")}
    # cohorts still needed: the read-only cohort report's own figure when one exists
    rp, rep = _newest_report(rc_dir)
    if rep is not None:
        rt = utc(rep.get("generated_utc"))
        lim = float(_cfg("DAY_FILE_COHORT_REPORT_STALE_HOURS", 192.0))
        rstale = rt is None or (now - rt).total_seconds() > lim * 3600
        needs = _report_needs(rep)
        got = {f: v for f, v in needs.items() if v is not None}
        txt = (f"fewest {min(v[0] for v in got.values())}, most {max(v[0] for v in got.values())} more forward cohorts "
               f"(~{max(v[1] or 0 for v in got.values())} weeks for the slowest) across {len(got)} families"
               if got else "no family could be planned")
        lines.append(line(RED if rstale or not got else INFO,
                          f"cohort report {rep.get('report_id')} ({fmt_age(None if rt is None else (now - rt).total_seconds())} old, "
                          f"red after {lim:g} h; {rep.get('n_forward')} forward of {rep.get('n_cohorts')} cohorts): "
                          f"STILL NEEDED (unit: forward cohorts, per the report's planning sd): {txt}; "
                          f"{len(needs) - len(got)} families CANNOT DETERMINE",
                          rel(rp, data_root), rt, now))
        data["cohort_report"] = {"report_id": rep.get("report_id"), "needs": needs, "generated_utc": rep.get("generated_utc")}
    else:
        lines.append(line(CD, "no cohort_report_*.json under rolling_cohorts/reports: the cohorts still needed CANNOT be "
                              "taken from the report (run `python -m scripts.rolling_cohorts report`)",
                          "rolling_cohorts/reports/"))
        sb_name = Path(str((row or {}).get("scoreboard") or "").replace("\\", "/")).name
        sb_path = rc_dir / sb_name if sb_name else None
        sb = read_json(sb_path) if sb_path is not None and sb_path.is_file() else None
        if sb is not None:
            bd = (sb.get("boards") or {}).get("21") or {}
            need_min = int((bd.get("header_all") or bd.get("header") or {}).get("min_strict_blocks") or 0)
            fam = bd.get("families_all") or {}
            blocks = {k: max(0, need_min - int(v.get("n_blocks_strict") or 0)) for k, v in fam.items() if isinstance(v, dict)}
            if need_min and blocks:
                lines.append(line(INFO, f"derived from the scoreboard (NOT the report): strict date blocks still needed "
                                        f"(unit: 21-session blocks of 2 x 21 entry sessions, minus the {need_min} each test "
                                        f"needs): fewest {min(blocks.values())}, most {max(blocks.values())} across "
                                        f"{len(blocks)} families; a block is not a cohort", rel(sb_path, data_root)))
                data["derived_blocks"] = blocks
    # dynamic books (CH-45): present or UNKNOWN, never omitted
    dp = data_root / "dynamic_books" / "runs.jsonl"
    dr = rel(dp, data_root)
    drow, dwhy = last_row(dp)
    if drow is None:
        lines.append(line(CD, f"dynamic books: no journal row ({dwhy}); nothing has written one, so their status "
                              f"CANNOT be determined", dr, defect=dp.exists()))
    else:
        t = utc(drow.get("utc"))
        lim_h = float(_cfg("DAY_FILE_DYNAMIC_STALE_HOURS", 30.0))
        stale = t is None or t > now or (now - t).total_seconds() > lim_h * 3600
        okact = drow.get("action") in ("BORN", "MARKED", "NOTHING_DUE")
        lines.append(line(RED if stale or not okact else OK,
                          f"dynamic books: last step {drow.get('action')} rc {drow.get('rc')}, through "
                          f"{drow.get('through')}; {drow.get('cohorts_total')} cohorts, {drow.get('paths_total')} path "
                          f"rows; stale calendar {drow.get('calendar_stale') or 'none'} (red when older than "
                          f"{lim_h:g} h or not BORN/MARKED/NOTHING_DUE)", f"{dr}[-1]", t, now))
        data["dynamic"] = {k: drow.get(k) for k in ("action", "rc", "through", "cohorts_total", "paths_total")}
    return section("cohorts", lines, data=data)


# ═══════════════════════════════════════════════════════════════ 10. owner inbox

def inbox_section(data_root: Path, now: datetime, replay: bool = False) -> dict:
    from scripts import owner_inbox as OI
    p = OI.inbox_path(data_root)
    r = rel(p, data_root)
    if replay:
        return section("inbox", [line(CD, "REPLAY: the unread count is live state (a note's read status is not "
                                          "dated per clock), so it CANNOT be determined as of this clock", r)])
    if not p.exists():
        return section("inbox", [line(CD, "no owner_inbox/notes.jsonl: the unread count CANNOT be determined (the "
                                          "file is written by the first note)", r)])
    res = OI.list_notes(data_root=data_root)
    newest = max((utc(n.get("utc")) for n in res["notes"] if utc(n.get("utc"))), default=None)
    n_un, n_all, bad = int(res["n_unread"]), int(res["n_notes"]), int(res["unreadable_lines"])
    del res                                     # the note text is never carried into this page
    if bad and n_all == 0:
        return section("inbox", [line(CD, f"the inbox file has {bad} unreadable line(s) and no readable note: the unread "
                                          f"count CANNOT be determined", r, defect=True)])
    ls = [line(RED if n_un else OK, f"{n_un} unread note(s) of {n_all} (count only: read them with "
                                    f"`python -m scripts.owner_inbox list --unread`)", r, newest, now)]
    if bad:
        ls.append(line(RED, f"{bad} unreadable line(s) in the inbox file: the count above may be short", r, defect=True))
    return section("inbox", ls, data={"n_unread": n_un, "n_notes": n_all, "unreadable_lines": bad})


# ═══════════════════════════════════════════════════════════════ 6. forecasts

_RA = re.compile(r'"resolves_after":\s*"([^"]+)"')
_RS = re.compile(r'"resolved_at":\s*(?:null|"([^"]*)")')
_MA = re.compile(r'"made_at":\s*"([^"]+)"')


def forecasts_section(data_root: Path, now: datetime, lines_fn: Optional[Callable[[Path], Iterable[str]]] = None) -> dict:
    p = data_root / "predictions.jsonl"
    try:
        if lines_fn is None:
            from backend.services import forecast_ledger as FL
            if not FL.exists(p):
                return section("forecasts", [line(CD, "the forecast ledger is absent", rel(p, data_root), defect=True)])
            lines_fn = FL.logical_lines
        today = now.date().isoformat()
        nowi = iso(now)
        rows = after = active = overdue = resolved = undated = 0
        newest_made = None
        for ln in lines_fn(p):
            if not ln.strip():
                continue
            m = _MA.search(ln)
            made = m.group(1) if m else None
            if made and (utc(made) or now) > now:
                after += 1
                continue
            rows += 1
            if made and (newest_made is None or made > newest_made):
                newest_made = made
            r = _RS.search(ln)
            ra = r.group(1) if r else None
            if ra and (utc(ra) or now) <= now:
                resolved += 1
                continue
            a = _RA.search(ln)
            if not a:
                undated += 1
            elif a.group(1)[:10] < today:
                overdue += 1
            else:
                active += 1
    except Exception as exc:  # noqa: BLE001
        return section("forecasts", [line(CD, f"ledger read failed ({type(exc).__name__}: {str(exc)[:160]})",
                                          rel(p, data_root), defect=True)])
    nm = utc(newest_made)
    lim_h = float(_cfg("DAY_FILE_FORECAST_STALE_HOURS", 48.0))
    stale = nm is None or (now - nm).total_seconds() > lim_h * 3600
    ls = [line(INFO, f"{rows} rows made at or before the clock ({after} after it skipped): {active} active, "
                     f"{overdue} OVERDUE (definition: resolves_after date earlier than today's UTC date {today} and "
                     f"no resolved_at), {resolved} resolved, "
                     f"{undated} with no resolves_after", f"{rel(p, data_root)} (streamed read-only)", nm, now),
          line(RED if stale else OK, f"newest forecast made {newest_made} (red after {lim_h:g} h)",
               rel(p, data_root), nm, now)]
    if overdue:
        ls.append(line(RED, f"{overdue} overdue forecast(s): resolves_after earlier than {today} UTC, resolved_at "
                            f"empty (a count; the expiry policy is CH-42's)", rel(p, data_root), nm, now))
    return section("forecasts", ls, data={"rows": rows, "active": active, "overdue": overdue, "resolved": resolved,
                                          "undated": undated, "after_clock": after, "newest_made": newest_made})


# ═══════════════════════════════════════════════════════════════ 7. owner calls

def owner_calls_section(data_root: Path, now: datetime) -> dict:
    from backend.services import owner_calls as OC
    p = data_root / "owner_calls" / "states.jsonl"
    yday = (now.date() - timedelta(days=1)).isoformat()
    rows = []
    if p.exists():
        try:
            rows = [r for r in OC._jsonl(p) if isinstance(r, dict)]
        except Exception as exc:  # noqa: BLE001
            return section("owner_calls", [line(CD, f"states.jsonl unreadable ({type(exc).__name__})", rel(p, data_root),
                                                defect=True)])
    seen = [r for r in rows if (utc(r.get("recorded_utc")) or now + timedelta(days=1)) <= now]
    after = len(rows) - len(seen)
    lines: list[dict] = []
    pick = next((r for r in reversed(seen) if r.get("day") == yday), None)
    if pick is None:
        lines.append(line(RED, f"no pinned reading for UTC day {yday} at or before the clock ({len(seen)} pinned row(s) "
                               f"by then, {after} recorded after it; inception {OC.INCEPTION}"
                               + ("; that day is before inception, so it is SEEN_BEFORE_FREEZE and never pinned"
                                  if yday < OC.INCEPTION else "; `owner_calls record` did not run for it") + ")",
                          rel(p, data_root)))
        pick = seen[-1] if seen else None
    if pick is not None:
        rt = utc(pick.get("recorded_utc"))
        st = pick.get("states") or {}
        txt = "; ".join(f"{k}: {v.get('state')} ({v.get('hits')} hits / {v.get('n_titles')} titles, share {v.get('share')})"
                        for k, v in sorted(st.items()))
        lines.append(line(INFO, f"pinned reading for UTC day {pick.get('day')}, recorded {iso(rt)}: {txt}",
                          f"{rel(p, data_root)} (seal {pick.get('seal')})", rt, now, day=pick.get("day")))
    try:
        ch = OC.verify_chain(p) if p.exists() else {"ok": None}
        if ch.get("ok") is False:
            lines.append(line(RED, f"owner_calls state chain does NOT verify: {json.dumps(ch, default=str)[:200]}",
                              rel(p, data_root)))
    except Exception:  # noqa: BLE001
        pass
    # the same rule computed now from the corpus for that day, labelled as such (never a pinned reading)
    if OC.day_ended(yday, now):
        try:
            c = OC.daily_counts(data_root, yday)
            comp = {t: OC.theme_state(c, t) for t in OC.THEMES}
            lab = "SEEN_BEFORE_FREEZE" if yday < OC.INCEPTION else "UNPINNED (computed from today's corpus files)"
            lines.append(line(INFO, f"rule recomputed now for UTC day {yday} [{lab}]: "
                                    + "; ".join(f"{k}: {v['state']} ({v['hits']}/{v['n_titles']})" for k, v in sorted(comp.items()))
                                    + f"; sources present {len(c['sources_present'])} of {len(OC.SOURCES)}",
                              f"news_corpus/<source>/{yday}.jsonl (owner_calls.daily_counts)"))
        except Exception as exc:  # noqa: BLE001
            lines.append(line(CD, f"corpus recompute failed ({type(exc).__name__})", "news_corpus/"))
    return section("owner_calls", lines)


# ═══════════════════════════════════════════════════════════════ build + render

def build(data_root: Path, *, now: Optional[datetime] = None, wall: Optional[datetime] = None,
          repo: Path = REPO, status_fn: Optional[Callable[..., dict]] = None,
          forecast_lines: Optional[Callable[[Path], Iterable[str]]] = None,
          fomc_file: Optional[Path] = None) -> dict:
    data_root = Path(data_root)
    if not data_root.is_dir():
        raise DayFileRefused("DATA_ROOT_MISSING", f"{data_root} is not a directory")
    wall = wall or datetime.now(timezone.utc)
    now = now or wall
    if now > wall + timedelta(seconds=int(_cfg("DAY_FILE_REPLAY_SLACK_S", 3600))):
        raise DayFileRefused("NOW_IN_FUTURE", f"--now {iso(now)} is after the wall clock {iso(wall)}")
    replay = is_replay(now, wall)
    secs: dict[str, dict] = {}

    def guard(key: str, fn: Callable[[], dict]) -> None:
        try:
            secs[key] = fn()
        except Exception as exc:  # noqa: BLE001
            secs[key] = section(key, [], error=f"{type(exc).__name__}: {str(exc)[:200]}")

    rid, roi, dna, why = None, None, None, "not read"
    try:
        rid, roi, dna, why = book_pair(data_root, now)
    except Exception as exc:  # noqa: BLE001
        why = f"book pair read raised {type(exc).__name__}"
    rec, err = collect_status(data_root, now, replay=replay, status_fn=status_fn)
    guard("red", lambda: red_section(rec, err, now, replay=replay))
    guard("schedule", lambda: schedule_section(rec, err, now))
    guard("dates", lambda: dates_section(data_root, now, dna, fomc_file=fomc_file))
    guard("events", lambda: events_section(data_root, now))
    guard("books", lambda: books_section(data_root, now, rid, roi, dna, why))
    guard("worst", lambda: worst_section(data_root, now, roi, dna, rid))
    guard("cohorts", lambda: cohorts_section(data_root, now))
    guard("forecasts", lambda: forecasts_section(data_root, now, forecast_lines))
    guard("owner_calls", lambda: owner_calls_section(data_root, now))
    guard("inbox", lambda: inbox_section(data_root, now, replay))
    ordered = {k: secs[k] for k, _ in SECTIONS}
    not_ok = [k for k, s in ordered.items() if s["status"] != OK]
    defects = [f"{k}: {ln['text'][:200]}" for k, s in ordered.items() for ln in s["lines"]
               if (ln.get("extra") or {}).get("defect")]
    rec = {"schema": SCHEMA, "receipt": "day_file", "day": local_day(now), "tz": str(_cfg("DAY_FILE_TZ", "Asia/Hong_Kong")),
           "now_utc": iso(now), "generated_utc": iso(wall), "replay": replay, "data_root": f"<data root> {data_root.name}",
           "sections": ordered, "sections_not_ok": not_ok, "red_sections": [k for k in not_ok if ordered[k]["status"] == RED],
           "sections_cannot_determine": [k for k, s in ordered.items() if s["status"] == CD],
           "defects": defects,
           "read_me_first": ("Built only from receipts on disk; every line names its receipt and that receipt's age "
                             "relative to now_utc. CANNOT_DETERMINE is never fine and never 0. Read-only: no broker, "
                             "no LLM, no network, no probe of its own: the systems rows are the newest "
                             "system_status/status.json. Exit 0 = written and faithful even when it reports red "
                             "content; 2 = this file is itself defective (see `defects`); 3 = not written.")}
    rec["today"] = today_block(rec)
    return rec


def today_block(rec: dict) -> list[str]:
    """The opening summary: at most `DAY_FILE_TODAY_MAX_LINES` lines, all read from the sections."""
    sec = rec["sections"]
    d = {k: (v.get("data") or {}) for k, v in sec.items()}

    def pct(x: Any) -> str:
        return "n/a" if x is None else f"{x:+.1f}%"

    L: list[str] = []
    bad = rec["sections_not_ok"]
    L.append("Sections not OK (" + str(len(bad)) + "): " + (", ".join(f"{k}={sec[k]['status']}" for k in bad) or "none"))
    L.append("This file's own defects (exit 2): " + (str(len(rec["defects"])) + " - " + "; ".join(
        x[:90] for x in rec["defects"][:3]) if rec["defects"] else "none"))
    down = d["red"].get("down")
    if down is None:
        L.append("DOWN rows: CANNOT DETERMINE (the systems receipt is unreadable)")
    else:
        L.append(f"DOWN rows ({len(down)}): " + (", ".join(down[:10]) + (f" (+{len(down) - 10})" if len(down) > 10 else "")
                                                   if down else "none"))
    bk = d["books"]
    main = bk.get("main") or []
    fams = set(_cfg("DAY_FILE_BROKER_FAMILIES", ()))
    shown = set(_cfg("DAY_FILE_SHOWN_ACCOUNTS", ()))
    if not main:
        L.append("Main accounts: CANNOT DETERMINE (no book pair)")
    else:
        b1 = [r for r in main if r["family"] in fams]
        b2 = [r for r in main if r["account"] in shown]
        L.append("Broker-held, return (SPY same window): " + ", ".join(
            f"{r['account']} {pct(r['roi_pct'])} ({pct(r['spy_same_window_pct'])})" for r in b1))
        L.append("Shown accounts, return (SPY same window): " + ", ".join(
            f"{r['account']} {pct(r['roi_pct'])} ({pct(r['spy_same_window_pct'])})" for r in b2))
    bl = d["worst"].get("broker_largest")
    L.append("Largest BROKER-HELD worst case: " + (
        f"{bl['book']} ${bl['worst_usd']:,.0f} (gross {bl['gross_over_equity']:.2f}x equity; {bl['basis']}; "
        f"{float(_cfg('DAY_FILE_GAP_NO_STOP', 0.3)):.0%} gap assumed where no stop is recorded)" if bl
        else "CANNOT DETERMINE"))
    fc = d["forecasts"]
    L.append("Overdue forecasts: " + (f"{fc['overdue']} (resolves_after earlier than today's UTC date and no resolved_at; "
                                      f"{fc['active']} active, {fc['resolved']} resolved)" if "overdue" in fc else "CANNOT DETERMINE"))
    ne = d["dates"].get("next_event")
    L.append("Next dated event: " + (f"{ne['date']} {ne['what']}" if ne else "CANNOT DETERMINE"))
    ro = (d["cohorts"].get("rolling") or {})
    L.append("Rolling cohorts: " + (f"newest {ro.get('newest_cohort')}, {ro.get('cohorts_forward')} forward of "
                                    f"{ro.get('cohorts_total')}" if ro else "CANNOT DETERMINE")
             + "; dynamic books: " + (str((d["cohorts"].get("dynamic") or {}).get("action")) if d["cohorts"].get("dynamic")
                                       else "CANNOT DETERMINE"))
    L.append("Owner inbox unread: " + (str(d["inbox"]["n_unread"]) if "n_unread" in d["inbox"] else "CANNOT DETERMINE"))
    cap = int(_cfg("DAY_FILE_TODAY_MAX_LINES", 15))
    return [x[:420] for x in L[:cap]]


def _md_line(ln: dict) -> str:
    tag = {OK: "ok", INFO: "", RED: "RED", CD: "CANNOT DETERMINE"}[ln["status"]]
    src = ln.get("receipt") or "(no receipt)"
    age = f", {fmt_age(ln['age_s'])} old" if ln.get("age_s") is not None else ""
    return f"- {'**' + tag + '** ' if tag else ''}{ln['text']} `[{src}{age}]`"


def _pct(x: Optional[float], plus: bool = True) -> str:
    return "CANNOT DETERMINE" if x is None else (f"{x:+.2f}" if plus else f"{x:.2f}")


def _book_table(rows: list[dict], receipt: str) -> list[str]:
    out = ["| account | family | status | return % | SPY same window % | raw excess pp | sessions | label | "
           "realised beta | beta-adj. excess pp | last mark |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['account']} | {r['family']} | {r['status']} | {_pct(r['roi_pct'])} | "
                   f"{_pct(r['spy_same_window_pct'])} | {_pct(r['vs_spy_pp'])} | {r['sessions_graded'] if r['sessions_graded'] is not None else 'CANNOT DETERMINE'} | "
                   f"{r['evidence_label'] or 'CANNOT DETERMINE'} | {r['beta']} | {r['beta_adjusted_excess_pp']} | "
                   f"{r['last_mark'] or 'CANNOT DETERMINE'} |")
    out.append(f"\nevery row: `{receipt}`")
    return out


def render_md(rec: dict, run_name: str) -> str:
    nr = rec["red_sections"]
    head = (f"# Day file {rec['day']} | RED: {', '.join(nr) if nr else 'none'} | CANNOT DETERMINE: "
            f"{', '.join(rec['sections_cannot_determine']) or 'none'} | file defects: {len(rec['defects'])}")
    L = [head, "",
         f"Clock `{rec['now_utc']}`" + (" - **REPLAY** (rows written after the clock are skipped; live machine state "
                                        "is CANNOT DETERMINE)" if rec["replay"] else "")
         + f" · generated `{rec['generated_utc']}` · `{run_name}` · {rec['data_root']} · {rec['tz']}", "",
         "## TODAY", ""] + [f"- {x}" for x in rec["today"]] + ["", f"> {rec['read_me_first']}"]
    for key, s in rec["sections"].items():
        L += ["", f"## {s['title']} - {s['status']}", ""]
        if key == "books" and s.get("data"):
            d = s["data"]
            rc = " + ".join(d.get("receipts") or [])
            L += [_md_line(ln) for ln in s["lines"]]
            L += ["", "Main accounts"] + _book_table(d.get("main") or [], rc)
            L += ["", f"Best {len(d.get('top') or [])} of the other {d.get('n_other')} books by raw excess"] + _book_table(d.get("top") or [], rc)
            L += ["", f"Worst {len(d.get('bottom') or [])}"] + _book_table(d.get("bottom") or [], rc)
            continue
        L += [_md_line(ln) for ln in s["lines"]]
    L += ["", "---", "Exit: 0 written and faithful (red content is reported, not an error); 2 written but this file is "
                     "itself defective (systems receipt stale or missing, a section missing or raising, a source of "
                     "truth unreadable); 3 not written. `python -m scripts.day_file`."]
    return "\n".join(L) + "\n"


# ═══════════════════════════════════════════════════════════════ io + probe + cli

def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    if tmp.read_text(encoding="utf-8") != text:
        tmp.unlink(missing_ok=True)
        raise OSError(f"verify failed for {tmp}")
    os.replace(tmp, path)


def write(rec: dict, out_dir: Path) -> tuple[Path, Path, Path]:
    """Run-stamped files (never overwritten), then DAY_<date>.md/.json repointed at them."""
    stamp = utc(rec["generated_utc"]).strftime("%Y%m%dT%H%M%SZ")
    base = f"DAY_{rec['day']}"
    md_p, js_p = out_dir / f"{base}__{stamp}.md", out_dir / f"{base}__{stamp}.json"
    if md_p.exists() or js_p.exists():
        raise OSError(f"{md_p.name} already exists: a run stamp is never reused")
    md = render_md(rec, md_p.name)
    js = json.dumps({**rec, "run_file": md_p.name}, indent=1, default=str)
    _atomic(js_p, js)
    _atomic(md_p, md)
    ptr = out_dir / f"{base}.md"
    _atomic(ptr, md + f"\n<!-- pointer: newest run of {rec['day']} is {md_p.name}; earlier runs keep their own "
                 f"stamped files -->\n")
    _atomic(out_dir / f"{base}.json", js)
    return md_p, js_p, ptr


def p_day_file(ctx: Any) -> Any:
    """`system_health` probe: the newest run-stamped DAY_*.json under `<optimus>/day_file/`,
    dated by its own `generated_utc` (never mtime). A missing day file is UNKNOWN (red)."""
    from backend.services.system_health import ProbeResult, _unknown
    d = Path(ctx.optimus_dir) / str(_cfg("DAY_FILE_DIRNAME", "day_file"))
    files = sorted(p for p in (d.glob("DAY_*__*.json") if d.is_dir() else []) if _STAMP_RE.match(p.name))
    files = [p for p in files if (utc(_STAMP_RE.match(p.name).group(2)) or ctx.now) <= ctx.now]
    if not files:
        return _unknown(f"no run-stamped DAY_<date>__<stamp>.json under {d.name}/: nothing has written a day file")
    rec = read_json(files[-1])
    t = utc((rec or {}).get("generated_utc")) if isinstance(rec, dict) else None
    if t is None:
        return _unknown(f"{files[-1].name} unreadable or undated")
    age = round((ctx.now - t).total_seconds(), 1)
    lim = float(_cfg("DAY_FILE_STALE_HOURS", 26.0)) * 3600
    bad = rec.get("sections_not_ok") or []
    return ProbeResult("ALIVE" if age <= lim else "STALE", iso(t), age,
                       f"{files[-1].name}: {len(bad)} section(s) not OK ({', '.join(bad)})"
                       + (" [REPLAY file]" if rec.get("replay") else ""),
                       proof="day_file/DAY_<date>__<stamp>.json generated_utc; never mtime")


def _count_files(root: Path) -> Optional[int]:
    try:
        return sum(len(fs) for _, _, fs in os.walk(root))
    except OSError:
        return None


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Write DAY_<date>.md + .json from receipts (read-only otherwise).")
    ap.add_argument("--data-root", type=Path, default=Path(C.OPTIMUS_LEDGER_DIR), help="the optimus ledger dir")
    ap.add_argument("--out", type=Path, default=None, help="default: <data-root>/day_file")
    ap.add_argument("--now", default=None, help="ISO clock; in the past it is a replay")
    ap.add_argument("--repo", type=Path, default=REPO)
    ap.add_argument("--fomc-file", type=Path, default=None)
    ap.add_argument("--count-files", action="store_true", help="print the data root's file count before and after")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    now = None
    if a.now:
        now = utc(a.now)
        if now is None:
            print(f"REFUSED NOW_INVALID: {a.now!r} is not an ISO time", file=sys.stderr)
            return 3
    before = _count_files(a.data_root) if a.count_files else None
    try:
        rec = build(a.data_root, now=now, repo=a.repo, fomc_file=a.fomc_file)
        out_dir = a.out or (a.data_root / str(_cfg("DAY_FILE_DIRNAME", "day_file")))
        md_p, js_p, ptr = write(rec, out_dir)
    except DayFileRefused as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"NOT WRITTEN: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    print(f"wrote {md_p}\n      {js_p}\n      {ptr} (pointer)")
    for k, s in rec["sections"].items():
        n_red = sum(1 for ln in s["lines"] if ln["status"] in (RED, CD))
        print(f"  {s['status']:<17} {k:<12} {n_red} red/undeterminable line(s)")
    if a.count_files:
        after = _count_files(a.data_root)
        print(f"data-root files before {before} after {after}")
    if rec["sections_not_ok"]:
        print("NOT OK: " + ", ".join(f"{k}={rec['sections'][k]['status']}" for k in rec["sections_not_ok"]))
    if rec["defects"]:
        print(f"DEFECTIVE FILE ({len(rec['defects'])}): " + "; ".join(x[:120] for x in rec["defects"]), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
