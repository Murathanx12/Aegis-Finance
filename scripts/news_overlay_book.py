"""CH-14b news risk-overlay book: contract, BACKFILL replay, the forward step, and grading.

    python -m scripts.news_overlay_book contract --out DIR
    python -m scripts.news_overlay_book replay --out DIR [--data-dir D]
    python -m scripts.news_overlay_book step [--date YYYY-MM-DD] [--data-dir D]
    python -m scripts.news_overlay_book grade --out DIR [--data-dir D]

`replay` is BACKFILL over the digests already on disk: it proves the mechanism
and is NOT forward evidence. It writes only under --out and refuses an --out
inside the data folder. `step` is the forward decision for TODAY's
America/New_York session, inside NEWS_OVERLAY_STEP_WINDOW_ET only; it writes
only when `NEWS_OVERLAY_BOOK_ENABLED` is True (env AEGIS_NEWS_OVERLAY_BOOK=1).
A `--date` other than today's ET session writes a BACKDATED row, never graded.
`grade` marks FORWARD rows only; a session with no row is 1.0 (NO_DECISION_ROW).
No broker, no order, no LLM call, no network.
Exit codes: 0 ok, 2 refused (missing input / foreign contract / bad --out /
non-session day / outside the step window).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                                  # noqa: E402
from backend.services import news_overlay_book as NO                # noqa: E402


def _paths(data_dir: Path | None) -> dict:
    d = Path(data_dir) if data_dir else Path(_cfg.DATA_DIR)
    opt = d / "optimus"
    return {"data": d, "digest": opt / "digest", "db": d / "aegis_pi.db",
            "bars": opt / "prices_2025_26" / "bars.parquet"}


def _describe(p: Path) -> str:
    if p.is_dir():
        fs = list(p.iterdir())
        return f"{p} (dir, {len(fs)} entries)"
    st = p.stat()
    return f"{p} ({st.st_size:,} B, mtime {datetime.fromtimestamp(st.st_mtime, timezone.utc):%Y-%m-%dT%H:%M}Z)"


def _count(p: Path) -> int:
    return sum(1 for _ in p.iterdir()) if p.is_dir() else -1


def _closes(bars: Path, symbols: list[str], start: date):
    import pandas as pd
    if not bars.is_file():
        raise NO.NewsOverlayRefused(f"no bars panel at {bars}")
    df = pd.read_parquet(bars, columns=["symbol", "date", "close"],
                         filters=[("symbol", "in", symbols)])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df[df["date"] >= start]
    return df.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()


def _write_json(p: Path, obj) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True, default=str), encoding="utf-8")
    tmp.replace(p)


def _guard_out(out: Path, data: Path) -> None:
    o, d = out.resolve(), data.resolve()
    if o == d or d in o.parents:
        raise NO.NewsOverlayRefused(f"--out {o} is inside the data folder {d}; this command never "
                                    f"writes there")


def _base_panel(P: dict, c: dict, first: date, last: Optional[date] = None) -> dict:
    """Base holdings, closes, weights, re-target flags and stale holdings over
    the bar sessions in [first, last]. Read-only."""
    snaps = NO.load_base_holdings(P["db"], c["base_book_id"])
    held = sorted({s for sn in snaps for s in sn["shares"]})
    wide = _closes(P["bars"], held, min(first, min(sn["asof"] for sn in snaps)) - timedelta(days=60))
    no_bars = [s for s in held if s not in wide.columns]
    if no_bars:
        raise NO.NewsOverlayRefused(f"held symbols with no bars at all: {no_bars}")
    sessions = [d for d in wide.index if d >= first and (last is None or d <= last)]
    if not sessions:
        raise NO.NewsOverlayRefused(f"no bar sessions in {first}..{last}")
    # distance (in panel sessions) from each session to the symbol's last real bar
    idx = {d: i for i, d in enumerate(wide.index)}
    last_pos: dict = {}
    for s in held:
        col = wide[s]
        lastreal, m = None, {}
        for d, v in col.items():
            if v == v:
                lastreal = idx[d]
            m[d] = None if lastreal is None else idx[d] - lastreal
        last_pos[s] = m
    carried = {s: int(wide.loc[sessions, s].isna().sum()) for s in held if wide.loc[sessions, s].isna().any()}
    wide = wide.ffill()
    closes = {d: {s: float(v) for s, v in wide.loc[d].items() if v == v} for d in sessions}
    weights, changed = NO.base_weights_by_session(snaps, sessions, closes)
    stale = NO.stale_holdings(last_pos, sessions, weights)
    return {"snaps": snaps, "sessions": sessions, "closes": closes, "weights": weights,
            "changed": changed, "stale": stale, "carried": carried, "n_symbols": len(held)}


def worst_case_lines(sessions, closes, weights, sim) -> dict:
    """Three honest lines, each named for what it is."""
    notional = sim["notional"]
    sr = sim["rows"]
    nav_prev = {sessions[i]: sr[i - 1]["twin_nav"] for i in range(1, len(sessions))}
    worst, losses = None, []
    for i in range(1, len(sessions)):
        t0, t1 = sessions[i - 1], sessions[i]
        for s, w in weights[t0].items():
            p0, p1 = closes[t0].get(s), closes[t1].get(s)
            if not p0 or not p1:
                continue
            r = p1 / p0 - 1.0
            usd = w * nav_prev[t1] * r          # signed: only a LOSS can set it
            losses.append((usd, s, t1.isoformat(), w, r))
            if worst is None or usd < worst["usd"]:
                worst = {"usd": usd, "symbol": s, "session": t1.isoformat(), "weight": w, "move": r}
    worst_day = {k: min(sr[1:], key=lambda r: r[f"{k}_ret"]) for k in ("overlay", "twin")}
    gross = {k: max(r[f"{k}_gross"] for r in sr) for k in ("overlay", "twin")}
    return {
        "worst_single_name_loss": {
            "what": "the worst one-day dollar loss of ONE holding at its actual weight in the twin (signed)",
            "usd": round(worst["usd"], 2), "symbol": worst["symbol"], "session": worst["session"],
            "weight": round(worst["weight"], 5), "move": round(worst["move"], 5),
            "top5": [{"usd": round(u, 2), "symbol": sy, "session": se, "weight": round(w, 5),
                      "move": round(r, 5)} for u, sy, se, w, r in sorted(losses)[:5]],
            "caveat": ("bars are read as stored; a one-day move near -50% can be an unadjusted "
                       "split rather than a loss, and it hits the twin and the overlay alike")},
        "worst_observed_basket_day": {
            "what": "the worst observed one-day change of the whole book in the replay",
            **{k: {"usd": round(v[f"{k}_ret"] * notional, 2), "pct": round(100 * v[f"{k}_ret"], 4),
                   "session": v["session"]} for k, v in worst_day.items()}},
        "total_loss_bound": {
            "what": "sum|notional| / equity x equity: what is lost if every holding goes to zero",
            "gross_over_equity_max": {k: round(v, 5) for k, v in gross.items()},
            "usd": {k: round(v * notional, 2) for k, v in gross.items()}},
    }


def _print_worst(wc: dict) -> None:
    a, b, c = (wc["worst_single_name_loss"], wc["worst_observed_basket_day"], wc["total_loss_bound"])
    print(f"WORST SINGLE-NAME LOSS ${a['usd']:,.0f}: {a['symbol']} {a['weight']:.2%} x {a['move']:+.2%} "
          f"on {a['session']}")
    print(f"WORST OBSERVED BASKET DAY: twin ${b['twin']['usd']:,.0f} ({b['twin']['session']}), overlay "
          f"${b['overlay']['usd']:,.0f} ({b['overlay']['session']})")
    print(f"TOTAL-LOSS BOUND: gross/equity max twin {c['gross_over_equity_max']['twin']:.3f} -> "
          f"${c['usd']['twin']:,.0f}; overlay {c['gross_over_equity_max']['overlay']:.3f} -> "
          f"${c['usd']['overlay']:,.0f}")


def cmd_contract(a) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    c = NO.contract()
    p = out / f"CONTRACT_{NO.CONTRACT_NAME}_{c['policy_hash']}.json"
    _write_json(p, c | {"written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    print(f"contract {NO.CONTRACT_NAME} policy_hash {c['policy_hash']} -> {p}")
    return 0


def cmd_replay(a) -> int:
    P = _paths(a.data_dir)
    out = Path(a.out)
    _guard_out(out, P["data"])
    out.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    before = {"digest": _count(P["digest"]), "data_top": _count(P["data"])}
    print("INPUTS (read-only):")
    for k in ("digest", "db", "bars"):
        if not P[k].exists():
            raise NO.NewsOverlayRefused(f"missing input {k}: {P[k]}")
        print("  ", _describe(P[k]))
    c = NO.contract()
    digests = NO.load_digests(P["digest"])
    if not digests:
        raise NO.NewsOverlayRefused(f"no non-dry world digests in {P['digest']}")
    print(f"  digests: {len(digests)} non-dry, {digests[0]['digest_id']} .. {digests[-1]['digest_id']}, "
          f"{sum(1 for g in digests if g['F'] is not None)} with >= {_cfg.NEWS_OVERLAY_MIN_THEMES} toned themes")
    B = _base_panel(P, c, digests[0]["stamped_utc"].date())
    sessions, closes, weights, changed = B["sessions"], B["closes"], B["weights"], B["changed"]
    if len(sessions) < 2:
        raise NO.NewsOverlayRefused("fewer than 2 sessions with bars after the first digest")
    print(f"  bars: {B['n_symbols']} base symbols, sessions {sessions[0]} .. {sessions[-1]} ({len(sessions)}), "
          f"closes CARRIED (last bar forward-filled, as the base book's own mark does): {B['carried']}")

    rows, scal = [], {}
    prev = None
    for t in sessions:
        r = NO.step(t, digests=digests, base_weights=weights[t], prev_scalar=prev,
                    enabled=False, write=False, label=NO.BACKFILL)
        if r["digest_stamped_utc"] and datetime.fromisoformat(r["digest_stamped_utc"]) >= NO.decision_time(t):
            raise NO.NewsOverlayRefused(f"look-ahead: {t} read digest {r['digest_id']}")
        r["grade_status"] = "DEGRADED" if t in B["stale"] else "OK"
        r["stale_holdings"] = B["stale"].get(t, {})
        rows.append(r)
        scal[t] = r["scalar"]
        prev = r["scalar"]
    sim = NO.simulate(sessions, closes, weights, changed, scal)
    sr = sim["rows"]
    for r, d in zip(sr, rows):
        r["grade_status"] = d["grade_status"]

    notional = sim["notional"]
    wc = worst_case_lines(sessions, closes, weights, sim)
    sc_vals = [r["scalar"] for r in rows]
    moved = sum(1 for i in range(1, len(sc_vals)) if sc_vals[i] != sc_vals[i - 1])
    deg = Counter(r["degradation"] or "NONE (mapped)" for r in rows)
    ov_tot = sr[-1]["overlay_nav"] / notional - 1.0
    tw_tot = sr[-1]["twin_nav"] / notional - 1.0
    ov_cost = sum(r["overlay_cost"] for r in sr)
    tw_cost = sum(r["twin_cost"] for r in sr)
    scalar_cost = sum(r["overlay_cost"] for r, d in zip(sr, rows) if d["scalar"] != d["prev_scalar"]
                      and not changed.get(date.fromisoformat(r["session"])))
    by_month: dict = {}
    for r in sr[1:]:
        b = by_month.setdefault(r["session"][:7], {"overlay": 1.0, "twin": 1.0, "n": 0})
        b["overlay"] *= 1 + r["overlay_ret"]
        b["twin"] *= 1 + r["twin_ret"]
        b["n"] += 1
    by_month = {m: {"overlay_pct": round(100 * (v["overlay"] - 1), 3), "twin_pct": round(100 * (v["twin"] - 1), 3),
                    "sessions": v["n"]} for m, v in by_month.items()}
    stale_days = {t.isoformat(): v for t, v in B["stale"].items()}

    after = {"digest": _count(P["digest"]), "data_top": _count(P["data"])}
    head = {
        "LABEL": "BACKFILL REPLAY over digests already on disk -- NOT forward evidence, no skill claim",
        "worst_case_first": wc,
        "days": len(sessions), "first_session": sessions[0].isoformat(), "last_session": sessions[-1].isoformat(),
        "days_with_mapped_scalar": deg.get("NONE (mapped)", 0),
        "degradations": dict(deg),
        "scalar_distribution": {"min": min(sc_vals), "max": max(sc_vals),
                                "mean": round(statistics.mean(sc_vals), 4),
                                "median": statistics.median(sc_vals),
                                "counts": {str(k): v for k, v in sorted(Counter(sc_vals).items())}},
        "days_scalar_moved": moved,
        "raw_lines": {"overlay_total_pct": round(100 * ov_tot, 4), "twin_total_pct": round(100 * tw_tot, 4),
                      "overlay_minus_twin_pp": round(100 * (ov_tot - tw_tot), 4),
                      "overlay_end_nav": round(sr[-1]["overlay_nav"], 2), "twin_end_nav": round(sr[-1]["twin_nav"], 2)},
        "by_month": by_month,
        "turnover_and_cost": {"cost_rate_one_way": sim["cost_rate"],
                              "overlay_traded_usd": round(sum(r["overlay_traded"] for r in sr), 2),
                              "twin_traded_usd": round(sum(r["twin_traded"] for r in sr), 2),
                              "overlay_cost_usd": round(ov_cost, 2), "twin_cost_usd": round(tw_cost, 2),
                              "overlay_cost_on_scalar_only_days_usd": round(scalar_cost, 2)},
        "base_rebalance_sessions": [t.isoformat() for t in sessions if changed.get(t)],
        "stale_bar_days": {"n_days_degraded": len(stale_days),
                           "rule": f"a holding whose last real bar is > {_cfg.NEWS_OVERLAY_STALE_BAR_SESSIONS} "
                                   f"sessions old", "by_day": stale_days},
        "mapping": {"contract": NO.CONTRACT_NAME, "rule": c["mapping"], "disclosure": c["disclosure"],
                    "history": c["history"]},
        "honesty": ("BACKFILL; digests carried 0 themes 2026-10-15..2026-11-03 (provider_budget block) and "
                    "none 11-04..11-09, so mapped days fall in two short windows: this cannot distinguish "
                    "the overlay from its twin and says nothing about skill"),
    }
    receipt = {"schema": "news_overlay_book_replay/v2", "run_id": run_id, "licence": NO.LICENCE,
               "contract": c, "headline": head,
               "inputs": {k: str(P[k]) for k in ("digest", "db", "bars")},
               "carried_closes_by_symbol": B["carried"],
               "live_folder_counts": {"before": before, "after": after, "unchanged": before == after},
               "decision_rows": rows, "daily": sr}
    rp = out / f"news_overlay_replay_{run_id}.json"
    _write_json(rp, receipt)
    dp = out / f"news_overlay_backfill_decisions_{run_id}.jsonl"
    dp.write_text("".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in rows), encoding="utf-8")
    sha = hashlib.sha256(rp.read_bytes()).hexdigest()[:16]

    print("\nBACKFILL REPLAY -- NOT FORWARD EVIDENCE")
    _print_worst(wc)
    print(f"days {len(sessions)} ({sessions[0]}..{sessions[-1]}); mapped {head['days_with_mapped_scalar']}; "
          f"degradations {dict(deg)}; grade DEGRADED (stale base bars) on {len(stale_days)} days")
    print(f"scalar min {min(sc_vals)} max {max(sc_vals)} mean {head['scalar_distribution']['mean']} "
          f"counts {head['scalar_distribution']['counts']}; moved on {moved} days")
    print(f"RAW overlay {100 * ov_tot:+.3f}%  twin {100 * tw_tot:+.3f}%  diff {100 * (ov_tot - tw_tot):+.3f} pp")
    print(f"by month {by_month}")
    print(f"cost overlay ${ov_cost:,.2f} (scalar-only days ${scalar_cost:,.2f}) twin ${tw_cost:,.2f}; "
          f"traded overlay ${head['turnover_and_cost']['overlay_traded_usd']:,.0f} twin "
          f"${head['turnover_and_cost']['twin_traded_usd']:,.0f}")
    cited = [r for r in rows if r["digest_id"]]
    print(f"decision rows {len(rows)}, citing a digest_id {len(cited)}; e.g. {cited[-1]['session']} -> "
          f"{cited[-1]['digest_id']} scalar {cited[-1]['scalar']} ({cited[-1]['degradation']})")
    print(f"policy_hash {c['policy_hash']}; receipt {rp} sha256[:16] {sha}; decisions {dp}")
    print(f"live folder counts before {before} after {after} unchanged={before == after}")
    if before != after:
        print("WARNING: a live folder count changed during the run (another process may have written)")
    return 0


def cmd_step(a, now: Optional[datetime] = None) -> int:
    P = _paths(a.data_dir)
    if not bool(_cfg.NEWS_OVERLAY_BOOK_ENABLED):
        print("NEWS_OVERLAY_BOOK_ENABLED=False: nothing computed, nothing written (attended seeding "
              "required; see the PR's seeding steps)")
        return 0
    now = now or datetime.now(timezone.utc)
    today, refusal = NO.forward_session(now)
    if a.date and date.fromisoformat(a.date) != today:
        t, label = date.fromisoformat(a.date), NO.BACKDATED
        if not NO.is_session(t):
            raise NO.NewsOverlayRefused(f"{t} is not an XNYS session")
    else:
        if refusal:
            raise NO.NewsOverlayRefused(refusal)
        t, label = today, NO.FORWARD
    c = NO.contract()
    digests = NO.load_digests(P["digest"])
    snaps = NO.load_base_holdings(P["db"], c["base_book_id"])
    syms = sorted({s for sn in snaps for s in sn["shares"]})
    wide = _closes(P["bars"], syms, min(sn["asof"] for sn in snaps)).ffill()
    days = [d for d in wide.index if d <= t]
    if not days:
        raise NO.NewsOverlayRefused(f"no bars on or before {t}")
    last = days[-1]
    closes = {last: {s: float(v) for s, v in wide.loc[last].items() if v == v}}
    w, _ = NO.base_weights_by_session(snaps, [last], closes)
    dp = NO.decisions_path(P["data"] / "optimus")
    fwd = NO.read_forward_rows(dp, c["policy_hash"]) if dp.exists() else []
    prev = fwd[-1]["scalar"] if fwd else None
    row = NO.step(t, digests=digests, base_weights=w[last], prev_scalar=prev, out_path=dp,
                  label=label, now=now)
    print(json.dumps({k: row.get(k) for k in ("session", "label", "scalar", "degradation", "digest_id",
                                               "decision_utc", "written_utc", "policy_hash", "written",
                                               "duplicate")}, default=str))
    return 0


def cmd_grade(a) -> int:
    """Mark the FORWARD decision rows of this contract as overlay vs twin. A
    session with no row is 1.0 (NO_DECISION_ROW). Read-only on the data folder."""
    P = _paths(a.data_dir)
    out = Path(a.out)
    _guard_out(out, P["data"])
    c = NO.contract()
    dp = NO.decisions_path(P["data"] / "optimus")
    if not dp.is_file():
        raise NO.NewsOverlayRefused(f"no forward decision file at {dp} (the book is not seeded)")
    rows = NO.read_forward_rows(dp, c["policy_hash"])
    if not rows:
        raise NO.NewsOverlayRefused(f"no FORWARD rows under {c['policy_hash']} in {dp}")
    first = date.fromisoformat(rows[0]["session"])
    lastd = date.fromisoformat(rows[-1]["session"])
    B = _base_panel(P, c, first, lastd)
    sessions = B["sessions"]
    scal, why = NO.grade_scalars(sessions, rows)
    sim = NO.simulate(sessions, B["closes"], B["weights"], B["changed"], scal)
    sr = sim["rows"]
    for r in sr:
        t = date.fromisoformat(r["session"])
        r["reason"] = why[t]
        r["grade_status"] = "DEGRADED" if t in B["stale"] else "OK"
        r["stale_holdings"] = B["stale"].get(t, {})
    ov, tw = sr[-1]["overlay_nav"] / sim["notional"] - 1, sr[-1]["twin_nav"] / sim["notional"] - 1
    out.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rp = out / f"news_overlay_grade_{run_id}.json"
    n_missing = sum(1 for v in why.values() if v == NO.NO_DECISION_ROW)
    n_deg = sum(1 for r in sr if r["grade_status"] == "DEGRADED")
    _write_json(rp, {"schema": "news_overlay_book_grade/v2", "run_id": run_id, "label": NO.FORWARD,
                     "policy_hash": c["policy_hash"], "sessions": len(sessions),
                     "no_decision_row_sessions": n_missing, "degraded_sessions": n_deg,
                     "worst_case_first": worst_case_lines(sessions, B["closes"], B["weights"], sim),
                     "overlay_total_pct": 100 * ov, "twin_total_pct": 100 * tw,
                     "overlay_cost_usd": sum(r["overlay_cost"] for r in sr),
                     "twin_cost_usd": sum(r["twin_cost"] for r in sr), "daily": sr})
    print(f"FORWARD {len(sessions)} sessions {sessions[0]}..{sessions[-1]} ({n_missing} NO_DECISION_ROW -> "
          f"1.0, {n_deg} DEGRADED): RAW overlay {100 * ov:+.3f}% twin {100 * tw:+.3f}% "
          f"diff {100 * (ov - tw):+.3f} pp -> {rp}")
    return 0


def main(argv=None, *, now: Optional[datetime] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c1 = sub.add_parser("contract")
    c1.add_argument("--out", required=True)
    c2 = sub.add_parser("replay")
    c2.add_argument("--out", required=True)
    c2.add_argument("--data-dir", default=None)
    c3 = sub.add_parser("step")
    c3.add_argument("--date", default=None)
    c3.add_argument("--data-dir", default=None)
    c4 = sub.add_parser("grade")
    c4.add_argument("--out", required=True)
    c4.add_argument("--data-dir", default=None)
    a = ap.parse_args(argv)
    cmds: dict[str, Callable] = {"contract": cmd_contract, "replay": cmd_replay,
                                 "step": lambda x: cmd_step(x, now=now), "grade": cmd_grade}
    try:
        return cmds[a.cmd](a)
    except NO.NewsOverlayRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
