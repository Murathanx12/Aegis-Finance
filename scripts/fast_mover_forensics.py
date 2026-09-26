"""Chunk A runner: every forward position that moved fast, and why.

    python -m scripts.fast_mover_forensics                 # full run, 10 X quests
    python -m scripts.fast_mover_forensics --x-quests 0    # no OpenClaw
    python -m scripts.fast_mover_forensics --refetch-fleet # re-GET Alpaca fills
    python -m scripts.fast_mover_forensics --build-rule-holdings  # library holdings only

The main run needs `forensics/rule_holdings_<day>.json` (every non-control
strategy-library rule's holdings by rebalance date). When it is missing the
main run builds it in a CHILD process first, so the monthly panel's memory is
returned before the forensics load their own bars.

Read-only everywhere: Alpaca is read with GET /v2/account/activities/FILL, the
aegis DB is SELECTed, nothing places an order, nothing writes under `sim/`.
Receipts: backend/data/optimus/forensics/fast_movers_<date>.json + FAST_MOVERS.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import fast_mover_forensics as F    # noqa: E402

#: The +10% night books' names the adjudication asks about by name.
NAMED = ("NUAI", "AXTI", "TWST", "MU")
#: Holdings older than this are not written (no case enters before 2026-05).
HOLDINGS_SINCE = "2024-06-01"


def rule_holdings_path(day: str) -> Path:
    return F.OUT_DIR / f"rule_holdings_{day}.json"


def build_rule_holdings(day: str) -> Path:
    """Every non-control library rule's top-k holdings at every rebalance
    since HOLDINGS_SINCE, from the factory's own panel and engine
    (`strategy_library.run_strategy(..., holdings=)`), at the k the
    leaderboard reports. CPU only, $0."""
    import pandas as pd
    from scripts import night_backtest_factory as NBF
    from backend import config as C
    from backend.services import strategy_library as SL
    from backend.services import xs_ranker as XR
    t0 = time.time()
    W = NBF.load_wide(XR.survivorship_free_paths(), start=C.STRATEGY_LIB_START)
    panel = NBF.build_panel(W, delist_return=float(C.STRATEGY_LIB_DELIST_RETURN))
    for c_ in ("high", "low", "volume"):
        W.pop(c_, None)
    panel, fmeta = NBF.attach_fundamentals(panel)
    panel, flmeta = NBF.attach_flow(panel)
    extra = {}
    for name, fn in (("ratings", lambda p: NBF.attach_ratings(p, W)),
                     ("insider", NBF.attach_insider),
                     ("eightk", lambda p: NBF.attach_8k(p, W)),
                     ("short_interest", NBF.attach_short_interest),
                     ("sector", NBF.attach_sector),
                     ("extension", lambda p: NBF.attach_extension(p, W))):
        try:
            panel, extra[name] = fn(panel)
        except Exception as e:                                # noqa: BLE001
            extra[name] = {"status": "REFUSED", "why": f"{type(e).__name__}: {e}"}
    panel["tiebreak"] = SL._tiebreak(panel)
    # run_strategy skips a period whose forward return is still open, so the
    # LAST month-end decision (the one a September entry actually sat under)
    # would be missing and the join would silently fall back a month. Drop a
    # trailing mid-month "decision" (the panel's last session, not a month
    # end) and give the open month-end period a 0 forward return so its
    # rebalance is recorded. Holdings only -- no return is read from here.
    import numpy as np
    ds = pd.DatetimeIndex(sorted(panel["date"].unique()))
    # only the TRAILING date can be a mid-month stub (a pre-holiday month end
    # such as 2018-03-29 also has a same-month next business day)
    not_me = [ds[-1]] if (ds[-1] + pd.offsets.BDay(1)).month == ds[-1].month else []
    panel = panel[~panel["date"].isin(not_me)].copy()
    open_dates = [d for d, g in panel.groupby("date")["fwd_ret"]
                  if not np.isfinite(g.to_numpy(dtype=float)).any()]
    panel.loc[panel["date"].isin(open_dates), "fwd_ret"] = 0.0
    print(f"dropped mid-month decision dates {[str(d.date()) for d in not_me]}; "
          f"open month-end periods recorded: {[str(pd.Timestamp(d).date()) for d in open_dates]}",
          flush=True)
    print(f"panel {len(panel):,} rows, {panel['date'].nunique()} dates, last "
          f"{panel['date'].max().date()}  [{time.time() - t0:.0f}s]", flush=True)
    board = json.loads((NBF.out_dir() / f"leaderboard_{day}.json").read_text(encoding="utf-8")) \
        if (NBF.out_dir() / f"leaderboard_{day}.json").exists() else None
    if board is None:
        lbs = sorted(NBF.out_dir().glob("leaderboard_*.json"))
        board = json.loads(lbs[-1].read_text(encoding="utf-8")) if lbs else {"all_rows": []}
    rows = sorted([r for r in board.get("all_rows", []) if not r.get("control")],
                  key=NBF.sealed_sort_key, reverse=True)
    meta = {r["id"]: {"sealed_rank": i + 1, "sealed_vs_spy": r.get("sealed_vs_spy"),
                      "k": r.get("k"), "family": r.get("family")}
            for i, r in enumerate(rows)}
    holdings, refused = {}, {}
    for rule in SL.rules(include_controls=False):
        k = int((meta.get(rule.id) or {}).get("k") or rule.k)
        hold: list = []
        try:
            SL.run_strategy(panel, rule, k=k, holdings=hold)
        except Exception as e:                                # noqa: BLE001 -- named
            refused[rule.id] = f"{type(e).__name__}: {e}"
            continue
        holdings[rule.id] = {h["date"]: h["symbols"] for h in hold
                             if h["date"] >= HOLDINGS_SINCE}
    out = {"schema": "fast_mover_forensics.rule_holdings/1", "day": day,
           "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "source": "strategy_library.run_strategy(panel, rule, k=board k, holdings=[]) "
                     "on night_backtest_factory's panel (same start, same attachers)",
           "leaderboard": board.get("date"), "since": HOLDINGS_SINCE,
           "panel": {"rows": int(len(panel)), "last_date": str(panel["date"].max().date())},
           "attachers": {"fundamentals": fmeta.get("status"), "flow": flmeta.get("status"),
                         **{k_: v.get("status") for k_, v in extra.items()}},
           "pit_note": "a rebalance on date d is decided at d's close; the forensics join "
                       "uses the last rebalance with d <= R (the last close knowable at entry)",
           "dropped_mid_month_decisions": [str(d.date()) for d in not_me],
           "open_periods_recorded": [str(pd.Timestamp(d).date()) for d in open_dates],
           "n_rules": len(holdings), "refused": refused, "rule_meta": meta,
           "holdings": holdings, "runtime_s": round(time.time() - t0, 1)}
    path = rule_holdings_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out), encoding="utf-8")
    tmp.replace(path)
    print(f"wrote {path}: {len(holdings)} rules, {len(refused)} refused  "
          f"[{time.time() - t0:.0f}s]", flush=True)
    return path


def ensure_rule_holdings(day: str) -> dict:
    """Load the holdings file, building it in a child process when absent.
    Refuses loudly (returns an empty join with the reason) rather than
    printing a SELECTABLE_BY_RULE count of 0 that means 'not joined'."""
    import subprocess
    p = rule_holdings_path(day)
    if not p.exists():
        print(f"{p.name} absent -- building it in a child process", flush=True)
        rc = subprocess.run([sys.executable, "-m", "scripts.fast_mover_forensics",
                             "--build-rule-holdings", "--day", day], cwd=str(REPO)).returncode
        if rc != 0 or not p.exists():
            return {"status": "REFUSED", "why": f"rule-holdings build rc={rc}",
                    "holdings": {}, "rule_meta": {}}
    d = json.loads(p.read_text(encoding="utf-8"))
    d["status"] = "OK"
    d["file"] = p.name
    return d


def archive_quarantine(day: str) -> dict:
    """Per-source count of corpus rows graded `archive` at read time; the
    receipt goes under news_corpus/_receipts/. The corpus is not rewritten."""
    from backend.services import news_registry as NR
    census = NR.archive_census(F.NEWS_DIR)
    census.update(receipt=f"news_corpus/_receipts/archive_quarantine_{day}.json",
                  generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  readers_graded=["backend.services.book_signals.load_news_rows",
                                  "backend.services.fast_mover_forensics.load_news "
                                  "(state_at_entry excludes archive rows)"])
    out = F.NEWS_DIR / "_receipts" / f"archive_quarantine_{day}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(census, indent=1), encoding="utf-8")
    return census


def named_rule_join(rows: list[dict], names=NAMED) -> dict:
    out = {}
    for tk in names:
        for r in sorted((r for r in rows if r["ticker"] == tk),
                        key=lambda r: (not r["priority"], r["R"])):
            key = f"{tk}@{r['R']}"
            if key in out:
                continue
            rk = (r.get("rule_join") or {}).get("sealed_rank_by_rule") or {}
            out[key] = {"ticker": tk, "R": r["R"], "book": r["book"],
                        "n_rules_selecting": r.get("n_rules_selecting", 0),
                        "rules_with_sealed_rank": [[rid, rk.get(rid)]
                                                   for rid in r.get("selectable_by_rules", [])]}
    return out


def fetch_fleet(cache: Path) -> dict:
    from scripts import fleet_trade_autopsy as FTA
    env = FTA._env()
    raw, by_role = [], {}
    for role in FTA.ROLES:
        kid, sec = env.get(f"AAT_{role}_KEY_ID"), env.get(f"AAT_{role}_SECRET_KEY")
        if not (kid and sec):
            by_role[role] = "no key"
            continue
        try:
            got = FTA.fills(role, kid, sec, max_rows=5000)
            raw += got
            by_role[role] = len(got)
        except Exception as exc:                              # noqa: BLE001
            by_role[role] = f"{type(exc).__name__}: {exc}"
    d = {"fetched_utc": datetime.now(timezone.utc).isoformat(),
         "source": "GET paper-api.alpaca.markets/v2/account/activities/FILL (read-only)",
         "by_role": by_role, "fills": raw}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(d), encoding="utf-8")
    return d


def llm_spend(prefix: str = "fast_mover_forensics") -> dict:
    """Sum this chunk's rows in the house LLM ledger (the SAME ledger every
    cap reads), by purpose. None costs make the total a declared lower bound."""
    from backend.services import llm_telemetry as LT
    f = LT.LLM_CALLS.parent / f"{LT.LLM_CALLS.stem}_{date.today():%Y-%m}.jsonl"
    out = {"ledger": f.name, "calls": 0, "usd": 0.0, "unpriced_calls": 0, "by_purpose": {}}
    if not f.exists():
        return out
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            if prefix not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not str(r.get("purpose", "")).startswith(prefix):
                continue
            out["calls"] += 1
            c = r.get("cost_usd")
            if c is None:
                out["unpriced_calls"] += 1
            else:
                out["usd"] += float(c)
            k = str(r["purpose"]).split(":")[1] if ":" in str(r["purpose"]) else r["purpose"]
            out["by_purpose"][k] = round(out["by_purpose"].get(k, 0.0) + float(c or 0), 5)
    out["usd"] = round(out["usd"], 5)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--x-quests", type=int, default=F.X_QUEST_CAP)
    ap.add_argument("--no-adjudicate", action="store_true")
    ap.add_argument("--refetch-fleet", action="store_true")
    ap.add_argument("--day", default=date.today().isoformat())
    ap.add_argument("--reuse-quests", default=None,
                    help="a previous receipt whose x_quests are re-attached (no new quests)")
    ap.add_argument("--build-rule-holdings", action="store_true",
                    help="only build forensics/rule_holdings_<day>.json and exit")
    a = ap.parse_args(argv)
    t0 = time.time()
    if a.build_rule_holdings:
        build_rule_holdings(a.day)
        return 0
    rh = ensure_rule_holdings(a.day)
    print(f"rule holdings: {rh['status']} {len(rh.get('holdings', {}))} rules "
          f"{rh.get('why', '')}", flush=True)
    aq = archive_quarantine(a.day)
    print(f"archive quarantine: {aq['total_archive']:,} of {aq['total_rows']:,} corpus rows "
          f"-> {aq['receipt']}", flush=True)

    cache = F.OUT_DIR / f"fleet_fills_{a.day}.json"
    if a.refetch_fleet or not cache.exists():
        fl = fetch_fleet(cache)
        print(f"fleet fills fetched: {fl['by_role']}")
    fleet_meta = json.loads(cache.read_text(encoding="utf-8"))
    fleet_meta = {k: v for k, v in fleet_meta.items() if k != "fills"}

    positions, ctx = F.build_real_inputs(cache)
    ctx.rule_holdings = rh.get("holdings", {})
    ctx.rule_meta = rh.get("rule_meta", {})
    print(f"{len(positions)} positions; bars {ctx.closes.index.min().date()} -> "
          f"{ctx.closes.index.max().date()}, {ctx.closes.shape[1]} symbols; "
          f"sector map {len(ctx.sector)} names  [{time.time() - t0:.0f}s]")
    coverage: dict = {}
    cases = F.find_fast_movers(positions=positions, ctx=ctx, coverage=coverage)
    print(f"{len(cases)} fast-mover cases  [{time.time() - t0:.0f}s]")
    tickers = {c.position.ticker for c in cases}
    F.enrich_context(ctx, tickers)
    print(f"news rows for case tickers: {len(ctx.news)}; revisions "
          f"{0 if ctx.revisions is None else len(ctx.revisions)}; forecasts "
          f"{len(ctx.predictions)}  [{time.time() - t0:.0f}s]")

    # X quests: priority books first, then the largest |z|; one per (ticker, S)
    # probes run by hand before this script count against the same cap
    quests: list[dict] = []
    for f in sorted((F.OUT_DIR / "_quests").glob("probe_*.json")):
        pq = json.loads(f.read_text(encoding="utf-8"))
        pq.update(probe=True, probe_file=f.name)
        quests.append(pq)
    if a.reuse_quests:
        prev = json.loads(Path(a.reuse_quests).read_text(encoding="utf-8"))
        have = {q.get("probe_file") for q in quests}
        for q in prev.get("x_quests", []):
            if q.get("probe_file") not in have or not q.get("probe"):
                if not q.get("probe"):
                    quests.append(q)
        for q in quests:
            for c in cases:
                if (c.position.ticker, c.S) == (q.get("ticker"), q.get("S")):
                    ctx.x_posts[c.case_id] = q
        a.x_quests = 0
    n_probe = len(quests)
    if a.x_quests > 0:
        order = sorted(cases, key=lambda c: (not c.position.priority,
                                             -abs(c.z or 0)))
        seen, fails = set(), 0
        spent = sum(float(q.get("openclaw_cost_usd") or 0) for q in quests)
        for c in order:
            key = (c.position.ticker, c.S)
            if key in seen:
                continue
            if (len(quests) >= min(a.x_quests + n_probe, F.X_QUEST_CAP)
                    or spent >= F.X_QUEST_BUDGET_USD):
                break
            if fails >= 2:
                print("two failed quests in a row -- stopping X reads")
                break
            seen.add(key)
            q = F.x_quest(c.position.ticker, c.position.entry_ts,
                          workdir=F.OUT_DIR / "_quests")
            cost = q.get("openclaw_cost_usd")
            spent += float(cost or 0)
            fails = fails + 1 if q["status"] != "OK" else 0
            q.update(ticker=c.position.ticker, S=c.S, entry_ts=c.position.entry_ts)
            quests.append(q)
            for cc in cases:
                if (cc.position.ticker, cc.S) == key:
                    ctx.x_posts[cc.case_id] = q
            print(f"  X quest {c.position.ticker} {c.S}: {q['status']} "
                  f"{len(q['posts'])} pre-entry posts ({q['dropped_post_entry']} dropped "
                  f"post-entry), cost {cost}")

    adj = None if a.no_adjudicate else F.Adjudicator()
    rows = F.analyse(cases, ctx, adjudicate=adj)

    # The ~10% books made their gain on the 6th session (2026-09-21), one past
    # the declared window. A SUPPLEMENT, not a change of the declared rule.
    prio = [p for p in positions if p.priority]
    h6_cases = F.find_fast_movers(positions=prio, ctx=ctx, horizons=(6,))
    for c in h6_cases:
        for q in quests:
            if (q.get("ticker"), q.get("S")) == (c.position.ticker, c.S):
                ctx.x_posts[c.case_id] = q
    h6_rows = F.analyse(h6_cases, ctx, adjudicate=adj)
    summary = F.summarise(rows, coverage)
    book_mv = F.book_moves(positions, ctx)
    nj = named_rule_join(rows + h6_rows)
    print("\nwhich library rules held the +10% books' names at entry:")
    for k_, v in nj.items():
        print(f"  {k_} ({v['book']}): {v['n_rules_selecting']} -- "
              + ", ".join(f"{rid} (sealed #{rk})" for rid, rk in v["rules_with_sealed_rank"]))
    print("\nbook moves in book-sigma (priority books first):")
    for b in sorted(book_mv, key=lambda b: (not b.get("priority"), b["book"])):
        print(f"  {b['book']} {b.get('title') or ''} S={b['S']}: {F.book_sigma_line(b)}")
    meta = {
        "receipt": "fast_mover_forensics", "chunk": "A", "day": a.day,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "licence": "PRODUCT_EXPERIMENT (forensics; no claim)",
        "read_only": True, "orders_placed": 0,
        "thresholds": {"min_abs": F.MIN_ABS, "min_sigma": F.MIN_SIGMA,
                       "horizons": list(F.HORIZONS), "sigma_window": F.SIGMA_WINDOW,
                       "n_controls": F.N_CONTROLS, "credit_bar": "control median + 1 sigma_h"},
        "conventions": F.__doc__.split("Move conventions")[1].strip(),
        "bars": {"paths": "xs_ranker.survivorship_free_paths()",
                 "first": str(ctx.closes.index.min().date()),
                 "last": str(ctx.closes.index.max().date()),
                 "n_symbols": int(ctx.closes.shape[1])},
        "data_notes": [
            "news corpus first_seen_utc starts 2026-09-11: pre-entry news for earlier "
            "entries is structurally empty, not absent",
            "archive quarantine (wave-1 row 12): a corpus row whose published_utc precedes "
            "first_seen_utc by > 30 days is pit_grade 'archive' at read time and excluded "
            "from state_at_entry; a forecast whose resolves_after < entry date is expired "
            "and never 'visible'",
            "SELECTABLE_BY_RULE (wave-1 row 11): a favourable case on a name >= 1 "
            "non-control library rule held at its last rebalance <= R; credits no book; "
            "the ex-post label is kept in class_before_rule_join",
            "news rows whose published_utc <= entry but first_seen_utc > entry are "
            "counted as published_before_entry_seen_after and kept OUT of both columns",
            "sector = GICS 2-digit from JKP x CRSP-PIT (vintage 2024-12); names listed "
            "later are unmapped and controls fall back to the liquidity band",
            "sector move = equal-weight mean of eligible same-sector names (no sector "
            "ETFs in the bars panel)",
            "website lanes: the LOCAL DB mirror only (prod authoritative); they hold "
            "sector ETFs the bars panel does not carry, so most are UNPRICED",
            "PC-PAPER first traded 2026-09-25, after the panel's last session: UNPRICED",
            "search attention: no column exists anywhere in the repo's data",
            "fleet: entries rebuilt FIFO from Alpaca fills; the terminal's per-decision "
            "thesis is NOT joined, so why_selected is the book name only",
            "target_revisions.event_date is vendor-stamped; the parquet was pulled "
            "2026-09-25, after most entries -- rows are PIT by event_date, not by pull",
        ],
        "fleet_fills": fleet_meta,
        "x_quests": quests,
        "x_quests_used": len(quests),
        "x_quests_cost_usd_openclaw": round(sum(float(q.get("openclaw_cost_usd") or 0)
                                                for q in quests), 4),
        "adjudications": adj.calls if adj else [],
        "priority_books_h6_supplement": {
            "why": "the three ~10% books gained on session 6 (2026-09-21), outside h in (1,5)",
            "summary": F.summarise(h6_rows, {}), "cases": h6_rows},
        "summary": summary,
        "honest_controls_sentence": F.HONEST_CONTROLS_SENTENCE.format(
            n_sel=summary.get("favourable_selectable_by_rule", 0),
            n_sel_u=summary.get("favourable_unique_ticker_entries_selectable", 0),
            n_priced=summary.get("n_positions_priced", 0)),
        "rule_holdings": {k_: rh.get(k_) for k_ in ("status", "why", "file", "leaderboard",
                                                    "since", "n_rules", "refused", "panel",
                                                    "attachers")},
        "named_rule_join": nj,
        "book_moves": book_mv,
        "archive_quarantine": {k_: v for k_, v in aq.items()},
        "llm_spend_house_ledger": llm_spend(),
        "runtime_s": round(time.time() - t0, 1),
    }
    jp, md = F.write_receipts(rows, meta, day=a.day)
    print(json.dumps(summary, indent=1, default=str))
    print(f"wrote {jp}\nwrote {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
