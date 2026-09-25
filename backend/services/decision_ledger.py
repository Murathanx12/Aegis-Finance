"""THE DECISION LEDGER — did anyone SEE this before the window closed?

WHY A THIRD FILE AND NOT A THIRD LEDGER
=======================================
`predictions.jsonl` records what we BELIEVED and grades it. It does not record
what happened to a decision on its way to an executor, and nothing in either
repo did: the audit's §4.2 item 2 found no record anywhere of "the row was
written, and then nobody read it." That is the failure a decision that never
reaches a human looks like from the outside — identical to a day on which the
engine found nothing.

So this is an append-only JSONL beside the prediction ledger, with the SAME
durability pattern and the SAME two-population field
(`evidence_population.EvidencePopulation`) the 2026-08-15 adjudication
established — reused rather than reinvented, because a third ledger shape is a
third thing to get wrong and the whole reason that field exists is that two
populations were once confused for one.

THE STATES, AND WHO WRITES THEM
===============================
``DECIDED -> DELIVERED -> SEEN_BY_EXECUTOR -> REFUSED | ORDER_SUBMITTED ->
REVISED -> FILLED -> SCORED``

* ``DECIDED`` — the morning wrote the row (`decision_contract`).
* ``DELIVERED`` — a surface returned it to a caller.
* ``SEEN_BY_EXECUTOR`` — a chat surface actually RETRIEVED the row and put it in
  front of a reader (`ask_tools.tool_decisions`, `copilot.get_todays_decisions`).
* ``REFUSED`` — the row was declined. In this repo that is the contract's own
  REFUSED direction; in the execution repo it is a gate.
* ``ORDER_SUBMITTED`` / ``FILLED`` — **written by the execution artery, not by
  this repo.** Nothing in `aegis-finance` places an order. They are in the enum
  because a stored row must be written against the whole lifecycle: a ledger
  that grew a state later is a ledger whose old rows silently mean something
  else. When the artery lands (a terminal chunk) it POSTs them through the same
  hash-verified path `seal_authority.py` already uses — never a shared
  filesystem.
* ``REVISED`` — a re-run of the SAME ranking over the SAME capital level
  superseded this row (`decision_contract.revise`). Written on the PARENT, in
  the same call that writes ``DECIDED`` on the child; the child carries
  ``parent_decision_id``. The parent row on disk is never edited — it must stay
  gradeable exactly as it was decided, and a mutated row would be a silently
  rewritten one, which is the worse failure.
* ``SCORED`` — the grader joined the row's own expiry to realised close-to-close
  returns.

ORDER IS ENFORCED, AND THE ENFORCEMENT CAN GO GREEN
===================================================
The rule is monotone-in-rank with `DECIDED` first, **not** "every predecessor
must exist". A strict-predecessor rule would make `SCORED` unreachable in this
repo forever, because nothing here can ever write `FILLED` — and a gate that
cannot go green is a broken gate, not a strict one (CLAUDE.md). So a decision
that was written and never delivered is still gradeable, and `FILLED` before
`DECIDED` is refused BY NAME.

`REFUSED` and `ORDER_SUBMITTED` are siblings at one rank and mutually
exclusive: a decision cannot both have been declined and have become an order.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from backend import config
from backend.services.decision_contract import DECISION_STATES, DECISIONS_DIR

logger = logging.getLogger(__name__)


class DecisionLedgerError(ValueError):
    """A state that cannot follow what the ledger already holds.

    A refusal, not a silent drop: a lifecycle row written out of order is
    evidence that two writers disagree about what happened, and appending it
    anyway would make the disagreement invisible in exactly the file built to
    show it.
    """


LEDGER = DECISIONS_DIR / "ledger.jsonl"

STATES: tuple[str, ...] = DECISION_STATES

#: Rank, not a chain. `REFUSED` and `ORDER_SUBMITTED` share rank 3 because they
#: are alternatives at the same point in the life of a decision.
#:
#: `REVISED` is 3.5 — after the row could have been declined or sent, before it
#: could have been filled or scored. The ranks are floats for exactly this: a
#: renumbering (3 -> 4, 4 -> 5 ...) would change what every stored row's
#: neighbours are, and the ledger's ordering is read by comparing ranks, not by
#: their absolute values. A half step inserts a state without moving any other.
RANK: dict[str, float] = {
    "DECIDED": 0,
    "DELIVERED": 1,
    "SEEN_BY_EXECUTOR": 2,
    "REFUSED": 3,
    "ORDER_SUBMITTED": 3,
    "REVISED": 3.5,
    "FILLED": 4,
    "SCORED": 5,
}
assert set(RANK) == set(STATES), "every declared state needs a rank"

#: The two states no code in THIS repository may write. Enforced rather than
#: documented: a research process that could stamp `FILLED` could make a paper
#: fill look like a real one in the only file that records the difference.
EXECUTION_ARTERY_STATES: frozenset[str] = frozenset({"ORDER_SUBMITTED", "FILLED"})

_SIBLINGS: dict[str, str] = {"REFUSED": "ORDER_SUBMITTED",
                             "ORDER_SUBMITTED": "REFUSED"}

#: Chunk 2 (2026-09-25): the expected-return decomposition every decision row
#: carries (`expected_return.row_fields`), so `decision_autopsy` can say WHICH
#: component was wrong. Written on DECIDED by the planner and COPIED onto
#: SCORED by the grader, beside the realised excess return -- the join the
#: blend's own forward grade and every component's reputation are fit on.
ER_ROW_FIELDS: tuple[str, ...] = ("er_total", "er_equal", "er_by_component", "weights",
                                  "weights_source", "components_awake", "regime",
                                  "er_horizon")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ledger_path(path: Path | None = None) -> Path:
    return Path(path) if path is not None else LEDGER


def read(path: Path | None = None) -> list[dict]:
    """Every row, oldest first. A malformed line is SKIPPED and counted in the
    log — an append-only file that one bad write makes unreadable is not
    durable, and refusing to read it would hide every good row behind one."""
    p = ledger_path(path)
    if not p.is_file():
        return []
    out: list[dict] = []
    bad = 0
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(row, dict):
            out.append(row)
    if bad:
        logger.warning("decision ledger: %d unparseable line(s) in %s", bad, p)
    return out


def states_of(decision_id: str, *, rows: Iterable[dict] | None = None,
              path: Path | None = None) -> list[str]:
    rows = rows if rows is not None else read(path)
    return [str(r.get("state")) for r in rows
            if str(r.get("decision_id")) == str(decision_id)]


def _population() -> str:
    """Which body of forward evidence these rows belong to.

    The same field, spelled the same way, as `belief_state`'s records. A
    decision written on a developer machine belongs to the campaign, because
    the live product ledger genuinely does not exist here — the 2026-08-15
    adjudication's answer, reused rather than re-argued.
    """
    try:
        from backend.services.evidence_population import EvidencePopulation
        return EvidencePopulation.CAMPAIGN_FORWARD.value
    except Exception:                                              # noqa: BLE001
        return "campaign_forward"


def record(decision_id: str, state: str, *, by: str, detail: Any = None,
           asof: str | date | None = None, path: Path | None = None,
           allow_execution_states: bool = False) -> dict:
    """Append one lifecycle row. Idempotent per `(decision_id, state)`.

    A repeat is NOT an error and NOT a second row: two surfaces retrieving the
    same decision on the same day is the normal case, and a ledger that counted
    it twice would report engagement it did not have. The returned row carries
    `duplicate: True` so a caller can tell which it got.
    """
    did = str(decision_id or "").strip()
    st = str(state or "").strip().upper()
    if not did:
        raise DecisionLedgerError(
            "a lifecycle row needs a decision_id; an empty id would make the "
            "row unjoinable to the contract it is about")
    if st not in RANK:
        raise DecisionLedgerError(
            f"{st!r} is not a declared decision state. The closed set is "
            f"{list(STATES)} — a state that is not in it cannot be written, "
            f"because a reader of this file must be able to enumerate the "
            f"lifecycle without reading every row.")
    if st in EXECUTION_ARTERY_STATES and not allow_execution_states:
        raise DecisionLedgerError(
            f"{st} is written by the EXECUTION artery (aegis-alpha-terminal), "
            f"not by this repository: nothing in aegis-finance places an order, "
            f"so a row stamped {st} here would be a paper fill wearing a real "
            f"one's clothes.")

    rows = read(path)
    mine = [r for r in rows if str(r.get("decision_id")) == did]
    existing = [r for r in mine if str(r.get("state")) == st]
    if existing:
        out = dict(existing[0])
        out["duplicate"] = True
        return out

    seen = {str(r.get("state")) for r in mine}
    if not mine and st != "DECIDED":
        raise DecisionLedgerError(
            f"{st} before DECIDED for {did}: this ledger has never heard of that "
            f"decision, so there is nothing for {st} to be about. A lifecycle "
            f"row that arrives before the decision it describes is evidence of "
            f"two writers disagreeing, not of an event.")
    sibling = _SIBLINGS.get(st)
    if sibling and sibling in seen:
        raise DecisionLedgerError(
            f"{did} already carries {sibling}; {st} is its alternative at the "
            f"same point in the lifecycle and a decision cannot be both.")
    if mine:
        high = max(RANK[s] for s in seen if s in RANK)
        if RANK[st] <= high:
            current = sorted(seen, key=lambda s: RANK.get(s, 99))
            raise DecisionLedgerError(
                f"{st} (rank {RANK[st]}) cannot follow {current[-1]} "
                f"(rank {high}) for {did}: the lifecycle only moves forward, and "
                f"a row that walks it backwards would make the ledger's own "
                f"ordering unreadable.")

    row = {
        "utc": _now(),
        "decision_id": did,
        "state": st,
        "by": str(by),
        "detail": detail,
        "asof": str(asof) if asof is not None else None,
        "evidence_population": _population(),
        "ledger_version": "decision-ledger-1.0.0",
    }
    p = ledger_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def record_many(decision_ids: Iterable[str], state: str, *, by: str,
                detail: Any = None, asof: str | date | None = None,
                path: Path | None = None) -> dict:
    """Best-effort fan-out for a surface that just delivered N rows.

    A refusal on one id must NOT stop the other N-1 from being recorded: the
    ledger is a record of what a surface did, and half a record beats none. The
    refusals come back by name in `refused` so nothing is swallowed.
    """
    written, duplicate, refused = 0, 0, []
    for did in decision_ids:
        try:
            row = record(did, state, by=by, detail=detail, asof=asof, path=path)
        except DecisionLedgerError as exc:
            refused.append({"decision_id": str(did), "reason": str(exc)})
            continue
        if row.get("duplicate"):
            duplicate += 1
        else:
            written += 1
    return {"state": str(state).upper(), "by": by, "written": written,
            "duplicate": duplicate, "refused": refused}


def deliver(decision_ids: Iterable[str], *, by: str,
            asof: str | date | None = None, detail: Any = None,
            path: Path | None = None) -> dict:
    """A surface just put these rows in front of a reader: DELIVERED + SEEN.

    It BACKFILLS `DECIDED` when the ledger has never heard of the row. That is
    not a loosening of the order rule: the contract FILE is the evidence that
    the decision was made, and a ledger that refused to record a delivery
    because its own first row was missing would lose the one event this file
    exists for — while leaving the contract on disk saying the opposite. The
    backfilled row says `by="contract_file"` so it is never mistaken for a
    morning that ran.
    """
    ids = [str(d) for d in decision_ids if str(d or "").strip()]
    backfilled = 0
    for did in ids:
        if not states_of(did, path=path):
            record(did, "DECIDED", by="contract_file", asof=asof, path=path,
                   detail={"backfilled": True,
                           "why": ("the contract file carries this row and the "
                                   "ledger did not; the file is the evidence "
                                   "the decision was made")})
            backfilled += 1
    out_d = record_many(ids, "DELIVERED", by=by, detail=detail, asof=asof,
                        path=path)
    out_s = record_many(ids, "SEEN_BY_EXECUTOR", by=by, detail=detail,
                        asof=asof, path=path)
    return {"by": by, "n": len(ids), "backfilled_decided": backfilled,
            "delivered": out_d, "seen": out_s}


def summary(asof: str | date | None = None, *, path: Path | None = None) -> dict:
    """State counts for one day — the board's row.

    `asof` is the CONTRACT's date, not the row's write time: a decision written
    on Friday and seen on Monday belongs to Friday's contract, and counting it
    on Monday would make the delivery rate of every Friday look like zero.
    """
    rows = read(path)
    day = str(asof) if asof is not None else None
    if day is not None:
        rows = [r for r in rows if str(r.get("asof") or "") == day]
    counts = {s: 0 for s in STATES}
    ids: set[str] = set()
    for r in rows:
        st = str(r.get("state"))
        if st in counts:
            counts[st] += 1
        ids.add(str(r.get("decision_id")))
    return {
        "date": day,
        "n_rows": len(rows),
        "n_decisions": len(ids),
        "count_by_state": counts,
        "states_declared": list(STATES),
        "execution_artery_states": sorted(EXECUTION_ARTERY_STATES),
        "note": ("ORDER_SUBMITTED and FILLED are written by the execution repo's "
                 "artery, never by this one, so a zero there is the expected "
                 "reading and not a gap in the record."),
    }


# ===========================================================================
# THE GRADER — SCORED, from close-to-close returns
# ===========================================================================


def default_price_fetch(tickers: list[str], start: str, end: str):
    """The SAME fetch the ledger resolver and `decision_vs_reality` grade on.

    Named as a module-level indirection so the fast suite replaces the call
    rather than the network: this is the only function in either new module
    that can reach outside the process, and `test_decision_ledger.py` passes a
    fake.
    """
    from backend.services.ledger_resolver import _default_price_fetch
    return _default_price_fetch(tickers, start, end)


def _close_to_close(frame, ticker: str, start: str, end: str) -> tuple[float | None, str]:
    """(return, basis). None when the frame cannot price both ends BY NAME."""
    try:
        col = frame[ticker]
    except Exception:                                              # noqa: BLE001
        return None, f"CANNOT DETERMINE: {ticker} is not a column of the price frame"
    try:
        series = col.dropna()
    except AttributeError:
        return None, "CANNOT DETERMINE: the price frame is not a pandas object"
    if len(series) < 2:
        return None, (f"CANNOT DETERMINE: {ticker} has {len(series)} priced "
                      f"session(s) between {start} and {end}; a close-to-close "
                      f"return needs two")
    first, last = float(series.iloc[0]), float(series.iloc[-1])
    if first == 0:
        return None, f"CANNOT DETERMINE: {ticker}'s first close is zero"
    return (last / first) - 1.0, (
        f"close-to-close {series.index[0]} -> {series.index[-1]} "
        f"({len(series)} sessions)")


def score_due(*, today: date | None = None, contracts: list[dict] | None = None,
              price_fetch: Callable[..., Any] | None = None,
              path: Path | None = None, out_dir: Path | None = None) -> dict:
    """Write `SCORED` for every decision whose own expiry has passed.

    The horizon is the ROW's (`expiry_utc`, derived from its falsifier's window
    or its policy horizon), never a horizon chosen at grading time — a window
    picked after the outcome is known is the failure this programme is built
    against. A row that cannot be priced is `unpriceable` BY NAME and stays
    open; it is never dropped and never graded at zero.
    """
    day = today or datetime.now(timezone.utc).date()
    fetch = price_fetch or default_price_fetch
    rows = contracts if contracts is not None else _open_contract_rows(
        day=day, out_dir=out_dir, path=path)

    due, unpriceable, scored = [], [], []
    for r in rows:
        expiry = r.get("expiry_utc")
        if not expiry:
            unpriceable.append({"decision_id": r.get("decision_id"),
                                "reason": r.get("expiry_basis") or
                                "CANNOT DETERMINE: the row carries no expiry"})
            continue
        try:
            when = datetime.fromisoformat(str(expiry)).date()
        except ValueError:
            unpriceable.append({"decision_id": r.get("decision_id"),
                                "reason": f"unparseable expiry {expiry!r}"})
            continue
        if when > day:
            continue
        due.append((r, when))

    if not due:
        return {"status": "nothing_to_do", "as_of": str(day), "due": 0,
                "newly_scored": 0, "unpriceable": unpriceable,
                "reason": "no decision's own expiry had passed by today"}

    tickers = sorted({str(r.get("ticker")) for r, _ in due
                      if r.get("source") == "investment_committee"})
    # The benchmark is REQUESTED with the names (chunk 23a, §16.5 item 37: an
    # internal figure is quoted beside the external one when one exists). A raw
    # close-to-close return is mostly the market; a panel built on raw returns
    # measures beta and calls it a mechanism. If the fetch comes back without
    # it, the two benchmark fields are present and None with the reason — never
    # a zero, which would read as "the market did nothing".
    benchmark = str(config.DECISION_BENCHMARK_SYMBOL)
    start = min(str(r.get("asof")) for r, _ in due)
    frame = None
    if tickers:
        try:
            frame = fetch(sorted(set(tickers) | {benchmark}), start, str(day))
        except Exception as exc:                                   # noqa: BLE001
            return {"status": "refused", "as_of": str(day), "due": len(due),
                    "newly_scored": 0, "unpriceable": unpriceable,
                    "reason": (f"grading needs prices and the fetch failed: "
                               f"{type(exc).__name__}: {exc}. The due rows stay "
                               f"open rather than being graded without one.")}

    for r, when in due:
        ticker = str(r.get("ticker"))
        if frame is None or r.get("source") != "investment_committee":
            unpriceable.append({"decision_id": r.get("decision_id"),
                                "reason": ("CANNOT DETERMINE: an agency BOOK row "
                                           "is priced by its own NAV, not by a "
                                           "ticker close")})
            continue
        ret, basis = _close_to_close(frame, ticker, str(r.get("asof")), str(when))
        if ret is None:
            unpriceable.append({"decision_id": r.get("decision_id"),
                                "reason": basis})
            continue
        bench_ret, bench_basis = _close_to_close(
            frame, benchmark, str(r.get("asof")), str(when))
        excess = None if bench_ret is None else ret - bench_ret
        detail = {"ticker": ticker, "realised_return": ret, "basis": basis,
                  "direction": r.get("direction"), "expiry_utc": r.get("expiry_utc"),
                  "artifact_sha256": r.get("artifact_sha256"),
                  "benchmark_symbol": benchmark,
                  "benchmark_return": bench_ret,
                  "excess_return": excess,
                  "benchmark_basis": (
                      bench_basis if bench_ret is not None else
                      f"CANNOT DETERMINE: {bench_basis}. The raw return stands "
                      f"and the excess is null — never zero, which would read "
                      f"as 'the market did nothing'")}
        # chunk 23a: what the PROBE panel joins on. Carried on the LEDGER row
        # and not only on the contract row, because the panel reads the ledger
        # and a join that needed both files would break the day a contract file
        # is rotated out of the year the grader scans.
        for key in ("hypothesis_id", "shortlist_hypothesis_id", "horizon_sessions", "virtual",
                    "selection_probability", "action_set_sha256"):
            if r.get(key) is not None:
                detail[key] = r.get(key)
        for key in ER_ROW_FIELDS:
            if key in r:
                detail[key] = r.get(key)
        try:
            record(str(r.get("decision_id")), "SCORED", by="decision_grader",
                   detail=detail, asof=r.get("asof"), path=path)
        except DecisionLedgerError as exc:
            unpriceable.append({"decision_id": r.get("decision_id"),
                                "reason": str(exc)})
            continue
        scored.append(detail)

    return {"status": "ok" if scored else "nothing_to_do", "as_of": str(day),
            "due": len(due), "newly_scored": len(scored), "scored": scored,
            "unpriceable": unpriceable}


def _open_contract_rows(*, day: date, out_dir: Path | None,
                        path: Path | None) -> list[dict]:
    """Every contract row from the last year that is not already SCORED.

    A year, not "all of them": the files are per-day and a grader that re-read
    five years of them every morning would spend its budget on rows whose
    windows closed long ago and are already in the ledger.
    """
    from backend.services import decision_contract as DC

    folder = Path(out_dir or DC.DECISIONS_DIR)
    if not folder.is_dir():
        return []
    already = {str(r.get("decision_id")) for r in read(path)
               if str(r.get("state")) == "SCORED"}
    floor = day - timedelta(days=366)
    rows: list[dict] = []
    # `pc_plan/` holds `sim_run.u_plan`'s PROBE rows (chunk C3, 2026-09-25):
    # the same row shape in a subfolder, because the top-level files are
    # written whole by `decision_contract` and a second writer's rows appended
    # there would be lost on its next run.
    files = sorted(folder.glob("*.json")) + sorted((folder / "pc_plan").glob("*.json"))
    for p in files:
        try:
            stamp = date.fromisoformat(p.stem)
        except ValueError:
            continue
        if stamp < floor:
            continue
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in blob.get("rows") or []:
            # PROBE joined BUY and WATCH here on 2026-09-21 (chunk 23a). A
            # virtual row that was written and never graded is a row that
            # bought nothing and taught nothing, and the whole point of the
            # state is that it is graded exactly like the rest.
            if r.get("direction") in ("BUY", "WATCH", "PROBE") and \
                    str(r.get("decision_id")) not in already:
                rows.append(r)
    return rows


__all__ = ["DecisionLedgerError", "ER_ROW_FIELDS", "EXECUTION_ARTERY_STATES", "LEDGER", "RANK",
           "STATES", "default_price_fetch", "deliver", "ledger_path", "read",
           "record", "record_many", "score_due", "states_of", "summary"]
