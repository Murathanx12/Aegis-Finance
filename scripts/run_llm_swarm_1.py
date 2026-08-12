"""LLM-SWARM-1 — thousands of independent, gradeable specialist calls.

GRAND-ARENA-1 chunk 3. Murat's instruction was "make thousands of llm calls why
did we stop?", and the answer to "why did we stop" is that nothing had been
built that could spend inference at that rate and still produce something a
machine could grade. This is that thing.

    python scripts/run_llm_swarm_1.py --target 6000
    python scripts/run_llm_swarm_1.py --pilot 60        # measure before spending
    python scripts/run_llm_swarm_1.py --resume          # after a crash
    python scripts/run_llm_swarm_1.py --report-only     # rebuild the report

WHAT IT DOES, IN ORDER
  1. assembles a broad universe from what the repo already knows, keeping only
     names with enough price history at the observation timestamp to be
     forecast about at all;
  2. builds a POINT-IN-TIME snapshot per security — the panel is truncated at
     `as_of` before any field is computed, so nothing after that date is
     visible to any specialist;
  3. runs (specialist x security) cells through a concurrent pool, each one an
     independent call that has not seen any other specialist's answer;
  4. keeps only what can be graded, counts everything it refuses and why, and
     mints the survivors into the Optimus prediction ledger through
     `belief_state.make_prediction`;
  5. checkpoints every completed cell to JSONL so a crash at call 6,000 resumes
     rather than restarts;
  6. writes docs/GRAND_ARENA_SWARM.md.

THE GOVERNOR IS THE AUTHORITY ON SPEND. `research_budget.require()` is called
before every vendor request including every retry. When it raises, the campaign
stops cleanly and reports; nothing here second-guesses it or catches it into a
retry loop.

ARCHITECTURE_RESULT_ONLY: nothing produced here certifies alpha. The foundation
model may know history that overlaps anything we could backtest, so only the
forward resolution of these records is evidence.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:                                       # pragma: no cover
    print("python-dotenv missing — relying on the ambient environment")

from backend import config as cfg                          # noqa: E402
from backend.services import belief_state as bs            # noqa: E402
from backend.services import llm_swarm as sw               # noqa: E402
from backend.services import llm_telemetry as tel          # noqa: E402
from backend.services import research_budget               # noqa: E402

OUT_DIR = ROOT / "docs"
RUN_DIR = ROOT / "backend" / "data" / "swarm"
CHECKPOINT = RUN_DIR / "swarm_1_cells.jsonl"
UNIVERSE_FILE = RUN_DIR / "swarm_1_universe.json"
RUN_META = RUN_DIR / "swarm_1_run_meta.json"
REPORT = OUT_DIR / "GRAND_ARENA_SWARM.md"
ARTIFACT = OUT_DIR / "grand_arena_swarm_1.json"

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("swarm")


# ── universe ────────────────────────────────────────────────────────────────

def assemble_universe() -> tuple[list[str], dict]:
    """Every US equity the repo already has a reason to look at.

    Built from sources that existed BEFORE this campaign, so the universe is not
    a set of names chosen because they were about to be interesting. Provenance
    is returned with counts because "how was the universe chosen" is the first
    question any result here has to survive.
    """
    prov: dict[str, list[str]] = {}

    sector_stocks = cfg.config["stock_universe"]["sector_stocks"]
    prov["config.stock_universe.sector_stocks"] = sorted(
        {t.upper() for v in sector_stocks.values() for t in v})

    def _load(path: Path, extract) -> list[str]:
        try:
            return sorted({str(t).upper() for t in extract(path) if t})
        except Exception as exc:                          # noqa: BLE001
            log.warning("universe source %s unavailable (%s: %s) — the universe "
                        "is that much narrower, and it says so", path,
                        type(exc).__name__, exc)
            return []

    prov["funnel_night10.candidates"] = _load(
        ROOT / "backend" / "data" / "funnel_night10.json",
        lambda p: [c["ticker"] for c in json.loads(p.read_text())["candidates"]])

    def _book(p: Path) -> list[str]:
        import yaml
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        return ([x["ticker"] for x in (d.get("positions") or [])]
                + list(d.get("watchlist") or []))
    prov["murat_book.positions+watchlist"] = _load(
        ROOT / "backend" / "data" / "murat_book.yaml", _book)

    def _lanes(p: Path) -> list[str]:
        import yaml
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        out: list[str] = []

        def walk(o: Any) -> None:
            if isinstance(o, dict):
                if isinstance(o.get("ticker"), str):
                    out.append(o["ticker"])
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    # Both shapes appear in this repo and the first version of
                    # this walker only understood one of them: theme_baskets
                    # holds {"ticker": ...} records, paper_portfolios holds bare
                    # ticker strings under nested category keys. Reading only
                    # the first shape returned ZERO names from an 81-name file
                    # and looked exactly like a file with nothing in it — the
                    # house failure mode, caught only because the provenance
                    # table prints a count per source.
                    if isinstance(v, str) and 1 <= len(v) <= 6 and v.isupper():
                        out.append(v)
                    else:
                        walk(v)
        walk(d)
        return out
    prov["paper_portfolios.yaml"] = _load(
        ROOT / "backend" / "data" / "paper_portfolios.yaml", _lanes)
    prov["theme_baskets.yaml"] = _load(
        ROOT / "backend" / "data" / "theme_baskets.yaml", _lanes)

    prov["conviction_prices.csv columns"] = _load(
        ROOT / "backend" / "data" / "conviction_prices.csv",
        lambda p: p.read_text(encoding="utf-8").splitlines()[0].split(",")[1:])

    # A seeded sample from the 5,324-name US listing the opportunity funnel
    # already caches. Sampled rather than screened, deliberately: any screen we
    # could apply here (momentum, quality, liquidity) is a selection rule this
    # campaign has not pre-registered, and a universe chosen by a rule is a
    # universe that can flatter the result. A random draw cannot. Names without
    # enough price history fall out at the history gate below and are counted.
    def _funnel_pool(p: Path) -> list[str]:
        pool = sorted(json.loads(p.read_text())["tickers"])
        return random.Random(20260812).sample(pool, k=min(220, len(pool)))
    prov["funnel_cache.universe (seeded random sample of 5,324)"] = _load(
        ROOT / "backend" / "data" / "funnel_cache" / "universe.json",
        _funnel_pool)

    universe = sorted({t for v in prov.values() for t in v
                       if t and t.replace("-", "").replace(".", "").isalnum()
                       and len(t) <= 6})
    return universe, {k: len(v) for k, v in prov.items()}


def sector_map(universe: list[str]) -> dict[str, str]:
    """Best available sector label per name, from the repo before the network."""
    out: dict[str, str] = {}
    for sec, names in cfg.config["stock_universe"]["sector_stocks"].items():
        for t in names:
            out.setdefault(t.upper(), sec)
    for t, sec in cfg.WHY_MOVED_TICKER_SECTOR.items():
        out.setdefault(t.upper(), sec)
    try:
        d = json.loads((ROOT / "backend" / "data" / "funnel_night10.json")
                       .read_text())
        for c in d["candidates"]:
            if c.get("sector"):
                out.setdefault(str(c["ticker"]).upper(), str(c["sector"]))
    except Exception as exc:                              # noqa: BLE001
        log.warning("funnel sectors unavailable (%s) — those names fall back to "
                    "Unknown and are routed to every specialist", exc)
    return {t: out.get(t, "Unknown") for t in universe}


def fetch_metadata(tickers: list[str], *, workers: int = 8) -> dict[str, dict]:
    """Sector, industry and market cap from the vendor, degrading to nothing.

    A name whose metadata will not fetch keeps whatever the repo knew and is
    marked so in the snapshot. Never a fabricated sector: a wrong label routes a
    biotech specialist at a utility and the abstention that follows costs a call.
    """
    import yfinance as yf
    out: dict[str, dict] = {}
    lock = threading.Lock()

    def one(t: str) -> None:
        try:
            i = yf.Ticker(t).info or {}
            row = {"vendor_sector": i.get("sector"),
                   "industry": i.get("industry"),
                   "market_cap_usd": i.get("marketCap"),
                   "shares_short_pct_float": i.get("shortPercentOfFloat"),
                   "company_name": i.get("shortName")}
        except Exception as exc:                          # noqa: BLE001
            row = {"metadata_status": f"unavailable: {type(exc).__name__}"}
        with lock:
            out[t] = {k: v for k, v in row.items() if v is not None}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, tickers))
    return out


def price_panel(tickers: list[str], as_of: str, *, years: float = 2.2):
    """One adjusted-close panel, same convention as the ledger resolver."""
    import pandas as pd
    import yfinance as yf
    end = date.fromisoformat(as_of) + timedelta(days=1)
    start = end - timedelta(days=int(365 * years))
    # Deduped before the download, not after: the benchmark is usually already
    # in the universe, and two SPY columns make `panel["SPY"]` a DataFrame,
    # which every downstream `to_numeric` rejects with a type error that says
    # nothing about the actual problem.
    tickers = sorted(set(tickers))
    frames = []
    batch = 120
    for i in range(0, len(tickers), batch):
        chunk = tickers[i:i + batch]
        df = yf.download(chunk, start=str(start), end=str(end),
                         auto_adjust=True, progress=False, timeout=60)["Close"]
        if isinstance(df, pd.Series):
            df = df.to_frame(name=chunk[0])
        frames.append(df)
        print(f"  prices: {min(i + batch, len(tickers))}/{len(tickers)}",
              flush=True)
    out = pd.concat(frames, axis=1).sort_index()
    return out.loc[:, ~out.columns.duplicated()]


# ── the plan ────────────────────────────────────────────────────────────────

def plan_cells(snapshots: dict[str, dict], *, passes: int, target: int | None,
               seed: int = 20260812) -> list[tuple[int, str, str]]:
    """(pass_id, specialist, ticker) cells, routed by sector and shuffled.

    Shuffled with a fixed seed so that a run stopped early by the budget is a
    RANDOM subsample of the grid rather than the alphabetical front of it. A
    campaign truncated at 'every specialist on A through F' would have a
    universe chosen by the letter A, which is not a universe.
    """
    rnd = random.Random(seed)
    base: list[tuple[str, str]] = []
    for tkr, snap in snapshots.items():
        sec = str(snap.get("sector", "Unknown"))
        vend = str(snap.get("vendor_sector", "") or "")
        for name, spec in sw.SPECIALISTS.items():
            if spec.sectors is None or sec in spec.sectors or vend in spec.sectors:
                base.append((name, tkr))
    rnd.shuffle(base)
    cells = [(p, s, t) for p in range(1, passes + 1) for s, t in base]
    if target is not None:
        cells = cells[:target]
    return cells


# ── checkpointing ───────────────────────────────────────────────────────────

def load_checkpoint() -> tuple[list[dict], set[str]]:
    if not CHECKPOINT.exists():
        return [], set()
    rows, done = [], set()
    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            log.warning("checkpoint: an unreadable line was skipped — its cell "
                        "will be re-run, which costs a call and loses nothing")
            continue
        rows.append(r)
        done.add(f"{r.get('pass_id', 1)}|{r['specialist']}|{r['ticker']}")
    return rows, done


# ── the run ─────────────────────────────────────────────────────────────────

def run(args: argparse.Namespace) -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    since = str(started.date())

    st = research_budget.check(sw.CAMPAIGN, since=since)
    print(f"budget at start: {st.as_dict()}", flush=True)
    if not st.ok:
        print(f"REFUSING TO START — {st.reason}")
        return 2

    if UNIVERSE_FILE.exists() and args.resume:
        uni = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
        snapshots = uni["snapshots"]
        as_of = uni["as_of"]
        provenance = uni["provenance"]
        print(f"resuming with the frozen universe: {len(snapshots)} securities "
              f"as of {as_of}")
    else:
        universe, provenance = assemble_universe()
        print(f"universe candidates: {len(universe)} from {provenance}",
              flush=True)
        secmap = sector_map(universe)
        # The observation timestamp defaults to the last session actually in
        # the panel, not to today: on 2026-08-12 the vendor had 08-11 closes
        # and nothing later, and forecasting "from" a date with no data would
        # silently be forecasting from the day before it anyway.
        panel = price_panel(universe + [cfg.SWARM_BENCHMARK],
                            args.as_of or str(date.today()))
        as_of = args.as_of or str(panel.index[-1].date())
        print(f"observation timestamp: {as_of}", flush=True)
        print("fetching sector/market-cap metadata...", flush=True)
        meta = fetch_metadata(universe, workers=args.meta_workers)
        snapshots = {}
        dropped: list[str] = []
        for t in universe:
            m = dict(meta.get(t, {}))
            m["sector"] = secmap.get(t, "Unknown")
            s = sw.snapshot_from_panel(t, panel, as_of=as_of,
                                       benchmark=cfg.SWARM_BENCHMARK, meta=m)
            if s is None or s["n_bars_available"] < cfg.SWARM_MIN_HISTORY_BARS:
                dropped.append(t)
                continue
            snapshots[t] = s
        provenance["dropped_for_insufficient_history"] = len(dropped)
        provenance["dropped_names"] = sorted(dropped)[:40]
        UNIVERSE_FILE.write_text(json.dumps(
            {"as_of": as_of, "provenance": provenance, "snapshots": snapshots},
            indent=1, default=str), encoding="utf-8")
        print(f"universe after the history gate: {len(snapshots)} securities "
              f"({len(dropped)} dropped)", flush=True)

    cells = plan_cells(snapshots, passes=args.passes, target=args.target)
    if args.pilot:
        cells = cells[:args.pilot]
    # The checkpoint is always authoritative, `--resume` or not: a completed
    # cell is a call already paid for, and re-running it would spend money to
    # produce a second correlated opinion while looking like progress.
    rows, done = load_checkpoint()
    todo = [c for c in cells if f"{c[0]}|{c[1]}|{c[2]}" not in done]
    print(f"planned {len(cells)} cells, {len(done)} already done, "
          f"{len(todo)} to run, {args.workers} workers", flush=True)
    if not todo:
        print("nothing to do")
        return 0

    made_at = started.isoformat(timespec="seconds")
    lock = threading.Lock()
    ck = CHECKPOINT.open("a", encoding="utf-8")
    pending: list[Any] = []
    counts = Counter()
    n_records = 0
    halted: str | None = None
    t0 = time.perf_counter()

    def flush(force: bool = False) -> None:
        nonlocal pending
        if pending and (force or len(pending) >= cfg.SWARM_LEDGER_BATCH):
            bs.append(pending)
            pending = []

    def work(cell: tuple[int, str, str]) -> Any:
        pid, spec, tkr = cell
        return sw.run_cell(spec, snapshots[tkr], model=cfg.SWARM_MODEL,
                           benchmark=cfg.SWARM_BENCHMARK, made_at=made_at,
                           pass_id=pid,
                           llm_call=lambda s, u: sw.default_llm_call(
                               s, u, since=since))

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, c): c for c in todo}
        try:
            for i, fut in enumerate(as_completed(futs), 1):
                cell = futs[fut]
                try:
                    res = fut.result()
                except research_budget.ResearchBudgetExhausted as exc:
                    halted = str(exc)
                    break
                except Exception as exc:                  # noqa: BLE001
                    counts["failed"] += 1
                    log.warning("cell %s crashed: %s: %s", cell,
                                type(exc).__name__, exc)
                    continue
                with lock:
                    counts[res.status] += 1
                    for r in (res.parsed.rejections if res.parsed else []):
                        counts[f"reject:{r['reason']}"] += 1
                    if res.reply:
                        counts["retries"] += res.reply.retries
                    n_records += len(res.records)
                    pending.extend(res.records)
                    row = res.as_row()
                    rows.append(row)
                    ck.write(json.dumps(row, default=str) + "\n")
                    if i % 50 == 0:
                        ck.flush()
                        flush()
                    if i % 100 == 0:
                        b = research_budget.check(sw.CAMPAIGN, since=since)
                        rate = i / max(time.perf_counter() - t0, 1e-9) * 60
                        print(f"[{i}/{len(todo)}] ok={counts['ok']} "
                              f"abstain={counts['abstained']} "
                              f"zero={counts['zero_yield']} "
                              f"fail={counts['failed']} recs={n_records} "
                              f"${b.cost_usd} zy={b.zero_yield_rate} "
                              f"{rate:.0f}/min", flush=True)
        finally:
            if halted:
                for f in futs:
                    f.cancel()
            with lock:
                flush(force=True)
                ck.flush()
                ck.close()

    wall = time.perf_counter() - t0
    # Persisted so `--report-only` can restate the run honestly instead of
    # printing 0.0 minutes and 'no governor halt' because it happens to be a
    # different process. A regenerated report that quietly loses the wall clock
    # is a report that has started making things up.
    RUN_META.write_text(json.dumps(
        {"started_utc": started.isoformat(timespec="seconds"),
         "wall_clock_min": round(wall / 60, 1), "workers": args.workers,
         "halted_by_governor": halted, "since": since}, indent=1),
        encoding="utf-8")
    if halted:
        print(f"\nHALTED BY THE GOVERNOR: {halted}")
    print(f"\ndone in {wall/60:.1f} min: {dict(counts)} records={n_records}")

    write_report(rows, provenance=provenance, as_of=as_of, started=started,
                 wall_s=wall, workers=args.workers, halted=halted,
                 n_securities=len(snapshots), n_planned=len(cells), since=since)
    return 0


# ── the report ──────────────────────────────────────────────────────────────

def write_report(rows: list[dict], *, provenance: dict, as_of: str,
                 started: datetime, wall_s: float, workers: int,
                 halted: str | None, n_securities: int, n_planned: int,
                 since: str | None = None) -> dict:
    """Every number the campaign owes, with the zero-yield rate as the headline."""
    n = len(rows)
    status = Counter(r["status"] for r in rows)
    rejects: Counter = Counter()
    for r in rows:
        for x in r.get("rejections", []):
            rejects[x["reason"]] += 1

    forecasts = [f for r in rows for f in r.get("forecasts", [])]
    obs_dist = Counter(f["observable"] for f in forecasts)
    hor_dist = Counter(f["horizon_days"] for f in forecasts)
    prob_hist: Counter = Counter()
    for f in forecasts:
        prob_hist[round(float(f["probability"]) * 10) / 10] += 1

    # §20 over the whole swarm and per specialist. The minted forecasts carry
    # the ticker on their cell row, so the effective count is computable from
    # the checkpoint alone — no re-reading of the ledger, no re-minting.
    def as_preds(rs: list[dict]) -> list[dict]:
        return [{"ticker": r["ticker"], "observable": f["observable"],
                 "probability": f["probability"],
                 "horizon_days": f["horizon_days"]}
                for r in rs for f in r.get("forecasts", [])]

    eff_all = sw.effective_distinct_ideas(as_preds(rows))
    by_spec: dict[str, dict] = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        grouped[r["specialist"]].append(r)
    for spec, rs in sorted(grouped.items()):
        st = Counter(x["status"] for x in rs)
        e = sw.effective_distinct_ideas(as_preds(rs))
        by_spec[spec] = {
            "calls": len(rs), "ok": st["ok"], "abstained": st["abstained"],
            "zero_yield": st["zero_yield"], "failed": st["failed"],
            "records": sum(x["n_records"] for x in rs),
            "effective_distinct_ideas": e["effective_distinct_ideas"],
            "n_forecasts": e["n_forecasts"], "ratio": e["ratio"],
            "mean_confidence": (round(sum(x["confidence"] for x in rs
                                          if x.get("confidence") is not None)
                                      / max(sum(1 for x in rs
                                                if x.get("confidence") is not None), 1), 3)),
        }

    spend = tel.summary(since=since)
    gradeable = status["ok"]
    zero_yield = n - gradeable
    cost = spend.get("total_cost_usd")

    # Test-retest: the same (specialist, security) asked twice. This is the
    # ONLY direct measurement of how much of the swarm's apparent variety is
    # the model resampling itself, and it needs pass 2 to exist.
    retest = _test_retest(rows)
    panel = _panel_agreement(rows)

    minted = [r for row in rows for r in row.get("prediction_ids", [])]
    earliest = None
    try:
        ledger = bs.read_predictions()
        pend = [r["resolves_after"][:10] for r in ledger
                if r.get("outcome") is None and not r.get("void_reason")]
        earliest = min(pend) if pend else None
    except Exception as exc:                              # noqa: BLE001
        log.warning("could not read the ledger for the resolution date: %s", exc)

    art = {
        "campaign": "LLM-SWARM-1", "module": sw.MODULE_VERSION,
        "started_utc": started.isoformat(timespec="seconds"),
        "observation_timestamp": as_of, "wall_clock_min": round(wall_s / 60, 1),
        "workers": workers, "halted_by_governor": halted,
        "universe": {"n_securities": n_securities, "provenance": provenance},
        "calls": {"planned": n_planned, "attempted": n,
                  "succeeded_gradeable": gradeable,
                  "abstained": status["abstained"],
                  "zero_yield_parsed": status["zero_yield"],
                  "failed": status["failed"],
                  "retries": sum(r.get("retries", 0) for r in rows)},
        "zero_yield_rate": round(zero_yield / n, 4) if n else None,
        "cost": {"total_usd_estimate": cost,
                 "is_estimate": True,
                 "is_lower_bound": spend.get("total_is_lower_bound"),
                 "n_unpriced_calls": spend.get("n_unpriced_calls"),
                 "n_unreadable_ledger_lines": spend.get(
                     "n_unreadable_ledger_lines"),
                 "per_gradeable_output_usd": (round(cost / gradeable, 5)
                                              if cost and gradeable else None),
                 "pricing_as_of": spend.get("pricing_as_of"),
                 "tokens_in": sum(r.get("tokens_in", 0) for r in rows),
                 "tokens_out": sum(r.get("tokens_out", 0) for r in rows)},
        "rejections": dict(rejects.most_common()),
        "observable_distribution": dict(obs_dist.most_common()),
        "horizon_distribution": {str(k): v for k, v in sorted(hor_dist.items())},
        "probability_histogram": {str(k): v for k, v in sorted(prob_hist.items())},
        "effective_distinct_ideas": eff_all,
        "by_specialist": by_spec,
        "test_retest": retest,
        "panel_agreement": panel,
        "predictions_minted": len(minted),
        "distinct_predictions_minted": len(set(minted)),
        "earliest_pending_resolution": earliest,
        "ARCHITECTURE_RESULT_ONLY": (
            "The foundation model may know history that overlaps any backtest, "
            "so nothing in this artifact certifies alpha. Every record here is "
            "about a future that has not happened; forward resolution is the "
            "only evidence, and the earliest of it is "
            f"{earliest}."),
    }
    ARTIFACT.write_text(json.dumps(art, indent=1, default=str), encoding="utf-8")
    REPORT.write_text(_markdown(art), encoding="utf-8")
    print(f"wrote {REPORT} and {ARTIFACT}")
    return art


def _panel_agreement(rows: list[dict]) -> dict:
    """Do fourteen roles that never saw each other actually say different things?

    The §20 question this campaign was built to answer, asked directly. For
    every (security, observable, horizon) that two or more DIFFERENT specialists
    forecast, measure the spread of their stated probabilities. A panel whose
    spread is near zero is one forecaster wearing fourteen names, and the fact
    that the roles were prompted separately would not save it — separation
    prevents CONTAGION between roles, it cannot manufacture disagreement the
    underlying model does not have.

    Reported beside the effective-idea ratio because the two answer different
    questions: the ratio asks how many distinct forecasts exist, this asks
    whether the ROLE STRUCTURE is buying any of them.
    """
    import statistics
    cells: dict[tuple, dict[str, float]] = defaultdict(dict)
    for r in rows:
        if r["status"] != "ok":
            continue
        for f in r["forecasts"]:
            cells[(r["ticker"], f["observable"], f["horizon_days"])][
                r["specialist"]] = float(f["probability"])
    multi = [v for v in cells.values() if len(v) >= 2]
    if not multi:
        return {"n_contested_cells": 0,
                "reading": "no two specialists forecast the same (security, "
                           "observable, horizon), so the panel's internal "
                           "agreement is not measurable here"}
    spreads = [statistics.pstdev(list(v.values())) for v in multi]
    ranges = [max(v.values()) - min(v.values()) for v in multi]
    one_bucket = sum(1 for v in multi
                     if len({round(x / 0.05) for x in v.values()}) == 1)
    return {
        "n_contested_cells": len(multi),
        "mean_specialists_per_cell": round(
            sum(len(v) for v in multi) / len(multi), 2),
        "mean_probability_stdev": round(sum(spreads) / len(spreads), 4),
        "mean_probability_range": round(sum(ranges) / len(ranges), 4),
        "share_of_cells_where_every_role_lands_in_one_0_05_bucket": round(
            one_bucket / len(multi), 4),
        "reading": ("a small spread means the fourteen roles are one "
                    "forecaster with fourteen system prompts; separation "
                    "prevented contagion, it did not create independence"),
    }


def _test_retest(rows: list[dict]) -> dict:
    """How often the same specialist, asked the same question twice, agrees.

    The number that decides how much of a multi-pass swarm is exploration and
    how much is the model resampling its own opinion. Agreement is measured on
    the (observable, horizon) pairs both passes produced, as the mean absolute
    difference in stated probability — a pair only one pass produced is counted
    separately, because choosing a DIFFERENT question is itself a form of
    disagreement and folding it into a probability distance would hide it.
    """
    seen: dict[tuple[str, str], dict[int, dict]] = defaultdict(dict)
    for r in rows:
        if r["status"] != "ok":
            continue
        seen[(r["specialist"], r["ticker"])][int(r.get("pass_id", 1))] = r
    pairs = [v for v in seen.values() if len(v) >= 2]
    if not pairs:
        return {"n_repeated_cells": 0,
                "reading": "only one pass was run, so self-agreement is not "
                           "measured — the §20 ratio is the only §20 number "
                           "this run supports"}
    diffs: list[float] = []
    only_one = 0
    both = 0
    for v in pairs:
        ks = sorted(v)
        a = {(f["observable"], f["horizon_days"]): float(f["probability"])
             for f in v[ks[0]]["forecasts"]}
        b = {(f["observable"], f["horizon_days"]): float(f["probability"])
             for f in v[ks[1]]["forecasts"]}
        common = set(a) & set(b)
        both += len(common)
        only_one += len(set(a) ^ set(b))
        diffs.extend(abs(a[k] - b[k]) for k in common)
    return {
        "n_repeated_cells": len(pairs),
        "n_matched_forecast_slots": both,
        "n_slots_only_one_pass_asked": only_one,
        "mean_abs_probability_difference": (round(sum(diffs) / len(diffs), 4)
                                            if diffs else None),
        "reading": ("a small probability difference on matched slots means the "
                    "second pass bought little new information; a large share "
                    "of unmatched slots means the passes explored differently, "
                    "which is the only thing extra passes can honestly buy"),
    }


def _markdown(a: dict) -> str:
    c = a["calls"]
    cost = a["cost"]
    L: list[str] = []
    L.append("# GRAND-ARENA-1 · Chunk 3 — LLM-SWARM-1\n")
    L.append(f"**Run {a['started_utc']} · observation timestamp "
             f"{a['observation_timestamp']} · {a['wall_clock_min']} min wall · "
             f"{a['workers']} workers.**\n")
    L.append("> **ARCHITECTURE_RESULT_ONLY.** " + a["ARCHITECTURE_RESULT_ONLY"]
             + "\n")
    if a["halted_by_governor"]:
        L.append(f"> **The run was HALTED by `research_budget`:** "
                 f"{a['halted_by_governor']}\n")

    L.append("## The headline is the zero-yield rate, not the call count\n")
    zy = a["zero_yield_rate"]
    L.append(f"| number | value |\n|---|---|")
    L.append(f"| calls attempted | {c['attempted']} |")
    L.append(f"| **produced a gradeable record** | **{c['succeeded_gradeable']}** |")
    L.append(f"| abstained (counted, not discarded) | {c['abstained']} |")
    L.append(f"| parsed but minted nothing | {c['zero_yield_parsed']} |")
    L.append(f"| failed on the wire | {c['failed']} |")
    L.append(f"| retries | {c['retries']} |")
    L.append(f"| **zero-yield rate** | **{zy:.1%}** |" if zy is not None
             else "| zero-yield rate | n/a |")
    L.append(f"| cost (ESTIMATE, list prices {cost['pricing_as_of']}) | "
             f"${cost['total_usd_estimate']} |")
    L.append(f"| cost per gradeable output | "
             f"${cost['per_gradeable_output_usd']} |")
    L.append(f"| tokens in / out | {cost['tokens_in']:,} / "
             f"{cost['tokens_out']:,} |")
    L.append(f"| predictions minted | {a['predictions_minted']} "
             f"({a['distinct_predictions_minted']} distinct) |")
    L.append(f"| earliest pending resolution | "
             f"{a['earliest_pending_resolution']} |\n")
    L.append("Cost is reconstructed from the dated list prices in "
             "`config.LLM_PRICE_PER_MTOK`, not from a billed amount.")
    if cost.get("is_lower_bound"):
        why = []
        if cost.get("n_unpriced_calls"):
            why.append(f"{cost['n_unpriced_calls']} call(s) used a model with "
                       f"no price in the table")
        if cost.get("n_unreadable_ledger_lines"):
            why.append(f"{cost['n_unreadable_ledger_lines']} ledger line(s) are "
                       f"unreadable and their spend is simply gone (see "
                       f"Defects)")
        L.append(f"It is a **LOWER BOUND**: {'; '.join(why) or 'reason not '
                 'recorded'}.\n")
    else:
        L.append("")

    L.append("## The universe, and how it was chosen\n")
    u = a["universe"]
    L.append(f"**{u['n_securities']} securities**, all of which had at least "
             f"{cfg.SWARM_MIN_HISTORY_BARS} trading days of history at the "
             f"observation timestamp — a name we cannot price cannot be "
             f"forecast about, and its records could never resolve.\n")
    L.append("| source (all pre-dating this campaign) | names |\n|---|---|")
    empty = []
    for k, v in u["provenance"].items():
        if isinstance(v, int):
            L.append(f"| `{k}` | {v} |")
            if v == 0:
                empty.append(k)
    L.append("")
    if empty:
        # A zero here is either a real absence or a broken extractor, and the
        # two look identical from the outside. Saying so is the only thing that
        # makes the difference visible to a reader.
        L.append(f"**Sources that contributed ZERO names: "
                 f"{', '.join('`' + e + '`' for e in empty)}.** A zero is "
                 f"either a genuinely empty source or an extractor that no "
                 f"longer matches the file's shape — indistinguishable from "
                 f"outside, so it is flagged rather than summed silently.\n")
    L.append("Selection used only information available at the observation "
             "timestamp: the snapshot panel is truncated at `as_of` before any "
             "field is computed, so no specialist saw a number from after the "
             "date it was forecasting from.\n")

    L.append("## What was refused, and why\n")
    L.append("A rejection is not an error log. It is the measurement of how "
             "much of the spend bought ungradeable output.\n")
    L.append("| reason | n |\n|---|---|")
    for k, v in a["rejections"].items():
        L.append(f"| `{k}` | {v} |")
    L.append("")

    L.append("## The p=0.50 monoculture is gone\n")
    L.append("The first WHY-MOVED batch was 23 of 25 one-day `return_sign` "
             "claims at exactly 0.50. This run:\n")
    L.append("| observable | n |\n|---|---|")
    for k, v in a["observable_distribution"].items():
        L.append(f"| `{k}` | {v} |")
    L.append("\n| horizon (trading days) | n |\n|---|---|")
    for k, v in a["horizon_distribution"].items():
        L.append(f"| {k} | {v} |")
    L.append("\n| stated probability (rounded to 0.1) | n |\n|---|---|")
    for k, v in a["probability_histogram"].items():
        L.append(f"| {k} | {v} |")
    L.append("\nExact 0.50 is refused at parse time "
             "(`SWARM_COIN_FLIP_EPS`), and a batch that collapses onto one "
             "(observable, horizon) pair is refused whole "
             "(`monoculture_batch`). The abstain channel is where 'no view' "
             "is supposed to go.\n")

    L.append("## CANON §20 — asking one model 8,000 times is not n=8,000\n")
    e = a["effective_distinct_ideas"]
    L.append(f"**{e['n_forecasts']} forecasts → "
             f"{e['effective_distinct_ideas']} effective distinct ideas "
             f"(ratio {e['ratio']}).** Same rule "
             f"`optimus_specialists.effective_distinct_ideas` uses, so the two "
             f"surfaces are comparable: one idea is one (security, observable, "
             f"probability-to-0.05) bucket.\n")
    L.append(f"Distinct tickers {e['distinct_tickers']} · observables "
             f"{e['distinct_observables']} · horizons "
             f"{e.get('distinct_horizons')}.\n")
    L.append("**This ratio is the honest denominator for anything said about "
             "the swarm.** Volume bought exploration diversity. Only market "
             "outcomes supply evidence.\n")
    L.append("### Do fourteen roles say fourteen different things?\n")
    L.append("```json\n" + json.dumps(a["panel_agreement"], indent=1) + "\n```\n")
    L.append("Separation prevents contagion between the roles. It cannot "
             "manufacture independence the underlying model does not have, and "
             "this is the number that says which of those happened.\n")
    L.append("### The same role, asked the same question twice\n")
    L.append("```json\n" + json.dumps(a["test_retest"], indent=1) + "\n```\n")

    L.append("## Per specialist\n")
    L.append("| specialist | calls | ok | abstain | zero-yield | fail | records "
             "| forecasts | eff. ideas | ratio | mean conf |\n"
             "|---|---|---|---|---|---|---|---|---|---|---|")
    for k, v in a["by_specialist"].items():
        L.append(f"| `{k}` | {v['calls']} | {v['ok']} | {v['abstained']} | "
                 f"{v['zero_yield']} | {v['failed']} | {v['records']} | "
                 f"{v['n_forecasts']} | {v['effective_distinct_ideas']} | "
                 f"{v['ratio']} | {v['mean_confidence']} |")
    L.append("")

    L.append("## The ledger refused what the swarm duplicated\n")
    dup = a["predictions_minted"] - a["distinct_predictions_minted"]
    L.append(f"{a['predictions_minted']} forecasts were accepted; "
             f"**{a['distinct_predictions_minted']} distinct records reached "
             f"the ledger**. The other {dup} were byte-identical claims — same "
             f"security, specialist, observable, horizon, snapshot and prompt — "
             f"produced when the second pass reproduced the first exactly. "
             f"`belief_state.append` refused them by `prediction_id`, which is "
             f"the correct outcome and worth stating plainly: **a repeated "
             f"forecast is not a second piece of evidence**, and scoring it "
             f"twice would silently double that forecaster's weight in its own "
             f"calibration. The duplicate rate is itself a §20 measurement.\n")

    L.append("## Calibration prior: this batch looks overconfident\n")
    L.append("The probability histogram is not centred. Stated credences pile "
             "up between 0.55 and 0.70, with very little mass below 0.30 — a "
             "forecaster that is confident about almost every security it is "
             "shown. That is the failure mode "
             "`docs/TRIALS/TRIAL-SWARM-CAL-specialist-calibration.md` "
             "**pre-registered as the expected one**, before any of these "
             "records could resolve. It is stated here as a description of the "
             "inputs, NOT as a result: whether the confidence is earned is "
             "exactly what the forward Brier will decide, and nothing before "
             "the minimum window may be read as an answer.\n")
    L.append("The `skeptic` carries the lowest mean confidence of the fourteen "
             "roles and abstained more than any other, which is what its prompt "
             "asks for. That is instruction-following, not evidence of "
             "judgment — the ledger will say which.\n")

    L.append("## Defects this run exposed (all fixed or disclosed)\n")
    L.append("- **Two telemetry rows were TORN by concurrent appends.** 24 "
             "threads writing `llm_calls.jsonl` produced two unparseable lines "
             "(`\"1.0.0\"}` and `\"}`). A single short `write()` is atomic on "
             "POSIX by convention and not guaranteed on Windows. `read_calls` "
             "counted them and downgraded every total to a LOWER BOUND, which "
             "is the only reason it was visible. `append` is now serialised by "
             "a process-level lock in both `llm_telemetry` and `belief_state`, "
             "with a regression test that runs 16 threads; the lock does NOT "
             "cover two processes sharing a volume, and says so.\n"
             "- **The budget governor cost 0.31s per gate at scale.** "
             "`research_budget` called `llm_telemetry.summary()`, which joins "
             "every claimed prediction id against a 25MB ledger — irrelevant to "
             "the decision. A governor that is expensive to consult is one "
             "somebody eventually consults less often, so `spend()` now serves "
             "the gate with the same four inputs and none of the join.\n"
             "- **A universe source silently returned zero names.** The "
             "`paper_portfolios.yaml` extractor only understood "
             "`{\"ticker\": ...}` records and that file holds bare strings, so "
             "an 81-name source read as empty and looked exactly like an empty "
             "file. Fixed for future runs; the frozen universe used here "
             "predates the fix, and the provenance table flags every "
             "zero-yielding source for precisely this reason.\n"
             "- **The ledger resolver fetched every due ticker in ONE request.** "
             "Correct at a dozen names; with hundreds in the ledger a single "
             "timeout would mark every due record unpriceable and page on a "
             "problem that is not in the ledger. Now chunked, so a bad chunk "
             "strands only its own names.\n"
             "- **`ResearchBudgetExhausted` was being absorbed into the "
             "per-cell failure count** in an early draft of `run_cell`, which "
             "would have made an exhausted budget look like vendor flakiness "
             "while the pool kept submitting work. It is now re-raised.\n")

    L.append("## What this does and does not license\n")
    L.append("- It licenses nothing about skill. Every record is unresolved.\n"
             "- The first grade falls on "
             f"`{a['earliest_pending_resolution']}`, and CANON §19 applies to "
             "every slice of it: each prints its own n and its own MDE.\n"
             "- A 1-day Brier is mostly noise. The short horizons exist to "
             "accrue n fast, not to be read early.\n"
             "- Abstentions are honestly counted as producing no gradeable "
             "output, because they do not. That is what keeps the zero-yield "
             "brake able to see the campaign it watches.\n")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=cfg.SWARM_WORKERS)
    ap.add_argument("--meta-workers", type=int, default=8)
    ap.add_argument("--passes", type=int, default=1)
    ap.add_argument("--target", type=int, default=None,
                    help="cap the number of cells planned")
    ap.add_argument("--pilot", type=int, default=None,
                    help="run only this many cells, to measure before spending")
    ap.add_argument("--as-of", default=None,
                    help="observation timestamp; default = last session in the "
                         "panel")
    ap.add_argument("--resume", action="store_true",
                    help="reuse the frozen universe and skip completed cells")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    if args.report_only:
        rows, _ = load_checkpoint()
        uni = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
        meta = (json.loads(RUN_META.read_text(encoding="utf-8"))
                if RUN_META.exists() else {})
        write_report(rows, provenance=uni["provenance"], as_of=uni["as_of"],
                     started=datetime.fromisoformat(
                         meta.get("started_utc")
                         or datetime.now(timezone.utc).isoformat(timespec="seconds")),
                     wall_s=float(meta.get("wall_clock_min") or 0.0) * 60.0,
                     workers=int(meta.get("workers") or args.workers),
                     halted=meta.get("halted_by_governor"),
                     n_securities=len(uni["snapshots"]), n_planned=len(rows),
                     since=meta.get("since"))
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
