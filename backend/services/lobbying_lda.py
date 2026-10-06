"""Senate LDA lobbying dollars by client -- a SENSOR, never a trade signal.

    python -m backend.services.lobbying_lda --pull [--limit-clients 10] [--quarters 2]

WHAT (chunk C16, 2026-10-07)
============================
Quarterly LD-2 filings from the Senate Office of Public Records' Lobbying
Disclosure Act API (`lda.senate.gov/api/v1/`, now served at `lda.gov/api/v1/`;
anonymous tier 15 requests / minute, honoured with a 4.2 s gap). Clients are
companies; each client name is mapped to a ticker through the SAME crosswalk as
USAspending (`lda_client_patterns`). One row per filing:

| field | meaning |
|---|---|
| row_id | `lda:<filing_uuid>` |
| filing_year, filing_period, period_start, period_end | the quarter the filing COVERS (NOT public then) |
| dt_posted | when LDA posted the filing -- the public time (`public_utc`, basis `LDA_DT_POSTED`) |
| first_seen_utc | when this collector first held the row |
| filing_type | Q1..Q4, amendments (1A..4A), terminations |
| registrant_name / client_name | the lobbying firm / the company paying |
| self_filer | registrant == client (in-house lobbying reports EXPENSES; an outside firm reports INCOME) |
| amount_usd, amount_kind | expenses (self-filer) or income (outside firm); None when the filer reported under $5,000 |
| issue_codes | the general issue area codes lobbied on |
| ticker, crosswalk_confidence, match_status | the crosswalk join |

The firm-level DOLLARS are the variable (roadmap 2026-10-06 §2 item 10).
Nothing about who any person is enters a row.

CITATION (the API's terms ask it of any republished analysis): "Lobbying
Disclosure Act data from the Senate Office of Public Records (lda.senate.gov).
The Senate Office of Public Records cannot vouch for the data or analyses
derived from these data after the data have been retrieved from LDA.gov." The
Senate Seal is never used.

NOT pulled, by decision: FEC (needs an owner key, and its Acceptable Use Policy
bars use as ML/AI training data -- owner decision D19 in the C16 build note);
OpenSecrets (API discontinued 2026-04-15; bulk terms prohibit redistribution).

FAILURE CONTRACT: an access-denied / bot page / rate limit REFUSES the run and
the receipt says so (it is never worked around: no browser headers, no proxy);
zero new rows on a weekday is not DEGRADED here only because LDA is quarterly
(`quiet_ok`), but zero rows READ with refusals is REFUSED.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from backend import config as _config
from backend.services import public_flow_common as PF

SOURCE = "senate_lda"
TABLE = "lobbying_filings"
CITATION = ("Lobbying Disclosure Act data from the Senate Office of Public Records "
            "(lda.senate.gov). The Senate Office of Public Records cannot vouch for the data or "
            "analyses derived from these data after the data have been retrieved from LDA.gov.")
BANNER = ("SENSOR -- quarterly lobbying dollars by client with filing date and covered period "
          "kept apart; never a trade signal on its own")

_PERIODS = {"first_quarter": 1, "second_quarter": 2, "third_quarter": 3, "fourth_quarter": 4}


def client(base: Optional[Path] = None, http=None, sleep_fn=None) -> PF.Client:
    kw = {} if sleep_fn is None else {"sleep_fn": sleep_fn}
    return PF.Client(source=SOURCE, min_gap_s=float(_config.LDA_MIN_GAP_S),
                     day_cap=int(_config.LDA_DAY_CAP), base=base, http=http, **kw)


def period_bounds(year: Any, period: Any) -> tuple[Optional[str], Optional[str]]:
    """PURE. ('first_quarter', 2026) -> ('2026-01-01', '2026-03-31'); mid_year /
    year_end (pre-2008 semiannual) are handled too."""
    try:
        y = int(year)
    except (TypeError, ValueError):
        return None, None
    q = _PERIODS.get(str(period or ""))
    if q:
        start = date(y, 3 * q - 2, 1)
        end = {1: date(y, 3, 31), 2: date(y, 6, 30), 3: date(y, 9, 30), 4: date(y, 12, 31)}[q]
        return start.isoformat(), end.isoformat()
    if period == "mid_year":
        return date(y, 1, 1).isoformat(), date(y, 6, 30).isoformat()
    if period == "year_end":
        return date(y, 7, 1).isoformat(), date(y, 12, 31).isoformat()
    return None, None


def _num(x: Any) -> Optional[float]:
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def parse_filings(payload: dict, crosswalk: list[dict]) -> list[dict]:
    """PURE. One row per filing of an LDA `/filings/` page."""
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise PF.PublicFlowRefused("MALFORMED_PAYLOAD: no `results` list")
    out = []
    for f in payload["results"]:
        uid = f.get("filing_uuid")
        if not uid:
            continue
        reg = f.get("registrant") or {}
        cli = f.get("client") or {}
        ps, pe = period_bounds(f.get("filing_year"), f.get("filing_period"))
        posted = PF.parse_dt(f.get("dt_posted"))
        self_filer = bool(reg.get("id") is not None and cli.get("client_id") is not None
                          and PF.normalize_name(reg.get("name")) == PF.normalize_name(cli.get("name")))
        income, expenses = _num(f.get("income")), _num(f.get("expenses"))
        amount, kind = ((expenses, "expenses") if expenses is not None or self_filer
                        else (income, "income"))
        m = PF.match_entity(cli.get("name"), crosswalk, "lda_client_patterns", on=pe)
        out.append({
            "row_id": f"lda:{uid}", "source": SOURCE, "filing_uuid": uid,
            "filing_type": f.get("filing_type"), "filing_year": f.get("filing_year"),
            "filing_period": f.get("filing_period"), "period_start": ps, "period_end": pe,
            "dt_posted": PF.iso(posted) if posted else None,
            "posted_date": posted.date().isoformat() if posted else None,
            "public_utc": PF.iso(posted) if posted else None, "public_ts_basis": "LDA_DT_POSTED",
            "registrant_id": reg.get("id"), "registrant_name": reg.get("name"),
            "client_id": cli.get("client_id") or cli.get("id"), "client_name": cli.get("name"),
            "self_filer": self_filer, "income_usd": income, "expenses_usd": expenses,
            "amount_usd": amount, "amount_kind": kind,
            "issue_codes": sorted({a.get("general_issue_code") for a in
                                   (f.get("lobbying_activities") or []) if a.get("general_issue_code")}),
            "filing_document_url": f.get("filing_document_url"),
            "citation": "Senate Office of Public Records (LDA)", **m})
    return out


def lobbying_totals(rows: list[dict]) -> dict:
    """PURE (review F10). Lobbying dollars per (ticker, period) without double
    counting: per (client, registrant, period) only the LATEST posted filing
    counts (an amendment supersedes its original); a client that self-files
    reports total EXPENSES, which already include what it pays outside firms, so
    outside-firm INCOME is added only for clients with no self-filing."""
    latest: dict[tuple, dict] = {}
    for r in rows:
        if r.get("match_status") != "MAPPED" or not r.get("period_end"):
            continue
        k = (PF.normalize_name(r.get("client_name")), r.get("registrant_id"), r["period_end"])
        if k not in latest or str(r.get("dt_posted") or "") > str(latest[k].get("dt_posted") or ""):
            latest[k] = r
    by: dict[tuple, dict] = {}
    for r in latest.values():
        a = by.setdefault((r["ticker"], r["period_end"]), {"self": 0.0, "outside": 0.0, "has_self": False,
                                                           "n_filings": 0})
        a["n_filings"] += 1
        if r.get("self_filer"):
            a["has_self"] = True
            a["self"] += float(r.get("amount_usd") or 0.0)
        else:
            a["outside"] += float(r.get("amount_usd") or 0.0)
    return {f"{t}|{pe}": {"amount_usd": round(a["self"] if a["has_self"] else a["outside"], 2),
                          "basis": "self-filer expenses" if a["has_self"] else "outside-firm income",
                          "n_filings_latest": a["n_filings"]}
            for (t, pe), a in sorted(by.items())}


def wanted_periods(now: datetime, quarters: int) -> list[tuple[int, str]]:
    """PURE. The last `quarters` COMPLETED quarters before `now`, newest first."""
    y, q = now.year, (now.month - 1) // 3          # q = the last completed quarter (0 -> last year Q4)
    if q == 0:
        y, q = y - 1, 4
    out = []
    names = {v: k for k, v in _PERIODS.items()}
    for _ in range(max(1, int(quarters))):
        out.append((y, names[q]))
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return out


def clients_of(crosswalk: list[dict]) -> list[dict]:
    out, seen = [], set()
    for e in crosswalk:
        for pat in e.get("lda_client_patterns") or []:
            if pat not in seen:
                seen.add(pat)
                out.append({"ticker": e["ticker"], "text": pat})
            break
    return out


def pull(*, quarters: int = 2, limit_clients: Optional[int] = None, base: Optional[Path] = None,
         http=None, sleep_fn=None, now: Optional[datetime] = None,
         crosswalk_path: Optional[Path] = None) -> dict:
    now = now or PF.now_utc()
    cw = PF.load_crosswalk(crosswalk_path)
    targets = clients_of(cw)[: limit_clients or None]
    periods = wanted_periods(now, quarters)
    c = client(base, http, sleep_fn)
    url = f"{_config.LDA_API_BASE}/filings/"
    rows, refusals, per = [], [], {}
    prior = {r.get("search_text") for r in PF.read_table(TABLE, base)}
    stop = False
    for t in targets:
        if stop:
            break
        n0 = len(rows)
        for (yr, per_name) in periods:
            page = 0
            while True:
                page += 1
                try:
                    payload = c.request_json("GET", url, params={
                        "client_name": t["text"], "filing_year": yr, "filing_period": per_name,
                        "page": page})
                except PF.PublicFlowRefused as exc:
                    cls = str(exc).split(":")[0]
                    refusals.append({"step": f"{t['text']} {yr} {per_name}", "why": str(exc)[:300],
                                     "fatal": cls in ("ACCESS_DENIED", "BOT_CHECK", "RATE_LIMITED",
                                                      "DAY_CAP")})
                    stop = refusals[-1]["fatal"]      # a host that refused us is not asked again
                    break
                rows.extend(parse_filings(payload, cw))
                if not payload.get("next") or page >= int(_config.LDA_MAX_PAGES_PER_CLIENT):
                    break
            if stop:
                break
        got = rows[n0:]
        for r in got:                                  # F3: a first contact is a backfill
            r["search_text"] = t["text"]
            if t["text"] not in prior:
                r["latency"] = PF.BACKFILL_LATENCY
        per[t["text"]] = {"ticker": t["ticker"], "filings_read": len(got),
                          "mapped": sum(r["match_status"] == "MAPPED" for r in got)}
    wr = PF.append_rows(TABLE, rows, event_field="posted_date", base=base, now=now)
    not_mapped: dict[str, int] = {}
    for r in rows:
        if r["match_status"] != "MAPPED":
            k = f"{r['match_status']}:{r.get('client_name')}"
            not_mapped[k] = not_mapped.get(k, 0) + 1
    body = {"banner": BANNER, "citation": CITATION, "periods": [f"{y} {p}" for y, p in periods],
            "clients_requested": len(targets), "requests": c.n_requests,
            "request_classes": c.statuses, "rows_read": len(rows), "rows_added": wr["written"],
            "duplicates": wr["duplicate"], "pit_refused": wr["pit_refused"],
            # F5/F10: dollars from the TABLE, amendments superseded, no self/outside double count
            "lobbying_usd_by_ticker_period": lobbying_totals(
                [r for r in PF.read_table(TABLE, base) if r.get("row_id") in {x["row_id"] for x in rows}]),
            "latency_posted_minus_period_end": PF.latency_summary(
                [{"period_end": r["period_end"], "first_seen_utc": r["dt_posted"]}
                 for r in rows if r.get("period_end") and r.get("dt_posted")], "period_end"),
            "latency_first_seen_minus_posted": PF.latency_summary(wr["rows"], "posted_date"),
            "latency_note": ("posted minus period end is the filer's reporting lag (the LD-2 is due 20 "
                             "days after the quarter); first seen minus posted is ours"),
            "not_mapped_top": dict(sorted(not_mapped.items(), key=lambda kv: -kv[1])[:25]),
            "per_client": per, "refusals": refusals,
            "rate_limit": f"15 requests / minute anonymous; paced at {_config.LDA_MIN_GAP_S}s"}
    body["status"] = PF.pull_status(wr["written"], refusals, now, quiet_ok=True)
    if refusals and not rows:
        body["status"] = "REFUSED"
    elif not rows and targets:
        # a feed that ANSWERED with nothing for every target is not a quiet day
        body["status"] = "DEGRADED"
        body["degraded_why"] = "zero rows read across every requested target"
    body["receipt"] = str(PF.write_receipt(SOURCE, body, base, now))
    return body


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="lobbying_lda")
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--quarters", type=int, default=2)
    ap.add_argument("--limit-clients", type=int, default=None)
    a = ap.parse_args(argv)
    if not a.pull:
        ap.print_help()
        return 0
    r = pull(quarters=a.quarters, limit_clients=a.limit_clients)
    print(json.dumps({k: v for k, v in r.items() if k != "per_client"}, default=str, indent=1))
    return 0 if r["status"] == "OK" else 2


if __name__ == "__main__":
    sys.exit(main())
