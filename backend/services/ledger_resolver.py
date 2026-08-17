"""The caller resolve_one/resolve_all never had.

WHY THIS FILE EXISTS
====================
`belief_state.py` shipped a complete resolution machine — and for a month
NOTHING called it. No scheduler job, no route, no script. Records would have
sailed past `resolves_after` forever while the calibration clock read "still
accruing". That is the house failure mode (code that runs green and silently
does nothing), so this entry point is built to make skipping LOUD:

* every due record is accounted for in the returned report — resolved, still
  pending, overdue, or UNPRICEABLE, never absent;
* a ticker the resolver cannot price is surfaced by name with the number of
  records it strands, and leaves the ledger canary DEGRADED (overdue keeps
  growing) rather than quietly shrinking the denominator;
* the report ends with `ledger_health()` so the caller sees the same status
  row the /api/health/full canary pages on.

PRICE PANEL
-----------
The frozen conviction CSV (`backend/data/conviction_prices.csv`) is used only
when it actually covers made_at → today for every needed ticker — it is a
replay artifact that ends where the replay ended, and this module NEVER
mutates it. When it does not suffice, fresh adjusted closes are fetched via
yfinance (auto_adjust=True, the same convention as
scripts/fetch_conviction_prices.py), with the frozen CSV as a per-ticker
fallback for anything the fetch fails to return.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

from backend.config import (LEDGER_RESOLVER_CSV_GRACE_DAYS,
                            LEDGER_RESOLVER_FETCH_BATCH,
                            LEDGER_RESOLVER_FETCH_PAD_DAYS)
from backend.services.belief_state import (Observable, ledger_health,
                                           read_predictions, resolve_all)

logger = logging.getLogger(__name__)

#: price_fetch contract: (tickers, start_iso, end_iso) -> wide DataFrame of
#: adjusted closes (DatetimeIndex, one column per ticker; missing tickers may
#: simply be absent — the caller accounts for them).
PriceFetch = Callable[[list[str], str, str], pd.DataFrame]


def _default_price_fetch(tickers: list[str], start: str, end: str,
                         *, batch: int = LEDGER_RESOLVER_FETCH_BATCH) -> pd.DataFrame:
    """Live yfinance fetch, same convention as fetch_conviction_prices.py.

    CHUNKED, and the reason is a change in scale rather than taste. This used
    to be one request for every ticker with a due record, which was correct
    when the ledger held ~100 records over a dozen names. LLM-SWARM-1 put
    hundreds of securities in the ledger in one night, and a single 460-symbol
    request against a 30-second timeout fails as a UNIT: one slow symbol and
    the whole panel comes back empty, every due record becomes unpriceable, and
    the ledger canary goes DEGRADED on a problem that is not in the ledger.

    Chunking makes the failure PROPORTIONAL — a bad chunk strands its own
    names, which `resolve_due` already counts and names — instead of total. A
    chunk that raises is logged and skipped rather than taking the other
    chunks' prices down with it; its tickers are simply absent from the panel,
    which is exactly the contract this callable already declares.
    """
    import yfinance as yf
    frames: list[pd.DataFrame] = []
    ordered = list(tickers)
    for i in range(0, len(ordered), max(1, batch)):
        chunk = ordered[i:i + batch]
        try:
            df = yf.download(chunk, start=start, end=end, auto_adjust=True,
                             progress=False, timeout=30)["Close"]
        except Exception as e:                                # noqa: BLE001
            logger.error("ledger resolver: price chunk %d-%d (%d tickers) "
                         "failed (%s) — those names are absent from the panel "
                         "and will be reported UNPRICEABLE, the rest are "
                         "unaffected", i, i + len(chunk), len(chunk), e)
            continue
        if isinstance(df, pd.Series):  # single ticker collapses to a Series
            df = df.to_frame(name=chunk[0])
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, axis=1).sort_index()
    return out.loc[:, ~out.columns.duplicated()]


def _load_frozen_csv() -> pd.DataFrame | None:
    """The conviction replay panel, read-only. None if missing/unreadable."""
    try:
        from backend.services.conviction_prices import load_prices
        return load_prices()
    except Exception as e:
        logger.warning("frozen conviction CSV unavailable (%s) — resolver will "
                       "rely on the live fetch alone", e)
        return None


def _needed_tickers(records: list[dict]) -> set[str]:
    """Every column a record needs to resolve: its ticker AND its benchmark."""
    need: set[str] = set()
    for r in records:
        need.add(r["ticker"])
        if r.get("observable") == Observable.BEATS_BENCHMARK.value and r.get("benchmark"):
            need.add(r["benchmark"])
    return need


def _usable(panel: pd.DataFrame | None, ticker: str) -> bool:
    """A column exists and has at least one real price in it."""
    if panel is None or ticker not in panel.columns:
        return False
    return int(pd.to_numeric(panel[ticker], errors="coerce").notna().sum()) > 0


def assert_single_population(path: Path, population: str) -> dict:
    """Refuse to resolve a ledger that holds more than one evidence population.

    `resolve_all` rewrites the whole file, so resolving a mixed ledger would
    grade the other population's records as a side effect of grading this one.
    There is no rule that licenses that and there is no way to undo it, so the
    resolver stops instead. This is the code half of the two-ledger ruling: the
    campaign resolver never writes the volume, the production resolver never
    reads the repo ledger.
    """
    from backend.services import evidence_population as EP
    want = EP.parse(population)
    EP.assert_write_allowed(want, path)
    found: dict[str, int] = {}
    for r in EP._read_jsonl(Path(path)):
        try:
            p = EP.population_of(r, path=path).value
        except EP.PopulationRequired:
            p = "unattributable"
        found[p] = found.get(p, 0) + 1
    foreign = {k: v for k, v in found.items() if k != want.value}
    if foreign:
        raise EP.PopulationCrossWrite(
            f"{path} holds {foreign} alongside {found.get(want.value, 0)} "
            f"{want.value} record(s). Resolution rewrites the whole file, so "
            f"grading this population would grade the other one too. Refusing.")
    return found


def resolve_due(path: Path | None = None, *,
                price_fetch: PriceFetch | None = None,
                today: date | None = None,
                population: str | None = None) -> dict:
    """Resolve every ledger record whose window has closed, loudly.

    Returns the full accounting: {as_of, due, newly_resolved, pending, overdue,
    unpriceable, priced_from, resolve_report, health}. An unpriceable due
    record is COUNTED AND NAMED, never silently skipped — it stays overdue and
    keeps the health canary DEGRADED until someone prices it or voids it.

    `population`, when named, pins WHICH forward ledger this run may touch and
    refuses everything else. Callers that pass a bare `path` (tests, one-off
    tools) are unaffected and unattributed, exactly as before.
    """
    today = today or date.today()
    lineage = None
    skip_hashes: frozenset = frozenset()
    comparison_available = True
    if population is not None:
        from backend.services import evidence_population as EP
        pop = EP.parse(population)
        path = path or EP.ledger_path(pop)
        assert_single_population(path, population)
        lineage = EP.lineage(pop, path)

        # AN UNESTABLISHED POPULATION IS NOT RESOLVED, IT IS REFUSED.
        #
        # Adjudicated 2026-08-15: every record on the LIVE_FORWARD volume is
        # content-identical to a CAMPAIGN_FORWARD record — a partial copy of
        # campaign history that reached the volume before the migration guard
        # existed. Their `resolves_after` dates begin 2026-08-16, with 25 due
        # that month, so this nightly job was four days away from grading
        # campaign swarm rows into the live product's ledger, automatically and
        # unattended, and every surface reading "the deployed product's forward
        # record" would then have been reading the swarm.
        #
        # Resolving them is not a small error that could be corrected later: an
        # outcome written onto a record is the thing that makes it evidence.
        # See docs/LEDGER_DIVERGENCE_ADJUDICATION_2026-08-15.md.
        if pop is EP.EvidencePopulation.LIVE_FORWARD:
            est = EP.live_forward_is_established(path=path)
            # RECORD-LEVEL, NOT POPULATION-LEVEL.
            #
            # The refusal below is correct but it is not sufficient, because its
            # condition (`not established`) is released by the arrival of ONE
            # unrelated record: 112 copies + 1 genuine forecast ⇒ established,
            # and `resolve_all` rewrites the whole file, so all 112 copies get
            # graded into the live product's forward record on the next tick.
            # Reproduced 2026-08-17. So the copies are excluded BY CONTENT here
            # and stay excluded after the population becomes established.
            skip_hashes = est.get("quarantined_hashes") or frozenset()
            comparison_available = est.get("comparison_available") is not False
            if est["n_records"] and not est["established"] and comparison_available:
                logger.error("ledger resolve REFUSED for %s: %s",
                             pop.value, est["reason"])
                return {
                    "as_of": str(today), "status": "REFUSED",
                    "reason": est["reason"],
                    "due": 0, "newly_resolved": 0,
                    "pending": est["n_records"], "overdue": 0,
                    "unpriceable": [], "priced_from": None,
                    "resolve_report": None,
                    "health": {"status": "DEGRADED",
                               "problems": ["live_forward population "
                                            "unestablished — resolution "
                                            "refused, nothing was graded"]},
                    "lineage": lineage,
                    "quarantine": {
                        "n_quarantined": len(skip_hashes),
                        "reason": "whole population is campaign copies",
                    },
                }
    rows = read_predictions(path)
    if skip_hashes:
        from backend.services.evidence_population import record_hash
        quarantined = [r for r in rows if record_hash(r) in skip_hashes]
        rows_gradeable = [r for r in rows if record_hash(r) not in skip_hashes]
    else:
        quarantined, rows_gradeable = [], rows
    # `active`/`due` drive the PRICE PANEL as well as the report, so quarantined
    # records are removed here rather than only at grading time: otherwise their
    # tickers get fetched nightly forever and every one of them lands in
    # `unpriceable`, which would read as a resolver fault rather than as a
    # deliberate quarantine awaiting attended disposition.
    active = [r for r in rows_gradeable
              if r.get("outcome") is None and not r.get("void_reason")]
    due = [r for r in active
           if today >= date.fromisoformat(r["resolves_after"][:10])]
    quarantined_overdue = [
        r for r in quarantined
        if r.get("outcome") is None and not r.get("void_reason")
        and today >= date.fromisoformat(r["resolves_after"][:10])]
    quarantine_note = {
        "n_quarantined": len(quarantined),
        "n_quarantined_overdue": len(quarantined_overdue),
        "prediction_ids": [r.get("prediction_id") for r in quarantined][:20],
        "reason": ("content-identical to CAMPAIGN_FORWARD records — never "
                   "graded on the live volume, whatever else this file holds. "
                   "Disposition is attended (Murat), not a session's: see "
                   "docs/LEDGER_DIVERGENCE_ADJUDICATION_2026-08-15.md"),
    } if quarantined else None
    if quarantined:
        logger.warning("ledger resolver: %d record(s) QUARANTINED (%d of them "
                       "past due) and excluded from grading — campaign copies "
                       "on the live volume, awaiting attended disposition",
                       len(quarantined), len(quarantined_overdue))

    # THE GUARD BINDS WHERE THE IRREVERSIBLE ACT IS, AND ONLY THERE.
    #
    # If the campaign ledger cannot be read, we cannot tell a copy from a genuine
    # record — so grading anything here risks writing outcomes onto the campaign's
    # rows, which cannot be undone. But a ledger with nothing due is in no danger,
    # and refusing there would strand a clean live ledger on any machine that has
    # no campaign artifact. So the refusal is conditioned on there being something
    # to grade, which is derived from the records rather than declared.
    if due and not comparison_available:
        logger.error("ledger resolve REFUSED: %d record(s) are due but the "
                     "campaign ledger is unreadable, so a copy cannot be told "
                     "from a genuine record", len(due))
        return {
            "as_of": str(today), "status": "REFUSED",
            "reason": (f"{len(due)} record(s) are due, but the campaign ledger "
                       f"is missing or empty so the quarantine cannot be "
                       f"computed. Absence of the comparison set is not "
                       f"evidence these records are the product's own — "
                       f"nothing was graded."),
            "due": len(due), "newly_resolved": 0,
            "pending": len(active), "overdue": 0,
            "unpriceable": [], "priced_from": None,
            "resolve_report": None,
            "quarantine": {"n_quarantined": 0,
                           "reason": "UNCOMPUTABLE — campaign ledger unreadable"},
            "health": {"status": "DEGRADED",
                       "problems": ["quarantine uncomputable — resolution "
                                    "refused, nothing was graded"]},
            "lineage": lineage,
        }

    if not due:
        # Nothing has matured: no price panel is needed, and fetching one
        # anyway would burn quota nightly for months. The report still carries
        # the full accounting so "nothing to do" is a statement, not silence.
        health = ledger_health(path, today=today,
                               quarantined_hashes=skip_hashes)
        return {
            "as_of": str(today),
            "due": 0,
            "newly_resolved": 0,
            "pending": len(active),
            "overdue": 0,
            "unpriceable": [],
            "quarantine": quarantine_note,
            "priced_from": None,
            "resolve_report": None,
            "health": health,
            "lineage": lineage,
        }

    need = _needed_tickers(due)
    start = (min(date.fromisoformat(r["made_at"][:10]) for r in due)
             - timedelta(days=LEDGER_RESOLVER_FETCH_PAD_DAYS))
    csv_panel = _load_frozen_csv()

    csv_covers = (
        csv_panel is not None
        and need.issubset(set(csv_panel.columns))
        and csv_panel.index.min().date() <= start + timedelta(
            days=LEDGER_RESOLVER_FETCH_PAD_DAYS)
        and csv_panel.index.max().date() >= today - timedelta(
            days=LEDGER_RESOLVER_CSV_GRACE_DAYS)
    )

    if csv_covers:
        panel, priced_from = csv_panel[sorted(need)].copy(), "frozen_csv"
    else:
        priced_from = "fresh_fetch"
        fetch = price_fetch or _default_price_fetch
        try:
            panel = fetch(sorted(need), str(start), str(today + timedelta(days=1)))
        except Exception as e:
            logger.error("ledger resolver: fresh price fetch failed outright "
                         "(%s) — falling back to the frozen CSV", e, exc_info=True)
            panel = pd.DataFrame()
            priced_from = "frozen_csv_fallback_after_fetch_error"
        # Per-ticker fallback: anything the fetch did not return is taken from
        # the frozen CSV when the CSV has it AND its bars actually reach back
        # to the earliest due made_at. A column that starts mid-window would
        # not refuse — resolve_one slices .loc[start:] and would happily grade
        # a benchmark on the wrong window — so partial coverage is rejected
        # here, loudly, and the record lands in `unpriceable` instead.
        if csv_panel is not None:
            earliest_made_at = start + timedelta(days=LEDGER_RESOLVER_FETCH_PAD_DAYS)
            # A fallback column must cover BOTH ends of the due window: bars
            # reaching back to the earliest made_at AND forward to the latest
            # due resolves_after. The frozen CSV ends at its build date, so a
            # ticker graded from it beside a fresh-fetched counterpart would
            # otherwise pair a full-horizon leg with a truncated one — the
            # belief_state window guard refuses to grade that, but refusing
            # HERE names the ticker in `unpriceable` instead of leaving the
            # record silently pending forever.
            latest_due = max(date.fromisoformat(r["resolves_after"][:10])
                             for r in due)
            fallback_cols = []
            for t in sorted(need):
                if _usable(panel, t) or not _usable(csv_panel, t):
                    continue
                bars = pd.to_numeric(csv_panel[t], errors="coerce").dropna()
                first_bar = bars.index.min().date()
                last_bar = bars.index.max().date()
                if first_bar <= earliest_made_at and last_bar >= latest_due:
                    fallback_cols.append(t)
                else:
                    logger.warning(
                        "ledger resolver: frozen CSV covers %s only %s..%s but "
                        "the due windows span %s..%s — NOT used (a partial "
                        "series would grade the wrong window)",
                        t, first_bar, last_bar, earliest_made_at, latest_due)
            if fallback_cols:
                panel = panel.drop(
                    columns=[c for c in fallback_cols if c in panel.columns])
                panel = pd.concat([panel, csv_panel[fallback_cols]], axis=1)
                for t in fallback_cols:
                    logger.warning("ledger resolver: %s priced from the frozen "
                                   "CSV (live fetch returned nothing)", t)
        panel = panel.sort_index()

    # ── the loud part: who CANNOT be priced ─────────────────────────────────
    dark = sorted(t for t in need if not _usable(panel, t))
    unpriceable = []
    for t in dark:
        stranded = [r["prediction_id"] for r in due
                    if r["ticker"] == t or r.get("benchmark") == t]
        unpriceable.append({
            "ticker": t,
            "n_due_records_stranded": len(stranded),
            "prediction_ids": stranded[:20],
            "reason": ("no usable bars from the live fetch and none in the "
                       "frozen CSV — these records stay OVERDUE and keep the "
                       "ledger canary DEGRADED until priced or voided"),
        })
    if unpriceable:
        logger.warning("ledger resolver: %d ticker(s) UNPRICEABLE, stranding "
                       "%d due record(s): %s", len(unpriceable),
                       sum(u["n_due_records_stranded"] for u in unpriceable),
                       [u["ticker"] for u in unpriceable])

    report = resolve_all(panel, path, today=today, skip_hashes=skip_hashes)
    health = ledger_health(path, today=today,
                           quarantined_hashes=skip_hashes)
    return {
        "as_of": str(today),
        "due": len(due),
        "newly_resolved": report["newly_resolved"],
        "pending": report["pending_not_yet_due"],
        "overdue": report["OVERDUE_AND_UNRESOLVED"],
        "unpriceable": unpriceable,
        "quarantine": quarantine_note,
        "priced_from": priced_from,
        "resolve_report": report,
        "health": health,
        "lineage": lineage,
    }
