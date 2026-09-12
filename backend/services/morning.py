"""ONE CLICK = MORNING (roadmap 2026-09-11, lane O item O5).

Murat's ask, verbatim from the roadmap: *"One click = Morning. Pull news, build
the digest, mark every paper book, write the pre-open forecast rows, refresh the
coverage card, then hand the operator the Ask page with today's brief loaded."*

WHAT THIS MODULE IS, AND WHAT IT REFUSES TO BE
==============================================
It is a **sequence of named steps that each write their own status into ONE
receipt**, and nothing else. It runs no job in a subprocess, imports no broker,
places no order, arms no lane and asks no LLM for a number. The forecast rows it
writes carry a probability the ENGINE computed from the lanes' own realised
history; the local model is not consulted, because a model that cannot be graded
on what it said is not a forecaster (and "no LLM authority over capital" is not
negotiable in this programme).

INVARIANT 15 IS THE WHOLE DESIGN
================================
*A step that did nothing says so.* Every step returns one of five statuses and
each of them is a different sentence:

* ``ok``        — it ran and the counts are in the row;
* ``nothing_to_do`` — it ran, correctly, and there was nothing (a Saturday's
  corpus, a ledger with nothing due). This is NOT a failure and NOT an ``ok``
  with zeros: the two are different facts and a card cannot tell them apart
  from a bare 0;
* ``refused``   — a precondition was absent and the row NAMES it (the corpus
  directory, the CRSP stocknames table, the network). A refusal is a finding;
* ``error``     — it raised. The type and message are in the row, truncated;
  nothing propagates, because half a morning is still a morning and the
  operator needs the receipt more than the traceback;
* ``skipped``   — the caller asked for it not to run (``do_network=False``).

There is no sixth status and no step that can be absent from the receipt: the
step list is a module constant, and the runner walks IT, not whatever happened
to succeed. A check that reads the record of what ran cannot see what never got
called (`signal_reachability.py`'s founding lesson), so the plan is enumerated.

IDEMPOTENT PER DAY
==================
The receipt is ``backend/data/optimus/morning/<YYYY-MM-DD>_run<NN>.json`` and
the run number increments. A second click does not overwrite the first: two
mornings on one day is a fact about the day, and the earlier receipt is the only
evidence of what the first click saw.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    """The checkout, the same three lines as `routers/control.py:48`."""
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent.parent


REPO = _repo_root()
MORNING_DIR = REPO / "backend" / "data" / "optimus" / "morning"

#: Lane N-A's corpus writer (chunk 4). Held behind a NAME rather than built
#: inline in the coverage step, because a test that asserts "this source is
#: still PENDING" against a hard-coded live path encodes a filesystem moment --
#: and this one went red the hour another agent's `news_pull` first created the
#: directory. Same family as CLAUDE.md rule 5's calendar-moment fixtures.
NEWS_CORPUS_DIR = REPO / "backend" / "data" / "optimus" / "news_corpus"

#: The steps, in order, as (id, docstring-ish one-liner). The runner walks this
#: tuple; a step that raises still produces its row. Adding a step here without
#: a handler is a KeyError at import-time in `_HANDLERS`, which is the point.
STEPS: tuple[tuple[str, str], ...] = (
    ("news_pull", "today's market news (the dashboard fetch, not the corpus)"),
    ("digest", "yesterday's corpus rows, anonymised through the R2 digest spec"),
    ("mark_books", "the PI daily check for every lane, in-process"),
    ("forecasts", "one gradeable forecast row per lane, written by the engine"),
    ("agency_review", "one hold/sell/buy_more/trim call per holding of every "
                      "book a human holds, each with its row already written"),
    ("grade", "resolve every ledger record whose window has closed"),
    ("coverage", "rows per source today, from what exists"),
    ("ready", "what the operator can read next"),
)

STATUSES = ("ok", "nothing_to_do", "refused", "error", "skipped")

#: The horizon every morning forecast is written at. One session: the claim is
#: about TODAY, and a claim about today graded in a month is a different claim.
FORECAST_HORIZON_DAYS = 1

#: Below this many paired daily observations the lane's own win rate is not a
#: base rate, it is a handful of coin flips. The forecast is still written --
#: p = 0.5 with the basis named -- because a morning that writes nothing is
#: indistinguishable from a morning that did not run.
MIN_DAYS_FOR_WIN_RATE = 20

#: The lane every other reference lane is forecast AGAINST. It is the
#: equal-weight control that already exists; a lane with no control (the control
#: itself) is forecast against SPY and the row says so.
CONTROL_LANE = "balanced-ew-control"
FALLBACK_BENCHMARK = "SPY"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _trunc(exc: BaseException, n: int = 300) -> str:
    return f"{type(exc).__name__}: {exc}"[:n]


# ===========================================================================
# EVERY EXTERNAL CALL GOES THROUGH A MODULE-LEVEL FUNCTION
# ===========================================================================
#
# Not indirection for its own sake: the acceptance test for this module is "a
# network-less run yields refusals, not exceptions", and that test has to be
# able to replace each external call one at a time. A lazily-imported call inside a
# step body cannot be monkeypatched by name; these can.


def fetch_gdelt() -> dict:
    from backend.services.news_intelligence import fetch_gdelt_signals
    return fetch_gdelt_signals()


def fetch_stock_news(ticker: str, max_items: int = 10) -> list[dict]:
    from backend.services.news_intelligence import fetch_stock_news as _f
    return _f(ticker, max_items=max_items)


def run_all_lanes() -> dict:
    from backend.services.portfolio_intelligence.reference_engine import run_all_lanes as _f
    return _f()


def refresh_paper_snapshot(timeout_s: float = 30.0) -> dict:
    # The FETCH, not the route: a route carries `_require_enabled()`, and the
    # first real morning run reported `403 the control plane is disabled` for a
    # step the operator had already authorised by clicking the button.
    from backend.routers.control import paper_snapshot_fetch
    return paper_snapshot_fetch(timeout_s=timeout_s)


def resolve_due(**kw) -> dict:
    from backend.services.ledger_resolver import resolve_due as _f
    return _f(**kw)


def lane_nav_series() -> dict[str, list[tuple[str, float]]]:
    from backend.routers.control import _nav_series
    return _nav_series()


def corpus_dir() -> Path:
    from scripts.r7_news_representation import CORPUS_OBS_DIR
    return Path(CORPUS_OBS_DIR)


def company_name_map() -> dict[str, set[str]]:
    from scripts.r7_news_representation import company_name_map as _f
    return _f()


def digest_spec() -> tuple[dict, str]:
    """The FROZEN digest construction and its sha256, from the R2 prereg.

    Imported rather than restated: a morning digest built to a different recipe
    than the one the R2 arm was registered under is a different experiment, and
    the hash in the receipt is what lets a later reader tell.
    """
    from backend.services.portfolio_intelligence.r2_trial import (
        DIGEST_SPEC, DIGEST_SPEC_SHA256)
    return dict(DIGEST_SPEC), DIGEST_SPEC_SHA256


# ===========================================================================
# THE STEPS
# ===========================================================================


def _row(step: str, status: str, **fields) -> dict:
    assert status in STATUSES, status
    row = {"step": step, "status": status, "utc": _now()}
    row.update(fields)
    return row


def step_news_pull(ctx: dict) -> dict:
    """Today's market news.

    HONESTLY LABELLED. This is the DASHBOARD fetch -- GDELT's aggregate tone
    series plus a handful of yfinance headlines for SPY and QQQ -- and it is
    not a corpus: nothing is deduped, cursored, stamped with a `first_seen_utc`
    or written to disk for a later join. Lane N's `news_pull.py` is the corpus
    writer and it replaces this step in chunk 4. Until then the row says
    `dashboard_fetch_not_corpus` so nobody reads the count as coverage.
    """
    if not ctx["do_network"]:
        return _row("news_pull", "skipped", kind="dashboard_fetch_not_corpus",
                    reason="the caller asked for no network")
    out: dict[str, Any] = {"kind": "dashboard_fetch_not_corpus"}
    failures: list[str] = []
    try:
        g = fetch_gdelt()
        out["gdelt_available"] = bool(g.get("available", True))
        out["gdelt_points"] = len(g.get("tone_timeline") or [])
        if not out["gdelt_available"]:
            failures.append(f"gdelt: {str(g.get('reason'))[:120]}")
    except Exception as exc:                                       # noqa: BLE001
        failures.append(f"gdelt: {_trunc(exc, 160)}")
        out["gdelt_available"] = False
    headlines: list[dict] = []
    for sym, n in (("SPY", 10), ("QQQ", 5)):
        try:
            headlines.extend(fetch_stock_news(sym, n) or [])
        except Exception as exc:                                   # noqa: BLE001
            failures.append(f"{sym}: {_trunc(exc, 160)}")
    out["headlines"] = len(headlines)
    ctx["headlines"] = headlines
    if failures and not headlines and not out.get("gdelt_available"):
        return _row("news_pull", "refused", reason="; ".join(failures)[:400],
                    note=("every source failed. On a machine with no network "
                          "this is the expected row, and it is a refusal "
                          "naming the sources rather than an exception."),
                    **out)
    if failures:
        out["partial_failures"] = failures[:6]
    if not headlines and not out.get("gdelt_available"):
        return _row("news_pull", "nothing_to_do",
                    reason="both sources answered with nothing", **out)
    return _row("news_pull", "ok", **out)


_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def step_digest(ctx: dict) -> dict:
    """Yesterday's corpus rows, anonymised to the R2 digest spec.

    The anonymiser and the item format are IMPORTED from the frozen R2 trial
    (`r2_trial.DIGEST_SPEC`, sha256 in the row), so a morning digest and a
    research-arm digest are the same object. The two things it needs that this
    repo does not own -- the observation corpus (the terminal repo) and CRSP
    stocknames (the WRDS pull) -- are refused BY NAME when absent, never
    silently replaced with unmasked text, because an unmasked digest read by a
    model is a recall test wearing a reading test's clothes.
    """
    spec, spec_sha = digest_spec()
    base = {"digest_spec_sha256": spec_sha,
            "max_docs_in_digest": int(spec["max_docs_in_digest"]),
            "max_chars_per_doc": int(spec["max_chars_per_doc"])}
    try:
        cdir = corpus_dir()
    except Exception as exc:                                       # noqa: BLE001
        return _row("digest", "refused", reason=_trunc(exc), **base)
    if not cdir.is_dir():
        return _row("digest", "refused", corpus_dir=str(cdir),
                    reason=(f"news corpus absent: {cdir}. It lives in the TERMINAL "
                            f"repo and is read-only from here; lane N's corpus "
                            f"writer replaces this dependency in chunk 4."),
                    **base)
    day = ctx["yesterday"]
    shard = cdir / f"{day[:7]}.jsonl"
    if not shard.is_file():
        return _row("digest", "refused", corpus_dir=str(cdir), shard=str(shard),
                    reason=f"no shard for {day[:7]} under {cdir}", **base)
    try:
        names = company_name_map()
    except Exception as exc:                                       # noqa: BLE001
        return _row("digest", "refused", reason=_trunc(exc, 400),
                    note="the anonymiser needs CRSP issuer names; it is refused, not skipped",
                    **base)

    from scripts.r7_news_representation import mask_company, tokenise

    by_symbol: dict[str, list[str]] = {}
    n_rows = 0
    for line in shard.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        stamp = _DATE_RE.match(str(rec.get("observed_at") or ""))
        if not stamp or stamp.group(1) != day:
            continue
        n_rows += 1
        syms = rec.get("symbols") or []
        if not syms:
            continue
        text = " ".join(str(x) for x in (rec.get("title"), rec.get("body")) if x)
        if not text.strip():
            continue
        sym = str(syms[0]).upper().strip()
        items = by_symbol.setdefault(sym, [])
        if len(items) >= int(spec["max_docs_in_digest"]):
            continue
        masked = mask_company(tokenise(text), sym, names.get(sym, set()))
        item = " ".join(masked)[: int(spec["max_chars_per_doc"])].strip()
        if item:
            items.append(item)

    digests = {s: "\n".join(f"- {t}" for t in items)
               for s, items in by_symbol.items() if items}
    base.update({"corpus_day": day, "shard": str(shard), "rows_on_day": n_rows,
                 "n_symbols": len(digests),
                 "names_table_symbols": len(names)})
    if not digests:
        return _row("digest", "nothing_to_do",
                    reason=f"{n_rows} corpus rows stamped {day}, none with a symbol and text",
                    **base)
    sidecar = ctx["out_dir"] / f"{ctx['today']}_run{ctx['run']:02d}_digests.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(digests, ensure_ascii=False, indent=1), encoding="utf-8")
    base["digests_written_to"] = str(sidecar)
    return _row("digest", "ok", **base)


def step_mark_books(ctx: dict) -> dict:
    """Mark every paper book: the PI daily check, called in this process.

    In desktop mode the APScheduler jobs are not registered (`main.py`'s
    `_desktop_background_off`), so on the laptop this is the ONLY thing that
    marks a lane. Calling it in-process rather than spawning is deliberate: a
    subprocess would need its own database handle and its own `.env`, and the
    two-schedulers-one-NAV failure is exactly what desktop mode exists to stop.
    """
    out: dict[str, Any] = {}
    try:
        results = run_all_lanes() or {}
        out["lanes"] = sorted(results)
        out["n_lanes"] = len(results)
        out["rebalanced"] = sorted(
            lid for lid, snap in results.items()
            if getattr(snap, "latest_rebalance", None) is not None)
    except Exception as exc:                                       # noqa: BLE001
        return _row("mark_books", "error", reason=_trunc(exc, 400))
    if ctx["do_network"]:
        try:
            snap = refresh_paper_snapshot()
            out["paper_snapshot"] = {"ok": bool(snap.get("ok")),
                                     "n_lanes": snap.get("n_lanes"),
                                     "error": snap.get("error")}
        except Exception as exc:                                   # noqa: BLE001
            out["paper_snapshot"] = {"ok": False, "error": _trunc(exc, 200)}
    else:
        out["paper_snapshot"] = {"ok": False, "skipped": "the caller asked for no network"}
    # LANE B4: the paper books, in the same step and the same process.
    #
    # The books are a SEPARATE namespace from the lanes (`book:<fingerprint>`)
    # and a separate pass, but they share this step because they share the
    # failure it exists to prevent: on the laptop no APScheduler job is
    # registered, so if the morning click does not mark them nothing does, and
    # an unmarked book has no NAV series for its forecast to be graded against.
    try:
        from backend.services.book_cadence import run_all, yfinance_fallback
        report = run_all(price_fallback=(yfinance_fallback if ctx["do_network"]
                                         else None))
        out["books"] = {
            "n_marked": report.get("n_marked"),
            "n_decisions": report.get("n_decisions"),
            "n_refused": report.get("n_refused"),
            "receipts": [r.get("receipt_path")
                         for r in (report.get("passes") or {}).values()
                         if r.get("receipt_path")],
            "refused": [r for p_ in (report.get("passes") or {}).values()
                        for r in (p_.get("refused") or [])][:10],
        }
    except Exception as exc:                                       # noqa: BLE001
        # NOT fatal to the step: the lanes were marked and saying so is more
        # useful than reporting the whole morning as broken. The reason travels.
        out["books"] = {"error": _trunc(exc, 300)}

    if not out["n_lanes"] and not (out.get("books") or {}).get("n_marked"):
        return _row("mark_books", "nothing_to_do",
                    reason=("no reference lane is configured in this checkout "
                            "and no paper book was marked"), **out)
    return _row("mark_books", "ok", **out)


def _win_rate(lane: str, benchmark: str,
              series: dict[str, list[tuple[str, float]]]) -> tuple[float, dict]:
    """P(lane beats benchmark today), from the lanes' own paired history.

    THE PROBABILITY IS COMPUTED, NOT ASSERTED, and it is computed from the ONE
    quantity the forecast is about: how often this lane's daily return has
    exceeded that benchmark's on the days both marked. Below
    `MIN_DAYS_FOR_WIN_RATE` paired days it returns 0.5 and says why -- a win
    rate on four sessions is not a base rate, and rounding it into a forecast
    would launder four coin flips into a probability with a decimal point.
    """
    from backend.routers.control import _daily_returns

    a = _daily_returns(series.get(lane) or [])
    b = _daily_returns(series.get(benchmark) or [])
    both = sorted(set(a) & set(b))
    n = len(both)
    if not a and not b:
        return 0.5, {"basis": "no_local_nav_history", "n_paired_days": 0,
                     "note": ("neither lane has a NAV row in this checkout -- the "
                              "deployment marks the lanes, so the laptop's win rate "
                              "is not merely thin, it is absent")}
    if n < MIN_DAYS_FOR_WIN_RATE:
        return 0.5, {"basis": "insufficient_history", "n_paired_days": n,
                     "min_days": MIN_DAYS_FOR_WIN_RATE,
                     "note": (f"{n} paired sessions is below the {MIN_DAYS_FOR_WIN_RATE}-session "
                              f"floor, so the forecast is the coin flip and says so")}
    wins = sum(1 for d in both if a[d] > b[d])
    # Laplace, so a lane that has never lost does not forecast certainty off a
    # month of data. It moves a 20/20 from 1.00 to 0.955 and leaves 0.5 at 0.5.
    p = (wins + 1.0) / (n + 2.0)
    return round(float(p), 4), {"basis": "laplace_smoothed_paired_win_rate",
                                "n_paired_days": n, "wins": wins}


def step_forecasts(ctx: dict) -> dict:
    """One gradeable forecast per lane, written by the ENGINE.

    `model="engine"` is not decoration. The roadmap's B5 wants the local model
    writing its own rows eventually; until it does, the row that exists must say
    who made it, because a calibration table that mixes an engine's arithmetic
    with a model's judgement measures neither.

    Benchmark: every reference lane is forecast against the equal-weight control
    lane, which is what a control is for. The control lane itself has no
    control, so it is forecast against SPY and the row carries
    `benchmark_is_fallback: true` -- an index is not a twin and the receipt is
    not allowed to pretend otherwise.
    """
    from backend.services import belief_state as BS

    try:
        series = lane_nav_series()
    except Exception as exc:                                       # noqa: BLE001
        return _row("forecasts", "error", reason=_trunc(exc, 300))
    # THE LANE LIST IS NOT THE NAV MAP.
    #
    # Found on the first real run (2026-09-11): `run_all_lanes()` rebalanced all
    # four reference lanes and `paper_nav` was still empty, because the laptop
    # does not mark to market -- the deployment does. Keying the forecast step
    # off the NAV map made it `nothing_to_do` every single morning, which is a
    # gate that cannot go green. The lanes come from the step that just ran; the
    # NAV map only decides whether a win rate is computable, and when it is not,
    # the row is the coin flip with `no_local_nav_history` named on it.
    marked = next((r for r in ctx["rows"] if r["step"] == "mark_books"), {})
    lanes = ctx.get("lanes") or marked.get("lanes") or sorted(series)
    if not lanes:
        return _row("forecasts", "nothing_to_do",
                    reason=("no lane is configured in this checkout and none has a "
                            "NAV series"))
    made: list[dict] = []
    records = []
    for lane in lanes:
        fallback = lane == CONTROL_LANE or CONTROL_LANE not in series
        benchmark = FALLBACK_BENCHMARK if fallback else CONTROL_LANE
        p, basis = _win_rate(lane, benchmark, series)
        try:
            rec = BS.make_prediction(
                ticker=lane, specialist="morning_click",
                observable=BS.Observable.BEATS_BENCHMARK,
                horizon_days=FORECAST_HORIZON_DAYS, probability=p,
                benchmark=benchmark,
                thesis=(f"{lane} beats {benchmark} over the next session. The "
                        f"probability is this lane's own {basis['basis']} against "
                        f"that benchmark ({basis.get('n_paired_days')} paired sessions)."),
                counter_thesis=(f"A one-session win rate is mostly noise; the lane's "
                                f"edge over {benchmark} may be zero and this row is "
                                f"then a 50/50 dressed as {p}."),
                next_observable=f"tomorrow's marked NAV for {lane} and {benchmark}",
                model="engine", model_version="morning-o5-1",
                prompt=f"morning:{ctx['today']}:{lane}:{benchmark}",
                input_snapshot={"lane": lane, "benchmark": benchmark, **basis},
                made_at=ctx["made_at"], session_as_of=ctx["today"])
        except ValueError as exc:
            made.append({"lane": lane, "written": False, "reason": _trunc(exc, 200)})
            continue
        records.append(rec)
        made.append({"lane": lane, "benchmark": benchmark,
                     "benchmark_is_fallback": fallback,
                     "probability": p, "prediction_id": rec.prediction_id,
                     "resolves_after": rec.resolves_after, **basis})
    if not records:
        return _row("forecasts", "nothing_to_do", rows=made,
                    reason="every lane refused to produce a gradeable record")
    try:
        BS.append(records, ctx["predictions_path"])
    except Exception as exc:                                       # noqa: BLE001
        return _row("forecasts", "error", reason=_trunc(exc, 300), rows=made)
    return _row("forecasts", "ok", n_written=len(records), rows=made,
                model="engine", observable=BS.Observable.BEATS_BENCHMARK.value,
                horizon_days=FORECAST_HORIZON_DAYS,
                ledger=str(ctx["predictions_path"] or BS.PREDICTIONS))


def step_agency_review(ctx: dict) -> dict:
    """LANE A3/A4 — the daily review, and the protect-first check, per book.

    It runs AFTER `mark_books` (the positions and the NAV it reads are that
    step's output) and BEFORE `grade`, so a row written this morning is graded
    by the same morning's resolver only once its own window has closed.

    The receipt names every call AND its ledger row id. That pairing is the
    whole acceptance criterion of A3 — "every call has a forecast row" — and a
    receipt that printed the calls alone would let the two drift apart without
    anything failing.
    """
    from backend.services import agency as AG
    from backend.services import paper_books as PB

    try:
        bars = PB.load_bars()
    except Exception as exc:                                       # noqa: BLE001
        # REFUSED, not error: the books were marked by the deployment or not at
        # all, and a machine with no local bars cannot price a holding. Naming
        # the missing input is the finding.
        return _row("agency_review", "refused", reason=_trunc(exc, 300))
    try:
        out = AG.review_all(bars=bars, asof=ctx["date_obj"],
                            path=ctx["predictions_path"])
    except Exception as exc:                                       # noqa: BLE001
        return _row("agency_review", "error", reason=_trunc(exc, 400))
    # A4 IN THE SAME STEP AND THE SAME PASS. The breach rule reads the NAV
    # `mark_books` just wrote, and a protection that ran on a different clock
    # from the review would let a book be advised HOLD in the morning and
    # flipped by another pass in the afternoon on the same day's number.
    try:
        protect = AG.protect_first_pass(asof=ctx["date_obj"], bars=bars)
    except Exception as exc:                                       # noqa: BLE001
        protect = {"error": _trunc(exc, 300)}
    rows = [{"book_id": b["book_id"], "ticker": c["ticker"],
             "decision": c["decision"], "probability": c["probability"],
             "prediction_id": c["prediction_id"], "row_hash": c["row_hash"]}
            for b in out["books"] for c in b["calls"]]
    refused = [{"book_id": b["book_id"], **r}
               for b in out["books"] for r in b["refused"]]
    if not out["n_books"]:
        return _row("agency_review", "nothing_to_do",
                    reason=("no book carries origin='human_text' in this "
                            "checkout, so there is nothing a person holds to "
                            "review. That is not the same as a review that "
                            "found nothing to say."),
                    protect_first=protect)
    status = "ok" if rows else "nothing_to_do"
    return _row("agency_review", status, n_books=out["n_books"],
                n_calls=out["n_calls"], n_refused=out["n_refused"],
                calls=rows, refused=refused, protect_first=protect,
                vocabulary=list(AG.DECISIONS),
                ledger=str(ctx["predictions_path"] or "the default ledger"),
                ordering=out["books"][0]["ordering"] if out["books"] else None)


def step_grade(ctx: dict) -> dict:
    """Grade the local ledger, here, on the laptop.

    R4 ("what we thought vs what happened exists and does not close on the
    laptop") closes at this line: `resolve_due` has run on Railway for weeks and
    never on the machine the forecasts are now written on. A morning that writes
    forecasts and never grades them accrues an unreadable ledger.
    """
    kw: dict[str, Any] = {"today": ctx["date_obj"],
                          "price_fetch": nav_augmented_price_fetch}
    if ctx["predictions_path"] is not None:
        kw["path"] = ctx["predictions_path"]
    try:
        rep = resolve_due(**kw)
    except Exception as exc:                                       # noqa: BLE001
        return _row("grade", "error", reason=_trunc(exc, 400),
                    note=("grading needs prices. On a machine with no network the "
                          "resolver cannot price a due record, and an ungraded "
                          "record stays overdue rather than being dropped."))
    keep = {k: rep.get(k) for k in
            ("as_of", "due", "newly_resolved", "pending", "overdue", "priced_from")}
    # NOT `status`: that key is this ROW's own five-valued state, and the
    # resolver's own status ("REFUSED"/None) would silently overwrite it.
    keep["resolver_status"] = rep.get("status")
    keep["unpriceable"] = len(rep.get("unpriceable") or [])
    keep["health"] = (rep.get("health") or {}).get("status")
    if rep.get("status") == "REFUSED":
        return _row("grade", "refused", reason=str(rep.get("reason"))[:400], **keep)
    if not rep.get("due"):
        return _row("grade", "nothing_to_do",
                    reason="no ledger record's window had closed by today", **keep)
    return _row("grade", "ok", **keep)


def nav_augmented_price_fetch(tickers: list[str], start: str, end: str):
    """Adjusted closes, PLUS one column per paper lane from `paper_nav`.

    A morning forecast is `lane beats control_lane`, and neither name is a
    security: the stock resolver would log "can never resolve" for every one of
    them and the ledger would accrue rows nothing could ever grade. The lanes
    have a price series -- their own marked NAV -- so this fetch unions the two.
    A lane with no NAV rows is simply absent from the frame, which the resolver
    already reports BY NAME rather than silently dropping.

    Only ADDS columns. A ticker the stock fetch returns is never overwritten.
    """
    import pandas as pd

    from backend.services.ledger_resolver import _default_price_fetch

    wanted = [t for t in tickers if t]
    frame = pd.DataFrame()
    stock_names = [t for t in wanted if not _looks_like_lane(t)]
    if stock_names:
        try:
            frame = _default_price_fetch(stock_names, start, end)
        except Exception as exc:                                   # noqa: BLE001
            logger.warning("morning: stock price fetch failed (%s); lanes only",
                           _trunc(exc, 120))
            frame = pd.DataFrame()
    try:
        series = lane_nav_series()
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("morning: lane NAV read failed: %s", _trunc(exc, 120))
        return frame
    try:
        from backend.services.paper_books import nav_series as book_nav_series
        series = {**series, **book_nav_series()}
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("morning: book NAV read failed: %s", _trunc(exc, 120))
    for lane, rows in series.items():
        if lane in getattr(frame, "columns", []):
            continue
        if not rows:
            continue
        idx = pd.to_datetime([d for d, _ in rows])
        col = pd.Series([v for _, v in rows], index=idx).sort_index()
        frame = col.to_frame(lane) if frame.empty else frame.join(col.rename(lane), how="outer")
    return frame


def _looks_like_lane(name: str) -> bool:
    """A lane or book id, not a ticker.

    Lowercase or hyphenated; tickers are neither. A book id (`book:<16 hex>`)
    is lowercase and therefore already excluded, but it is named explicitly
    because "it happens to be lowercase" is not a rule anyone can rely on.
    """
    from backend.services.paper_books import is_book_id
    return is_book_id(name) or name != name.upper() or "-" in name


def step_coverage(ctx: dict) -> dict:
    """Rows per source today, from what exists -- and an em dash for the rest.

    Lane N has not landed, so the honest coverage card is small: whatever the
    corpus shard holds for today, whatever the analyst snapshot holds for today,
    and this run's dashboard headline count with its `dashboard_fetch_not_corpus`
    label. `news_corpus/` is listed as PENDING rather than 0 -- a source that
    does not exist yet and a source that returned nothing are different facts.
    """
    sources: list[dict] = []
    day = ctx["today"]
    try:
        cdir = corpus_dir()
        shard = cdir / f"{day[:7]}.jsonl"
        if shard.is_file():
            n = 0
            for ln in shard.read_text(encoding="utf-8", errors="replace").splitlines():
                if not ln.strip():
                    continue
                try:
                    stamp = _DATE_RE.match(str(json.loads(ln).get("observed_at") or ""))
                except ValueError:
                    continue
                if stamp and stamp.group(1) == day:
                    n += 1
            sources.append({"source": "terminal_corpus_observations", "rows_today": n,
                            "path": str(shard), "pit_grade": "first_seen_only"})
        else:
            sources.append({"source": "terminal_corpus_observations", "rows_today": None,
                            "path": str(shard), "note": "no shard for this month"})
    except Exception as exc:                                       # noqa: BLE001
        sources.append({"source": "terminal_corpus_observations", "rows_today": None,
                        "error": _trunc(exc, 200)})
    snaps = REPO / "backend" / "data" / "analyst_snapshots.jsonl"
    if snaps.is_file():
        try:
            n = sum(1 for ln in snaps.read_text(encoding="utf-8", errors="replace").splitlines()
                    if ln.strip() and f'"{day}"' in ln)
            sources.append({"source": "analyst_snapshots", "rows_today": n,
                            "path": str(snaps)})
        except OSError as exc:
            sources.append({"source": "analyst_snapshots", "rows_today": None,
                            "error": _trunc(exc, 200)})
    else:
        sources.append({"source": "analyst_snapshots", "rows_today": None,
                        "path": str(snaps), "note": "no local snapshot file"})
    corpus_writer = NEWS_CORPUS_DIR
    shards = sorted(corpus_writer.rglob(f"{day}.jsonl")) if corpus_writer.is_dir() else []
    # ROWS, not files. The first version counted shard FILES under a key called
    # `rows_today`, which is a card printing "1" for a source that wrote 4,000
    # rows -- the quiet kind of wrong this board exists to not do.
    corpus_rows = None
    if corpus_writer.is_dir():
        corpus_rows = 0
        for s in shards:
            try:
                corpus_rows += sum(
                    1 for ln in s.read_text(encoding="utf-8", errors="replace").splitlines()
                    if ln.strip())
            except OSError:
                continue
    sources.append({"source": "news_corpus (lane N-A)",
                    "rows_today": corpus_rows,
                    "shards_today": len(shards),
                    "path": str(corpus_writer),
                    "note": ("PENDING: the corpus writer is chunk 4. An absent source "
                             "is not a source that returned zero.")})
    news_row = next((r for r in ctx["rows"] if r["step"] == "news_pull"), {})
    sources.append({"source": "dashboard_fetch_not_corpus",
                    "rows_today": news_row.get("headlines"),
                    "note": "display headlines; never joined to a return"})
    return _row("coverage", "ok", sources=sources, day=day,
                n_sources_with_rows=sum(1 for s in sources if s.get("rows_today")))


def step_ready(ctx: dict) -> dict:
    """What the operator can read next, and what did not happen.

    Deliberately the last row and deliberately a SUMMARY of the others rather
    than a new fact: a "ready" that is green while three steps refused is the
    house failure mode with a tick beside it.
    """
    counts: dict[str, int] = {s: 0 for s in STATUSES}
    for r in ctx["rows"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    refused = [r["step"] for r in ctx["rows"] if r["status"] in ("refused", "error")]
    fc = next((r for r in ctx["rows"] if r["step"] == "forecasts"), {})
    return _row("ready", "ok", step_status_counts=counts,
                steps_that_did_not_run=refused,
                forecast_rows_today=fc.get("n_written", 0),
                brief=("Ask Aegis can now answer 'what do you think happens today?' "
                       "from these forecast rows."
                       if fc.get("n_written") else
                       "No forecast row was written today, so Ask Aegis will say the "
                       "morning has not produced one rather than invent an answer."))


_HANDLERS: dict[str, Callable[[dict], dict]] = {
    "news_pull": step_news_pull,
    "digest": step_digest,
    "mark_books": step_mark_books,
    "forecasts": step_forecasts,
    "agency_review": step_agency_review,
    "grade": step_grade,
    "coverage": step_coverage,
    "ready": step_ready,
}
assert set(_HANDLERS) == {s for s, _ in STEPS}, "every declared step needs a handler"


# ===========================================================================
# THE RUNNER
# ===========================================================================


def next_run_number(day: str, out_dir: Path | None = None) -> int:
    """run01 the first time today, run02 the second. Never an overwrite."""
    out_dir = out_dir or MORNING_DIR
    if not out_dir.is_dir():
        return 1
    existing = [p for p in out_dir.glob(f"{day}_run*.json")
                if re.fullmatch(rf"{re.escape(day)}_run\d+\.json", p.name)]
    return len(existing) + 1


def run_morning(*, today: date | None = None, do_network: bool = True,
                predictions_path: Path | None = None,
                out_dir: Path | None = None,
                lanes: list[str] | None = None) -> dict:
    """Run every step in order, write ONE receipt, return it.

    Never raises for a step's sake. The only exceptions that escape are the ones
    that stop a receipt being written at all (an unwritable directory), because
    a morning whose receipt could not be written is the one case where silence
    would be worse than a traceback.
    """
    day_obj = today or datetime.now(timezone.utc).date()
    day = str(day_obj)
    out_dir = out_dir or MORNING_DIR
    run = next_run_number(day, out_dir)
    ctx: dict[str, Any] = {
        "today": day, "date_obj": day_obj,
        "yesterday": str(day_obj - timedelta(days=1)),
        "made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "do_network": bool(do_network),
        "predictions_path": predictions_path,
        "out_dir": out_dir, "run": run, "rows": [], "lanes": lanes,
    }
    started = datetime.now(timezone.utc)
    for step_id, what in STEPS:
        try:
            row = _HANDLERS[step_id](ctx)
        except Exception as exc:                                   # noqa: BLE001
            logger.exception("morning step %s raised", step_id)
            row = _row(step_id, "error", reason=_trunc(exc, 400))
        row.setdefault("what", what)
        ctx["rows"].append(row)
    receipt = {
        "receipt": "morning",
        "roadmap_item": "O5",
        "licence": "PRODUCT_EXPERIMENT",
        "date": day, "run": run,
        "started_utc": started.isoformat(timespec="seconds"),
        "finished_utc": _now(),
        "elapsed_s": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
        "network_requested": bool(do_network),
        "declared_steps": [s for s, _ in STEPS],
        "steps": ctx["rows"],
        "read_me_first": (
            "One row per DECLARED step, in order, always -- the runner walks the "
            "step list, not the list of things that worked. `refused` names the "
            "missing precondition and is a finding; `nothing_to_do` means the step "
            "ran correctly and there was nothing, which is not the same as zero. "
            "Nothing here places an order, arms a lane or asks a model for a number."),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{day}_run{run:02d}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding="utf-8")
    receipt["path"] = str(path)
    return receipt


def latest_receipt(day: str | None = None, out_dir: Path | None = None) -> dict | None:
    """Today's newest morning receipt, or None. Reads; never runs anything."""
    out_dir = out_dir or MORNING_DIR
    if not out_dir.is_dir():
        return None
    day = day or str(datetime.now(timezone.utc).date())
    files = sorted(p for p in out_dir.glob(f"{day}_run*.json")
                   if re.fullmatch(rf"{re.escape(day)}_run\d+\.json", p.name))
    if not files:
        return None
    try:
        blob = json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    blob["path"] = str(files[-1])
    return blob
