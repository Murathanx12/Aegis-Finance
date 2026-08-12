"""LLM-LEAKAGE-PROBE-1 — GRAND-ARENA-1 chunk 3B.

    python scripts/run_leakage_probe_1.py --build          # freeze the item set
    python scripts/run_leakage_probe_1.py --wave canary
    python scripts/run_leakage_probe_1.py --wave core
    python scripts/run_leakage_probe_1.py --wave deep,panel
    python scripts/run_leakage_probe_1.py --wave temps,framings,debate,reasoner
    python scripts/run_leakage_probe_1.py --resolve        # grade + report
    python scripts/run_leakage_probe_1.py --report-only

WHY NOT JUST RUN THE SWARM AGAIN
--------------------------------
LLM-SWARM-1 measured its own ceiling: 22,607 forecasts collapsed to 6,772
effective distinct ideas, fourteen roles disagreed by a mean probability spread
of 0.059, and every one of its 20,073 records is unresolved until 2026-08-16.
More of the same buys more correlated exploration and no more evidence.

This buys two things that campaign could not: records that resolve the moment
they are made, and a measurement of whether the model KNOWS or merely REMEMBERS.

THE LEDGER RULE
---------------
Historical records go to `leakage_probe.LEAK_PREDICTIONS`, never to
`predictions.jsonl`. The forward ledger's entire value is that it is
forward-only; mixing backfilled historical records into it would destroy the
one clean instrument the programme has.

ARCHITECTURE_RESULT_ONLY (A6). These are HISTORICAL resolutions. They may not
set production specialist weights (A5) and they certify nothing.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import random
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Windows consoles default to cp1252 and a single arrow in a progress line will
# take the whole run down at the last print. Losing an eight-hour campaign to an
# encoding error in a status message is not a risk worth carrying.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                         # pragma: no cover
    pass

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:                                       # pragma: no cover
    print("python-dotenv missing — relying on the ambient environment")

from backend import config as cfg                          # noqa: E402
from backend.services import belief_state as bs            # noqa: E402
from backend.services import leakage_probe as lp           # noqa: E402
from backend.services import llm_swarm as sw               # noqa: E402
from backend.services import llm_telemetry as tel          # noqa: E402
from backend.services import research_budget               # noqa: E402

RUN_DIR = ROOT / "backend" / "data" / "leakage_probe"
ITEMS_FILE = RUN_DIR / "items.json"
CHECKPOINT = RUN_DIR / "cells.jsonl"
CANARY_FILE = RUN_DIR / "canaries.jsonl"
META_FILE = RUN_DIR / "run_meta.json"
PANEL_FILE = RUN_DIR / "panel.parquet"
REPORT = ROOT / "docs" / "GRAND_ARENA_LEAKAGE_PROBE.md"
ARTIFACT = ROOT / "docs" / "grand_arena_leakage_probe.json"

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("leak")

SEED = 20260812
BENCH = cfg.SWARM_BENCHMARK

#: The REAL model ids, measured against the live account on 2026-08-12.
#: `deepseek-chat` and `deepseek-reasoner` are both aliases for v4-flash, so
#: nothing here ever requests them: the requested name goes on the record beside
#: the SERVED name, and only the served one is evidence.
MODEL_FLASH = "deepseek-v4-flash"
MODEL_PRO = "deepseek-v4-pro"

#: The two eras, and the deliberate GAP between them.
#: `pre_cutoff` is history the foundation model has plausibly read. `recent` is
#: after any plausible training cutoff for `deepseek-chat`. 2024 is excluded on
#: purpose: it is the band where "has the model seen this" is genuinely unknown,
#: and an item whose stratum is uncertain contributes noise to the one
#: comparison this campaign exists to make.
ERA_P = ("2015-01-01", "2023-12-31")
ERA_R = ("2025-03-01", "2026-05-01")

_lock = threading.Lock()


# ══ items ═══════════════════════════════════════════════════════════════════

def _universe() -> list[str]:
    """Names the repo already had a reason to look at, before this campaign."""
    s = cfg.config["stock_universe"]["sector_stocks"]
    return sorted({t.upper() for v in s.values() for t in v})


def _sector_map(tickers: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for sec, names in cfg.config["stock_universe"]["sector_stocks"].items():
        for t in names:
            out.setdefault(t.upper(), sec)
    for t, sec in cfg.WHY_MOVED_TICKER_SECTOR.items():
        out.setdefault(t.upper(), sec)
    return {t: out.get(t, "Unknown") for t in tickers}


def download_panel(tickers: list[str], start: str, end: str):
    import pandas as pd
    import yfinance as yf
    frames = []
    tickers = sorted(set(tickers))
    for i in range(0, len(tickers), 60):
        chunk = tickers[i:i + 60]
        df = yf.download(chunk, start=start, end=end, auto_adjust=True,
                         progress=False, timeout=90)["Close"]
        if isinstance(df, pd.Series):
            df = df.to_frame(name=chunk[0])
        frames.append(df)
        print(f"  prices {min(i + 60, len(tickers))}/{len(tickers)}", flush=True)
    out = pd.concat(frames, axis=1).sort_index()
    return out.loc[:, ~out.columns.duplicated()]


def _pick_dates(index, lo: str, hi: str, n: int, rng: random.Random) -> list[str]:
    """n observation dates inside a window, spread out and snapped to sessions.

    Spread rather than random: consecutive dates share almost the same 60-day
    forward window, and a design whose dates cluster has far less independent
    information than its item count suggests.
    """
    import pandas as pd
    sub = [d for d in index if pd.Timestamp(lo) <= d <= pd.Timestamp(hi)]
    if len(sub) <= n:
        return [str(d.date()) for d in sub]
    step = len(sub) / n
    picks = []
    for i in range(n):
        j = int(i * step + rng.random() * step * 0.6)
        picks.append(sub[min(j, len(sub) - 1)])
    return sorted({str(d.date()) for d in picks})


def build_items(args) -> dict:
    """Freeze the (security, date) grid, its PIT snapshots and its slates."""
    import pandas as pd

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    uni = _universe()
    print(f"universe candidates: {len(uni)}", flush=True)

    if PANEL_FILE.exists() and not args.refetch:
        panel = pd.read_parquet(PANEL_FILE)
        print(f"panel from cache: {panel.shape}", flush=True)
    else:
        panel = download_panel(uni + [BENCH], "2013-06-01", "2026-08-12")
        panel.to_parquet(PANEL_FILE)
        print(f"panel: {panel.shape}", flush=True)

    # A name usable across BOTH eras or the strata differ in composition as well
    # as in era, and the difference-in-differences would then be a comparison of
    # two different universes wearing one label.
    ok = []
    for t in uni:
        if t not in panel.columns:
            continue
        s = pd.to_numeric(panel[t], errors="coerce").dropna()
        if len(s) < 2800:
            continue
        if str(s.index[0].date()) > "2014-01-15" or str(s.index[-1].date()) < "2026-08-01":
            continue
        ok.append(t)
    tickers = sorted(rng.sample(ok, k=min(args.tickers, len(ok))))
    print(f"tickers with full 2014-2026 history: {len(ok)} → using {len(tickers)}",
          flush=True)

    dates_p = _pick_dates(panel.index, *ERA_P, args.dates_p, rng)
    dates_r = _pick_dates(panel.index, *ERA_R, args.dates_r, rng)
    print(f"dates: {len(dates_p)} pre_cutoff, {len(dates_r)} recent", flush=True)

    secmap = _sector_map(tickers)
    names = _company_names(tickers)

    items: list[dict] = []
    dropped = Counter()
    for era, dates in (("pre_cutoff", dates_p), ("recent", dates_r)):
        for d in dates:
            for t in tickers:
                snap = sw.snapshot_from_panel(
                    t, panel, as_of=d, benchmark=BENCH,
                    meta={"sector": secmap.get(t, "Unknown")})
                if snap is None or snap["n_bars_available"] < 252:
                    dropped["insufficient_history"] += 1
                    continue
                # Every slot must be resolvable or the pair is half a pair.
                fwd = pd.to_numeric(panel[t], errors="coerce").dropna().loc[d:]
                fb = pd.to_numeric(panel[BENCH], errors="coerce").dropna().loc[d:]
                if len(fwd) < 61 or len(fb) < 61:
                    dropped["outcome_window_incomplete"] += 1
                    continue
                slate = lp.slate_for(snap)
                if slate is None:
                    dropped["no_priceable_threshold"] += 1
                    continue
                # Non-PIT vendor fields are NOT fetched for historical items:
                # today's market cap is a fact from the future, and an industry
                # label that has drifted would re-cut a past snapshot. What
                # remains is computed from closes at or before `as_of`.
                items.append({
                    "item_id": f"{t}|{d}", "ticker": t, "as_of": d, "era": era,
                    "made_at": f"{d}T00:00:00+00:00",
                    "company_name": names.get(t, ""),
                    "last_close": snap["last_close"],
                    "snapshot": snap, "slate": slate,
                })
    print(f"items: {len(items)}  dropped: {dict(dropped)}", flush=True)

    payload = {
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": SEED, "benchmark": BENCH,
        "era_windows": {"pre_cutoff": ERA_P, "recent": ERA_R},
        "n_tickers": len(tickers), "tickers": tickers,
        "n_dates_pre_cutoff": len(dates_p), "n_dates_recent": len(dates_r),
        "dates_pre_cutoff": dates_p, "dates_recent": dates_r,
        "universe_pool": len(ok), "dropped": dict(dropped),
        "n_items": len(items), "items": items,
        "slate": [s.__dict__ for s in lp.SLATE],
    }
    ITEMS_FILE.write_text(json.dumps(payload, default=str), encoding="utf-8")
    print(f"wrote {ITEMS_FILE}", flush=True)
    return payload


def _company_names(tickers: list[str]) -> dict[str, str]:
    """Company names, for the IDENTIFIED arm and for the masking check.

    Fetched once and cached. A name we cannot fetch degrades to empty: the
    identified prompt then carries the ticker alone, and the masking check
    scans for one fewer string — which is stated in the report rather than
    silently reducing the check's coverage.
    """
    cache = RUN_DIR / "company_names.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    import yfinance as yf
    out: dict[str, str] = {}
    lk = threading.Lock()

    def one(t: str) -> None:
        try:
            i = yf.Ticker(t).info or {}
            n = i.get("longName") or i.get("shortName") or ""
        except Exception:                                  # noqa: BLE001
            n = ""
        with lk:
            out[t] = str(n)

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(one, tickers))
    cache.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


# ══ the plan ════════════════════════════════════════════════════════════════

CORE_ROLES = ("company_fundamental", "execution_momentum")
PANEL_ROLES = ("options_volatility", "macro_rates", "behavioral_narrative",
               "skeptic")


def _subset(items: list[dict], n: int, rng: random.Random) -> list[dict]:
    """A seeded, era-balanced subsample. Balanced because a subset that drifted
    toward one era would make its own stratum comparison uninterpretable."""
    by = defaultdict(list)
    for it in items:
        by[it["era"]].append(it)
    out = []
    for era, rows in sorted(by.items()):
        k = min(n // 2, len(rows))
        out.extend(rng.sample(sorted(rows, key=lambda r: r["item_id"]), k=k))
    return sorted(out, key=lambda r: r["item_id"])


def plan_wave(wave: str, items: list[dict], args) -> list[dict]:
    """Cells for one wave. Every cell carries everything needed to run it."""
    rng = random.Random(SEED + hash(wave) % 1000)
    cells: list[dict] = []

    def add(cond: str, arm: str, role: str, it: dict, *, rep: int = 0,
            model: str = MODEL_FLASH, temp: float = cfg.SWARM_TEMPERATURE,
            framing: str | None = None, deep: bool = False,
            thinking: bool = False, debate_base: str | None = None) -> None:
        cells.append({
            "cell_id": f"{cond}|{arm}|{role}|{it['item_id']}|{rep}",
            "condition": cond, "arm": arm, "role": role, "rep": rep,
            "item_id": it["item_id"], "model": model, "temperature": temp,
            "framing": framing, "deep": deep, "thinking": thinking,
            "debate_base": debate_base})

    if wave == "core":
        for it in items:
            for role in CORE_ROLES:
                add("core", "identified", role, it)
                add("core", "masked", role, it)
    elif wave == "panel":
        for it in _subset(items, args.panel_items, rng):
            for role in PANEL_ROLES:
                add("panel", "identified", role, it)
                add("panel", "masked", role, it)
    elif wave == "deep":
        for it in _subset(items, args.deep_items, rng):
            for role in CORE_ROLES:
                add("deep", "deep_masked", role, it, deep=True)
    elif wave == "temps":
        for it in _subset(items, args.div_items, rng):
            for t in (0.0, 0.4, 1.0):
                for rep in range(2):
                    add(f"temp_{t}", "identified", CORE_ROLES[0], it,
                        rep=rep, temp=t)
    elif wave == "framings":
        for it in _subset(items, args.div_items, rng):
            for f in ("framing_bull", "framing_bear", "framing_baserate"):
                add(f, "identified", CORE_ROLES[0], it, framing=f)
    elif wave == "debate":
        for it in _subset(items, args.div_items, rng):
            add("debate_first", "identified", CORE_ROLES[0], it)
    elif wave == "debate2":
        # The refuter runs only where the first speaker produced something to
        # refute. Labelled NON-INDEPENDENT everywhere and never pooled with the
        # independent arms — it is testing a different thing.
        done = {r["cell_id"]: r for r in _load_cells()
                if r["condition"] == "debate_first" and r["status"] == "ok"}
        for cid, row in sorted(done.items()):
            it = _ITEM_BY_ID.get(row["ticker"] + "|" + row["as_of"])
            if it is not None:
                add("debate_refute", "identified", CORE_ROLES[1], it,
                    debate_base=cid)
    elif wave == "models":
        # THE CORRECTED MODEL ARM. The brief's original "deepseek-chat vs
        # deepseek-reasoner" is VOID BY CONSTRUCTION: both names are server-side
        # aliases for `deepseek-v4-flash`, so that arm would have compared one
        # model with itself and any null it produced would have been
        # manufactured by a config error. It was never run; this replaces it.
        # Both legs are requested by their REAL id, both with thinking ON (the
        # capability question), on the SAME items, so the difference is paired.
        for it in _subset(items, args.model_items, rng):
            for m in (MODEL_FLASH, MODEL_PRO):
                add(f"model_{m}", "identified", CORE_ROLES[0], it,
                    model=m, thinking=True)
                add(f"model_{m}", "masked", CORE_ROLES[0], it,
                    model=m, thinking=True)
    else:
        raise SystemExit(f"unknown wave {wave!r}")
    return cells


# ══ checkpoint ══════════════════════════════════════════════════════════════

_ITEM_BY_ID: dict[str, dict] = {}


def _load_cells() -> list[dict]:
    if not CHECKPOINT.exists():
        return []
    rows = []
    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            log.warning("checkpoint: unreadable line skipped — its cell will "
                        "re-run, which costs a call and loses nothing")
    return rows


def _load_canaries() -> list[dict]:
    if not CANARY_FILE.exists():
        return []
    out = []
    for line in CANARY_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


# ══ running ═════════════════════════════════════════════════════════════════

def run_cells(cells: list[dict], items: dict[str, dict], args,
              since: str) -> dict:
    done = {r["cell_id"] for r in _load_cells()}
    todo = [c for c in cells if c["cell_id"] not in done]
    print(f"planned {len(cells)}, already done {len(cells) - len(todo)}, "
          f"to run {len(todo)}", flush=True)
    if not todo:
        return {"ran": 0}

    base_by_cell = {r["cell_id"]: r for r in _load_cells()}
    counts: Counter = Counter()
    pending: list[Any] = []
    halted: str | None = None
    ck = CHECKPOINT.open("a", encoding="utf-8")
    t0 = time.perf_counter()

    def flush(force: bool = False) -> None:
        nonlocal pending
        if pending and (force or len(pending) >= 3000):
            bs.append(pending, path=lp.LEAK_PREDICTIONS)
            pending = []

    def work(c: dict) -> lp.CellResult:
        it = items[c["item_id"]]
        snap = (it["snapshot"] if c["arm"] == "identified"
                else lp.mask_snapshot(it["snapshot"], deep=c["deep"]))
        opp = None
        if c.get("debate_base"):
            b = base_by_cell.get(c["debate_base"])
            if b:
                opp = {"their_confidence": b.get("confidence"),
                       "their_forecasts": [
                           {"key": f["key"], "probability": f["probability"]}
                           for f in b.get("forecasts", [])]}
        return lp.run_cell(
            cell_id=c["cell_id"], condition=c["condition"], arm=c["arm"],
            role=c["role"],
            item={**{k: v for k, v in it.items()
                     if k in ("ticker", "as_of", "era", "made_at",
                              "company_name", "last_close")},
                  "universe": args.scan_tickers},
            snapshot=snap, slate=it["slate"], model=c["model"],
            temperature=c["temperature"], thinking=bool(c.get("thinking")),
            framing=c["framing"], opponent=opp, since=since)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, c): c for c in todo}
        try:
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    res = fut.result()
                except research_budget.ResearchBudgetExhausted as exc:
                    halted = str(exc)
                    break
                except Exception as exc:                  # noqa: BLE001
                    counts["crashed"] += 1
                    log.warning("cell crashed: %s: %s", type(exc).__name__, exc)
                    continue
                with _lock:
                    counts[res.status] += 1
                    for r in (res.parsed.rejections if res.parsed else []):
                        counts[f"reject:{r['reason']}"] += 1
                    pending.extend(res.records)
                    row = res.as_row()
                    base_by_cell[row["cell_id"]] = row
                    ck.write(json.dumps(row, default=str) + "\n")
                    if i % 50 == 0:
                        ck.flush()
                        flush()
                    if i % 200 == 0:
                        b = research_budget.check(lp.CAMPAIGN, since=since)
                        zy = 1 - counts["ok"] / max(i, 1)
                        rate = i / max(time.perf_counter() - t0, 1e-9) * 60
                        print(f"[{i}/{len(todo)}] ok={counts['ok']} "
                              f"abst={counts['abstained']} "
                              f"zero={counts['zero_yield']} "
                              f"maskrefused={counts['refused_mask']} "
                              f"fail={counts['failed']} | ${b.cost_usd} "
                              f"wave-zero-yield={zy:.1%} {rate:.0f}/min",
                              flush=True)
        finally:
            if halted:
                for f in futs:
                    f.cancel()
            with _lock:
                flush(force=True)
                ck.flush()
                ck.close()
    if halted:
        print(f"\nHALTED BY THE GOVERNOR: {halted}")
    print(f"\nwave done in {(time.perf_counter()-t0)/60:.1f} min: {dict(counts)}")
    return {"ran": len(todo), "counts": dict(counts), "halted": halted}


def run_canaries(items: dict[str, dict], args, since: str) -> dict:
    """Identification canary on masked items, recall canary on identified ones.

    Run BEFORE the forecast waves on purpose. If the mask is porous, the whole
    core experiment is measuring something else and the money should not be
    spent on it.
    """
    rng = random.Random(SEED + 5)
    pool = _subset(list(items.values()), args.canary_items, rng)
    done = {(r["kind"], r["item_id"]) for r in _load_canaries()}
    jobs = []
    for it in pool:
        if ("identify", it["item_id"]) not in done:
            jobs.append(("identify", it))
        if ("recall", it["item_id"]) not in done:
            jobs.append(("recall", it))
    print(f"canaries to run: {len(jobs)}", flush=True)
    if not jobs:
        return {"ran": 0}
    fh = CANARY_FILE.open("a", encoding="utf-8")
    counts: Counter = Counter()
    halted = None

    def one(job) -> dict:
        kind, it = job
        if kind == "identify":
            masked = lp.mask_snapshot(it["snapshot"])
            system, user = lp.identification_canary(masked)
            viol = lp.masking_violations(
                user, ticker=it["ticker"], company_name=it["company_name"],
                as_of=it["as_of"], last_close=it["last_close"],
                other_tickers=args.scan_tickers)
            if viol:
                return {"kind": kind, "item_id": it["item_id"],
                        "status": "refused_mask", "violations": viol[:5]}
        else:
            system, user = lp.recall_canary(it["ticker"], it["as_of"],
                                            it["company_name"])
        rep = lp.call_llm(system, user, model=MODEL_FLASH, max_tokens=260,
                          temperature=0.0, thinking=False, since=since)
        try:
            parsed = lp.extract_json(rep.text)
        except Exception:                                  # noqa: BLE001
            parsed = None
        try:
            tel.record_call(provider="deepseek", model=MODEL_FLASH,
                            model_version=rep.model_version,
                            purpose=f"leakage_probe_canary_{kind}",
                            agent=kind, prompt=system + user,
                            context={"item": it["item_id"]},
                            tokens_in=rep.tokens_in, tokens_out=rep.tokens_out,
                            cached_tokens=rep.cached_tokens,
                            latency_ms=rep.latency_ms, retries=rep.retries,
                            schema_valid=parsed is not None,
                            meta={"item_id": it["item_id"], "kind": kind,
                                  "era": it["era"],
                                  "served_model": rep.served_model,
                                  "model_unverified": rep.model_unverified,
                                  "reasoning_tokens": rep.reasoning_tokens,
                                  "module": lp.MODULE_VERSION})
        except Exception:                                  # noqa: BLE001
            pass
        return {"kind": kind, "item_id": it["item_id"], "ticker": it["ticker"],
                "as_of": it["as_of"], "era": it["era"],
                "status": "ok" if parsed is not None else "unparseable",
                "served_model": rep.served_model,
                "parsed": parsed, "raw": (rep.text or "")[:400]}

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(one, j): j for j in jobs}
        try:
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    r = fut.result()
                except research_budget.ResearchBudgetExhausted as exc:
                    halted = str(exc)
                    break
                except Exception as exc:                  # noqa: BLE001
                    counts["failed"] += 1
                    log.warning("canary failed: %s", exc)
                    continue
                with _lock:
                    counts[f"{r['kind']}:{r['status']}"] += 1
                    fh.write(json.dumps(r, default=str) + "\n")
                    if i % 100 == 0:
                        fh.flush()
                        print(f"[canary {i}/{len(jobs)}] {dict(counts)}",
                              flush=True)
        finally:
            if halted:
                for f in futs:
                    f.cancel()
            fh.flush()
            fh.close()
    print(f"canaries: {dict(counts)}  halted={halted}")
    return {"ran": len(jobs), "counts": dict(counts), "halted": halted}


# ══ resolution and analysis ═════════════════════════════════════════════════

def resolve(args) -> dict:
    import pandas as pd
    panel = pd.read_parquet(PANEL_FILE)
    out = bs.resolve_all(panel, path=lp.LEAK_PREDICTIONS, today=date.today())
    print(json.dumps(out, indent=1))
    return out


def _baselines(items: dict[str, dict], panel) -> dict[str, dict[str, float]]:
    """A PIT baseline bank: the trailing frequency of each slot's outcome.

    AMNESIA-1's own retirement note is the reason this exists. That trial could
    not tell "the LLM has no skill" from "this task has no signal", because
    nothing cheap was measured beside it. Here every slot carries the
    unconditional frequency of its own outcome over the three years BEFORE the
    observation date, computed across the same universe from closes at or
    before that date. A forecaster that cannot beat this has not earned the
    inference budget.
    """
    import numpy as np
    import pandas as pd

    cols = sorted({it["ticker"] for it in items.values()})
    px = panel[cols].astype(float)
    idx = px.index
    arr = px.to_numpy()
    pos = {str(d.date()): i for i, d in enumerate(idx)}

    def fwd_ret(h: int) -> np.ndarray:
        out = np.full_like(arr, np.nan)
        out[:-h] = arr[h:] / arr[:-h] - 1.0
        return out

    def fwd_dd(h: int) -> np.ndarray:
        out = np.full_like(arr, np.nan)
        for i in range(arr.shape[0] - h):
            w = arr[i:i + h + 1]
            cm = np.maximum.accumulate(w, axis=0)
            out[i] = (w / cm - 1.0).min(axis=0)
        return out

    b = panel[cfg.SWARM_BENCHMARK].astype(float).to_numpy()

    def fwd_bench(h: int) -> np.ndarray:
        o = np.full(len(b), np.nan)
        o[:-h] = b[h:] / b[:-h] - 1.0
        return o

    cache = {"r5": fwd_ret(5), "r20": fwd_ret(20), "dd60": fwd_dd(60),
             "b20": fwd_bench(20)}
    win = 756

    out: dict[str, dict[str, float]] = {}
    for it in items.values():
        i = pos.get(it["as_of"])
        if i is None:
            continue
        lo = max(0, i - win)
        row: dict[str, float] = {}
        r5 = cache["r5"][lo:i]
        r20 = cache["r20"][lo:i]
        dd60 = cache["dd60"][lo:i]
        b20 = cache["b20"][lo:i][:, None]
        thr = {s["key"]: s["threshold"] for s in it["slate"]}
        with np.errstate(invalid="ignore"):
            row["q1"] = float(np.nanmean(r5 > 0))
            row["q2"] = float(np.nanmean(r20 > 0))
            row["q3"] = float(np.nanmean(r20 > b20))
            row["q4"] = float(np.nanmean(np.abs(r20) > thr["q4"]))
            row["q5"] = float(np.nanmean(np.abs(dd60) > thr["q5"]))
        out[it["item_id"]] = {k: (0.5 if not np.isfinite(v) else
                                  min(max(v, 0.02), 0.98))
                              for k, v in row.items()}
    return out


def _thinking_depth(cells: list[dict]) -> dict:
    """Reasoning tokens per served model x thinking state, beside zero yield.

    Thinking depth and answer length are different quantities, and the vendor
    charges for both. Reported together with the zero-yield share because the
    measured failure mode of a thinking-on call is not a worse answer — it is
    NO answer: the completion budget is spent entirely on reasoning and the
    content comes back empty with finish_reason="length".
    """
    out: dict[str, dict] = {}
    for served in (MODEL_FLASH, MODEL_PRO):
        for think in (True, False):
            g = [c for c in cells
                 if str(c.get("served_model")) == served
                 and bool(c.get("thinking")) is think
                 and c.get("status") in ("ok", "zero_yield", "abstained")]
            if not g:
                continue
            n = len(g)
            out[f"{served} | thinking={'on' if think else 'off'}"] = {
                "n_calls": n,
                "mean_reasoning_tokens": round(
                    sum(int(c.get("reasoning_tokens") or 0) for c in g) / n, 1),
                "mean_completion_tokens": round(
                    sum(int(c.get("tokens_out") or 0) for c in g) / n, 1),
                "mean_prompt_tokens": round(
                    sum(int(c.get("tokens_in") or 0) for c in g) / n, 1),
                "share_zero_yield": round(
                    sum(1 for c in g if c["status"] == "zero_yield") / n, 4),
            }
    return out


def analyse(args) -> dict:
    """Everything the campaign owes, with the paired gap as the headline."""
    import pandas as pd

    payload = json.loads(ITEMS_FILE.read_text(encoding="utf-8"))
    items = {it["item_id"]: it for it in payload["items"]}
    panel = pd.read_parquet(PANEL_FILE)
    cells = _load_cells()
    canaries = _load_canaries()
    ledger = {r["prediction_id"]: r
              for r in bs.read_predictions(lp.LEAK_PREDICTIONS)}

    # ── join every forecast to its outcome ──────────────────────────────────
    recs: list[dict] = []
    for c in cells:
        if c["status"] != "ok":
            continue
        item = items.get(f"{c['ticker']}|{c['as_of']}")
        for pid, f in zip(c["prediction_ids"], c["forecasts"]):
            r = ledger.get(pid)
            if r is None or r.get("outcome") is None:
                continue
            recs.append({
                "cell_id": c["cell_id"], "condition": c["condition"],
                "arm": c["arm"], "role": c["role"], "ticker": c["ticker"],
                "as_of": c["as_of"], "era": c["era"], "key": f["key"],
                "observable": f["observable"], "horizon_days": f["horizon_days"],
                "probability": f["probability"], "threshold": f["threshold"],
                "outcome": int(r["outcome"]), "brier": float(r["brier"]),
                # Requested vs SERVED. Every model claim below keys on the
                # served name; the requested one is kept only so a silent alias
                # is visible as a disagreement between the two columns.
                "model_requested": c.get("model_requested")
                or c.get("model") or cfg.SWARM_MODEL,
                "served_model": c.get("served_model"),
                "thinking": bool(c.get("thinking")),
                "reasoning_tokens": c.get("reasoning_tokens", 0),
                "rep": c["cell_id"].rsplit("|", 1)[-1],
                "realised_return": (r.get("resolution_detail") or {}).get(
                    "realised_return"),
            })
    print(f"resolved forecast rows: {len(recs)}", flush=True)

    base = _baselines(items, panel)

    def with_base(rs: list[dict]) -> list[dict]:
        out = []
        for r in rs:
            p = (base.get(f"{r['ticker']}|{r['as_of']}") or {}).get(r["key"])
            if p is None:
                continue
            q = dict(r)
            q["baseline_probability"] = p
            q["baseline_brier"] = (p - r["outcome"]) ** 2
            out.append(q)
        return out

    recs = with_base(recs)

    # ── the paired identified-vs-masked table ───────────────────────────────
    def pair_up(cond_a: str, arm_a: str, cond_b: str, arm_b: str,
                served: str | None = None) -> list[dict]:
        """Match on (role, ticker, as_of, slot). A slot present in one arm and
        not the other is NOT compared against nothing — it is dropped and
        counted, because a missing slot is usually a refusal and refusals are
        not symmetric between the arms."""
        def key(r: dict) -> tuple:
            return (r["role"], r["ticker"], r["as_of"], r["key"])
        A = {key(r): r for r in recs
             if r["condition"] == cond_a and r["arm"] == arm_a
             and (served is None or r["served_model"] == served)}
        B = {key(r): r for r in recs
             if r["condition"] == cond_b and r["arm"] == arm_b
             and (served is None or r["served_model"] == served)}
        out = []
        for k in sorted(set(A) & set(B)):
            a, b = A[k], B[k]
            out.append({"role": k[0], "ticker": k[1], "as_of": k[2],
                        "key": k[3], "era": a["era"],
                        "observable": a["observable"],
                        "horizon_days": a["horizon_days"],
                        "brier_a": a["brier"], "brier_b": b["brier"],
                        "d": a["brier"] - b["brier"],
                        "p_a": a["probability"], "p_b": b["probability"],
                        "dp": abs(a["probability"] - b["probability"]),
                        "outcome": a["outcome"],
                        "baseline_brier": a["baseline_brier"],
                        "realised_return": a["realised_return"]})
        return out

    pairs_core = pair_up("core", "identified", "core", "masked")
    pairs_panel = pair_up("panel", "identified", "panel", "masked")
    pairs_all = pairs_core + pairs_panel
    pairs_deep = pair_up("core", "identified", "deep", "deep_masked")
    # The leakage gap re-measured on each REAL model, thinking on.
    cf, cp = f"model_{MODEL_FLASH}", f"model_{MODEL_PRO}"
    pairs_flash_leak = pair_up(cf, "identified", cf, "masked")
    pairs_pro_leak = pair_up(cp, "identified", cp, "masked")
    # THE CAPABILITY QUESTION, paired on the same items: v4-flash against
    # v4-pro, not an alias against itself.
    pairs_flash_vs_pro = pair_up(cf, "identified", cp, "identified")
    pairs_flash_vs_pro_masked = pair_up(cf, "masked", cp, "masked")
    # Thinking ON vs OFF on the SAME model — the depth question, separated from
    # the model question, which the alias confusion had welded together.
    pairs_thinking = pair_up(cf, "identified", "core", "identified")

    def stratum(ps, era):
        return [p for p in ps if p["era"] == era]

    def salient(ps):
        # AMNESIA-1 finding 4: the model remembers catastrophes, not returns.
        # A dramatic outcome is the case where memory, if any exists, should
        # show. Defined on the OUTCOME, so it is a reported slice and never a
        # selection rule.
        return [p for p in ps if p.get("realised_return") is not None
                and abs(float(p["realised_return"])) >= 0.20]

    head: dict[str, Any] = {}
    for name, ps in (("core_2_roles", pairs_core),
                     ("core_plus_panel_6_roles", pairs_all),
                     ("deep_mask", pairs_deep),
                     ("v4_flash_thinking_on", pairs_flash_leak),
                     ("v4_pro_thinking_on", pairs_pro_leak)):
        if not ps:
            head[name] = {"n_pairs": 0}
            continue
        head[name] = {
            "all": lp.paired_difference(ps),
            "mde": lp.measure_mde(ps, n_sim=args.mde_sims),
            "pre_cutoff": lp.paired_difference(stratum(ps, "pre_cutoff")),
            "recent": lp.paired_difference(stratum(ps, "recent")),
            "salient_outcomes": lp.paired_difference(salient(ps)),
            "did_pre_minus_recent": lp.difference_in_differences(
                stratum(ps, "pre_cutoff"), stratum(ps, "recent")),
            "did_mde": lp.measure_did_mde(stratum(ps, "pre_cutoff"),
                                          stratum(ps, "recent"),
                                          n_sim=max(args.mde_sims // 2, 60)),
            "mean_abs_probability_difference_between_arms": round(
                sum(p["dp"] for p in ps) / len(ps), 4),
            "by_observable": {
                o: lp.paired_difference([p for p in ps if p["observable"] == o])
                for o in sorted({p["observable"] for p in ps})},
            "by_horizon": {
                str(h): lp.paired_difference(
                    [p for p in ps if p["horizon_days"] == h])
                for h in sorted({p["horizon_days"] for p in ps})},
            "by_role": {
                r: lp.paired_difference([p for p in ps if p["role"] == r])
                for r in sorted({p["role"] for p in ps})},
        }

    # ── the model arm, corrected ────────────────────────────────────────────
    served_counts: dict[str, Counter] = defaultdict(Counter)
    for c in cells:
        served_counts[str(c.get("model_requested") or c.get("model"))][
            str(c.get("served_model"))] += 1
    model_arm = {
        "VOIDED_ARM": {
            "arm": "deepseek-chat vs deepseek-reasoner",
            "status": "VOID BY CONSTRUCTION — NEVER RUN",
            "why": ("`GET /models` returns exactly two ids, "
                    "deepseek-v4-flash and deepseek-v4-pro. Both "
                    "`deepseek-chat` and `deepseek-reasoner` are served by "
                    "v4-flash, so that arm would have compared one model with "
                    "itself. A null from it would have been manufactured by a "
                    "config error, and 'no model effect' would have been the "
                    "most confident possible way of reporting a bug."),
        },
        "served_model_verification": {k: dict(v)
                                      for k, v in sorted(served_counts.items())},
        "n_records_model_unverified": sum(
            1 for c in cells if c.get("status") == "ok"
            and c.get("model_unverified")),
        "flash_vs_pro_identified": (
            lp.paired_difference(pairs_flash_vs_pro) if pairs_flash_vs_pro
            else {"n_pairs": 0}),
        "flash_vs_pro_identified_mde": (
            lp.measure_mde(pairs_flash_vs_pro, n_sim=args.mde_sims)
            if pairs_flash_vs_pro else {"mde_at_80pct_power": None}),
        "flash_vs_pro_masked": (
            lp.paired_difference(pairs_flash_vs_pro_masked)
            if pairs_flash_vs_pro_masked else {"n_pairs": 0}),
        "thinking_on_vs_off_same_model": (
            lp.paired_difference(pairs_thinking) if pairs_thinking
            else {"n_pairs": 0}),
        "thinking_on_vs_off_mde": (
            lp.measure_mde(pairs_thinking, n_sim=args.mde_sims)
            if pairs_thinking else {"mde_at_80pct_power": None}),
        "thinking_depth": _thinking_depth(cells),
        "reading": ("the leakage question and the capability question are "
                    "different questions and are reported as two numbers, each "
                    "beside its own MDE (§18/§19)"),
    }

    # ── masking verification ────────────────────────────────────────────────
    mask_refused = sum(1 for c in cells if c["status"] == "refused_mask")
    ident = [c for c in canaries if c["kind"] == "identify" and c.get("parsed")]
    recall = [c for c in canaries if c["kind"] == "recall" and c.get("parsed")]

    def _year(p):
        try:
            return int(p.get("year") or 0)
        except (TypeError, ValueError):
            return 0
    id_rows = []
    for c in ident:
        p = c["parsed"] or {}
        got_t = str(p.get("ticker", "")).strip().upper()
        yr = _year(p)
        true_yr = int(str(c["as_of"])[:4])
        id_rows.append({"era": c["era"],
                        "ticker_named": got_t not in ("", "UNKNOWN", "N/A"),
                        "ticker_correct": got_t == c["ticker"],
                        "year_named": yr > 1900,
                        "year_exact": yr == true_yr,
                        "year_within_1": abs(yr - true_yr) <= 1 if yr > 1900 else False})

    def _agg_id(rows):
        if not rows:
            return {"n": 0}
        n = len(rows)
        return {"n": n,
                **{k: round(sum(1 for r in rows if r[k]) / n, 4)
                   for k in ("ticker_named", "ticker_correct", "year_named",
                             "year_exact", "year_within_1")},
                "n_ticker_correct": sum(1 for r in rows if r["ticker_correct"]),
                "n_year_exact": sum(1 for r in rows if r["year_exact"])}

    rec_rows = []
    for c in recall:
        p = c["parsed"] or {}
        said = str(p.get("recall", "")).strip().upper() == "YES"
        it = items.get(f"{c['ticker']}|{c['as_of']}")
        truth = None
        if it is not None:
            s = pd.to_numeric(panel[c["ticker"]], errors="coerce").dropna().loc[c["as_of"]:]
            if len(s) >= 21:
                truth = "UP" if float(s.iloc[20] / s.iloc[0] - 1) > 0 else "DOWN"
        d20 = str(p.get("direction_20d", "")).strip().upper()
        rec_rows.append({"era": c["era"], "recall_yes": said,
                         "directional": d20 in ("UP", "DOWN"),
                         "correct": bool(truth and d20 == truth)})

    def _agg_rec(rows):
        if not rows:
            return {"n": 0}
        n = len(rows)
        d = [r for r in rows if r["directional"]]
        return {"n": n,
                "share_claiming_recall": round(
                    sum(1 for r in rows if r["recall_yes"]) / n, 4),
                "share_giving_a_direction": round(len(d) / n, 4),
                "n_directional": len(d),
                "direction_accuracy_when_given": (
                    round(sum(1 for r in d if r["correct"]) / len(d), 4)
                    if d else None)}

    masking = {
        "cells_refused_before_the_wire": mask_refused,
        "identification_canary": {
            "all": _agg_id(id_rows),
            "pre_cutoff": _agg_id([r for r in id_rows if r["era"] == "pre_cutoff"]),
            "recent": _agg_id([r for r in id_rows if r["era"] == "recent"]),
            "reading": ("a masked prompt the model can name or date is not "
                        "masked; this is the porosity measurement AMNESIA-1 "
                        "made standard practice")},
        "recall_canary_positive_control": {
            "all": _agg_rec(rec_rows),
            "pre_cutoff": _agg_rec([r for r in rec_rows if r["era"] == "pre_cutoff"]),
            "recent": _agg_rec([r for r in rec_rows if r["era"] == "recent"]),
            "reading": ("'the mask worked' and 'there was nothing to mask' "
                        "look identical in aggregate; this separates them by "
                        "asking outright, with no suppression framing")},
    }

    # ── diversity ───────────────────────────────────────────────────────────
    def cond_rows(cond_prefix: str) -> list[dict]:
        return [c for c in cells if c["condition"].startswith(cond_prefix)]

    div: dict[str, Any] = {}
    for label, conds in (("temperature_0.0", ["temp_0.0"]),
                         ("temperature_0.4", ["temp_0.4"]),
                         ("temperature_1.0", ["temp_1.0"]),
                         ("model_v4-flash_thinking-off", ["core"]),
                         (f"model_v4-flash_thinking-on",
                          [f"model_{MODEL_FLASH}"]),
                         (f"model_v4-pro_thinking-on", [f"model_{MODEL_PRO}"]),
                         ("framing_bull", ["framing_bull"]),
                         ("framing_bear", ["framing_bear"]),
                         ("framing_baserate", ["framing_baserate"]),
                         ("framings_pooled(3 opposed instructions)",
                          ["framing_bull", "framing_bear", "framing_baserate"]),
                         ("roles_pooled(6 independent roles)", ["core", "panel"]),
                         ("adversarial_debate_NOT_INDEPENDENT",
                          ["debate_first", "debate_refute"])):
        rows = [c for c in cells if c["condition"] in conds
                and c["status"] == "ok" and c["arm"] == "identified"]
        preds = [{"ticker": c["ticker"], "observable": f["observable"],
                  "probability": f["probability"]}
                 for c in rows for f in c["forecasts"]]
        div[label] = {"n_calls": len(rows),
                      **lp.effective_distinct_ideas(preds),
                      "within_item_dispersion": lp.within_item_dispersion(rows)}

    # ── calibration ─────────────────────────────────────────────────────────
    def cal(rows: list[dict]) -> dict:
        c = lp.calibration_slice(rows)
        if rows:
            bb = sum(r["baseline_brier"] for r in rows) / len(rows)
            c["pit_baseline_brier"] = round(bb, 5)
            c["brier_minus_pit_baseline"] = round(c["brier"] - bb, 5)
            c["beats_pit_baseline"] = bool(c["brier"] < bb)
        return c

    core_recs = [r for r in recs if r["condition"] in ("core", "panel")]
    calib = {
        "all_core": cal(core_recs),
        "reliability_curve_all_core": lp.reliability_curve(core_recs),
        "by_arm": {a: cal([r for r in core_recs if r["arm"] == a])
                   for a in sorted({r["arm"] for r in core_recs})},
        "by_era": {e: cal([r for r in core_recs if r["era"] == e])
                   for e in sorted({r["era"] for r in core_recs})},
        "by_specialist": {s: cal([r for r in core_recs if r["role"] == s])
                          for s in sorted({r["role"] for r in core_recs})},
        "by_observable": {o: cal([r for r in core_recs if r["observable"] == o])
                          for o in sorted({r["observable"] for r in core_recs})},
        "by_horizon": {str(h): cal([r for r in core_recs
                                    if r["horizon_days"] == h])
                       for h in sorted({r["horizon_days"] for r in core_recs})},
        "by_specialist_x_observable": {
            f"{s}|{o}": cal([r for r in core_recs
                             if r["role"] == s and r["observable"] == o])
            for s in sorted({r["role"] for r in core_recs})
            for o in sorted({r["observable"] for r in core_recs})},
        "other_conditions": {
            c: cal([r for r in recs if r["condition"] == c])
            for c in sorted({r["condition"] for r in recs}
                            - {"core", "panel"})},
    }

    # ── spend ───────────────────────────────────────────────────────────────
    all_rows = tel.read_calls()
    mine = [r for r in all_rows
            if str(r.get("purpose", "")).startswith("leakage_probe")]
    cost = round(sum(float(r["cost_usd"]) for r in mine
                     if r.get("cost_usd") is not None), 5)
    status = Counter(c["status"] for c in cells)
    rejects: Counter = Counter()
    for c in cells:
        for r in c.get("rejections", []):
            rejects[r["reason"]] += 1

    n_resolved = len({r["cell_id"] + r["key"] for r in recs})
    art = {
        "campaign": "LLM-LEAKAGE-PROBE-1", "module": lp.MODULE_VERSION,
        "chunk": "GRAND-ARENA-1 chunk 3B",
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ARCHITECTURE_RESULT_ONLY": (
            "Every resolution here is HISTORICAL. Under Amendment A A5 and A6 "
            "these records may NOT set production specialist weights, may not "
            "arm a lane and certify nothing. They characterise the instrument. "
            "Forward records from 2026-08-16 remain the only certification "
            "path."),
        "design": {
            "eras": payload["era_windows"],
            "n_tickers": payload["n_tickers"],
            "n_dates": {"pre_cutoff": payload["n_dates_pre_cutoff"],
                        "recent": payload["n_dates_recent"]},
            "n_items": payload["n_items"],
            "slate": payload["slate"],
            "thinking_max_tokens": lp.THINKING_MAX_TOKENS,
            "models_real_ids": list(lp.REAL_MODELS),
            "search_denominator": {
                "arms_defined": ["identified", "masked", "deep_masked"],
                "conditions_defined": sorted({c["condition"] for c in cells}),
                "roles_defined": sorted(lp.ROLES),
                "primary_metric_frozen_before_any_call":
                    "paired Brier difference (identified - masked), and its "
                    "difference between eras",
                "n_headline_tests": 2,
                "note": ("the pre-registration froze ONE primary metric and "
                         "ONE headline estimator; every other cut in this "
                         "artifact is a REPORTED slice and none of them may be "
                         "promoted to the headline after the fact"),
            },
        },
        "calls": {
            "cells_attempted": len(cells),
            "ok": status["ok"], "abstained": status["abstained"],
            "zero_yield": status["zero_yield"],
            "refused_before_the_wire_for_a_mask_leak": status["refused_mask"],
            "failed": status["failed"],
            "canaries": len(canaries),
            "zero_yield_rate": (round(1 - status["ok"] / len(cells), 4)
                                if cells else None),
        },
        "rejections": dict(rejects.most_common()),
        "spend": {
            "campaign_cost_usd_PROVISIONAL": cost,
            "n_calls": len(mine),
            "resolved_forecast_records": len(recs),
            "cost_per_resolved_record_usd_PROVISIONAL": (
                round(cost / len(recs), 6) if recs else None),
            "pricing_as_of": cfg.LLM_PRICE_AS_OF,
            "is_estimate": True,
            "PROVISIONAL": (
                "Every dollar figure here is PROVISIONAL. The price table was "
                "keyed on `deepseek-chat`/`deepseek-reasoner`, which are not "
                "models but server-side aliases, and it was corrected mid-"
                "campaign. Rows written before the correction are priced at the "
                "old rates and rows after it at the new ones, so the ledger "
                "total mixes two price regimes. It is reconstructed from list "
                "prices, never from a billed amount, and the vendor balance is "
                "the only authority on what was actually spent."),
            "ledger_total_all_campaigns_usd_PROVISIONAL":
                tel.spend().get("total_cost_usd"),
        },
        "headline_identified_vs_masked": head,
        "model_arm": model_arm,
        "masking_verification": masking,
        "diversity": div,
        "calibration_vs_climatology": calib,
    }
    ARTIFACT.write_text(json.dumps(art, indent=1, default=str), encoding="utf-8")
    REPORT.write_text(_markdown(art), encoding="utf-8")
    print(f"wrote {REPORT} and {ARTIFACT}")
    return art


# ══ report ══════════════════════════════════════════════════════════════════

def _f(x, nd=4):
    if x is None:
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int,)):
        return str(x)
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return str(x)


def _pd_row(label: str, d: dict) -> str:
    if not d or d.get("n_pairs", 0) == 0:
        return f"| {label} | 0 | — | — | — | — |"
    return (f"| {label} | {d['n_pairs']} | {d.get('n_dates')} | "
            f"{_f(d.get('mean_difference_date_weighted'), 5)} | "
            f"{_f(d.get('se_used'), 5)} | {_f(d.get('t_stat'), 2)} |")


def _markdown(a: dict) -> str:
    L: list[str] = []
    A = a["headline_identified_vs_masked"]
    core = A.get("core_plus_panel_6_roles") or {}
    all_d = core.get("all") or {}
    mde = (core.get("mde") or {}).get("mde_at_80pct_power")
    did = core.get("did_pre_minus_recent") or {}
    did_mde = (core.get("did_mde") or {}).get("mde_at_80pct_power")

    L.append("# GRAND-ARENA-1 · Chunk 3B — LLM-LEAKAGE-PROBE-1\n")
    L.append(f"**Written {a['written_utc']} · {a['module']}**\n")
    L.append("> **ARCHITECTURE_RESULT_ONLY.** " + a["ARCHITECTURE_RESULT_ONLY"]
             + "\n")
    L.append("Pre-registration: `docs/TRIALS/TRIAL-LEAK-1-identified-vs-"
             "masked.md`, committed before the first call. Predecessor with "
             "receipts: **TRIAL-LLM-AMNESIA-1 / 1B** (2026-08-08), whose own "
             "retirement note asked for exactly this successor — shorter "
             "horizons, an outcome-salience stratum, canaries built in from the "
             "start, and a baseline bank so *no skill* can be told from *no "
             "signal*.\n")

    L.append("## The headline: does identity buy accuracy?\n")
    L.append("The paired unit is one **slot**: same security, same observation "
             "date, same role, same question, asked twice. Negative "
             "`Brier(identified) - Brier(masked)` means the identified arm was "
             "MORE accurate.\n")
    L.append("| slice | pairs | dates | mean ΔBrier | SE | t |\n"
             "|---|---|---|---|---|---|")
    for label, k in (("**all pairs**", "all"),
                     ("pre-cutoff era (2015–2023)", "pre_cutoff"),
                     ("recent era (2025–2026)", "recent"),
                     ("dramatic outcomes (|60d move| ≥ 20%)", "salient_outcomes")):
        L.append(_pd_row(label, core.get(k) or {}))
    L.append("")
    L.append(f"**Measured 80%-power MDE for the pooled gap: "
             f"{_f(mde, 4)} Brier points.** Anything smaller than this is NOT "
             f"DETECTABLE by this design and is never a kill (CANON §19).\n")
    if all_d.get("n_pairs"):
        L.append("Standard errors, all three, because they answer different "
                 "questions and the honest ruler is the widest:\n")
        L.append(f"- treating every slot as independent: "
                 f"{_f(all_d.get('se_iid_pairs'), 5)}\n"
                 f"- clustering by observation date: "
                 f"{_f(all_d.get('se_cluster_date'), 5)}\n"
                 f"- Newey-West on the date series (lag "
                 f"{all_d.get('nw_lag')}, for overlapping horizons): "
                 f"{_f(all_d.get('se_hac_date'), 5)}\n")

    L.append("### The estimator that actually isolates leakage\n")
    L.append("A masked prompt could score worse simply because it is stranger "
             "to read. That penalty is present in BOTH eras. Memory can only be "
             "present in the era the model was trained on. So the leakage "
             "estimate is the **difference of the two gaps**, tested as a "
             "difference with its own SE (CANON §18):\n")
    L.append("| quantity | value |\n|---|---|")
    L.append(f"| gap, pre-cutoff era | {_f(did.get('gap_a'), 5)} |")
    L.append(f"| gap, recent era | {_f(did.get('gap_b'), 5)} |")
    L.append(f"| **difference-in-differences** | "
             f"**{_f(did.get('difference_in_differences'), 5)}** |")
    L.append(f"| cluster-bootstrap SE | "
             f"{_f(did.get('se_cluster_bootstrap'), 5)} |")
    L.append(f"| t | {_f(did.get('t_stat'), 2)} |")
    L.append(f"| **measured 80%-power MDE** | **{_f(did_mde, 4)}** |")
    L.append(f"| pairs (pre / recent) | {did.get('n_a_pairs')} / "
             f"{did.get('n_b_pairs')} |\n")

    L.append("### The same test on the other arms\n")
    L.append("| arm | pairs | mean ΔBrier | SE | t | MDE |\n|---|---|---|---|---|---|")
    for label, k in (("core, 2 roles (v4-flash, thinking off)", "core_2_roles"),
                     ("core + panel, 6 roles", "core_plus_panel_6_roles"),
                     ("DEEP mask (identity + era stripped)", "deep_mask"),
                     ("`deepseek-v4-flash`, thinking ON", "v4_flash_thinking_on"),
                     ("`deepseek-v4-pro`, thinking ON", "v4_pro_thinking_on")):
        d = (A.get(k) or {}).get("all") or {}
        m = ((A.get(k) or {}).get("mde") or {}).get("mde_at_80pct_power")
        if not d.get("n_pairs"):
            L.append(f"| {label} | 0 | — | — | — | — |")
            continue
        L.append(f"| {label} | {d['n_pairs']} | "
                 f"{_f(d.get('mean_difference_date_weighted'), 5)} | "
                 f"{_f(d.get('se_used'), 5)} | {_f(d.get('t_stat'), 2)} | "
                 f"{_f(m, 4)} |")
    L.append("")

    L.append("## The model arm — and the arm that was VOID before it ran\n")
    ma = a["model_arm"]
    v = ma["VOIDED_ARM"]
    L.append(f"> **{v['arm']} — {v['status']}.** {v['why']}\n")
    L.append("`GET /models` on the live account returns exactly two ids. What "
             "was requested, and what was actually served:\n")
    L.append("| requested | served | calls |\n|---|---|---|")
    for req, served in ma["served_model_verification"].items():
        for s, n in served.items():
            L.append(f"| `{req}` | `{s}` | {n} |")
    L.append("")
    L.append(f"Records whose served model could not be read at all: "
             f"**{ma['n_records_model_unverified']}** (marked "
             f"`model_unverified`; a record credited to a model on the strength "
             f"of the name we typed is not evidence about that model).\n")
    L.append("### The real capability question, paired\n")
    L.append("| comparison | pairs | mean ΔBrier | SE | t | MDE |\n"
             "|---|---|---|---|---|---|")
    for label, dk, mk in (
            ("v4-flash − v4-pro, IDENTIFIED", "flash_vs_pro_identified",
             "flash_vs_pro_identified_mde"),
            ("v4-flash − v4-pro, MASKED", "flash_vs_pro_masked", None),
            ("thinking ON − OFF, same model (v4-flash)",
             "thinking_on_vs_off_same_model", "thinking_on_vs_off_mde")):
        d = ma.get(dk) or {}
        m = ((ma.get(mk) or {}).get("mde_at_80pct_power") if mk else None)
        if not d.get("n_pairs"):
            L.append(f"| {label} | 0 | — | — | — | — |")
            continue
        L.append(f"| {label} | {d['n_pairs']} | "
                 f"{_f(d.get('mean_difference_date_weighted'), 5)} | "
                 f"{_f(d.get('se_used'), 5)} | {_f(d.get('t_stat'), 2)} | "
                 f"{_f(m, 4) if mk else '—'} |")
    L.append("")
    L.append("### Thinking depth is not answer length\n")
    L.append("A thinking-on call does not fail by answering worse. It fails by "
             "answering **nothing**: the completion budget is spent entirely on "
             "reasoning tokens and the content comes back empty with "
             "`finish_reason=\"length\"`. Measured before the campaign at "
             "`max_tokens` 300, 600, 1500 and 3000 — `content_len=0` every "
             "time — so the thinking arms run at "
             f"`max_tokens={a['design'].get('thinking_max_tokens')}`.\n")
    L.append("| served model / thinking | calls | mean reasoning tok | mean "
             "completion tok | mean prompt tok | zero-yield |\n"
             "|---|---|---|---|---|---|")
    for k, d in (ma.get("thinking_depth") or {}).items():
        L.append(f"| `{k}` | {d['n_calls']} | {d['mean_reasoning_tokens']} | "
                 f"{d['mean_completion_tokens']} | {d['mean_prompt_tokens']} | "
                 f"{_f(d['share_zero_yield'], 4)} |")
    L.append("")

    L.append("## Did the mask actually mask?\n")
    m = a["masking_verification"]
    L.append(f"**{m['cells_refused_before_the_wire']} masked cell(s) were "
             f"REFUSED before the wire** because an identifier survived into "
             f"the rendered prompt. A refusal costs nothing; a leaked prompt "
             f"would have quietly turned the masked arm into a second "
             f"identified arm and biased the whole experiment toward *no "
             f"leakage*.\n")
    L.append("The masker is checked by `masking_violations`, which scans the "
             "rendered prompt for the item's own ticker, every scanned "
             "universe ticker of 3+ characters, the benchmark's name, every "
             "non-generic token of the company name, ISO dates, bare "
             "four-digit years, and the absolute price level. Pinned by "
             "`backend/tests/test_leakage_probe.py`.\n")
    L.append("### The porosity canary — can the model break the mask itself?\n")
    L.append("| stratum | n | names a ticker | ticker CORRECT | gives a year | "
             "year EXACT | year ±1 |\n|---|---|---|---|---|---|---|")
    for k in ("all", "pre_cutoff", "recent"):
        d = m["identification_canary"].get(k) or {}
        if not d.get("n"):
            L.append(f"| {k} | 0 | — | — | — | — | — |")
            continue
        L.append(f"| {k} | {d['n']} | {_f(d['ticker_named'], 3)} | "
                 f"{_f(d['ticker_correct'], 3)} ({d['n_ticker_correct']}) | "
                 f"{_f(d['year_named'], 3)} | {_f(d['year_exact'], 3)} "
                 f"({d['n_year_exact']}) | {_f(d['year_within_1'], 3)} |")
    L.append("")
    L.append("### The positive control — is there anything to mask?\n")
    L.append("*\"The mask worked\" and \"there was nothing to mask\" look "
             "identical in aggregate.* AMNESIA-1B separated them by asking "
             "outright, with no suppression framing. Same instrument here, at "
             "the horizons this campaign actually uses.\n")
    L.append("| stratum | n | claims recall | gives a direction | direction "
             "accuracy when given |\n|---|---|---|---|---|")
    for k in ("all", "pre_cutoff", "recent"):
        d = m["recall_canary_positive_control"].get(k) or {}
        if not d.get("n"):
            L.append(f"| {k} | 0 | — | — | — |")
            continue
        L.append(f"| {k} | {d['n']} | {_f(d['share_claiming_recall'], 3)} | "
                 f"{_f(d['share_giving_a_direction'], 3)} "
                 f"({d['n_directional']}) | "
                 f"{_f(d['direction_accuracy_when_given'], 3)} |")
    L.append("")

    L.append("## Does diversity exist at all?\n")
    L.append("LLM-SWARM-1's ratio was **0.2996** over 22,607 forecasts, and "
             "fourteen roles differed by a mean probability spread of **0.059**. "
             "With a FIXED slate the comparison is exact — same security, same "
             "date, same question — so `within-item dispersion` here is not the "
             "swarm's loose version of the number.\n")
    L.append("| condition | calls | forecasts | eff. distinct ideas | ratio | "
             "cells asked 2+ times | mean σ(p) | mean range | one 0.05 bucket |"
             "\n|---|---|---|---|---|---|---|---|---|")
    for k, d in a["diversity"].items():
        w = d.get("within_item_dispersion") or {}
        L.append(f"| `{k}` | {d['n_calls']} | {d.get('n_forecasts')} | "
                 f"{d.get('effective_distinct_ideas')} | {_f(d.get('ratio'),4)} | "
                 f"{w.get('n_cells_with_2plus', 0)} | "
                 f"{_f(w.get('mean_probability_stdev'), 4)} | "
                 f"{_f(w.get('mean_probability_range'), 4)} | "
                 f"{_f(w.get('share_of_cells_in_one_0_05_bucket'), 4)} |")
    L.append("")
    L.append("The **adversarial debate** row deliberately breaks independence: "
             "the second agent SEES the first's answer. It is labelled and is "
             "never pooled with the independent arms, because a panel that has "
             "read itself has an effective n of one however loudly it "
             "disagrees.\n")

    L.append("## Calibration — measurable at last, and against three bars\n")
    c = a["calibration_vs_climatology"]
    ac = c["all_core"]
    L.append("Because these resolve immediately, the programme can finally "
             "compute what it has never had. Three bars, not one: the slice's "
             "own climatology, and a **point-in-time baseline** — the trailing "
             "three-year frequency of that exact outcome across the same "
             "universe, computed from closes at or before the observation "
             "date. AMNESIA-1 could not tell *no skill* from *no signal*; the "
             "baseline is what separates them.\n")
    L.append(f"| slice | n | Brier | climatology | Δ | PIT baseline | Δ vs "
             f"baseline | base rate | mean p | overconfidence |\n"
             f"|---|---|---|---|---|---|---|---|---|---|")

    def calrow(label, d):
        if not d or not d.get("n"):
            return f"| {label} | 0 | — | — | — | — | — | — | — | — |"
        return (f"| {label} | {d['n']} | {_f(d['brier'])} | "
                f"{_f(d['climatology_brier'])} | "
                f"{_f(d['brier_minus_climatology'])} | "
                f"{_f(d.get('pit_baseline_brier'))} | "
                f"{_f(d.get('brier_minus_pit_baseline'))} | "
                f"{_f(d['base_rate'])} | {_f(d['mean_probability'])} | "
                f"{_f(d['overconfidence'])} |")

    L.append(calrow("**all core+panel**", ac))
    for name, group in (("arm", "by_arm"), ("era", "by_era"),
                        ("specialist", "by_specialist"),
                        ("observable", "by_observable"),
                        ("horizon", "by_horizon")):
        for k, d in (c.get(group) or {}).items():
            L.append(calrow(f"{name}: `{k}`", d))
    L.append("")
    L.append("### Specialist × observable\n")
    L.append("| slice | n | Brier | climatology | Δ | beats climatology |\n"
             "|---|---|---|---|---|---|")
    for k, d in (c.get("by_specialist_x_observable") or {}).items():
        if not d.get("n"):
            continue
        L.append(f"| `{k}` | {d['n']} | {_f(d['brier'])} | "
                 f"{_f(d['climatology_brier'])} | "
                 f"{_f(d['brier_minus_climatology'])} | "
                 f"{_f(d['beats_climatology'])} |")
    L.append("")
    L.append("### Reliability\n")
    L.append("| stated probability bin | n | mean p | realised frequency |\n"
             "|---|---|---|---|")
    for b in c["reliability_curve_all_core"]:
        L.append(f"| {b['bin']} | {b['n']} | {_f(b.get('mean_probability'))} | "
                 f"{_f(b.get('realised_frequency'))} |")
    L.append("")

    L.append("## What it cost, and what was refused\n")
    s = a["spend"]
    cl = a["calls"]
    L.append("| number | value |\n|---|---|")
    L.append(f"| cells attempted | {cl['cells_attempted']} |")
    L.append(f"| gradeable | {cl['ok']} |")
    L.append(f"| abstained | {cl['abstained']} |")
    L.append(f"| parsed but minted nothing | {cl['zero_yield']} |")
    L.append(f"| **refused before the wire (mask leak)** | "
             f"**{cl['refused_before_the_wire_for_a_mask_leak']}** |")
    L.append(f"| failed on the wire | {cl['failed']} |")
    L.append(f"| canary calls | {cl['canaries']} |")
    L.append(f"| zero-yield rate | {_f(cl['zero_yield_rate'], 4)} |")
    L.append(f"| campaign spend (**PROVISIONAL**, list prices "
             f"{s['pricing_as_of']}) | ${s['campaign_cost_usd_PROVISIONAL']} |")
    L.append(f"| resolved forecast records | {s['resolved_forecast_records']} |")
    L.append(f"| **cost per resolved record (PROVISIONAL)** | "
             f"${s['cost_per_resolved_record_usd_PROVISIONAL']} |")
    L.append(f"| ledger total, all campaigns (PROVISIONAL) | "
             f"${s['ledger_total_all_campaigns_usd_PROVISIONAL']} |\n")
    L.append("> " + s["PROVISIONAL"] + "\n")
    L.append("| rejection | n |\n|---|---|")
    for k, v in a["rejections"].items():
        L.append(f"| `{k}` | {v} |")
    L.append("")

    L.append("## The search denominator\n")
    sd = a["design"]["search_denominator"]
    L.append("```json\n" + json.dumps(sd, indent=1) + "\n```\n")
    L.append(f"Design: **{a['design']['n_items']} items** = "
             f"{a['design']['n_tickers']} securities × "
             f"{a['design']['n_dates']['pre_cutoff']} pre-cutoff dates + "
             f"{a['design']['n_dates']['recent']} recent dates, five fixed "
             f"questions each. 2024 is excluded on purpose: it is the band "
             f"where *has the model seen this* is genuinely unknown, and an "
             f"item whose stratum is uncertain contributes noise to the one "
             f"comparison this campaign exists to make.\n")

    L.append("## What this cannot tell us\n")
    L.append(
        "- **It cannot certify alpha, and it is not allowed to try.** Every "
        "resolution is historical. A5 forbids these records from setting "
        "specialist weights; A6 labels the whole class `ARCHITECTURE_RESULT_"
        "ONLY`. Forward records from 2026-08-16 are the only certification "
        "path, and this artifact does not shorten that wait by one day.\n"
        "- **It cannot prove the absence of leakage.** A null here is bounded "
        "by the MDE printed beside it, and by the fact that the masked arm "
        "still shows the model a market's volatility and a security's beta. A "
        "sufficiently determined memory could survive that. The DEEP-mask arm "
        "narrows the channel; it does not close it.\n"
        "- **It cannot separate *the model does not remember* from *the model "
        "remembers but the memory does not help*.** The recall canary "
        "addresses the first directly; where it reports near-zero recall, the "
        "second question does not arise, and where it reports recall the gap "
        "is the only evidence about whether it paid.\n"
        "- **The universe survives.** Securities were required to have "
        "continuous history from 2014 to 2026, so every name is one that "
        "existed throughout. That biases base rates upward and it biases the "
        "salient-outcome stratum away from the terminal collapses AMNESIA-1 "
        "found the model remembers best — which is the direction that makes "
        "leakage HARDER to detect, not easier.\n"
        "- **Era is a proxy, not a fact.** The training cutoff of "
        "`deepseek-chat` is not published, so 'pre-cutoff' and 'recent' are "
        "informed guesses with a deliberate 2024 gap between them. The recall "
        "canary's per-era split is the only empirical check on that "
        "assignment, and it is reported above.\n"
        "- **It cannot price itself.** Every dollar in this artifact is "
        "PROVISIONAL: the price table was keyed on names that turned out to be "
        "aliases and was corrected mid-campaign, so the ledger total mixes two "
        "price regimes and is a list-price reconstruction either way. Only the "
        "vendor balance knows what was spent.\n"
        "- **It says nothing about `deepseek-chat` versus `deepseek-reasoner`, "
        "because there is no such comparison to make.** Both are aliases for "
        "v4-flash. The arm the brief originally specified was void before it "
        "ran and was never run; had it run, its null would have been the most "
        "confident possible way of reporting a configuration bug.\n"
        "- **One model, many calls, is still one opinion.** Every diversity "
        "number is an `effective_distinct_ideas` count for exactly this "
        "reason (CANON §20).\n"
        "- **Nothing here says the specialist architecture is worth its cost.** "
        "That is A4's ladder and chunk 7's job.\n")
    return "\n".join(L)


# ══ main ════════════════════════════════════════════════════════════════════

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--wave", default="")
    ap.add_argument("--resolve", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--workers", type=int, default=cfg.SWARM_WORKERS)
    ap.add_argument("--tickers", type=int, default=20)
    ap.add_argument("--dates-p", type=int, default=30)
    ap.add_argument("--dates-r", type=int, default=24)
    ap.add_argument("--panel-items", type=int, default=240)
    ap.add_argument("--deep-items", type=int, default=400)
    ap.add_argument("--div-items", type=int, default=180)
    ap.add_argument("--model-items", type=int, default=200)
    ap.add_argument("--canary-items", type=int, default=540)
    ap.add_argument("--limit", type=int, default=None,
                    help="cap cells planned in this wave")
    ap.add_argument("--mde-sims", type=int, default=400)
    args = ap.parse_args()

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    since = str(date.today())

    if args.build:
        build_items(args)
        return 0
    if args.report_only:
        analyse(args)
        return 0
    if args.resolve:
        resolve(args)
        analyse(args)
        return 0
    if not args.wave:
        ap.error("nothing to do: pass --build, --wave, --resolve or "
                 "--report-only")

    payload = json.loads(ITEMS_FILE.read_text(encoding="utf-8"))
    items = {it["item_id"]: it for it in payload["items"]}
    _ITEM_BY_ID.update(items)
    args.scan_tickers = payload["tickers"]

    st = research_budget.check(lp.CAMPAIGN, since=since)
    print(f"budget at start: {st.as_dict()}", flush=True)
    if not st.ok:
        print(f"REFUSING TO START — {st.reason}")
        return 2

    for wave in [w.strip() for w in args.wave.split(",") if w.strip()]:
        print(f"\n═══ wave {wave} ═══", flush=True)
        if wave == "canary":
            out = run_canaries(items, args, since)
        else:
            cells = plan_wave(wave, list(items.values()), args)
            if args.limit:
                cells = cells[:args.limit]
            out = run_cells(cells, items, args, since)
        META_FILE.write_text(json.dumps(
            {"last_wave": wave, "at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"), "result": out}, indent=1, default=str),
            encoding="utf-8")
        if out.get("halted"):
            print("governor halted the campaign — stopping cleanly")
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
