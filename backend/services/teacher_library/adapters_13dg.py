"""TEACHER-LIBRARY-1 — SEC Schedule 13D / 13G adapter.

A DISTINCT event family from institutional ownership, and the reason it gets its
own adapter rather than a flag on a 13F one:

  **13D** — a >5% holder declaring intent to influence or control. Since 2023
  the initial filing is due within five business days, a far faster public clock
  than 13F's 45-day quarterly lag.
  **13G** — the passive counterpart: same threshold, no control intent.

Collapsing the two would average an activist's declaration of intent together
with an index fund crossing a threshold mechanically. That is not one signal
measured twice; it is two different things that happen to share a percentage.

THE ACTOR IS THE FILER, NOT THE ISSUER
======================================
The issuer's submissions feed lists the filing but not who filed it, so
resolving the actor costs one extra paced fetch of the filing header. A 13D/G
whose filer could not be resolved is emitted as `IDENTITY_AMBIGUOUS` — counted,
not usable — because an activist event with no actor cannot support any
actor-level question, and an anonymous row in a library whose entire subject is
*who did what* is worse than no row.

AMENDMENTS ARE FLAGGED, NOT LINKED
==================================
EDGAR does not say which filing a `/A` amends. So `is_amendment` is set and
`amends_event_id` is left None, with a flag saying the parent is unresolved.
That is deliberately safe: the ledger only supersedes a parent when
`amends_event_id` is present, so an unlinked amendment cannot silently hide the
original it might not even be amending.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

from . import events as E
from .adapters import _status_row
from .events import TeacherEvent, sha256_of

logger = logging.getLogger(__name__)

PARSER_VERSION_13DG = "sc13dg-adapter-1.0.0"

#: The `FILED BY:` block in EDGAR's filing header.
_FILER_RE = re.compile(
    r"FILED\s+BY:.*?COMPANY\s+CONFORMED\s+NAME:\s*(?P<name>[^\r\n]+?)\s*\n"
    r".*?CENTRAL\s+INDEX\s+KEY:\s*(?P<cik>\d+)",
    re.S | re.I)


class Schedule13DGAdapter:
    source_name = "sec_13dg"
    FORMS = ("SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A")

    def __init__(self, fetch=None, resolve_filers: bool = True):
        self._fetch = fetch
        self.resolve_filers = resolve_filers

    # ── fetch ───────────────────────────────────────────────────────────────
    def fetch(self, subject: str, *, lookback_days: int = 365,
              max_filings: int = 20) -> dict:
        if self._fetch is not None:
            return self._fetch(subject, lookback_days=lookback_days,
                               max_filings=max_filings)

        from backend.services import edgar_events as EE

        base = {"ticker": subject.upper(), "source": self.source_name,
                "filings": [], "n_filings": 0, "n_unresolved_filers": 0}
        try:
            cik = EE.lookup_cik(subject)
        except Exception as exc:                               # noqa: BLE001
            return {**base, "status": E.UNAVAILABLE,
                    "reason": f"cik_lookup_failed:{type(exc).__name__}"}
        if cik is None:
            return {**base, "status": E.UNAVAILABLE,
                    "reason": "ticker_not_in_cik_map"}
        try:
            sub = EE._fetch_submissions(cik)
        except Exception as exc:                               # noqa: BLE001
            return {**base, "status": E.UNAVAILABLE,
                    "reason": f"submissions_fetch_failed:{type(exc).__name__}"}
        if not sub:
            return {**base, "status": E.UNAVAILABLE,
                    "reason": "submissions_fetch_failed"}

        rec = (sub.get("filings") or {}).get("recent") or {}
        forms = rec.get("form") or []
        n = len(forms)
        filed_dates = rec.get("filingDate") or [""] * n
        accessions = rec.get("accessionNumber") or [""] * n
        accepted = rec.get("acceptanceDateTime") or [""] * n
        cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

        rows, unresolved = [], 0
        for i, form in enumerate(forms):
            if form not in self.FORMS or filed_dates[i] < cutoff:
                continue
            if len(rows) >= max_filings:
                break
            acc = accessions[i]
            row = {"form": form, "accession": acc,
                   "filing_date": filed_dates[i], "accepted_at": accepted[i],
                   "issuer_cik": str(cik), "filer_name": "", "filer_cik": ""}
            if self.resolve_filers and acc:
                name, fcik = self._resolve_filer(cik, acc)
                row["filer_name"], row["filer_cik"] = name, fcik
                if not fcik:
                    unresolved += 1
            rows.append(row)

        return {**base, "filings": rows, "n_filings": len(rows),
                "n_unresolved_filers": unresolved,
                "status": E.OK_DATA if rows else E.OK_EMPTY,
                "reason": "" if rows else "no_13dg_filings_in_window"}

    def _resolve_filer(self, cik: int, accession: str) -> tuple[str, str]:
        """(name, cik) of the FILER, or ("", "") — never a guess."""
        from backend.services.insider_form4 import _sec_get
        acc = accession.replace("-", "")
        url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/"
               f"{accession}-index-headers.html")
        try:
            m = _FILER_RE.search(_sec_get(url).text)
        except Exception as exc:                               # noqa: BLE001
            logger.warning("13D/G filer header fetch failed (%s): %s", url, exc)
            return "", ""
        if not m:
            return "", ""
        return m.group("name").strip(), m.group("cik").lstrip("0")

    # ── map ─────────────────────────────────────────────────────────────────
    def to_events(self, payload: dict) -> list[TeacherEvent]:
        ticker = str(payload.get("ticker", "")).upper()
        fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
        status = payload.get("status")

        if status in (E.UNAVAILABLE, E.OK_EMPTY):
            return [_status_row(self.source_name, ticker, status,
                                str(payload.get("reason", "")),
                                E.ACTOR_ACTIVIST_INVESTOR, fetched)]

        out: list[TeacherEvent] = []
        for f in payload.get("filings") or []:
            form = str(f.get("form", ""))
            is_13d = form.startswith("SC 13D")
            fcik = str(f.get("filer_cik") or "").strip()
            fname = str(f.get("filer_name") or "").strip()

            # Acceptance, not filing date. One accepted at 18:05 was public to
            # nobody during that session.
            public_at = f.get("accepted_at") or f.get("filing_date") or ""

            flags = ["actor_type_inferred_from_form_type"]
            if not f.get("accepted_at"):
                flags.append("acceptance_missing_filing_date_used")
            if form.endswith("/A"):
                flags.append("amendment_parent_unresolved")

            if fcik:
                actor_id, iq = f"cik:{fcik}", "cik"
                row_status, reason = E.OK_DATA, ""
            else:
                actor_id = f"unresolved:{f.get('accession', ticker)}"
                iq = "unresolved"
                row_status, reason = E.IDENTITY_AMBIGUOUS, "filer_not_resolved"

            try:
                out.append(TeacherEvent(
                    source=self.source_name,
                    source_event_id=str(f.get("accession") or f"{ticker}:{form}"),
                    actor_id=actor_id,
                    actor_name=fname,
                    # The inference is from the FORM, not from the filer's
                    # nature, and the flag above says so out loud.
                    actor_type=(E.ACTOR_ACTIVIST_INVESTOR if is_13d
                                else E.ACTOR_FUND_MANAGER),
                    actor_subtype=("activist_13d" if is_13d
                                   else "passive_13g_filer"),
                    action_type=("ACTIVIST_STAKE" if is_13d
                                 else "PASSIVE_STAKE"),
                    ticker_at_event=ticker,
                    security_id=ticker,
                    issuer_cik=str(f.get("issuer_cik") or ""),
                    public_at=public_at or None,
                    accepted_at=f.get("accepted_at") or None,
                    filed_at=f.get("filing_date") or None,
                    filing_type=form,
                    is_amendment=form.endswith("/A"),
                    status=row_status,
                    reason=reason,
                    source_quality="sec_primary",
                    source_url=(f"https://www.sec.gov/Archives/edgar/data/"
                                f"{f.get('issuer_cik')}/"
                                f"{str(f.get('accession', '')).replace('-', '')}/"),
                    raw_sha256=sha256_of(f),
                    parser_version=PARSER_VERSION_13DG,
                    identity_quality=iq,
                    mapping_quality="ticker_at_event",
                    data_quality_flags=flags,
                    fetched_at=fetched,
                ))
            except E.TeacherEventInvalid as exc:
                logger.warning("13D/G adapter: refusing a row for %s (%s)",
                               ticker, exc)
                out.append(_status_row(self.source_name, ticker, E.PARSE_ERROR,
                                       str(exc)[:200],
                                       E.ACTOR_ACTIVIST_INVESTOR, fetched))
        return out or [_status_row(self.source_name, ticker, E.OK_EMPTY,
                                   "no_13dg_filings_in_window",
                                   E.ACTOR_ACTIVIST_INVESTOR, fetched)]
