"""Recover Murat's book from what the repo already knows. Read-only.

WHY THIS EXISTS. BUILD-1.1 ended by asking Murat to type in his holdings. He
answered: *"mirror and conviction is already my portfolio, i logged them."* He
is right, and the ask was a failure of this codebase rather than a gap in his
records — three independent sources already carry the book, and nothing had ever
read two of them together:

    book_lanes.yaml            12 share counts, called GROUND TRUTH in its own
                               header, used to seed the mirror/conviction lanes
    conviction decision log    12 dated `enter` decisions with share counts AND
                               a price, immutable, logged 2026-07-11
    murat_book.yaml            11 positions with a cost basis, reconstructed
                               from a January 2026 PDF

They do not agree, and the disagreements are the interesting part. This module
prints every one of them rather than picking a winner quietly, because a
silently-chosen share count is exactly the kind of number that survives into a
dollar ticket without anyone having decided it.

WHAT IT WILL NOT DO
-------------------
* It will not treat the **$100k normalised MIRROR lane** as the $45k brokerage
  account. The mirror lane is a paper comparison seeded at a notional $100k
  (book_lanes.yaml: "seeded shares = $100k·weight/price"); its share counts are
  a *rescaling* of the real book, not the real book. Reading them as holdings
  would overstate the account by roughly 2.5x.
* It will not treat a **logging price as a cost basis**. The conviction log's
  `price` is the market price when Murat typed the decision in on 2026-07-11,
  and his own rationale says he bought "months ago". Those are different
  numbers, and only one of them is what he paid.
* It will not **invent cash**. Cash is unrecoverable from every source here, and
  a book with an unknown cash balance is a book with an unknown NAV.

The output is deliberately shaped like evidence, not like a conclusion: each
field carries where it came from, how confident that source is, and whether the
sources conflicted.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parents[1] / "data"
BOOK_LANES = DATA / "book_lanes.yaml"
CONVICTION_SNAPSHOT = DATA / "conviction_decisions_snapshot.json"
MURAT_BOOK = DATA / "murat_book.yaml"

PROD_DECISIONS_URL = (
    "https://aegis-finance-production.up.railway.app/api/pi/conviction/decisions"
)

#: How much a source is trusted for a SHARE COUNT, most trusted first. Recency
#: wins: the conviction log is a dated, immutable statement of what was held on
#: the day it was written; book_lanes.yaml is a config file with no revision
#: history, and murat_book.yaml is an explicit reconstruction.
SHARE_PRECEDENCE = ("conviction_log", "book_lanes", "murat_book")

#: For a COST BASIS the ordering inverts. The conviction log's price is a
#: mark on the logging date, not a fill, so it is not a cost-basis source at
#: all — only the reconstruction carries anything resembling what was paid.
COST_PRECEDENCE = ("murat_book",)

SOURCE_NOTES = {
    "conviction_log": (
        "immutable personal decision log (prod, /api/pi/conviction/decisions), "
        "12 `enter` rows dated 2026-07-11"
    ),
    "book_lanes": (
        "backend/data/book_lanes.yaml `holdings:` — its own header calls these "
        "share counts GROUND TRUTH, used to derive lane seed weights"
    ),
    "murat_book": (
        "backend/data/murat_book.yaml — reconstructed from the January 2026 "
        "research PDF; positions are a placeholder dollar split, cost_basis is "
        "the PDF's entry price"
    ),
}


class ReconcileError(RuntimeError):
    """A source was present but unreadable. Never silently skipped."""


@dataclass
class Claim:
    """One source's assertion about one field of one position."""
    source: str
    value: Any
    as_of: Optional[str] = None
    detail: str = ""


@dataclass
class ReconciledPosition:
    ticker: str
    shares: Optional[float] = None
    shares_source: Optional[str] = None
    shares_claims: list[Claim] = field(default_factory=list)
    shares_contested: bool = False
    cost_basis: Optional[float] = None
    cost_basis_source: Optional[str] = None
    cost_basis_status: str = "MISSING"
    last_logged_price: Optional[float] = None
    last_logged_at: Optional[str] = None
    entry_date: Optional[str] = None
    thesis: str = ""
    kill_condition: str = ""
    sources_present: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "ticker": self.ticker,
            "shares": self.shares,
            "shares_source": self.shares_source,
            "shares_contested": self.shares_contested,
            "shares_claims": [
                {"source": c.source, "value": c.value, "as_of": c.as_of}
                for c in self.shares_claims
            ],
            "cost_basis": self.cost_basis,
            "cost_basis_source": self.cost_basis_source,
            "cost_basis_status": self.cost_basis_status,
            "last_logged_price": self.last_logged_price,
            "last_logged_at": self.last_logged_at,
            "entry_date": self.entry_date,
            "thesis": self.thesis,
            "kill_condition": self.kill_condition,
            "sources_present": self.sources_present,
            "notes": self.notes,
        }
        return d


# ───────────────────────────── the three readers ────────────────────────────

def read_book_lanes(path: Path | None = None) -> dict[str, Claim]:
    """`holdings:` from book_lanes.yaml. NOT the seeded lane share counts."""
    p = Path(path or BOOK_LANES)
    if not p.exists():
        raise ReconcileError(f"book_lanes.yaml not found at {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - a parse failure is a finding
        raise ReconcileError(f"book_lanes.yaml did not parse: {exc}") from exc
    holdings = raw.get("holdings") or {}
    if not isinstance(holdings, dict):
        raise ReconcileError("book_lanes.yaml `holdings:` is not a mapping")
    out: dict[str, Claim] = {}
    for tic, sh in holdings.items():
        out[str(tic).upper()] = Claim(
            source="book_lanes", value=float(sh),
            as_of=_file_date(p), detail="holdings: block")
    return out


def read_conviction_log(path: Path | None = None) -> dict[str, dict]:
    """Net share position per ticker from the immutable decision log.

    `enter` adds, `exit` subtracts, `trim`/`add` apply the signed delta as
    logged. An unrecognised action is NOT silently treated as zero — it is
    recorded as a note, because a decision the engine cannot interpret is a
    hole in the book, not an absence of one.
    """
    p = Path(path or CONVICTION_SNAPSHOT)
    if not p.exists():
        raise ReconcileError(
            f"conviction snapshot not found at {p} — run "
            f"scripts/snapshot_conviction.py while prod is reachable")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ReconcileError(f"conviction snapshot did not parse: {exc}") from exc

    rows = raw.get("decisions") or []
    per: dict[str, dict] = {}
    unknown_actions: list[str] = []
    for r in sorted(rows, key=lambda x: (x.get("timestamp") or "", x.get("id") or 0)):
        tic = str(r.get("ticker") or "").upper()
        if not tic:
            continue
        act = str(r.get("action") or "").lower()
        delta = r.get("shares_delta")
        try:
            delta = float(delta)
        except (TypeError, ValueError):
            unknown_actions.append(f"{tic}: non-numeric shares_delta {delta!r}")
            continue
        if act in {"enter", "add", "increase"}:
            signed = abs(delta)
        elif act in {"exit", "trim", "reduce", "sell"}:
            signed = -abs(delta)
        else:
            unknown_actions.append(f"{tic}: unrecognised action {act!r}")
            continue
        e = per.setdefault(tic, {"shares": 0.0, "rows": 0, "last_price": None,
                                 "last_at": None, "rationale": "",
                                 "late_entry": False, "conviction": None})
        e["shares"] += signed
        e["rows"] += 1
        e["last_price"] = r.get("price")
        e["last_at"] = r.get("timestamp")
        e["rationale"] = r.get("rationale") or e["rationale"]
        e["late_entry"] = bool(r.get("late_entry")) or e["late_entry"]
        e["conviction"] = r.get("conviction")
    if unknown_actions:
        logger.warning("conviction log: %d uninterpretable row(s): %s",
                       len(unknown_actions), "; ".join(unknown_actions[:5]))
    return {
        "positions": {t: e for t, e in per.items() if e["shares"] != 0.0},
        "closed": {t: e for t, e in per.items() if e["shares"] == 0.0},
        "uninterpretable": unknown_actions,
        "fetched_at": raw.get("fetched_at"),
        "payload_sha256": raw.get("payload_sha256"),
        "source_url": raw.get("source"),
    }


def read_murat_book(path: Path | None = None) -> dict:
    p = Path(path or MURAT_BOOK)
    if not p.exists():
        raise ReconcileError(f"murat_book.yaml not found at {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    positions = {}
    for entry in raw.get("positions") or []:
        tic = str(entry.get("ticker") or "").upper()
        if tic:
            positions[tic] = entry
    return {
        "positions": positions,
        "closed": raw.get("closed") or [],
        "watchlist": raw.get("watchlist") or [],
        "cash": raw.get("cash"),
        "confirmed": bool(raw.get("confirmed", False)),
        "as_of": raw.get("as_of"),
        "source": raw.get("source", ""),
        "wealth_targets": raw.get("wealth_targets") or {},
        "sizing_mode": raw.get("sizing_mode", "growth"),
    }


def _file_date(p: Path) -> str:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).date().isoformat()
    except OSError:
        return ""


# ───────────────────────────── the reconciliation ───────────────────────────

def reconcile(*, book_lanes_path: Path | None = None,
              conviction_path: Path | None = None,
              murat_book_path: Path | None = None) -> dict:
    """Merge the three sources. Every conflict is reported, none is hidden."""
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {},
        "positions": [],
        "disagreements": [],
        "unrecoverable": [],
        "excluded": [],
    }

    lanes: dict[str, Claim] = {}
    conv: dict = {"positions": {}, "closed": {}, "uninterpretable": []}
    mb: dict = {"positions": {}}

    for key, fn, arg in (("book_lanes", read_book_lanes, book_lanes_path),
                         ("conviction_log", read_conviction_log, conviction_path),
                         ("murat_book", read_murat_book, murat_book_path)):
        try:
            val = fn(arg)  # type: ignore[operator]
            report["sources"][key] = {"status": "READ", "note": SOURCE_NOTES[key]}
            if key == "book_lanes":
                lanes = val  # type: ignore[assignment]
                report["sources"][key]["n_holdings"] = len(lanes)
            elif key == "conviction_log":
                conv = val  # type: ignore[assignment]
                report["sources"][key].update(
                    n_open=len(conv["positions"]),
                    logged_at=conv.get("fetched_at"),
                    payload_sha256=conv.get("payload_sha256"),
                    source_url=conv.get("source_url"))
            else:
                mb = val  # type: ignore[assignment]
                report["sources"][key]["n_positions"] = len(mb["positions"])
        except ReconcileError as exc:
            # A source that cannot be read is a FINDING, not a silent zero.
            report["sources"][key] = {"status": "UNREADABLE", "error": str(exc),
                                      "note": SOURCE_NOTES[key]}
            logger.error("reconcile: source %s unreadable: %s", key, exc)

    if conv.get("uninterpretable"):
        report["disagreements"].append({
            "kind": "uninterpretable_decision_rows",
            "detail": conv["uninterpretable"],
            "consequence": "these rows did not move any share count",
        })

    tickers = sorted(set(lanes) | set(conv["positions"]) | set(mb["positions"]))

    for tic in tickers:
        pos = ReconciledPosition(ticker=tic)
        claims: list[Claim] = []

        # A ticker the log has EXITED is a claim of zero shares, not an absence
        # of a claim. Filing it under `closed` and moving on would let a lower-
        # precedence source supply a share count for a name Murat has sold, and
        # nothing would flag it — the position would simply reappear.
        conv_entry = conv["positions"].get(tic) or conv["closed"].get(tic)
        if conv_entry is not None:
            claims.append(Claim("conviction_log", float(conv_entry["shares"]),
                                as_of=(conv_entry.get("last_at") or "")[:10],
                                detail=f"{conv_entry['rows']} logged decision(s)"))
            pos.last_logged_price = conv_entry.get("last_price")
            pos.last_logged_at = conv_entry.get("last_at")
            pos.sources_present.append("conviction_log")
            if tic in conv["closed"]:
                pos.notes.append(
                    "the decision log nets to ZERO shares — this name was "
                    "exited. Any other source still listing it is stale.")
        if tic in lanes:
            claims.append(lanes[tic])
            pos.sources_present.append("book_lanes")
        if tic in mb["positions"]:
            entry = mb["positions"][tic]
            pos.sources_present.append("murat_book")
            if entry.get("shares") is not None:
                claims.append(Claim("murat_book", float(entry["shares"]),
                                    as_of=str(mb.get("as_of") or ""),
                                    detail="explicit shares"))
            # PyYAML turns a bare 2025-11-07 into a date object; everything
            # downstream is JSON, so it becomes text here rather than at four
            # separate call sites that would each have to remember.
            ed = entry.get("entry_date")
            pos.entry_date = None if ed is None else str(ed)
            pos.thesis = entry.get("thesis") or ""
            pos.kill_condition = entry.get("kill_condition") or ""

        # Five recovered names (ABSI, AMSC, HUBS, KYTX, SLDP) are absent from
        # the January reconstruction, so they arrive with no thesis at all. The
        # conviction log DOES carry Murat's rationale for them, and a generic
        # real reason beats an invented specific one. A kill condition is a
        # different matter: none exists, none is inferred, and the gap is
        # reported so the brief can say a position has no exit discipline.
        if not pos.thesis and conv_entry and conv_entry.get("rationale"):
            pos.thesis = ("(from the conviction log, 2026-07-11) "
                          + str(conv_entry["rationale"]).strip())
            pos.notes.append("thesis carried from the decision log — generic, "
                             "and it is his own words rather than a guess")
        if not pos.kill_condition:
            pos.notes.append("NO KILL CONDITION — no source carries one, and "
                             "none was invented")
            report["unrecoverable"].append({
                "field": "kill_condition", "ticker": tic,
                "why": ("neither the January reconstruction nor the decision "
                        "log states an exit rule for this name. A position "
                        "without one has no exit discipline, and inventing a "
                        "plausible-sounding rule would be worse than saying so."),
                "needs_murat": True,
            })

        pos.shares_claims = claims

        # A name only the STALE reconstruction knows about is not a holding.
        # It is recorded once, below, where the cost basis is also to hand.
        if not claims:
            continue

        # Share count: highest-precedence source that has one.
        by_source = {c.source: c for c in claims}
        for src in SHARE_PRECEDENCE:
            if src in by_source:
                pos.shares = float(by_source[src].value)
                pos.shares_source = src
                break

        values = {round(float(c.value), 6) for c in claims}
        if len(values) > 1:
            pos.shares_contested = True
            detail = ", ".join(f"{c.source}={c.value:g}" for c in claims)
            pos.notes.append(
                f"share count CONTESTED ({detail}); using {pos.shares_source} "
                f"because it is the most recent dated statement")
            report["disagreements"].append({
                "kind": "share_count",
                "ticker": tic,
                "claims": {c.source: c.value for c in claims},
                "using": {"source": pos.shares_source, "value": pos.shares},
                "why": ("the conviction log is a dated immutable entry; "
                        "book_lanes.yaml is an undated config file"),
                "needs_murat": True,
            })

        # Cost basis: only the reconstruction has anything like one.
        entry = mb["positions"].get(tic) or {}
        cb = entry.get("cost_basis")
        if cb is not None:
            pos.cost_basis = float(cb)
            pos.cost_basis_source = "murat_book"
            pos.cost_basis_status = "RECONSTRUCTED"
            pos.notes.append(
                "cost basis is the January 2026 PDF's entry price, not a "
                "broker fill — good enough for P&L colour, not for tax")
        else:
            pos.cost_basis_status = "MISSING"
            report["unrecoverable"].append({
                "field": "cost_basis", "ticker": tic,
                "why": ("no source carries a fill price for this name. The "
                        "conviction log's `price` is the market price on "
                        "2026-07-11, the day it was typed in, and the rationale "
                        "says the shares were bought months earlier."),
                "observed_price_when_logged": pos.last_logged_price,
            })

        report["positions"].append(pos.to_dict())

    # Names in the stale reconstruction that the current book does not hold.
    # The conviction log is a COMPLETE statement of holdings on 2026-07-11 — a
    # name absent from it was exited, not forgotten. That inference is the one
    # place this module reasons rather than reports, so it is stated as such.
    for tic in sorted(set(mb["positions"]) - set(lanes) - set(conv["positions"])):
        report["excluded"].append({
            "ticker": tic,
            "reason": ("in murat_book.yaml (January 2026 reconstruction) but "
                       "absent from BOTH the 2026-07-11 conviction log and "
                       "book_lanes.yaml — read as exited before the log was "
                       "written, because the log enumerates the whole book"),
            "reconstruction_cost_basis": mb["positions"][tic].get("cost_basis"),
            "inference": True,
            "needs_murat": True,
        })

    report["unrecoverable"].append({
        "field": "cash",
        "why": ("no source records a cash balance. book_lanes.yaml normalises to "
                "a notional $100k, the conviction log records share decisions "
                "only, and murat_book.yaml carries `cash: 0` as a placeholder. "
                "An unknown cash balance is an unknown NAV."),
        "needs_murat": True,
    })

    report["summary"] = {
        "n_positions_recovered": len(report["positions"]),
        "n_share_counts_known": sum(1 for p in report["positions"]
                                    if p["shares"] is not None),
        "n_contested": sum(1 for p in report["positions"] if p["shares_contested"]),
        "n_cost_basis_reconstructed": sum(
            1 for p in report["positions"]
            if p["cost_basis_status"] == "RECONSTRUCTED"),
        "n_cost_basis_missing": sum(
            1 for p in report["positions"] if p["cost_basis_status"] == "MISSING"),
        "cash": "UNRECOVERABLE",
        "n_excluded": len(report["excluded"]),
    }
    return report


def to_book_yaml(report: dict, *, confirmed: bool = False,
                 cash: float = 0.0, sizing_mode: str = "high_growth",
                 wealth_targets: dict | None = None,
                 watchlist: list[str] | None = None) -> str:
    """Render the reconciliation as a murat_book.yaml with provenance per line.

    `confirmed` defaults to FALSE and this function will not set it true: a
    reconciliation is evidence about the book, not the broker's statement of it.
    The share counts are recovered, but cash is not, and a NAV missing its cash
    leg is not a NAV.
    """
    wt = wealth_targets or {"horizon_months": 12, "target_value": 100000,
                            "floor_value": 30000, "ruin_value": 20000}
    lines: list[str] = []
    add = lines.append

    add("# Murat's live book — RECOVERED, not re-typed.")
    add("#")
    add("# Generated by backend/services/pm_reconcile.py from three sources that")
    add("# the repo already held. Murat's instruction was that this should never")
    add("# have been asked of him: \"mirror and conviction is already my")
    add("# portfolio, i logged them.\" It was. Every share count below carries")
    add("# the source that asserted it.")
    add("#")
    add(f"# Reconciled at {report['generated_at']}")
    for key, meta in report.get("sources", {}).items():
        add(f"#   {key:16s} {meta.get('status'):10s} {meta.get('note','')[:90]}")
    add("#")
    add("# STILL UNCONFIRMED, and these are the reasons:")
    for u in report.get("unrecoverable", []):
        if u.get("needs_murat"):
            add(f"#   - {u['field']}: {u['why'][:150]}")
    n_contested = report["summary"]["n_contested"]
    if n_contested:
        add(f"#   - {n_contested} share count(s) CONTESTED between sources; see")
        add("#     docs/PORTFOLIO_RECONCILIATION.md. Marked inline below.")
    add("")
    add("account: murat_live")
    add(f"confirmed: {str(bool(confirmed)).lower()}")
    add(f"as_of: {date.today().isoformat()}")
    add("currency: USD")
    add('source: "reconciled from book_lanes.yaml + conviction decision log '
        '(prod, immutable) + murat_book.yaml reconstruction"')
    add("")
    add(f"cash: {cash}   # UNRECOVERABLE from any source — Murat must supply it")
    add("")
    add("wealth_targets:")
    for k, v in wt.items():
        add(f"  {k}: {v}")
    add("")
    add(f"sizing_mode: {sizing_mode}")
    add("")
    add("positions:")
    for p in report["positions"]:
        add(f"  - ticker: {p['ticker']}")
        sh = p["shares"]
        marker = "  # CONTESTED" if p["shares_contested"] else ""
        add(f"    shares: {sh:g}{marker}")
        srcs = ", ".join(f"{c['source']}={c['value']:g}" for c in p["shares_claims"])
        add(f"    # shares from {p['shares_source']} | claims: {srcs}")
        if p["cost_basis"] is not None:
            add(f"    cost_basis: {p['cost_basis']:g}"
                f"   # {p['cost_basis_status']} ({p['cost_basis_source']})")
        else:
            add("    # cost_basis: MISSING — no source carries a fill price."
                f" Logged mark on {str(p['last_logged_at'])[:10]}"
                f" was {p['last_logged_price']}")
        if p.get("entry_date"):
            add(f"    entry_date: {p['entry_date']}")
        if p.get("thesis"):
            add(f"    thesis: {json.dumps(p['thesis'])}")
        if p.get("kill_condition"):
            add(f"    kill_condition: {json.dumps(p['kill_condition'])}")
    add("")
    if report.get("excluded"):
        add("# Excluded — in the January reconstruction, not in the current book:")
        for e in report["excluded"]:
            add(f"#   {e['ticker']}: {e['reason'][:120]}")
        add("")
    if watchlist:
        add("watchlist: [" + ", ".join(watchlist) + "]")
    return "\n".join(lines) + "\n"
