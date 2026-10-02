"""THE SHADOW SCOREBOARD — every shadow book read the way its registration says.

    python -m scripts.shadow_grade            # human lines
    python -m scripts.shadow_grade --json     # + one `<<<{...}>>>` line (daily pass)

Why this exists (2026-09-30). The daily pass grades every frozen book in
`llm_portfolio/books.jsonl`, but

* SHADOW_NEWS_v0 (contract f3b149ea42311760) is not a frozen book: it is a daily
  TILT of the SHADOW_BAYES_v0 sleeve, written per world digest to
  `news_digest/shadow/decisions.jsonl`, and its contract's own grading line is
  "sum_i (w'_i - w_i) x r_i over the next 5 and 20 sessions, read vs zero by
  date block". Nothing computed that, so its forward record would never have
  been graded. It is graded HERE, from the contract file (read, never edited);
* the leaderboard prints each book's NAV and a vs_<twin> column, but not the
  registered statistic (sleeve scale), nor the kill line -- which for
  CRSP_BLEND_v0 is the AMENDED one (2026-09-29), not the registration's.

So this reads the leaderboard `grade_books` has just written plus the bars, and
prints, per shadow book: D vs its registered twin, D vs the market, the session
count, the read sessions and the kill line with where it came from. Before a
read session it says READ_NOT_DUE: one session says nothing, and the receipt
says so in words.

No LLM, no network, no order. Out of process from the daily pass.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config        # noqa: E402

LEDGER = Path(_config.OPTIMUS_LEDGER_DIR)
SB_DIR = LEDGER / "shadow_bayes"
NEWS_DIR = LEDGER / "news_digest" / "shadow"
LB_DIR = LEDGER / "llm_portfolio"

#: The registered shadow books. Each field is READ from the named files at run
#: time; this table only says which files and which twin is primary.
BOOKS: tuple[dict, ...] = (
    {"name": "SHADOW_BAYES_v0", "registration": "REGISTRATION_SHADOW_BAYES_v0_2026-09-28.json",
     "amendment": "AMENDMENT_SHADOW_BAYES_v0_2026-09-29.json",
     "primary_twin": "random_same_band", "read_sessions": [21, 63], "kill_session": 63},
    {"name": "SHADOW_BAYES_v1", "registration": "REGISTRATION_SHADOW_BAYES_v1_2026-09-28_20260929T032138Z.json",
     "amendment": None, "primary_twin": "matched_twin21", "read_sessions": [21, 63],
     "kill_session": 63},
    {"name": "CRSP_BLEND_v0", "registration": "REGISTRATION_CRSP_BLEND_v0_2026-09-28_20260929T082258Z.json",
     "amendment": "AMENDMENT_CRSP_BLEND_v0_KILL_RULE_2026-09-29.json",
     "primary_twin": "matched_twin21", "read_sessions": [21, 63, 126], "kill_session": 126},
)
NEWS_CONTRACT = "CONTRACT_SHADOW_NEWS_v0.json"
NEWS_HORIZONS = (5, 20)
ONE_SESSION_SAYS_NOTHING = ("a forward reading of fewer sessions than the first read date is "
                            "reported, never read: it says nothing yet")


def _load(p: Path) -> Optional[dict]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def latest_leaderboard(lb_dir: Path = LB_DIR) -> tuple[Optional[Path], Optional[dict]]:
    """The leaderboard with the newest `graded_utc` (by its own stamp, not mtime)."""
    best: tuple[str, Optional[Path], Optional[dict]] = ("", None, None)
    for p in lb_dir.glob("leaderboard_*.json"):
        d = _load(p)
        if d and str(d.get("graded_utc") or "") > best[0]:
            best = (str(d["graded_utc"]), p, d)
    return best[1], best[2]


def _sleeve_weight(book: dict) -> float:
    """1 - the SPY leg: the scale on which the registered statistic is stated."""
    spy = sum(float(p.get("weight") or 0) for p in book.get("positions") or []
              if p.get("ticker") == "SPY")
    return max(1e-9, 1.0 - spy)


def kill_line_of(spec: dict, reg: dict, amd: Optional[dict]) -> dict:
    """The kill line in force and where it came from (the amendment wins)."""
    if amd and isinstance(amd.get("kill_rule"), dict) and amd["kill_rule"].get("kill_line") is not None:
        return {"kill_line": float(amd["kill_rule"]["kill_line"]), "rule": amd["kill_rule"].get("rule"),
                "source": f"{spec['amendment']} (AMENDED 2026-09-29; replaces the registration's line)",
                "bands_by_session": (amd.get("reading_schedule") or {}).get("by_session")}
    ps = reg.get("primary_statistic")
    if isinstance(ps, dict) and "kill_if" in ps:
        try:
            line = float(str(ps["kill_if"]).rsplit("=", 1)[1])
        except (IndexError, ValueError):
            line = None
        return {"kill_line": line, "rule": ps["kill_if"], "source": spec["registration"],
                "reading": ps.get("reading")}
    return {"kill_line": 0.0 if "trails" in str(reg.get("kill_rule")) else None,
            "rule": reg.get("kill_rule"), "source": spec["registration"],
            "caveat": next((w.get("reading") for w in (amd or {}).get("weaknesses") or []
                            if w.get("id") == "KILL_RULE_HAS_NO_POWER"), None)}


def grade_book(spec: dict, lb: dict, books: dict[str, dict], sb_dir: Path = SB_DIR) -> dict:
    reg = _load(sb_dir / spec["registration"])
    if reg is None:
        return {"name": spec["name"], "status": "REFUSED", "why": f"registration {spec['registration']} unreadable"}
    amd = _load(sb_dir / spec["amendment"]) if spec.get("amendment") else None
    bid = reg["book_id"]
    tid = reg.get("twin_book_id") or (reg.get("twins") or {}).get(spec["primary_twin"])
    rows = {r["book_id"]: r for r in lb.get("books") or []}
    b, t = rows.get(bid), rows.get(tid)
    out: dict[str, Any] = {"name": spec["name"], "book_id": bid, "twin_book_id": tid,
                           "primary_twin": spec["primary_twin"],
                           "kill": kill_line_of(spec, reg, amd),
                           "read_sessions": spec["read_sessions"], "kill_session": spec["kill_session"]}
    if b is None or t is None:
        out.update(status="REFUSED", why="book or twin absent from the leaderboard")
        return out
    if b.get("status") != "OK" or t.get("status") != "OK":
        out.update(status=str(b.get("status")), why=b.get("why") or t.get("why"))
        return out
    scale = _sleeve_weight(books.get(bid) or {})
    nav_gap = float(b["net_to_date"]) - float(t["net_to_date"])
    s = int(b.get("sessions") or 0)
    out.update(sessions=s, book_net=b["net_to_date"], twin_net=t["net_to_date"],
               market_net=b.get("benchmark_to_date"), vs_market=b.get("vs_benchmark"),
               nav_gap_vs_twin=nav_gap, sleeve_weight=scale,
               D_vs_twin_sleeve_scale=nav_gap / scale)
    first = min(spec["read_sessions"])
    if s < first:
        out.update(status="READ_NOT_DUE", reading=f"session {s} of {first} (first read); "
                   + ONE_SESSION_SAYS_NOTHING)
    elif s < spec["kill_session"]:
        out.update(status="REPORT_ONLY", reading=f"session {s}; the kill look is at {spec['kill_session']}")
    else:
        line = out["kill"].get("kill_line")
        D = out["D_vs_twin_sleeve_scale"]
        out.update(status="KILL_LOOK", verdict=("FAILED_VARIANT" if line is not None and D < line
                                                 else "CANNOT_DISTINGUISH"))
    return out


# ───────────────────────────── SHADOW_NEWS_v0 ──────────────────────────────

def _bars_for(symbols: set[str]):
    import pandas as pd
    from backend.services import xs_ranker as XR
    frames = []
    for p in XR.survivorship_free_paths():
        if Path(p).exists():
            frames.append(pd.read_parquet(p, columns=["symbol", "date", "open", "close"],
                                          filters=[("symbol", "in", sorted(symbols))]))
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["symbol", "date", "open", "close"])
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    return df.drop_duplicates(["symbol", "date"], keep="last")


def _session_open_utc(day) -> datetime:
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    return datetime(day.year, day.month, day.day, 9, 30, tzinfo=et).astimezone(timezone.utc)


def grade_news(news_dir: Path = NEWS_DIR, bars=None) -> dict:
    """The contract's own statistic, per entry session: the LAST decision written
    before that session's 09:30 ET open is the one in force; D_h = sum_i
    (w'_i - w_i) x r_i with r_i = close(h-th session) / open(entry) - 1."""
    import pandas as pd
    c = _load(news_dir / NEWS_CONTRACT)
    if c is None:
        return {"name": "SHADOW_NEWS_v0", "status": "REFUSED", "why": "contract file unreadable"}
    out: dict[str, Any] = {"name": "SHADOW_NEWS_v0", "contract_hash": c.get("contract_hash"),
                           "grading_rule": c.get("grading"), "twin": c.get("matched_twin"),
                           "horizons": list(NEWS_HORIZONS)}
    decs = []
    p = news_dir / "decisions.jsonl"
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("contract_hash") == c.get("contract_hash"):
                decs.append(r)
    out["n_decisions"] = len(decs)
    if not decs:
        out.update(status="NOTHING_TO_GRADE", why="no decision row under this contract hash")
        return out
    syms = {"SPY"} | {t for r in decs for t in list(r.get("shadow") or {}) + list(r.get("base") or {})}
    bars = _bars_for(syms) if bars is None else bars
    sessions = sorted(bars.loc[bars["symbol"] == "SPY", "date"].unique())
    if not sessions:
        out.update(status="REFUSED", why="no SPY bars: the session calendar is unknown")
        return out
    by = {s: g.set_index("date") for s, g in bars.groupby("symbol")}
    # entry session for each decision: the first session whose open is after it
    entries: dict[Any, dict] = {}
    from backend.services import market_sessions as MS
    for r in sorted(decs, key=lambda r: r["t"]):
        t = datetime.fromisoformat(r["t"])
        day = pd.Timestamp(t.date())
        for _ in range(15):
            if MS.is_session(day) and _session_open_utc(day) > t:
                break
            day += pd.Timedelta(days=1)
        entries[day] = r                        # the last before the open wins
    rows = []
    for day, r in sorted(entries.items()):
        w1, w0 = r.get("shadow") or {}, r.get("base") or {}
        tilt = {k: float(w1.get(k, 0)) - float(w0.get(k, 0)) for k in set(w1) | set(w0)}
        row: dict[str, Any] = {"entry_session": str(day.date()), "decision_t": r["t"],
                               "digest_id": r.get("digest_id"), "trust_dir": r.get("trust_dir"),
                               "trust_size": r.get("trust_size"),
                               "sum_abs_tilt": round(sum(abs(v) for v in tilt.values()), 8)}
        after = [s for s in sessions if s >= day]
        for h in NEWS_HORIZONS:
            if len(after) < h or after[0] != day:
                row[f"h{h}"] = {"status": "PENDING", "why": f"needs {h} sessions from {day.date()}, "
                                f"has {len([s for s in after if s >= day])}"}
                continue
            end = after[h - 1]

            def ret(sym):
                g = by.get(sym)
                try:
                    return float(g.loc[end, "close"]) / float(g.loc[day, "open"]) - 1.0
                except (KeyError, TypeError, ZeroDivisionError, AttributeError):
                    return None
            rs = {k: ret(k) for k in tilt}
            miss = [k for k, v in rs.items() if v is None and (w1.get(k) or w0.get(k))]
            base_r = sum(float(w0[k]) * (rs[k] or 0.0) for k in w0) / max(1e-12, sum(map(float, w0.values())))
            shadow_r = sum(float(w1[k]) * (rs[k] or 0.0) for k in w1) / max(1e-12, sum(map(float, w1.values())))
            spy = ret("SPY")
            row[f"h{h}"] = {"status": "OK" if not miss else "PARTIAL", "unpriced": miss,
                            "through": str(pd.Timestamp(end).date()),
                            "D_tilt": sum(tilt[k] * (rs[k] or 0.0) for k in tilt),
                            "shadow_sleeve": shadow_r, "twin_sleeve_base": base_r,
                            "market_spy": spy, "shadow_vs_market": (shadow_r - spy) if spy is not None else None}
        rows.append(row)
    out["by_entry"] = rows
    agg = {}
    for h in NEWS_HORIZONS:
        ds = [r[f"h{h}"]["D_tilt"] for r in rows if r[f"h{h}"].get("status") in ("OK", "PARTIAL")]
        agg[f"h{h}"] = {"n_date_blocks": len(ds), "mean_D_tilt": (sum(ds) / len(ds)) if ds else None}
    out["aggregate"] = agg
    trusts = {(r.get("trust_dir"), r.get("trust_size")) for r in decs}
    zero_trust = trusts == {(0.0, 0.0)}
    n_res = max(v["n_date_blocks"] for v in agg.values())
    out["status"] = "PENDING" if n_res == 0 else "GRADED"
    out["reading"] = ("both trusts are 0 on every decision, so the tilt is zero by construction "
                      "(shadow = twin up to 6-dp rounding): D is 0 and says nothing about news yet"
                      if zero_trust else f"{n_res} date block(s) resolved; read vs zero by date block")
    return out


def run(*, lb_dir: Path = LB_DIR, sb_dir: Path = SB_DIR, news_dir: Path = NEWS_DIR,
        write: bool = True) -> dict:
    from backend.services import llm_portfolio as LP
    now = datetime.now(timezone.utc)
    lbp, lb = latest_leaderboard(lb_dir)
    books = {b["book_id"]: b for b in LP.read_books()}
    rec: dict[str, Any] = {"receipt": "shadow_grade", "licence": "PRODUCT_EXPERIMENT",
                           "written_utc": now.isoformat(timespec="seconds"), "llm_spend_usd": 0.0,
                           "leaderboard": str(lbp) if lbp else None,
                           "leaderboard_graded_utc": (lb or {}).get("graded_utc"),
                           "bars_through": (lb or {}).get("bars_through"),
                           "read_me_first": ONE_SESSION_SAYS_NOTHING}
    rec["books"] = ([grade_book(s, lb, books, sb_dir) for s in BOOKS] if lb else
                    [{"name": s["name"], "status": "REFUSED", "why": "no leaderboard on disk"} for s in BOOKS])
    try:
        rec["books"].append(grade_news(news_dir))
    except Exception as exc:                                        # noqa: BLE001
        rec["books"].append({"name": "SHADOW_NEWS_v0", "status": "REFUSED",
                             "why": f"{type(exc).__name__}: {str(exc)[:200]}"})
    n_ref = sum(1 for b in rec["books"] if b.get("status") == "REFUSED")
    rec["status"] = "refused" if n_ref == len(rec["books"]) else "ok"
    if write:
        p = sb_dir / f"shadow_grade_{now:%Y-%m-%d}_{now:%Y%m%dT%H%M%SZ}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
        tmp.replace(p)
        rec["receipt_path"] = str(p)
    return rec


def _f(v: Any) -> str:
    return "n/a" if v is None else f"{float(v):+.4f}"


def _line(b: dict) -> str:
    if b["name"] == "SHADOW_NEWS_v0":
        return f"{b['name']}: {b.get('status')} ({b.get('n_decisions', 0)} decisions) -- {b.get('reading') or b.get('why')}"
    if b.get("sessions") is None:
        return f"{b['name']}: {b.get('status')} -- {b.get('why')}"
    k = b["kill"]
    return (f"{b['name']}: {b['status']} s={b['sessions']} D_vs_twin={b['D_vs_twin_sleeve_scale']:+.4f} "
            f"(sleeve scale; NAV gap {b['nav_gap_vs_twin']:+.4f}) vs_market={_f(b.get('vs_market'))} "
            f"kill line {k.get('kill_line')} at s={b['kill_session']} [{k.get('source')}]")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    rec = run(write=not a.no_write)
    for b in rec["books"]:
        print(_line(b))
    if a.json:
        summary = {"status": rec["status"], "receipt": rec.get("receipt_path"),
                   "bars_through": rec.get("bars_through"),
                   "books": {b["name"]: {k: b.get(k) for k in ("status", "sessions", "D_vs_twin_sleeve_scale",
                                                                "vs_market", "reading", "why")}
                             for b in rec["books"]}}
        print("<<<" + json.dumps(summary, default=str) + ">>>")
    return 0 if rec["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
