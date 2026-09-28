"""Read the social hosts through the dedicated MuratClaw Chrome, READ-ONLY.

Murat, 2026-09-28: "dont read it too slow, while its waiting make it read other
pages then, reddit x and other socials are logged in too". The orchestrator's
brief, the same day: add reader lanes for x.com / reddit.com / stocktwits.com
"only as far as: load a ticker's search or community page, scroll, store the
visible text with the url, timestamp and host. No claim extraction."

* One lane per (host, ticker). A search is a NAVIGATION to a search URL
  (`web_reader.SOCIAL_URLS`), never typing; the client refuses a click, a
  non-scroll key, a write path or typing on a social host, on both transports.
* The next page goes to the lane whose HOST is free soonest
  (`web_reader.pick_next_lane`) -- the same-host floor is spent on another host.
* Pace and caps are the shared `Throttle` (current pace, config; the social
  hosts' own daily cap is `WEB_READER_MAX_PER_DAY_BY_HOST`, 150 each).
* Rows land in `news_corpus/social/<host>/<day>.jsonl` with
  `source_kind = "social"`: never an alert's origin, never an order's.
* The instance is PROVEN before any tab is opened (`instance_gate`), one tab
  per host is opened with `open_tab` and closed at the end whatever happened,
  and the yield check refuses a host that returns no text on every page.
* Refuses without `--handoff` AND the hand-over file, like the Dow Jones
  reader: X, Reddit and Dow Jones terms all restrict automated access, and
  reading with a signed-in account carries account risk (stated to Murat
  2026-09-28; his decision).

    python -m scripts.social_browser_pull --tickers NVDA,MU --hosts x.com,reddit.com,stocktwits.com --handoff
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402
from backend.services import web_reader as WR  # noqa: E402


def plan_lanes(tickers: list[str], hosts: list[str]) -> list[dict]:
    """PURE. One lane per (host, ticker), host-major, with its URL."""
    out = []
    for t in tickers:
        for h in hosts:
            out.append({"lane": f"{h}:{t.upper()}", "host": h, "ticker": t.upper(),
                        "url": WR.social_url(h, t)})
    return out


def run(lanes: list[dict], *, driver: Any = None, throttle: Any = None, profile: str = "muratclaw",
        max_pages: int = 30, root: Path | None = None, printer: Any = print) -> dict:
    """Read every lane once, host-aware order. Returns the receipt."""
    if driver is None:
        from backend.services import openclaw_client as driver  # type: ignore[no-redef]
    thr = throttle or WR.Throttle(WR.throttle_path(), wait_on_hour_cap=True)
    rc: dict[str, Any] = {"receipt": "social_browser_pull", "profile": profile, "rows": [],
                          "refusals": [], "opened": [], "closed": {}, "stopped": None,
                          "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    from scripts.dowjones_pull import instance_gate
    rc["instance"] = instance_gate(profile, driver)
    ychk = WR.YieldCheck(after=min(int(getattr(_config, "READER_YIELD_CHECK_AFTER", 10)),
                                   max(1, len(lanes))), printer=printer)
    rc["yield"] = ychk.reports
    readers: dict[str, WR.Reader] = {}
    todo = list(lanes)
    try:
        while todo and sum(r.pages for r in readers.values()) < max_pages:
            last = thr.last_load_by_host()
            nxt = WR.pick_next_lane([(ln["lane"], ln["host"]) for ln in todo], last,
                                    thr.now_fn(), float(thr.min_same_host_gap_s))
            ln = next(x for x in todo if x["lane"] == nxt)
            todo.remove(ln)
            rd = readers.get(ln["host"])
            try:
                if rd is None:
                    thr.acquire("open", host=ln["host"])
                    op = driver.open_tab(ln["url"], profile_name=profile)
                    rc["opened"].append(op["new_tab"])
                    rd = WR.Reader(profile=profile, tab=op["new_tab"], throttle=thr,
                                   driver=driver, lock=False, direct_open=True)
                    rd.pages, rd.tab_pages = 1, 1          # the open WAS the page load
                    rd._mark_loaded()
                    readers[ln["host"]] = rd
                    row = _read_current(rd, ln, root)
                else:
                    row = WR.read_social_page(rd, ln["url"], ticker=ln["ticker"], root=root)
                rc["rows"].append({k: row.get(k) for k in ("host", "ticker", "url", "chars",
                                                           "read_utc", "stored")})
                ychk.record(ln["host"], chars=row.get("chars"), kind="social")
            except WR.ReaderRefused as exc:
                if "REFUSED_ZERO_YIELD_LANE" in str(exc) or "THROTTLE_DAY" in str(exc):
                    raise
                rc["refusals"].append({"lane": ln["lane"], "why": str(exc)[:240]})
    except Exception as exc:  # noqa: BLE001 -- the receipt says why, tabs still close
        rc["stopped"] = f"{type(exc).__name__}: {str(exc)[:240]}"
    finally:
        for h, rd in readers.items():
            rc["closed"][rd.tab] = rd.close_tab()
            rd.close(write_footprint=False)
    if ychk.rows:
        try:
            ychk.check("end")
        except WR.ReaderRefused as exc:
            rc["stopped"] = rc["stopped"] or str(exc)[:240]
    rc["n_rows"] = len(rc["rows"])
    rc["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return rc


def _read_current(rd: WR.Reader, ln: dict, root: Path | None) -> dict:
    """The tab was OPENED at the lane's URL: scroll, read, store (no second load)."""
    import time as _t
    t0 = _t.time()
    steps = rd.scroll_through()
    got = rd.driver.read_text(rd.tab, profile_name=rd.profile)
    if got.get("error") or not (got.get("text") or "").strip():
        raise WR.ReaderRefused(f"REFUSED_EMPTY_READ: {ln['url']!r}")
    final = got.get("url") or ln["url"]
    if not WR.is_social(final):
        raise WR.ReaderRefused(f"REFUSED_LEFT_HOSTS: read landed on {final!r}")
    text = str(got.get("text") or "")
    row = {"source_kind": "social", "host": WR.host_of(final), "url": final,
           "requested_url": ln["url"], "ticker": ln["ticker"], "title": got.get("title"),
           "text": text, "chars": len(text),
           "read_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "scroll_steps": steps, "read_s": round(_t.time() - t0, 2), "tab": rd.tab,
           "profile": rd.profile, "never": ["alert_origin", "order"]}
    row["stored"] = str(WR.store_social(row, root=root))
    rd.blank()
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--hosts", default=",".join(WR.social_hosts()))
    ap.add_argument("--max-pages", type=int, default=30)
    ap.add_argument("--handoff", action="store_true")
    ap.add_argument("--profile", default="muratclaw")
    a = ap.parse_args(argv)
    hand = Path(getattr(_config, "DOWJONES_HANDOFF_FILE", REPO / "HANDOFF_PC"))
    if not a.handoff or not hand.exists():
        print(f"REFUSED_NO_HANDOFF: social reads need --handoff AND {hand} (Murat's act).")
        return 2
    hosts = [h.strip() for h in a.hosts.split(",") if h.strip()]
    bad = [h for h in hosts if h not in WR.social_hosts()]
    if bad:
        print(f"REFUSED_SOCIAL_HOST: {bad} not in {WR.social_hosts()}")
        return 2
    lanes = plan_lanes([t.strip() for t in a.tickers.split(",") if t.strip()], hosts)
    rc = run(lanes, profile=a.profile, max_pages=a.max_pages)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    out = WR.social_root() / f"social_browser_pull_{day}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rc, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"receipt": str(out), "n_rows": rc["n_rows"], "stopped": rc["stopped"],
                      "refusals": len(rc["refusals"])}, indent=1))
    return 0 if not rc["stopped"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
