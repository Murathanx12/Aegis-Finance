"""The paper fleet, read-only: what it holds, how old, and would it buy it today?

    python -m scripts.fleet_audit
    python -m scripts.fleet_audit --deep      # also join the ranker's opinion

WHY AN AUDIT AND NOT ANOTHER STRATEGY
=====================================
The five Railway books are $461,940 of $500,000 -- **-7.6%** -- and they
underperformed on an up day (+0.60% vs SPY +1.55%) and again on a flat one
(-0.19% vs -0.09%). Two sessions is not a result, but the shape is suggestive
and the cause is testable rather than guessable.

The hypothesis this script exists to test is NOT "the picks are bad". It is:

    THE BOOKS CANNOT ROTATE.

Old positions hold the gross-notional budget, so a better-ranked candidate
arriving today is refused for capacity rather than for merit. If that is what is
happening, then every hour spent improving the RANKER is wasted, because nothing
the ranker produces can get into the portfolio. That would make this the highest
value thing in the programme and it has never been measured.

THE QUESTION EACH POSITION MUST ANSWER
======================================
    Would this mandate OPEN this position today?

A trade entered on a five-day event thesis that is still held on day 40 is not a
held conviction, it is an absent exit. The distinction is invisible in a
portfolio listing and obvious once each row carries its age, its current rank
and what it is costing in foregone capacity.

WHAT IT WILL NOT DO
===================
**Read-only. It places no order and cancels nothing.** The Railway loops own
those accounts; a second writer is exactly the failure `pc_broker`'s execution
lease exists to prevent. Anything this finds is written up as a PROPOSAL for a
human, never executed from here.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                          # noqa: E402

OUT = _cfg.OPTIMUS_LEDGER_DIR / "fleet_audit"
TERMINAL_ENV = Path(_cfg.PROJECT_ROOT).parent / "aegis-alpha-terminal" / ".env" \
    if hasattr(_cfg, "PROJECT_ROOT") else Path("../aegis-alpha-terminal/.env")
HOST = "https://paper-api.alpaca.markets"

#: hack3 was retired 2026-09-22; its Railway loop is gone. It is absent here on
#: purpose rather than failing every run.
ROLES = ("HACK1", "HACK2", "HACK4", "HACK5", "HACK6")
START_EQUITY = 100_000.0

#: A position older than this, with no exit and no thesis, is the pathology
#: this script is looking for. Not a rule -- a flag for a human to read.
STALE_DAYS = 14
#: Above this share of equity in open notional, a new candidate is competing for
#: capacity rather than for merit.
CAPACITY_WARN = 0.90


def _env() -> dict[str, str]:
    out: dict[str, str] = {}
    p = TERMINAL_ENV
    if not p.exists():
        raise SystemExit(f"REFUSED: no terminal .env at {p}")
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _get(path: str, kid: str, sec: str, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(HOST + path,
                                 headers={"APCA-API-KEY-ID": kid,
                                          "APCA-API-SECRET-KEY": sec})
    with urllib.request.urlopen(req, timeout=timeout) as fh:   # noqa: S310 allowlisted
        return json.loads(fh.read())


def _age_days(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return round((datetime.now(timezone.utc) - t).total_seconds() / 86400, 1)
    except ValueError:
        return None


#: Alpaca caps `/v2/orders` at 500 per page, so the history must be PAGED.
#:
#: The first version of this function asked for `limit=500&direction=asc` once,
#: which is "the oldest 500 closed orders". `fleet_trade_autopsy` had already
#: measured 500 fills across this fleet, so the request was sitting exactly on
#: the cap -- and every position opened after a book's 500th order came back
#: with no entry date. The line below it read
#:
#:     "stale": (age is not None and age > STALE_DAYS)
#:
#: so an UNDATEABLE position was silently counted as FRESH. The published
#: headline "11 of 18 positions are older than 14 days" was therefore a lower
#: bound reported as a count, and it failed in the direction that flatters the
#: fleet. Missing data must not resolve to the benign branch.
ORDER_PAGE = 500
#: Hard stop on paging, so a book with a pathological history cannot hang an
#: audit that is supposed to be cheap and read-only.
MAX_ORDER_PAGES = 20


def entry_dates(kid: str, sec: str) -> tuple[dict[str, str], dict]:
    """When each open position was first entered, from the FULL order history.

    Alpaca's `/v2/positions` says WHAT is held and not SINCE WHEN, and the age
    is the whole point of this audit. Reconstructed from the oldest filled BUY
    -- approximate (it does not reconstruct flats), and labelled as such.

    Returns the map AND a coverage row, because the caller must be able to tell
    "this position is new" from "this audit could not see far enough back".
    """
    out: dict[str, str] = {}
    cov = {"pages": 0, "orders_seen": 0, "complete": False, "why": None}
    cursor: str | None = None
    try:
        for _ in range(MAX_ORDER_PAGES):
            q = f"/v2/orders?status=closed&limit={ORDER_PAGE}&direction=asc"
            if cursor:
                # `after` is exclusive, so the page cannot repeat its last row.
                q += f"&after={urllib.parse.quote(cursor)}"
            page = _get(q, kid, sec)
            cov["pages"] += 1
            cov["orders_seen"] += len(page)
            for o in page:
                if o.get("side") == "buy" and o.get("filled_at"):
                    out.setdefault(o["symbol"], o["filled_at"])
            if len(page) < ORDER_PAGE:
                cov["complete"] = True
                break
            nxt = page[-1].get("submitted_at") or page[-1].get("created_at")
            if not nxt or nxt == cursor:
                cov["why"] = "pagination cursor did not advance"
                break
            cursor = nxt
        else:
            cov["why"] = f"stopped at the {MAX_ORDER_PAGES}-page cap"
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        cov["why"] = f"order history unavailable: {e}"
    return out, cov


def audit_book(role: str, kid: str, sec: str, *, ranks: dict | None = None) -> dict:
    acct = _get("/v2/account", kid, sec)
    pos = _get("/v2/positions", kid, sec)
    entries, coverage = entry_dates(kid, sec)

    eq = float(acct["equity"])
    gross = sum(abs(float(p["market_value"])) for p in pos)
    rows = []
    for p in pos:
        sym = p["symbol"]
        mv = float(p["market_value"])
        age = _age_days(entries.get(sym))
        rank = (ranks or {}).get(sym)
        would_open = None
        why = None
        if rank is not None:
            # The ranker's own opinion of a name the book already owns.
            would_open = rank <= 50
            why = (f"ranked {rank} today" if would_open
                   else f"ranked {rank} today — outside the top 50")
        elif ranks is not None:
            would_open = False
            why = "not in today's eligible universe at all"
        rows.append({
            "symbol": sym, "qty": float(p["qty"]),
            "market_value": mv, "weight": round(mv / eq, 4) if eq else None,
            "unrealized_pl": float(p["unrealized_pl"]),
            "unrealized_plpc": round(float(p["unrealized_plpc"]) * 100, 2),
            "age_days": age,
            "stale": (age is not None and age > STALE_DAYS),
            # A position whose entry the order history could not reach is
            # UNKNOWN age, not fresh. It is counted separately and never
            # allowed to lower the stale fraction.
            "age_unknown": age is None,
            "current_rank": rank, "would_open_today": would_open, "why": why,
        })
    rows.sort(key=lambda r: -(r["age_days"] or 0))

    stale = [r for r in rows if r["stale"]]
    unknown = [r for r in rows if r["age_unknown"]]
    losers_held = [r for r in rows if r["unrealized_plpc"] < -5 and r["stale"]]
    capacity = gross / eq if eq else None
    return {
        "role": role, "account": acct["account_number"],
        "equity": eq, "cash": float(acct["cash"]),
        "vs_start_pct": round((eq / START_EQUITY - 1) * 100, 2),
        "since_last_close_pct": (round((eq / float(acct["last_equity"]) - 1) * 100, 2)
                                 if float(acct.get("last_equity") or 0) else None),
        "n_positions": len(pos),
        "gross_notional": gross,
        "gross_pct_of_equity": round(capacity * 100, 1) if capacity else None,
        "capacity_constrained": bool(capacity and capacity >= CAPACITY_WARN),
        "n_stale": len(stale),
        "oldest_position_days": rows[0]["age_days"] if rows else None,
        "n_age_unknown": len(unknown),
        # Paging coverage travels with the number it qualifies. A stale COUNT
        # read without it is a lower bound presented as a measurement.
        "order_history": coverage,
        "stale_losers": len(losers_held),
        "positions": rows,
    }


def todays_ranks(top_n: int = 400) -> dict[str, int]:
    """symbol -> today's cross-sectional rank, for the would-open test."""
    base = _cfg.OPTIMUS_LEDGER_DIR / "pc_book"
    files = sorted(base.glob("*/ranking.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        return {}
    try:
        r = json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {x["symbol"]: int(x["rank"]) for x in (r.get("top") or [])[:top_n]
            if x.get("symbol") and x.get("rank")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", action="store_true",
                    help="join today's ranking so each holding answers "
                         "'would this mandate open it today?'")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    env = _env()
    ranks = todays_ranks() if a.deep else None
    books, failed = [], []
    for role in ROLES:
        kid, sec = env.get(f"AAT_{role}_KEY_ID"), env.get(f"AAT_{role}_SECRET_KEY")
        if not kid or not sec:
            failed.append({"role": role, "why": "keys absent"})
            continue
        try:
            books.append(audit_book(role, kid, sec, ranks=ranks))
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
            failed.append({"role": role, "why": f"{type(exc).__name__}: {exc}"[:150]})

    tot_eq = sum(b["equity"] for b in books)
    tot_gross = sum(b["gross_notional"] for b in books)
    constrained = [b["role"] for b in books if b["capacity_constrained"]]
    stale_total = sum(b["n_stale"] for b in books)
    unknown_total = sum(b.get("n_age_unknown") or 0 for b in books)
    pos_total = sum(b["n_positions"] for b in books)
    # If any position's entry could not be reached, the stale COUNT is a lower
    # bound and the fleet line must say so rather than printing a bare ratio.
    paging_complete = all((b.get("order_history") or {}).get("complete")
                          for b in books) if books else False

    res = {
        "receipt": "fleet_audit", "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "read_only": True,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "books": books, "failed": failed,
        "fleet": {
            "equity": tot_eq, "start": START_EQUITY * len(books),
            "vs_start_pct": round((tot_eq / (START_EQUITY * len(books)) - 1) * 100, 2)
                            if books else None,
            "gross_notional": tot_gross,
            "gross_pct": round(tot_gross / tot_eq * 100, 1) if tot_eq else None,
            "n_positions": pos_total, "n_stale": stale_total,
            "n_age_unknown": unknown_total,
            "order_history_complete": paging_complete,
            "stale_share": round(stale_total / pos_total, 3) if pos_total else None,
            "capacity_constrained_books": constrained,
        },
        "verdict": _verdict(books, constrained, stale_total, pos_total,
                            unknown_total, paging_complete),
        "read_me_first": ("READ-ONLY. The Railway loops own these accounts; a "
                          "second writer is the failure the execution lease "
                          "exists to prevent. Findings are proposals for a "
                          "human, never executed from here."),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT / f"fleet_audit_{date.today()}.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")

    print(f"{'book':>7} {'equity':>10} {'vs$100k':>8} {'pos':>4} {'gross%':>7} "
          f"{'stale':>6} {'oldest':>7}")
    print("-" * 60)
    for b in books:
        print(f"{b['role'].lower():>7} {b['equity']:>10,.0f} {b['vs_start_pct']:>+7.1f}% "
              f"{b['n_positions']:>4} {(b['gross_pct_of_equity'] or 0):>6.0f}% "
              f"{b['n_stale']:>6} {(b['oldest_position_days'] or 0):>6.0f}d")
    f = res["fleet"]
    print(f"{'FLEET':>7} {f['equity']:>10,.0f} {f['vs_start_pct']:>+7.1f}% "
          f"{f['n_positions']:>4} {(f['gross_pct'] or 0):>6.0f}% {f['n_stale']:>6}")
    for x in failed:
        print(f"  {x['role']}: {x['why']}")
    print(f"\nVERDICT: {res['verdict']}")
    print(f"-> {out}")
    return 0


def _verdict(books, constrained, stale_total, pos_total,
             unknown_total: int = 0, paging_complete: bool = True) -> str:
    if not books:
        return "CANNOT DETERMINE: no book answered"
    share = stale_total / pos_total if pos_total else 0
    parts = []
    # Said FIRST, because it qualifies every count that follows. `stale_total`
    # can only ever undercount: a position whose entry the order history could
    # not reach has unknown age, and unknown is not fresh.
    bound = ""
    if unknown_total or not paging_complete:
        bound = (f" This is a LOWER BOUND: {unknown_total} position(s) have no "
                 f"reachable entry date"
                 + ("" if paging_complete else
                    " and at least one book's order history was not paged to the end")
                 + ", so their age is UNKNOWN and they are excluded from the stale "
                   "count rather than counted as fresh.")
    if constrained:
        parts.append(
            f"{len(constrained)} book(s) are at or above 90% gross ({', '.join(constrained)}): "
            f"a better-ranked candidate arriving today competes for CAPACITY, not on merit")
    if share >= 0.5:
        parts.append(
            f"{stale_total} of {pos_total} positions ({share:.0%}) are older than "
            f"{STALE_DAYS} days — a held conviction and an absent exit look identical "
            f"in a portfolio listing")
    if not parts:
        return (f"No rotation pathology found: {stale_total}/{pos_total} stale, "
                f"no book at the gross ceiling. If the fleet is underperforming, "
                f"it is the PICKS, not the plumbing." + bound)
    # The conclusion depends on WHICH condition fired, and the first version of
    # this asserted the capacity conclusion whenever EITHER did. Staleness alone
    # does not block a new entry when gross is 38% -- there is room; the old
    # positions are simply not being closed. Saying "nothing it produces can
    # enter the portfolio" in that case is an overclaim, and an overclaim in a
    # verdict line is worse than none because it is the sentence people quote.
    tail = (" If this is the binding constraint then improving the RANKER cannot "
            "help, because nothing it produces can enter the portfolio. Test that "
            "before spending another night on alpha."
            if constrained else
            " Note that gross is NOT at the ceiling, so this does not block new "
            "entries -- there is room. What it shows is that exits are not firing, "
            "which costs whatever the stale names drift rather than costing "
            "opportunity. The ranker is not blocked.")
    return " AND ".join(parts) + "." + tail + bound


if __name__ == "__main__":
    raise SystemExit(main())
