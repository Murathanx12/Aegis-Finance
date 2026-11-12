"""CH-14b news risk-overlay book: contract, BACKFILL replay, and the forward step.

    python -m scripts.news_overlay_book contract --out DIR
    python -m scripts.news_overlay_book replay --out DIR [--data-dir D]
    python -m scripts.news_overlay_book step [--date YYYY-MM-DD] [--data-dir D]
    python -m scripts.news_overlay_book grade --out DIR [--data-dir D]

`replay` is BACKFILL over the digests already on disk: it proves the mechanism
and is NOT forward evidence. It writes only under --out and refuses an --out
inside the data folder. `step` is the forward decision; it writes only when
`NEWS_OVERLAY_BOOK_ENABLED` is True (default False -> nothing written).
No broker, no order, no LLM call, no network.
Exit codes: 0 ok, 2 refused (missing input / foreign contract / bad --out).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

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
    wide = df.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()
    return wide


def _write_json(p: Path, obj) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True, default=str), encoding="utf-8")
    tmp.replace(p)


def _guard_out(out: Path, data: Path) -> None:
    o, d = out.resolve(), data.resolve()
    if o == d or d in o.parents:
        raise NO.NewsOverlayRefused(f"--out {o} is inside the data folder {d}; the replay never "
                                    f"writes there")


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
    snaps = NO.load_base_holdings(P["db"], c["base_book_id"])
    syms = sorted({s for sn in snaps for s in sn["shares"]})
    start = digests[0]["stamped_utc"].date()
    from datetime import timedelta
    wide = _closes(P["bars"], syms, min(start, min(sn["asof"] for sn in snaps)) - timedelta(days=60))
    sessions = [d for d in wide.index if d >= start]
    held_any = sorted({s for sn in snaps for s in sn["shares"]})
    win = wide.loc[sessions, [s for s in held_any if s in wide.columns]]
    carried = {s: int(n) for s, n in win.isna().sum().items() if n}
    wide = wide.ffill()
    no_bars = [s for s in held_any if s not in wide.columns]
    if no_bars:
        raise NO.NewsOverlayRefused(f"held symbols with no bars at all: {no_bars}")
    if len(sessions) < 2:
        raise NO.NewsOverlayRefused("fewer than 2 sessions with bars after the first digest")
    closes = {d: {s: float(v) for s, v in wide.loc[d].items() if v == v} for d in sessions}
    print(f"  bars: {len(syms)} base symbols, sessions {sessions[0]} .. {sessions[-1]} ({len(sessions)}), "
          f"closes CARRIED (last bar forward-filled, as the base book's own mark does) per symbol: {carried}")
    weights, changed = NO.base_weights_by_session(snaps, sessions, closes)
    changed[sessions[0]] = False

    rows, scal = [], {}
    prev = None
    for t in sessions:
        r = NO.step(t, digests=digests, base_weights=weights[t], prev_scalar=prev,
                    enabled=False, write=False, label="BACKFILL")
        if r["digest_stamped_utc"] and datetime.fromisoformat(r["digest_stamped_utc"]) >= NO.decision_time(t):
            raise NO.NewsOverlayRefused(f"look-ahead: {t} read digest {r['digest_id']}")
        rows.append(r)
        scal[t] = r["scalar"]
        prev = r["scalar"]
    sim = NO.simulate(sessions, closes, weights, changed, scal)
    sr = sim["rows"]

    # ── headline numbers ──
    notional = sim["notional"]
    n_names = len(weights[sessions[-1]])
    max_gross = max(r["twin_gross"] for r in sr)
    name_moves = []
    for i in range(1, len(sessions)):
        a0, a1 = closes[sessions[i - 1]], closes[sessions[i]]
        for s in weights[sessions[i - 1]]:
            if a0.get(s) and a1.get(s):
                name_moves.append((abs(a1[s] / a0[s] - 1.0), s, sessions[i].isoformat()))
    worst_name = max(name_moves)
    per_name = max(max(w.values()) for w in weights.values())
    worst_case_usd = n_names * per_name * notional * worst_name[0]
    worst_day = {k: min(sr[1:], key=lambda r: r[f"{k}_ret"]) for k in ("overlay", "twin")}
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
        m = r["session"][:7]
        b = by_month.setdefault(m, {"overlay": 1.0, "twin": 1.0, "n": 0})
        b["overlay"] *= 1 + r["overlay_ret"]
        b["twin"] *= 1 + r["twin_ret"]
        b["n"] += 1
    by_month = {m: {"overlay_pct": round(100 * (v["overlay"] - 1), 3), "twin_pct": round(100 * (v["twin"] - 1), 3),
                    "sessions": v["n"]} for m, v in by_month.items()}

    after = {"digest": _count(P["digest"]), "data_top": _count(P["data"])}
    head = {
        "LABEL": "BACKFILL REPLAY over digests already on disk -- NOT forward evidence, no skill claim",
        "worst_case_usd_first": {
            "rule": "n names x max per-name notional% x notional x worst one-day single-name |move| in the replay",
            "n_names": n_names, "max_per_name_weight": round(per_name, 5), "notional_usd": notional,
            "worst_single_name_one_day_move": {"abs_move": round(worst_name[0], 5), "symbol": worst_name[1],
                                               "session": worst_name[2]},
            "worst_case_usd": round(worst_case_usd, 2),
            "gross_over_equity_max": {"twin": round(max_gross, 5),
                                      "overlay": round(max(r["overlay_gross"] for r in sr), 5)},
            "worst_observed_day_usd": {k: {"session": v["session"],
                                           "usd": round(v[f"{k}_ret"] * notional, 2),
                                           "pct": round(100 * v[f"{k}_ret"], 4)} for k, v in worst_day.items()},
        },
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
        "mapping": {"declared_utc": _cfg.NEWS_OVERLAY_MAPPING_DECLARED_UTC,
                    "mappings_tried": _cfg.NEWS_OVERLAY_MAPPINGS_TRIED, "rule": c["mapping"]},
        "honesty": ("one replay of one mapping; the first typed digests are 2026-09-29 and digests carried "
                    "0 themes 2026-10-15..2026-11-03 (provider_budget block) and none 11-04..11-09, so most "
                    "mapped days fall in two short windows: this cannot distinguish the overlay from its twin "
                    "and says nothing about skill"),
    }
    receipt = {"schema": "news_overlay_book_replay/v1", "run_id": run_id, "licence": NO.LICENCE,
               "contract": c, "headline": head,
               "inputs": {k: str(P[k]) for k in ("digest", "db", "bars")},
               "carried_closes_by_symbol": carried,
               "live_folder_counts": {"before": before, "after": after, "unchanged": before == after},
               "decision_rows": rows, "daily": sr}
    rp = out / f"news_overlay_replay_{run_id}.json"
    _write_json(rp, receipt)
    dp = out / f"news_overlay_backfill_decisions_{run_id}.jsonl"
    dp.write_text("".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in rows), encoding="utf-8")
    sha = hashlib.sha256(rp.read_bytes()).hexdigest()[:16]

    wc = head["worst_case_usd_first"]
    print("\nBACKFILL REPLAY -- NOT FORWARD EVIDENCE")
    print(f"WORST CASE ${wc['worst_case_usd']:,.0f}: {n_names} names x {per_name:.2%} x ${notional:,.0f} x "
          f"{worst_name[0]:.2%} ({worst_name[1]} {worst_name[2]}); gross/equity max twin "
          f"{wc['gross_over_equity_max']['twin']:.3f}, overlay {wc['gross_over_equity_max']['overlay']:.3f}; "
          f"worst observed day overlay ${wc['worst_observed_day_usd']['overlay']['usd']:,.0f} "
          f"({wc['worst_observed_day_usd']['overlay']['session']}), twin "
          f"${wc['worst_observed_day_usd']['twin']['usd']:,.0f}")
    print(f"days {len(sessions)} ({sessions[0]}..{sessions[-1]}); mapped {head['days_with_mapped_scalar']}; "
          f"degradations {dict(deg)}")
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


def cmd_step(a) -> int:
    P = _paths(a.data_dir)
    if not bool(_cfg.NEWS_OVERLAY_BOOK_ENABLED):
        print("NEWS_OVERLAY_BOOK_ENABLED=False: nothing computed, nothing written (attended seeding "
              "required; see the PR's seeding steps)")
        return 0
    t = date.fromisoformat(a.date) if a.date else date.today()
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
    prev = None
    if dp.exists():
        lines = [x for x in dp.read_text(encoding="utf-8").splitlines() if x.strip()]
        prev = json.loads(lines[-1]).get("scalar") if lines else None
    row = NO.step(t, digests=digests, base_weights=w[last], prev_scalar=prev, out_path=dp)
    print(json.dumps({k: row[k] for k in ("session", "scalar", "degradation", "digest_id", "policy_hash",
                                           "written")}, default=str))
    return 0


def cmd_grade(a) -> int:
    """Mark the FORWARD decision rows (label FORWARD, this contract only) as
    overlay vs twin. Read-only on the data folder; writes under --out."""
    P = _paths(a.data_dir)
    out = Path(a.out)
    _guard_out(out, P["data"])
    c = NO.contract()
    dp = NO.decisions_path(P["data"] / "optimus")
    if not dp.is_file():
        raise NO.NewsOverlayRefused(f"no forward decision file at {dp} (the book is not seeded)")
    rows = [json.loads(x) for x in dp.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = [r for r in rows if r.get("label") == "FORWARD" and r.get("policy_hash") == c["policy_hash"]]
    if len(rows) < 2:
        raise NO.NewsOverlayRefused(f"{len(rows)} forward rows under {c['policy_hash']}; need >= 2 to grade")
    snaps = NO.load_base_holdings(P["db"], c["base_book_id"])
    syms = sorted({s for sn in snaps for s in sn["shares"]})
    from datetime import timedelta
    first = date.fromisoformat(rows[0]["session"])
    wide = _closes(P["bars"], syms, first - timedelta(days=60)).ffill()
    scal = {date.fromisoformat(r["session"]): float(r["scalar"]) for r in rows}
    sessions = [d for d in wide.index if d >= first and d <= max(scal)]
    closes = {d: {s: float(v) for s, v in wide.loc[d].items() if v == v} for d in sessions}
    weights, changed = NO.base_weights_by_session(snaps, sessions, closes)
    changed[sessions[0]] = False
    prev, full = 1.0, {}
    for d in sessions:                                   # a session with no row holds the last scalar
        prev = scal.get(d, prev)
        full[d] = prev
    sim = NO.simulate(sessions, closes, weights, changed, full)
    sr = sim["rows"]
    ov, tw = sr[-1]["overlay_nav"] / sim["notional"] - 1, sr[-1]["twin_nav"] / sim["notional"] - 1
    out.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rp = out / f"news_overlay_grade_{run_id}.json"
    _write_json(rp, {"schema": "news_overlay_book_grade/v1", "run_id": run_id, "label": "FORWARD",
                     "policy_hash": c["policy_hash"], "sessions": len(sessions),
                     "overlay_total_pct": 100 * ov, "twin_total_pct": 100 * tw,
                     "overlay_cost_usd": sum(r["overlay_cost"] for r in sr),
                     "twin_cost_usd": sum(r["twin_cost"] for r in sr), "daily": sr})
    print(f"FORWARD {len(sessions)} sessions {sessions[0]}..{sessions[-1]}: RAW overlay {100 * ov:+.3f}% "
          f"twin {100 * tw:+.3f}% diff {100 * (ov - tw):+.3f} pp -> {rp}")
    return 0


def main(argv=None) -> int:
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
    try:
        return {"contract": cmd_contract, "replay": cmd_replay, "step": cmd_step,
                "grade": cmd_grade}[a.cmd](a)
    except NO.NewsOverlayRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
