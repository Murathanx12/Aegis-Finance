"""Forms 3/4/5 → `TeacherEvent`, keeping the sells.

This is the ingestion path Order 5 asks for, and it differs from
`adapters.Form4Adapter` in the two ways that decide what the library can later
be asked:

* **It is driven by the SEC daily index, not by a ticker list**, so the corpus
  is not filtered through the universe we happened to be watching.
* **It keeps every transaction code and both directions.** The existing adapter
  emits `action_type="BUY"` and nothing else, which means a study of insider
  performance run against it would be a study of insider PURCHASES wearing the
  name of a study of insiders. R6: losers get the same machinery as winners.

WHAT IS STATED AND WHAT IS INFERRED
===================================
Everything written here is stated by the filing: who, what security, how many
shares, which transaction code, whether a 10b5-1 plan was checked, whether the
filer is an officer or a director. The library's `why` — "first open-market buy
in four years, stock down 38%, revisions stabilising" — is INFERRED, belongs to
a later layer, and must be labelled as inference there. Keeping the boundary at
a file boundary is the cheapest way to keep it at all.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.services.teacher_library import events as E
from backend.services.teacher_library.events import TeacherEvent, sha256_of

logger = logging.getLogger(__name__)

PARSER_VERSION = "teacher_library/ownership/1.0.0"

#: Transaction code → the library's action vocabulary.
#:
#: Only P and S become BUY/SELL. Everything else is OTHER **on purpose**: a
#: grant, a tax withholding or an option exercise is a compensation mechanic,
#: not a market opinion, and mapping `A` to BUY is how "insiders are buying"
#: charts get built out of payroll. The code itself is preserved on the event,
#: so a later study can regroup them — but it has to do so deliberately.
_ACTION_BY_CODE = {"P": "BUY", "S": "SELL"}


def _action_for(tx: dict) -> str:
    return _ACTION_BY_CODE.get(tx.get("code", ""), "OTHER")


class OwnershipFormsAdapter:
    """One day of Form 3/4/5 filings → events.

    `subject` is a DATE, not a ticker. That is the whole point of this adapter
    and the reason it does not subclass the per-ticker one.
    """

    source_name = "sec_ownership_daily"

    def __init__(self, collect=None):
        from backend.services.sec_daily_index import collect_day
        self._collect = collect or collect_day

    def fetch(self, subject: str, **kw) -> dict:
        return self._collect(subject, **kw)

    def to_events(self, payload: dict) -> list[TeacherEvent]:
        fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
        day = str(payload.get("date", ""))
        status = payload.get("status")

        if status in ("UNAVAILABLE", "REFUSED"):
            return [_status_row(self.source_name, day, E.UNAVAILABLE,
                                str(payload.get("reason", ""))[:200], fetched)]
        if status == "OK_EMPTY":
            return [_status_row(self.source_name, day, E.OK_EMPTY,
                                str(payload.get("reason", ""))[:200], fetched)]

        out: list[TeacherEvent] = []
        for filing in payload.get("parsed") or []:
            out.extend(self._events_for_filing(filing, fetched))
        if not out:
            out.append(_status_row(self.source_name, day, E.OK_EMPTY,
                                   "index_had_filings_but_none_parsed", fetched))
        return out

    def _events_for_filing(self, f: dict, fetched: str) -> list[TeacherEvent]:
        if f.get("status") in ("PARSE_ERROR", "UNAVAILABLE"):
            return [_status_row(self.source_name,
                                f.get("ticker") or f.get("cik", ""),
                                E.PARSE_ERROR if f.get("status") == "PARSE_ERROR"
                                else E.UNAVAILABLE,
                                str(f.get("reason", ""))[:200], fetched)]

        ticker = (f.get("ticker") or "").upper()
        filed = f.get("filed_date") or ""
        owner_cik = str(f.get("owner_cik") or "").strip()
        name = str(f.get("owner_name") or "Unknown").strip()
        accession = f.get("accession", "")

        if owner_cik:
            actor_id, identity_quality = f"cik:{owner_cik}", "cik"
        else:
            # Name strings collide. Recording that here is what lets an
            # actor-history feature later refuse to build on this row.
            actor_id, identity_quality = f"name:{name.lower()}", "name_only"

        rows: list[TeacherEvent] = []
        items = [("tx", t) for t in (f.get("transactions") or [])]
        # Form 3 holdings are not transactions — they are the opening balance
        # every later delta for this actor is measured against. Dropping them
        # would make an actor's first appearance look like their first trade.
        items += [("hold", h) for h in (f.get("holdings") or [])]

        for i, (kind, item) in enumerate(items):
            is_tx = kind == "tx"
            flags: list[str] = []
            if not filed:
                flags.append("no_filing_date")
            if is_tx and not item.get("is_discretionary_market_trade"):
                flags.append("not_a_discretionary_market_trade")
            if is_tx and item.get("rule_10b5_1") is None:
                # Pre-2023 filings carry no explicit element. Flagged rather
                # than defaulted, so a 10b5-1-vs-discretionary study can EXCLUDE
                # the unknowns instead of silently counting them as one side.
                flags.append("rule_10b5_1_unknown")
            if not ticker:
                flags.append("no_trading_symbol_on_filing")
            n_owners = int(f.get("n_reporting_owners") or 1)
            if n_owners > 1:
                # ONE event per transaction, attributed to the LEAD filer, and
                # said so. A jointly-filed Form 4 reports the group's trade
                # once; emitting it once per owner would multiply the share
                # count by the number of co-filers and turn one purchase into
                # an eleven-insider "cluster" that never happened. Attributing
                # it silently to the first name would be the opposite error.
                flags.append(f"joint_filing_lead_filer_of_{n_owners}")

            try:
                rows.append(TeacherEvent(
                    source=self.source_name,
                    source_event_id=f"{accession}:{kind}:{i}",
                    actor_id=actor_id,
                    actor_name=name,
                    actor_type=E.ACTOR_CORPORATE_INSIDER,
                    action_type=_action_for(item) if is_tx else "OTHER",
                    ticker_at_event=ticker,
                    security_id=ticker or f"cik:{f.get('issuer_cik', '')}",
                    issuer_cik=str(f.get("issuer_cik") or "") or None,
                    # THE SIGNAL TIMESTAMP is the FILING date. Section 16 allows
                    # two business days after the trade, and the gap is exactly
                    # what the copyability question turns on.
                    public_at=filed or None,
                    filed_at=filed or None,
                    transaction_at=(item.get("transaction_date") or None
                                    if is_tx else None),
                    shares=item.get("shares") if is_tx
                    else item.get("shares_owned"),
                    reported_price=item.get("price_per_share") if is_tx else None,
                    position_after=(item.get("shares_owned_after") if is_tx
                                    else item.get("shares_owned")),
                    ownership_type=item.get("ownership_type", ""),
                    filing_type=f.get("form_type", ""),
                    insider_role=f.get("officer_title", ""),
                    is_officer=f.get("is_officer"),
                    is_director=f.get("is_director"),
                    is_ten_pct_owner=f.get("is_ten_pct_owner"),
                    rule_10b5_1=item.get("rule_10b5_1") if is_tx else None,
                    status=E.OK_DATA if filed else E.PARSE_ERROR,
                    reason="" if filed else "no_filing_date",
                    source_quality="sec_primary",
                    raw_sha256=sha256_of(item),
                    parser_version=PARSER_VERSION,
                    identity_quality=identity_quality,
                    mapping_quality="ticker_at_event" if ticker else "cik_only",
                    data_quality_flags=flags,
                    fetched_at=fetched,
                ))
            except E.TeacherEventInvalid as exc:
                logger.warning("ownership adapter: refusing a row for %s (%s)",
                               ticker or accession, exc)
                rows.append(_status_row(self.source_name, ticker or accession,
                                        E.PARSE_ERROR, str(exc)[:200], fetched))
        return rows


def _status_row(source: str, subject: str, status: str, reason: str,
                fetched_at: str) -> TeacherEvent:
    """A row that records an ABSENCE with its cause.

    `OK_EMPTY` and `UNAVAILABLE` are never merged. "No insider filed anything
    today" and "EDGAR did not answer" look identical in a count and mean
    opposite things.
    """
    return TeacherEvent(
        source=source,
        source_event_id=f"{source}:{subject}:{status}:{fetched_at}",
        actor_id=f"unresolved:{subject}",
        actor_type=E.ACTOR_CORPORATE_INSIDER,
        action_type="OTHER",
        ticker_at_event=subject.upper()[:12],
        status=status,
        reason=reason,
        fetched_at=fetched_at,
        observed_at=fetched_at,
        parser_version=PARSER_VERSION,
    )


def collect_and_append(day: str, *, path=None, limit: int | None = None,
                       allow_historical: bool = False) -> dict:
    """One forward collection cycle: fetch a day, write its events, receipt it."""
    from backend.services.teacher_library.ledger import append

    adapter = OwnershipFormsAdapter()
    payload = adapter.fetch(day, limit=limit,
                            allow_historical=allow_historical)
    produced = adapter.to_events(payload)
    res = append(produced, path=path)
    res.update({
        "day": day,
        "source_status": payload.get("status"),
        "reason": payload.get("reason", ""),
        "n_index_rows": payload.get("n_index_rows", 0),
        "n_ownership_filings_in_index":
            payload.get("n_ownership_filings_in_index", 0),
        "n_joint_filing_rows_collapsed":
            payload.get("n_joint_filing_rows_collapsed", 0),
        "n_attempted": payload.get("n_attempted", 0),
        "sampled": payload.get("sampled", False),
        "coverage": payload.get("coverage", 0.0),
        "n_parse_errors": payload.get("n_parse_errors", 0),
        "usable_events": sum(1 for e in produced if e.usable),
        "n_buys": sum(1 for e in produced if e.action_type == "BUY"),
        "n_sells": sum(1 for e in produced if e.action_type == "SELL"),
    })
    return res
