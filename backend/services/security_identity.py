"""SECURITY-IDENTITY-LAYER-1 — a ticker is a dated alias, never an identity.

One week produced four proofs that treating tickers as stable identities
loses real companies: MMC was "unexplained absent" for a session because it
had been MRSH since 2026-01-14; SQ trades as XYZ; EA's quotes ghosted on for
8 days after its 2026-08-04 delisting (a quotes panel cannot see death);
PXD sat in a sector list two years dead. This module is the smallest layer
that makes that class of loss structural rather than vigilance-dependent.

V1 IS CURATED AND SAYS SO
=========================
The master below covers the transitions this project has PROVEN, plus a
passthrough for everything else stamped ``ASSUMED_STABLE`` — a visible
provenance, not a silent default, because a four-row table pretending to
cover the market would be the house failure mode wearing a fix. The CRSP
PIT universe build (UNIVERSE-SURVIVAL-STRESS-1) replaces the curated table
with PERMNO-keyed history; the API is written so only the table changes.

Dates carry their evidence grade: MMC→MRSH and EA's delisting are DATED
(verified in TAQ + news during the 08-18 grind); SQ→XYZ is UNRECORDED in
this repo and stays None rather than invented — resolving it is the CRSP
build's job, and a wrong date would be worse than a declared absence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


class IdentityUnknown(LookupError):
    """A required identity input is missing or unresolvable. Refused, not
    defaulted — a resolver that guesses is how MMC stayed 'unexplained'."""


class SecurityDead(RuntimeError):
    """The security has a terminal corporate action on/before the asked
    date. Raised by assert_alive; panels decide their own handling."""


@dataclass(frozen=True)
class SecurityRecord:
    aegis_id: str                       # stable internal key; PERMNO later
    company: str
    aliases: tuple[tuple[str, str | None, str | None], ...]  # (tkr, from, to)
    terminal_date: str | None = None    # ISO date of delist/acquisition
    terminal_reason: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def ticker_on(self, on: date) -> str | None:
        iso = on.isoformat()
        for tkr, frm, to in self.aliases:
            if (frm is None or frm <= iso) and (to is None or iso < to):
                return tkr
        return None

    def is_alive_on(self, on: date) -> bool:
        return self.terminal_date is None or on.isoformat() < self.terminal_date


#: The proven transitions. valid_from/valid_to None = unknown/open;
#: an alias whose end date is UNRECORDED gets to=None on BOTH aliases and a
#: note, so date-scoped resolution refuses to pick a side it cannot know.
_MASTER: tuple[SecurityRecord, ...] = (
    SecurityRecord(
        aegis_id="AEGIS-MARSH", company="Marsh (Marsh & McLennan until 2026)",
        aliases=(("MMC", None, "2026-01-14"), ("MRSH", "2026-01-14", None)),
        notes=("NYSE rebrand verified live in TAQ (MRSH quotes 2026-08-14) "
               "and by news search, 08-18 grind cycle H",)),
    SecurityRecord(
        aegis_id="AEGIS-BLOCK", company="Block Inc",
        aliases=(("SQ", None, None), ("XYZ", None, None)),
        notes=("rename date UNRECORDED in this repo — both aliases open; "
               "resolve from CRSP names file, do not invent",)),
    SecurityRecord(
        aegis_id="AEGIS-EA", company="Electronic Arts",
        aliases=(("EA", None, "2026-08-04"),),
        terminal_date="2026-08-04",
        terminal_reason="PIF-led buyout completed ($210/share cash); trades "
                        "end 08-04, quotes ghosted 8 further days",
        notes=("the case that proved a quotes panel cannot see death",)),
    SecurityRecord(
        aegis_id="AEGIS-PXD", company="Pioneer Natural Resources",
        aliases=(("PXD", None, "2024-05-03"),),
        terminal_date="2024-05-03",
        terminal_reason="acquired by ExxonMobil (merger closed May 2024)",
        notes=("only name whose TAQ cost band did not retire — it is dead",)),
)

_BY_TICKER: dict[str, SecurityRecord] = {}
for _rec in _MASTER:
    for _tkr, _f, _t in _rec.aliases:
        _BY_TICKER[_tkr] = _rec


@dataclass(frozen=True)
class Resolution:
    aegis_id: str
    ticker_asked: str
    ticker_on_date: str | None
    alive: bool
    provenance: str                     # CURATED | ASSUMED_STABLE
    terminal_date: str | None
    terminal_reason: str | None


def resolve(ticker: str | None, on: date | str | None) -> Resolution:
    """Resolve a ticker AS OF a date. Missing inputs refuse; unknown tickers
    pass through with visible ``ASSUMED_STABLE`` provenance."""
    if not ticker or not str(ticker).strip():
        raise IdentityUnknown("resolve() needs a ticker; got nothing")
    if on is None:
        raise IdentityUnknown(
            f"resolve({ticker!r}) needs an as-of date — identity is dated "
            f"or it is not identity")
    on_d = date.fromisoformat(on) if isinstance(on, str) else on
    t = str(ticker).strip().upper()
    rec = _BY_TICKER.get(t)
    if rec is None:
        return Resolution(aegis_id=f"AEGIS-TKR-{t}", ticker_asked=t,
                          ticker_on_date=t, alive=True,
                          provenance="ASSUMED_STABLE", terminal_date=None,
                          terminal_reason=None)
    return Resolution(aegis_id=rec.aegis_id, ticker_asked=t,
                      ticker_on_date=rec.ticker_on(on_d),
                      alive=rec.is_alive_on(on_d), provenance="CURATED",
                      terminal_date=rec.terminal_date,
                      terminal_reason=rec.terminal_reason)


def assert_alive(ticker: str, on: date | str) -> Resolution:
    """resolve(), then refuse if the security is dead on that date."""
    r = resolve(ticker, on)
    if not r.alive:
        raise SecurityDead(
            f"{ticker} is terminal on {on} ({r.terminal_reason}); a panel "
            f"that keeps accruing it is measuring a ghost")
    return r


def quote_ghost_scan(panel: pd.DataFrame, *, min_ghost_days: int = 3
                     ) -> list[dict]:
    """Find names whose quotes continue while their trades have stopped.

    `panel` needs columns ``ticker``, ``date``, ``n_trades``, ``n_quotes``
    (per name-day). A name whose LAST ``min_ghost_days``+ observed days all
    show quotes>0 with trades==0 is flagged — the EA signature. Missing
    columns refuse; an empty panel refuses (a scan of nothing reporting
    "no ghosts" is the lift-audit defect again).
    """
    need = {"ticker", "date", "n_trades", "n_quotes"}
    if panel is None or not need.issubset(getattr(panel, "columns", ())):
        raise IdentityUnknown(
            f"quote_ghost_scan needs columns {sorted(need)}; got "
            f"{sorted(getattr(panel, 'columns', ()))!r}")
    if panel.empty:
        raise IdentityUnknown("quote_ghost_scan on an empty panel — refusing "
                              "to report a clean verdict over nothing")
    out = []
    for tkr, g in panel.sort_values("date").groupby("ticker"):
        ghost = (g["n_quotes"] > 0) & (g["n_trades"] == 0)
        run = 0
        for flag in ghost.to_list()[::-1]:
            if flag:
                run += 1
            else:
                break
        if run >= min_ghost_days:
            out.append({"ticker": str(tkr), "ghost_days_at_end": run,
                        "last_trade_date": str(
                            g.loc[g["n_trades"] > 0, "date"].max()),
                        "action": "QUARANTINE — trades panel says dead, "
                                  "quotes panel says fine; trust the trades"})
    return out
