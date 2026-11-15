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
1. Red rows: `scripts.system_status.collect` (which runs every `system_health`
   probe without its public redaction, plus its own learning/universe/books/night/
   machine rows and the `schtasks` view). Only non-OK rows are printed.
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
* No network except `gh` (through system_status). Railway HTTP and the `railway`
  CLI are refused inside this run.
* Exit 0 written and nothing red or undeterminable; 2 written with a red or
  CANNOT DETERMINE section (printed); 3 could not be written.
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
    ("red", "1. Red rows (stale, empty, refused or missing sources; scheduled tasks)"),
    ("dates", "2. Scheduled today and the next sessions (held names, sensors, macro)"),
    ("events", "3. Open event nodes"),
    ("books", "4. Books (main accounts first)"),
    ("worst", "5. Largest dollar worst case across open paper books"),
    ("forecasts", "6. Forecasts (counts only)"),
    ("owner_calls", "7. Owner-calls reading (yesterday)"),
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


def line(status: str, text: str, receipt: str = "", stamp: Optional[datetime] = None,
         now: Optional[datetime] = None, **extra: Any) -> dict:
    age = None if (stamp is None or now is None) else round((now - stamp).total_seconds(), 1)
    return {"status": status, "text": text, "receipt": receipt, "receipt_utc": iso(stamp),
            "age_s": age, **({"extra": extra} if extra else {})}


def section(key: str, lines: list[dict], *, error: Optional[str] = None, data: Any = None) -> dict:
    title = dict(SECTIONS)[key]
    if error:
        lines = lines + [line(CD, f"section reader failed: {error}")]
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
        return str(p).replace("\\", "/")


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

def _no_network(url: str, timeout: float) -> tuple:
    return None, 0.0, "NETWORK_DISABLED_IN_DAY_FILE"


def _guarded_run(argv: list, timeout: float) -> tuple:
    """`system_health`'s runner, minus anything that leaves the box but `gh`."""
    if argv and Path(str(argv[0])).stem.lower() in {"railway", "curl", "wget"}:
        return 127, ""
    from backend.services import system_health as SH
    return SH._default_run(argv, timeout)


_LIVE_ONLY_ROWS = {"ram_free", "last_boot", "sleep_settings", "open_prs"}


def red_section(data_root: Path, now: datetime, *, replay: bool, repo: Path,
                status_fn: Optional[Callable[..., dict]] = None) -> dict:
    lines: list[dict] = []
    try:
        if status_fn is None:
            from backend.services import system_health as SH
            from scripts import system_status as SS
            ctx = SH.make_ctx(optimus_dir=data_root, now=now, allow_proc=not replay, repo=repo,
                              http_json=_no_network, run=_guarded_run)
            rec = SS.collect(optimus_dir=data_root, repo=repo, now=now, allow_proc=not replay, ctx=ctx,
                             run=_guarded_run)
        else:
            rec = status_fn(data_root=data_root, now=now, replay=replay)
    except Exception as exc:  # noqa: BLE001
        return section("red", [], error=f"system_status.collect raised {type(exc).__name__}: {str(exc)[:200]}")
    counts = rec.get("counts") or {}
    tasks = (rec.get("sections") or {}).get("tasks", {}).get("rows") or []
    sched_unknown = any(r.get("name") == "scheduler" and r.get("status") == "UNKNOWN" for r in tasks)
    if replay:
        lines.append(line(CD, "REPLAY: the Windows scheduler, processes, RAM and boot time are live state "
                              "and cannot be read as of this clock; those rows are left out",
                          "schtasks /query; GlobalMemoryStatusEx"))
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
    lines.insert(0, line(INFO, f"system_status: {counts.get('OK', 0)} OK, {counts.get('DEGRADED', 0)} degraded, "
                               f"{counts.get('DOWN', 0)} down, {counts.get('UNKNOWN', 0)} unknown; "
                               f"{n_red} non-OK rows listed below",
                         "scripts/system_status.py collect() (system_health probes + its own rows), run now",
                         utc(rec.get("generated_utc")), now))
    return section("red", lines, data={"counts": counts, "undetermined": rec.get("undetermined")})


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

def _fomc_path(data_root: Path, override: Optional[Path]) -> Path:
    if override:
        return Path(override)
    cand = data_root.parent / "fomc_schedule.json"
    if cand.exists():
        return cand
    from backend.services import macro_calendar as MC
    return MC.fomc_path() if MC.fomc_path().exists() else REPO / "backend" / "data" / "fomc_schedule.json"


def dates_section(data_root: Path, now: datetime, dna: Optional[dict], *, fomc_file: Optional[Path] = None) -> dict:
    from backend.services import forward_calendar as FC
    lines: list[dict] = []
    n_sess = int(_cfg("DAY_FILE_UPCOMING_SESSIONS", 10))
    today = FC.market_date(now)
    sess_today = is_session(today)
    lines.append(line(INFO, f"New York market date {today.isoformat()}: "
                            + ("a session day" if sess_today else "NOT a session day" if sess_today is False
                               else "session status CANNOT be determined (market_sessions unavailable)"),
                      "backend/services/market_sessions.py"))
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
                          f"{len(want)} names asked ({len(held)} held by an open paper book, {len(sensors)} sensors); "
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
        for t, r in upcoming:
            who = "sensor" if t in sensors else "held"
            lines.append(line(INFO, f"{r['date']} ({r['sessions_away']} session(s) away, {r.get('timing') or 'time ?'}, "
                                    f"{r.get('confirmation') or 'unconfirmed'}): {t} earnings [{who}]",
                              f"{store} pull {r.get('pull_id')}", utc(r.get("pulled_utc")), now))
        if not upcoming:
            lines.append(line(INFO, f"no held or sensor name has an earnings date in the next {n_sess} sessions "
                                    f"(among the {counts.get(FC.DATE_IN_HORIZON, 0)} names with a date in horizon)",
                              store))
        data["counts"] = counts
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
        for r in sorted(mac.get("dates") or [], key=lambda x: (x["date"], str(x.get("kind")))):
            lines.append(line(INFO, f"{r['date']} ({r['days_away']} day(s) away): {r.get('kind')} - {r.get('what')}",
                              f"forward_calendar/snapshots/{mac.get('pull_id')}.jsonl ({r.get('source')})",
                              utc(mac.get("pulled_utc")), now))
    # the Fed table itself: NOT_SEEDED / STALE / verified after the clock are red rows
    try:
        from backend.services import macro_calendar as MC
        fp = _fomc_path(data_root, fomc_file)
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
                          rel(fp, data_root) if fp.exists() else str(fp)))
        if ok_tb:
            for d in nxt:
                dd = (date.fromisoformat(d) - now.date()).days
                if dd <= hz:
                    lines.append(line(INFO, f"{d} ({dd} day(s) away): FOMC statement", rel(fp, data_root)))
    except Exception as exc:  # noqa: BLE001
        lines.append(line(CD, f"FOMC table unreadable ({type(exc).__name__}: {str(exc)[:160]})", "fomc_schedule.json"))
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
                                           f"{str(exc)[:200]}", rel(store, data_root))])
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
    for i, b in enumerate(briefs[:int(_cfg("DAY_FILE_TOP_EVENTS", 10))], 1):
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
    if family in set(_cfg("DAY_FILE_MAIN_FAMILIES", ("website_lane",))):
        return "__" not in account
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
        return section("books", [line(CD, f"no book pair: {why}", "paper_accounts/roi_<run>.json + book_dna_<run>.json")])
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
    rows_main, rows_other, excluded = [], [], []
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
        bad = row["status"] != "LIVE" or row["roi_pct"] is None
        lines.append(line(RED if bad else INFO, f"MAIN {row['account']} ({row['family']}): status {row['status']}"
                          + ("" if bad else f", return {row['roi_pct']:+.2f}%"), rr, gen, now, main=True))
    if excluded:
        lines.append(line(INFO, f"left out by config.DAY_FILE_EXCLUDED_FAMILIES (the owner's own holdings are not "
                                f"reviewed): {', '.join(sorted(excluded))}", rr))
    return section("books", lines, data={"run_id": rid, "receipts": [rr, dr], "main": rows_main, "other": rows_other,
                                          "excluded": excluded})


# ═══════════════════════════════════════════════════════════════ 5. worst case

def worst_section(data_root: Path, now: datetime, roi: Optional[dict], dna: Optional[dict], rid: Optional[str]) -> dict:
    gap = float(_cfg("DAY_FILE_GAP_NO_STOP", 0.30))
    out: list[dict] = []
    lines: list[dict] = []
    # (a) broker-truth accounts from the fleet manager's own receipt
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
                out.append({"book": role, "source": rel(fp, data_root), "stamp": fs, "worst_usd": None,
                            "why": f"status {a.get('status')} ({str(a.get('why') or '')[:80]}): positions not readable"})
                continue
            if not a.get("positions"):
                continue
            wc = a.get("worst_case_now") or {}
            if _num(wc.get("worst_usd")) is None:
                out.append({"book": role, "source": rel(fp, data_root), "stamp": fs, "worst_usd": None,
                            "why": "positions present but worst_case_now absent in the receipt"})
                continue
            out.append({"book": role, "source": f"{rel(fp, data_root)} accounts[{role}].worst_case_now", "stamp": fs,
                        "worst_usd": float(wc["worst_usd"]), "n_names": wc.get("n_names"),
                        "gross_over_equity": _num(wc.get("gross_over_equity")),
                        "equity": _num(a.get("equity")),
                        "basis": "fleet manager: resting stop per name, else its own gap rule"})
    # (b) the PC paper account (no stop recorded in its snapshot -> the gap)
    sp, sd, why = pc_snapshot(data_root, now)
    if sd is None:
        out.append({"book": "PC-PAPER", "source": rel(sp, data_root), "stamp": None, "worst_usd": None,
                    "why": f"positions not readable: {why}"})
    else:
        pos = [p for p in sd.get("positions") or [] if isinstance(p, dict)]
        mv = [abs(_num(p.get("market_value")) or 0.0) for p in pos if _num(p.get("market_value")) is not None]
        eq = _num(sd.get("equity"))
        if pos and len(mv) == len(pos) and eq:
            out.append({"book": "PC-PAPER", "source": rel(sp, data_root), "stamp": utc(sd.get("t")),
                        "worst_usd": round(sum(mv) * gap, 2), "n_names": len(pos),
                        "gross_over_equity": round(sum(mv) / eq, 4), "equity": eq,
                        "basis": f"no stop recorded in this snapshot: |market value| x {gap:.0%} gap"})
        elif pos:
            out.append({"book": "PC-PAPER", "source": rel(sp, data_root), "stamp": utc(sd.get("t")), "worst_usd": None,
                        "why": f"{len(pos) - len(mv)} of {len(pos)} positions carry no market value, or no equity"})
    # (c) every other LIVE book with recorded weights: weights x ROI equity x gap
    if isinstance(roi, dict) and isinstance(dna, dict):
        eq_by = {str(r.get("account")): _num(r.get("equity")) for r in roi.get("rows") or []}
        excl = set(_cfg("DAY_FILE_EXCLUDED_FAMILIES", ()))
        done = {x["book"] for x in out}
        for b in dna.get("books") or []:
            a = str(b.get("account"))
            if b.get("status") != "LIVE" or a in done or b.get("family") in excl or b.get("family") in ("alpaca_fleet", "pc_paper"):
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
                row["partial"] = True
            out.append(row)
    known = sorted((x for x in out if x.get("worst_usd") is not None), key=lambda x: (-x["worst_usd"], x["book"]))
    unknown = [x for x in out if x.get("worst_usd") is None]
    top = int(_cfg("DAY_FILE_TOP_WORST", 15))
    for x in known[:top]:
        lines.append(line(INFO, f"{x['book']}: worst ${x['worst_usd']:,.0f} on {x['n_names']} name(s); gross "
                                f"{x['gross_over_equity']:.2f}x equity ${x['equity']:,.0f}; {x['basis']}",
                          x["source"], x["stamp"], now))
    if len(known) > top:
        lines.append(line(INFO, f"{len(known) - top} more books with a computed worst case are in the JSON", "DAY_<date>.json"))
    for x in unknown:
        lines.append(line(RED, f"{x['book']}: worst case CANNOT be computed - {x['why']}", x["source"], x["stamp"], now))
    if not out:
        lines.append(line(CD, "no open paper book's positions were readable from any receipt",
                          "fleet_manager/runs, pc_snapshot, book_dna"))
    for x in out:
        x["stamp"] = iso(x["stamp"])
    return section("worst", lines, data={"gap_no_stop": gap, "books": known + unknown})


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
                return section("forecasts", [line(RED, "the forecast ledger is absent", rel(p, data_root))])
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
                                          rel(p, data_root))])
    nm = utc(newest_made)
    lim_h = float(_cfg("DAY_FILE_FORECAST_STALE_HOURS", 48.0))
    stale = nm is None or (now - nm).total_seconds() > lim_h * 3600
    ls = [line(INFO, f"{rows} rows made at or before the clock ({after} after it skipped): {active} active, "
                     f"{overdue} overdue (resolves_after before {today}, still unresolved), {resolved} resolved, "
                     f"{undated} with no resolves_after", f"{rel(p, data_root)} (streamed read-only)", nm, now),
          line(RED if stale else OK, f"newest forecast made {newest_made} (red after {lim_h:g} h)",
               rel(p, data_root), nm, now)]
    if overdue:
        ls.append(line(RED, f"{overdue} forecast(s) are past their resolution date and ungraded (expiry policy is "
                            f"CH-42's; this is a count)", rel(p, data_root), nm, now))
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
            return section("owner_calls", [line(CD, f"states.jsonl unreadable ({type(exc).__name__})", rel(p, data_root))])
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
    guard("red", lambda: red_section(data_root, now, replay=replay, repo=repo, status_fn=status_fn))
    guard("dates", lambda: dates_section(data_root, now, dna, fomc_file=fomc_file))
    guard("events", lambda: events_section(data_root, now))
    guard("books", lambda: books_section(data_root, now, rid, roi, dna, why))
    guard("worst", lambda: worst_section(data_root, now, roi, dna, rid))
    guard("forecasts", lambda: forecasts_section(data_root, now, forecast_lines))
    guard("owner_calls", lambda: owner_calls_section(data_root, now))
    ordered = {k: secs[k] for k, _ in SECTIONS}
    not_ok = [k for k, s in ordered.items() if s["status"] != OK]
    return {"schema": SCHEMA, "receipt": "day_file", "day": local_day(now), "tz": str(_cfg("DAY_FILE_TZ", "Asia/Hong_Kong")),
            "now_utc": iso(now), "generated_utc": iso(wall), "replay": replay, "data_root": str(data_root),
            "sections": ordered, "sections_not_ok": not_ok,
            "sections_cannot_determine": [k for k, s in ordered.items() if s["status"] == CD],
            "read_me_first": ("Built only from receipts on disk; every line names its receipt and that receipt's age "
                              "relative to now_utc. CANNOT_DETERMINE is never fine and never 0. Read-only: no broker, "
                              "no LLM, no network but gh.")}


def _md_line(ln: dict) -> str:
    tag = {OK: "ok", INFO: "  ", RED: "RED", CD: "CANNOT DETERMINE"}[ln["status"]]
    src = ln.get("receipt") or "(no receipt)"
    age = f", {fmt_age(ln['age_s'])} old" if ln.get("age_s") is not None else ""
    return f"- **{tag}** {ln['text']}  \n  <sub>receipt: `{src}`{age}</sub>"


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
    out.append(f"\n<sub>every row: `{receipt}`</sub>")
    return out


def render_md(rec: dict, run_name: str) -> str:
    L = [f"# Day file {rec['day']} ({rec['tz']})", "",
         f"Clock `{rec['now_utc']}`" + (" - **REPLAY** (rows written after the clock are skipped; live machine state "
                                        "is CANNOT DETERMINE)" if rec["replay"] else "")
         + f" · generated `{rec['generated_utc']}` · this run: `{run_name}` · data root `{rec['data_root']}`", ""]
    bad = rec["sections_not_ok"]
    L.append("**Sections not OK:** " + (", ".join(f"{k} ({rec['sections'][k]['status']})" for k in bad) if bad else "none"))
    L.append("")
    L.append(f"> {rec['read_me_first']}")
    for key, s in rec["sections"].items():
        L += ["", f"## {s['title']} - {s['status']}", ""]
        if key == "books" and s.get("data"):
            d = s["data"]
            rc = " + ".join(d.get("receipts") or [])
            L.append("### Main accounts")
            L += _book_table(d.get("main") or [], rc)
            L += [""] + [_md_line(ln) for ln in s["lines"]]
            L += ["", f"### Every other book in the pair ({len(d.get('other') or [])})"]
            L += _book_table(d.get("other") or [], rc)
            continue
        L += [_md_line(ln) for ln in s["lines"]]
    L += ["", "---", "Exit: 0 written and every section OK; 2 written with a red or CANNOT DETERMINE section; "
                     "3 not written. Generated by `python -m scripts.day_file`."]
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
    _atomic(ptr, f"<!-- pointer: newest run of {rec['day']} is {md_p.name}; earlier runs keep their own "
                 f"stamped files -->\n" + md)
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
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
