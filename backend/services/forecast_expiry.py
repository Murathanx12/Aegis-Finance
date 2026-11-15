"""Forecast and evidence expiry (roadmap CH-42): every forecast gets a `valid_until`.

    python -m scripts.forecast_expiry sweep  --data-root <optimus dir> --out <dir>
    python -m scripts.forecast_expiry labels --data-root <optimus dir> --out <dir>

WHAT THIS ANSWERS
=================
Six months of forecasts never aged. A row in `predictions.jsonl` carries a
`resolves_after` -- a deliberately GENEROUS calendar bound (`horizon * 1.45 + 3`
days, `belief_state.PredictionRecord.resolution_date`) that tells the resolver
when it may grade -- but nothing said when the claim stopped being a live claim.
This module derives that date from the row's own fields on the XNYS session
calendar and sorts every row into exactly one state:

* ``VOID``              -- the row carries a `void_reason` (the existing vocabulary,
                           `forecast_grader.VOID_REASONS` and the threshold voids);
* ``EXPIRED_GRADED``    -- the row has an outcome: it belongs in the graded archive;
* ``UNDATED``           -- no `valid_until` can be derived from the row (named, counted,
                           never silently ACTIVE);
* ``EXPIRED_UNGRADED``  -- `as_of > valid_until` and no outcome: the window closed and a
                           grade is owed;
* ``ACTIVE``            -- the window is still open.

Each ledger's rows read = the five counts, printed as a reconciliation.

READ-ONLY OVER THE LEDGERS
==========================
The forecast rows are frozen (canon: append-only, no mutation of seeded
histories). Nothing here opens a ledger for writing. The sweep writes only its
own SIDE ledger, ``<out>/forecast_expiry/expiry.jsonl``, append-only: a second
sweep appends a row only when an id's (state, valid_until, reason code) changed.
Every row carries the sha256 of the ledger line it was derived from, so a later
reader can tell whether the frozen row it describes is still the same bytes.

THE VOID RULE IS STATED BEFORE ANYTHING IS COUNTED
==================================================
A due, ungraded row is dispositioned RESOLVABLE_NOW / WAITING_INPUT / VOID
(proposed, side ledger only) by `disposition()`. It reads the ticker, benchmark,
horizon, window dates and the LOCAL bar panel -- never `probability`, `outcome`
or `brier` -- and the void branch is `forecast_grader.unresolvable_reason`
itself, so no void can be chosen to improve a score. `VOID_RULE` is written
into every receipt before the counts.

WHAT IS NOT HERE
================
No regrade (that is CH-06), no write to any ledger, no network: the readiness
question `scripts.campaign_resolution_readiness` asks ("can it be graded now?")
is answered against the local bar panels, because that script copies the whole
ledger and calls `ledger_resolver.resolve_due`, which fetches from a vendor
when the frozen CSV does not cover the window.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional, Sequence

from backend import config as _config

SCHEMA = "forecast_expiry/1"
LEDGER_PREDICTIONS = "predictions"

ACTIVE = "ACTIVE"
EXPIRED_GRADED = "EXPIRED_GRADED"
EXPIRED_UNGRADED = "EXPIRED_UNGRADED"
VOID = "VOID"
UNDATED = "UNDATED"
STATES = (ACTIVE, EXPIRED_GRADED, EXPIRED_UNGRADED, VOID, UNDATED)

RESOLVED = "RESOLVED"
RESOLVABLE_NOW = "RESOLVABLE_NOW"
WAITING_INPUT = "WAITING_INPUT"
VOID_PROPOSED = "VOID"
NOT_IN_LEDGER = "NOT_IN_LIVE_LEDGER"
DISPOSITIONS = (RESOLVED, VOID_PROPOSED, RESOLVABLE_NOW, WAITING_INPUT, NOT_IN_LEDGER)

VOID_RULE = (
    "Stated before counting. A due, ungraded forecast is VOID only when "
    "forecast_grader.unresolvable_reason() returns a code from its closed set "
    "(UNRESOLVABLE_NO_EQUITY_BAR, UNRESOLVABLE_DELISTED, UNRESOLVABLE_NO_BAR_PAST_HORIZON) "
    "against the local bar panel; else RESOLVABLE_NOW when the panel holds horizon+1 "
    "bars from the window start for the ticker (and the benchmark of a beats_benchmark "
    "row) and the resolver's own date has arrived; else WAITING_INPUT naming the input. "
    "The rule reads ticker, benchmark, observable, horizon_days, made_at, resolves_after "
    "and the panel; it never reads probability, outcome or brier. A row already voided "
    "ON the ledger keeps its recorded void_reason. Proposed voids are written to the "
    "side ledger only; no ledger row is changed.")


class ForecastExpiryRefused(RuntimeError):
    """The sweep will not report: an input is missing or the output would land in
    the live data folder."""


# ─────────────────────────────── the session calendar ───────────────────────

def session_calendar(lo: date, hi: date) -> list[date]:
    """XNYS sessions from `lo` to `hi` inclusive (holidays and weekends excluded).

    Raises `market_sessions.SessionCalendarUnavailable` rather than inventing
    weekday arithmetic -- a valid_until on a fabricated session is the defect
    market_sessions exists to remove."""
    from backend.services import market_sessions as MS
    out: list[date] = []
    for y in range(lo.year, hi.year + 1):
        out.extend(d for d in MS.sessions_in_year(y) if lo <= d <= hi)
    return sorted(out)


def _day(v: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _horizon(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    try:
        h = int(v)
    except (TypeError, ValueError):
        return None
    return h if h > 0 and float(v) == h else None


def kind_of(row: dict) -> str:
    """The forecast KIND: what is claimed and over how long."""
    obs = str(row.get("observable") or "?")
    h = _horizon(row.get("horizon_days"))
    return f"{obs}|h{h if h is not None else '?'}"


def family_of(row: dict) -> str:
    spec = str(row.get("specialist") or "?")
    return spec.split(":", 1)[0]


def derive_valid_until(row: dict, sessions: Sequence[date]) -> dict:
    """The last session of the forecast's window, from the row's OWN fields.

    Session calendar first: entry session = the first XNYS session on or after
    the window start (`belief_state.resolution_start_date`, i.e. `made_at`'s date
    except for the standalone-source mechanism), and the window is the entry bar
    plus `horizon_days` sessions -- the same `horizon + 1` bars `resolve_one`
    grades. Fallback: the row's own target date `resolves_after`. Neither -> no
    valid_until and the reason.

    Returns {valid_until, basis, entry_session, why_undated}."""
    from backend.services import belief_state as B
    h = _horizon(row.get("horizon_days"))
    start = None
    start_why = None
    if row.get("made_at"):
        try:
            start = _day(B.resolution_start_date(row))
        except (ValueError, KeyError, TypeError) as exc:
            start_why = f"window start unreadable ({exc})"[:120]
    else:
        start_why = "no made_at"
    if h is not None and start is not None:
        i = bisect.bisect_left(sessions, start)
        if i + h < len(sessions):
            return {"valid_until": sessions[i + h].isoformat(),
                    "basis": "session_calendar", "entry_session": sessions[i].isoformat(),
                    "why_undated": None}
        start_why = f"calendar loaded to {sessions[-1] if sessions else None} ends inside the window"
    ra = _day(row.get("resolves_after"))
    if ra is not None:
        return {"valid_until": ra.isoformat(), "basis": "resolves_after", "entry_session": None,
                "why_undated": None}
    why = []
    if h is None:
        why.append(f"horizon_days {row.get('horizon_days')!r} is not a positive integer")
    if start_why:
        why.append(start_why)
    why.append("no readable resolves_after")
    return {"valid_until": None, "basis": None, "entry_session": None, "why_undated": "; ".join(why)}


def classify(row: dict, *, as_of: date, sessions: Sequence[date]) -> dict:
    """Exactly one of `STATES` for one ledger row, with its valid_until and reason."""
    vu = derive_valid_until(row, sessions)
    base = {"valid_until": vu["valid_until"], "basis": vu["basis"]}
    if row.get("void_reason"):
        return {**base, "state": VOID, "reason": str(row["void_reason"])[:300]}
    if row.get("outcome") is not None:
        why = f"graded {str(row.get('resolved_at') or '')[:10] or 'date not recorded'}"
        if vu["valid_until"] and vu["valid_until"] >= as_of.isoformat():
            why += f"; graded although valid_until {vu['valid_until']} has not passed"
        return {**base, "state": EXPIRED_GRADED, "reason": why}
    if vu["valid_until"] is None:
        return {**base, "state": UNDATED, "reason": f"UNDATED: {vu['why_undated']}"}
    if as_of.isoformat() > vu["valid_until"]:
        return {**base, "state": EXPIRED_UNGRADED,
                "reason": f"window closed {vu['valid_until']} ({vu['basis']}); no outcome"}
    return {**base, "state": ACTIVE, "reason": f"open until {vu['valid_until']} ({vu['basis']})"}


def reason_code(reason: str) -> str:
    """The stable part of a reason, for idempotence (free text carries dates)."""
    s = str(reason or "")
    for sep in (":", ";", " "):
        if sep in s:
            s = s.split(sep, 1)[0]
    return s


# ─────────────────────────────── reading the ledger ─────────────────────────

def line_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw.rstrip(b"\r\n")).hexdigest()


def iter_lines(path: Path) -> Iterator[tuple[int, bytes]]:
    """Stream a JSONL file READ-ONLY, one line at a time (never the whole file)."""
    with open(path, "rb") as fh:
        for n, raw in enumerate(fh, 1):
            if raw.strip():
                yield n, raw


def iter_git_blob_lines(repo: Path, ref: str, path: str) -> Iterator[tuple[int, bytes]]:
    """Stream `git show <ref>:<path>` line by line (a committed copy of a ledger)."""
    proc = subprocess.Popen(["git", "-C", str(repo), "show", f"{ref}:{path}"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    n = 0
    try:
        for raw in proc.stdout:
            n += 1
            if raw.strip():
                yield n, raw
    finally:
        proc.stdout.close()
        err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        rc = proc.wait()
    if rc != 0:
        raise ForecastExpiryRefused(f"git show {ref}:{path} failed (rc {rc}): {err.strip()[:200]}")
    if n == 0:
        raise ForecastExpiryRefused(f"git show {ref}:{path} returned no lines")


def _parse(raw: bytes) -> Optional[dict]:
    try:
        r = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    return r if isinstance(r, dict) else None


# ─────────────────────────────── the local bar panel ────────────────────────

@dataclass
class Panel:
    """What `forecast_grader.unresolvable_reason` needs, from the local parquet(s)."""
    panel_dates: Any                    # DatetimeIndex of every session any symbol has
    last_bar: dict
    by_sym: dict
    source: str
    alt_by_sym: Optional[dict] = None   # llm_portfolio/global_bars.parquet: NOT read by the grader
    alt_source: Optional[str] = None

    def bars_from(self, sym: str, d: str) -> int:
        import pandas as pd
        s = self.by_sym.get(sym)
        if s is None or not d:
            return 0
        return int((s >= pd.Timestamp(d)).sum())

    def alt_bars_from(self, sym: str, d: str) -> int:
        import pandas as pd
        s = (self.alt_by_sym or {}).get(sym)
        if s is None or not d:
            return 0
        return int((s >= pd.Timestamp(d)).sum())

    def last_session(self) -> Optional[str]:
        return str(self.panel_dates[-1])[:10] if len(self.panel_dates) else None


def load_panel(data_root: Path, symbols: Iterable[str]) -> Panel:
    """The same two local panels `forecast_grader` grades from (main + forecast-only),
    read with `columns=` and a symbol filter; the session index from the main
    panel's `date` column alone. Raises ForecastExpiryRefused when the main
    panel is missing -- a disposition without bars would call every row WAITING."""
    import pandas as pd
    main = Path(data_root) / "prices_2025_26" / "bars.parquet"
    extra = Path(data_root) / "prices_2025_26" / "bars_forecast_only.parquet"
    if not main.exists():
        raise ForecastExpiryRefused(f"no bar panel at {main}: cannot say which overdue "
                                    f"forecasts are resolvable")
    want = sorted({str(s) for s in symbols if s})
    dates = pd.read_parquet(main, columns=["date"])["date"]
    panel_dates = pd.DatetimeIndex(sorted(pd.to_datetime(dates).unique()))
    frames = []
    srcs = [f"{main.name} ({len(panel_dates)} sessions to {str(panel_dates[-1])[:10] if len(panel_dates) else None})"]
    if want:
        frames.append(pd.read_parquet(main, columns=["symbol", "date"],
                                      filters=[("symbol", "in", want)]))
        if extra.exists():
            frames.append(pd.read_parquet(extra, columns=["symbol", "date"],
                                          filters=[("symbol", "in", want)]))
            srcs.append(extra.name)
    if frames:
        b = pd.concat(frames, ignore_index=True).drop_duplicates(["symbol", "date"])
        b["date"] = pd.to_datetime(b["date"])
    else:
        b = pd.DataFrame({"symbol": [], "date": pd.to_datetime([])})
    last_bar = b.groupby("symbol")["date"].max().to_dict()
    by_sym = {s: g.sort_values() for s, g in b["date"].groupby(b["symbol"])}
    # The global panel the llm books are marked against. forecast_grader does not
    # read it, so a bar found ONLY here is named as such, never counted as resolvable.
    alt, alt_src = None, None
    g = Path(data_root) / "llm_portfolio" / "global_bars.parquet"
    rest = sorted(set(want) - set(by_sym))
    if g.exists() and rest:
        try:
            gb = pd.read_parquet(g, columns=["symbol", "date"], filters=[("symbol", "in", rest)])
            gb["date"] = pd.to_datetime(gb["date"])
            alt = {s: gg.sort_values() for s, gg in gb["date"].groupby(gb["symbol"])}
            alt_src = f"llm_portfolio/{g.name} ({len(alt)} of {len(rest)} names the grader's panels lack)"
        except Exception as exc:                                   # noqa: BLE001
            alt_src = f"llm_portfolio/{g.name} unreadable ({type(exc).__name__})"
    return Panel(panel_dates, last_bar, by_sym, " + ".join(srcs), alt, alt_src)


def disposition(rec: dict, *, as_of: date, panel: Panel) -> dict:
    """RESOLVED / VOID / RESOLVABLE_NOW / WAITING_INPUT for one forecast. See VOID_RULE.

    Reads no probability, outcome-to-be or brier: the branch order is fixed and
    the void branch is forecast_grader's own rule."""
    from backend.services import belief_state as B
    from backend.services import forecast_grader as FG
    if rec.get("outcome") is not None:
        return {"disposition": RESOLVED, "detail": f"graded on record {str(rec.get('resolved_at') or '')[:10]}"}
    if rec.get("void_reason"):
        return {"disposition": VOID_PROPOSED, "on_record": True, "detail": str(rec["void_reason"])[:300]}
    why = FG.unresolvable_reason(rec, today=as_of, panel_dates=panel.panel_dates,
                                 last_bar=panel.last_bar, bars_from=panel.bars_from)
    if why:
        return {"disposition": VOID_PROPOSED, "on_record": False, "code": why[0],
                "detail": f"{why[0]}: {why[1]}"[:300]}
    h = _horizon(rec.get("horizon_days")) or 0
    try:
        start = B.resolution_start_date(rec)
    except (ValueError, KeyError, TypeError):
        return {"disposition": WAITING_INPUT, "waiting_for": "a readable window start",
                "detail": "resolution_start_date raised"}
    needs = [str(rec.get("ticker") or "").strip()]
    bench = str(rec.get("benchmark") or "").strip()
    if rec.get("observable") == "beats_benchmark" and bench:
        needs.append(bench)
    missing = []
    for sym in needs:
        have = panel.bars_from(sym, start)
        if have < h + 1:
            if sym.startswith("book:"):
                missing.append(f"nav:{sym} (a paper-book id: no bar panel carries it; the grader's "
                               f"panels hold {have} bars)")
                continue
            alt = panel.alt_bars_from(sym, start)
            where = (f"; {alt} bars in llm_portfolio/global_bars.parquet, which forecast_grader does "
                     f"not read" if alt >= h + 1 else "")
            missing.append(f"bars:{sym} ({have} of {h + 1} from {start}; panel to "
                           f"{panel.last_session()}{where})")
    ra = _day(rec.get("resolves_after"))
    if missing:
        return {"disposition": WAITING_INPUT, "waiting_for": "; ".join(missing), "detail": "local panel short"}
    if ra is not None and as_of < ra:
        return {"disposition": WAITING_INPUT, "waiting_for": f"resolver date resolves_after={ra}",
                "detail": "bars exist; the resolver's calendar bound has not arrived"}
    return {"disposition": RESOLVABLE_NOW,
            "inputs": f"{', '.join(needs)}: >= {h + 1} local bars from {start}",
            "detail": ("the attended grader would grade it: python -m scripts.resolve_campaign_ledger "
                       "--commit, or forecast_grader.grade_due on the runtime ledger")}


# ─────────────────────────────── the side ledger ────────────────────────────

def expiry_path(out_dir: Path) -> Path:
    return Path(out_dir) / _config.FORECAST_EXPIRY_SUBDIR / "expiry.jsonl"


def fold_expiry(path: Path) -> dict:
    """{(ledger, forecast_id): last row} of the side ledger (empty if absent)."""
    last: dict = {}
    if not Path(path).exists():
        return last
    for _, raw in iter_lines(path):
        r = _parse(raw)
        if r and r.get("forecast_id") is not None:
            last[(r.get("ledger"), r.get("forecast_id"))] = r
    return last


def _changed(prev: Optional[dict], row: dict) -> bool:
    if prev is None:
        return True
    return (prev.get("state"), prev.get("valid_until"), reason_code(prev.get("reason") or "")) != \
           (row["state"], row["valid_until"], reason_code(row["reason"]))


def _out_must_be_outside(data_root: Path, out_dir: Path) -> None:
    dr = Path(data_root).resolve()
    od = Path(out_dir).resolve()
    guard = dr.parent
    if od == guard or guard in od.parents:
        raise ForecastExpiryRefused(f"--out {od} is inside {guard} (the live data folder's parent); "
                                    f"the sweep writes only outside it")


def snapshot_tree(root: Path) -> dict:
    """{relative path: size} of every file under root (for the before/after check)."""
    out = {}
    root = Path(root)
    for dp, _dn, fns in os.walk(root):
        for f in fns:
            p = Path(dp) / f
            try:
                out[str(p.relative_to(root))] = p.stat().st_size
            except OSError:
                continue
    return out


def tree_diff(before: dict, after: dict) -> dict:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    resized = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    return {"n_before": len(before), "n_after": len(after), "added": added[:50],
            "n_added": len(added), "removed": removed[:50], "n_removed": len(removed),
            "resized": resized[:50], "n_resized": len(resized)}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def sweep(*, data_root: Path, out_dir: Path, as_of: Optional[date] = None,
          campaign_lines: Optional[Callable[[], Iterable[tuple[int, bytes]]]] = None,
          campaign_label: str = "", campaign_as_of: Optional[date] = None,
          now: Optional[datetime] = None, write: bool = True) -> dict:
    """Classify every row of the forecast ledger, append state changes to the side
    ledger, account for the campaign's overdue forecasts one by one, and return
    the summary receipt (also written as `sweep_<stamp>.json`).

    `campaign_lines` yields (lineno, raw) of the campaign ledger copy whose overdue
    forecasts are to be accounted for (default: none). Overdue there uses
    `belief_state.ledger_health`'s strict predicate: `as_of > resolves_after`."""
    data_root, out_dir = Path(data_root), Path(out_dir)
    ledger = data_root / "predictions.jsonl"
    if not ledger.exists():
        raise ForecastExpiryRefused(f"no forecast ledger at {ledger}")
    _out_must_be_outside(data_root, out_dir)
    now = now or _now()
    as_of = as_of or now.date()
    campaign_as_of = campaign_as_of or as_of
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    from backend.services import forecast_ledger as FL
    be = FL.backend_for(ledger)
    if be.kind != "legacy":
        raise ForecastExpiryRefused(f"{ledger} is answered by the monthly streams ({be.reason}); "
                                    f"this sweep reads the single legacy file and would read a frozen copy")
    size_before = ledger.stat().st_size

    # 1. campaign ids first (the copy is streamed once; ~15k ids kept)
    camp: dict = {}
    camp_rows = 0
    if campaign_lines is not None:
        for _, raw in campaign_lines():
            r = _parse(raw)
            camp_rows += 1
            if not r:
                continue
            ra = _day(r.get("resolves_after"))
            if r.get("outcome") is None and not r.get("void_reason") and ra is not None and campaign_as_of > ra:
                camp[str(r.get("prediction_id"))] = {k: r.get(k) for k in (
                    "ticker", "benchmark", "observable", "horizon_days", "made_at", "resolves_after",
                    "specialist", "mechanism_id", "inputs_used")}

    # 2. the calendar: wide enough for every row (made_at back to 2025, +2 years)
    sessions = session_calendar(date(2024, 1, 1), as_of + timedelta(days=800))

    # 3. stream the live ledger once
    prev = fold_expiry(expiry_path(out_dir))
    counts = {s: 0 for s in STATES}
    by_kind: dict = {}
    by_family: dict = {}
    basis_n: dict = {}
    undated: list = []
    owed: dict = {}                 # pid -> minimal rec (EXPIRED_UNGRADED, for disposition)
    camp_live: dict = {}            # pid -> minimal live rec
    new_rows: list = []
    rows_read = unparseable = 0
    graded_brier: list = []
    expired_ungraded_not_due = 0
    seen_ids: set = set()
    dup_ids = 0
    for n, raw in iter_lines(ledger):
        rows_read += 1
        r = _parse(raw)
        if r is None:
            unparseable += 1
            fid, row = f"line:{n}", None
            c = {"state": UNDATED, "valid_until": None, "basis": None,
                 "reason": f"UNDATED: line {n} is not a JSON object"}
            kind = family = "unparseable"
        else:
            row = r
            fid = str(r.get("prediction_id") or f"line:{n}")
            if fid in seen_ids:
                dup_ids += 1
                fid = f"{fid}#line:{n}"
            seen_ids.add(fid)
            c = classify(r, as_of=as_of, sessions=sessions)
            kind, family = kind_of(r), family_of(r)
        st = c["state"]
        counts[st] += 1
        k = by_kind.setdefault(kind, {s: 0 for s in STATES} | {"rows": 0, "derivable": 0})
        k["rows"] += 1
        k[st] += 1
        k["derivable"] += int(c["valid_until"] is not None)
        f = by_family.setdefault(family, {s: 0 for s in STATES} | {"rows": 0})
        f["rows"] += 1
        f[st] += 1
        basis_n[str(c["basis"])] = basis_n.get(str(c["basis"]), 0) + 1
        if st == UNDATED:
            undated.append({"forecast_id": fid, "line": n, "reason": c["reason"]})
        if row is not None and st == EXPIRED_GRADED and row.get("brier") is not None:
            try:
                graded_brier.append(float(row["brier"]))
            except (TypeError, ValueError):
                pass
        if row is not None and st == EXPIRED_UNGRADED:
            owed[fid] = {k2: row.get(k2) for k2 in (
                "prediction_id", "ticker", "benchmark", "observable", "horizon_days", "made_at",
                "resolves_after", "specialist", "mechanism_id", "inputs_used")}
            ra = _day(row.get("resolves_after"))
            if ra is not None and as_of < ra:
                expired_ungraded_not_due += 1
        if row is not None and fid in camp:
            camp_live[fid] = {k2: row.get(k2) for k2 in (
                "prediction_id", "ticker", "benchmark", "observable", "horizon_days", "made_at",
                "resolves_after", "outcome", "resolved_at", "void_reason", "inputs_used", "mechanism_id")}
        out_row = {"schema": SCHEMA, "ledger": LEDGER_PREDICTIONS, "forecast_id": fid, "kind": kind,
                   "family": family, "valid_until": c["valid_until"], "valid_until_basis": c["basis"],
                   "state": st, "reason": c["reason"], "sweep_utc": now.isoformat(timespec="seconds"),
                   "sweep_as_of": as_of.isoformat(), "line": n, "row_sha256": line_sha256(raw)}
        if _changed(prev.get((LEDGER_PREDICTIONS, fid)), out_row):
            new_rows.append(out_row)
    size_after = ledger.stat().st_size

    # 4. dispositions: every owed grade in the live ledger + every campaign overdue id
    syms: set = set()
    for rec in list(owed.values()) + list(camp_live.values()):
        syms.add(str(rec.get("ticker") or ""))
        if rec.get("benchmark"):
            syms.add(str(rec["benchmark"]))
    panel = load_panel(data_root, syms)
    owed_disp: dict = {d: 0 for d in DISPOSITIONS}
    owed_rows = []
    owed_waiting: dict = {}
    for fid, rec in owed.items():
        d = disposition(rec, as_of=as_of, panel=panel)
        owed_disp[d["disposition"]] += 1
        if d["disposition"] == WAITING_INPUT:
            w = str(d.get("waiting_for") or "")
            w = ("resolver_date" if w.startswith("resolver") else
                 "bars_only_in_global_panel" if "global_bars.parquet" in w else w.split(":", 1)[0])
            owed_waiting[w] = owed_waiting.get(w, 0) + 1
        owed_rows.append({"forecast_id": fid, "ticker": rec.get("ticker"), **d})
    camp_disp: dict = {d: 0 for d in DISPOSITIONS}
    camp_on_record_void = 0
    camp_global = 0
    camp_rows_out = []
    waiting_for: dict = {}
    void_codes: dict = {}
    for fid in sorted(camp):
        live = camp_live.get(fid)
        if live is None:
            d = {"disposition": NOT_IN_LEDGER, "detail": "id absent from the live ledger"}
        else:
            d = disposition(live, as_of=as_of, panel=panel)
        camp_disp[d["disposition"]] += 1
        if d["disposition"] == VOID_PROPOSED:
            code = reason_code(d.get("code") or d.get("detail") or "")
            void_codes[code] = void_codes.get(code, 0) + 1
            camp_on_record_void += int(bool(d.get("on_record")))
        if d["disposition"] == WAITING_INPUT:
            w = str(d.get("waiting_for") or "").split(" (")[0]
            waiting_for[w] = waiting_for.get(w, 0) + 1
            camp_global += int("global_bars.parquet" in str(d.get("waiting_for")))
        camp_rows_out.append({"schema": SCHEMA + "/campaign", "forecast_id": fid,
                              "ticker": (live or camp[fid]).get("ticker"),
                              "resolves_after": camp[fid].get("resolves_after"),
                              "sweep_as_of": as_of.isoformat(), **d})

    total = sum(counts.values())
    receipt = {
        "schema": SCHEMA + "/receipt", "generated_utc": now.isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(), "data_root": str(data_root), "ledger": str(ledger),
        "ledger_backend": be.describe(), "ledger_bytes_before": size_before,
        "ledger_bytes_after": size_after,
        "void_rule": VOID_RULE,
        "states_definition": {
            VOID: "row carries void_reason (the ledger's own vocabulary)",
            EXPIRED_GRADED: "row has an outcome (graded archive, shown DEGRADED, never live evidence)",
            UNDATED: "no valid_until derivable from the row's own fields",
            EXPIRED_UNGRADED: "as_of > valid_until and no outcome: a grade is owed",
            ACTIVE: "as_of <= valid_until"},
        "valid_until_rule": ("entry session = first XNYS session on/after belief_state.resolution_start_date; "
                             "valid_until = the session horizon_days later (horizon+1 bars, as resolve_one "
                             "grades); fallback resolves_after; else UNDATED"),
        "reconciliation": {
            LEDGER_PREDICTIONS: {"rows_read": rows_read, **counts, "sum_of_states": total,
                                 "reconciles": total == rows_read,
                                 "unparseable_lines": unparseable, "duplicate_ids": dup_ids}},
        "valid_until_basis_counts": basis_n,
        "by_kind": dict(sorted(by_kind.items())),
        "by_family": dict(sorted(by_family.items())),
        "undated": {"n": len(undated), "rows": undated[:200]},
        "expired_ungraded": {
            "n": counts[EXPIRED_UNGRADED],
            "n_before_resolver_date": expired_ungraded_not_due,
            "dispositions": owed_disp, "waiting_for": owed_waiting},
        "score": {
            "graded_rows_with_brier": len(graded_brier),
            "mean_brier_voids_excluded": (round(sum(graded_brier) / len(graded_brier), 5)
                                          if graded_brier else None),
            "voids_on_record": counts[VOID],
            "note": ("A voided row carries no outcome and no brier, so the score with voids is not "
                     "computable and the score without them is the only one; a proposed void below "
                     "is an ungraded row and moves no score either way.")},
        "bar_panel": {"source": panel.source, "alt_source": panel.alt_source,
                      "last_session": panel.last_session(),
                      "symbols_needed": len(syms), "symbols_found": len(panel.last_bar)},
        "side_ledger": {"path": str(expiry_path(out_dir)), "rows_before": len(prev),
                        "rows_appended": len(new_rows)},
    }
    if campaign_lines is not None:
        receipt["campaign"] = {
            "source": campaign_label, "rows_read": camp_rows,
            "overdue_predicate": "outcome is None, no void_reason, as_of > resolves_after (ledger_health)",
            "overdue_as_of": campaign_as_of.isoformat(),
            "n_overdue": len(camp), "quoted": int(_config.FORECAST_EXPIRY_CAMPAIGN_QUOTED),
            "dispositions": camp_disp,
            "sum_of_dispositions": sum(camp_disp.values()),
            "reconciles": sum(camp_disp.values()) == len(camp),
            "void_on_ledger_record": camp_on_record_void,
            "void_proposed_side_ledger_only": camp_disp[VOID_PROPOSED] - camp_on_record_void,
            "void_codes": void_codes, "waiting_for": waiting_for,
            "waiting_with_bars_only_in_global_panel": camp_global}
    if write:
        sub = Path(out_dir) / _config.FORECAST_EXPIRY_SUBDIR
        sub.mkdir(parents=True, exist_ok=True)
        if new_rows:
            with open(expiry_path(out_dir), "ab") as fh:
                for r in new_rows:
                    fh.write((json.dumps(r, sort_keys=True) + "\n").encode("utf-8"))
        _write_new(sub / f"owed_dispositions_{stamp}.jsonl",
                   "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in owed_rows))
        if campaign_lines is not None:
            _write_new(sub / f"campaign_accounting_{stamp}.jsonl",
                       "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in camp_rows_out))
        receipt["receipt_path"] = str(_write_new(sub / f"sweep_{stamp}.json",
                                                 json.dumps(receipt, indent=1, default=str)))
    return receipt


def _write_new(path: Path, text: str) -> Path:
    """Write a NEW file (a second run in the same second gets a suffix, never an overwrite)."""
    p, n = Path(path), 1
    while p.exists():
        p = path.with_name(f"{path.stem}_{n}{path.suffix}")
        n += 1
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)
    return p


# ─────────────────────────────── evidence labels (report only) ──────────────

def regime_of(spy_rets: Sequence[float], vol_cut: float) -> dict:
    """SPY's compounded return and annualised volatility over a window, and the cut."""
    import math
    xs = [float(x) for x in spy_rets if x == x]
    if len(xs) < 2:
        return {"status": "CANNOT_DETERMINE", "why": f"{len(xs)} SPY period returns"}
    tot = 1.0
    for x in xs:
        tot *= 1.0 + x
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
    vol = sd * math.sqrt(252)
    tag = f"SPY_{'UP' if tot >= 1.0 else 'DOWN'}_{'VOLATILE' if vol > vol_cut else 'CALM'}"
    return {"status": "OK", "tag": tag, "spy_return_pct": round(100 * (tot - 1.0), 2),
            "spy_vol_annual": round(vol, 3), "n_periods": len(xs),
            "note": "period returns between marks; a multi-session period understates daily vol"}


def trailing_series(series: Sequence, spy_sessions: Sequence[str], inception: Optional[str],
                    last_mark: Optional[str], n_sessions: int,
                    full_sessions: Optional[int]) -> tuple[list, Optional[int], Optional[str], bool]:
    """The periods ending inside the last `n_sessions` SPY sessions after inception
    up to last_mark -> (periods, sessions, window start, whole_window).

    A book younger than the window is its own trailing window (whole_window True).
    A multi-session period that ends inside the window but starts before it is
    kept whole (the series has no finer grain), which the receipt says."""
    inc, lm = str(inception or "")[:10], str(last_mark or "")[:10]
    ss = [d for d in spy_sessions if (not inc or d > inc) and (not lm or d <= lm)]
    if len(ss) <= n_sessions:
        return list(series), full_sessions, (ss[0] if ss else None), True
    cut = ss[-n_sessions - 1]
    return [x for x in series if str(x[0])[:10] > cut], n_sessions, ss[-n_sessions], False


def label_stepdown(books: Sequence[dict], *, spy_sessions: Sequence[str], p: dict,
                   n_trailing: int, vol_cut: float) -> list[dict]:
    """For each book (book_dna.book_rows output, with `_series`): the label as built,
    the window it was earned in and its regime, and the label on the trailing
    window through `book_dna.evidence_label` itself. Changes nothing."""
    from backend.services import book_dna as BD
    ladder = list(BD.LABEL_LADDER)
    rows: list[dict] = []
    trail: dict = {}
    for e in books:
        ser = list(e.get("_series") or [])
        tser, tsess, tlo, whole = trailing_series(ser, spy_sessions, e.get("inception"), e.get("last_mark"),
                                                  n_trailing, e.get("sessions_graded"))
        if tser:
            b = s = 1.0
            for _, x, y in tser:
                b *= 1.0 + float(x)
                s *= 1.0 + float(y)
            texcess = round(100 * (b - s), 3)
        else:
            texcess = None
        tsub = BD.subwindows(tser, tsess)
        trail[e["account"]] = (tser, tsess, tlo, texcess, tsub, whole)
    early = {}
    for e in books:
        tser, tsess, tlo, texcess, tsub, _w = trail[e["account"]]
        early[e["account"]] = BD.evidence_label(sessions=tsess, excess_pp=texcess, sub=tsub,
                                                fair_twin_excess_pp=None, replicated_by=None,
                                                p=p)["label"] == "EARLY_EVIDENCE"
    by_rule: dict = {}
    for e in books:
        if e.get("rule") and e.get("category") == "strategy":
            by_rule.setdefault(e["rule"], []).append(e["account"])
    for e in books:
        tser, tsess, tlo, texcess, tsub, whole = trail[e["account"]]
        rep = next((a for a in by_rule.get(e.get("rule"), []) if a != e["account"] and early[a]), None)
        tl = BD.evidence_label(sessions=tsess, excess_pp=texcess, sub=tsub,
                               fair_twin_excess_pp=None, replicated_by=rep, p=p)
        cur = (e.get("evidence") or {}).get("label") or "?"
        cur_rung, t_rung = cur.split("(")[0], tl["label"].split("(")[0]
        step = (ladder.index(t_rung) - ladder.index(cur_rung)
                if cur_rung in ladder and t_rung in ladder else None)
        ser = list(e.get("_series") or [])
        rows.append({
            "account": e["account"], "family": e.get("family"), "category": e.get("category"),
            "label": cur, "label_why": (e.get("evidence") or {}).get("why"),
            "earned_window": {"from": e.get("inception"), "to": e.get("last_mark"),
                              "sessions": e.get("sessions_graded"), "excess_pp": e.get("excess_pp")},
            "earned_regime": regime_of([y for _, _, y in ser], vol_cut),
            "trailing_window": {"from": tlo, "to": e.get("last_mark"), "sessions": tsess,
                                "n_periods": len(tser), "excess_pp": texcess,
                                "whole_window": whole,
                                "subwindows": tsub, "fair_twin": "not recomputed on the trailing window"},
            "trailing_regime": regime_of([y for _, _, y in tser], vol_cut),
            "trailing_label": tl["label"], "trailing_why": tl["why"],
            "rung_change": step, "would_step_down": bool(step is not None and step < 0)})
    return rows
