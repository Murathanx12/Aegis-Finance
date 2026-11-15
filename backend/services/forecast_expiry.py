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
* ``GRADE_OWED``        -- the GRADER's own due rule holds (`forecast_grader.bucket_of`:
                           today >= `resolves_after`), no outcome, no void. This is the
                           only state that says a grade is owed;
* ``UNDATED``           -- no `valid_until` can be derived from the row (named, counted,
                           never silently ACTIVE). A non-US ticker that is not yet due is
                           here with basis `foreign_calendar_unverified`: its window runs
                           on its own exchange's sessions, which this module does not hold;
* ``WINDOW_CLOSED_NOT_DUE`` -- the session window closed (`as_of > valid_until`) but the
                           resolver's bound `resolves_after` is still in the future: no
                           longer a live claim, and nothing is owed yet;
* ``ACTIVE``            -- the window is still open.

Each ledger's rows read = the six counts, printed as a reconciliation. The receipt
also carries a bridge from "rows without resolved_at past resolves_after" (which
includes voids) to GRADE_OWED, term by term.

A STATE NEVER MOVES BACKWARDS SILENTLY
======================================
ACTIVE -> WINDOW_CLOSED_NOT_DUE -> GRADE_OWED -> EXPIRED_GRADED / VOID is the only
direction a frozen row can travel. A sweep that would record the reverse (an outcome
or a void removed, or an earlier `--as-of`) raises `ForecastExpiryRegress` naming the
ids and appends nothing to the side ledger, unless `allow_regress` is passed; then
the rows are appended flagged `regress`. A row whose bytes changed while its state
did not is appended too (`changes: ["row_sha256"]`).

READ-ONLY OVER THE LEDGERS
==========================
The forecast rows are frozen (canon: append-only, no mutation of seeded
histories). Nothing here opens a ledger for writing. The sweep writes only its
own SIDE ledger, ``<out>/forecast_expiry/expiry.jsonl``, append-only: a second
sweep appends a row only when an id's (state, valid_until, reason code, row sha256) changed.
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

SCHEMA = "forecast_expiry/2"
LEDGER_PREDICTIONS = "predictions"

ACTIVE = "ACTIVE"
EXPIRED_GRADED = "EXPIRED_GRADED"
WINDOW_CLOSED_NOT_DUE = "WINDOW_CLOSED_NOT_DUE"
GRADE_OWED = "GRADE_OWED"
VOID = "VOID"
UNDATED = "UNDATED"
STATES = (ACTIVE, WINDOW_CLOSED_NOT_DUE, GRADE_OWED, EXPIRED_GRADED, VOID, UNDATED)

#: How far along its one-way life a state is. A move to a LOWER rank is a regress.
#: UNDATED ranks with ACTIVE (nothing is known to have closed); a grade and a void
#: are both terminal, so a move between them is not a regress.
STATE_RANK = {ACTIVE: 0, UNDATED: 0, WINDOW_CLOSED_NOT_DUE: 1, GRADE_OWED: 2,
              EXPIRED_GRADED: 3, VOID: 3}

BASIS_FOREIGN = "foreign_calendar_unverified"
#: The one bucket of `forecast_grader.bucket_of` that means "the due date has not arrived".
GRADER_NOT_YET_DUE = "not_yet_due"

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


#: Said wherever a FOREIGN name's bars are found only in the global panel (a US-listed
#: name found only there shares the US calendar and gets no such caveat): having
#: enough bars is not the same as having a gradeable window.
GLOBAL_BARS_WINDOW_CAVEAT = (
    "Those bars are on the ticker's own exchange calendar: its entry bar and its window's "
    "last bar can fall on different dates from a US benchmark's, so a beats_benchmark grade "
    "built from them would compare two different windows (window mismatch)")

BRIER_POPULATION = (
    "every row of this ledger that has an outcome and a brier: the WHOLE ledger, grades made "
    "before the erratum included. It is not the population CH-12 scored, so this figure is "
    "not comparable with CH-12's")


class ForecastExpiryRefused(RuntimeError):
    """The sweep will not report: an input is missing or the output would land in
    the live data folder."""


class ForecastExpiryRegress(ForecastExpiryRefused):
    """One or more forecasts would move BACKWARDS (e.g. graded -> ungraded). Nothing
    was appended to the side ledger. `moves` lists every one."""

    def __init__(self, message: str, moves: list):
        super().__init__(message)
        self.moves = moves


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


def is_foreign_ticker(ticker: Any) -> bool:
    """A ticker carrying an exchange suffix (`005930.KS`, `7011.T`): the suffix
    convention `opportunities.split_suffix` already owns. `DX-Y.NYB` is the grader's
    non-equity notation, not a foreign listing."""
    from backend.services import forecast_grader as FG
    from backend.services import opportunities as O
    t = str(ticker or "").strip().upper()
    return bool(t) and t not in FG.NON_EQUITY_EXACT and O.is_foreign(t)


def derive_valid_until(row: dict, sessions: Sequence[date]) -> dict:
    """The last session of the forecast's window, from the row's OWN fields.

    Session calendar first: entry session = the first XNYS session on or after
    the window start (`belief_state.resolution_start_date`, i.e. `made_at`'s date
    except for the standalone-source mechanism), and the window is the entry bar
    plus `horizon_days` sessions -- the same `horizon + 1` bars `resolve_one`
    grades. Fallback: the row's own target date `resolves_after`. Neither -> no
    valid_until and the reason.

    A non-US ticker gets no date at all: basis `foreign_calendar_unverified`.

    Returns {valid_until, basis, entry_session, why_undated}."""
    from backend.services import belief_state as B
    if is_foreign_ticker(row.get("ticker")):
        # The resolver grades a foreign name over ITS OWN bars (belief_state.resolve_one),
        # so the window's last session is a date on that exchange's calendar. An XNYS
        # count gives a different, wrong date; no date is better than that one.
        return {"valid_until": None, "basis": BASIS_FOREIGN, "entry_session": None,
                "why_undated": (f"{BASIS_FOREIGN}: {row.get('ticker')} trades on its own exchange's "
                                f"sessions, which are not held here; an XNYS date would be wrong")}
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


def grader_bucket(row: dict, as_of: date) -> str:
    """`forecast_grader.bucket_of` for this row: the grader's OWN due rule, called,
    not copied (today >= resolves_after, no outcome, no void)."""
    from backend.services import forecast_grader as FG
    return FG.bucket_of(row, today=as_of)


def classify(row: dict, *, as_of: date, sessions: Sequence[date]) -> dict:
    """Exactly one of `STATES` for one ledger row, with its valid_until and reason.

    Order: VOID, EXPIRED_GRADED, then GRADE_OWED by the grader's rule (which needs
    no valid_until), then UNDATED, WINDOW_CLOSED_NOT_DUE, ACTIVE."""
    vu = derive_valid_until(row, sessions)
    base = {"valid_until": vu["valid_until"], "basis": vu["basis"]}
    if row.get("void_reason"):
        return {**base, "state": VOID, "reason": str(row["void_reason"])[:300]}
    if row.get("outcome") is not None:
        why = f"graded {str(row.get('resolved_at') or '')[:10] or 'date not recorded'}"
        if vu["valid_until"] and vu["valid_until"] >= as_of.isoformat():
            why += f"; graded although valid_until {vu['valid_until']} has not passed"
        return {**base, "state": EXPIRED_GRADED, "reason": why}
    ra = _day(row.get("resolves_after"))
    if ra is not None:
        bucket = grader_bucket(row, as_of)
        if bucket != GRADER_NOT_YET_DUE:
            return {**base, "state": GRADE_OWED, "grader_bucket": bucket,
                    "reason": (f"due {ra} by the grader's rule (as_of >= resolves_after); no outcome, "
                               f"no void; grader bucket {bucket}")}
    if vu["valid_until"] is None:
        return {**base, "state": UNDATED, "reason": f"UNDATED: {vu['why_undated']}"}
    if as_of.isoformat() > vu["valid_until"]:
        if ra is None:
            # The grader does not call an unreadable date "not yet due" either: it is a finding.
            return {**base, "state": GRADE_OWED, "grader_bucket": grader_bucket(row, as_of),
                    "reason": (f"due: window closed {vu['valid_until']} ({vu['basis']}) and resolves_after "
                               f"is unreadable, which the grader buckets as a finding, not as not-yet-due")}
        return {**base, "state": WINDOW_CLOSED_NOT_DUE,
                "reason": (f"window closed {vu['valid_until']} ({vu['basis']}); resolver date "
                           f"{ra} not reached, nothing owed yet")}
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

    def sessions_from(self, d: str) -> int:
        """Sessions the PANEL holds on or after `d` (any symbol)."""
        import pandas as pd
        if not d or not len(self.panel_dates):
            return 0
        return int((self.panel_dates >= pd.Timestamp(d)).sum())

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
            if where and is_foreign_ticker(sym):
                where += f". {GLOBAL_BARS_WINDOW_CAVEAT}"
            gap = ""
            if have and not is_foreign_ticker(sym):
                held = panel.sessions_from(start)
                gap = (f"; the panel holds {held} sessions from {start}, so {max(held - have, 0)} "
                       f"are missing for this ticker")
            missing.append(f"bars:{sym} ({have} of the {h + 1} needed from {start}{gap}; panel to "
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


def read_expiry(path: Path) -> tuple[dict, Optional[str]]:
    """({(ledger, forecast_id): last row}, newest `sweep_as_of` on ANY row) of the
    side ledger; ({}, None) if absent."""
    last: dict = {}
    newest: Optional[str] = None
    if not Path(path).exists():
        return last, newest
    for _, raw in iter_lines(path):
        r = _parse(raw)
        if r and r.get("forecast_id") is not None:
            last[(r.get("ledger"), r.get("forecast_id"))] = r
            a = str(r.get("sweep_as_of") or "")[:10]
            if a and (newest is None or a > newest):
                newest = a
    return last, newest


def fold_expiry(path: Path) -> dict:
    """{(ledger, forecast_id): last row} of the side ledger (empty if absent)."""
    return read_expiry(path)[0]


def changes_since(prev: Optional[dict], row: dict) -> list[str]:
    """Which recorded facts differ from the id's last side-ledger row ([] = nothing
    to append). `row_sha256` alone is a change: the frozen line's bytes moved."""
    if prev is None:
        return ["new"]
    out = []
    if prev.get("schema") != row["schema"]:
        out.append("schema")
    if prev.get("state") != row["state"]:
        out.append("state")
    if prev.get("valid_until") != row["valid_until"]:
        out.append("valid_until")
    if reason_code(prev.get("reason") or "") != reason_code(row["reason"]):
        out.append("reason")
    if prev.get("row_sha256") and prev["row_sha256"] != row["row_sha256"]:
        out.append("row_sha256")
    return out


def is_regress(prev: Optional[dict], row: dict) -> bool:
    """True when the state moved to a lower `STATE_RANK` than the id's last row.
    A row written under another schema is a restatement (the states were defined
    differently), never a regress."""
    if prev is None or prev.get("schema") != row["schema"]:
        return False
    a, b = STATE_RANK.get(prev.get("state")), STATE_RANK.get(row["state"])
    return a is not None and b is not None and b < a


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
            "resized": resized[:50], "n_resized": len(resized),
            "all_added": added, "all_removed": removed, "all_resized": resized}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def sweep(*, data_root: Path, out_dir: Path, as_of: Optional[date] = None,
          campaign_lines: Optional[Callable[[], Iterable[tuple[int, bytes]]]] = None,
          campaign_label: str = "", campaign_as_of: Optional[date] = None,
          now: Optional[datetime] = None, write: bool = True,
          allow_regress: bool = False) -> dict:
    """Classify every row of the forecast ledger, append state changes to the side
    ledger, account for the campaign's overdue forecasts one by one, and return
    the summary receipt (also written as `sweep_<stamp>.json`).

    `campaign_lines` yields (lineno, raw) of the campaign ledger copy whose overdue
    forecasts are to be accounted for (default: none). Overdue there uses
    `belief_state.ledger_health`'s strict predicate: `as_of > resolves_after`.

    Refuses (`ForecastExpiryRefused`) an `as_of` earlier than the newest entry of the
    side ledger under `out_dir`, and (`ForecastExpiryRegress`, with every id) a sweep
    in which a forecast would move to an earlier state -- both unless `allow_regress`."""
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
    prev, newest_as_of = read_expiry(expiry_path(out_dir))
    if newest_as_of and as_of.isoformat() < newest_as_of and not allow_regress:
        raise ForecastExpiryRefused(
            f"--as-of {as_of} is earlier than the side ledger's newest entry ({newest_as_of}) in "
            f"{expiry_path(out_dir)}: sweeping backwards would record states moving backwards. "
            f"Use a new --out folder, or pass --allow-regress to append them flagged")
    counts = {s: 0 for s in STATES}
    by_kind: dict = {}
    by_family: dict = {}
    basis_n: dict = {}
    undated: list = []
    foreign_by_state = {s: 0 for s in STATES}
    owed: dict = {}                 # pid -> minimal rec (GRADE_OWED, for disposition)
    closed: dict = {}               # pid -> minimal rec (WINDOW_CLOSED_NOT_DUE, for disposition)
    camp_live: dict = {}            # pid -> minimal live rec
    new_rows: list = []
    regress: list = []
    sha_only = restated = 0
    rows_read = unparseable = 0
    graded_brier: list = []
    # the bridge from the loose count ("no resolved_at, past resolves_after") to GRADE_OWED
    br = {"start": 0, "void": 0, "graded": 0, "past": 0, "today": 0, "stamped": 0, "unreadable": 0}
    owed_buckets: dict = {}
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
        if c["basis"] == BASIS_FOREIGN:
            foreign_by_state[st] += 1
        if row is not None:
            ra = _day(row.get("resolves_after"))
            loose = not row.get("resolved_at") and ra is not None and as_of > ra
            if loose:
                br["start"] += 1
                if row.get("void_reason"):
                    br["void"] += 1
                elif row.get("outcome") is not None:
                    br["graded"] += 1
            if st == GRADE_OWED:
                br["unreadable" if ra is None else "today" if ra == as_of
                   else "past" if loose else "stamped"] += 1
                b = str(c.get("grader_bucket"))
                owed_buckets[b] = owed_buckets.get(b, 0) + 1
        if row is not None and st in (GRADE_OWED, WINDOW_CLOSED_NOT_DUE):
            (owed if st == GRADE_OWED else closed)[fid] = {k2: row.get(k2) for k2 in (
                "prediction_id", "ticker", "benchmark", "observable", "horizon_days", "made_at",
                "resolves_after", "specialist", "mechanism_id", "inputs_used")}
        if row is not None and fid in camp:
            camp_live[fid] = {k2: row.get(k2) for k2 in (
                "prediction_id", "ticker", "benchmark", "observable", "horizon_days", "made_at",
                "resolves_after", "outcome", "resolved_at", "void_reason", "inputs_used", "mechanism_id")}
        out_row = {"schema": SCHEMA, "ledger": LEDGER_PREDICTIONS, "forecast_id": fid, "kind": kind,
                   "family": family, "valid_until": c["valid_until"], "valid_until_basis": c["basis"],
                   "state": st, "reason": c["reason"], "sweep_utc": now.isoformat(timespec="seconds"),
                   "sweep_as_of": as_of.isoformat(), "line": n, "row_sha256": line_sha256(raw)}
        was = prev.get((LEDGER_PREDICTIONS, fid))
        ch = changes_since(was, out_row)
        if ch:
            out_row["changes"] = ch
            if was is not None:
                out_row["prev_state"] = was.get("state")
                if "row_sha256" in ch:
                    out_row["prev_row_sha256"] = was.get("row_sha256")
                sha_only += int(ch == ["row_sha256"])
                restated += int("schema" in ch)
            if is_regress(was, out_row):
                out_row["regress"] = True
                regress.append({"forecast_id": fid, "line": n, "from": was.get("state"), "to": st,
                                "last_recorded_as_of": was.get("sweep_as_of"),
                                "row_sha256_changed": "row_sha256" in ch})
            new_rows.append(out_row)
    size_after = ledger.stat().st_size
    absent = sum(1 for (led, fid) in prev if led == LEDGER_PREDICTIONS and fid not in seen_ids
                 and not str(fid).startswith("line:"))
    if regress and not allow_regress:
        ids = [m["forecast_id"] for m in regress]
        path = None
        if write:
            sub = Path(out_dir) / _config.FORECAST_EXPIRY_SUBDIR
            sub.mkdir(parents=True, exist_ok=True)
            path = _write_new(sub / f"regress_refused_{stamp}.json", json.dumps(
                {"schema": SCHEMA + "/regress_refused", "generated_utc": now.isoformat(timespec="seconds"),
                 "as_of": as_of.isoformat(), "ledger": str(ledger), "n": len(regress), "moves": regress,
                 "side_ledger_rows_appended": 0}, indent=1, default=str))
        raise ForecastExpiryRegress(
            f"{len(regress)} forecast(s) would move to an EARLIER state than the side ledger records "
            f"(an outcome or a void was removed from the ledger row, or the clock went back); nothing "
            f"was appended. Full list: {path or ids}. Pass --allow-regress to append them flagged",
            regress)

    def _dispose(recs: dict, state: str) -> tuple[dict, dict, list]:
        disp: dict = {d: 0 for d in DISPOSITIONS}
        waiting: dict = {}
        out: list = []
        for fid, rec in recs.items():
            d = disposition(rec, as_of=as_of, panel=panel)
            disp[d["disposition"]] += 1
            if d["disposition"] == WAITING_INPUT:
                w = str(d.get("waiting_for") or "")
                w = ("resolver_date" if w.startswith("resolver") else
                     "bars_only_in_global_panel" if "global_bars.parquet" in w else w.split(":", 1)[0])
                waiting[w] = waiting.get(w, 0) + 1
            out.append({"forecast_id": fid, "state": state, "ticker": rec.get("ticker"), **d})
        return disp, waiting, out

    # 4. dispositions: every owed grade in the live ledger + every campaign overdue id
    syms: set = set()
    for rec in list(owed.values()) + list(closed.values()) + list(camp_live.values()):
        syms.add(str(rec.get("ticker") or ""))
        if rec.get("benchmark"):
            syms.add(str(rec["benchmark"]))
    panel = load_panel(data_root, syms)
    owed_disp, owed_waiting, owed_rows = _dispose(owed, GRADE_OWED)
    closed_disp, closed_waiting, closed_rows = _dispose(closed, WINDOW_CLOSED_NOT_DUE)
    net_past = br["start"] - br["void"] - br["graded"]
    bridge_total = net_past + br["today"] + br["stamped"] + br["unreadable"]
    bridge = {
        "rows_without_resolved_at_past_resolves_after": br["start"],
        "minus_voided_on_record": br["void"],
        "minus_graded_without_a_resolved_at_stamp": br["graded"],
        "equals_ungraded_unvoided_past_resolves_after": net_past,
        "plus_due_today_resolves_after_equals_as_of": br["today"],
        "plus_resolved_at_stamp_but_no_outcome": br["stamped"],
        "plus_resolves_after_unreadable_and_window_closed": br["unreadable"],
        "equals": bridge_total, GRADE_OWED: counts[GRADE_OWED],
        "reconciles": bridge_total == counts[GRADE_OWED] and net_past == br["past"],
        "why": ("the loose count uses a strict date (as_of > resolves_after) and counts voided rows, "
                "which carry no resolved_at; the grader's rule is as_of >= resolves_after with no "
                "outcome and no void")}
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
            GRADE_OWED: ("forecast_grader.bucket_of's due rule: as_of >= resolves_after, no outcome, "
                         "no void (also: resolves_after unreadable and the window closed). The only "
                         "state in which a grade is owed"),
            UNDATED: ("no valid_until derivable from the row's own fields; includes a non-US ticker "
                      f"not yet due (basis {BASIS_FOREIGN})"),
            WINDOW_CLOSED_NOT_DUE: ("as_of > valid_until, no outcome, no void, and resolves_after is "
                                    "still in the future: not a live claim, nothing owed yet"),
            ACTIVE: "as_of <= valid_until and not due"},
        "valid_until_rule": ("entry session = first XNYS session on/after belief_state.resolution_start_date; "
                             "valid_until = the session horizon_days later (horizon+1 bars, as resolve_one "
                             "grades); fallback resolves_after; else UNDATED. A ticker with an exchange "
                             f"suffix gets no date: basis {BASIS_FOREIGN} (its window runs on its own "
                             "exchange's sessions)"),
        "reconciliation": {
            LEDGER_PREDICTIONS: {"rows_read": rows_read, **counts, "sum_of_states": total,
                                 "reconciles": total == rows_read,
                                 "unparseable_lines": unparseable, "duplicate_ids": dup_ids}},
        "valid_until_basis_counts": basis_n,
        "by_kind": dict(sorted(by_kind.items())),
        "by_family": dict(sorted(by_family.items())),
        "undated": {"n": len(undated), "n_foreign_calendar_unverified": foreign_by_state[UNDATED],
                    "rows": undated[:200]},
        "foreign_calendar_unverified": {
            "n": sum(foreign_by_state.values()), "by_state": foreign_by_state,
            "note": ("no valid_until is given to these rows. One that is due is GRADE_OWED by the "
                     "grader's date rule like any other; one that is not yet due is UNDATED, because "
                     "whether its window has closed cannot be said without its exchange's calendar")},
        "grade_owed": {
            "n": counts[GRADE_OWED], "bridge": bridge, "grader_buckets": owed_buckets,
            "dispositions": owed_disp, "waiting_for": owed_waiting},
        "window_closed_not_due": {
            "n": counts[WINDOW_CLOSED_NOT_DUE],
            "dispositions": closed_disp, "waiting_for": closed_waiting},
        "score": {
            "population": BRIER_POPULATION,
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
                        "newest_as_of_before": newest_as_of,
                        "rows_appended": len(new_rows),
                        "appended_row_sha256_changed_only": sha_only,
                        "appended_restated_from_another_schema": restated,
                        "allow_regress": bool(allow_regress),
                        "regress_n": len(regress), "regress": regress[:200],
                        "ids_recorded_before_but_absent_from_ledger": absent},
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
                   "".join(json.dumps(r, sort_keys=True, default=str) + "\n"
                           for r in owed_rows + closed_rows))
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
        # A book younger than the window: the trailing window IS the earned window, so the
        # fair twin computed on it still applies. Otherwise the twin is not recomputed here.
        fair = (e.get("fair_twin") or {}).get("excess_over_twin_pp") if whole else None
        tl = BD.evidence_label(sessions=tsess, excess_pp=texcess, sub=tsub,
                               fair_twin_excess_pp=fair, replicated_by=rep, p=p)
        cur = (e.get("evidence") or {}).get("label") or "?"
        cur_rung, t_rung = cur.split("(")[0], tl["label"].split("(")[0]
        step = (ladder.index(t_rung) - ladder.index(cur_rung)
                if cur_rung in ladder and t_rung in ladder else None)
        ser = list(e.get("_series") or [])
        verdict = "NO" if step is None or step >= 0 else "YES"
        why_v = None
        if (verdict == "YES" and cur_rung == "REPLICATED" and t_rung == "EARLY_EVIDENCE"
                and "fair twin" in str((e.get("evidence") or {}).get("why") or "")):
            verdict, why_v = "CANNOT_DETERMINE", ("REPLICATED was earned over the fair twin, which this "
                                                  "report does not recompute on the trailing window")
        rows.append({
            "account": e["account"], "family": e.get("family"), "category": e.get("category"),
            "label": cur, "label_why": (e.get("evidence") or {}).get("why"),
            "earned_window": {"from": e.get("inception"), "to": e.get("last_mark"),
                              "sessions": e.get("sessions_graded"), "excess_pp": e.get("excess_pp")},
            "earned_regime": regime_of([y for _, _, y in ser], vol_cut),
            "trailing_window": {"from": tlo, "to": e.get("last_mark"), "sessions": tsess,
                                "n_periods": len(tser), "excess_pp": texcess,
                                "whole_window": whole,
                                "subwindows": tsub,
                                "fair_twin": ("the book's own (trailing window = earned window)" if whole
                                              else "not recomputed on the trailing window")},
            "trailing_regime": regime_of([y for _, _, y in tser], vol_cut),
            "trailing_label": tl["label"], "trailing_why": tl["why"],
            "rung_change": step, "step_down": verdict, "step_down_why": why_v,
            "would_step_down": verdict == "YES"})
    return rows


def stepdown_coverage(rows: Sequence[dict], *, n_trailing: int) -> dict:
    """How many books the trailing-window step-down result really TESTS.

    A book younger than the window is its own trailing window (`whole_window`):
    its trailing label is its earned label by construction, so it cannot step down
    and says nothing about whether labels age. Only a book that holds a label above
    OBSERVED and is older than the window is a test."""
    from backend.services import book_dna as BD
    ladder = list(BD.LABEL_LADDER)

    def rung(r: dict) -> Optional[int]:
        k = str(r.get("label") or "").split("(")[0]
        return ladder.index(k) if k in ladder else None

    floor = ladder.index("OBSERVED") if "OBSERVED" in ladder else 0
    whole = [r for r in rows if (r.get("trailing_window") or {}).get("whole_window")]
    above = [r for r in rows if rung(r) is not None and rung(r) > floor]
    above_whole = [r for r in above if (r.get("trailing_window") or {}).get("whole_window")]
    tested = [r for r in above if not (r.get("trailing_window") or {}).get("whole_window")]
    not_strategy = [r for r in above if r.get("category") != "strategy"]
    return {
        "trailing_sessions": int(n_trailing), "n_books": len(rows),
        "n_whole_window": len(whole),
        "n_above_observed": len(above),
        "n_above_observed_whole_window": len(above_whole),
        "n_really_tested": len(tested),
        "really_tested": sorted(str(r.get("account")) for r in tested),
        "n_above_observed_not_a_strategy_book": len(not_strategy),
        "statement": (
            f"{len(whole)} of {len(rows)} books are younger than the {int(n_trailing)}-session trailing "
            f"window (whole-window: trailing label = earned label by construction, a step-down is "
            f"impossible). Of the {len(above)} books holding a label above OBSERVED, {len(above_whole)} "
            f"are whole-window, so the step-down result tests {len(tested)} book(s); "
            f"{len(not_strategy)} of the {len(above)} are twins or controls, not strategy books.")}
