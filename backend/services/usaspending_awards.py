"""USAspending.gov contract transactions by recipient -- a SENSOR, never a trade signal.

    python -m backend.services.usaspending_awards --pull [--mode modified|action] [--limit-recipients 10] [--days N]
    python -m backend.services.usaspending_awards --agency-months [--fiscal-years 3]
    python -m backend.services.usaspending_awards --aggregate     # month x agency, latest versions

WHAT (chunk C16, 2026-10-07; review fixes F1-F6, F12 the same day)
==================================================================
Contract TRANSACTIONS (award types A/B/C/D) for the hand-curated public
contractors in `backend/data/crosswalks/usaspending_recipient_ticker.yaml`, read
from `POST /api/v2/search/spending_by_transaction/` (no auth; documented limit
1,000 requests / 300 s, honoured with a 0.5 s gap and a rolling-day cap).

HOW A PULL READS (F1, F2)
-------------------------
* `--mode modified` (the DAILY default): the filter is the transaction's
  LAST-MODIFIED date over the last `USASPENDING_MODIFIED_LOOKBACK_DAYS`, so a
  DoD action published on its ~90-day delay is seen the day it is published.
  Rows are stored when their action date is inside the rolling
  `USASPENDING_ACTION_WINDOW_DAYS` (older modifications are counted only).
* `--mode action`: an action-date window (a backfill).
* Pages are sorted on `USASPENDING_SORT` ("Award ID"): an "Action Date" sort
  ties, and a tied sort served 2 GD rows twice and 2 never (measured).
* Every recipient is RECONCILED: distinct identities read must equal
  `spending_by_transaction_count` for the same filter. On a mismatch the
  recipient is re-read once in the opposite order and unioned; if it still does
  not reconcile it is REFUSED and none of its rows are written (a partial
  recipient would make its dollar totals silently wrong).

ONE ROW PER TRANSACTION IDENTITY (F4)
-------------------------------------
`identity = usaspending:<generated_internal_id>|<Mod>` (the award plus its
modification number; the API exposes no transaction id, and `internal_id` is the
AWARD's id). The amount is never part of the key. A later read of the same
identity with different content is a REVISION (`<identity>#v<k>`, `supersedes`
the previous version); totals read `latest_versions` only.

| field | meaning |
|---|---|
| action_date | the transaction's action date -- the EVENT date (NOT public then) |
| first_seen_utc | when this collector first held the row -- the PIT stamp |
| public_utc / public_ts_basis | = first_seen_utc / `FIRST_SEEN_BY_COLLECTOR` (the endpoint carries no publication time) |
| modified_window | the last-modified window the row was found in (`mode modified`) |
| latency | `NOT_MEASURABLE_BACKFILL` on a recipient's first contact or an action-mode pull (F3): every row then shares one first_seen, and "first seen minus action date" is the age of the window, not a latency |
| ticker, crosswalk_confidence, crosswalk_pattern, match_status | the crosswalk join, using only entries valid on the action date |

`--agency-months` snapshots `spending_over_time` (group by month) per awarding
toptier agency. Each row carries its fetch date (`snapshot_date`), `partial`
(the month had not ended) and `settled` (fetch date >= month end +
`USASPENDING_SETTLE_DAYS`: 100 for DoD, 45 otherwise). `agency_months_as_of(t)`
returns, per agency, the latest snapshot fetched on or before `t` -- the only
reader a backtest may use; `q4_share` refuses rows from more than one snapshot.

WHAT IT IS NOT: not a signal, not a feature in any scoring path, not an order
path.

FAILURE CONTRACT: an HTTP refusal is a REFUSED step with its class; zero new
rows on a US weekday that is not a federal holiday is DEGRADED; a recipient
whose expected activity is >= `USASPENDING_EXPECTED_ROWS_FLOOR` rows and that
returns zero is DEGRADED; an identity repeated inside one read is DEGRADED, never
"duplicate"; an action date after first_seen is refused (PIT).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from backend import config as _config
from backend.services import public_flow_common as PF

SOURCE = "usaspending"
TABLE = "gov_awards"
AGENCY_TABLE = "gov_agency_month_obligations"
IDENTITY = "identity"
CONTENT_FIELDS = ("action_date", "action_type", "obligation_usd", "agency", "sub_agency", "naics",
                  "psc", "recipient", "recipient_uei", "award_type", "description")
BANNER = ("SENSOR -- federal contract dollars with provenance and latency; never a trade "
          "signal on its own; no scoring path reads it before a declared cell passes")
FIELDS = ["Award ID", "Recipient Name", "Recipient UEI", "Action Date", "Action Type",
          "Transaction Amount", "Awarding Agency", "Awarding Sub Agency", "Award Type",
          "Transaction Description", "naics_code", "naics_description", "Mod",
          "generated_internal_id", "internal_id", "PSC"]
FATAL = ("ACCESS_DENIED", "BOT_CHECK", "RATE_LIMITED", "DAY_CAP")


def client(base: Optional[Path] = None, http=None, sleep_fn=None) -> PF.Client:
    kw = {} if sleep_fn is None else {"sleep_fn": sleep_fn}
    return PF.Client(source=SOURCE, min_gap_s=float(_config.USASPENDING_MIN_GAP_S),
                     day_cap=int(_config.USASPENDING_DAY_CAP), base=base, http=http, **kw)


# ───────────────────────────── parse (PURE) ──────────────────────────────────

def _num(x: Any) -> Optional[float]:
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def identity_of(t: dict) -> Optional[str]:
    """PURE. The transaction's identity: award + modification number. Never the
    amount (a correction would become a second row) and never `internal_id`
    alone (it is the award's id: 129 rows, 102 ids for one recipient)."""
    gid = t.get("generated_internal_id")
    if not gid:
        return None
    return f"usaspending:{gid}|{t.get('Mod') if t.get('Mod') is not None else ''}"


def parse_transactions(payload: dict, crosswalk: list[dict], *, search_text: str = "") -> list[dict]:
    """PURE. One row per transaction of a `spending_by_transaction` page."""
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise PF.PublicFlowRefused("MALFORMED_PAYLOAD: no `results` list")
    out = []
    for t in payload["results"]:
        ident = identity_of(t)
        if ident is None:
            continue
        psc = t.get("PSC") if isinstance(t.get("PSC"), dict) else {}
        m = PF.match_entity(t.get("Recipient Name"), crosswalk, "recipient_patterns",
                            uei=t.get("Recipient UEI"), on=t.get("Action Date"))
        out.append({
            IDENTITY: ident, "award_internal_id": t.get("internal_id"), "source": SOURCE,
            "action_date": t.get("Action Date"),
            "public_ts_basis": "FIRST_SEEN_BY_COLLECTOR",
            "recipient": t.get("Recipient Name"), "recipient_uei": t.get("Recipient UEI"),
            "agency": t.get("Awarding Agency"), "sub_agency": t.get("Awarding Sub Agency"),
            "naics": t.get("naics_code"), "naics_description": t.get("naics_description"),
            "psc": psc.get("code"), "obligation_usd": _num(t.get("Transaction Amount")),
            "award_type": t.get("Award Type"), "action_type": t.get("Action Type"),
            "mod": t.get("Mod"), "award_id": t.get("Award ID"),
            "generated_internal_id": t.get("generated_internal_id"),
            "description": (t.get("Transaction Description") or "")[:400],
            "search_text": search_text, **m})
    return out


def fiscal_to_calendar(fy: int, fiscal_month: int) -> tuple[int, int]:
    """PURE. US federal FY: fiscal month 1 = October of fy-1."""
    cal_m = (fiscal_month + 8) % 12 + 1
    return (fy - 1 if fiscal_month <= 3 else fy), cal_m


def settle_days(agency: str) -> int:
    d = dict(_config.USASPENDING_SETTLE_DAYS)
    return int(d.get(agency, d.get("_default", 45)))


def parse_agency_months(payload: dict, agency: str, snapshot_date: str) -> list[dict]:
    """PURE. `spending_over_time` (group=month) -> one row per (agency, FY month),
    with `partial` and `settled` judged against the fetch date (F6)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise PF.PublicFlowRefused("MALFORMED_PAYLOAD: no `results` list")
    snap = PF.parse_date(snapshot_date)
    if snap is None:
        raise PF.PublicFlowRefused(f"NO_SNAPSHOT_DATE: {snapshot_date!r}")
    out = []
    for r in payload["results"]:
        tp = r.get("time_period") or {}
        try:
            fy, fm = int(tp.get("fiscal_year")), int(tp.get("month"))
        except (TypeError, ValueError):
            continue
        cy, cm = fiscal_to_calendar(fy, fm)
        pend = date.fromisoformat(_month_end(cy, cm))
        sd = settle_days(agency)
        out.append({
            IDENTITY: f"usa_aom:{agency}:{fy}-{fm:02d}:{snapshot_date}", "source": SOURCE,
            "agency": agency, "fiscal_year": fy, "fiscal_month": fm,
            "calendar_month": f"{cy}-{cm:02d}", "period_start": f"{cy}-{cm:02d}-01",
            "period_end": pend.isoformat(),
            "contract_obligations_usd": _num(r.get("Contract_Obligations")
                                             if r.get("Contract_Obligations") is not None
                                             else r.get("aggregated_amount")),
            "snapshot_date": snapshot_date, "fy_q4": fm >= 10,
            "partial": snap <= pend,
            "settle_days": sd, "settled": snap >= pend + timedelta(days=sd),
            "public_ts_basis": "FIRST_SEEN_BY_COLLECTOR (a month total REVISES as late reports land)"})
    return out


def _month_end(y: int, m: int) -> str:
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return (nxt - timedelta(days=1)).isoformat()


def latest_rows(base: Optional[Path] = None) -> list[dict]:
    """The transaction table, latest version per identity (what totals read)."""
    return PF.latest_versions(PF.read_table(TABLE, base), IDENTITY)


def aggregate_month_agency(rows: list[dict], *, mapped_only: bool = True) -> list[dict]:
    """PURE. Obligations by (action month, agency) over the LATEST version of
    each identity (a revision supersedes; never summed across versions)."""
    agg: dict[tuple, dict] = {}
    for r in PF.latest_versions(rows, IDENTITY):
        if mapped_only and r.get("match_status") != "MAPPED":
            continue
        d = PF.parse_date(r.get("action_date"))
        if d is None:
            continue
        k = (f"{d.year}-{d.month:02d}", r.get("agency") or "UNKNOWN")
        a = agg.setdefault(k, {"month": k[0], "agency": k[1], "obligation_usd": 0.0, "n": 0,
                               "tickers": set()})
        a["obligation_usd"] += float(r.get("obligation_usd") or 0.0)
        a["n"] += 1
        if r.get("ticker"):
            a["tickers"].add(r["ticker"])
    return [{**a, "obligation_usd": round(a["obligation_usd"], 2), "tickers": sorted(a["tickers"])}
            for _, a in sorted(agg.items())]


def agency_months_as_of(as_of: Any, rows: Optional[list[dict]] = None,
                        base: Optional[Path] = None) -> list[dict]:
    """The ONLY history reader (F6): per agency, the rows of the latest snapshot
    FETCHED on or before `as_of`. A snapshot fetched later can never change an
    earlier as-of read. An unparseable as-of refuses."""
    t = PF.parse_date(as_of)
    if t is None:
        raise PF.PublicFlowRefused(f"NO_AS_OF: {as_of!r}")
    rows = PF.read_table(AGENCY_TABLE, base) if rows is None else rows
    best: dict[str, str] = {}
    for r in rows:
        s = str(r.get("snapshot_date") or "")
        if s and s <= t.isoformat() and s > best.get(r.get("agency"), ""):
            best[r.get("agency")] = s
    return [r for r in rows if r.get("agency") in best
            and str(r.get("snapshot_date")) == best[r.get("agency")]]


def q4_share(rows: list[dict]) -> dict:
    """PURE. Per (agency, FY) in ONE snapshot: the share of the FY's obligations in
    fiscal Q4 (Jul-Sep). Refuses rows from more than one snapshot (summing
    vintages averages revisions). `settled` = every month of the FY settled; an
    unsettled share is a LOWER bound, not a reading."""
    snaps = {str(r.get("snapshot_date")) for r in rows}
    if len(snaps) > 1:
        raise PF.PublicFlowRefused(f"MIXED_SNAPSHOTS: q4_share got {len(snaps)} snapshots; "
                                   f"read one (agency_months_as_of)")
    by: dict[tuple, dict] = {}
    for r in rows:
        k = (r["agency"], r["fiscal_year"])
        a = by.setdefault(k, {"total": 0.0, "q4": 0.0, "months": set(), "settled": True,
                              "partial": False})
        v = float(r.get("contract_obligations_usd") or 0.0)
        a["total"] += v
        a["months"].add(r["fiscal_month"])
        a["settled"] = a["settled"] and bool(r.get("settled"))
        a["partial"] = a["partial"] or bool(r.get("partial"))
        if r.get("fy_q4"):
            a["q4"] += v
    out = {}
    for (ag, fy), a in sorted(by.items()):
        out.setdefault(ag, {})[str(fy)] = {
            "q4_share": round(a["q4"] / a["total"], 4) if a["total"] > 0 else None,
            "months": len(a["months"]), "complete": len(a["months"]) == 12,
            "settled": a["settled"] and len(a["months"]) == 12, "has_partial_month": a["partial"]}
    return out


# ───────────────────────────── fetch ─────────────────────────────────────────

def search_texts(crosswalk: list[dict], since: Optional[date] = None,
                 tickers: Optional[set] = None) -> list[dict]:
    """One search per crosswalk entry valid at some point on/after `since`: its
    first recipient pattern (the API matches it as free text, parents included;
    our dated matcher assigns the ticker). `tickers` narrows to those symbols."""
    out, seen = [], set()
    for e in crosswalk:
        if tickers and e["ticker"] not in tickers:
            continue
        if since is not None and e.get("valid_to") and PF.parse_date(e["valid_to"]) < since:
            continue
        for pat in e.get("recipient_patterns") or []:
            if pat not in seen:
                seen.add(pat)
                out.append({"ticker": e["ticker"], "text": pat})
            break
    return out


def _filters(text: str, start: date, end: date, mode: str) -> dict:
    tp: dict = {"start_date": start.isoformat(), "end_date": end.isoformat()}
    if mode == "modified":
        tp["date_type"] = "last_modified_date"
    return {"recipient_search_text": [text],
            "award_type_codes": list(_config.USASPENDING_CONTRACT_TYPES), "time_period": [tp]}


def _read_pages(c: PF.Client, flt: dict, crosswalk: list[dict], text: str, max_pages: int,
                order: str) -> tuple[list[dict], int, bool]:
    url = f"{_config.USASPENDING_API_BASE}/search/spending_by_transaction/"
    rows, pages = [], 0
    while True:
        pages += 1
        payload = c.request_json("POST", url, body={
            "filters": flt, "fields": FIELDS, "limit": int(_config.USASPENDING_PAGE_LIMIT),
            "page": pages, "sort": _config.USASPENDING_SORT, "order": order})
        rows.extend(parse_transactions(payload, crosswalk, search_text=text))
        if not (payload.get("page_metadata") or {}).get("hasNext"):
            return rows, pages, False
        if pages >= max_pages:
            return rows, pages, True


def count_of(c: PF.Client, flt: dict) -> int:
    d = c.request_json("POST", f"{_config.USASPENDING_API_BASE}/search/spending_by_transaction_count/",
                       body={"filters": flt})
    try:
        return int(((d or {}).get("results") or {}).get("contracts"))
    except (TypeError, ValueError) as exc:
        raise PF.PublicFlowRefused("MALFORMED_COUNT: no results.contracts") from exc


def fetch_recipient(c: PF.Client, text: str, start: date, end: date, crosswalk: list[dict],
                    max_pages: int, mode: str = "action") -> dict:
    """Read, count, reconcile. `status` OK / REFUSED_UNRECONCILED / REFUSED_TRUNCATED."""
    flt = _filters(text, start, end, mode)
    rows, pages, trunc = _read_pages(c, flt, crosswalk, text, max_pages, "desc")
    n_api = count_of(c, flt)
    raw_read = len(rows)
    by_id: dict[str, dict] = {}
    repeats = 0
    for r in rows:
        if r[IDENTITY] in by_id:
            repeats += 1
        by_id.setdefault(r[IDENTITY], r)
    retried = False
    if (len(by_id) != n_api or repeats) and not trunc:
        retried = True                               # one re-read in the opposite order, unioned
        rows2, _, trunc = _read_pages(c, flt, crosswalk, text, max_pages, "asc")
        for r in rows2:
            by_id.setdefault(r[IDENTITY], r)
    status = ("REFUSED_TRUNCATED" if trunc else
              "OK" if len(by_id) == n_api else "REFUSED_UNRECONCILED")
    return {"rows": list(by_id.values()) if status == "OK" else [], "rows_read_raw": raw_read,
            "distinct_read": len(by_id), "api_count": n_api, "repeats_in_first_read": repeats,
            "retried_opposite_order": retried, "pages": pages, "status": status}


def _prior_by_target(base: Optional[Path], since: date) -> dict[str, int]:
    """Rows per search target with an action date on or after `since` (for the
    expected-activity floor) -- and which targets have ANY prior row."""
    out: dict[str, int] = {}
    for r in latest_rows(base):
        t = r.get("search_text") or ""
        d = PF.parse_date(r.get("action_date"))
        out.setdefault(t, 0)
        if d is not None and d >= since:
            out[t] += 1
    return out


def pull(*, mode: str = "modified", days: Optional[int] = None, limit_recipients: Optional[int] = None,
         tickers: Optional[list[str]] = None, base: Optional[Path] = None, http=None, sleep_fn=None, now: Optional[datetime] = None,
         crosswalk_path: Optional[Path] = None, max_pages: Optional[int] = None) -> dict:
    """Read the crosswalk's recipients, reconcile each against the count
    endpoint, append new identities and revisions, write one receipt."""
    if mode not in ("modified", "action"):
        raise PF.PublicFlowRefused(f"BAD_MODE: {mode!r}")
    now = now or PF.now_utc()
    cw = PF.load_crosswalk(crosswalk_path)             # refuses loudly: nothing to match against
    c = client(base, http, sleep_fn)
    end = now.date()
    days = int(days if days is not None else (_config.USASPENDING_MODIFIED_LOOKBACK_DAYS
                                              if mode == "modified" else 90))
    start = end - timedelta(days=days)
    targets = search_texts(cw, since=start if mode == "action" else end - timedelta(
        days=int(_config.USASPENDING_ACTION_WINDOW_DAYS)),
        tickers={t.upper() for t in tickers} if tickers else None)[: limit_recipients or None]
    action_floor = end - timedelta(days=int(_config.USASPENDING_ACTION_WINDOW_DAYS))
    prior = _prior_by_target(base, end - timedelta(days=90))
    # F3: a row first seen now is a publication-lag reading only if its action date
    # lies inside a window this target was ALREADY read over (else we simply never
    # looked there before, and "first seen minus action date" measures our coverage)
    coverage: dict[str, str] = {}
    for r0 in latest_rows(base):
        t0, d0 = r0.get("search_text") or "", str(r0.get("action_date") or "")
        if d0 and (t0 not in coverage or d0 < coverage[t0]):
            coverage[t0] = d0
    mp = int(max_pages or _config.USASPENDING_MAX_PAGES_PER_RECIPIENT)
    per, refusals, keep = {}, [], []
    outside_window = 0
    for t in targets:
        try:
            r = fetch_recipient(c, t["text"], start, end, cw, mp, mode)
        except PF.PublicFlowRefused as exc:
            fatal = str(exc).split(":")[0] in FATAL
            refusals.append({"step": t["text"], "why": str(exc)[:300], "fatal": fatal})
            per[t["text"]] = {"ticker": t["ticker"], "status": "REFUSED", "why": str(exc)[:200]}
            if fatal:
                break                                 # do not hammer a host that refused us
            continue
        backfill = mode == "action" or t["text"] not in prior
        rows = []
        for x in r["rows"]:
            d = PF.parse_date(x.get("action_date"))
            if mode == "modified" and (d is None or d < action_floor):
                outside_window += 1
                continue
            x["pull_mode"] = mode
            x["modified_window"] = ([start.isoformat(), end.isoformat()] if mode == "modified" else None)
            if backfill:
                x["latency"] = PF.BACKFILL_LATENCY
            elif str(x.get("action_date") or "") < coverage.get(t["text"], ""):
                x["latency"] = PF.BEFORE_COVERAGE_LATENCY
            rows.append(x)
        keep.extend(rows)
        st = dict.fromkeys(("MAPPED", "NOT_MAPPED", "AMBIGUOUS"), 0)
        for x in rows:
            st[x["match_status"]] = st.get(x["match_status"], 0) + 1
        expected = (prior.get(t["text"], 0) * days / 90.0) if t["text"] in prior else None
        tstat = r["status"]
        why = ""
        if tstat == "OK" and r["api_count"] == 0:
            if expected is not None and expected >= float(_config.USASPENDING_EXPECTED_ROWS_FLOOR):
                tstat, why = "DEGRADED_ZERO_ROWS", f"0 rows vs ~{expected:.0f} expected from the prior 90 days"
            elif t["text"] not in prior and days >= 60:
                tstat, why = "DEGRADED_ZERO_ROWS", f"0 rows in a {days}-day first contact"
        if r["status"] != "OK":
            why = (f"distinct read {r['distinct_read']} vs API count {r['api_count']}"
                   + ("; truncated at max pages" if r["status"] == "REFUSED_TRUNCATED" else "")
                   + "; NO rows written for this recipient")
            refusals.append({"step": t["text"], "why": f"{r['status']}: {why}", "fatal": False})
        per[t["text"]] = {"ticker": t["ticker"], "status": tstat, "why": why,
                          "rows_read_raw": r["rows_read_raw"], "distinct_read": r["distinct_read"],
                          "api_count": r["api_count"], "repeats_in_first_read": r["repeats_in_first_read"],
                          "retried_opposite_order": r["retried_opposite_order"], "pages": r["pages"],
                          "stored": len(rows), "backfill": backfill, "match": st,
                          "uei_seen": sorted({x["recipient_uei"] for x in rows
                                              if x.get("recipient_uei") and x.get("match_status") == "MAPPED"})}
    # the same transaction found by two searches (a parent text matches several
    # entries) is ONE row; counted, not an anomaly. A repeat INSIDE one recipient's
    # read is the anomaly, and fetch_recipient reconciles or refuses it.
    uniq: dict[str, dict] = {}
    for x in keep:
        uniq.setdefault(x[IDENTITY], x)
    cross_target_overlap = len(keep) - len(uniq)
    keep = list(uniq.values())
    wr = PF.append_versioned(TABLE, keep, identity_field=IDENTITY, content_fields=CONTENT_FIELDS,
                             event_field="action_date", base=base, now=now)
    # F5: dollars from the TABLE (latest version per identity), never from the read
    read_ids = {x[IDENTITY] for x in keep}
    latest = latest_rows(base)
    pulled = [r for r in latest if r[IDENTITY] in read_ids and r.get("match_status") == "MAPPED"]
    not_mapped: dict[str, int] = {}
    for r in keep:
        if r["match_status"] != "MAPPED":
            k = f"{r['match_status']}:{r.get('recipient')}"
            not_mapped[k] = not_mapped.get(k, 0) + 1
    by_conf: dict[str, int] = {}
    for r in pulled:
        by_conf[r["crosswalk_confidence"]] = by_conf.get(r["crosswalk_confidence"], 0) + 1
    dates = sorted(r["action_date"] for r in keep if r.get("action_date"))
    body = {"banner": BANNER, "mode": mode,
            "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days,
                       "date_type": "last_modified_date" if mode == "modified" else "action_date",
                       "action_window_from": action_floor.isoformat() if mode == "modified" else None},
            "recipients_requested": len(targets), "requests": c.n_requests,
            "request_classes": c.statuses, "rows_stored_candidates": len(keep),
            "outside_action_window": outside_window, "cross_target_overlap": cross_target_overlap,
            "rows_added": wr["written"] - wr["revisions"], "revisions": wr["revisions"],
            "unchanged": wr["unchanged"], "in_call_repeats": wr["in_call_repeats"],
            "pit_refused": wr["pit_refused"],
            "action_date_range": [dates[0], dates[-1]] if dates else None,
            "mapped_by_confidence": by_conf,
            "obligation_usd_mapped_this_pull": round(sum(float(r.get("obligation_usd") or 0)
                                                         for r in pulled), 2),
            "obligation_basis": "latest version per identity in the table, identities read this pull",
            "latency_first_seen_minus_action": PF.latency_summary(
                [r for r in wr["rows"] if r.get("match_status") == "MAPPED"], "action_date"),
            "not_mapped_top": dict(sorted(not_mapped.items(), key=lambda kv: -kv[1])[:25]),
            "per_recipient": per, "refusals": refusals,
            "rate_limit": "1,000 requests / 300 s documented; paced at "
                          f"{_config.USASPENDING_MIN_GAP_S}s per request"}
    st = PF.pull_status(wr["written"], refusals, now)
    bad_targets = [k for k, v in per.items() if v.get("status") != "OK"]
    if st == "OK" and (bad_targets or wr["in_call_repeats"]):
        st = "DEGRADED"
    if refusals and not keep:
        st = "REFUSED"
    elif not keep and targets and st == "OK":
        st = "DEGRADED"
        body["degraded_why"] = "zero rows read across every requested target"
    if bad_targets:
        body["degraded_targets"] = {k: per[k].get("status") for k in bad_targets}
    body["status"] = st
    body["receipt"] = str(PF.write_receipt(SOURCE, body, base, now))
    return body


def pull_agency_months(*, fiscal_years: int = 3, agencies: Optional[tuple] = None,
                       base: Optional[Path] = None, http=None, sleep_fn=None,
                       now: Optional[datetime] = None) -> dict:
    """Month x toptier-agency contract obligations, snapshotted at the fetch date."""
    now = now or PF.now_utc()
    snap = now.date().isoformat()
    c = client(base, http, sleep_fn)
    cur_fy = now.year + (1 if now.month >= 10 else 0)
    start = date(cur_fy - int(fiscal_years), 10, 1)
    rows, refusals = [], []
    url = f"{_config.USASPENDING_API_BASE}/search/spending_over_time/"
    for ag in (agencies or _config.USASPENDING_AGENCIES):
        body = {"group": "month",
                "filters": {"time_period": [{"start_date": start.isoformat(), "end_date": snap}],
                            "agencies": [{"type": "awarding", "tier": "toptier", "name": ag}],
                            "award_type_codes": list(_config.USASPENDING_CONTRACT_TYPES)}}
        try:
            rows.extend(parse_agency_months(c.request_json("POST", url, body=body), ag, snap))
        except PF.PublicFlowRefused as exc:
            refusals.append({"step": ag, "why": str(exc)[:300], "fatal": False})
    for r in rows:
        r["row_id"] = r[IDENTITY]
    # PIT (F6): a month that had not STARTED by the fetch date cannot be in it
    wr = PF.append_rows(AGENCY_TABLE, rows, event_field="period_start", base=base, now=now)
    body = {"banner": BANNER, "snapshot_date": snap, "fiscal_years": int(fiscal_years),
            "agencies": list(agencies or _config.USASPENDING_AGENCIES), "requests": c.n_requests,
            "rows_read": len(rows), "rows_added": wr["written"], "duplicates": wr["duplicate"],
            "pit_refused": wr["pit_refused"],
            "n_partial": sum(bool(r["partial"]) for r in rows),
            "n_unsettled": sum(not r["settled"] for r in rows),
            "fy_q4_share": q4_share(rows) if rows else {}, "refusals": refusals}
    body["status"] = "REFUSED" if refusals and not rows else ("DEGRADED" if refusals or not rows
                                                              else "OK")
    body["receipt"] = str(PF.write_receipt(f"{SOURCE}_agency_months", body, base, now))
    return body


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="usaspending_awards")
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--mode", choices=("modified", "action"), default="modified")
    ap.add_argument("--agency-months", action="store_true")
    ap.add_argument("--aggregate", action="store_true")
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--limit-recipients", type=int, default=None)
    ap.add_argument("--tickers", default="", help="comma-separated tickers to pull (default: all)")
    ap.add_argument("--fiscal-years", type=int, default=3)
    a = ap.parse_args(argv)
    rc = 0
    if a.pull:
        r = pull(mode=a.mode, days=a.days, limit_recipients=a.limit_recipients,
                 tickers=[t for t in a.tickers.split(",") if t.strip()] or None)
        print(json.dumps({k: v for k, v in r.items() if k != "per_recipient"}, default=str, indent=1))
        rc = max(rc, 0 if r["status"] == "OK" else 2)
    if a.agency_months:
        r = pull_agency_months(fiscal_years=a.fiscal_years)
        print(json.dumps(r, default=str, indent=1))
        rc = max(rc, 0 if r["status"] == "OK" else 2)
    if a.aggregate:
        print(json.dumps(aggregate_month_agency(PF.read_table(TABLE)), default=str, indent=1))
    if not (a.pull or a.agency_months or a.aggregate):
        ap.print_help()
    return rc


if __name__ == "__main__":
    sys.exit(main())
