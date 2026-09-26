"""GRADE THE FORECASTS — the daily caller the ledger resolver never had.

WHAT WAS WRONG
==============
MEASURED 2026-09-20 on the live ledger
(`backend/data/optimus/predictions.jsonl`, 24,839 records): **every single one
carried `resolved_at: null` and `outcome: null`.** 17,614 of them were past
their `resolves_after` date — the oldest since 2026-08-11 — and 7,219 were not
yet due. `lab_decision_vs_reality` reported this faithfully every hour and
re-graded nothing, exactly as its docstring says it must; the problem was that
the graders it aggregates over were never RUN. No step of the daily pass graded
anything, so the whole calibration half of the programme was accruing forecasts
and resolving none of them.

`belief_state.resolve_one/resolve_all` and `ledger_resolver.resolve_due` are a
complete, tested resolution machine. Its only production caller is
`portfolio_intelligence.scheduler`, a background thread inside a server process
that does not run on this machine. So this module is the caller, and it is
called from `scripts/daily_pass.py` after `book_cadence`.

NOTHING HERE GRADES ANYTHING ITSELF
===================================
Not one line of return arithmetic lives in this file. `resolve_due` does the
grading, `belief_state.resolve_one` does the per-record maths, and both keep
every guard they already carry: the evidence-population refusal, the campaign
quarantine by content hash, the horizon-window check that refuses to grade a
truncated series, and the whole-file rewrite that is the ledger's own writing
convention. A second implementation of "did the stock beat the benchmark" would
be a second answer to a question that already has one.

What this module adds is exactly three things:

1. **A LOCAL price panel.** `ledger_resolver`'s default fetch is yfinance over
   several hundred tickers. A step inside the daily pass must not depend on a
   vendor being up, so the panel is built from
   `paper_books.load_bars()` — the same local daily bars the paper books are
   marked against and the agency proposes against. The source is DERIVED from
   the record (its `ticker`, and its `benchmark` when the observable needs one)
   and the panel is named on the receipt with its first and last bar date.
2. **A NAMED reason per record that did not grade**, counted per mechanism.
3. **A receipt** at
   `night_factory_<date>/grade_forecasts_<date>.json`.

`graded_by` IS ON THE RECEIPT, NOT ON THE ROW
=============================================
The task this module was built for asked for `resolved_at`, `outcome`,
`realised_return` and `graded_by` on each graded record. The first three are
the ledger's own convention and `belief_state.resolve_one` already writes them
— `resolved_at`, `outcome`, `brier`, `calibration_bucket`, and
`resolution_detail["realised_return"]`. There is no `graded_by` field in the
schema, and adding one would be a schema change across 24,839 records to carry
a string that is identical on every row of a run. It is on the receipt instead,
as `graded_by`, which is where a fact about the RUN belongs.

EVERY MECHANISM IS ON THE RECEIPT, INCLUDING AT ZERO
====================================================
A group that vanishes is a group nobody notices is missing. The mechanism list
is the union of `lab_decision_vs_reality.DECLARED_MECHANISMS` and every
mechanism the ledger actually carries, so a declared mechanism that has written
nothing is a visible row of zeros rather than an absence.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: This step places no order, arms no lane and asks no model anything. It reads
#: a ledger and a parquet of daily bars and writes outcomes onto records whose
#: windows have closed.
LICENCE = "PRODUCT_EXPERIMENT"

#: The CLOSED set of buckets every due record finishes in. Closed, because the
#: whole failure this module exists to fix was a population of records sitting
#: in no bucket at all: 17,614 of them, for six weeks, while an hourly roll-up
#: reported the fact and nothing acted on it.
#:
#: `graded` is what the RESOLVER wrote, read back off the ledger — never what
#: this module predicted would happen. The rest are the reasons a due record is
#: still ungraded after the resolver ran.
BUCKETS: tuple[str, ...] = (
    "graded",
    #: the record cannot be graded by any grader: a field the observable needs
    #: is absent (no ticker, no threshold, no benchmark).
    "RECORD_LACKS_TARGET",
    #: the record's `observable` is not one `belief_state.Observable` knows, so
    #: no grader in this repository can resolve it.
    "MECHANISM_HAS_NO_GRADER",
    #: the local bar panel cannot cover this record's window: the ticker (or its
    #: benchmark) has no column, or has fewer than `horizon_days + 1` bars from
    #: `made_at`. The record stays due and is graded on a later day.
    "NO_BAR_FOR_RESOLUTION_DATE",
    #: deliberately excluded from grading by `evidence_population`'s quarantine.
    #: NOT a fault: an attended disposition is owed, and counting it beside a
    #: price gap would read as a resolver bug.
    "QUARANTINED",
    #: voided before this run (a malformed threshold, say). Already terminal.
    "VOID",
    #: resolution date has not passed. The only bucket that is not a finding.
    "not_yet_due",
)

#: The buckets that mean "this record did not grade and here is why". Used by
#: the receipt to compute one headline number instead of making the reader add
#: six up.
REFUSAL_BUCKETS: tuple[str, ...] = (
    "RECORD_LACKS_TARGET", "MECHANISM_HAS_NO_GRADER",
    "NO_BAR_FOR_RESOLUTION_DATE", "QUARANTINED", "VOID",
)

#: Which record fields each observable needs before any grader can touch it.
#: Derived from `belief_state.resolve_one`'s own branches rather than restated
#: from memory: `abs_move_exceeds` and `drawdown_exceeds` read `threshold`,
#: `beats_benchmark` reads `benchmark`, `return_sign` needs neither.
_OBSERVABLE_REQUIRES: dict[str, tuple[str, ...]] = {
    "return_sign": (),
    "beats_benchmark": ("benchmark",),
    "abs_move_exceeds": ("threshold",),
    "drawdown_exceeds": ("threshold",),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_date() -> str:
    """The night folder this receipt belongs to. `NIGHT_RUN_DATE`, else TODAY.

    Never a literal: `night_factory.py` carried a hard-coded `2026-09-08` for
    five days and filed two real receipts five days in the past.
    """
    return os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")


def out_dir() -> Path:
    from scripts import night_factory_jobs as J
    return J._out()


def receipt_path(day: str) -> Path:
    return out_dir() / f"grade_forecasts_{day}.json"


def mechanism_of(rec: dict) -> str:
    """Which mechanism wrote this forecast.

    `mechanism_id` is the newer field (11 records carry it) and `specialist` is
    what the swarm wrote (24,839 do). Reading only the new one would report a
    ledger of 24,839 records as one mechanism of 11.
    """
    return str(rec.get("mechanism_id") or rec.get("specialist")
               or "UNATTRIBUTED")


# ===========================================================================
# THE LOCAL PRICE PANEL
# ===========================================================================


def bars_source() -> dict:
    """WHERE the prices come from, named and dated — or why they do not.

    On the receipt rather than in a comment: a grading run whose panel ended
    four days early grades fewer records for a reason nobody can see unless the
    last bar date is printed beside the refusal counts.
    """
    try:
        from backend.services import paper_books as PB
        path = PB._bars_path()
        bars = PB.load_bars()
    except Exception as exc:                                       # noqa: BLE001
        return {"available": False, "path": None,
                "reason": (f"CANNOT DETERMINE: the local daily bars could not be "
                           f"loaded ({type(exc).__name__}: {exc})")}
    return {
        "available": True,
        "path": str(path),
        "symbols": int(bars["symbol"].nunique()),
        "first_bar": str(bars["date"].min().date()),
        "last_bar": str(bars["date"].max().date()),
        "basis": ("`paper_books.load_bars()` — the same local daily panel the "
                  "paper books are marked against and the agency proposes "
                  "against. No vendor is called: a step inside the daily pass "
                  "must not depend on one being up."),
    }


def _with_forecast_only(bars):
    """Union the supplementary panel of names the RANKER excludes.

    `forecast_grader` reported the same **2,911 records past their resolution
    date and still unresolved** on every run, and kept the ledger canary
    DEGRADED for it. They were not unresolvable: 105 of the 110 stranded
    tickers were simply absent from `prices_2025_26/bars.parquet` -- ETFs (XBI,
    SMH), REITs (AVB, DLR) and a tail of microcaps that a universe screen
    dropped before the panel was built. Something forecast on them; nothing
    ever fetched a price.

    The extra panel is a SEPARATE file on purpose (`pull_forecast_bars`): the
    main one is read by the ranker and fingerprinted by `sim_run.u_rank`, and
    widening the ranker's universe with names its own eligibility screen
    rejected is a different change with its own survivorship argument. The
    grader needs prices for names the ranker is entitled to ignore.

    Absent supplementary file -> the main panel, unchanged. This can only ever
    ADD priceable names.
    """
    import pandas as pd

    from backend import config as _cfg

    p = (Path(_cfg.OPTIMUS_LEDGER_DIR) / "prices_2025_26"
         / "bars_forecast_only.parquet")
    if not p.exists():
        return bars
    try:
        extra = pd.read_parquet(p)
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("forecast-only panel unreadable (%s); using the main "
                       "panel alone", exc)
        return bars
    cols = [c for c in bars.columns if c in extra.columns]
    if "symbol" not in cols or "date" not in cols or "close" not in cols:
        return bars
    # The MAIN panel wins on a collision: it is the one the books are marked
    # against, and two prices for one symbol-date is a reconciliation problem
    # rather than a grading one.
    return (pd.concat([bars, extra[cols]], ignore_index=True)
            .drop_duplicates(["symbol", "date"], keep="first"))


def local_price_fetch(tickers: list[str], start: str, end: str,
                      *, bars=None):
    """`ledger_resolver.PriceFetch`, served from the LOCAL bars parquet.

    Returns a wide frame of closes (DatetimeIndex, one column per ticker).
    A ticker with no rows is simply ABSENT, which is the contract the resolver
    already declares and already accounts for by name in `unpriceable`.
    """
    import pandas as pd

    if bars is None:
        from backend.services import paper_books as PB
        bars = PB.load_bars()
        bars = _with_forecast_only(bars)
    want = [str(t) for t in tickers if t]
    df = bars[bars["symbol"].isin(want)]
    if df.empty:
        return pd.DataFrame()
    lo = pd.Timestamp(start)
    hi = pd.Timestamp(end)
    df = df[(df["date"] >= lo) & (df["date"] <= hi)]
    if df.empty:
        return pd.DataFrame()
    wide = df.pivot_table(index="date", columns="symbol", values="close",
                          aggfunc="last")
    wide.index = pd.to_datetime(wide.index)
    return wide.sort_index()


# ===========================================================================
# WHY A DUE RECORD DID NOT GRADE
# ===========================================================================


def _as_float(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def refusal_for(rec: dict) -> str:
    """The NAMED reason this still-ungraded record did not grade.

    Ordered by what is broken FURTHEST upstream, because the first answer is
    the actionable one: a record with no ticker cannot be blamed on a missing
    bar, and an observable no grader knows cannot be blamed on its threshold.

    `NO_BAR_FOR_RESOLUTION_DATE` is reached by ELIMINATION, not by looking in
    the panel, and that is deliberate: the resolver has already been round, and
    a record it left ungraded while the record itself is complete was left
    ungraded for want of bars. Re-deriving "does the panel cover this window"
    here would be a second implementation of the window check that
    `belief_state.resolve_one` already owns, and the one that would drift is
    this one. The resolver's own `unpriceable` block names the tickers.
    """
    if not str(rec.get("ticker") or "").strip():
        return "RECORD_LACKS_TARGET"
    obs = str(rec.get("observable") or "")
    required = _OBSERVABLE_REQUIRES.get(obs)
    if required is None:
        return "MECHANISM_HAS_NO_GRADER"
    for field in required:
        value = rec.get(field)
        if field == "threshold" and _as_float(value) is None:
            return "RECORD_LACKS_TARGET"
        if field == "benchmark" and not str(value or "").strip():
            return "RECORD_LACKS_TARGET"
    # Everything the RECORD owes is present, so what is missing is a BAR.
    return "NO_BAR_FOR_RESOLUTION_DATE"


def bucket_of(rec: dict, *, today: date,
              quarantined: bool = False) -> str:
    """Which of the closed `BUCKETS` this record finished in, after the run."""
    if rec.get("outcome") is not None:
        return "graded"
    if rec.get("void_reason"):
        return "VOID"
    try:
        due = today >= date.fromisoformat(str(rec["resolves_after"])[:10])
    except (KeyError, ValueError):
        # A record with no readable resolution date is not "not yet due" — that
        # would park it in the one bucket that is not a finding.
        return "RECORD_LACKS_TARGET"
    if not due:
        return "not_yet_due"
    if quarantined:
        return "QUARANTINED"
    return refusal_for(rec)


# ===========================================================================
# THE UNRESOLVABLE — voided, never "nothing to do" (review 2026-09-26 R9)
# ===========================================================================

#: Ticker notations no equity bar source can ever serve (futures, indices, the
#: dollar index in Yahoo notation). Same list `pull_forecast_bars` reports as
#: PERMANENTLY_UNPRICEABLE.
NON_EQUITY_SUFFIXES: tuple[str, ...] = ("=F",)
NON_EQUITY_PREFIXES: tuple[str, ...] = ("^",)
NON_EQUITY_EXACT: frozenset = frozenset({"DX-Y.NYB"})

#: The closed set of reasons a due record is voided as unresolvable.
VOID_REASONS: tuple[str, ...] = (
    "UNRESOLVABLE_NO_EQUITY_BAR",
    "UNRESOLVABLE_DELISTED",
    "UNRESOLVABLE_NO_BAR_PAST_HORIZON",
)


def _non_equity(t: str) -> bool:
    return (t.endswith(NON_EQUITY_SUFFIXES) or t.startswith(NON_EQUITY_PREFIXES)
            or t in NON_EQUITY_EXACT)


def unresolvable_reason(rec: dict, *, today: date, panel_dates, last_bar: dict,
                        bars_from: Any) -> tuple[str, str] | None:
    """(code, sentence) when this due record can NEVER resolve, else None.

    Three cases, each derived from the local panel itself, never a vendor call:

    * NO_EQUITY_BAR -- the ticker (or a named benchmark) is a futures/index
      notation no equity bar source serves, and the panel has no bar for it;
    * DELISTED -- the ticker's bars STOPPED at least
      `config.FORECAST_VOID_DELISTED_MIN_SESSIONS` panel sessions before the
      panel's newest bar, and fewer than `horizon_days + 1` bars exist from
      `made_at` (AVB stopped 2026-08-14, EA 2026-08-04; both `inactive` at the
      venue on 2026-09-26);
    * NO_BAR_PAST_HORIZON -- no panel has ANY bar for the ticker, its
      resolution date is `config.FORECAST_VOID_NO_BAR_GRACE_DAYS` behind
      today, and the panel covers that date.

    A record that might still resolve (a bar that may yet arrive) is None.
    """
    from backend import config as _cfg

    t = str(rec.get("ticker") or "").strip()
    if not t:
        return None
    try:
        ra = date.fromisoformat(str(rec["resolves_after"])[:10])
        h = int(rec.get("horizon_days") or 0)
    except (KeyError, ValueError, TypeError):
        return None
    if today < ra:
        return None
    bench = str(rec.get("benchmark") or "").strip()
    needs = [t] + ([bench] if rec.get("observable") == "beats_benchmark" and bench else [])
    for sym in needs:
        if sym not in last_bar and _non_equity(sym):
            return ("UNRESOLVABLE_NO_EQUITY_BAR",
                    f"{sym} is a futures/index notation; no equity bar source can "
                    f"serve it and the local panel has none")
    if not len(panel_dates):
        return None
    newest = panel_dates[-1]
    if t in last_bar:
        lb = last_bar[t]
        stopped = int((panel_dates > lb).sum())
        have = int(bars_from(t, str(rec.get("made_at", ""))[:10]))
        if (stopped >= int(_cfg.FORECAST_VOID_DELISTED_MIN_SESSIONS)
                and have < h + 1):
            return ("UNRESOLVABLE_DELISTED",
                    f"{t}'s bars stop at {str(lb)[:10]} while the panel runs to "
                    f"{str(newest)[:10]} ({stopped} sessions later); the window needs "
                    f"{h + 1} bars from {str(rec.get('made_at'))[:10]} and {have} exist")
        return None
    grace = int(_cfg.FORECAST_VOID_NO_BAR_GRACE_DAYS)
    import pandas as pd
    if (today - ra).days >= grace and pd.Timestamp(newest) >= pd.Timestamp(ra):
        return ("UNRESOLVABLE_NO_BAR_PAST_HORIZON",
                f"no local panel has any bar for {t}; its resolution date {ra} is "
                f"{(today - ra).days} days past (grace {grace}) and the panel runs to "
                f"{str(newest)[:10]}")
    return None


def void_unresolvable(*, path: Path, today: date, bars=None,
                      skip_ids: set[str] | None = None, write: bool = True) -> dict:
    """Void every due, ungraded record that can never resolve. Returns the census.

    The record STAYS in the ledger (`belief_state.resolve_one` already treats a
    `void_reason` as terminal and out of every score): voiding is additive --
    `void_reason`, `voided_at`, `voided_by` -- and reversible by removing those
    three fields. Quarantined records are never touched (their disposition is
    attended). The rewrite is atomic and re-reads the ledger immediately before
    it, so a row appended meanwhile is kept.
    """
    import pandas as pd

    from backend.services import belief_state as B

    if bars is None:
        from backend.services import paper_books as PB
        bars = _with_forecast_only(PB.load_bars())
    skip_ids = skip_ids or set()
    panel_dates = pd.DatetimeIndex(sorted(pd.to_datetime(bars["date"]).unique()))
    last_bar = bars.groupby("symbol")["date"].max().to_dict()
    by_sym = {s: g.sort_values() for s, g in
              pd.to_datetime(bars["date"]).groupby(bars["symbol"])}

    def _bars_from(sym: str, d: str) -> int:
        s = by_sym.get(sym)
        if s is None or not d:
            return 0
        return int((s >= pd.Timestamp(d)).sum())

    rows = B.read_predictions(path)
    plan: dict[str, tuple[str, str]] = {}
    for r in rows:
        if r.get("outcome") is not None or r.get("void_reason"):
            continue
        pid = str(r.get("prediction_id"))
        if pid in skip_ids:
            continue
        why = unresolvable_reason(r, today=today, panel_dates=panel_dates,
                                  last_bar=last_bar, bars_from=_bars_from)
        if why:
            plan[pid] = why
    by_reason: dict[str, int] = {k: 0 for k in VOID_REASONS}
    by_ticker: dict[str, int] = {}
    sample: list[dict] = []
    written = 0
    if plan and write:
        fresh = B.read_predictions(path)                  # re-read: keep late appends
        stamp = _now()
        out_rows = []
        for r in fresh:
            pid = str(r.get("prediction_id"))
            if (pid in plan and r.get("outcome") is None and not r.get("void_reason")):
                code, sentence = plan[pid]
                r = dict(r)
                r["void_reason"] = f"{code}: {sentence}"
                r["voided_at"] = stamp
                r["voided_by"] = "forecast_grader.void_unresolvable"
                written += 1
            out_rows.append(r)
        tmp = Path(path).with_name(Path(path).name + f".void.{os.getpid()}.tmp")
        tmp.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out_rows)
                       + "\n", encoding="utf-8")
        os.replace(tmp, path)
    for pid, (code, sentence) in plan.items():
        by_reason[code] = by_reason.get(code, 0) + 1
    for r in rows:
        pid = str(r.get("prediction_id"))
        if pid in plan:
            by_ticker[str(r.get("ticker"))] = by_ticker.get(str(r.get("ticker")), 0) + 1
            if len(sample) < 10:
                sample.append({"prediction_id": pid, "ticker": r.get("ticker"),
                               "void_reason": f"{plan[pid][0]}: {plan[pid][1]}"})
    return {"voided_unresolvable": written if write else 0,
            "would_void": len(plan), "by_reason": by_reason,
            "by_ticker": by_ticker, "sample": sample}


# ===========================================================================
# THE RUN
# ===========================================================================


def grade_due(*, path: Path | None = None, today: date | None = None,
              population: str | None = None,
              price_fetch=None, write: bool = True,
              out: Path | None = None, void_bars=None) -> dict:
    """Grade every due record off local bars; return the receipt.

    Never raises for a record's sake. The resolver's own refusals (an
    unestablished population, an unreadable campaign ledger) come back as a
    `status: REFUSED` report and are carried onto this receipt by name, because
    a run that refused and a run that found nothing due are opposite findings.
    """
    from backend.services import belief_state as B
    from backend.services import ledger_resolver as LR

    day = str(today or date.today())
    today = today or date.today()
    path = Path(path) if path is not None else B.PREDICTIONS
    source = bars_source()
    started = _now()

    before = B.read_predictions(path)
    n_graded_before = sum(1 for r in before if r.get("outcome") is not None)

    fetch = price_fetch or local_price_fetch
    try:
        report = LR.resolve_due(path=path, price_fetch=fetch, today=today,
                                population=population)
    except Exception as exc:                                       # noqa: BLE001
        logger.exception("forecast grader: resolve_due raised")
        report = {"status": "ERROR",
                  "reason": f"{type(exc).__name__}: {exc}",
                  "due": 0, "newly_resolved": 0}

    # THE UNRESOLVABLE ARE VOIDED, NEVER "NOTHING TO DO" (review 2026-09-26
    # R9: 130 records printed as a refusal every day since August). Only on the
    # production price path (local bars) or with bars named by the caller: a
    # test that injects a price fetch must not be voided against this
    # machine's panel.
    void_census: dict = {"voided_unresolvable": 0, "skipped": None}
    if price_fetch is None or void_bars is not None:
        try:
            pre_q, _ = quarantined_ids(B.read_predictions(path), report, path=path)
            void_census = void_unresolvable(path=path, today=today, bars=void_bars,
                                            skip_ids=pre_q, write=write)
        except Exception as exc:                                   # noqa: BLE001
            logger.exception("forecast grader: void pass failed")
            void_census = {"voided_unresolvable": 0,
                           "error": f"{type(exc).__name__}: {exc}"[:300]}
    else:
        void_census["skipped"] = ("an injected price fetch and no void_bars: the "
                                  "void pass reads only the panel it is given")

    after = B.read_predictions(path)
    n_graded_after = sum(1 for r in after if r.get("outcome") is not None)

    q_ids, q_note = quarantined_ids(after, report, path=path)
    if q_note:
        logger.warning("forecast grader: %s", q_note)
    counts: dict[str, dict[str, int]] = {}
    for mech in declared_mechanisms(after):
        counts[mech] = {b: 0 for b in BUCKETS}
    for rec in after:
        mech = mechanism_of(rec)
        row = counts.setdefault(mech, {b: 0 for b in BUCKETS})
        bucket = bucket_of(rec, today=today,
                           quarantined=str(rec.get("prediction_id")) in q_ids)
        row[bucket] = row.get(bucket, 0) + 1

    totals = {b: sum(row.get(b, 0) for row in counts.values()) for b in BUCKETS}
    newly = n_graded_after - n_graded_before
    receipt = {
        "receipt": "grade_forecasts",
        "roadmap_item": "chunk 18b",
        "licence": LICENCE,
        "llm_spend_usd": 0.0,
        # `pnl` is the last stage: an outcome written onto a forecast is the
        # thing that makes it evidence, and nothing upstream may read it.
        "stage": "pnl",
        "date": day,
        "started_utc": started,
        "written_utc": _now(),
        "ledger_path": str(path),
        "population": population,
        "bars": source,
        "graded_by": ("backend.services.forecast_grader -> "
                      "ledger_resolver.resolve_due -> belief_state.resolve_one; "
                      "no return arithmetic lives in the grader itself"),
        "n_records": len(after),
        "newly_resolved": int(newly),
        "graded_before_this_run": int(n_graded_before),
        "graded_after_this_run": int(n_graded_after),
        "resolver_status": report.get("status", "ok"),
        "resolver_reason": report.get("reason"),
        "resolver_due": report.get("due"),
        "resolver_priced_from": report.get("priced_from"),
        "unpriceable": report.get("unpriceable") or [],
        "n_unpriceable_tickers": len(report.get("unpriceable") or []),
        "quarantine": report.get("quarantine"),
        "quarantine_note": q_note or None,
        "health": report.get("health"),
        "counts_by_mechanism": counts,
        "totals": totals,
        "n_still_refused": sum(totals.get(b, 0) for b in REFUSAL_BUCKETS),
        "voided_unresolvable": int(void_census.get("voided_unresolvable") or 0),
        "void": void_census,
        "buckets": list(BUCKETS),
        "read_me_first": (
            "Every record in the ledger is in exactly one bucket of the closed "
            "set, and every mechanism is listed even at zero — the failure this "
            "step exists to fix was 17,614 due records sitting in no bucket at "
            "all while an hourly roll-up reported the number and nothing acted "
            "on it. `graded` is read back OFF the ledger after the resolver "
            "ran, never predicted. `NO_BAR_FOR_RESOLUTION_DATE` is not a fault "
            "in the record: the local panel ends at `bars.last_bar` and those "
            "records grade on a later day. Nothing here computes a return: "
            "`belief_state.resolve_one` does, with every guard it already had."),
        "headline": (
            f"{newly:,} newly resolved; {totals.get('graded', 0):,} of "
            f"{len(after):,} records now carry an outcome; "
            f"{int(void_census.get('voided_unresolvable') or 0):,} voided as "
            f"unresolvable this run; "
            f"{totals.get('NO_BAR_FOR_RESOLUTION_DATE', 0):,} wait on a bar, "
            f"{totals.get('not_yet_due', 0):,} are not yet due"),
    }
    if write:
        p = Path(out) if out is not None else receipt_path(day)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(receipt, ensure_ascii=False, indent=1,
                                default=str), encoding="utf-8")
        receipt["path"] = str(p)
    return receipt


def quarantined_ids(rows: list[dict], report: dict,
                    *, path: Path | None = None) -> tuple[set[str], str]:
    """Which records the resolver deliberately did NOT grade, by prediction id.

    The report lists at most twenty ids, so reading it alone would file every
    quarantined record past the twentieth into `NO_BAR_FOR_RESOLUTION_DATE` —
    a price-gap bucket, for records that are sitting there on purpose awaiting
    an attended disposition. The set is therefore asked of
    `evidence_population`, the module that owns the ruling, rather than
    re-derived or truncated; when it cannot answer, the twenty listed ids are
    used and the shortfall is NAMED on the receipt instead of being absorbed.
    """
    q = report.get("quarantine") or {}
    n = int(q.get("n_quarantined") or 0)
    listed = {str(i) for i in (q.get("prediction_ids") or [])}
    if not n:
        return set(), ""
    try:
        from backend.services import evidence_population as EP
        hashes = EP.quarantined_hashes(path=path)
        ids = {str(r.get("prediction_id")) for r in rows
               if EP.record_hash(r) in hashes}
    except Exception as exc:                                       # noqa: BLE001
        return listed, (
            f"CANNOT DETERMINE the full quarantine set "
            f"({type(exc).__name__}: {exc}); {len(listed)} of {n} quarantined "
            f"records are identified by the resolver's own listing and the "
            f"remainder are counted under their price/record reason instead")
    if len(ids) != n:
        return (ids | listed), (
            f"the quarantine set resolved to {len(ids)} ids against the "
            f"resolver's count of {n}; the union of both is used and this "
            f"disagreement is on the receipt rather than silently reconciled")
    return ids, ""


def declared_mechanisms(rows: list[dict] | None = None) -> list[str]:
    """Every mechanism that must appear on the receipt, zero or not.

    The union of the roll-up's DECLARED list and whatever the ledger actually
    holds. Declared alone would hide the swarm's 19 specialists; observed alone
    would hide a declared mechanism that has written nothing, which is the one
    a reader most needs to see named.
    """
    names: list[str] = []
    try:
        from backend.services.lab_decision_vs_reality import DECLARED_MECHANISMS
        names += [m[0] for m in DECLARED_MECHANISMS]
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("forecast grader: the declared mechanism list could not "
                       "be read (%s) — the receipt lists only what the ledger "
                       "holds, and says so", exc)
    for r in rows or []:
        m = mechanism_of(r)
        if m not in names:
            names.append(m)
    return names


__all__ = ["BUCKETS", "LICENCE", "REFUSAL_BUCKETS", "VOID_REASONS", "bars_source",
           "unresolvable_reason", "void_unresolvable",
           "bucket_of", "declared_mechanisms", "grade_due",
           "local_price_fetch", "mechanism_of", "out_dir", "quarantined_ids",
           "receipt_path", "refusal_for", "run_date"]
