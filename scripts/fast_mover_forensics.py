"""Chunk A runner: every forward position that moved fast, and why.

    python -m scripts.fast_mover_forensics                 # full run, 10 X quests
    python -m scripts.fast_mover_forensics --x-quests 0    # no OpenClaw
    python -m scripts.fast_mover_forensics --refetch-fleet # re-GET Alpaca fills

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
    a = ap.parse_args(argv)
    t0 = time.time()

    cache = F.OUT_DIR / f"fleet_fills_{a.day}.json"
    if a.refetch_fleet or not cache.exists():
        fl = fetch_fleet(cache)
        print(f"fleet fills fetched: {fl['by_role']}")
    fleet_meta = json.loads(cache.read_text(encoding="utf-8"))
    fleet_meta = {k: v for k, v in fleet_meta.items() if k != "fills"}

    positions, ctx = F.build_real_inputs(cache)
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
        "llm_spend_house_ledger": llm_spend(),
        "runtime_s": round(time.time() - t0, 1),
    }
    jp, md = F.write_receipts(rows, meta, day=a.day)
    print(json.dumps(summary, indent=1, default=str))
    print(f"wrote {jp}\nwrote {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
